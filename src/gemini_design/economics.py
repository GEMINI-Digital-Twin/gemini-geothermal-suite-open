"""Capital cost, annualised cost and levelised cost of energy for a design."""

from gemini_design.challenge import ASSUMPTIONS


def capital_cost_eur(design, assumptions=ASSUMPTIONS):
    """Return a CAPEX breakdown (EUR) for a design. All unit costs are stated assumptions."""
    a = assumptions
    well = a["well_cost_fixed_eur"] + a["well_cost_per_m_eur"] * design.depth_m
    chiller_unit = (
        a["absorption_chiller_cost_eur_per_mw"]
        if design.cooling == "absorption"
        else a["electric_chiller_cost_eur_per_mw"]
    )
    breakdown = {
        "wells": design.n_doublets * 2 * well,
        "doublet_surface": design.n_doublets * a["surface_cost_per_doublet_eur"],
        "heat_pump": design.heat_pump_capacity_mw * a["heat_pump_cost_eur_per_mw"],
        "boiler": design.boiler_capacity_mw * a["boiler_cost_eur_per_mw"],
        "chiller": design.chiller_capacity_mw * chiller_unit,
        "electric_backup_chiller": design.electric_backup_mw
        * a["electric_chiller_cost_eur_per_mw"],
    }
    breakdown["total"] = sum(breakdown.values())
    return breakdown


def capital_recovery_factor(rate, years):
    """Return the capital recovery factor for a discount rate and lifetime."""
    return rate * (1 + rate) ** years / ((1 + rate) ** years - 1)


def levelised_cost(design, annual_energy_cost_eur, delivered_mwh, assumptions=ASSUMPTIONS):
    """Return annualised cost terms and the levelised cost (EUR/MWh) of delivered heat + cooling."""
    capex = capital_cost_eur(design, assumptions)
    crf = capital_recovery_factor(assumptions["discount_rate"], assumptions["lifetime_years"])
    annual_capital = capex["total"] * crf
    fixed_om = capex["total"] * assumptions["fixed_om_fraction"]
    total = annual_capital + fixed_om + annual_energy_cost_eur
    return {
        "capex_eur": capex,
        "annual_capital_eur": annual_capital,
        "annual_fixed_om_eur": fixed_om,
        "annual_energy_cost_eur": annual_energy_cost_eur,
        "annual_total_cost_eur": total,
        "lcoe_eur_per_mwh": total / delivered_mwh if delivered_mwh > 0 else float("inf"),
    }
