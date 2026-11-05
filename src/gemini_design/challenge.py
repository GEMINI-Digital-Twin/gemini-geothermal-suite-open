"""Fixed GeoHackathon inputs, hard constraints and documented assumptions.

``CHALLENGE`` holds only values given in the official requirements
(28 October 2026). ``ASSUMPTIONS`` holds everything the brief does not
give; each entry is something an agent must state (or ask the user
about) rather than silently invent.
"""

import argparse
import math
import os
import warnings
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
    "operating_days": 330,  # geothermal source availability per year (organisers, 1 Nov 2026)
    "heating_supply_c": 100.0,
    "cooling_supply_c": 20.0,
}

ASSUMPTIONS = {
    # geothermal source outage (gemini_design.annual.schedule_outages). Organisers, 1 Nov 2026:
    # the 330 days are the availability of the geothermal source, the other 35 days are a
    # planned or unplanned shutdown, and the full system must meet demand on all 365 days.
    # The schedule is a design choice (second answer, 1 Nov): with several doublets each may
    # take its maintenance at a different time. Chosen by Sa'eed, 2 Nov: staggered.
    "geothermal_outage_common": 0.0,  # 0: staggered per doublet; 1: all doublets stop together
    "geothermal_outage_start_day": -1.0,  # -1: lowest-load window; 0-330: fixed start day
    # district networks (not given in the brief)
    "heating_return_c": 40.0,
    "cooling_return_c": 26.0,
    # what other return temperatures cost (gemini_design.network), relative to this reference
    "network_reference_heating_return_c": 40.0,
    "network_reference_cooling_return_c": 26.0,
    "building_heating_supply_c": 55.0,  # customer heating circuit (new build, low temperature)
    "building_heating_return_c": 30.0,
    "building_cooling_supply_c": 22.0,  # customer cooling circuit behind the 20 degC supply
    "building_cooling_return_c": 32.0,
    "substation_min_approach_k": 2.0,  # plate heat exchanger, practical minimum
    "heating_substation_hex_cost_eur_per_kw": 20.0,  # HEX-area share of a ~50 EUR/kW substation
    "cooling_substation_hex_cost_eur_per_kw": 25.0,
    "heating_network_dp_bar": 6.0,  # circulation pump head, supply + return loop
    "cooling_network_dp_bar": 4.0,
    "cooling_water_c": 30.0,  # heat-rejection circuit (dry cooler / tower)
    # used only when a day's outdoor temperature is given (gemini_design.climate):
    # 30 degC = ASHRAE 0.4 % cooling design dry-bulb at Amsterdam (27.8 degC) + 2.2 K
    "dry_cooler_approach_k": 2.2,
    "cooling_water_min_c": 20.0,  # chiller head-pressure floor
    "free_cooling_approach_k": 5.0,  # air -> glycol dry cooler + plate HEX to chilled water
    "free_cooling_fan_power_fraction": 0.03,  # W_el per W of free cooling
    # wet cooling tower (chiller_type "centrifugal_tower"); team assumptions
    "design_wet_bulb_c": 20.0,  # ASHRAE 0.4 % design wet-bulb, Amsterdam Schiphol (~19.8)
    "cooling_tower_approach_k": 4.0,  # tower outlet above the air wet-bulb
    "cooling_tower_cycles": 4.0,  # cycles of concentration (blowdown = evaporation / (c - 1))
    "water_latent_heat_j_per_kg": 2.43e6,
    "water_price_eur_per_m3": 1.5,  # make-up water incl. treatment and discharge (NL industry)
    "air_cooled_condenser_approach_k": 15.0,  # condensing temperature above the air
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
    # Below the bubble point (~42 bar, gemini_design.gas_solubility) gas breaks out in the
    # top ~300 m of the producer; the single-phase well model ignores that two-phase section.
    "producer_wellhead_pressure_bar": 10.0,
    "esp_intake_pressure_min_bar": 20.0,
    # dissolved gas (gemini_design.gas_solubility): ESP intake kept this far above the bubble point
    "esp_bubble_point_margin_bar": 5.0,
    # sized ESP (gemini_design.esp; only for designs with esp_rated_flow_m3h > 0). Team
    # estimates: multistage centrifugal curve with shut-off head 1.3 x best-efficiency head,
    # operating range 60-125 % of best-efficiency flow, VSD 30-69 Hz on a 60 Hz pump
    "esp_head_margin": 1.10,  # rated head over what the well needs at the rated flow
    "esp_shutoff_head_ratio": 1.30,
    "esp_min_flow_ratio": 0.60,
    "esp_max_flow_ratio": 1.25,
    "esp_vsd_speed_min": 0.50,
    "esp_vsd_speed_max": 1.15,
    "esp_vsd_efficiency": 0.97,
    "esp_motor_margin": 1.15,  # motor rating over the hydraulic power at the rated point
    "brine_salinity_mol_per_kg": 0.75,  # NaCl equivalent of 1030 kg/m3 brine (~43 g/l)
    "setschenow_ch4_kg_per_mol": 0.127,  # log10 salting-out coefficients, 25 degC values
    "setschenow_co2_kg_per_mol": 0.10,
    # wellbore heat loss in time (gemini_design.operations, Hasan and Kabir 1991)
    "formation_conductivity_w_per_m_k": 2.5,
    "formation_diffusivity_m2_per_s": 1.0e-6,
    "wellbore_u_w_per_m2_k": 30.0,  # fluid to cement/formation face, on wellbore_radius_m
    # producer heat loss relative to GEMINI's steady well model (U = 10 W/m2K) for runs WITHOUT
    # operating rules. 1 = GEMINI as is. Operating-rule runs compute their own (time since start),
    # so this lets the wellbore effect be shown apart from the start/stop rules.
    "wellbore_heat_loss_multiplier": 1.0,
    "surface_pressure_loss_bar": 2.0,  # separator + filters + HEX, wellhead to injector pump
    # surface equipment
    # plate HEX per doublet. eps-NTU at the design duty (300 m3/h brine, district 40 -> 100 degC,
    # C_min = district side ~0.23 MW/K): 4 MW/K is NTU ~17, a ~0.1 K hot-end approach, so this
    # is close to an ideal (very large) HEX, not the ~3 K approach the old comment said. A
    # 1.45 MW/K HEX (NTU ~6, ~3 K approach) is tested in run_stress_margin.py: it leaves the
    # 3.2 km pick unchanged (EUR 36.35/MWh) but costs the 3.1 km plant +EUR 0.74/MWh.
    "hex_ua_per_doublet_w_per_k": 4.0e6,
    "separator_temperature_drop_k": 0.5,
    "boiler_efficiency": 0.9,
    "heat_pump_eta_lorenz": 0.5,
    "electric_boiler_efficiency": 0.99,  # resistive / electrode boiler
    # gas boiler part load (Plant.boiler_part_load_ratio): 0 = rated efficiency at any load;
    # 1 = fuel/heat ratio HIR(PLR) = a + b PLR + c PLR^2 of the running units. Default: a
    # modulating boiler with standby + cycling losses of 2 % of rated fuel (EN 15316-4-1
    # standby 0.5-1.5 % for large boilers, plus purge/cycling). DOE-2's default hot-water
    # boiler curve (0.0826, 0.9968, -0.0794) is an older, much lossier boiler.
    "boiler_part_load": 1.0,
    "boiler_hir_fplr_coefficients": (0.02, 0.98, 0.0),
    "unit_cost_scale_exponent": 0.7,  # cost of one unit ~ size^0.7: n units cost n^0.3 x one
    "heat_recovery_approach_k": 3.0,  # evaporator and condenser, each side
    "heat_recovery_max_supply_c": 70.0,  # heat-recovery heat pump outlet on the return line
    # daily electricity prices (gemini_design.prices): 0 = flat prices above; 1 = the 2025 NL
    # day-ahead daily means, shifted (import) and scaled (export) to keep the annual means
    "electricity_daily_prices": 1.0,
    "absorption_eta_rev": 0.2,
    "absorption_cop_max": 0.8,
    "electric_chiller_eta_carnot": 0.40,
    "electric_chiller_cop_max": 7.0,
    "electric_chiller_evaporator_approach_k": 4.0,
    "electric_chiller_condenser_approach_k": 8.0,  # above cooling water, incl. its rise
    "electric_chiller_units": 3,  # staged modules
    "chp_efficiency": 0.85,  # fuel to heat + power (GEMINI CHP splits 1/3 power, 2/3 heat)
    "chiller_aux_power_fraction": 0.02,
    # air-cooled ORC power unit on the brine (gemini_model.orc), used when a design has one.
    # Second-law fraction calibrated on a CoolProp subcritical cycle (best of 7 fluids):
    # 0.45-0.54 at 100-140 degC brine, 0.33-0.45 below 90 degC (run_orc_cycle_check.py).
    "orc_second_law_fraction": 0.45,
    "orc_condenser_approach_k": 15.0,  # air-cooled condenser, condensing above the air
    "orc_min_outlet_above_condensing_k": 20.0,  # brine outlet floor (pinch + subcooling)
    "orc_plr_min": 0.3,  # turbine minimum part load
    "orc_default_air_c": 10.0,  # outdoor air when no weather is given (NL annual mean)
    "absorption_hot_dt_max_k": 20.0,  # max brine cooling across the generator (low-temp design)
    # shallow aquifer thermal energy storage (ATES) for cooling, used when ates_doublets > 0;
    # typical Dutch open-loop systems (team assumptions, see gemini_design.ates)
    "ates_groundwater_c": 11.0,  # undisturbed shallow aquifer (NL, 50-250 m)
    "ates_flow_max_m3h": 150.0,  # per well pair
    "ates_warm_well_max_c": 25.0,  # usual Dutch permit cap on the warm well
    "ates_cold_injection_min_c": 5.0,  # stay clear of freezing in the dry cooler
    "ates_charge_air_max_c": 10.0,  # charge only when the daily mean air is below this
    "ates_charge_approach_k": 5.0,  # warm-well water leaves the dry cooler at air + approach
    "ates_hex_approach_k": 1.5,  # groundwater / chilled-water plate HEX
    "ates_pressure_drop_bar": 4.0,  # both wells, filters and HEX at full flow
    # store temperatures relax towards groundwater (~0.76 of the difference left after 6 months)
    "ates_loss_fraction_per_day": 0.0015,
    "ates_store_volume_m3": 1.5e6,  # per well pair, per store (cold or warm bubble)
    "ates_balance_tolerance": 0.10,  # |annual heat in - heat out| / heat in (permit condition)
    # well integrity (GEMINI CO2 corrosion and erosion models, gemini_design.well_integrity)
    "brine_bicarbonate_mg_per_l": 300.0,  # not in the brief (NORSOK M-506 pH input)
    "well_integrity_costs": True,  # price the corrosion mitigation into CAPEX / O&M
    "corrosion_allowance_mm": 3.0,
    "corrosion_inhibitor_efficiency": 0.90,
    "corrosion_inhibitor_cost_eur_per_doublet_year": 1.0e5,
    "corrosion_resistant_liner_cost_eur_per_m": 400.0,  # GRE-lined casing premium per well metre
    # seasonal pit thermal energy storage (PTES), used only when a design has storage
    "storage_loss_fraction_per_day": 0.001,  # ~15 % of the stored heat over a 150-day season
    # seasonal pit thermal energy storage, built-in reference model (gemini_design.pit_storage),
    # used when a design has pit_store_m3 > 0. Built Danish pits: Marstal 75,000 m3 (2012),
    # Dronninglund 60,000 m3 (2014), Gram 122,000 m3 (2015), Vojens ~200,000 m3 (2015),
    # Hoje Taastrup 70,000 m3 (2023). Team assumptions from those plants, low confidence.
    "pit_store_top_max_c": 90.0,  # polymer liner limit (Dronninglund runs at up to ~89 degC)
    "pit_store_discharge_min_c": 50.0,  # top must be at least return + 10 K to discharge
    "pit_store_charge_approach_k": 5.0,  # charge water reaches the wellhead brine less this
    "pit_store_depth_m": 16.0,  # Dronninglund 16 m, Vojens 13 m
    "pit_store_side_slope": 2.0,  # horizontal per vertical (~26.6 degrees, Dronninglund)
    "pit_store_volume_min_m3": 30000.0,  # per pit
    "pit_store_volume_max_m3": 250000.0,  # per pit (largest built ~200,000 m3); more = more pits
    "pit_store_lid_u_w_per_m2_k": 0.15,  # floating insulated lid, incl. moisture ageing
    "pit_store_ground_u_w_per_m2_k": 0.15,  # uninsulated sides/bottom to far ground, after warm-up
    "pit_store_ground_c": 10.0,  # undisturbed ground (NL)
    "pit_store_conductivity_w_per_m_k": 1.5,  # water 0.65 + mixing at the diffusers
    "pit_store_cost_ref_eur_per_m3": 40.0,  # at the reference volume, 2015 prices
    "pit_store_cost_ref_volume_m3": 60000.0,  # Dronninglund-size pit
    "pit_store_cost_exponent": 0.42,  # fit: ~40 (60k), ~36 (75k), ~30 (122k), ~24 (210k) EUR/m3
    "pit_store_price_index": 1.35,  # 2015 -> 2027 construction prices (team estimate)
    "pit_store_land_factor": 1.5,  # site area / pit top area (embankment, access, plant room)
    "pit_store_land_cost_eur_per_m2": 30.0,  # NL edge-of-town land, team estimate
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
    # sized ESP cost (gemini_design.esp), team estimates: pump + motor + cable + install;
    # the reference is the ESP share of the surface cost above (~ a 300 m3/h VSD pump at 3 km)
    "esp_cost_fixed_eur": 3.0e5,
    "esp_cost_eur_per_kw": 700.0,
    "esp_vsd_cost_eur_per_kw": 120.0,
    "esp_reference_cost_eur": 8.0e5,
    "heat_pump_cost_eur_per_mw": 7.0e5,
    "boiler_cost_eur_per_mw": 1.0e5,
    "electric_boiler_cost_eur_per_mw": 1.0e5,  # incl. grid connection share (team estimate)
    "heat_recovery_hp_cost_eur_per_mw": 1.0e6,  # per MW of cooling (~0.7 M EUR per MW heat)
    "chp_cost_eur_per_mw_el": 1.0e6,  # gas engine on low-CV associated gas
    # installed small (0.5-5 MW) low-temperature ORC incl. air-cooled condenser:
    # ~2,000-4,500 EUR/kW_e in the literature (team mid estimate)
    "orc_cost_eur_per_mw_el": 3.0e6,
    "absorption_chiller_cost_eur_per_mw": 4.0e5,
    "electric_chiller_cost_eur_per_mw": 2.5e5,
    "cooling_tower_cost_eur_per_mw": 5.0e4,  # per MW of heat rejected at design (team assumption)
    "ates_well_pair_cost_eur": 6.0e5,  # two 150-250 m wells, pumps, piping (team assumption)
    "ates_hex_cost_eur_per_mw": 4.0e4,
    "ates_charge_cooler_cost_eur_per_mw": 8.0e4,  # dry cooler that charges the cold well
    "free_cooling_cost_eur_per_mw": 1.0e5,  # plate HEX, valves, controls (team assumption)
    "storage_cost_eur_per_mwh": 500.0,  # PTES ~30 EUR/m3 at 50 K (Dronninglund, Vojens range)
    "storage_power_cost_eur_per_mw": 1.0e5,  # charge/discharge HEX and pumps
    "fixed_om_fraction": 0.02,  # of CAPEX per year
    "discount_rate": 0.06,
    "lifetime_years": 30,
}

