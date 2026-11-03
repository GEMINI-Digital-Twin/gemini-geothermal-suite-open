"""One-at-a-time sensitivity of the final design, and whether the agent's pick changes.

Run in GEMINI repository root (after design_agent.py):
    $env:PYTHONPATH="src"; py -3.11 -m poetry run python hackathon_work/sensitivity.py

For each case one input is moved to its low / high value (ASSUMED ranges, below):
  1. the final design (fixed, from outputs/agent/run_summary.json) is re-simulated:
     delta emissions vs the base case and any hard-constraint failures;
  2. the rules agent is re-run from scratch with the changed input, to see whether
     its ranking rule picks a different design.
Outputs: outputs/sensitivity/summary.json, sensitivity.md (+ per-case decision logs).
"""

from __future__ import annotations

import copy
import json
import time
import warnings
from pathlib import Path

from daily_model import CANDIDATES_PATH
from design_agent import AGENT_OUT, REQUIRED_BY_NAME, DecisionLog, DesignAgent, RulesBackend, candidate_id, set_input
from doublet_model import CHALLENGE_PATH, PROJECT_PATH, REPO, ROOT, load_json

OUT = ROOT / "outputs" / "sensitivity"

# (parameter, label, unit, base, low, high); all ASSUMED plausible spreads (gradient: +-10% of the OFFICIAL 30 C/km)
CASES = [
    ("heating_return_T", "Heating return temperature", "C", 60, 50, 70),
    ("hp_eta_lorenz", "Heat pump Lorenz efficiency", "-", 0.45, 0.40, 0.50),
    ("absorption_COP", "Absorption chiller COP", "-", 0.7, 0.6, 0.8),
    ("gradient", "Geothermal gradient", "C/km", 30, 27, 33),
    ("brine_cp", "Brine specific heat", "J/(kg K)", 4100, 4000, 4200),
]


def case_inputs(param: str, value: float, folder: Path) -> tuple[dict, dict, Path, Path]:
    """Settings, project, project path and challenge path with one input changed."""
    settings, project = load_json(CANDIDATES_PATH), load_json(PROJECT_PATH)
    challenge_path = CHALLENGE_PATH
    if param == "gradient":
        challenge = load_json(CHALLENGE_PATH)
        challenge["reservoir"]["gradient_C_per_km"] = value
        challenge_path = folder / "challenge_inputs.json"
        challenge_path.write_text(json.dumps(challenge, indent=2), encoding="utf-8")
    else:
        set_input({"project": project, "settings": settings}, REQUIRED_BY_NAME[param], value)
    project_path = folder / "project.json"
    project_path.write_text(json.dumps(project, indent=2), encoding="utf-8")
    return settings, project, project_path, challenge_path


def run_case(param: str, value: float, pick: dict, folder: Path) -> dict:
    folder.mkdir(parents=True, exist_ok=True)
    settings, project, project_path, challenge_path = case_inputs(param, value, folder)
    agent = DesignAgent(RulesBackend(), DecisionLog(folder / "decision_log.jsonl", "rules"), folder)
    agent.project_path, agent.challenge_path = project_path, challenge_path
    start = time.perf_counter()
    result = agent.run("B_design", copy.deepcopy(project), settings)
    fixed = agent.evaluate(pick)["summary"]  # the base pick under the changed input
    agent_pick = result.get("pick")
    return {
        "parameter": param, "value": value, "runtime_s": time.perf_counter() - start,
        "final_design": {"candidate": candidate_id(pick), "feasible": fixed["feasible"],
                         "failing": sorted({c["check"] for c in fixed["annual_checks"] if c["status"] != "PASS"} | set(fixed["failing_checks"])),
                         "emissions_t": fixed["emissions_t"], "external_gas_GWh": fixed["external_gas_fuel_GWh"],
                         "grid_import_GWh": fixed["grid_import_GWh"]},
        "agent_pick": candidate_id(agent_pick["candidate"]) if agent_pick else None,
        "agent_pick_emissions_t": agent_pick["summary"]["emissions_t"] if agent_pick else None,
        "agent_evaluations": len(result.get("history", [])),
    }


def main():
    warnings.filterwarnings("ignore", category=RuntimeWarning)
    base_run = load_json(AGENT_OUT / "run_summary.json")
    pick = base_run["pick"]
    base_id, base_em = candidate_id(pick), base_run["pick_summary"]["emissions_t"]
    rows = []
    for param, label, unit, base, low, high in CASES:
        for side, value in (("low", low), ("high", high)):
            r = run_case(param, value, pick, OUT / "runs" / f"{param}_{value:g}")
            r.update(label=label, unit=unit, base=base, side=side,
                     delta_emissions_t=r["final_design"]["emissions_t"] - base_em,
                     delta_emissions_pct=(r["final_design"]["emissions_t"] - base_em) / base_em,
                     pick_changed=r["agent_pick"] != base_id)
            rows.append(r)
            print(f"{param}={value:g}: final design {r['final_design']['emissions_t']:.0f} t ({r['delta_emissions_t']:+.0f} t), "
                  f"feasible {r['final_design']['feasible']}; agent pick {r['agent_pick']}"
                  f"{' (CHANGED)' if r['pick_changed'] else ''} ({r['runtime_s']:.1f} s)", flush=True)
    summary = {"base": {"candidate": base_id, "emissions_t": base_em,
                        "values": {p: b for p, _, _, b, _, _ in CASES}},
               "cases": rows, "pick_changed_in": [f"{r['parameter']}={r['value']:g}" for r in rows if r["pick_changed"]]}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    lines = ["# One-at-a-time sensitivity of the final design", "",
             f"Base: `{base_id}`, {base_em:.0f} t CO2/yr. Each row moves one input (ASSUMED spread) with everything else at the base value. "
             "\"Final design\" is the base pick re-simulated; \"Agent pick\" is a fresh rules-agent run with the changed input.",
             "Rerun: `$env:PYTHONPATH=\"src\"; py -3.11 -m poetry run python hackathon_work/sensitivity.py`.", "",
             "| Input | Value | Final design emissions (t) | Delta (t) | Delta (%) | Hard constraints | Agent pick | Pick changed |",
             "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        fd = r["final_design"]
        lines.append(f"| {r['label']} ({r['unit']}) | {r['value']:g} (base {r['base']:g}) | {fd['emissions_t']:.0f} | {r['delta_emissions_t']:+.0f} | "
                     f"{r['delta_emissions_pct'] * 100:+.1f}% | {'PASS' if fd['feasible'] else 'FAIL: ' + ', '.join(fd['failing'])} | "
                     f"`{r['agent_pick']}` ({r['agent_pick_emissions_t']:.0f} t) | {'**yes**' if r['pick_changed'] else 'no'} |")
    changed = summary["pick_changed_in"]
    lines += ["", f"Pick changes in: {', '.join(changed)}." if changed else "The agent's pick is the same in every case."]
    (OUT / "sensitivity.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"WROTE {(OUT / 'summary.json').relative_to(REPO)}, {(OUT / 'sensitivity.md').relative_to(REPO)}")


if __name__ == "__main__":
    main()
