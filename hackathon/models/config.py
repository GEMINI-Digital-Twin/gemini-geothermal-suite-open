"""Load the hackathon's fixed inputs, assumptions and economics.

``load_config()`` returns a flat, typed view the models use, so no model
reads the YAML directly. Every assumption keeps its source and status so the
agent and the report can trace each number (see notes/decisions.md).
"""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

HACKATHON_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = HACKATHON_DIR.parent
DEFAULT_CONFIG = HACKATHON_DIR / "config" / "fixed_inputs.yaml"
MD_TO_M2 = 9.869233e-16


@dataclass
class Config:
    """Flat view of fixed_inputs.yaml."""

    raw: dict
    # reservoir
    ref_depth_m: float
    thickness_m: float
    gradient_c_per_m: float
    surface_temp_c: float
    ref_pressure_bar: float
    permeability_m2: float
    # brine and gas
    rho: float
    mu: float
    cp: float
    glr: float
    x_ch4: float
    x_co2: float
    ch4_lhv_mj_kg: float
    ch4_density: float
    co2_density: float
    gas_liberation_fraction: float
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
    # wells
    wellhead_pressure_bar: float
    surface_loss_bar: float
    well_id_m: float
    roughness_m: float
    skin_producer: float
    skin_injector: float
    well_spacing_m: float
    lifetime_years: float
    rock_cp: float
    rock_density: float
    porosity: float
    boiler_eff: float
    economics: dict = field(default_factory=dict)
    assumption_status: dict = field(default_factory=dict)
    uncertainty_ranges: dict = field(default_factory=dict)

    @property
    def ch4_lhv_mj_nm3(self):
        """Derived: GEMINI's 50 MJ/kg x methane density at 0 C, 1 atm."""
        return self.ch4_lhv_mj_kg * self.ch4_density

    def demand_path(self, kind):
        """Absolute path of the heating or cooling demand CSV."""
        return HACKATHON_DIR / self.raw["fact_sheet"]["demand_files"][kind]


def load_config(path=DEFAULT_CONFIG, overrides=None):
    """Read fixed_inputs.yaml and return a Config.

    ``overrides`` maps assumption names (e.g. ``"porosity"``) to new values;
    the agent and the robustness check use it instead of editing the YAML.
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
        ch4_lhv_mj_kg=a["ch4_lhv_mj_per_kg"],
        ch4_density=a["ch4_density_kg_nm3"],
        co2_density=a["co2_density_kg_nm3"],
        gas_liberation_fraction=a["gas_liberation_fraction"],
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
        wellhead_pressure_bar=a["wellhead_pressure_bar"],
        surface_loss_bar=a["surface_pressure_loss_bar"],
        well_id_m=a["well_inner_diameter_m"],
        roughness_m=a["pipe_roughness_m"],
        skin_producer=a["skin_producer"],
        skin_injector=a["skin_injector"],
        well_spacing_m=a["well_spacing_m"],
        lifetime_years=a["doublet_lifetime_years"],
        rock_cp=a["rock_grain_cp_j_kgk"],
        rock_density=a["rock_grain_density_kg_m3"],
        porosity=a["porosity"],
        boiler_eff=a["boiler_efficiency"],
        economics=raw["economics"],
        assumption_status={k: v["status"] for k, v in raw["assumptions"].items()},
        uncertainty_ranges={k: v["uncertainty"] for k, v in raw["assumptions"].items()
                            if v.get("uncertainty")},
    )
