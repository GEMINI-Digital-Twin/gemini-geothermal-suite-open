"""Fixed GeoHackathon inputs, hard constraints and documented assumptions.

``CHALLENGE`` holds only values given in the official requirements
(28 October 2026). ``ASSUMPTIONS`` holds everything the brief does not
give; each entry is something an agent must state (or ask the user
about) rather than silently invent.
"""

import math
from pathlib import Path

import pandas as pd

GRAVITY = 9.80665  # m/s2
CELSIUS_TO_KELVIN = 273.15

CHALLENGE = {
    # reservoir
    "reservoir_depth_m": 2500.0,  # midpoint TVD
    "reservoir_thickness_m": 100.0,
    "geothermal_gradient_c_per_km": 30.0,
    "surface_temperature_c": 12.0,
    "reservoir_pressure_bar": 250.0,  # at reservoir_depth_m
    "permeability_md": 200.0,
    # brine and gas
    "brine_density": 1030.0,  # kg/m3
    "brine_viscosity": 0.40e-3,  # Pa.s
    "gas_liquid_ratio": 0.8,  # Nm3 gas / m3 liquid
    "ch4_mol_fraction": 0.8,
    "co2_mol_fraction": 0.2,
    # design and operating constraints
    "doublets_min": 1,
    "doublets_max": 3,
    "flow_max_m3h": 300.0,  # per doublet
    "flow_min_m3h": 50.0,  # per doublet, while active
    "brine_cooling_max_k": 40.0,  # producer to injector
    "pump_efficiency": 0.70,
    "operating_days": 330,  # per doublet and year
    "heating_supply_c": 100.0,
    "cooling_supply_c": 20.0,
}

ASSUMPTIONS = {
    # district networks (not given in the brief)
    "heating_return_c": 40.0,
    "cooling_return_c": 26.0,
    "cooling_water_c": 30.0,  # heat-rejection circuit (dry cooler / tower)
    # fluids
    "brine_cp": 4180.0,  # J/(kg.K)
    "water_density": 1000.0,
    "water_cp": 4186.0,
    # wells
    "well_inner_diameter_m": 0.2159,  # 8.5 in production casing
    "wellbore_radius_m": 0.108,
    "drainage_radius_m": 1000.0,
    "skin": 0.0,
    "well_roughness_m": 4.5e-5,  # steel casing; GEMINI's 0.01 m default is a rough open hole
    "producer_wellhead_pressure_bar": 10.0,  # keeps gas in solution up to the separator
    "esp_intake_pressure_min_bar": 20.0,
    "surface_pressure_loss_bar": 2.0,  # separator + filters + HEX, wellhead to injector pump
    # surface equipment
    "hex_ua_per_doublet_w_per_k": 4.0e6,  # plate HEX sized for ~3 K approach at 300 m3/h
    "separator_temperature_drop_k": 0.5,
    "boiler_efficiency": 0.9,
    "heat_pump_eta_lorenz": 0.5,
    "absorption_eta_rev": 0.2,
    "absorption_cop_max": 0.8,
    "electric_chiller_eta_carnot": 0.40,
    "electric_chiller_cop_max": 7.0,
    "electric_chiller_evaporator_approach_k": 4.0,
    "electric_chiller_condenser_approach_k": 8.0,  # above cooling water, incl. its rise
    "electric_chiller_units": 3,  # staged modules
    "chp_efficiency": 0.85,  # fuel to heat + power (GEMINI CHP splits 1/3 power, 2/3 heat)
    "chiller_aux_power_fraction": 0.02,
    "absorption_hot_dt_max_k": 20.0,  # max brine cooling across the generator (low-temp design)
    # energy prices and emission factors (NL-type 2027 values)
    "electricity_price_eur_per_mwh": 120.0,
    "electricity_export_price_eur_per_mwh": 60.0,  # CHP surplus sold to the grid
    "gas_price_eur_per_mwh": 40.0,  # purchased natural gas, LHV basis
    "co2_price_eur_per_t": 80.0,
    "electricity_emission_kg_per_kwh": 0.30,  # same as GEMINI examples
    "natural_gas_emission_kg_per_gj": 56.6,  # same as GEMINI examples
    # costs
    "well_cost_fixed_eur": 1.5e6,
    "well_cost_per_m_eur": 1600.0,
    "surface_cost_per_doublet_eur": 3.0e6,  # ESP, separator, filters, HEX, injection pump
    "heat_pump_cost_eur_per_mw": 7.0e5,
    "boiler_cost_eur_per_mw": 1.0e5,
    "chp_cost_eur_per_mw_el": 1.0e6,  # gas engine on low-CV associated gas
    "absorption_chiller_cost_eur_per_mw": 4.0e5,
    "electric_chiller_cost_eur_per_mw": 2.5e5,
    "fixed_om_fraction": 0.02,  # of CAPEX per year
    "discount_rate": 0.06,
    "lifetime_years": 30,
}

