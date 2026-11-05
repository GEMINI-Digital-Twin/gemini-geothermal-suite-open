"""More realistic cooling and well choices around the selected design.

Every case runs through the agent's ToolBox, so it passes the physics gate
(hard rules, energy balances incl. the ATES electricity, sanity bounds,
GEMINI Solver cross-check) and gets a run id. All cases price the wells'
corrosion mitigation (gemini_design.well_integrity) unless stated.

Cases: the chiller technology menu (dry-cooler screw, centrifugal with a
wet cooling tower, air-cooled screw), free cooling, and a shallow aquifer
cold store (ATES) with 2-4 well pairs, also with a smaller chiller.

    $env:PYTHONPATH="src"
    python simulator_examples/run_realism_study.py --epw NLD_Amsterdam.062400_IWEC.epw

Writes simulator_examples/outputs/realism/results.csv and results.md.
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
OUT = Path(__file__).parent / "outputs" / "realism"
PICK = {
    "n_doublets": 2,
    "depth_m": 3100,
    "upgrade": "boiler",
    "cooling": "electric",
    "chp": True,
    "chiller_capacity_mw": 12.0,
}
NO_WELL_COSTS = {"corrosion_resistant_liner_cost_eur_per_m": 0.0}  # mitigation for free


def cases():
    """(label, with weather, design changes vs PICK, assumption overrides)."""
    tower = {"chiller_type": "centrifugal_tower"}
    tfc = {**tower, "free_cooling": True}
    out = [
        ("pick as reported (fixed 30 degC, no corrosion costs)", False, {}, NO_WELL_COSTS),
        ("pick, fixed 30 degC, corrosion mitigation priced", False, {}, None),
        ("pick, Amsterdam weather", True, {}, None),
    ]
    for kind in ("screw_dry_cooler", "centrifugal_tower", "air_cooled_screw"):
        out.append((f"{kind}", True, {"chiller_type": kind}, None))
        out.append(
            (f"{kind} + free cooling", True, {"chiller_type": kind, "free_cooling": True}, None)
        )
    for n in (2, 3, 4):
        out.append((f"tower + free cooling + ATES x{n}", True, {**tfc, "ates_doublets": n}, None))
    # Backup chiller sized so cooling survives one ATES well pair being out on the peak day:
    # 10 MW - (3 - 1) x ~2.35 MW -> 6 MW; air-cooled because it rarely runs (no tower water).
    afc = {"chiller_type": "air_cooled_screw", "free_cooling": True}
    cand = {**afc, "ates_doublets": 3, "chiller_capacity_mw": 6.0}
    out.append(("air-cooled + free cooling + ATES x3, 6 MW backup chiller", True, cand, None))
    out.append(("same, ATES well pair cost x2", True, cand, {"ates_well_pair_cost_eur": 1.2e6}))
    out.append(("same, ATES well pair cost x0.5", True, cand, {"ates_well_pair_cost_eur": 3.0e5}))
    out.append(
        ("same, ATES cold losses doubled", True, cand, {"ates_loss_fraction_per_day": 0.003})
    )
    out.append(
        (
            "air-cooled + free cooling + ATES x4, 4 MW backup chiller",
            True,
            {**afc, "ates_doublets": 4, "chiller_capacity_mw": 4.0},
            None,
        )
    )
    out.append(
        (
            "1 doublet, air-cooled + free cooling + ATES x3, 6 MW",
            True,
            {**cand, "n_doublets": 1},
            None,
        )
    )
    out.append(("2 doublets at 3400 m, tower + free cooling", True, {**tfc, "depth_m": 3400}, None))
    return out


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
    climate = with_climate(demand, weather, "max")
    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True)
    ledger, notes = RunLedger(OUT / "ws"), ProjectNotes(OUT / "ws")
    rows = []
    for label, use_weather, changes, overrides in cases():
        tb = ToolBox(climate if use_weather else demand, ledger, notes, OUT / "ws", workers=1)
        request = {**PICK, **changes}
        if overrides:
            request["assumptions"] = overrides
        head = tb.call("run_design", request)
        if "error" in head:
            raise RuntimeError(f"{label}: {head}")
        s = ledger.summary(head["run_id"])
        e, econ = s["energy_mwh"], s["economics"]
        at = s.get("ates", {})
        rows.append(
            {
                "case": label,
                "run_id": head["run_id"],
                "design": head["design"],
                "physics_gate": head["physics_gate"],
                "meets_all_hard_rules": head["meets_all_hard_rules"],
                "unmet_cooling_mwh": round(e["unmet_cooling"], 1),
                "free_cooling_mwh": round(e.get("free_cooling", 0.0)),
                "ates_cooling_mwh": round(e.get("ates_cooling", 0.0)),
                "ates_imbalance": round(at["heat_balance_imbalance"], 3) if at else "",
                "electricity_mwh": round(e["electricity"]),
                "tower_water_m3": round(s["kpi"].get("cooling_tower_water_m3_per_year", 0.0)),
                "co2_t_per_year": round(head["co2_t_per_year"]),
                "capex_meur": round(head["capex_meur"], 2),
                "well_integrity_meur": round(econ["capex_eur"].get("well_integrity", 0.0) / 1e6, 2),
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
        f"# Realistic cooling and well choices, weather: {source}",
        "",
        "| " + " | ".join(cols) + " |",
        "|" + "---|" * len(cols),
    ]
    lines += ["| " + " | ".join(str(r[c]) for c in cols) + " |" for r in rows]
    (OUT / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return rows


if __name__ == "__main__":
    main()
