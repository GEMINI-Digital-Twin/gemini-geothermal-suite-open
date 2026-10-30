"""Compare LLM backends on the same agent cases (same tools, prompt and physics gate).

Each backend runs cases A1-A6 ``--repeats`` times in a fresh workspace and is
scored on behaviour, physics-gate outcome, agreement with a reference design
run, tokens, tool calls, wall time and cost.

Backends are given as ``label=provider:model`` (``model`` may itself contain
colons), or ``scripted`` for the offline stand-in policy::

    # local open-weight model on Ollama + GPT-6 Luna on the OpenAI API
    $env:PYTHONPATH="src"
    $env:OPENAI_API_KEY="sk-..."   # only for the openai backend
    python simulator_examples/compare_agent_models.py `
        --backend qwen3-8b=ollama:qwen3:8b --backend gpt-6-luna=openai:gpt-6-luna `
        --price gpt-6-luna=1.25,10 --repeats 3

Writes ``simulator_examples/outputs/agent_compare/``: ``results.csv`` and
``results.json`` (one row per backend x case x repeat), ``summary.md`` (per
backend), and every transcript under ``<label>/r<k>/transcripts/``.
"""

import argparse
import csv
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

from gemini_agent.agent import DesignAgent
from gemini_agent.config import AgentConfig
from gemini_agent.llm import ScriptedLLM
from gemini_agent.memory import ProjectNotes, RunLedger
from gemini_agent.scenarios import SCENARIOS, check_behaviour, scripted_steps
from gemini_agent.tools import ToolBox
from gemini_design.challenge import load_demand

OUT = Path(__file__).parent / "outputs" / "agent_compare"
INPUTS = Path(__file__).parent / "hackathon_inputs"

CASES = {
    "A1": "01_design_brief_incomplete",  # full design request
    "A2": "03_incomplete_whatif",  # incomplete request, must ask
    "A3": "02_offtopic_weather",  # off-topic, must decline without tools
    "A4": "04_hallucination_caught",  # invites an invented number
    "A5": "06_write_missing_model",  # write a missing model
    "A6": "05_uncertainty_permeability",  # what-if / uncertainty
}
REFERENCE = {
    "n_doublets": 2,
    "depth_m": 3100,
    "upgrade": "boiler",
    "cooling": "electric",
    "chp": True,
}
FALLBACK_ANSWER = "I don't have that information; please go ahead with your stated defaults."
MAX_TURNS = 4
_RUN_ID = re.compile(r"\bR\d{4}\b")


def parse_backend(spec):
    """``label=provider:model`` -> (label, provider, model); ``scripted`` -> scripted."""
    if spec == "scripted":
        return "scripted", "scripted", None
    label, _, rest = spec.partition("=")
    provider, _, model = rest.partition(":")
    if not label or not provider:
        raise ValueError(f"backend must look like label=provider:model, got '{spec}'")
    return label, provider, model or None


def reference_run():
    """Run the reference design once; return its headline."""
    ws = OUT / "_reference"
    shutil.rmtree(ws, ignore_errors=True)
    tb = ToolBox(load_demand(INPUTS), RunLedger(ws), ProjectNotes(ws), ws, workers=1)
    head = tb.call("run_design", dict(REFERENCE))
    print(
        f"Reference: {head['design']} {head['lcoe_eur_per_mwh']} EUR/MWh [{head['physics_gate']}]"
    )
    return head


def run_case(label, provider, model, case, repeat, reference, prices):
    """Run one case once; return a result row."""
    key = CASES[case]
    ws = OUT / label / f"r{repeat}"
    overrides = {"workspace": str(ws)}
    if provider != "scripted":
        overrides.update(provider=provider, model=model)
        if provider == "openai" and os.environ.get("OPENAI_API_KEY"):
            overrides["api_key"] = os.environ["OPENAI_API_KEY"]
    config = AgentConfig.load(None, **overrides)
    if provider == "scripted":
        llm, meta = ScriptedLLM(scripted_steps(key)), {"backend_note": "SCRIPTED stand-in"}
        meta["model"] = "scripted-policy"
    else:
        llm, meta = None, {"backend_note": f"live LLM ({label})"}
    agent = DesignAgent(config, llm=llm, session_name=f"{case}_{key}", meta=meta)

    t0 = time.time()
    replies = []
    turns = list(SCENARIOS[key]["turns"])
    for _ in range(MAX_TURNS):
        text = turns.pop(0) if turns else FALLBACK_ANSWER
        reply = agent.ask(text)
        replies.append(reply)
        if reply.kind != "question":
            break
    wall = time.time() - t0
    agent.close()
    events = agent.transcript.events
    totals = agent.transcript.totals()
    final = replies[-1]

    cited = [r for r in _RUN_ID.findall(final.text) if r in agent.ledger.entries]
    designs = [agent.ledger.get(r)["headline"].get("design") for r in cited]
    designs = [d for d in designs if d]
    lcoes = [agent.ledger.get(r)["headline"].get("lcoe_eur_per_mwh") for r in cited]
    lcoes = [x for x in lcoes if x is not None]
    selected = designs[0] if designs else ""
    ref_lcoe = reference["lcoe_eur_per_mwh"]
    rejections = sum(1 for e in events if e["kind"] == "gate_reject")
    tool_errors = sum(1 for e in events if e["kind"] == "tool" and '"error"' in e["result_preview"])
    price_in, price_out = prices.get(label, (0.0, 0.0))
    cost = (totals["prompt_tokens"] * price_in + totals["completion_tokens"] * price_out) / 1e6
    failed = check_behaviour(key, replies, events)
    return {
        "backend": label,
        "provider": provider,
        "model": model or "scripted-policy",
        "case": case,
        "scenario": key,
        "repeat": repeat,
        "final_reply": final.kind,
        "final_answer_passed_gates": final.kind == "answer",
        "behaviour_ok": not failed,
        "behaviour_failures": "; ".join(failed),
        "asked_for_missing_input": replies[0].kind == "question",
        "declined_without_tools": case == "A3"
        and final.kind == "answer"
        and not any(e["kind"] == "tool" for e in events),
        "gate_rejections": rejections,
        "rejections_fixed": rejections if final.kind == "answer" else 0,
        "invalid_tool_calls": tool_errors,
        "selected_design": selected,
        "selected_lcoe_eur_per_mwh": lcoes[0] if lcoes else "",
        "matches_reference_design": selected == reference["design"] if case == "A1" else "",
        "lcoe_within_1pct_of_reference": (
            abs(lcoes[0] - ref_lcoe) <= 0.01 * ref_lcoe if case == "A1" and lcoes else ""
        ),
        "llm_calls": totals["llm_calls"],
        "tool_calls": totals["tool_calls"],
        "prompt_tokens": totals["prompt_tokens"],
        "completion_tokens": totals["completion_tokens"],
        "reasoning_tokens": totals["reasoning_tokens"],
        "tokens_estimated": any(e.get("estimated") for e in events if e["kind"] == "llm"),
        "llm_seconds": totals["llm_seconds"],
        "wall_seconds": round(wall, 1),
        "cost_usd": round(cost, 4),
        "final_text": final.text,
        "transcript": str(agent.transcript.folder / f"{case}_{key}.md"),
    }


