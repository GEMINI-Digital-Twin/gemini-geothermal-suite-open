"""One doublet with a realistic seasonal pit heat store, against the current pick.

GPT-6.1 Sol's own store model (3 Nov 2026, energy only: no temperatures, 0.1 %/day loss,
500 EUR/MWh) made 1 doublet + a 20 GWh store look cheaper than our pick on our basis
(34.29 against 35.71 EUR/MWh). This script reruns that comparison with the built-in pit
store model (``gemini_design.pit_storage``): stratified layers, a 90 degC liner limit, a
boiler top-up from the store's top temperature to the 100 degC supply, lid and ground
losses that depend on the pit size, 30,000-250,000 m3 per pit, and a size-based cost
curve fitted to the Danish pits plus land.

Basis (the report's): staggered 35-day doublet stops in the lowest-load window, CO2 at
80 EUR/t, KNMI Schiphol daily weather (2025 by default), lined casing priced. Runs, no LLM:

- the current pick (2 doublets, 3.1 km, CHP, air-cooled screw 9 MW + free cooling +
  3 ATES pairs, 33 MW boiler) and 1 doublet without a store;
- 1 doublet + pit store, swept over volume and rating, on two plants: Sol's (screw
  chiller with dry cooler, 0.55 MWe CHP, default boiler) and the pick's cooling side;
- the best store case under kinder assumptions (cheaper pits, half the losses, a 95 degC
  liner), under a whole-source winter stop and at a CO2 price of 180 EUR/t;
- 2 doublets + a pit store, for completeness.

    $env:PYTHONPATH="src"
    python simulator_examples/run_pit_store_study.py `
        --knmi simulator_examples/weather/knmi_etmgeg_240_1991_2025.txt

Writes simulator_examples/outputs/pit_store_study/: results.csv and summary.md.
"""

import argparse
import warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

from gemini_agent.physics_gate import check_run
from gemini_agent.tools import make_design
from gemini_design.annual import run_year
from gemini_design.challenge import ASSUMPTIONS, CHALLENGE, default_inputs_dir, load_demand
from gemini_design.climate import read_knmi_daily, with_climate

HERE = Path(__file__).parent
INPUTS = default_inputs_dir()  # $GEMINI_INPUTS or the official 2027 inputs
OUT = HERE / "outputs" / "pit_store_study"

FINAL_PICK = {
    "n_doublets": 2,
    "depth_m": 3100,
    "upgrade": "boiler",
    "cooling": "electric",
    "chp": True,
    "chiller_type": "air_cooled_screw",
    "free_cooling": True,
    "ates_doublets": 3,
    "chiller_capacity_mw": 9.0,
    "boiler_capacity_mw": 33.0,
}
SOL_PLANT = {
    "n_doublets": 1,
    "depth_m": 3100,
    "upgrade": "boiler",
    "cooling": "electric",
    "chp": True,
    "chp_capacity_mw_el": 0.55,
    "chiller_type": "screw_dry_cooler",
}
PICK_COOLING_1D = {**FINAL_PICK, "n_doublets": 1, "chp_capacity_mw_el": 0.55}
VOLUMES_M3 = (100_000, 200_000, 250_000, 350_000, 500_000, 750_000)
RATINGS_MW = (10.0, 15.0, 25.0)
KINDER = {
    "cheaper pits (-30 %)": {"pit_store_cost_ref_eur_per_m3": 28.0},
    "half the losses": {
        "pit_store_lid_u_w_per_m2_k": 0.075,
        "pit_store_ground_u_w_per_m2_k": 0.075,
    },
    "95 degC liner": {"pit_store_top_max_c": 95.0},
    "no land cost, no price index": {
        "pit_store_land_cost_eur_per_m2": 0.0,
        "pit_store_price_index": 1.0,
    },
    "all four together": {
        "pit_store_cost_ref_eur_per_m3": 28.0,
        "pit_store_lid_u_w_per_m2_k": 0.075,
        "pit_store_ground_u_w_per_m2_k": 0.075,
        "pit_store_top_max_c": 95.0,
        "pit_store_land_cost_eur_per_m2": 0.0,
        "pit_store_price_index": 1.0,
    },
}
# one pit larger than any built (upper bound for stores above 250,000 m3, which the model
# otherwise splits into equal pits run in parallel, the less efficient way to run them)
SINGLE_PIT = {"pit_store_volume_max_m3": 600_000.0}
BASES = {
    "winter stop (both doublets down 35 days from day 11)": {
        "geothermal_outage_common": 1.0,
        "geothermal_outage_start_day": 11.0,
    },
    "CO2 at 180 EUR/t": {"co2_price_eur_per_t": 180.0},
}


def store(v, mw):
    """Design keys of a pit store."""
    return {"pit_store_m3": float(v), "pit_store_mw": float(mw)} if v else {}


def cases():
    """(group, label, design request, assumption changes) for the main sweep."""
    out = [
        ("reference", "current pick (2D, ATES, 33 MW boiler)", FINAL_PICK, {}),
        ("reference", "1D, Sol's plant, no store", SOL_PLANT, {}),
        ("reference", "1D, pick's cooling, no store", PICK_COOLING_1D, {}),
    ]
    for v in VOLUMES_M3:
        for mw in RATINGS_MW:
            out.append(
                (
                    "1D + pit, Sol's plant",
                    f"1D + {v / 1000:g}k m3 @ {mw:g} MW",
                    {**SOL_PLANT, **store(v, mw)},
                    {},
                )
            )
    for v in (300_000, 350_000, 400_000):
        out.append(
            (
                "one pit above the built range (upper bound)",
                f"1D + one {v / 1000:g}k m3 pit @ 15 MW",
                {**SOL_PLANT, **store(v, 15)},
                SINGLE_PIT,
            )
        )
    for v in (200_000, 350_000, 500_000):
        out.append(
            (
                "1D + pit, pick's cooling",
                f"1D pick-cooling + {v / 1000:g}k m3 @ 25 MW",
                {**PICK_COOLING_1D, **store(v, 25)},
                {},
            )
        )
    for v in (100_000, 250_000):
        out.append(
            ("2D + pit", f"pick + {v / 1000:g}k m3 @ 15 MW", {**FINAL_PICK, **store(v, 15)}, {})
        )
    return out


