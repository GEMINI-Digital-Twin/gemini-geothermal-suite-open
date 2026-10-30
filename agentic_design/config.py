"""Challenge inputs, explicit assumptions and demand loading.

Everything the design workflow depends on lives here, split into:

* ``CHALLENGE`` - values fixed by the organisers ("GEMINI Hackathon Challenge
  Requirements", 28 October 2026). These must not be changed by the agent.
* ``Assumptions`` - values the challenge does NOT specify. Each one carries a
  short justification so the agent (and the report) can disclose it. The agent
  may change these, but every change must be logged.
"""

from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
HEATING_CSV = DATA_DIR / "gemini_heating_demand_daily_2027.csv"
COOLING_CSV = DATA_DIR / "gemini_cooling_demand_daily_2027.csv"

G = 9.81  # m/s2

# --------------------------------------------------------------------------
# Fixed challenge inputs (source: challenge requirements document, sections 2-3)
# --------------------------------------------------------------------------
CHALLENGE = {
    # 3.1 Geothermal reservoir
    "reservoir_midpoint_depth_m": 2500.0,
    "reservoir_gross_thickness_m": 100.0,
    "geothermal_gradient_c_per_km": 30.0,
    "surface_temperature_c": 12.0,
    "reservoir_pressure_bar": 250.0,  # bar(g) at the midpoint depth
    "permeability_md": 200.0,
    # 3.2 Brine and associated gas
    "brine_density_kg_m3": 1030.0,
    "brine_viscosity_pa_s": 0.40e-3,
    "gas_liquid_ratio_nm3_per_m3": 0.8,
    "gas_ch4_mol_frac": 0.80,
    "gas_co2_mol_frac": 0.20,
    # 3 Design and operating constraints
    "n_doublets_min": 1,
    "n_doublets_max": 3,
    "max_flow_m3h_per_doublet": 300.0,
    "min_flow_m3h_per_doublet": 50.0,  # while active
    "max_brine_cooling_c": 40.0,  # producer -> injector
    "pump_hydraulic_efficiency": 0.70,
    "max_operating_days_per_doublet": 330,  # "330 daily steps" - see Assumptions
    "heating_supply_temperature_c": 100.0,
    "cooling_supply_temperature_c": 20.0,
    # 2 Demand files
    "heating_annual_gwh": 111.67,
    "cooling_annual_gwh": 23.74,
}

# Gas properties at normal conditions (0 degC, 1.01325 bar), standard reference values
CH4_DENSITY_KG_NM3 = 0.7175
CO2_DENSITY_KG_NM3 = 1.9768
CH4_LHV_MJ_NM3 = 35.83  # lower heating value of methane per Nm3


@dataclass
class Assumptions:
    """Inputs the challenge leaves open. Each has a reason; all are disclosed."""

    # --- District heating network (NOT given in the challenge) ---
    heating_return_temperature_c: float = 55.0
    # typical 3rd-generation network return for a 100 degC supply

    # --- Brine thermophysics ---
    brine_specific_heat_j_kgk: float = 4000.0
    # saline brine ~3.9-4.1 kJ/kgK; the bootcamp presenter used ~4000-4100

    # --- Reservoir inflow ---
    drainage_radius_m: float = 1000.0  # steady-state radial inflow, Darcy
    wellbore_radius_m: float = 0.108  # 8.5 inch hole
    skin: float = 0.0
    net_to_gross: float = 1.0  # gross thickness taken as fully productive

    # --- Wells ---
    well_inner_diameter_m: float = 0.20  # ~8 inch flow path
    casing_roughness_m: float = 1.0e-4  # 0.1 mm used steel casing (GEMINI default 10 mm is unrealistic)
    well_heat_transfer_u_w_m2k: float = 10.0  # GEMINI DPDT default
    segment_length_m: float = 100.0
    esp_depth_m: float = 650.0  # as in the GEMINI doublet example
    producer_wellhead_pressure_bar: float = 10.0
    # keeps CO2/CH4 in solution up to the separator (bubble point not given)
    min_esp_intake_pressure_bar: float = 10.0  # avoid gas breakout / cavitation at the pump

    # --- Surface plant ---
    surface_pressure_drop_bar: float = 3.0  # separator + filters + HX at design flow
    surface_temperature_loss_c: float = 0.5  # piping/separator/filters
    hx_min_approach_c: float = 3.0  # plate HX pinch

    # --- Gas use and emissions ---
    boiler_efficiency: float = 0.90  # on LHV, condensing not assumed at 100 degC supply
    natural_gas_lhv_mj_nm3: float = 35.17  # Dutch H-gas, LHV
    natural_gas_co2_kg_nm3: float = 1.89  # stoichiometric CO2 of H-gas combustion
    natural_gas_density_kg_nm3: float = 0.833  # Dutch H-gas
    electricity_co2_kg_kwh: float = 0.30  # same factor as the GEMINI doublet example

    # --- Annual operation ("330 daily steps" interpreted as max 330 days/doublet) ---
    maintenance_days_per_doublet: int = 35
    maintenance_start_doy: list = field(default_factory=list)  # 0-based day of year per doublet

    # --- Feasibility tolerances ---
    demand_tolerance_mw: float = 1e-3

    def to_dict(self):
        return asdict(self)


