"""Shallow wells plus a heat pump: the brief's own trade-off (3 km well versus 1.5 km + heat pump).

The full screen starts at 2.5 km. This run adds 1.5 / 1.8 / 2.0 / 2.2 km, with the
reference 2.5 km and the pick's 3.1 km for comparison, on the same basis as the full
screen (KNMI weather, staggered stops, lined casing, ledger prices). Each depth gets
reservoir temperature from the 30 degC/km gradient and hydrostatic pressure, as the
brief allows.

    PYTHONPATH=src python simulator_examples/run_shallow_wells.py \
        --knmi simulator_examples/weather/knmi_etmgeg_240_1991_2025.txt

Writes simulator_examples/outputs/shallow_wells/results.csv and summary.md.
"""

import argparse
import itertools
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

from gemini_design.challenge import load_demand
from gemini_design.climate import read_knmi_daily, with_climate
from run_full_screen import COOLING, INPUTS, _run

OUT = Path(__file__).parent / "outputs" / "shallow_wells"
DEPTHS_M = (1500, 1800, 2000, 2200, 2500, 3100)
COOL = [c for c in COOLING if c[0] in ("screw + dry cooler", "air-cooled + free cooling + ATES x3")]


def main():
    """Run the shallow grid and write the results."""
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--knmi", required=True)
    p.add_argument("--year", type=int, default=2025)
    p.add_argument("--workers", type=int, default=4)
    a = p.parse_args()
    climate = with_climate(load_demand(INPUTS), read_knmi_daily(a.knmi, a.year), "max")
    jobs = []
    for n, depth, upgrade, chp, (label, cool) in itertools.product(
        (1, 2, 3), DEPTHS_M, ("boiler", "heat_pump"), (False, True), COOL
    ):
        req = {"n_doublets": n, "depth_m": depth, "upgrade": upgrade, "chp": chp, **cool}
        jobs.append((label, req, climate))
    with ProcessPoolExecutor(a.workers) as pool:
        rows = list(pool.map(_run, jobs, chunksize=2))
    OUT.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "results.csv", index=False)
    ok = df[df["meets_all_hard_rules"]]
    best = (
        ok.sort_values("lcoe_eur_per_mwh")
        .groupby(["depth_m", "upgrade"], as_index=False)
        .first()[["depth_m", "upgrade", "design", "lcoe_eur_per_mwh", "co2_t_per_year",
                  "capex_meur", "electricity_mwh", "purchased_gas_mwh"]]
    )
    text = (
        f"# Shallow wells + heat pump, KNMI {a.year}\n\n"
        f"{len(df)} runs, {len(ok)} meet every rule.\n\n"
        "## Cheapest passing design per depth and top-up\n\n" + best.to_markdown(index=False) + "\n"
    )
    (OUT / "summary.md").write_text(text, encoding="utf-8")
    print(text)
    print(df[~df["meets_all_hard_rules"]].groupby(["depth_m", "upgrade"])["failed_rules"].first())


if __name__ == "__main__":
    main()