# Molar masses (g/mol) and lower heating value of methane (MJ/kg)
_M_CH4, _M_CO2 = 16.04, 44.01
_LHV_CH4_MJ_PER_KG = 50.0
_NORMAL_MOLAR_VOLUME = 22.414e-3  # Nm3/mol at 0 degC, 1.01325 bar(a)


def associated_gas_properties(challenge=CHALLENGE):
    """Return density (kg/Nm3), LHV (J/kg of mixture) and CO2 mass fraction of produced gas."""
    x_ch4, x_co2 = challenge["ch4_mol_fraction"], challenge["co2_mol_fraction"]
    molar_mass = x_ch4 * _M_CH4 + x_co2 * _M_CO2  # g/mol
    density = molar_mass * 1e-3 / _NORMAL_MOLAR_VOLUME
    ch4_mass_fraction = x_ch4 * _M_CH4 / molar_mass
    return {
        "density": density,
        "lhv": ch4_mass_fraction * _LHV_CH4_MJ_PER_KG * 1e6,
        "co2_mass_fraction": 1.0 - ch4_mass_fraction,
        "ch4_mass_fraction": ch4_mass_fraction,
    }


def reservoir_at_depth(depth_m, challenge=CHALLENGE):
    """Return reservoir temperature (degC) and pressure (bar) at a midpoint depth.

    Temperature follows the geothermal gradient. Pressure is the given
    250 bar at the reference depth, shifted hydrostatically with the brine
    density for other depths (as the brief allows).
    """
    temperature = (
        challenge["surface_temperature_c"]
        + challenge["geothermal_gradient_c_per_km"] * depth_m / 1000.0
    )
    dz = depth_m - challenge["reservoir_depth_m"]
    pressure = challenge["reservoir_pressure_bar"] + challenge["brine_density"] * GRAVITY * dz / 1e5
    return temperature, pressure


def productivity_index_m3h_per_bar(challenge=CHALLENGE, assumptions=ASSUMPTIONS):
    """Steady-state radial (Darcy) productivity index of one well, in m3/h per bar.

    ``PI = 2 pi k h / (mu (ln(re/rw) + S))``, with k in m2.
    """
    k = challenge["permeability_md"] * 9.869233e-16
    h = challenge["reservoir_thickness_m"]
    mu = challenge["brine_viscosity"]
    log_term = math.log(assumptions["drainage_radius_m"] / assumptions["wellbore_radius_m"])
    pi_si = 2.0 * math.pi * k * h / (mu * (log_term + assumptions["skin"]))  # m3/s per Pa
    return pi_si * 3600.0 * 1e5


def load_demand(directory):
    """Load the two daily demand CSVs into one DataFrame (MW columns, 365 rows)."""
    directory = Path(directory)
    heating = pd.read_csv(directory / "GEMINI_Heating_Demand_Daily_2027.csv", parse_dates=["date"])
    cooling = pd.read_csv(directory / "GEMINI_Cooling_Demand_Daily_2027.csv", parse_dates=["date"])
    demand = heating.merge(cooling, on="date", how="outer").sort_values("date")
    demand = demand.rename(
        columns={"heating_demand_MWth": "heating_mw", "cooling_demand_MWcool": "cooling_mw"}
    )
    missing = demand[["heating_mw", "cooling_mw"]].isna().sum().sum()
    if missing or len(demand) != 365:
        raise ValueError(
            f"Demand files must hold 365 complete days, got {len(demand)} rows, {missing} gaps."
        )
    return demand.reset_index(drop=True)
