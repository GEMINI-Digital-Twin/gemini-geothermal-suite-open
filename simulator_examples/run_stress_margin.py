"""Margin study: the pick against held-out weather, warmer years and model doubts.

Added 4 Nov 2026 after the external review. The 2-4 Nov pick (2 doublets at 3.1 km,
9 MW backup chiller) was sized on the same demand and weather it was scored on. This
script runs it, the new pick (3.2 km, 10 MW) and the depths around it through stress
tests the sizing never saw: a cooler producer, a lower gradient, the low reservoir,
a whole-source outage (also from the heating peak), KNMI 2020 and 2014 weather made
warmer, more cooling, more demand and a smaller plate HEX (~3 K approach instead of
the default's ~0.1 K). Each test is one full 365-day dispatch.

    $env:PYTHONPATH="src;simulator_examples"
    python simulator_examples/run_stress_margin.py ^
        --knmi simulator_examples/weather/knmi_etmgeg_240_1991_2025.txt

Writes simulator_examples/outputs/stress_margin/: stress.csv and stress.md.
"""

import argparse
import csv
import warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from run_final_pick import INPUTS, PICK

from gemini_agent.tools import make_design
from gemini_design.annual import run_year
from gemini_design.challenge import ASSUMPTIONS, CHALLENGE, load_demand
from gemini_design.climate import read_knmi_daily, with_climate

OUT = Path(__file__).parent / "outputs" / "stress_margin"
# label: (depth m, backup chiller MW)
DESIGNS = {
    "3.1 km, 9 MW (2-4 Nov pick)": (3100, 9.0),
    "3.1 km, 10 MW": (3100, 10.0),
    "3.15 km, 10 MW": (3150, 10.0),
    "3.2 km, 10 MW (pick)": (3200, 10.0),
    "3.25 km, 10 MW": (3250, 10.0),
}
HEX_3K = {"hex_ua_per_doublet_w_per_k": 1.45e6}
COOLER = {"surface_temperature_c": CHALLENGE["surface_temperature_c"] - 1.5}


def tests(peak_day):
    """(label, dict(year, air K, cooling x, heating x, challenge, assumptions))."""
    return [
        ("base (KNMI 2025)", {}),
        ("producer 1.5 K cooler", {"ch": COOLER}),
        ("gradient 29 degC/km", {"ch": {"geothermal_gradient_c_per_km": 29.0}}),
        (
            "low reservoir (28.1 degC/km, 100 mD)",
            {"ch": {"geothermal_gradient_c_per_km": 28.1, "permeability_md": 100.0}},
        ),
        ("whole source down 35 days (summer)", {"a": {"geothermal_outage_common": 1.0}}),
        (
            "whole source down 35 days from the heating peak",
            {"a": {"geothermal_outage_common": 1.0, "geothermal_outage_start_day": peak_day}},
        ),
        ("KNMI 2020", {"year": 2020}),
        ("KNMI 2020, air +2 K", {"year": 2020, "air": 2.0}),
        ("KNMI 2020, cooling +10 %", {"year": 2020, "cool": 1.1}),
        ("KNMI 2014, air +1 K", {"year": 2014, "air": 1.0}),
        ("heating and cooling +10 %", {"cool": 1.1, "heat": 1.1}),
        ("smaller HEX (1.45 MW/K, ~3 K approach)", {"a": HEX_3K}),
        ("smaller HEX and producer 1.5 K cooler", {"ch": COOLER, "a": HEX_3K}),
    ]


def climate_for(knmi, year=2025, air=0.0, cool=1.0, heat=1.0):
    """Demand on one KNMI year, with air temperatures and demand shifted."""
    c = with_climate(load_demand(INPUTS), read_knmi_daily(knmi, year), "max")
    for k in ("ambient_c", "wet_bulb_c", "ambient_mean_c"):
        if k in c:
            c[k] = c[k] + air
    c["cooling_mw"] = c["cooling_mw"] * cool
    c["heating_mw"] = c["heating_mw"] * heat
    return c


def _run(args):
    knmi, design_label, test_label, t = args
    depth, chiller = DESIGNS[design_label]
    c = climate_for(knmi, t.get("year", 2025), t.get("air", 0.0), t.get("cool", 1.0),
                    t.get("heat", 1.0))
    # the design is sized on the official 2025 basis, not on the stressed demand
    base = climate_for(knmi)
    d = make_design({**PICK, "depth_m": depth, "chiller_capacity_mw": chiller},
                    float(base["heating_mw"].max()), float(base["cooling_mw"].max()))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        _, s = run_year(d, c, {**CHALLENGE, **t.get("ch", {})}, {**ASSUMPTIONS, **t.get("a", {})})
    e = s["energy_mwh"]
    return {
        "design": design_label,
        "test": test_label,
        "meets_all_hard_rules": bool(s["all_hard_constraints_met"]),
        "unmet_mwh": round(e["unmet_heating"] + e["unmet_cooling"], 1),
        "lcoe_eur_per_mwh": round(s["economics"]["lcoe_eur_per_mwh"], 2),
        "co2_t_per_year": round(s["kpi"]["co2_t_per_year"]),
    }


def main():
    """Run every design on every test and write the tables."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--knmi", required=True, help="KNMI etmgeg daily file")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    peak_day = float(load_demand(INPUTS)["heating_mw"].idxmax())
    cases = tests(peak_day)
    jobs = [(args.knmi, d, label, t) for d in DESIGNS for label, t in cases]
    with ProcessPoolExecutor(args.workers) as pool:
        rows = list(pool.map(_run, jobs))
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "stress.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    by = {(r["design"], r["test"]): r for r in rows}
    lines = [
        "# Margin study: LCOE EUR/MWh (CO2 t/yr), X = misses demand (unmet MWh)",
        "",
        "| test | " + " | ".join(DESIGNS) + " |",
        "|---|" + "---|" * len(DESIGNS),
    ]
    for label, _ in cases:
        cells = []
        for d in DESIGNS:
            r = by[(d, label)]
            mark = "" if r["meets_all_hard_rules"] else f" **X {r['unmet_mwh']} MWh**"
            cells.append(f"{r['lcoe_eur_per_mwh']:.2f} ({r['co2_t_per_year']}){mark}")
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    passed = {d: sum(by[(d, lab)]["meets_all_hard_rules"] for lab, _ in cases) for d in DESIGNS}
    lines.append("| **tests passed** | " + " | ".join(f"{passed[d]}/{len(cases)}" for d in DESIGNS)
                 + " |")
    (OUT / "stress.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