def run_case(job):
    """One year run; return its row."""
    group, label, req, changes, climate = job
    assumptions = {**ASSUMPTIONS, **changes}
    peaks = float(climate["heating_mw"].max()), float(climate["cooling_mw"].max())
    design = make_design(req, *peaks)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        daily, s = run_year(design, climate, CHALLENGE, assumptions)
    gate = check_run(s, daily, CHALLENGE, assumptions)
    e, k, econ = s["energy_mwh"], s["kpi"], s["economics"]
    pit = s.get("pit_store", {})
    return {
        "group": group,
        "case": label,
        "design": s["design"]["name"],
        "meets_all_hard_rules": s["all_hard_constraints_met"],
        "physics_gate": "pass" if gate["passed"] else "FAIL",
        "lcoe_eur_per_mwh": round(econ["lcoe_eur_per_mwh"], 2),
        "co2_t_per_year": round(k["co2_t_per_year"]),
        "capex_meur": round(econ["capex_eur"]["total"] / 1e6, 2),
        "store_capex_meur": round(econ["capex_eur"].get("pit_store", 0.0) / 1e6, 2),
        "purchased_gas_mwh": round(e["purchased_gas_fuel"]),
        "store_volume_m3": round(pit.get("volume_m3", 0)),
        "pits": pit.get("pits", 0),
        "land_ha": round(pit.get("land_ha", 0.0), 1),
        "store_capacity_mwh": round(pit.get("capacity_mwh", 0)),
        "store_in_mwh": round(pit.get("charge_mwh", 0)),
        "store_out_mwh": round(pit.get("discharge_mwh", 0)),
        "boiler_topup_mwh": round(pit.get("boiler_topup_mwh", 0)),
        "store_loss_mwh": round(pit.get("loss_mwh", 0)),
        "store_efficiency": round(pit.get("storage_efficiency", 0.0), 2),
        "max_top_c": round(pit.get("max_top_c", 0.0), 1),
        "cost_eur_per_m3": round(pit.get("cost_eur_per_m3", 0.0), 1),
        "unmet_heating_mwh": round(e["unmet_heating"], 1),
    }


TABLE_COLS = [
    "case",
    "lcoe_eur_per_mwh",
    "co2_t_per_year",
    "store_capex_meur",
    "pits",
    "land_ha",
    "store_in_mwh",
    "store_out_mwh",
    "boiler_topup_mwh",
    "store_loss_mwh",
    "store_efficiency",
    "max_top_c",
    "meets_all_hard_rules",
    "physics_gate",
]


def table(df):
    """Markdown table of the result rows."""
    lines = ["| " + " | ".join(TABLE_COLS) + " |", "|" + "---|" * len(TABLE_COLS)]
    lines += ["| " + " | ".join(str(r[c]) for c in TABLE_COLS) + " |" for _, r in df.iterrows()]
    return lines


def main():
    """Run the sweep, the sensitivities and write the results."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--knmi", required=True, help="KNMI etmgeg daily file")
    parser.add_argument("--year", type=int, default=2025, help="year to take from the file")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    climate = with_climate(load_demand(INPUTS), read_knmi_daily(args.knmi, args.year), "max")

    jobs = [(*c, climate) for c in cases()]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        main_rows = list(pool.map(run_case, jobs))
    df = pd.DataFrame(main_rows)
    stores = df[(df["group"] == "1D + pit, Sol's plant") & df["meets_all_hard_rules"]]
    best = stores.sort_values("lcoe_eur_per_mwh").iloc[0]
    best_req = next(c for c in cases() if c[1] == best["case"])

    extra = []
    for name, changes in KINDER.items():
        extra.append(("kinder store assumptions", f"{best['case']}, {name}", best_req[2], changes))
    for name, changes in BASES.items():
        for label, req in (
            ("current pick", FINAL_PICK),
            (best["case"], best_req[2]),
            ("1D, Sol's plant, no store", SOL_PLANT),
        ):
            extra.append((f"basis: {name}", f"{label}, {name}", req, changes))
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        extra_rows = list(pool.map(run_case, [(*c, climate) for c in extra]))
    df = pd.concat([df, pd.DataFrame(extra_rows)], ignore_index=True)

    OUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT / "results.csv", index=False)
    lines = [
        "# One doublet + a realistic pit heat store, against the current pick",
        "",
        "Author: Sa'eed Telvari",
        "",
        f"Simulator runs, no LLM (`run_pit_store_study.py`), weather {Path(args.knmi).name} "
        f"({args.year}). Store model: `gemini_design.pit_storage` (built in). Basis: "
        "staggered 35-day doublet stops in the lowest-load window, CO2 80 EUR/t, lined casing.",
        "",
    ]
    for group in df["group"].unique():
        lines += [f"## {group}", ""] + table(df[df["group"] == group]) + [""]
    (OUT / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    for _, r in df.iterrows():
        print(
            f"{r['case']:70s} {r['lcoe_eur_per_mwh']:7.2f} EUR/MWh {r['co2_t_per_year']:6d} t "
            f"{r['physics_gate']}"
        )


if __name__ == "__main__":
    main()
