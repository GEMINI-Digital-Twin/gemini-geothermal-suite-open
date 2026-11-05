"""Run the final pick (or a fixed example design) for a full year and print every rule.

By default this runs the **submitted design** (``PICK`` in ``run_final_pick.py``) on
the measured KNMI Schiphol weather of 2025 that is in the repository, through the
agent's ToolBox, so the run passes the physics gate, including the peak-day re-solve
with GEMINI's Solver. It prints the headline numbers and a table of every hard rule
of the brief against the value the design reaches, and writes, to
``simulator_examples/outputs/<design name>/``: ``daily.csv`` (one row per day),
``summary.json`` (KPIs, hard-constraint checks, economics) and ``rules.md``.

``--example`` runs the old fixed example instead (``EXAMPLE``: 2 doublets, boiler,
absorption chiller, no weather), with the peak day exported as a native
``gemini_simulator`` project (``peak_day_project.json``) and re-solved
(``cross_check.json``). It is a demonstration, not the submitted design.

Run with (PowerShell: ``$env:PYTHONPATH="src";`` first):
    PYTHONPATH=src python simulator_examples/run_heat_cool_design.py
    PYTHONPATH=src python simulator_examples/run_heat_cool_design.py --inputs my_demand_dir
    PYTHONPATH=src python simulator_examples/run_heat_cool_design.py --example

Exits 1 if a hard rule fails.
"""

import argparse
import json
import shutil
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gemini_agent.memory import ProjectNotes, RunLedger  # noqa: E402
from gemini_agent.tools import ToolBox  # noqa: E402
from gemini_design.annual import dispatch_day, run_year  # noqa: E402
from gemini_design.challenge import CHALLENGE, add_inputs_argument, load_demand  # noqa: E402
from gemini_design.climate import read_knmi_daily, with_climate  # noqa: E402
from gemini_design.doublet import DoubletHydraulics  # noqa: E402
from gemini_design.plant import Design, Plant  # noqa: E402
from gemini_design.project_json import cross_check  # noqa: E402
from run_final_pick import PICK  # noqa: E402

OUTPUTS = Path(__file__).parent / "outputs"
KNMI = Path(__file__).parent / "weather" / "knmi_etmgeg_240_1991_2025.txt"

EXAMPLE = Design(
    n_doublets=2,
    depth_m=3100.0,
    upgrade="boiler",
    cooling="absorption",
    boiler_capacity_mw=30.0,
    chiller_capacity_mw=10.0,
    electric_backup_mw=5.0,
)
DESIGN = EXAMPLE  # kept for scripts that import the old name


def rule_rows(summary, daily, demand):
    """(rule from the brief, limit, value reached, met?) for every hard rule."""
    k, e, checks = summary["kpi"], summary["energy_mwh"], summary["checks"]
    c = CHALLENGE
    heating_days = daily["heating_demand_w"] > 0
    supply = daily.loc[heating_days, "supply_temperature_c"]
    days = k["doublet_operating_days"]
    days = days if isinstance(days, (list, tuple)) else [days]
    active = daily["n_active"] > 0
    flows = daily.loc[active, "flow_per_doublet_m3h"]
    imbalance = summary.get("production_minus_injection_m3", 0.0)
    return [
        (
            "Heating demand met every day",
            f"{e['heating_demand']:,.0f} MWh/yr",
            f"unmet {e['unmet_heating']:.1f} MWh",
            checks["heating_demand_met"],
        ),
        (
            "Cooling demand met every day",
            f"{e['cooling_demand']:,.0f} MWh/yr",
            f"unmet {e['unmet_cooling']:.1f} MWh",
            checks["cooling_demand_met"],
        ),
        (
            "Heating network supply temperature",
            f"{c['heating_supply_c']:.0f} degC",
            f"min {supply.min():.1f} degC on heating days" if len(supply) else "n/a",
            checks["heating_demand_met"],
        ),
        (
            "Cooling network supply temperature",
            f"{c['cooling_supply_c']:.0f} degC",
            "set point of the chiller, free-cooling and ATES models",
            checks["cooling_demand_met"],
        ),
        (
            "Flow per active doublet",
            "50-300 m3/h",
            f"{flows.min():.0f}-{flows.max():.0f} m3/h" if len(flows) else "n/a",
            checks["flow_within_50_300_m3h"],
        ),
        (
            "Brine cooling across the plant",
            "at most 40 K",
            f"max {k['max_brine_cooling_k']:.2f} K",
            checks["brine_cooling_within_40K"],
        ),
        (
            "Days per doublet (geothermal source availability)",
            "at most 330 days",
            "max " + ", ".join(str(int(d)) for d in days) + " days",
            checks["doublet_days_within_330"],
        ),
        (
            "Number of doublets",
            "1-3",
            str(summary["design"]["n_doublets"]),
            checks["doublets_within_1_3"],
        ),
        (
            "Production equals injection",
            "every day",
            f"difference {imbalance:.1f} m3" if imbalance else "equal on all days",
            checks["production_equals_injection"],
        ),
        (
            "No daily rule violations",
            "365 days",
            f"{int((daily['violations'].fillna('') != '').sum())} days with a violation",
            checks["no_daily_violations"],
        ),
    ]


