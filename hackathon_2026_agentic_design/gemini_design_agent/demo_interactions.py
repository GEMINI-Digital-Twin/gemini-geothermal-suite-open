"""Evidence of agent interactions for the committee: incomplete, irrelevant and inconsistent
requests, how the agent answers, and the number of tokens used.   python demo_interactions.py
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from gemini_design_agent.intake import check_request

DATA = ROOT.parent
FULL = {
    "heating_demand_csv": str(DATA / "GEMINI_Heating_Demand_Daily_2027.csv"),
    "cooling_demand_csv": str(DATA / "GEMINI_Cooling_Demand_Daily_2027.csv"),
    "supply_temperature_heating_c": 100, "supply_temperature_cooling_c": 20,
    "reservoir_depth_m": 2500, "geothermal_gradient_c_per_km": 30, "reservoir_pressure_bar": 250,
    "permeability_md": 200, "brine_glr_nm3_per_m3": 0.8,
}
SCENARIOS = [
    ("1. Complete request (the challenge as issued)",
     "Design a geothermal heating and cooling system for the district with the attached demand files.", FULL),
    ("2. Incomplete request: heating file only, no supply temperatures",
     "Here is the heating demand. Design the geothermal system.",
     {k: v for k, v in FULL.items() if k in ("heating_demand_csv", "reservoir_depth_m", "geothermal_gradient_c_per_km",
                                             "reservoir_pressure_bar", "permeability_md", "brine_glr_nm3_per_m3")}),
    ("3. Irrelevant request",
     "Design a 50 MWe geothermal power plant with an ORC turbine for the same reservoir.", FULL),
    ("4. Off-topic question", "Which stock should I buy this week?", {}),
    ("5. Inconsistent inputs: a 140 C reservoir at 2,500 m with a 30 C/km gradient",
     "The reservoir at 2,500 m is 140 C. Design the system.", {**FULL, "reservoir_temperature_c": 140}),
    ("6. Request with a wrong file path",
     "Design the system; cooling demand is in cooling_2027.csv.", {**FULL, "cooling_demand_csv": "cooling_2027.csv"}),
]


def token_table() -> tuple[list[str], dict]:
    """Per-turn token accounting for the recorded Claude-orchestrated run.

    The run was driven from Claude Code (`claude_session.py`), where the API does not report usage to us, so
    the figures are estimates at 4 characters per token over the text actually exchanged: the rationale Claude
    wrote before each move (its output), the compact JSON summary the twin returned (the answer), and the
    conversation so far that is re-read on every turn (input). `--mode claude` through the API meters
    `response.usage` exactly and writes it to `llm_usage.json`."""
    log = (ROOT / "outputs_claude" / "orchestration_log.md").read_text(encoding="utf-8")
    blocks = re.split(r"\n(?=### Claude: )", log)
    try:
        from claude_session import load_tb
        tb = load_tb()
        summaries = {n: len(json.dumps(r.summary(), default=float)) for n, r in tb.results.items()}
    except Exception:
        summaries = {}
    rows, cum, tot_in, tot_out = [], 0, 0, 0
    context_chars = 6000   # system prompt + spec + demand summary returned by get_context
    for b in blocks:
        if not b.startswith("### Claude: "):
            continue
        head, _, rest = b.partition("\n")
        head = head[len("### Claude: "):]
        rationale = rest.split("\n[", 1)[0].strip()
        names = re.findall(r"`([^`]+)`", head)
        name = names[-1] if names else ""
        answer_chars = 60 if head.startswith("finalize") else summaries.get(name, 1500)
        out_tok = round(len(rationale) / 4)
        in_tok = round((context_chars + cum) / 4)       # the whole conversation so far is re-read each turn
        cum += len(rationale) + answer_chars
        tot_in += in_tok; tot_out += out_tok
        rows.append((head.split("`")[0].strip() + " " + name, out_tok, round(answer_chars / 4), in_tok))
    L = ["| Turn | Claude's move | Claude output (tokens) | Twin answer (tokens) | Context read (tokens) |",
         "|---|---|---|---|---|"]
    for i, (h, o, a, c) in enumerate(rows, 1):
        L.append(f"| {i} | {h} | {o} | {a} | {c} |")
    L.append(f"| | **total** | **{tot_out}** | **{sum(r[2] for r in rows)}** | **{tot_in}** |")
    usage = {"model": "claude-fable-5-1 (Claude Code session)", "turns": len(rows), "input_tokens": tot_in,
             "output_tokens": tot_out, "total_tokens": tot_in + tot_out,
             "method": "estimated at 4 chars/token from the logged text; API mode (--mode claude) meters response.usage exactly"}
    (ROOT / "outputs_claude" / "llm_usage.json").write_text(json.dumps(usage, indent=2), encoding="utf-8")
    return L, usage


L = ["# Agent interaction evidence\n",
     "The committee asked for evidence that the agent can reason about a request: identify missing inputs, refuse what is "
     "out of scope, and flag inconsistencies. These six exchanges are produced by the agent's intake gate "
     "(`gemini_design_agent/intake.py`), which runs before any simulation in both orchestration modes. They are "
     "deterministic, so anyone can rerun `python demo_interactions.py` and get the same answers.\n"]
for title, text, req in SCENARIOS:
    rep = check_request(req, text)
    L += [f"## {title}\n", f"> **User:** {text}\n", rep.markdown(), ""]

TOK, USAGE = token_table()
L += ["## 7. Reasoning transcript of the Claude-orchestrated design run\n",
      "`outputs_claude/orchestration_log.md` holds the eight design moves Claude made, each with its stated hypothesis "
      "before the simulation and the twin's verdict after it (for example: 'two doublets at 3,500 m with a 15 MW heat pump' "
      "was proposed, failed on 16 peak days, and the log explains why the heat pump cannot help once the brine is at the "
      "40 C cap). The rule-based run's equivalent is `outputs/agent_log.txt` (16 archetypes, 38 steps).\n",
      "## 8. Number of used tokens\n",
      f"LLM: Claude Fable 5.1 (Anthropic, commercial), orchestrating from Claude Code through `claude_session.py`. "
      f"{USAGE['turns']} decision turns, {USAGE['output_tokens']:,} output tokens, {USAGE['input_tokens']:,} input tokens read "
      f"across the turns, about {USAGE['total_tokens']:,} tokens in total. This is an estimate at 4 characters per token over "
      "the logged text, because the Claude Code session does not expose API usage; it is written to "
      "`outputs_claude/llm_usage.json`. Each twin answer is a compact JSON summary (feasibility, violations, 12 KPIs, cost), "
      "not the 365-day table, which is what keeps the run this small.\n"] + TOK + ["",
      "- API mode (`python -m gemini_design_agent.cli --mode claude` with `ANTHROPIC_API_KEY` set) meters `response.usage` "
      "on every turn, logs `[tokens] turn n: in/out`, and writes the exact totals to `<out>/llm_usage.json`.",
      "- Rule-based run (`--mode rule`): zero LLM tokens; 38 twin evaluations, ~5 minutes; fully reproducible offline. "
      "Its `llm_usage.json` records that.",
      "- Design-space screening for the optimisers used a fast evaluator (every 2nd/3rd day) with a cache keyed on the design "
      "signature, which cut the optimiser study from an estimated 6 hours to about 50 minutes; no LLM tokens."]
out = ROOT / "outputs_claude" / "INTERACTION_EVIDENCE.md"
out.write_text("\n".join(L), encoding="utf-8")
print("\n".join(L))
print("written", out)
