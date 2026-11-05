"""Weather-driven cooling: what real outdoor temperature does to the selected design.

The base model rejects chiller heat at a fixed 30 degC all year. This study
reads a year of outdoor air temperature (KNMI daily data or an EnergyPlus
.epw file, see gemini_design.climate), lets the chiller condenser follow it,
and adds a dry-cooler economizer (free cooling) ahead of the chiller. Every
case runs through the agent's ToolBox, so it passes the same physics gate
(hard rules, energy balance, sanity bounds, GEMINI Solver cross-check) and
gets a run id in the ledger.

    $env:PYTHONPATH="src"
    python simulator_examples/run_free_cooling_study.py --epw NLD_Amsterdam.062400_IWEC.epw
    python simulator_examples/run_free_cooling_study.py --knmi etmgeg_240.txt --year 2023

Writes simulator_examples/outputs/free_cooling/results.csv and results.md.
"""

import argparse
import csv
import shutil
from pathlib import Path

from gemini_agent.memory import ProjectNotes, RunLedger
from gemini_agent.tools import ToolBox
from gemini_design.challenge import default_inputs_dir, load_demand
from gemini_design.climate import read_epw_daily, read_knmi_daily, with_climate

INPUTS = default_inputs_dir()  # $GEMINI_INPUTS or the official 2027 inputs
OUT = Path(__file__).parent / "outputs" / "free_cooling"
PICK = {
    "n_doublets": 2,
    "depth_m": 3100,
    "upgrade": "boiler",
    "cooling": "electric",
    "chp": True,
    "chiller_capacity_mw": 12.0,
}
SLOW_AIR = {"dry_cooler_approach_k": 7.2, "free_cooling_approach_k": 10.0}  # +5 K each


def cases():
    """(label, weather statistic or None, design changes vs PICK, assumption overrides)."""
    fc = {"free_cooling": True}
    one = {"n_doublets": 1}
    absorption = {"cooling": "absorption", "chiller_capacity_mw": 12.0}
    return [
        ("pick, fixed 30 degC heat rejection (current report)", None, {}, None),
        ("pick, daily max air temp, chiller only", "max", {}, None),
        ("pick, daily max air temp + free cooling", "max", fc, None),
        ("pick, daily max, chiller only, approach +5 K", "max", {}, SLOW_AIR),
        ("pick, daily max + free cooling, approaches +5 K", "max", fc, SLOW_AIR),
        (
            "pick, daily max + free cooling, economizer cost x3",
            "max",
            fc,
            {"free_cooling_cost_eur_per_mw": 3.0e5},
        ),
        ("pick, daily mean air temp + free cooling", "mean", fc, None),
        ("ranking: 1 doublet, fixed 30 degC", None, one, None),
        ("ranking: 1 doublet, daily max + free cooling", "max", {**one, **fc}, None),
        ("ranking: absorption + CHP, fixed 30 degC", None, absorption, None),
        ("ranking: absorption + CHP, daily max", "max", absorption, None),
    ]


def main():
    """Run the study and write the results."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--epw", help="EnergyPlus weather file")
    src.add_argument("--knmi", help="KNMI etmgeg daily file")
    parser.add_argument("--year", type=int, default=2023, help="year to take from a KNMI file")
    args = parser.parse_args()
    weather = read_epw_daily(args.epw) if args.epw else read_knmi_daily(args.knmi, args.year)
    source = Path(args.epw or args.knmi).name + ("" if args.epw else f" ({args.year})")

    demand = load_demand(INPUTS)
    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True)
    ledger, notes = RunLedger(OUT / "ws"), ProjectNotes(OUT / "ws")
    rows = []
    for label, stat, changes, overrides in cases():
        dem = demand if stat is None else with_climate(demand, weather, stat)
        tb = ToolBox(dem, ledger, notes, OUT / "ws", workers=1)
        request = {**PICK, **changes}
        if overrides:
            request["assumptions"] = overrides
        head = tb.call("run_design", request)
        if "error" in head:
            raise RuntimeError(f"{label}: {head}")
        e = ledger.summary(head["run_id"])["energy_mwh"]
        daily = ledger.daily(head["run_id"])
        cop = (
            float(daily["electric_chiller_cop"].dropna().mean())
            if "electric_chiller_cop" in daily
            else float("nan")
        )
        cw = daily["cooling_water_c"] if "cooling_water_c" in daily else None
        rows.append(
            {
                "case": label,
                "run_id": head["run_id"],
                "design": head["design"],
                "physics_gate": head["physics_gate"],
                "meets_all_hard_rules": head["meets_all_hard_rules"],
                "unmet_heating_mwh": round(e["unmet_heating"], 1),
                "unmet_cooling_mwh": round(e["unmet_cooling"], 1),
                "free_cooling_mwh": round(e.get("free_cooling", 0.0), 0),
                "mean_chiller_cop": round(cop, 2),
                "max_heat_rejection_c": round(float(cw.max()), 1) if cw is not None else "",
                "electricity_mwh": round(e["electricity"], 0),
                "grid_import_mwh": round(e["grid_import"], 0),
                "co2_t_per_year": round(head["co2_t_per_year"], 0),
                "capex_meur": round(head["capex_meur"], 2),
                "lcoe_eur_per_mwh": round(head["lcoe_eur_per_mwh"], 2),
            }
        )
        print(
            f"{head['run_id']} {label}: {head['lcoe_eur_per_mwh']:.2f} EUR/MWh, "
            f"{head['co2_t_per_year']:.0f} t, gate {head['physics_gate']}"
        )

    with open(OUT / "results.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    cols = list(rows[0])
    lines = [
        f"# Weather-driven cooling, weather: {source}",
        "",
        "| " + " | ".join(cols) + " |",
        "|" + "---|" * len(cols),
    ]
    lines += ["| " + " | ".join(str(r[c]) for c in cols) + " |" for r in rows]
    (OUT / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return rows


if __name__ == "__main__":
    main()
