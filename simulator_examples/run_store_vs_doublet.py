"""Seasonal heat store or a second doublet? The comparison GPT-6.1 Sol did not run.

In the live stated-objective run of 3 Nov 2026 (agent_compare_results/2026-11-03-objective/
sol_r1), Sol priced a whole-source winter stop into every design and picked 1 doublet with a
37.5 GWh seasonal heat store. It never ran 2 doublets with a store, or a store without the stop.
This script runs those cases directly in the simulator (no LLM), with Sol's own store model
(``seasonal_heat_store.py``, registered in the ``thermal_storage`` slot), on two bases:

- A, Sol's basis: both doublets stop together for 35 days from day 11 (over the coldest
  day, 28 Jan), CO2 at 180 EUR/t.
- B, our basis: each doublet stops for 35 days at its own time in the lowest-load window
  (staggered), CO2 at the ledger price of 80 EUR/t.
- C, the client's CO2 weight without the yearly winter stop: staggered stops as in B,
  CO2 at 180 EUR/t (the basis of DeepSeek's headline in the same scenario).

Both use KNMI daily weather (Schiphol, 2025 by default), lined casing priced and the ledger
storage costs (500 EUR/MWh of capacity, 0.1 MEUR/MW of power). The designs: 1 and 2 doublets
at 3.1 km with CHP and a screw chiller with dry cooler, each with a store of 0-40 GWh at
25 MW; and our final pick (2 doublets, ATES, 33 MW boiler) for reference.

The store model is energy only: it holds MWh with a daily loss and has no temperatures.
Charged heat comes back at the 100 degC supply (gemini_design.storage), which a real pit store
does not reach without a top-up.

    $env:PYTHONPATH="src"
    python simulator_examples/run_store_vs_doublet.py `
        --knmi simulator_examples/weather/knmi_etmgeg_240_1991_2025.txt

Writes simulator_examples/outputs/store_vs_doublet/: results.csv and summary.md.
"""

import argparse
import importlib.util
import warnings
from pathlib import Path

import pandas as pd

from gemini_agent.tools import make_design, split_overrides
from gemini_design.annual import run_year
from gemini_design.challenge import default_inputs_dir, load_demand
from gemini_design.climate import read_knmi_daily, with_climate
from gemini_design.storage import STORAGE_TYPE, build_model, check_model
from gemini_simulator.registry import COMPONENT_REGISTRY

HERE = Path(__file__).parent
INPUTS = default_inputs_dir()  # $GEMINI_INPUTS or the official 2027 inputs
OUT = HERE / "outputs" / "store_vs_doublet"
SOL_MODEL = (
    HERE
    / "agent_compare_results/2026-11-03-objective/sol_r1/generated_models/seasonal_heat_store.py"
)
BASES = {
    "A": (
        "Sol: common 35-day stop from day 11, CO2 180 EUR/t",
        {
            "co2_price_eur_per_t": 180.0,
            "geothermal_outage_common": 1.0,
            "geothermal_outage_start_day": 11.0,
        },
    ),
    "B": ("ours: staggered stops in the lowest-load window, CO2 80 EUR/t", {}),
    "C": (
        "the client's CO2 weight without the yearly winter stop (DeepSeek's basis): "
        "staggered stops, CO2 180 EUR/t",
        {"co2_price_eur_per_t": 180.0},
    ),
}
STORES_GWH = (0.0, 5.0, 10.0, 20.0, 30.0, 37.5, 40.0)
STORE_MW = 25.0
SOL_PLANT = {
    "depth_m": 3100,
    "upgrade": "boiler",
    "cooling": "electric",
    "chp": True,
    "chiller_type": "screw_dry_cooler",
}
# 2 doublets, 3.1 km, CHP, air-cooled screw 9 MW + free cooling + 3 ATES pairs, 33 MW boiler
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


