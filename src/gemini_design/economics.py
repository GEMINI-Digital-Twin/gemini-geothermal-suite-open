"""Capital cost, annualised cost and levelised cost of energy for a design."""

from gemini_design import ates, pit_storage, well_integrity
from gemini_design.challenge import ASSUMPTIONS, CHILLER_TYPES


def _electric_chiller_cost_eur_per_mw(design, assumptions):
    kind = getattr(design, "chiller_type", "legacy")
    if kind == "legacy":
        return assumptions["electric_chiller_cost_eur_per_mw"]
    return CHILLER_TYPES[kind]["cost_eur_per_mw"]


def capital_cost_eur(
    design,
    assumptions=ASSUMPTIONS,
    peak_heat_rejected_mw=0.0,
    well_integrity_capex=None,
    network_capex_eur=0.0,
    esp_capex_eur=0.0,
):
    """Return a CAPEX breakdown (EUR) for a design. All unit costs are stated assumptions.

    ``peak_heat_rejected_mw`` sizes a wet cooling tower (centrifugal_tower
    chillers). ``well_integrity_capex`` is the corrosion-mitigation CAPEX (EUR) of
    all doublets, from :func:`gemini_design.well_integrity.mitigation_cost`.
    ``network_capex_eur`` is the customer-substation cost of the design's return
    temperatures relative to the reference network (:mod:`gemini_design.network`;
    negative when they need less plate area). ``esp_capex_eur`` is the cost of
    sized downhole pumps less the ESP share already in the surface cost
    (:func:`gemini_design.esp.capex_vs_reference_eur`; 0 for the ideal pump).
    """
    a = assumptions
    depths = design.well_depths_m() if hasattr(design, "well_depths_m") else None
    depths = depths or [design.depth_m] * design.n_doublets
    electric_unit = _electric_chiller_cost_eur_per_mw(design, a)
    chiller_unit = (
        a["absorption_chiller_cost_eur_per_mw"] if design.cooling == "absorption" else electric_unit
    )
    ates_pairs = getattr(design, "ates_doublets", 0)
    ates_mw = ates.nominal_capacity_mw(design, a) if ates_pairs > 0 else 0.0
    breakdown = {
        "wells": sum(2 * (a["well_cost_fixed_eur"] + a["well_cost_per_m_eur"] * d) for d in depths),
        "doublet_surface": design.n_doublets * a["surface_cost_per_doublet_eur"],
        "heat_pump": design.heat_pump_capacity_mw * a["heat_pump_cost_eur_per_mw"],
        "boiler": design.boiler_capacity_mw
        * a["boiler_cost_eur_per_mw"]
        * max(1, getattr(design, "boiler_units", 1)) ** (1.0 - a["unit_cost_scale_exponent"]),
        "electric_boiler": getattr(design, "electric_boiler_mw", 0.0)
        * a["electric_boiler_cost_eur_per_mw"],
        "heat_recovery_heat_pump": getattr(design, "heat_recovery_hp_mw", 0.0)
        * a["heat_recovery_hp_cost_eur_per_mw"],
        "chp": getattr(design, "chp_capacity_mw_el", 0.0) * a["chp_cost_eur_per_mw_el"],
        "orc": getattr(design, "orc_capacity_mw_el", 0.0) * a.get("orc_cost_eur_per_mw_el", 0.0),
        "chiller": design.chiller_capacity_mw * chiller_unit,
        "electric_backup_chiller": design.electric_backup_mw * electric_unit,
        "cooling_tower": peak_heat_rejected_mw * a["cooling_tower_cost_eur_per_mw"],
        "ates": ates_pairs * a["ates_well_pair_cost_eur"]
        + ates_mw * (a["ates_hex_cost_eur_per_mw"] + a["ates_charge_cooler_cost_eur_per_mw"]),
        "well_integrity": well_integrity_capex or 0.0,
        "free_cooling": (
            design.chiller_capacity_mw * a.get("free_cooling_cost_eur_per_mw", 0.0)
            if getattr(design, "free_cooling", False)
            else 0.0
        ),
        "storage": getattr(design, "storage_mwh", 0.0) * a["storage_cost_eur_per_mwh"]
        + getattr(design, "storage_mw", 0.0) * a["storage_power_cost_eur_per_mw"],
        "pit_store": pit_storage.capital_cost_eur(design, a)["total"],
        "network_substations_vs_reference": network_capex_eur,
        "esp_vs_reference": esp_capex_eur,
    }
    breakdown["total"] = sum(breakdown.values())
    return breakdown


def capital_recovery_factor(rate, years):
    """Return the capital recovery factor for a discount rate and lifetime."""
    return rate * (1 + rate) ** years / ((1 + rate) ** years - 1)


def levelised_cost(
    design,
    annual_energy_cost_eur,
    delivered_mwh,
    assumptions=ASSUMPTIONS,
    peak_heat_rejected_mw=0.0,
    network_capex_eur=0.0,
    esp_capex_eur=0.0,
):
    """Return annualised cost terms and the levelised cost (EUR/MWh) of delivered heat + cooling.

    Corrosion mitigation of the wells (GEMINI's corrosion models, see
    :mod:`gemini_design.well_integrity`) is included unless
    ``assumptions["well_integrity_costs"]`` is set to False.
    """
    wi_capex, wi_opex = well_integrity.mitigation_cost(design, assumptions)
    capex = capital_cost_eur(
        design, assumptions, peak_heat_rejected_mw, wi_capex, network_capex_eur, esp_capex_eur
    )
    crf = capital_recovery_factor(assumptions["discount_rate"], assumptions["lifetime_years"])
    annual_capital = capex["total"] * crf
    fixed_om = capex["total"] * assumptions["fixed_om_fraction"] + wi_opex
    total = annual_capital + fixed_om + annual_energy_cost_eur
    return {
        "capex_eur": capex,
        "annual_capital_eur": annual_capital,
        "annual_fixed_om_eur": fixed_om,
        "annual_energy_cost_eur": annual_energy_cost_eur,
        "annual_total_cost_eur": total,
        "lcoe_eur_per_mwh": total / delivered_mwh if delivered_mwh > 0 else float("inf"),
    }
