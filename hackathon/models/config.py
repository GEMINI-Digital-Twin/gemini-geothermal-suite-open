"""Load the hackathon's fixed inputs and assumptions.

``load_config()`` returns a flat, typed view the models use, so no model
reads the YAML directly. Every assumption keeps its status so the agent
and the report can say which numbers are confirmed and which are defaults.
"""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

HACKATHON_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = HACKATHON_DIR.parent
DEFAULT_CONFIG = HACKATHON_DIR / "config" / "fixed_inputs.yaml"


@dataclass
class Config:
    """Flat view of fixed_inputs.yaml (fact sheet + assumption values)."""

    raw: dict
    # reservoir
    ref_depth_m: float
    thickness_m: float
    gradient_c_per_m: float
    surface_temp_c: float
    ref_pressure_bar: float
    permeability_m2: float
    # brine
    rho: float
    mu: float
    cp: float
    glr: float
    x_ch4: float
    x_co2: float
    # constraints
    n_min: int
    n_max: int
    q_min: float
    q_max: float
    dt_brine_max: float
    pump_eff: float
    op_days: int
    # supply / return
    t_heat_supply: float
    t_cool_supply: float
    t_heat_return: float
    t_cool_return: float
    # well / plant assumptions
    wellhead_pressure_bar: float
    well_spacing_m: float
    well_id_m: float
    skin: float
    ch4_lhv_mj_nm3: float
    boiler_eff: float
    gas_liberation_fraction: float
    lifetime_years: float
    rock_cp: float
    rock_density: float
    porosity: float
    well_designs: dict
    default_well_design: str
    assumption_status: dict = field(default_factory=dict)
    uncertainty_ranges: dict = field(default_factory=dict)

    def well_id_for(self, design_name=None):
        """Inner diameter (m) of a named well design (default design if None)."""
        return self.well_designs[design_name or self.default_well_design]["inner_diameter_m"]

    def demand_path(self, kind):
        """Absolute path of the heating or cooling demand CSV."""
        return HACKATHON_DIR / self.raw["fact_sheet"]["demand_files"][kind]


MD_TO_M2 = 9.869233e-16


def load_config(path=DEFAULT_CONFIG, overrides=None):
    """Read fixed_inputs.yaml and return a Config.

    ``overrides`` maps assumption names (e.g. ``"heating_return_c"``) to new
    values; the agent and the uncertainty run use it instead of editing YAML.
    """
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    a = {k: v["value"] for k, v in raw["assumptions"].items()}
    if overrides:
        unknown = set(overrides) - set(a)
        if unknown:
            raise KeyError(f"Unknown assumption(s): {sorted(unknown)}")
        a.update(overrides)
    fs = raw["fact_sheet"]
    r, b, c, s = fs["reservoir"], fs["brine"], fs["constraints"], fs["supply"]
    return Config(
        raw=raw,
        ref_depth_m=r["midpoint_depth_m"],
        thickness_m=r["gross_thickness_m"],
        gradient_c_per_m=r["geothermal_gradient_c_per_km"] / 1000.0,
        surface_temp_c=r["surface_temperature_c"],
        ref_pressure_bar=r["pressure_bar"],
        permeability_m2=r["permeability_md"] * MD_TO_M2,
        rho=b["density_kg_m3"],
        mu=b["viscosity_pa_s"],
        cp=a["brine_cp_j_kgk"],
        glr=b["glr_nm3_per_m3"],
        x_ch4=b["gas_ch4_mol_frac"],
        x_co2=b["gas_co2_mol_frac"],
        n_min=c["doublets_min"],
        n_max=c["doublets_max"],
        q_min=c["flow_min_m3h"],
        q_max=c["flow_max_m3h"],
        dt_brine_max=c["brine_cooling_max_c"],
        pump_eff=c["pump_hydraulic_efficiency"],
        op_days=c["geothermal_operating_days"],
        t_heat_supply=s["heating_supply_c"],
        t_cool_supply=s["cooling_supply_c"],
        t_heat_return=a["heating_return_c"],
        t_cool_return=a["cooling_return_c"],
        wellhead_pressure_bar=a["wellhead_pressure_bar"],
        well_spacing_m=a["doublet_well_spacing_m"],
        well_id_m=a["well_designs"][a["default_well_design"]]["inner_diameter_m"],
        skin=a["skin"],
        ch4_lhv_mj_nm3=a["ch4_lhv_mj_per_nm3"],
        boiler_eff=a["boiler_efficiency"],
        gas_liberation_fraction=a["gas_liberation_fraction"],
        lifetime_years=a["doublet_lifetime_years"],
        rock_cp=a["rock_grain_cp_j_kgk"],
        rock_density=a["rock_grain_density_kg_m3"],
        porosity=a["porosity"],
        well_designs=a["well_designs"],
        default_well_design=a["default_well_design"],
        assumption_status={k: v["status"] for k, v in raw["assumptions"].items()},
        uncertainty_ranges={k: v["uncertainty"] for k, v in raw["assumptions"].items()
                            if v.get("uncertainty")},
    )
