"""The selected design on every measured year of KNMI Schiphol weather.

The report numbers were first made on the ASHRAE IWEC typical year for
Amsterdam, which has a cool summer. This script runs the pick (staggered
35-day stops, 33 MW boiler, see ``run_outage_study.py``) on each year of measured KNMI
daily weather for Schiphol, station 240, aligned by day of year with the
2027 demand profiles, for each backup chiller size given, and optionally on
an EPW typical year for comparison.

    $env:PYTHONPATH="src"
    python simulator_examples/run_weather_years.py ^
        --knmi simulator_examples/weather/knmi_etmgeg_240_1991_2025.txt ^
        [--epw NLD_Amsterdam.062400_IWEC.epw] [--chillers 6 9]

Writes simulator_examples/outputs/weather_years/: years.csv and years.md.
"""

import argparse
import csv
from pathlib import Path

from run_outage_study import run

from gemini_design.challenge import add_inputs_argument, load_demand
from gemini_design.climate import read_epw_daily, read_knmi_daily, with_climate

OUT = Path(__file__).parent / "outputs" / "weather_years"


def main():
    """Run the study and write the results."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--knmi", required=True, help="KNMI etmgeg daily file")
    parser.add_argument("--epw", help="EnergyPlus typical year, for comparison")
    parser.add_argument("--first", type=int, default=1991)
    parser.add_argument("--last", type=int, default=2025)
    parser.add_argument("--chillers", type=float, nargs="+", default=[6.0, 9.0])
    add_inputs_argument(parser)
    args = parser.parse_args()
    demand = load_demand(args.inputs)
    years = [(str(y), read_knmi_daily(args.knmi, y)) for y in range(args.first, args.last + 1)]
    if args.epw:
        years.insert(0, (Path(args.epw).stem, read_epw_daily(args.epw)))

    rows = []
    for label, weather in years:
        climate = with_climate(demand, weather, "max")
        for mw in args.chillers:
            r = run(climate, label, {"chiller_capacity_mw": mw})
            rows.append(
                {
                    "weather": label,
                    "chiller_mw": mw,
                    "mean_air_c": round(float(weather["mean"].mean()), 2),
                    "summer_days_max_above_25c": int((weather["max"] > 25.0).sum()),
                    "unmet_cooling_mwh": r["unmet_cooling_mwh"],
                    "unmet_heating_mwh": r["unmet_heating_mwh"],
                    "co2_t_per_year": r["co2_t_per_year"],
                    "lcoe_eur_per_mwh": r["lcoe_eur_per_mwh"],
                    "all_hard_rules": r["all_hard_rules"],
                }
            )
            print(rows[-1], flush=True)

    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "years.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    lines = [
        "# Selected design on measured KNMI Schiphol weather",
        "",
        f"KNMI station 240, {args.first}-{args.last}; staggered 35-day stops, 33 MW boiler.",
        "",
    ]
    for mw in args.chillers:
        knmi = [r for r in rows if r["chiller_mw"] == mw and r["weather"].isdigit()]
        fails = [r["weather"] for r in knmi if not r["all_hard_rules"]]
        lcoe = sorted(r["lcoe_eur_per_mwh"] for r in knmi)
        lines.append(
            f"- {mw:g} MW backup chiller: hard rules met in {len(knmi) - len(fails)} of "
            f"{len(knmi)} years (fails: {', '.join(fails) or 'none'}); LCOE "
            f"{lcoe[0]:.2f}-{lcoe[-1]:.2f}, median {lcoe[len(lcoe) // 2]:.2f} EUR/MWh."
        )
    cols = list(rows[0])
    lines += ["", "| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(str(r[c]) for c in cols) + " |" for r in rows]
    (OUT / "years.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:8]))


if __name__ == "__main__":
    main()
