"""Check the district return temperatures against the brief's constraints.

The brief fixes the supply temperatures (100 degC heating, 20 degC cooling)
but not the returns; the organisers said (1 Nov 2026) they are ours to
choose as long as no constraint is broken. The binding one is the 40 K cap
on brine cooling (producer to injector). The pick uses 40 degC heating
return and 26 degC cooling return (``challenge.ASSUMPTIONS``). This script
sweeps both and reports cost, CO2, demand met and the largest brine
cooling, so the choice can be justified.

    $env:PYTHONPATH="src"
    python simulator_examples/run_return_temperature_check.py \
        --knmi simulator_examples/weather/knmi_etmgeg_240_1991_2025.txt --year 2025

Writes simulator_examples/outputs/return_temperatures/results.md and .csv.
"""

import argparse
import csv
import sys
import warnings
from pathlib import Path

from gemini_agent.tools import make_design
from gemini_design.annual import run_year
from gemini_design.challenge import ASSUMPTIONS, CHALLENGE, default_inputs_dir, load_demand
from gemini_design.climate import read_epw_daily, read_knmi_daily, with_climate

sys.path.insert(0, str(Path(__file__).parent))
from run_final_pick import PICK  # noqa: E402

INPUTS = default_inputs_dir()  # $GEMINI_INPUTS or the official 2027 inputs
OUT = Path(__file__).parent / "outputs" / "return_temperatures"
SWEEPS = {
    "heating_return_c": [32.0, 35.0, 40.0, 45.0, 50.0, 55.0, 60.0, 62.0],
    "cooling_return_c": [23.0, 24.0, 26.0, 28.0, 30.0],
}


def main():
    """Run the sweeps and write the results."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--epw", help="EnergyPlus weather file")
    src.add_argument("--knmi", help="KNMI etmgeg daily file")
    parser.add_argument("--year", type=int, default=2025, help="year to take from a KNMI file")
    args = parser.parse_args()
    weather = read_epw_daily(args.epw) if args.epw else read_knmi_daily(args.knmi, args.year)
    demand = with_climate(load_demand(INPUTS), weather, "max")
    design = make_design(PICK, 30.0, 10.0)
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for key, values in SWEEPS.items():
        for value in values:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                _, s = run_year(design, demand, CHALLENGE, {**ASSUMPTIONS, key: value})
            e, k = s["energy_mwh"], s["kpi"]
            rows.append(
                {
                    "parameter": key,
                    "value_c": value,
                    "pick_value": value == ASSUMPTIONS[key],
                    "lcoe_eur_per_mwh": round(s["economics"]["lcoe_eur_per_mwh"], 2),
                    "co2_t_per_year": round(k["co2_t_per_year"]),
                    "unmet_heating_mwh": round(e["unmet_heating"], 1),
                    "unmet_cooling_mwh": round(e["unmet_cooling"], 1),
                    "max_brine_cooling_k": round(k["max_brine_cooling_k"], 2),
                    "geothermal_share_of_heat": round(k["geothermal_share_of_heat"], 3),
                    "all_hard_rules": s["all_hard_constraints_met"],
                }
            )
            print(rows[-1], flush=True)
    with open(OUT / "results.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    lines = [
        "# District return temperatures against the constraints",
        "",
        f"Weather: {Path(args.epw or args.knmi).name}. Pick: {PICK}.",
        "",
        "| " + " | ".join(rows[0]) + " |",
        "|" + "---|" * len(rows[0]),
    ]
    lines += ["| " + " | ".join(str(v) for v in r.values()) + " |" for r in rows]
    (OUT / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