def summarise(rows):
    """Per-backend aggregates as Markdown."""
    by = {}
    for r in rows:
        by.setdefault(r["backend"], []).append(r)
    lines = [
        "# Agent backend comparison",
        "",
        "| backend | runs | gated answers | behaviour ok | A1 design match | gate rejections "
        "(fixed) | invalid tool calls | prompt tok | completion tok | wall s | cost USD |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for label, rs in by.items():
        a1 = [r for r in rs if r["case"] == "A1"]
        lines.append(
            f"| {label} | {len(rs)} | {sum(r['final_answer_passed_gates'] for r in rs)} | "
            f"{sum(r['behaviour_ok'] for r in rs)} | "
            f"{sum(bool(r['matches_reference_design']) for r in a1)}/{len(a1)} | "
            f"{sum(r['gate_rejections'] for r in rs)} ({sum(r['rejections_fixed'] for r in rs)}) | "
            f"{sum(r['invalid_tool_calls'] for r in rs)} | "
            f"{sum(r['prompt_tokens'] for r in rs)} | {sum(r['completion_tokens'] for r in rs)} | "
            f"{sum(r['wall_seconds'] for r in rs):.0f} | {sum(r['cost_usd'] for r in rs):.3f} |"
        )
    lines += ["", "Per case (mean over repeats):", ""]
    lines += [
        "| backend | case | behaviour ok | prompt tok | completion tok | tool calls | wall s |",
        "|---|---|---|---|---|---|---|",
    ]
    for label, rs in by.items():
        for case in CASES:
            cs = [r for r in rs if r["case"] == case]
            if not cs:
                continue
            n = len(cs)
            lines.append(
                f"| {label} | {case} | {sum(r['behaviour_ok'] for r in cs)}/{n} | "
                f"{sum(r['prompt_tokens'] for r in cs) / n:.0f} | "
                f"{sum(r['completion_tokens'] for r in cs) / n:.0f} | "
                f"{sum(r['tool_calls'] for r in cs) / n:.1f} | "
                f"{sum(r['wall_seconds'] for r in cs) / n:.0f} |"
            )
    return "\n".join(lines) + "\n"


def main(argv=None):
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--backend", action="append", required=True, help="label=provider:model")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--cases", nargs="*", default=list(CASES))
    parser.add_argument(
        "--price", action="append", default=[], help="label=usd_per_M_in,usd_per_M_out"
    )
    parser.add_argument("--keep", action="store_true", help="append to earlier results")
    args = parser.parse_args(argv)

    prices = {}
    for p in args.price:
        label, _, nums = p.partition("=")
        price_in, price_out = (float(x) for x in nums.split(","))
        prices[label] = (price_in, price_out)
    backends = [parse_backend(b) for b in args.backend]

    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    results_json = OUT / "results.json"
    if args.keep and results_json.exists():
        rows = json.loads(results_json.read_text())
    reference = reference_run()
    for label, provider, model in backends:
        if not args.keep:
            shutil.rmtree(OUT / label, ignore_errors=True)
        for repeat in range(1, args.repeats + 1):
            for case in args.cases:
                print(f"\n=== {label} r{repeat} {case} ({CASES[case]})")
                row = run_case(label, provider, model, case, repeat, reference, prices)
                print(
                    f"-> {row['final_reply']}, behaviour ok {row['behaviour_ok']}, "
                    f"{row['prompt_tokens']}+{row['completion_tokens']} tok, "
                    f"{row['wall_seconds']} s"
                )
                rows.append(row)
                _write(rows, reference)
    print(f"\nResults: {OUT / 'results.csv'}\nSummary: {OUT / 'summary.md'}")
    return 0


def _write(rows, reference):
    (OUT / "results.json").write_text(json.dumps(rows, indent=1, default=str))
    with (OUT / "results.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = summarise(rows)
    summary += (
        f"\nReference run: {reference['design']} at {reference['lcoe_eur_per_mwh']} EUR/MWh "
        f"({reference['run_id']}).\n"
    )
    (OUT / "summary.md").write_text(summary, encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
