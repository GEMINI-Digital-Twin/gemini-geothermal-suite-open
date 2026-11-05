"""Techno-economics: CAPEX, OPEX, levelised cost and CO2 intensity of a design.

All prices and unit costs come from ``data/economics_assumptions.yaml`` and are
reported as assumptions (the brief gives none).
"""

from __future__ import annotations

from gemini_agent.physics.design import DesignSpec, load_economics
from gemini_agent.physics.plant import AnnualResult

MD_TO_TVD = 1.15  # deviated doublet wells drilled from one pad (assumption)


def crf(rate: float, years: int) -> float:
    """Capital recovery factor."""
    return rate * (1 + rate) ** years / ((1 + rate) ** years - 1)


def economics(res: AnnualResult, econ: dict | None = None) -> dict:
    """CAPEX breakdown, annual OPEX, levelised cost of energy (heat + cooling)."""
    e = (econ or load_economics())["values"]
    s: DesignSpec = res.spec
    md = s.well_depth_m * MD_TO_TVD
    n_wells = 2 * s.n_doublets
    peak_hex = max(d.q_hex for d in res.days) if res.days else 0.0
    capex = {
        "wells": n_wells * (e["well_fixed_eur"] + e["well_per_m_eur"] * md),
        "surface_doublets": s.n_doublets
        * (
            e["surface_per_doublet_eur"]
            + (
                e["pressurised_loop_extra_per_doublet_eur"]
                if s.gas_handling.startswith("keep")
                else 0
            )
        ),
        "heat_exchangers": e["heat_exchanger_eur_per_mw"] * peak_hex,
        "heat_pump": e["heat_pump_eur_per_mw_th"] * s.heat_pump_mw,
        "absorption_chiller": e["absorption_chiller_eur_per_mw_c"] * s.absorption_chiller_mw,
        "electric_chiller": e["electric_chiller_eur_per_mw_c"] * s.electric_chiller_mw,
        "backup_boiler": (
            e["gas_boiler_eur_per_mw"]
            if s.backup_fuel == "gas"
            else e["electric_boiler_eur_per_mw"]
        )
        * s.backup_boiler_mw,
    }
    capex_total = sum(capex.values())
    k = res.kpis()
    el_cost = k["electricity_gwh"] * 1000 * e["electricity_eur_per_mwh"]
    gas_cost = k["grid_gas_gwh"] * 1000 * e["natural_gas_eur_per_mwh"]
    co2_cost = k["co2_t"] * e["co2_eur_per_t"]
    fixed_om = (
        capex["wells"] * e["wells_fixed_fraction_per_year"]
        + (capex_total - capex["wells"]) * e["surface_fixed_fraction_per_year"]
    )
    opex = {
        "electricity": el_cost,
        "grid_gas": gas_cost,
        "co2": co2_cost,
        "fixed_om": fixed_om,
    }
    opex_total = sum(opex.values())
    energy_mwh = (k["heat_demand_gwh"] + k["cool_demand_gwh"]) * 1000
    annuity = crf(e["discount_rate"], int(e["lifetime_years"])) * capex_total
    lcoe = (annuity + opex_total) / energy_mwh if energy_mwh else float("nan")
    return {
        "capex_eur": {k2: round(v, 0) for k2, v in capex.items()},
        "capex_total_meur": round(capex_total / 1e6, 2),
        "opex_eur_per_year": {k2: round(v, 0) for k2, v in opex.items()},
        "opex_total_meur_per_year": round(opex_total / 1e6, 3),
        "annualised_capex_meur": round(annuity / 1e6, 3),
        "lcoe_eur_per_mwh": round(lcoe, 2),
        "co2_intensity_kg_per_mwh": (
            round(k["co2_t"] * 1000 / energy_mwh, 2) if energy_mwh else None
        ),
        "assumptions": {
            "discount_rate": e["discount_rate"],
            "lifetime_years": e["lifetime_years"],
            "electricity_eur_per_mwh": e["electricity_eur_per_mwh"],
            "natural_gas_eur_per_mwh": e["natural_gas_eur_per_mwh"],
            "co2_eur_per_t": e["co2_eur_per_t"],
            "well_md_to_tvd": MD_TO_TVD,
        },
    }
