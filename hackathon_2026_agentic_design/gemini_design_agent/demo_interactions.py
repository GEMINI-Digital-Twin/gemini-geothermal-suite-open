"""Evidence of agent interactions for the committee: incomplete, irrelevant and inconsistent
requests, and how the agent answers.   python demo_interactions.py
"""
from __future__ import annotations
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

L = ["# Agent interaction evidence\n",
     "The committee asked for evidence that the agent can reason about a request: identify missing inputs, refuse what is "
     "out of scope, and flag inconsistencies. These six exchanges are produced by the agent's intake gate "
     "(`gemini_design_agent/intake.py`), which runs before any simulation in both orchestration modes. They are "
     "deterministic, so anyone can rerun `python demo_interactions.py` and get the same answers.\n"]
for title, text, req in SCENARIOS:
    rep = check_request(req, text)
    L += [f"## {title}\n", f"> **User:** {text}\n", rep.markdown(), ""]
L += ["## 7. Reasoning transcript of the Claude-orchestrated design run\n",
      "`outputs_claude/orchestration_log.md` holds the eight design moves Claude made, each with its stated hypothesis "
      "before the simulation and the twin's verdict after it (for example: 'two doublets at 3,500 m with a 15 MW heat pump' "
      "was proposed, failed on 16 peak days, and the log explains why the heat pump cannot help once the brine is at the "
      "40 C cap). The rule-based run's equivalent is `outputs/agent_log.txt` (16 archetypes, 38 steps).\n",
      "## 8. Compute and token footprint\n",
      "- Claude-orchestrated run: 8 LLM decision turns, 7 twin evaluations of 10-18 s each, about 2 minutes of simulation. "
      "Each tool result returned to the LLM is a compact JSON summary (~1-2 kB: feasibility, violations, 12 KPIs, cost), "
      "not the 365-day table, so the whole orchestration stays under an estimated 60k tokens. Token counts were not "
      "metered by the API in this run (the session ran inside Claude Code); the estimate is from the transcript size.",
      "- Rule-based run: zero LLM tokens; 38 evaluations, ~5 minutes; fully reproducible offline.",
      "- Design-space screening for the optimisers used a fast evaluator (every 2nd/3rd day) with a cache keyed on the design "
      "signature, which cut the optimiser study from an estimated 6 hours to about 50 minutes."]
out = ROOT / "outputs_claude" / "INTERACTION_EVIDENCE.md"
out.write_text("\n".join(L), encoding="utf-8")
print("\n".join(L))
print("written", out)
