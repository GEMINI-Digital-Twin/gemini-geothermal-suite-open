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
geothermal digital twin through tools. Design an integrated system that meets the daily heating
(100 C supply) and cooling (20 C supply) demand on all 365 days, using deep geothermal for direct
heating and, where possible, to drive cooling.

Rules:
- Every number must come from a tool. Never invent or estimate results yourself.
- Start with get_problem_brief and inspect_gemini_capabilities. Identify what GEMINI cannot model
  and load the supplementary models you need before evaluating designs.
- Use assess_resource to understand temperatures and capacities at candidate depths. Use
  run_gemini_project once to verify a doublet against the native GEMINI simulator.
- Evaluate designs with evaluate_design. Read the violations. Fix every hard violation by
  revising the design, and respond to warnings where reasonable.
- Compare at least three genuinely different alternatives (for example depth, number of doublets,
  heat pump versus deeper wells, chiller type) with compare_candidates.
- Finish with finish(candidate_id, justification). The justification must explain the trade-offs
  against the other candidates, with numbers from the tools.
- Keep each message short: state what you will do next and why, then call one tool."""


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
            v.get("severity") == "hard" for v in result.get("violations", []))
        if hard or (isinstance(result, dict) and "error" in result) or tool_name == "compare_candidates":
            self.force_api_next = True


def run(llm_by_route, routing="hybrid", max_steps=20, budget_usd=0.5, task=None, run_dir=None):
    run_dir = Path(run_dir or RUNS / datetime.now().strftime("%Y%m%d_%H%M%S"))
    session = Session(run_dir)
    log = next(iter(llm_by_route.values())).log
    router = Router(routing, llm_by_route)
    messages = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": task or "Design the system and report the final choice."}]
    md = [f"# Agent run {run_dir.name}\n", f"Routing: {routing}\n"]
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
        for tc in calls:
            name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args, result = {}, {"error": "arguments were not valid JSON"}
            else:
                result = call_tool(session, name, args)
            router.observe(name, result)
            text = json.dumps(result, default=str)
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": text})
            md.append(f"- **Tool** `{name}({json.dumps(args)})`\n\n  ```json\n  {text[:1500]}\n  ```\n")
        if session.final:
            md.append(f"\n## Final design: {session.final['candidate_id']}\n\n"
                      f"{session.final['justification']}\n")
            break
        if log.totals["cost_usd"] > budget_usd:
            md.append(f"\n**Stopped: estimated cost {log.totals['cost_usd']:.3f} USD over budget.**\n")
            break
    t = log.totals
    md.append(f"\n## Token use\n\nCalls {t['calls']}, prompt tokens {t['prompt_tokens']}, "
              f"completion tokens {t['completion_tokens']}, estimated cost {t['cost_usd']:.4f} USD\n")
    for m, s in t["by_model"].items():
        md.append(f"- {m}: {s['calls']} calls, {s['prompt_tokens']} in, "
                  f"{s['completion_tokens']} out, {s['cost_usd']:.4f} USD\n")
    (run_dir / "transcript.md").write_text("".join(md), encoding="utf-8")
    with open(run_dir / "token_totals.json", "w", encoding="utf-8") as f:
        json.dump(t, f, indent=2)
    return session, run_dir


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--routing", choices=["hybrid", "api_only", "local_only"])
    ap.add_argument("--scripted", action="store_true", help="offline demo with a fixed script")
    ap.add_argument("--max-steps", type=int)
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
