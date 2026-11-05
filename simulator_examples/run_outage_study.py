"""Geothermal source outage study for the selected design.

The organisers confirmed (1 Nov 2026) that the 330 operating days are the
availability of the geothermal source only: it can be shut down for 35
days, planned or unplanned, and the full system (backup boiler, chillers,
ATES) must still meet heating and cooling demand on all 365 days.

A second answer (1 Nov 2026, late) made the schedule our design choice:
several doublets may take their maintenance at different times, or one
doublet can rely on backup. The final pick (Sa'eed, 2 Nov) uses staggered
planned stops and a 33 MW boiler. This script runs its scenario set:

S1  headline: staggered planned stops (plus the best summer pair, and the
    same plant with a 30 MW boiler for comparison)
S2  the whole source down together in the lowest-load window
S3  one doublet fails (unplanned) at the winter heating peak
S4  both doublets fail at the winter peak
S5  both fail at the winter peak with heating demand +6 % (one sigma of the
    uncertainty study), with the 33 MW boiler and with a 30 MW one
S6  the whole-source outage started on every day of the year

    $env:PYTHONPATH="src"
    python simulator_examples/run_outage_study.py \
        --knmi simulator_examples/weather/knmi_etmgeg_240_1991_2025.txt --year 2025

Writes simulator_examples/outputs/outage/results.csv and results.md.
"""

import argparse
import csv
import sys
from pathlib import Path

import numpy as np

from gemini_agent.tools import make_design
from gemini_design.annual import run_year
from gemini_design.challenge import (
    ASSUMPTIONS,
    CHALLENGE,
    add_inputs_argument,
    default_inputs_dir,
    load_demand,
)
from gemini_design.climate import read_epw_daily, read_knmi_daily, with_climate

INPUTS = default_inputs_dir()  # $GEMINI_INPUTS or the official 2027 inputs
OUT = Path(__file__).parent / "outputs" / "outage"
sys.path.insert(0, str(Path(__file__).parent))
from run_final_pick import PICK  # noqa: E402  (staggered stops, 9 MW chiller, 33 MW boiler)

OUTAGE_DAYS = 365 - int(CHALLENGE["operating_days"])


def _windows(daily, n_doublets):
    """Return the days with fewer than all doublets available, as 'MM-DD..MM-DD' ranges."""
    short = daily["n_available"] < n_doublets
    dates, out, start = daily["date"], [], None
    for i in range(len(daily)):
        if short.iloc[i] and start is None:
            start = i
        if start is not None and (not short.iloc[i] or i == len(daily) - 1):
            end = i if short.iloc[i] else i - 1
            n = "0" if (daily["n_available"].iloc[start : end + 1] == 0).all() else "1"
            out.append(f"{dates.iloc[start]:%m-%d}..{dates.iloc[end]:%m-%d} ({n} on)")
            start = None
    return "; ".join(out)


def run(demand, label, design_args=None, **assumption_changes):
    """Run one year and return a result row."""
    args = {**PICK, **(design_args or {})}
    design = make_design(args, 30.0, 10.0)  # sizing rules on the brief's peaks
    assumptions = {**ASSUMPTIONS, **assumption_changes}
    daily, s = run_year(design, demand, CHALLENGE, assumptions)
    e, k, econ = s["energy_mwh"], s["kpi"], s["economics"]
    headroom = design.boiler_capacity_mw - daily["boiler_heat_w"].max() / 1e6
    return {
        "case": label,
        "doublet_outages": _windows(daily, design.n_doublets),
        "days_without_geothermal": k["days_without_geothermal"],
        "boiler_mw": design.boiler_capacity_mw,
        "unmet_heating_mwh": round(e["unmet_heating"], 1),
        "unmet_cooling_mwh": round(e["unmet_cooling"], 1),
        "purchased_gas_mwh": round(e["purchased_gas_fuel"]),
        "peak_boiler_mw": round(daily["boiler_heat_w"].max() / 1e6, 2),
        "boiler_headroom_mw": round(headroom, 2),
        "co2_t_per_year": round(k["co2_t_per_year"]),
        "lcoe_eur_per_mwh": round(econ["lcoe_eur_per_mwh"], 2),
        "all_hard_rules": s["all_hard_constraints_met"],
    }


