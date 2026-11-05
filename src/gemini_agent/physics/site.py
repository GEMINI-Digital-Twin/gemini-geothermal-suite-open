"""Design brief and site model.

Turns the fixed technical inputs of the challenge brief into the quantities the
GEMINI models need for *any* candidate well depth:

- reservoir temperature from the geothermal gradient,
- reservoir pressure scaled hydrostatically from the reference point,
- well productivity / injectivity index from permeability (Darcy radial flow) --
  a model GEMINI does not provide (its IPR takes PI as an input),
- associated-gas properties (CH4/CO2 mix) for energy and CO2 accounting.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from pathlib import Path

import yaml

MD_TO_M2 = 9.869233e-16  # 1 milliDarcy in m2
G = 9.80665  # m/s2
BAR = 1e5  # Pa

# Gas properties at normal conditions (0 C, 1.01325 bar a)
RHO_CH4_NM3 = 0.7168  # kg/Nm3
RHO_CO2_NM3 = 1.9768  # kg/Nm3
LHV_CH4_MJ_PER_NM3 = 35.88  # lower heating value, MJ/Nm3

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_BRIEF = Path(__file__).resolve().parents[1] / "data" / "brief_geohackathon2026.yaml"


@dataclass
class Demand:
    """Daily demand profiles (MW, daily average)."""

    dates: list[str]
    heating_mw: list[float]
    cooling_mw: list[float]
    heating_supply_c: float
    cooling_supply_c: float

    @property
    def n_days(self) -> int:
        """Number of daily steps."""
        return len(self.dates)

    def summary(self) -> dict:
        """Compact statistics used by tools and the requirements analyst."""
        h, c = self.heating_mw, self.cooling_mw
        ih, ic = h.index(max(h)), c.index(max(c))
        combined = [a + b for a, b in zip(h, c)]
        return {
            "days": self.n_days,
            "heating_peak_mw": round(max(h), 3),
            "heating_peak_date": self.dates[ih],
            "heating_min_mw": round(min(h), 3),
            "heating_energy_gwh": round(sum(h) * 24 / 1000, 3),
            "cooling_peak_mw": round(max(c), 3),
            "cooling_peak_date": self.dates[ic],
            "cooling_energy_gwh": round(sum(c) * 24 / 1000, 3),
            "cooling_days_nonzero": sum(1 for x in c if x > 0),
            "combined_peak_mw": round(max(combined), 3),
            "heating_supply_c": self.heating_supply_c,
            "cooling_supply_c": self.cooling_supply_c,
        }


@dataclass
class Brief:
    """Fixed technical inputs of the design problem (see brief YAML)."""

    raw: dict = field(repr=False)

    @classmethod
    def load(cls, path: str | Path | None = None) -> "Brief":
        """Load a brief YAML file (defaults to the GeoHackathon 2026 brief)."""
        with open(path or DEFAULT_BRIEF, "r", encoding="utf-8") as f:
            return cls(raw=yaml.safe_load(f))

    # --- convenience accessors -------------------------------------------------
    @property
    def reservoir(self) -> dict:
        """Reservoir section."""
        return self.raw["reservoir"]

    @property
    def brine(self) -> dict:
        """Brine and gas section."""
        return self.raw["brine"]

    @property
    def constraints(self) -> dict:
        """Hard design/operating constraints."""
        return self.raw["constraints"]

    def assumption(self, name: str) -> float:
        """Value of a documented assumption (inputs the brief does not specify)."""
        return self.raw["assumptions"][name]["value"]

    def assumptions_table(self) -> list[dict]:
        """All assumptions with justification (for the brief card / report)."""
        return [{"name": k, **v} for k, v in self.raw.get("assumptions", {}).items()]

    def load_demand(self, root: str | Path | None = None) -> Demand:
        """Read the heating and cooling CSV files referenced by the brief."""
        root = Path(root) if root else REPO_ROOT
        d = self.raw["demand"]
        dates, heat = _read_csv(root / d["heating_csv"])
        dates_c, cool = _read_csv(root / d["cooling_csv"])
        if dates != dates_c:
            raise ValueError("Heating and cooling CSV files do not share the same dates.")
        return Demand(
            dates, heat, cool, d["heating_supply_temperature_c"], d["cooling_supply_temperature_c"]
        )


def _read_csv(path: Path) -> tuple[list[str], list[float]]:
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    key = [k for k in rows[0] if k != "date"][0]
    return [r["date"] for r in rows], [float(r[key]) for r in rows]


@dataclass
class ReservoirState:
    """Reservoir conditions at a chosen well (midpoint) depth."""

    depth_m: float
    temperature_c: float
    pressure_bar: float
    productivity_index_m3h_per_bar: float
    injectivity_index_m3h_per_bar: float


def reservoir_temperature_c(brief: Brief, depth_m: float) -> float:
    """Reservoir temperature from the linear geothermal gradient."""
    r = brief.reservoir
    return r["surface_temperature_c"] + r["geothermal_gradient_c_per_km"] * depth_m / 1000.0


def reservoir_pressure_bar(brief: Brief, depth_m: float) -> float:
    """Reservoir pressure, hydrostatic scaling through the brief's reference point.

    The brief gives 250 bar(g) at 2,500 m and says to use hydrostatic pressure
    for other depths. Scaling linearly through the reference point keeps the
    reference value exact (implied gradient 0.1 bar/m, i.e. ~1,020 kg/m3 brine
    column, consistent with the 1,030 kg/m3 brine density within 1 %).
    """
    r = brief.reservoir
    return r["reference_pressure_bar"] * depth_m / r["reference_depth_m"]


def productivity_index_m3h_per_bar(
    brief: Brief,
    well_spacing_m: float = 1500.0,
    wellbore_radius_m: float = 0.108,
    skin: float = 0.0,
) -> float:
    """Well productivity index from permeability (steady-state Darcy radial flow).

    PI = 2*pi*k*h / (mu * (ln(r_e / r_w) + S)), with the drainage radius r_e
    taken as the doublet spacing (steady source-sink doublet: each well sees
    half of the total pressure difference mu*Q/(pi*k*h)*ln(L/r_w)).

    GEMINI's ``IPR`` model needs PI as an input but has no model to derive it
    from reservoir properties; this function fills that gap.
    """
    k = brief.reservoir["permeability_md"] * MD_TO_M2
    h = brief.reservoir["gross_thickness_m"]
    mu = brief.brine["viscosity_pa_s"]
    pi_si = 2 * math.pi * k * h / (mu * (math.log(well_spacing_m / wellbore_radius_m) + skin))
    return pi_si * 3600.0 * BAR  # (m3/s)/Pa -> (m3/h)/bar


def reservoir_state(brief: Brief, depth_m: float, **pi_kwargs) -> ReservoirState:
    """Reservoir state at ``depth_m`` (TVD of the reservoir midpoint)."""
    pi = productivity_index_m3h_per_bar(brief, **pi_kwargs)
    return ReservoirState(
        depth_m=depth_m,
        temperature_c=reservoir_temperature_c(brief, depth_m),
        pressure_bar=reservoir_pressure_bar(brief, depth_m),
        productivity_index_m3h_per_bar=pi,
        injectivity_index_m3h_per_bar=pi,  # same reservoir, viscosity fixed by the brief
    )


@dataclass
class GasProperties:
    """Associated gas (CH4/CO2 mix) per m3 of produced brine."""

    gas_nm3_per_m3: float
    ch4_nm3_per_m3: float
    co2_nm3_per_m3: float
    fuel_energy_mj_per_m3: float  # LHV of the CH4 content
    co2_if_burned_kg_per_m3: float  # combustion CO2 + co-produced CO2
    co2_if_vented_kg_per_m3: float  # co-produced CO2 only (CH4 venting excluded: not allowed)
    mix_density_kg_per_nm3: float
    mix_lhv_mj_per_kg: float


def gas_properties(brief: Brief) -> GasProperties:
    """Energy and CO2 content of the associated gas per m3 of produced brine."""
    b = brief.brine
    glr, x_ch4, x_co2 = (
        b["gas_liquid_ratio_nm3_per_m3"],
        b["gas_ch4_mol_frac"],
        b["gas_co2_mol_frac"],
    )
    ch4, co2 = glr * x_ch4, glr * x_co2
    rho_mix = x_ch4 * RHO_CH4_NM3 + x_co2 * RHO_CO2_NM3
    return GasProperties(
        gas_nm3_per_m3=glr,
        ch4_nm3_per_m3=ch4,
        co2_nm3_per_m3=co2,
        fuel_energy_mj_per_m3=ch4 * LHV_CH4_MJ_PER_NM3,
        co2_if_burned_kg_per_m3=(ch4 + co2) * RHO_CO2_NM3,  # 1 mol CO2 per mol CH4 burned
        co2_if_vented_kg_per_m3=co2 * RHO_CO2_NM3,
        mix_density_kg_per_nm3=rho_mix,
        mix_lhv_mj_per_kg=x_ch4 * LHV_CH4_MJ_PER_NM3 / rho_mix,
    )
