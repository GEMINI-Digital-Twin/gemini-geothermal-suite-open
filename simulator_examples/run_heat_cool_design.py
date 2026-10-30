"""Run one GeoHackathon heating + cooling design for a full year.

Writes, to ``simulator_examples/outputs/<design name>/``:
``daily.csv`` (one row per day), ``summary.json`` (KPIs, hard-constraint
checks, economics), ``peak_day_project.json`` (the peak heating day as a
native gemini_simulator project) and ``cross_check.json`` (that project
re-run through GEMINI's Solver and compared with the dispatcher).

Run with:
    $env:PYTHONPATH="src"; python simulator_examples/run_heat_cool_design.py
"""

import json
import sys
from pathlib import Path

from gemini_design.annual import dispatch_day, run_year
from gemini_design.challenge import load_demand
from gemini_design.doublet import DoubletHydraulics
from gemini_design.plant import Design, Plant
from gemini_design.project_json import cross_check

INPUTS = Path(__file__).parent / "hackathon_inputs"
OUTPUTS = Path(__file__).parent / "outputs"

DESIGN = Design(
    n_doublets=2,
    depth_m=3100.0,
    upgrade="boiler",
    cooling="absorption",
    boiler_capacity_mw=30.0,
    chiller_capacity_mw=10.0,
    electric_backup_mw=5.0,
)


def main(design=DESIGN):
    """Run the design, print headline results and write the output files."""
    demand = load_demand(INPUTS)
    daily, summary = run_year(design, demand)

    out_dir = OUTPUTS / design.name
    out_dir.mkdir(parents=True, exist_ok=True)
    daily.to_csv(out_dir / "daily.csv", index=False)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=float))

    peak = int(demand["heating_mw"].idxmax())
    hydraulics = DoubletHydraulics(design.depth_m)
    plant = Plant(design, hydraulics)
    n_available = int(daily.loc[peak, "n_available"])
    day = dispatch_day(
        plant,
        demand.loc[peak, "heating_mw"] * 1e6,
        demand.loc[peak, "cooling_mw"] * 1e6,
        n_available,
    )
    project, check = cross_check(design, hydraulics, day)
    (out_dir / "peak_day_project.json").write_text(json.dumps(project, indent=2, default=float))
    (out_dir / "cross_check.json").write_text(json.dumps(check, indent=2, default=float))

    e, k, res = summary["energy_mwh"], summary["kpi"], summary["reservoir"]
    lcoe = summary["economics"]["lcoe_eur_per_mwh"]
    print(f"Design: {design.name}")
    print(f"Reservoir: {res['temperature_c']:.1f} C, {res['pressure_bar']:.1f} bar")
    print(f"Heating delivered: {e['heating_delivered']:,.0f} / {e['heating_demand']:,.0f} MWh")
    print(f"Cooling delivered: {e['cooling_delivered']:,.0f} / {e['cooling_demand']:,.0f} MWh")
    print(f"Geothermal share of heat: {k['geothermal_share_of_heat']:.1%}")
    print(f"Purchased gas: {e['purchased_gas_fuel']:,.0f} MWh")
    print(f"Electricity: {e['electricity']:,.0f} MWh")
    print(f"CO2: {k['co2_t_per_year']:,.0f} t/yr, LCOE: {lcoe:.1f} EUR/MWh")
    print(
        "Hard constraints:", "ALL MET" if summary["all_hard_constraints_met"] else summary["checks"]
    )
    print("Peak day GEMINI Solver cross-check:", "agrees" if check["agrees"] else check)
    print(f"Outputs written to {out_dir}")
    return summary


if __name__ == "__main__":
    sys.exit(0 if main()["all_hard_constraints_met"] else 1)
