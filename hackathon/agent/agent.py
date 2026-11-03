"""Agent loop: plan -> tool call -> observe -> revise -> compare -> finish.

Run from the repo root:
    PYTHONPATH=. python -m hackathon.agent.agent                 # routing from llm_config.yaml
    PYTHONPATH=. python -m hackathon.agent.agent --routing local_only
    PYTHONPATH=. python -m hackathon.agent.agent --scripted      # offline demo, 0 tokens

Each run writes to hackathon/runs/<timestamp>/:
    llm_log.jsonl      every call: full prompt, answer, tokens, cost
    transcript.md      readable step-by-step record
    D*_daily.csv       daily tables of each evaluated design
    final_design.json  chosen design with the agent's justification
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

from .llm_client import ChatModel, ScriptedLLM, TokenLog, load_env, load_llm_config
from .tools import TOOL_SCHEMAS, Session, call_tool

RUNS = Path(__file__).resolve().parents[1] / "runs"

SYSTEM_PROMPT = """You are a geothermal energy-system design engineer working with the GEMINI
geothermal digital twin through tools.

Goal: design an integrated system that meets the daily heating (100 C supply) and cooling
(20 C supply) demand on all 365 days, using deep geothermal for direct heating and, where
possible, to drive cooling. Objective: the lowest expected (P50) levelised cost, with the design
feasible in at least 90% of uncertainty samples. Report P10/P50/P90 with P90 as the conservative
case.

Rules:
- Every number must come from a tool. Never invent or estimate results yourself.
- GEMINI does not cover everything this design needs. Find out what is missing and connect
  what you need.
- Explore genuinely different alternatives (for example depth, number of doublets, well
  spacing, heat pump versus deeper wells, chiller type, return temperature). Fix hard
  violations by revising the design; respond to warnings where reasonable.
- Justify the final choice against the alternatives with numbers from the tools, including
  its downside risk (P90) and its sensitivity to the heating return temperature.