def run_pick(inputs=None, knmi=KNMI, year=2025):
    """Run the submitted design through the gated ToolBox; return (summary, daily, head)."""
    climate = with_climate(load_demand(inputs), read_knmi_daily(knmi, year), "max")
    ws = OUTPUTS / "heat_cool_design_ws"
    shutil.rmtree(ws, ignore_errors=True)
    ledger, notes = RunLedger(ws), ProjectNotes(ws)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        head = ToolBox(climate, ledger, notes, ws, workers=1).call("run_design", dict(PICK))
    if "error" in head:
        raise RuntimeError(head)
    return ledger.summary(head["run_id"]), ledger.daily(head["run_id"]), head, climate


def run_example(inputs=None, design=EXAMPLE):
    """The old fixed example (no weather), with the peak day re-solved by the Solver."""
    demand = load_demand(inputs)
    daily, summary = run_year(design, demand)
    out_dir = OUTPUTS / design.name
    out_dir.mkdir(parents=True, exist_ok=True)
    peak = int(demand["heating_mw"].idxmax())
    hydraulics = DoubletHydraulics(design.depth_m)
    plant = Plant(design, hydraulics)
    day = dispatch_day(
        plant,
        demand.loc[peak, "heating_mw"] * 1e6,
        demand.loc[peak, "cooling_mw"] * 1e6,
        int(daily.loc[peak, "n_available"]),
    )
    project, check = cross_check(design, hydraulics, day)
    (out_dir / "peak_day_project.json").write_text(json.dumps(project, indent=2, default=float))
    (out_dir / "cross_check.json").write_text(json.dumps(check, indent=2, default=float))
    return (
        summary,
        daily,
        {"physics_gate": "solver " + ("agrees" if check["agrees"] else "differs")},
        demand,
    )


def main(argv=None):
    """Run, print the headline and the rule table, write the outputs."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--example", action="store_true", help="run the old fixed example")
    parser.add_argument("--knmi", default=str(KNMI), help="KNMI etmgeg daily weather file")
    parser.add_argument("--year", type=int, default=2025, help="year to take from the KNMI file")
    add_inputs_argument(parser)
    args = parser.parse_args(argv)
    if args.example:
        summary, daily, head, demand = run_example(args.inputs)
        label = "EXAMPLE design (not the submitted design)"
    else:
        summary, daily, head, demand = run_pick(args.inputs, args.knmi, args.year)
        label = f"SUBMITTED design, KNMI Schiphol {args.year} weather, run {head['run_id']}"

    name = summary["design"]["name"]
    out_dir = OUTPUTS / name
    out_dir.mkdir(parents=True, exist_ok=True)
    daily.to_csv(out_dir / "daily.csv", index=False)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=float))

    k, econ = summary["kpi"], summary["economics"]
    print(label)
    print(f"Design: {name}")
    print(f"LCOE: {econ['lcoe_eur_per_mwh']:.2f} EUR/MWh (heat + cooling delivered)")
    print(
        f"CO2: {k['co2_t_per_year']:,.0f} t/yr, CAPEX: EUR {econ['capex_eur']['total'] / 1e6:.1f} M"
    )
    print(f"Geothermal share of heat: {k['geothermal_share_of_heat']:.1%}")
    print(f"Physics gate: {head.get('physics_gate')}")
    rows = rule_rows(summary, daily, demand)
    table = ["| Rule (brief) | Limit | Reached | Met |", "|---|---|---|---|"]
    table += [f"| {r} | {lim} | {val} | {'yes' if ok else 'NO'} |" for r, lim, val, ok in rows]
    (out_dir / "rules.md").write_text("\n".join(table) + "\n", encoding="utf-8")
    print("\n".join(table))
    met = summary["all_hard_constraints_met"]
    print("Hard constraints:", "ALL MET" if met else "FAILED")
    print(f"Outputs written to {out_dir}")
    return summary


if __name__ == "__main__":
    sys.exit(0 if main()["all_hard_constraints_met"] else 1)
