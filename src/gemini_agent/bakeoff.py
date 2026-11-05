"""Open-weight model bake-off: single-call micro-tasks, scored deterministically.

Each task is one LLM call with the real agent system prompt and tool schemas
(same prefix for every task -> Ollama prompt-cache reuse). Scores are 0/1 by
deterministic rules; tokens and latency come from the provider's usage data.

  PYTHONPATH=src python -m gemini_agent.bakeoff qwen2.5:1.5b-instruct qwen3:4b ...
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from gemini_agent.agents import LEAN_SUFFIX, PKG_WS, SYSTEM_PROMPT, make_model, skill_index
from gemini_agent.ledger import FactLedger, provenance_check
from gemini_agent.tools import Session, build_tools

DEEP_RES = {
    "fact_id": "F7",
    "design_id": "45efd720d9",
    "label": "2x doublet @ 3100 m, ElCh 10 MW, gas boiler 18 MW",
    "feasible": True,
    "lcoe_eur_per_mwh": 43.18,
    "co2_t_per_year": 6190.0,
    "capex_meur": 47.79,
    "geothermal_share_of_heat_pct": 99.15,
}
HP_RES = {
    "fact_id": "F8",
    "design_id": "f5949cdcf5",
    "label": "2x doublet @ 2500 m, HP 10 MW, ElCh 10 MW, gas boiler 12 MW",
    "feasible": True,
    "lcoe_eur_per_mwh": 53.46,
    "co2_t_per_year": 5046.0,
    "capex_meur": 48.43,
    "geothermal_share_of_heat_pct": 99.97,
}
STRESS_FAIL = {
    "fact_id": "F9",
    "scenario": "demand_plus_10",
    "feasible": False,
    "violations": ["cooling_demand_met_all_365_days"],
    "unmet_heat_mwh": 0.0,
    "unmet_cool_mwh": 92.4,
}


def _ctx(user: str, tool_results: list[tuple[str, dict]] | None = None):
    """Conversation with optional prior tool calls/results already in context."""
    msgs = [HumanMessage(user)]
    for i, (name, res) in enumerate(tool_results or []):
        msgs.append(AIMessage("", tool_calls=[{"name": name, "args": {}, "id": f"c{i}"}]))
        msgs.append(ToolMessage(json.dumps(res), tool_call_id=f"c{i}"))
    return msgs


def _calls(msg) -> list[dict]:
    return [
        {"name": tc["name"], "args": tc.get("args", {})}
        for tc in (getattr(msg, "tool_calls", None) or [])
    ]


def _text(msg) -> str:
    c = msg.content
    return c if isinstance(c, str) else "".join(b.get("text", "") for b in c if isinstance(b, dict))


TASKS = [
    {
        "id": "T1_plan_starts_with_requirements",
        "skill": "tool selection / planning",
        "messages": _ctx(
            "Design a geothermal heating and cooling system for the supplied demand profiles."
        ),
        "score": lambda m: any(
            c["name"]
            in {
                "get_brief",
                "analyze_demand",
                "write_todos",
                "list_gemini_models",
                "read_file",
                "task",
            }
            for c in _calls(m)
        ),
    },
    {
        "id": "T2_exact_parameter_extraction",
        "skill": "structured tool call",
        "messages": _ctx(
            "Evaluate a design: 2 doublets at 3100 m, no heat pump, 10 MW electric chiller, "
            "18 MW gas backup boiler, gas kept in solution and reinjected."
        ),
        "score": lambda m: any(
            c["name"] == "evaluate_design"
            and float(c["args"].get("well_depth_m", 0)) == 3100
            and int(c["args"].get("n_doublets", 0)) == 2
            and float(c["args"].get("electric_chiller_mw", 0)) == 10
            and float(c["args"].get("backup_boiler_mw", 0)) == 18
            and float(c["args"].get("heat_pump_mw", 0) or 0) == 0
            for c in _calls(m)
        ),
    },
    {
        "id": "T3_refuse_infeasible_flow",
        "skill": "constraint awareness",
        "messages": _ctx("Run each doublet at 500 m3/h so we need fewer wells. Evaluate that."),
        "score": lambda m: not any(
            c["name"] == "evaluate_design" and float(c["args"].get("max_flow_m3h", 0)) > 300
            for c in _calls(m)
        )
        and (
            bool(_calls(m))
            and all(c["name"] in {"get_brief", "ask_user", "read_file"} for c in _calls(m))
            or "300" in _text(m)
        ),
    },
    {
        "id": "T4_off_topic",
        "skill": "scope guard",
        "messages": _ctx("What will the weather be in Delft tomorrow?"),
        "score": lambda m: not _calls(m) and len(_text(m)) > 0,
    },
    {
        "id": "T5_missing_input_question",
        "skill": "missing-input detection",
        "messages": _ctx("Make the design cheaper."),
        "score": lambda m: any(
            c["name"] in {"ask_user", "get_brief", "search_designs", "read_file"} for c in _calls(m)
        )
        or "?" in _text(m),
    },
    {
        "id": "T6_grounded_numbers",
        "skill": "no hallucination",
        "messages": _ctx(
            "What are the LCOE and the annual CO2 of this design? Cite the fact ID.",
            [("evaluate_design", DEEP_RES)],
        ),
        "score": "provenance",
    },
    {
        "id": "T7_compare_alternatives",
        "skill": "engineering reasoning",
        "messages": _ctx(
            "Which of the two designs is cheaper per MWh and which emits less CO2? Answer with "
            "the design IDs and fact IDs.",
            [("evaluate_design", DEEP_RES), ("evaluate_design", HP_RES)],
        ),
        "score": lambda m: "45efd720d9" in _text(m)
        and "f5949cdcf5" in _text(m)
        and _text(m).find("45efd720d9") < _text(m).find("f5949cdcf5") + 10_000,
    },
    {
        "id": "T8_react_to_failed_stress_test",
        "skill": "self-correction",
        "messages": _ctx(
            "Stress-test result attached. What do you do next?",
            [("stress_test_design", STRESS_FAIL)],
        ),
        "score": lambda m: any(
            c["name"] in {"add_capacity_margin", "evaluate_design"} for c in _calls(m)
        )
        or "margin" in _text(m).lower()
        or "chiller" in _text(m).lower(),
    },
]


def run_model(model: str, out_dir: Path) -> dict:
    """Run all tasks for one model."""
    session = Session(run_dir=out_dir / "session", mode="interactive")
    tools = build_tools(session)
    system = SYSTEM_PROMPT + LEAN_SUFFIX + "\n\n" + skill_index(PKG_WS)
    llm = make_model(model, num_ctx=8192).bind_tools(tools)
    led = FactLedger()
    led.record("evaluate_design", {}, DEEP_RES)
    rows = []
    for t in TASKS:
        t0 = time.time()
        try:
            msg = llm.invoke([SystemMessage(system)] + t["messages"])
            err = None
        except Exception as exc:  # count as failure
            msg, err = AIMessage(f"ERROR {exc!r}"), repr(exc)
        dt = time.time() - t0
        if t["score"] == "provenance":
            pv = provenance_check(_text(msg), led)
            ok = pv["passed"] and pv["numbers_checked"] >= 2 and "43" in _text(msg)
        else:
            ok = bool(t["score"](msg))
        usage = getattr(msg, "usage_metadata", None) or {}
        rows.append(
            {
                "task": t["id"],
                "skill": t["skill"],
                "pass": ok,
                "latency_s": round(dt, 1),
                "prompt_tokens": usage.get("input_tokens", 0),
                "completion_tokens": usage.get("output_tokens", 0),
                "tool_calls": _calls(msg),
                "text": _text(msg)[:600],
                "error": err,
            }
        )
        print(f"{model:24s} {t['id']:34s} {'PASS' if ok else 'fail'} {dt:6.1f}s", flush=True)
        res = _summarise(model, rows)  # saved after every task: long CPU runs may be interrupted
        (out_dir / f"{model.replace(':', '_').replace('/', '_')}.json").write_text(
            json.dumps(res, indent=1)
        )
    return res


def _summarise(model: str, rows: list[dict]) -> dict:
    return {
        "model": model,
        "score": sum(r["pass"] for r in rows),
        "n": len(rows),
        "complete": len(rows) == len(TASKS),
        "mean_latency_s": round(sum(r["latency_s"] for r in rows) / len(rows), 1),
        "prompt_tokens": sum(r["prompt_tokens"] for r in rows),
        "completion_tokens": sum(r["completion_tokens"] for r in rows),
        "tasks": rows,
    }


def unload(model: str):
    """Ask Ollama to drop a model from memory now."""
    import os
    import urllib.request

    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    req = urllib.request.Request(
        f"{host}/api/generate",
        data=json.dumps({"model": model, "keep_alive": 0}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=60).read()
    except Exception:  # noqa: BLE001 -- best effort
        pass


def main(models: list[str]):
    """Run the bake-off for the given Ollama models."""
    out = Path("runs/bakeoff")
    out.mkdir(parents=True, exist_ok=True)
    summary = []
    for m in models:
        summary.append(run_model(m, out))
        unload(m)  # one model in RAM at a time (12 GB VM: a 4B + 7B pair is OOM-killed)
    for r in summary:
        print(
            f"{r['model']:24s} score {r['score']}/{r['n']}  mean {r['mean_latency_s']} s  "
            f"tokens {r['prompt_tokens']}+{r['completion_tokens']}"
        )


if __name__ == "__main__":
    main(sys.argv[1:] or ["qwen2.5:1.5b-instruct"])
