"""What to do with the co-produced gas: burn, keep dissolved, co-inject, a disposal well, or export.

Runs gemini_design.gas_handling.compare on the selected design (and, for
reference, on the design the first report picked) with a year of
Amsterdam weather. Every option is priced with the team's prices
(EUR 80/t CO2) and its break-even CO2 price is reported.

    $env:PYTHONPATH="src"
    python simulator_examples/run_gas_options_study.py --epw NLD_Amsterdam.062400_IWEC.epw

Writes simulator_examples/outputs/gas_options/results.csv and results.md.
"""

import argparse
import csv
from pathlib import Path

from gemini_design.challenge import default_inputs_dir, load_demand
from gemini_design.climate import read_epw_daily, read_knmi_daily, with_climate
from gemini_design.gas_handling import compare, summary_table
from gemini_design.plant import Design
from gemini_design.screening import chp_size_mw_el

INPUTS = default_inputs_dir()  # $GEMINI_INPUTS or the official 2027 inputs
OUT = Path(__file__).parent / "outputs" / "gas_options"


def designs():
    """The realistic candidate and the first report's pick."""
    common = dict(
        n_doublets=2,
        depth_m=3100.0,
        upgrade="boiler",
        cooling="electric",
        chp_capacity_mw_el=chp_size_mw_el(2),
    )
    return [
        Design(
            **common,
            chiller_type="air_cooled_screw",
            free_cooling=True,
            ates_doublets=3,
            chiller_capacity_mw=6.0,
        ),
        Design(**common, chiller_capacity_mw=12.0),
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
    demand = with_climate(load_demand(INPUTS), weather, "max")
    OUT.mkdir(parents=True, exist_ok=True)
    rows, lines = [], ["# Co-produced gas options", ""]
    for design in designs():
        options, info = compare(design, demand)
        table = summary_table(options)
        for r in table:
            rows.append({"design": design.name, **r})
        lines += [
            f"## {design.name}",
            "",
            f"Bubble point {info['bubble_point_bar_at_wellhead']:.0f} bar at the wellhead "
            f"({info['wellhead_temperature_c']:.0f} degC), "
            f"{info['bubble_point_bar_at_injection']:.0f} bar at the injection temperature. "
            f"Gas produced {info['gas_nm3_per_year'] / 1e6:.2f} million Nm3/yr; burning or "
            f"flaring it emits {info['co2_from_associated_gas_t']:,.0f} t CO2/yr, of which "
            f"{info['co2_inherent_t']:,.0f} t is the CO2 the gas already holds.",
            "",
            "| option | LCOE EUR/MWh | CO2 t/yr (plant) | CO2 t/yr (global) | saved t/yr | "
            "abatement EUR/t | break-even CO2 price EUR/t | notes |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for r in table:
            lines.append(
                f"| {r['option']} | {r['lcoe_eur_per_mwh']} | {r['co2_t_per_year']:,} | "
                f"{r['global_co2_t_per_year']:,} | {r['co2_saved_t']:,} | "
                f"{r['abatement_eur_per_t'] if r['abatement_eur_per_t'] is not None else '-'} | "
                f"{r['break_even_co2_price_eur_per_t'] or '-'} | {r['notes']} |"
            )
        lines.append("")
    with open(OUT / "results.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    (OUT / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