def register_sol_model():
    """Load Sol's store model into the thermal_storage slot and check its interface.

    Sol's model raises when the state of charge is outside 0-capacity. A store that gives
    out all its heat ends the day a rounding error below zero (available - 24 h x
    available / 24 h, e.g. -3e-14 MWh), so the next day raises. Sol's 1-doublet runs never
    emptied the store that way; 2 doublets do. The wrapper clips only that rounding excess
    (within 1e-6 of capacity, at either end) and changes nothing else.
    """
    spec = importlib.util.spec_from_file_location("seasonal_heat_store", SOL_MODEL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class SolStore(module.SeasonalHeatStore):
        def calculate_output(self, u, x=None):
            cap = float(self.parameters["capacity_mwh"])
            soc = float(u["soc_mwh"])
            tol = 1e-6 * max(cap, 1.0)
            if -tol <= soc < 0.0 or cap < soc <= cap + tol:
                u = {**u, "soc_mwh": min(max(soc, 0.0), cap)}
            return super().calculate_output(u, x)

    COMPONENT_REGISTRY[STORAGE_TYPE] = SolStore
    problems = check_model(
        build_model(
            make_design(
                {**SOL_PLANT, "n_doublets": 1, "storage_mwh": 1000.0, "storage_mw": STORE_MW},
                30.0,
                10.0,
            )
        )
    )
    if problems:
        raise RuntimeError(f"Sol's store model fails the interface check: {problems}")


def cases():
    """(label, design request, basis key) for every run."""
    out = []
    for basis in BASES:
        for n in (1, 2):
            # Sol sized the CHP at 0.55 MWe for 1 doublet; 2 doublets keep the default size
            chp = {"chp_capacity_mw_el": 0.55} if n == 1 else {}
            for gwh in STORES_GWH:
                store = {"storage_mwh": gwh * 1000, "storage_mw": STORE_MW} if gwh else {}
                req = {**SOL_PLANT, "n_doublets": n, **chp, **store}
                out.append((f"{n}D + {gwh:g} GWh store" if gwh else f"{n}D, no store", req, basis))
        out.append(("final pick (2D, ATES, 33 MW boiler)", FINAL_PICK, basis))
    return out


def run_case(label, req, basis, climate):
    """One year run; return its row."""
    challenge, assumptions, _ = split_overrides(BASES[basis][1])
    peaks = float(climate["heating_mw"].max()), float(climate["cooling_mw"].max())
    design = make_design(req, *peaks)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        _, s = run_year(design, climate, challenge, assumptions)
    e, k, econ = s["energy_mwh"], s["kpi"], s["economics"]
    return {
        "basis": basis,
        "case": label,
        "design": s["design"]["name"],
        "n_doublets": design.n_doublets,
        "storage_gwh": design.storage_mwh / 1000,
        "storage_mw": design.storage_mw,
        "meets_all_hard_rules": s["all_hard_constraints_met"],
        "unmet_heating_mwh": round(e["unmet_heating"], 1),
        "unmet_cooling_mwh": round(e["unmet_cooling"], 1),
        "lcoe_eur_per_mwh": round(econ["lcoe_eur_per_mwh"], 2),
        "co2_t_per_year": round(k["co2_t_per_year"]),
        "capex_meur": round(econ["capex_eur"]["total"] / 1e6, 2),
        "storage_capex_meur": round(econ["capex_eur"].get("storage", 0.0) / 1e6, 2),
        "purchased_gas_mwh": round(e["purchased_gas_fuel"]),
        "geothermal_heat_mwh": round(e["geothermal_heat"]),
        "boiler_heat_mwh": round(e["boiler_heat"]),
        "storage_in_mwh": round(e.get("storage_charge", 0.0)),
        "storage_out_mwh": round(e.get("storage_discharge", 0.0)),
        "storage_loss_mwh": round(e.get("storage_loss", 0.0)),
    }


def summarise(df, source):
    """Markdown summary: the main comparison, the store sweep and the cheapest per basis."""
    cols = [
        "case",
        "lcoe_eur_per_mwh",
        "co2_t_per_year",
        "capex_meur",
        "purchased_gas_mwh",
        "storage_in_mwh",
        "storage_out_mwh",
        "storage_loss_mwh",
        "meets_all_hard_rules",
    ]
    lines = [
        "# Seasonal heat store or a second doublet?",
        "",
        "Author: Sa'eed Telvari",
        "",
        f"Simulator runs, no LLM (`run_store_vs_doublet.py`), weather {source}. Store model: "
        "GPT-6.1 Sol's `seasonal_heat_store.py` (sol_r1), 25 MW, 500 EUR/MWh of capacity and "
        "0.1 MEUR/MW of power, 0.1 %/day loss. 1D and 2D plants: 3.1 km, boiler, CHP, screw "
        "chiller with dry cooler.",
        "",
        "**The store model is energy only.** It holds MWh with a daily loss and has no "
        "temperatures; charged heat comes back at the 100 degC supply. A real pit store holds "
        "80-95 degC water and needs a top-up, so the store results are optimistic.",
        "",
    ]
    for basis, (text, _) in BASES.items():
        sub = df[df["basis"] == basis]
        lines += [
            f"## Basis {basis}: {text}",
            "",
            "| " + " | ".join(cols) + " |",
            "|" + "---|" * len(cols),
        ]
        lines += ["| " + " | ".join(str(r[c]) for c in cols) + " |" for _, r in sub.iterrows()]
        ok = sub[sub["meets_all_hard_rules"]].sort_values("lcoe_eur_per_mwh")
        best = ok.iloc[0]
        lines += [
            "",
            f"Cheapest that meets every rule: **{best['case']}**, "
            f"{best['lcoe_eur_per_mwh']} EUR/MWh, {best['co2_t_per_year']} t CO2/yr.",
            "",
        ]
        for n in (1, 2):
            g = ok[(ok["n_doublets"] == n) & ~ok["case"].str.startswith("final")]
            if len(g):
                b, none = g.iloc[0], g[g["storage_gwh"] == 0]
                ref = f" (no store: {none.iloc[0]['lcoe_eur_per_mwh']})" if len(none) else ""
                lines.append(
                    f"- {n} doublet{'s' if n > 1 else ''}: best store size "
                    f"{b['storage_gwh']:g} GWh, {b['lcoe_eur_per_mwh']} EUR/MWh{ref}."
                )
        lines.append("")
    return "\n".join(lines) + "\n"


def main():
    """Run every case and write the results."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--knmi", required=True, help="KNMI etmgeg daily file")
    parser.add_argument("--year", type=int, default=2025, help="year to take from the file")
    args = parser.parse_args()
    register_sol_model()
    climate = with_climate(load_demand(INPUTS), read_knmi_daily(args.knmi, args.year), "max")
    rows = []
    for label, req, basis in cases():
        rows.append(run_case(label, req, basis, climate))
        r = rows[-1]
        print(
            f"{basis} {label:40s} {r['lcoe_eur_per_mwh']:7.2f} EUR/MWh "
            f"{r['co2_t_per_year']:6d} t"
        )
    OUT.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "results.csv", index=False)
    source = f"{Path(args.knmi).name} ({args.year})"
    (OUT / "summary.md").write_text(summarise(df, source), encoding="utf-8")


if __name__ == "__main__":
    main()