# Electric chiller technologies. "legacy" is the conservative model the first
# screen used. The others are calibrated with the model's own approach
# convention (evaporator 4 K below the chilled-water supply, condenser
# ``condenser_approach_k`` above its heat sink) to the ASHRAE 90.1-2019
# Table 6.8.1-3 path A minimum full-load efficiencies at AHRI 550/590
# conditions (6.7 degC chilled water; 29.4 degC condenser water or 35 degC
# air), so they are code-minimum machines, not best-in-class ones:
#   water-cooled centrifugal >= 600 t: 0.560 kW/t -> COP 6.28 -> eta 0.79
#   water-cooled screw >= 600 t:       0.585 kW/t -> COP 6.01 -> eta 0.76
#   air-cooled >= 150 t:               10.1 EER   -> COP 2.96 -> eta 0.51 (fans included)
# Part-load curves are the DOE-2 defaults (centrifugal; positive displacement).
CHILLER_TYPES = {
    "legacy": {
        "heat_rejection": "dry_cooler",
        "eta_carnot": 0.40,
        "cop_max": 7.0,
        "condenser_approach_k": 8.0,
        "part_load_coefficients": [0.222, 0.313, 0.465],
        "plr_min": 0.15,
        "units": 3,
        "aux_power_fraction": 0.02,
        "cost_eur_per_mw": 2.5e5,
    },
    "screw_dry_cooler": {
        "heat_rejection": "dry_cooler",
        "eta_carnot": 0.76,
        "cop_max": 10.0,
        "condenser_approach_k": 8.0,
        "part_load_coefficients": [0.088, 1.138, -0.226],
        "plr_min": 0.10,
        "units": 3,
        "aux_power_fraction": 0.03,  # dry-cooler fans and pumps
        "cost_eur_per_mw": 2.5e5,
    },
    "centrifugal_tower": {
        "heat_rejection": "tower",
        "eta_carnot": 0.79,
        "cop_max": 10.0,
        "condenser_approach_k": 8.0,
        "part_load_coefficients": [0.222, 0.313, 0.465],
        "plr_min": 0.20,  # surge limit
        "units": 3,
        "aux_power_fraction": 0.02,  # tower fans and condenser pumps
        "cost_eur_per_mw": 2.2e5,  # plus the tower (cooling_tower_cost_eur_per_mw)
    },
    "air_cooled_screw": {
        "heat_rejection": "air",
        "eta_carnot": 0.51,
        "cop_max": 7.0,
        "condenser_approach_k": 15.0,
        "part_load_coefficients": [0.088, 1.138, -0.226],
        "plr_min": 0.10,
        "units": 8,  # packaged modules of ~1.5 MW
        "aux_power_fraction": 0.0,  # condenser fans are inside the rated efficiency
        "cost_eur_per_mw": 2.0e5,
    },
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


OFFICIAL_FILES = {
    "heating": "GEMINI_Heating_Demand_Daily_2027.csv",
    "cooling": "GEMINI_Cooling_Demand_Daily_2027.csv",
}
DEFAULT_INPUTS = Path(__file__).resolve().parents[2] / "simulator_examples" / "hackathon_inputs"
MAX_GAP_DAYS = 3  # longer gaps in a demand file are an error, not interpolated


def default_inputs_dir():
    """Demand folder to use: ``$GEMINI_INPUTS`` if set, else the official 2027 inputs."""
    env = os.environ.get("GEMINI_INPUTS", "").strip()
    return Path(env) if env else DEFAULT_INPUTS


def _inputs_dir_arg(text):
    """argparse type for ``--inputs``: a folder; also exported as ``$GEMINI_INPUTS`` so
    worker processes and the agent's tools load the same files."""
    path = Path(text).expanduser().resolve()
    if not path.is_dir():
        raise argparse.ArgumentTypeError(f"--inputs: {text} is not a folder")
    os.environ["GEMINI_INPUTS"] = str(path)
    return path


def add_inputs_argument(parser):
    """Add ``--inputs DIR`` (other heating and cooling demand files) to a script."""
    parser.add_argument(
        "--inputs",
        type=_inputs_dir_arg,
        default=None,
        metavar="DIR",
        help="folder with a heating and a cooling daily demand CSV (default: $GEMINI_INPUTS "
        "or simulator_examples/hackathon_inputs). See gemini_design.challenge.load_demand.",
    )
    return parser


def _demand_file(directory, kind):
    """The heating or cooling CSV in ``directory``: the official name, else the one CSV
    whose name contains 'heat' / 'cool' (any year, any case)."""
    official = directory / OFFICIAL_FILES[kind]
    if official.exists():
        return official
    stem = kind[:4]  # "heat" / "cool"
    found = sorted(p for p in directory.glob("*.csv") if stem in p.name.lower())
    if len(found) != 1:
        raise ValueError(
            f"Need exactly one {kind} demand CSV in {directory} (a name containing "
            f"'{stem}'), found {[p.name for p in found] or 'none'}."
        )
    return found[0]


def _parse_dates(values):
    """Dates from ISO (2027-01-31), compact (20270131) or day-first (31/01/2027) text."""
    text = values.astype(str).str.strip()
    for fmt in ("ISO8601", "%Y%m%d"):
        try:
            return pd.to_datetime(text, format=fmt)
        except (ValueError, TypeError):
            pass
    return pd.to_datetime(text, dayfirst=True)  # raises if the column holds no dates


def _read_profile(path, kind):
    """One demand file as (date, MW) columns. Detects the date and value columns."""
    raw = pd.read_csv(path, sep=None, engine="python")
    raw.columns = [str(c).strip() for c in raw.columns]
    names = {c.lower(): c for c in raw.columns}
    date_col = next(
        (names[n] for n in names if any(w in n for w in ("date", "day", "time"))), raw.columns[0]
    )
    others = [c for c in raw.columns if c != date_col]
    numeric = [c for c in others if pd.to_numeric(raw[c], errors="coerce").notna().mean() > 0.9]
    by_name = [c for c in numeric if kind[:4] in c.lower()]
    if len(numeric) == 1:
        value_col = numeric[0]
    elif len(by_name) == 1:
        value_col = by_name[0]
    else:
        raise ValueError(
            f"{path.name}: can not tell which column is the {kind} demand among {numeric}."
        )
    values = pd.to_numeric(raw[value_col], errors="coerce").astype(float)
    unit = value_col.lower()
    if "kw" in unit and "mw" not in unit:
        values = values / 1000.0  # kW columns to MW
    elif "gw" in unit:
        values = values * 1000.0
    out = pd.DataFrame({"date": _parse_dates(raw[date_col]), f"{kind}_mw": values})
    if out["date"].duplicated().any():
        raise ValueError(
            f"{path.name}: dates repeat ({out['date'][out['date'].duplicated()].iloc[0].date()})."
        )
    if (out[f"{kind}_mw"] < 0).any():
        raise ValueError(f"{path.name}: negative {kind} demand.")
    return out


def load_demand(directory=None):
    """Load the two daily demand CSVs into one DataFrame (date, heating_mw, cooling_mw).

    Works for the official 2027 files and for other daily profiles: any year, file
    names that contain 'heat' and 'cool', any date and value column names (MW, or
    kW/GW by name), comma or semicolon separators and day-first dates. The design
    year is 365 days on a January to December calendar (weather and price days are
    matched by month and day), so:

    * a leap year's 29 February is dropped, with a warning;
    * gaps of up to ``MAX_GAP_DAYS`` days are filled by linear interpolation, with a
      warning; longer gaps, or a profile that is not one year of days, raise.
    """
    directory = Path(directory) if directory is not None else default_inputs_dir()
    heating = _read_profile(_demand_file(directory, "heating"), "heating")
    cooling = _read_profile(_demand_file(directory, "cooling"), "cooling")
    demand = heating.merge(cooling, on="date", how="outer").sort_values("date")
    leap = (demand["date"].dt.month == 2) & (demand["date"].dt.day == 29)
    if leap.any():
        warnings.warn("Demand: 29 February dropped (the design year has 365 days).")
        demand = demand[~leap]
    start = demand["date"].iloc[0]
    days = pd.date_range(start, start + pd.DateOffset(years=1) - pd.Timedelta(days=1), freq="D")
    days = days[~((days.month == 2) & (days.day == 29))]
    if len(demand) > len(days) or not demand["date"].isin(days).all():
        raise ValueError(
            f"Demand files must hold one year of daily values, got {len(demand)} rows "
            f"from {start.date()} to {demand['date'].iloc[-1].date()}."
        )
    demand = demand.set_index("date").reindex(days)
    gaps = demand[["heating_mw", "cooling_mw"]].isna().any(axis=1)
    if gaps.any():
        run = gaps.groupby((~gaps).cumsum()).sum().max()
        if run > MAX_GAP_DAYS:
            raise ValueError(
                f"Demand files must hold 365 complete days: {int(gaps.sum())} days missing, "
                f"up to {int(run)} in a row (at most {MAX_GAP_DAYS} are filled)."
            )
        warnings.warn(f"Demand: {int(gaps.sum())} missing days filled by linear interpolation.")
        demand = demand.interpolate(limit_direction="both")
    demand = demand.rename_axis("date").reset_index()
    if start.month != 1 or start.day != 1:  # weather and prices run January to December
        warnings.warn("Demand: profile does not start on 1 January; days put in calendar order.")
        order = demand["date"].dt.month * 100 + demand["date"].dt.day
        demand = demand.iloc[order.argsort(kind="stable")]
    return demand[["date", "heating_mw", "cooling_mw"]].reset_index(drop=True)
