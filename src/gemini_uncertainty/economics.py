"""Sourced techno-economic model used by the uncertainty study.

It reuses the ``gemini_design`` CAPEX breakdown for surface equipment but
replaces the linear well cost with TNO ThermoGIS's quadratic well-cost
curve, and applies the sampled cost factors, discount rate and energy
prices. Prices are real (2026 EUR), so the discount rate is the real WACC.
"""

from gemini_design.economics import capital_cost_eur, capital_recovery_factor
from gemini_uncertainty.parameters import (
    EXPORT_SHARE_OF_WHOLESALE,
    GAS_SUPPLY_ADDER_EUR_PER_MWH,
)

# TNO pyThermoGIS default economic properties (TG base case)
THERMOGIS_WELL_COST = {"scale": 1.3, "base_eur": 0.25e6, "per_m_eur": 700.0, "per_m2_eur": 0.2}


def thermogis_well_cost_eur(along_hole_depth_m, coeffs=THERMOGIS_WELL_COST):
    """Return the cost (EUR) of one well from the ThermoGIS curve.

    ``scale x (base + per_m x L + per_m2 x L^2)``, with ``L`` the
    along-hole depth. Our wells are vertical, so ``L`` is the reservoir
    midpoint depth (a deviated Dutch well would be 10-20% longer).
    """
    length = along_hole_depth_m
    return coeffs["scale"] * (
        coeffs["base_eur"] + coeffs["per_m_eur"] * length + coeffs["per_m2_eur"] * length**2
    )


def energy_prices(values, assumptions):
    """Return an assumptions dict with prices derived from sampled values.

    ``values`` may hold the ``cost`` parameters of
    ``gemini_uncertainty.parameters``; anything missing keeps the value
    already in ``assumptions``.
    """
    a = dict(assumptions)
    if "electricity_wholesale_eur_per_mwh" in values or "electricity_adder_eur_per_mwh" in values:
        wholesale = values.get("electricity_wholesale_eur_per_mwh", 85.0)
        adder = values.get("electricity_adder_eur_per_mwh", 30.0)
        a["electricity_price_eur_per_mwh"] = wholesale + adder
        a["electricity_export_price_eur_per_mwh"] = EXPORT_SHARE_OF_WHOLESALE * wholesale
    if "ttf_gas_eur_per_mwh" in values:
        a["gas_price_eur_per_mwh"] = values["ttf_gas_eur_per_mwh"] + GAS_SUPPLY_ADDER_EUR_PER_MWH
    return a


def capital_cost(design, assumptions, well_cost_factor=1.0, surface_cost_factor=1.0):
    """Return a CAPEX breakdown (EUR) with ThermoGIS wells and scaled surface equipment."""
    breakdown = dict(capital_cost_eur(design, assumptions))
    breakdown.pop("total")
    surface = {k: v * surface_cost_factor for k, v in breakdown.items() if k != "wells"}
    wells = design.n_doublets * 2 * thermogis_well_cost_eur(design.depth_m) * well_cost_factor
    out = {"wells": wells, **surface}
    out["total"] = sum(out.values())
    return out


def levelised_cost(design, summary, assumptions, values=None):
    """Return CAPEX, annual cost terms and levelised cost for one simulated year.

    ``summary`` is a ``gemini_design.annual.run_year`` summary simulated with
    ``assumptions`` (so its energy cost already uses the sampled prices,
    including CO2). The levelised cost divides by delivered heat + cooling,
    which is the same convention as ``gemini_design``. A per-MWh-of-heat
    figure that books cooling at the same price is therefore identical.
    """
    values = values or {}
    capex = capital_cost(
        design,
        assumptions,
        values.get("well_cost_factor", 1.0),
        values.get("surface_cost_factor", 1.0),
    )
    rate = values.get("discount_rate", assumptions["discount_rate"])
    crf = capital_recovery_factor(rate, assumptions["lifetime_years"])
    annual_capital = capex["total"] * crf
    fixed_om = capex["total"] * assumptions["fixed_om_fraction"]
    energy_cost = summary["economics"]["annual_energy_cost_eur"]
    e = summary["energy_mwh"]
    delivered = e["heating_delivered"] + e["cooling_delivered"]
    total = annual_capital + fixed_om + energy_cost
    co2_cost = summary["kpi"]["co2_t_per_year"] * assumptions["co2_price_eur_per_t"]
    return {
        "capex_eur": capex,
        "annual_capital_eur": annual_capital,
        "annual_fixed_om_eur": fixed_om,
        "annual_energy_cost_eur": energy_cost,
        "annual_co2_cost_eur": co2_cost,
        "annual_total_cost_eur": total,
        "lcoe_eur_per_mwh": total / delivered if delivered > 0 else float("inf"),
    }
