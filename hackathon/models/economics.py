"""Levelised cost of the energy delivered (heat plus cooling).

Costs follow the TNO ThermoGIS NL defaults (pythermogis 'Cost Model' and
'UTC Properties ThermoGIS NL'), taken as they are, no inflation correction.
For equipment ThermoGIS doesn't cover we use the sources listed under
economics.other_sources in config/fixed_inputs.yaml.

LCOH = (CRF * CAPEX + OPEX + electricity + gas - CHP electricity value)
       / (heat delivered + cooling delivered)          [EUR/MWh]

This is for comparing designs with each other, not a cost forecast.
Simplifications: vertical wells (ThermoGIS s_curve = 1), no tax, no
inflation, CHP electricity valued at the purchase price.
"""

HOURS = 24.0


def crf(rate, years):
    """Capital recovery factor."""
    return rate * (1 + rate) ** years / ((1 + rate) ** years - 1)


def well_pair_capex_eur(tg, depth_m):
    """ThermoGIS: CAPEX_wells = 2 * wscale * (wc0 + wc1*MD + wc2*MD^2), MD = TVD (vertical)."""
    md = depth_m
    return 2 * tg["wscale"] * (tg["wc0_eur"] + tg["wc1_eur_per_m"] * md + tg["wc2_eur_per_m2"] * md ** 2)


def design_economics(cfg, design, daily, doublet_power_mw):
    """CAPEX, OPEX, energy cost and LCOH of one evaluated design."""
    econ = cfg.economics
    tg, oth = econ["thermogis"], econ["other_sources"]
    p = design.surface
    n = design.n_doublets
    gas_price = oth["natural_gas_eur_per_mwh"]
    e_price = tg["electricity_price_eur_per_kwh"] * 1000  # EUR/MWh

    chp_mw_el = float(daily.chp_elec.max()) if len(daily) else 0.0
    capex = {
        "wells": n * well_pair_capex_eur(tg, design.depth_m),
        "geothermal_plant": n * (tg["capex_base_eur"]
                                 + tg["capex_other_var_eur_per_kw"] * doublet_power_mw * 1e3),
        "heat_pump": tg["capex_hp_eur_per_kw"] * p.hp_capacity_mw * 1e3,
    }
    capex = {k: v * (1 + tg["capex_contingency"]) for k, v in capex.items()}  # ThermoGIS items
    capex.update({
        "absorption_chiller": oth["absorption_chiller_eur_per_kw"] * p.sorption_capacity_mw * 1e3
        if p.chiller_type.startswith("absorption") else 0.0,
        "electric_chiller": oth["electric_chiller_eur_per_kw"] * p.elec_chiller_capacity_mw * 1e3,
        "chp": oth["chp_eur_per_kw_el"] * chp_mw_el * 1e3,
        "boiler": oth["boiler_eur_per_kw"] * p.boiler_capacity_mw * 1e3,
    })

    mwh = lambda col: float(daily[col].sum() * HOURS)
    geo_heat_mwh = mwh("heat_direct") + mwh("heat_hp")
    opex = {
        "geothermal_fixed": tg["opex_power_eur_per_kw_yr"] * n * doublet_power_mw * 1e3,
        "geothermal_variable": tg["opex_heat_var_eur_per_kwh"] * geo_heat_mwh * 1e3,
        "heat_pump": tg["opex_hp_eur_per_kw_yr"] * p.hp_capacity_mw * 1e3,
        "absorption_chiller": oth["absorption_om_eur_per_mwh"] * mwh("cool_sorption"),
        "electric_chiller": oth["electric_chiller_om_eur_per_kw_yr"] * p.elec_chiller_capacity_mw * 1e3,
        "chp": oth["chp_om_eur_per_mwh_el"] * mwh("chp_elec"),
        "boiler": oth["boiler_om_eur_per_kw_yr"] * p.boiler_capacity_mw * 1e3,
    }
    elec_mwh = mwh("pump_elec") + mwh("hp_elec") + mwh("chiller_elec")
    energy = {
        "electricity": elec_mwh * e_price,
        "natural_gas": mwh("ng_used_mw") * gas_price,
        "chp_electricity_value": -mwh("chp_elec") * e_price,
    }
    rate = econ["derived"]["discount_rate"]
    years = tg["econ_lifetime_years"]
    capex_total = sum(capex.values())
    annual = crf(rate, years) * capex_total + sum(opex.values()) + sum(energy.values())
    delivered = mwh("heat_demand_mw") - mwh("heat_unmet") + mwh("cool_demand_mw") - mwh("cool_unmet")
    return {
        "lcoh_eur_per_mwh": annual / delivered if delivered > 0 else float("inf"),
        "capex_total_meur": capex_total / 1e6,
        "annual_cost_meur": annual / 1e6,
        "capex_meur": {k: round(v / 1e6, 3) for k, v in capex.items()},
        "opex_meur_yr": {k: round(v / 1e6, 3) for k, v in opex.items()},
        "energy_meur_yr": {k: round(v / 1e6, 3) for k, v in energy.items()},
        "delivered_gwh": delivered / 1000,
    }
