"""Fixed hackathon inputs and hard constraints (from GEMINI_Hackathon_Challenge_Requirements)."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass(frozen=True)
class ReservoirSpec:
    """Section 3.1 - Geothermal reservoir (baseline at 2,500 m midpoint)."""

    midpoint_depth_m: float = 2500.0          # m TVD
    gross_thickness_m: float = 100.0          # m
    geothermal_gradient_c_per_km: float = 30.0
    surface_temperature_c: float = 12.0
    pressure_bar_g: float = 250.0             # bar(g) at 2,500 m
    permeability_md: float = 200.0            # mD

    def temperature_at_depth(self, depth_m: float) -> float:
        """Reservoir temperature from the fixed geothermal gradient (deg C)."""
        return self.surface_temperature_c + self.geothermal_gradient_c_per_km * depth_m / 1000.0

    def pressure_at_depth(self, depth_m: float, brine_density: float = 1030.0) -> float:
        """Reservoir pressure in bar(g).

        The requirements fix 250 bar(g) at 2,500 m (slightly below the brine hydrostatic
        column) and allow a hydrostatic estimate for other depths. We anchor the hydrostatic
        line on the fixed value so the baseline depth reproduces the specified pressure.
        """
        g = 9.80665
        base = self.pressure_bar_g
        return base + brine_density * g * (depth_m - self.midpoint_depth_m) / 1e5


@dataclass(frozen=True)
class BrineSpec:
    """Section 3.2 - Geothermal brine and associated gas."""

    density_kg_m3: float = 1030.0
    viscosity_pa_s: float = 0.40e-3           # 0.40 mPa.s
    glr_nm3_per_m3: float = 0.8               # Nm3 gas per m3 produced liquid
    ch4_mol_frac: float = 0.80
    co2_mol_frac: float = 0.20
    specific_heat_j_kg_k: float = 3900.0      # brine ~ 1030 kg/m3 (slightly saline water)


@dataclass(frozen=True)
class Constraints:
    """Section 3 - Design and operating constraints (hard caps)."""

    min_doublets: int = 1
    max_doublets: int = 3
    max_flow_m3_h_per_doublet: float = 300.0
    min_flow_m3_h_per_doublet: float = 50.0
    max_brine_cooling_c: float = 40.0         # producer -> injector delta T
    pump_hydraulic_efficiency: float = 0.70
    operating_days_per_year: int = 330
    heating_supply_temperature_c: float = 100.0
    cooling_supply_temperature_c: float = 20.0
    # Not a hackathon cap, but a practical well-engineering guard used by the agent:
    max_esp_power_kw: float = 1500.0          # typical large geothermal ESP envelope
    min_injection_temperature_c: float = 15.0  # avoid scaling / thermal shock on injection
    max_wellhead_pressure_bar: float = 60.0    # production wellhead envelope


@dataclass(frozen=True)
class HackathonSpec:
    reservoir: ReservoirSpec = field(default_factory=ReservoirSpec)
    brine: BrineSpec = field(default_factory=BrineSpec)
    constraints: Constraints = field(default_factory=Constraints)

    def to_dict(self) -> dict:
        return asdict(self)


SPEC = HackathonSpec()