- Keep each message short: say what you will do next and why, then call a tool."""


class Router:
    """Chooses the route per step: API for planning, recovery and the final step."""

    def __init__(self, routing, models):
        self.routing, self.models = routing, models
        self.force_api_next = True  # first step is planning

    def pick(self, step, max_steps):
        if self.routing == "api_only" or "local" not in self.models:
            return self.models["api"]
        if self.routing == "local_only" or "api" not in self.models:
            return self.models["local"]
        if self.force_api_next or step >= max_steps - 3:
            self.force_api_next = False
            return self.models["api"]
        return self.models["local"]

    def observe(self, tool_name, result):
        hard = isinstance(result, dict) and any(
            (v.get("severity") == "hard") if isinstance(v, dict) else str(v).startswith("hard")
            for v in result.get("violations", []))
        rejected = isinstance(result, dict) and result.get("accepted") is False
        repeat = isinstance(result, dict) and result.get("repeat") is True   # L2
        if hard or rejected or repeat or (isinstance(result, dict) and "error" in result) \
                or tool_name in ("compare_candidates", "robustness_check"):
            self.force_api_next = True


def run(llm_by_route, routing="hybrid", max_steps=20, budget_usd=0.5, task=None, run_dir=None):
    run_dir = Path(run_dir or RUNS / datetime.now().strftime("%Y%m%d_%H%M%S"))
    session = Session(run_dir)
    log = next(iter(llm_by_route.values())).log
    router = Router(routing, llm_by_route)
    messages = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": task or "Design the system and report the final choice."}]
    md = [f"# Agent run {run_dir.name}\n", f"Routing: {routing}\n"]
    try:
        _loop(session, log, router, messages, md, max_steps, budget_usd)
    except Exception as exc:  # keep the evidence: transcript and totals are written anyway
        md.append(f"\n**Run stopped by an error: {type(exc).__name__}: {exc}**\n")
        raise
    finally:
        _write_outputs(run_dir, log, md)
    return session, run_dir


# Loop guard (P4). Tools whose output can legitimately change for the same arguments are
# exempt from repeat detection.
REPEAT_EXEMPT = {"compare_candidates", "finish"}
MAX_REPEAT_STEPS = 3  # method choice: stop after this many consecutive all-repeat steps


def _loop(session, log, router, messages, md, max_steps, budget_usd):
    seen = {}          # (tool, canonical args) -> compact result text (L1)
    repeat_steps = 0   # consecutive steps in which every call was a repeat (L3)
    for step in range(max_steps):
        model = router.pick(step, max_steps)
        msg = model.chat(messages, tools=TOOL_SCHEMAS, step=step)
        msg = {k: v for k, v in msg.items() if k in ("role", "content", "tool_calls")}
        msg["role"] = "assistant"
        messages.append(msg)
        md.append(f"\n## Step {step + 1} ({model.name})\n")
        if msg.get("content"):
            md.append(f"**Agent:** {msg['content']}\n")
        calls = msg.get("tool_calls") or []
        if not calls:
            messages.append({"role": "user", "content": "Continue by calling a tool. "
                             "Use finish when the design is final."})
            continue
        n_repeats = 0
        for tc in calls:
            name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args, result = {}, {"error": "arguments were not valid JSON"}
                key = None
            else:
                key = (name, json.dumps(args, sort_keys=True))
                if name not in REPEAT_EXEMPT and key in seen:   # L1: do not re-run, point back
                    n_repeats += 1
                    result = {"repeat": True,
                              "note": f"identical {name} call already made; the result is unchanged. "
                                      "Try a genuinely different design, or move on "
                                      "(robustness_check, return_temperature_sensitivity, finish).",
                              "earlier_result": json.loads(seen[key])}
                else:
                    result = call_tool(session, name, args)
            router.observe(name, result)
            text = json.dumps(result, default=str, separators=(",", ":"))  # compact (P3)
            if key is not None and not (isinstance(result, dict) and result.get("repeat")):
                seen[key] = text
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": text})
            md.append(f"- **Tool** `{name}({json.dumps(args)})`\n\n  ```json\n  {text[:1500]}\n  ```\n")
        repeat_steps = repeat_steps + 1 if n_repeats == len(calls) else 0
        if repeat_steps >= MAX_REPEAT_STEPS:                       # L3
            md.append(f"\n**Stopped: loop detected ({repeat_steps} consecutive steps repeating "
                      f"earlier tool calls).**\n")
            break
        if session.final:
            md.append(f"\n## Final design: {session.final['candidate_id']}\n\n"
                      f"{session.final['justification']}\n")
            break
        if log.totals["cost_usd"] > budget_usd:
            md.append(f"\n**Stopped: estimated cost {log.totals['cost_usd']:.3f} USD over budget.**\n")
            break


def _write_outputs(run_dir, log, md):
    t = log.totals
    md.append(f"\n## Token use\n\nCalls {t['calls']}, prompt tokens {t['prompt_tokens']}, "
              f"completion tokens {t['completion_tokens']}, estimated cost {t['cost_usd']:.4f} USD\n")
    for m, s in t["by_model"].items():
        md.append(f"- {m}: {s['calls']} calls, {s['prompt_tokens']} in, "
                  f"{s['completion_tokens']} out, {s['cost_usd']:.4f} USD\n")
    (run_dir / "transcript.md").write_text("".join(md), encoding="utf-8")
    with open(run_dir / "token_totals.json", "w", encoding="utf-8") as f:
        json.dump(t, f, indent=2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--routing", choices=["hybrid", "api_only", "local_only"])
    ap.add_argument("--scripted", action="store_true", help="offline demo with a fixed script")
    ap.add_argument("--max-steps", type=int)
    ap.add_argument("--local-model", help="override the local Ollama model id, e.g. qwen3.5:9b")
    ap.add_argument("--api-model", help="override the API model id")
    a = ap.parse_args()
    cfg = load_llm_config()
    run_dir = RUNS / datetime.now().strftime("%Y%m%d_%H%M%S")
    log = TokenLog(run_dir / "llm_log.jsonl")
    if a.scripted:
        from .demo_script import demo_script
        models = {"api": ScriptedLLM(demo_script(), log)}
        routing = "api_only"
    else:
        load_env()
        if a.local_model:
            cfg["routes"]["local"]["model"] = a.local_model
        if a.api_model:
            cfg["routes"]["api"]["model"] = a.api_model
        models = {n: ChatModel(n, r, log, cfg.get("temperature", 0.2))
                  for n, r in cfg["routes"].items()}
        routing = a.routing or cfg.get("routing", "hybrid")
    session, out = run(models, routing=routing, max_steps=a.max_steps or cfg.get("max_iterations", 20),
                       budget_usd=cfg.get("budget_usd_per_run", 0.5), run_dir=run_dir)
    print(f"Run folder: {out}")
    print(f"Final: {session.final['candidate_id'] if session.final else 'none'}")
    print(f"Tokens: {log.totals}")


if __name__ == "__main__":
    main()
