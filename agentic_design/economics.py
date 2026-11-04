"""Techno-economics: investment, yearly cost and levelised cost of the delivered heat and cooling.

The challenge gives no costs, so every number here is an assumption with a source. Wells and the
geothermal surface plant use TNO's own ThermoGIS defaults (pythermogis documentation), so they match the
organisers' tool. Chillers and boilers use typical large-scale values (stated as assumptions and varied in
the sensitivity runs). Energy prices are Eurostat non-household averages (EU, second half of 2025); the CO2
price is the EU ETS level of mid-2026.

Levelised cost (EUR per MWh delivered heat + cooling):

    LCOE = (CAPEX x CRF + fixed O&M + electricity + natural gas + CO2 cost) / (heating + cooling delivered)
    CRF  = r / (1 - (1 + r)^-n)   (capital recovery factor)

Backup boiler sizing (security of supply, N-1): with one doublet unexpectedly out on the coldest day,
the boilers must cover what the remaining doublets cannot. A single doublet therefore needs boilers for
the whole peak; three doublets need much less.
"""

from dataclasses import asdict, dataclass, field

import numpy as np

from agentic_design.config import CHALLENGE, Assumptions

THERMOGIS = "TNO ThermoGIS defaults (pythermogis docs: theory/utcprops, theory/economicmodel/cost_model)"


@dataclass
class CostAssumptions:
    # wells and geothermal plant: ThermoGIS defaults
    well_cost_scaling: float = 1.3          # wcscale [-]
    well_cost_base_eur: float = 0.25e6      # wc0 [EUR per well]
    well_cost_per_m: float = 700.0          # wc1 [EUR/m]
    well_cost_per_m2: float = 0.2           # wc2 [EUR/m2]
    plant_base_meur_per_doublet: float = 3.0  # CAPEXbase [MEUR], applied per doublet
    plant_eur_per_kw: float = 300.0         # CAPEXother,var [EUR/kW geothermal capacity]
    plant_opex_eur_per_kw_yr: float = 100.0  # OPEXpower [EUR/kW/yr]
    plant_opex_eur_per_mwh: float = 1.9     # OPEXheat,var 0.19 ct/kWh
    heat_pump_eur_per_kw: float = 200.0     # CAPEXhp,var (ThermoGIS; low for industrial units -> sensitivity)
    heat_pump_opex_eur_per_kw_yr: float = 10.0
    contingency: float = 0.15               # CAPEXcont
    lifetime_yr: int = 30                   # ECONlifetime
    discount_rate: float = 0.059            # WACC from ThermoGIS: 80 % debt at 5 % (after 25 % tax) + 20 % equity at 14.5 %
    # other equipment: typical MW-scale values (assumptions, varied in sensitivity)
    electric_chiller_eur_per_kw: float = 250.0   # water-cooled, incl. cooling tower
    absorption_chiller_eur_per_kw: float = 500.0  # single-effect LiBr, incl. cooling tower
    boiler_eur_per_kw: float = 100.0             # gas boilers (dual fuel: associated gas / natural gas)
    equipment_opex_share_yr: float = 0.02        # fixed O&M of chillers and boilers, share of their CAPEX
    gas_reinjection_meur: float = 1.0            # compressor package (shared)
    gas_reinjection_meur_per_doublet: float = 0.5  # gas injection string in each injector
    gas_reinjection_opex_share_yr: float = 0.04
    # energy and carbon prices
    electricity_eur_per_mwh: float = 183.7   # Eurostat, EU non-household, H2 2025 (18.37 EUR/100 kWh)
    natural_gas_eur_per_mwh: float = 60.5    # Eurostat, EU non-household, H2 2025 (6.05 EUR/100 kWh)
    co2_eur_per_t: float = 82.0              # EU ETS (EUA Dec-26) ~82 EUR/t, July 2026 (what the plant would pay)
    # value of CO2 for choosing the design (societal appraisal): EIB shadow cost of carbon, 250 EUR/t in 2030 rising
    # to 800 EUR/t in 2050; discounted (5.9 %) average over the 2027-2056 plant life ~450 EUR/t
    co2_shadow_eur_per_t: float = 450.0
    sources: dict = field(default_factory=lambda: {
        "wells, geothermal plant, heat pump, contingency, lifetime, financing": THERMOGIS,
        "electricity and natural gas prices": "Eurostat news release, prices for non-household consumers, H2 2025",
        "CO2 price": "EU ETS EUA Dec-26 contract, July 2026 (GMK Center)",
        "CO2 value for design choice": "EIB shadow cost of carbon (250 EUR/t 2030, 800 EUR/t 2050; E3G summary), "
                                       "discounted lifetime average ~450 EUR/t",
        "electric/absorption chillers, boilers, their O&M": "team assumption (typical MW-scale values), sensitivity +/-50 %",
        "gas reinjection (compressor, injection string)": "team assumption, sensitivity x2",
        "grid CO2 factor 0.30 kg/kWh": "organisers' reference value (GEMINI electricity_emission_factor), Discord 3 Nov",
    })

    def crf(self):
        r, n = self.discount_rate, self.lifetime_yr
        return 1.0 / n if abs(r) < 1e-12 else r / (1 - (1 + r) ** -n)


def well_cost_eur(depth_m, c: CostAssumptions = None):
    c = c or CostAssumptions()
    return c.well_cost_scaling * (c.well_cost_base_eur + c.well_cost_per_m * depth_m + c.well_cost_per_m2 * depth_m ** 2)