def main():
    """Run the study and write the results."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--epw", help="EnergyPlus weather file")
    src.add_argument("--knmi", help="KNMI etmgeg daily file")
    parser.add_argument("--year", type=int, default=2025, help="year to take from a KNMI file")
    parser.add_argument("--step", type=int, default=1, help="days between tested outage starts")
    add_inputs_argument(parser)
    args = parser.parse_args()
    weather = read_epw_daily(args.epw) if args.epw else read_knmi_daily(args.knmi, args.year)
    demand = with_climate(load_demand(args.inputs), weather, "max")
    OUT.mkdir(parents=True, exist_ok=True)

    stag = {"geothermal_outage_common": 0.0}
    whole = {"geothermal_outage_common": 1.0}
    b30 = {"boiler_capacity_mw": 30.0}
    heat = demand["heating_mw"].to_numpy()
    winter = float(np.argmax(np.convolve(heat, np.ones(OUTAGE_DAYS), mode="valid")))
    hot = demand.copy()
    hot["heating_mw"] = hot["heating_mw"] * 1.06
    summer = [
        run(demand, f"day {d}", geothermal_outage_start_day=float(d), **stag)
        for d in range(120, 231, 7)
    ]
    best = min(summer, key=lambda r: (r["lcoe_eur_per_mwh"], r["co2_t_per_year"]))
    rows = [
        run(demand, "S1 headline: staggered planned stops, 33 MW boiler", **stag),
        {**best, "case": f"S1b staggered, best summer pair (doublet 1 from {best['case']})"},
        run(demand, "S1c staggered, 30 MW boiler (= peak)", b30, **stag),
        run(demand, "S2 whole source planned in the lowest-load window", **whole),
        run(
            demand,
            "S3 one doublet fails at the winter peak",
            geothermal_outage_start_day=winter,
            **stag,
        ),
        run(
            demand,
            "S4 both doublets fail at the winter peak",
            geothermal_outage_start_day=winter,
            **whole,
        ),
        run(
            hot,
            "S5 both fail at the winter peak, heating +6 %",
            geothermal_outage_start_day=winter,
            **whole,
        ),
        run(
            hot,
            "S5b same with a 30 MW boiler",
            b30,
            geothermal_outage_start_day=winter,
            **whole,
        ),
    ]
    sweep = []
    for start in range(0, 365 - OUTAGE_DAYS + 1, args.step):
        sweep.append(
            run(demand, f"start day {start}", geothermal_outage_start_day=float(start), **whole)
        )
    worst_cost = max(sweep, key=lambda r: r["lcoe_eur_per_mwh"])
    tightest = min(sweep, key=lambda r: r["boiler_headroom_mw"])
    rows += [
        {**worst_cost, "case": "S6 whole-source sweep: costliest start day"},
        {**tightest, "case": "S6 whole-source sweep: least boiler headroom"},
    ]

    for path, data in (("results.csv", rows), ("sweep.csv", sweep)):
        with open(OUT / path, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(data[0]))
            w.writeheader()
            w.writerows(data)
    met = sum(r["unmet_heating_mwh"] + r["unmet_cooling_mwh"] < 1e-3 for r in sweep)
    lcoe = [r["lcoe_eur_per_mwh"] for r in sweep]
    lines = [
        "# Geothermal source outage study",
        "",
        f"Weather: {Path(args.epw or args.knmi).name}. Pick: {PICK}.",
        "",
        f"S6: whole-source {OUTAGE_DAYS}-day outage started on each of {len(sweep)} days: "
        f"demand fully met in {met} of {len(sweep)}; LCOE {min(lcoe):.2f}-{max(lcoe):.2f} "
        "EUR/MWh.",
        "",
        "| " + " | ".join(rows[0]) + " |",
        "|" + "---|" * len(rows[0]),
    ]
    lines += ["| " + " | ".join(str(v) for v in r.values()) + " |" for r in rows]
    (OUT / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
