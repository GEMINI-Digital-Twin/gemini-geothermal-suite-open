"""Series or parallel doublets: what changes for the district heating side.

Runs gemini_design.arrangement.compare_year for doublet pairs at equal and
at mixed depths, each connected three ways (one mixed header, split
parallel HEXs, series HEXs coolest first), over the 2027 heating profile.

    $env:PYTHONPATH="src"
    python simulator_examples/run_doublet_arrangement_study.py

Writes simulator_examples/outputs/arrangement/results.csv and results.md.
"""

import csv
from pathlib import Path

from gemini_design.arrangement import compare_year
from gemini_design.challenge import default_inputs_dir, load_demand

INPUTS = default_inputs_dir()  # $GEMINI_INPUTS or the official 2027 inputs
OUT = Path(__file__).parent / "outputs" / "arrangement"
PAIRS = (
    (3100, 3100),  # the pick
    (2800, 3400),  # same drilling metres, one cooler and one hotter doublet
    (2500, 3700),
    (2500, 3400),  # 300 m less drilling
    (2500, 3100),  # 600 m less drilling
)
LABELS = {
    "parallel_header": "parallel, one header + HEX",
    "parallel_split": "parallel, own HEX each",
    "series": "series, coolest first",
}


def main():
    """Run the study and write the results."""
    demand = load_demand(INPUTS)
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for depths in PAIRS:
        for arrangement, r in compare_year(depths, demand).items():
            peak = r["peak_day"]
            rows.append(
                {
                    "depths_m": "+".join(str(int(d)) for d in r["depths_m"]),
                    "arrangement": arrangement,
                    "geothermal_heat_mwh": round(r["geothermal_heat_mwh"]),
                    "boiler_heat_mwh": round(r["boiler_heat_mwh"]),
                    "pump_electricity_mwh": round(r["pump_electricity_mwh"]),
                    "co2_t": round(r["co2_t"]),
                    "energy_cost_keur": round(r["energy_cost_eur"] / 1e3),
                    "well_capex_meur": round(r["well_capex_eur"] / 1e6, 2),
                    "wells_plus_energy_keur_per_year": round(
                        r["wells_plus_energy_eur_per_year"] / 1e3
                    ),
                    "peak_day_after_geothermal_c": round(peak["district_after_geothermal_c"], 1),
                    "peak_day_boiler_mw": round(peak["boiler_mw"], 2),
                    "peak_day_brine_cooling_k": "/".join(
                        f"{k:.0f}" for k in peak["brine_cooling_k"]
                    ),
                }
            )
    with open(OUT / "results.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    base = next(
        r for r in rows if r["depths_m"] == "3100+3100" and r["arrangement"] == "parallel_header"
    )
    lines = [
        "# Series or parallel doublets (heating side, 2027 profile)",
        "",
        "Boiler and pump energy are priced at the team's prices incl. CO2; wells are annualised "
        "(6 %, 30 years, 2 % O&M). Cooling, CHP and associated gas do not depend on the "
        "arrangement and are left out. The delta is against the pick (3100+3100, one header).",
        "",
        "| doublets (m) | arrangement | geothermal MWh | boiler MWh | pumps MWh | CO2 t | "
        "wells + energy kEUR/yr | delta kEUR/yr | peak day: after geothermal degC | "
        "brine dT K |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        delta = r["wells_plus_energy_keur_per_year"] - base["wells_plus_energy_keur_per_year"]
        lines.append(
            f"| {r['depths_m']} | {LABELS[r['arrangement']]} | {r['geothermal_heat_mwh']:,} | "
            f"{r['boiler_heat_mwh']:,} | {r['pump_electricity_mwh']:,} | {r['co2_t']:,} | "
            f"{r['wells_plus_energy_keur_per_year']:,} | {delta:+,} | "
            f"{r['peak_day_after_geothermal_c']} | {r['peak_day_brine_cooling_k']} |"
        )
    (OUT / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