def n_minus_1_boiler_mw(design, daily, a: Assumptions):
    """Boiler capacity so that the coldest day is still covered with one doublet out (security of supply)."""
    peak = int(daily["heating_mw"].idxmax())
    r = daily.loc[peak]
    t_sup, t_ret = CHALLENGE["heating_supply_temperature_c"], a.heating_return_temperature_c
    rho_cp = CHALLENGE["brine_density_kg_m3"] * a.brine_specific_heat_j_kgk / 3600 / 1e6  # MW/K per m3/h
    t_b = r["t_wellhead_c"] - a.surface_temperature_loss_c
    dt = max(0.0, min(CHALLENGE["max_brine_cooling_c"] - a.surface_temperature_loss_c, t_b - (t_ret + a.hx_min_approach_c)))
    per_doublet = CHALLENGE["max_flow_m3h_per_doublet"] * rho_cp * dt
    c_net = r["heating_mw"] / (t_sup - t_ret)
    net_cap = c_net * max(0.0, min(t_sup, t_b - a.hx_min_approach_c) - t_ret)  # network cannot pass brine temperature
    geo_n1 = min((design.n_doublets - 1) * per_doublet, net_cap) + min(design.heat_pump_mw, r["heating_mw"])
    planned = float((daily["heat_assoc_gas_boiler_mw"] + daily["heat_ng_boiler_mw"]).max())
    return max(planned, r["heating_mw"] - geo_n1, 0.0)


def economics(design, daily, kpis, a: Assumptions = None, c: CostAssumptions = None):
    a, c = a or Assumptions(), c or CostAssumptions()
    geo_mw = float((daily["heat_geothermal_mw"] + daily["absorption_drive_mw"] + daily["heat_pump_evaporator_mw"]).max())
    boiler_mw = n_minus_1_boiler_mw(design, daily, a)
    capex = {
        "wells": 2 * design.n_doublets * well_cost_eur(design.well.depth_m, c),
        "geothermal_plant": design.n_doublets * c.plant_base_meur_per_doublet * 1e6 + c.plant_eur_per_kw * geo_mw * 1e3,
        "heat_pump": c.heat_pump_eur_per_kw * design.heat_pump_mw * 1e3,
        "absorption_chiller": c.absorption_chiller_eur_per_kw * design.absorption_mw * 1e3,
        "electric_chiller": c.electric_chiller_eur_per_kw * design.electric_chiller_mw * 1e3,
        "boilers": c.boiler_eur_per_kw * boiler_mw * 1e3,
        "gas_reinjection": ((c.gas_reinjection_meur + c.gas_reinjection_meur_per_doublet * design.n_doublets) * 1e6
                            if kpis.get("assoc_gas_handling", "burn_all") != "burn_all" else 0.0),
    }
    capex["contingency"] = c.contingency * sum(capex.values())
    capex_total = sum(capex.values())
    geo_gwh = float((daily["heat_geothermal_mw"] + daily["absorption_drive_mw"] + daily["heat_pump_evaporator_mw"]).sum() * 24 / 1e3)
    ng_fuel_gwh = float(daily["ng_fuel_mw"].sum() * 24 / 1e3)
    opex = {
        "geothermal_fixed": c.plant_opex_eur_per_kw_yr * geo_mw * 1e3 + c.plant_opex_eur_per_mwh * geo_gwh * 1e3,
        "heat_pump_fixed": c.heat_pump_opex_eur_per_kw_yr * design.heat_pump_mw * 1e3,
        "chillers_boilers_fixed": c.equipment_opex_share_yr * (capex["absorption_chiller"] + capex["electric_chiller"]
                                                                + capex["boilers"]),
        "gas_reinjection_fixed": c.gas_reinjection_opex_share_yr * capex["gas_reinjection"],
        "electricity": c.electricity_eur_per_mwh * kpis["electricity_gwh"] * 1e3,
        "natural_gas": c.natural_gas_eur_per_mwh * ng_fuel_gwh * 1e3,
    }
    co2_cost = c.co2_eur_per_t * kpis["co2_t"]
    annual_capital = capex_total * c.crf()
    delivered_mwh = (kpis["heating_demand_gwh"] - kpis["heating_unmet_gwh"]
                     + kpis["cooling_demand_gwh"] - kpis["cooling_unmet_gwh"]) * 1e3
    annual = annual_capital + sum(opex.values())
    return {
        "capex_meur": capex_total / 1e6,
        "capex_breakdown_meur": {k: v / 1e6 for k, v in capex.items()},
        "boiler_capacity_mw": boiler_mw,
        "geothermal_capacity_mw": geo_mw,
        "annual_cost_meur": annual / 1e6,
        "annual_cost_with_co2_meur": (annual + co2_cost) / 1e6,
        "opex_breakdown_meur": {k: v / 1e6 for k, v in opex.items()},
        "annual_capital_meur": annual_capital / 1e6,
        "co2_cost_meur": co2_cost / 1e6,
        "lcoe_eur_per_mwh": annual / delivered_mwh,
        "lcoe_with_co2_eur_per_mwh": (annual + co2_cost) / delivered_mwh,
        "lcoe_with_shadow_co2_eur_per_mwh": (annual + c.co2_shadow_eur_per_t * kpis["co2_t"]) / delivered_mwh,
        "cost_assumptions": {k: v for k, v in asdict(c).items() if k != "sources"},
    }


__all__ = ["CostAssumptions", "economics", "well_cost_eur", "n_minus_1_boiler_mw"]