def reservoir_temperature_c(depth_m: float) -> float:
    """Linear geotherm from the challenge inputs."""
    return (
        CHALLENGE["surface_temperature_c"]
        + CHALLENGE["geothermal_gradient_c_per_km"] * depth_m / 1000.0
    )


def ambient_temperature_c(depth_m):
    """Undisturbed formation temperature along the well (vectorised)."""
    return CHALLENGE["surface_temperature_c"] + CHALLENGE[
        "geothermal_gradient_c_per_km"
    ] * np.asarray(depth_m) / 1000.0


def reservoir_pressure_bar(depth_m: float) -> float:
    """Reservoir pressure at depth.

    Anchored to the given 250 bar(g) at the 2,500 m midpoint and extrapolated
    with a hydrostatic brine gradient, as the challenge suggests for other
    depths. (Pure hydrostatic rho*g*z would give 252.6 bar at 2,500 m, 1%
    above the given value, so we anchor to the given value.)
    """
    rho = CHALLENGE["brine_density_kg_m3"]
    z0 = CHALLENGE["reservoir_midpoint_depth_m"]
    return CHALLENGE["reservoir_pressure_bar"] + rho * G * (depth_m - z0) / 1e5


def gas_properties():
    """Associated gas: density, LHV and CO2 released per Nm3 when burned."""
    x_ch4, x_co2 = CHALLENGE["gas_ch4_mol_frac"], CHALLENGE["gas_co2_mol_frac"]
    density = x_ch4 * CH4_DENSITY_KG_NM3 + x_co2 * CO2_DENSITY_KG_NM3
    lhv_mj_nm3 = x_ch4 * CH4_LHV_MJ_NM3
    # burning CH4 makes 1 mol CO2 per mol CH4; the 20% CO2 passes through
    co2_kg_nm3 = (x_ch4 + x_co2) * CO2_DENSITY_KG_NM3
    return {
        "density_kg_nm3": density,
        "lhv_mj_nm3": lhv_mj_nm3,
        "lhv_mj_kg": lhv_mj_nm3 / density,
        "co2_kg_nm3_burned": co2_kg_nm3,
    }


def load_demand(heating_csv=HEATING_CSV, cooling_csv=COOLING_CSV) -> pd.DataFrame:
    """Return a 365-row DataFrame: date, heating_mw, cooling_mw (daily averages)."""
    h = pd.read_csv(heating_csv, parse_dates=["date"])
    c = pd.read_csv(cooling_csv, parse_dates=["date"])
    df = h.merge(c, on="date", how="outer").sort_values("date").reset_index(drop=True)
    df = df.rename(columns={"heating_demand_MWth": "heating_mw", "cooling_demand_MWcool": "cooling_mw"})
    problems = []
    if len(df) != 365:
        problems.append(f"expected 365 days, got {len(df)}")
    if df[["heating_mw", "cooling_mw"]].isna().any().any():
        problems.append("missing values after merging heating and cooling files")
    if (df[["heating_mw", "cooling_mw"]] < 0).any().any():
        problems.append("negative demand values")
    if problems:
        raise ValueError("Demand data check failed: " + "; ".join(problems))
    return df
