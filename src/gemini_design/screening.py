"""Design-space screening: enumerate candidate plants, run each for a year, rank them."""

import itertools
from concurrent.futures import ProcessPoolExecutor

import pandas as pd

from gemini_design.annual import run_year
from gemini_design.challenge import ASSUMPTIONS, CHALLENGE, associated_gas_properties
from gemini_design.plant import Design
from gemini_model.chp.chp import CHP

DEFAULT_DEPTHS_M = (2500.0, 2800.0, 3100.0, 3400.0)


def chp_size_mw_el(n_doublets, challenge=CHALLENGE, assumptions=ASSUMPTIONS):
    """Return the CHP rating (MW_el) that burns all associated gas at 300 m3/h per doublet."""
    gas = associated_gas_properties(challenge)
    gas_kg_s = (
        n_doublets
        * challenge["flow_max_m3h"]
        / 3600.0
        * challenge["gas_liquid_ratio"]
        * gas["density"]
    )
    return (
        gas_kg_s * gas["lhv"] * assumptions["chp_efficiency"] * CHP.ELECTRICAL_POWER_FRACTION / 1e6
    )


def candidate_designs(
    depths_m=DEFAULT_DEPTHS_M,
    peak_heating_mw=30.0,
    peak_cooling_mw=10.0,
    include_chp=True,
    chiller_margin=1.0,
):
    """Return the default candidate grid with rule-based equipment sizing.

    Sizing rules (stated so an agent can explain them): the gas boiler is
    sized for the full heating peak, so heat supply survives any doublet
    outage; a heat pump, when chosen, is sized at a third of the heating
    peak (the 87 -> 100 degC top-up at the 2.5 km reference depth);
    cooling capacity equals the cooling peak, and absorption chillers get
    a half-size electric backup for days with too little brine. With
    ``include_chp`` every combination is also tried with a CHP sized to
    burn all associated gas at full flow (about 0.54 MW_el per doublet).
    ``chiller_margin`` scales the chiller above the cooling peak; the
    uncertainty study found about 1.2 is needed once cooling demand is
    uncertain (an exact-peak chiller misses cooling in about half the samples).
    """
    designs = []
    chp_options = (False, True) if include_chp else (False,)
    for n, depth, upgrade, cooling, chp in itertools.product(
        (1, 2, 3), depths_m, ("boiler", "heat_pump"), ("absorption", "electric"), chp_options
    ):
        designs.append(
            Design(
                n_doublets=n,
                depth_m=depth,
                upgrade=upgrade,
                cooling=cooling,
                heat_pump_capacity_mw=peak_heating_mw / 3 if upgrade == "heat_pump" else 0.0,
                boiler_capacity_mw=peak_heating_mw,
                chiller_capacity_mw=peak_cooling_mw * chiller_margin,
                electric_backup_mw=peak_cooling_mw / 2 if cooling == "absorption" else 0.0,
                chp_capacity_mw_el=chp_size_mw_el(n) if chp else 0.0,
            )
        )
    return designs


def _run(args):
    design, demand = args
    _, summary = run_year(design, demand)
    return summary


def flatten_summary(summary):
    """Return a one-row dict of the headline numbers of a run summary."""
    d, e, k, econ = summary["design"], summary["energy_mwh"], summary["kpi"], summary["economics"]
    return {
        "name": d["name"],
        "n_doublets": d["n_doublets"],
        "depth_m": d["depth_m"],
        "upgrade": d["upgrade"],
        "cooling": d["cooling"],
        "chp_mw_el": d.get("chp_capacity_mw_el", 0.0),
        "reservoir_temperature_c": summary["reservoir"]["temperature_c"],
        "all_hard_constraints_met": summary["all_hard_constraints_met"],
        "unmet_heating_mwh": e["unmet_heating"],
        "unmet_cooling_mwh": e["unmet_cooling"],
        "geothermal_share_of_heat": k["geothermal_share_of_heat"],
        "purchased_gas_mwh": e["purchased_gas_fuel"],
        "electricity_mwh": e["electricity"],
        "grid_import_mwh": e["grid_import"],
        "chp_electricity_mwh": e["chp_electricity"],
        "associated_gas_flared_mwh": e["associated_gas_flared"],
        "co2_t_per_year": k["co2_t_per_year"],
        "capex_meur": econ["capex_eur"]["total"] / 1e6,
        "annual_energy_cost_meur": econ["annual_energy_cost_eur"] / 1e6,
        "lcoe_eur_per_mwh": econ["lcoe_eur_per_mwh"],
        "max_flow_per_doublet_m3h": k["max_flow_per_doublet_m3h"],
        "max_brine_cooling_k": k["max_brine_cooling_k"],
    }


def screen(designs, demand, workers=None):
    """Run every design for a year (in parallel) and return a ranked DataFrame and summaries.

    Ranking: designs meeting every hard constraint and all demand first,
    then by levelised cost.
    """
    with ProcessPoolExecutor(max_workers=workers) as pool:
        summaries = list(pool.map(_run, [(d, demand) for d in designs]))
    table = pd.DataFrame([flatten_summary(s) for s in summaries])
    table = table.sort_values(
        ["all_hard_constraints_met", "lcoe_eur_per_mwh"], ascending=[False, True]
    ).reset_index(drop=True)
    return table, summaries
