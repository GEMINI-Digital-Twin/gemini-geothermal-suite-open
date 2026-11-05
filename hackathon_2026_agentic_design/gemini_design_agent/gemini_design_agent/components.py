"""Complementary surface component models (heating and cooling plant).

GEMINI covers the subsurface and the well engineering; the hackathon asks participants to add
complementary component models for heating and cooling. These are deliberately simple,
transparent steady-state models so that every engineering decision can be explained.

Temperature convention: deg C.  Power: MW (thermal or electric).  Flow: m3/h.
"""

from __future__ import annotations

from dataclasses import dataclass

K0 = 273.15


# --------------------------------------------------------------------------------------------
# Brine thermal capacity
# --------------------------------------------------------------------------------------------
def brine_heat_capacity_mw_per_k(flow_m3_h: float, density: float = 1030.0, cp: float = 3900.0) -> float:
    """Thermal capacity rate of a brine stream, MW per K of cooling."""
    return flow_m3_h / 3600.0 * density * cp / 1e6


# --------------------------------------------------------------------------------------------
# Plate heat exchanger (direct heating)
# --------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class HeatExchanger:
    """Counter-flow brine / district-water plate heat exchanger."""

    approach_c: float = 3.0            # minimum terminal temperature difference
    effectiveness: float = 0.95        # fraction of the ideal duty actually transferred

    def direct_supply_possible(self, brine_in_c: float, supply_c: float) -> bool:
        return brine_in_c - self.approach_c >= supply_c

    def max_brine_outlet_c(self, district_return_c: float) -> float:
        """Brine cannot be cooled below the district return + approach."""
        return district_return_c + self.approach_c


# --------------------------------------------------------------------------------------------
# High-temperature heat pump (brine-source, lifts to the 100 C supply)
# --------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class HeatPump:
    """Water-source high-temperature heat pump (e.g. R1233zd / ammonia cascade).

    COP is modelled as a fraction of the Carnot COP between the condenser (supply + pinch)
    and the evaporator (mean brine temperature in the evaporator - pinch).
    """

    capacity_mw_th: float = 0.0        # rated heat output (MW)
    carnot_efficiency: float = 0.50    # second-law efficiency, typical 0.45-0.55 for HTHP
    condenser_pinch_c: float = 5.0
    evaporator_pinch_c: float = 5.0
    max_lift_c: float = 85.0           # single-stage/cascade limit on sink - source

    def cop(self, source_mean_c: float, sink_supply_c: float) -> float:
        t_cond = sink_supply_c + self.condenser_pinch_c + K0
        t_evap = source_mean_c - self.evaporator_pinch_c + K0
        lift = t_cond - t_evap
        if lift <= 0.0:
            return 10.0  # practically free (direct heat would be used instead)
        if lift > self.max_lift_c:
            return 0.0  # outside operating envelope
        cop = self.carnot_efficiency * t_cond / lift
        return float(min(cop, 8.0))

    def split(self, heat_out_mw: float, cop: float) -> tuple[float, float]:
        """Return (source heat drawn from brine, electrical power) for a heat output."""
        if cop <= 0.0:
            return 0.0, float("inf")
        w = heat_out_mw / cop
        return heat_out_mw - w, w


# --------------------------------------------------------------------------------------------
# Chillers
# --------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class AbsorptionChiller:
    """Single-effect LiBr/H2O absorption chiller driven by the geothermal brine.

    Thermal COP depends strongly on the driving (generator inlet) temperature. We use a
    piece-wise linear envelope: no operation below `min_driving_c`, full COP at or above
    `full_cop_driving_c`. Generator brine outlet is limited to `min_generator_outlet_c`.
    """

    capacity_mw_cool: float = 0.0
    cop_nominal: float = 0.72
    min_driving_c: float = 72.0
    full_cop_driving_c: float = 95.0
    min_generator_outlet_c: float = 68.0
    parasitic_el_fraction: float = 0.02      # pumps/controls, fraction of cooling
    cooling_tower_kw_per_mw_rejected: float = 25.0  # fans + condenser water pumps

    def cop(self, driving_c: float) -> float:
        if driving_c < self.min_driving_c:
            return 0.0
        if driving_c >= self.full_cop_driving_c:
            return self.cop_nominal
        f = (driving_c - self.min_driving_c) / (self.full_cop_driving_c - self.min_driving_c)
        return float(self.cop_nominal * (0.55 + 0.45 * f))

    def electricity_mw(self, cooling_mw: float, driving_heat_mw: float) -> float:
        rejected = cooling_mw + driving_heat_mw
        return cooling_mw * self.parasitic_el_fraction + rejected * self.cooling_tower_kw_per_mw_rejected / 1000.0


@dataclass(frozen=True)
class ElectricChiller:
    """Water-cooled electric (vapour compression) chiller as backup / alternative."""

    capacity_mw_cool: float = 0.0
    cop: float = 5.5                          # generous because 20 C supply is a mild duty
    cooling_tower_kw_per_mw_rejected: float = 25.0

    def electricity_mw(self, cooling_mw: float) -> float:
        w = cooling_mw / self.cop
        rejected = cooling_mw + w
        return w + rejected * self.cooling_tower_kw_per_mw_rejected / 1000.0


# --------------------------------------------------------------------------------------------
# Associated gas handling
# --------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class GasHandling:
    """Degasser + gas treatment for the associated CH4/CO2 at GLR 0.8 Nm3/m3."""

    glr_nm3_per_m3: float = 0.8
    ch4_frac: float = 0.80
    co2_frac: float = 0.20
    ch4_lhv_mj_per_nm3: float = 35.8
    co2_density_kg_per_nm3: float = 1.977
    ch4_density_kg_per_nm3: float = 0.717
    use_gas_engine: bool = False
    engine_electric_efficiency: float = 0.38

    def rates(self, liquid_flow_m3_h: float) -> dict:
        gas = self.glr_nm3_per_m3 * liquid_flow_m3_h
        ch4 = gas * self.ch4_frac
        co2 = gas * self.co2_frac
        fuel_mw = ch4 * self.ch4_lhv_mj_per_nm3 / 3600.0
        return {
            "gas_nm3_h": gas,
            "ch4_nm3_h": ch4,
            "co2_nm3_h": co2,
            "co2_kg_h": co2 * self.co2_density_kg_per_nm3,
            "ch4_kg_h": ch4 * self.ch4_density_kg_per_nm3,
            "ch4_fuel_mw_lhv": fuel_mw,
            "engine_electric_mw": fuel_mw * self.engine_electric_efficiency if self.use_gas_engine else 0.0,
        }


def bubble_point_estimate_bar(glr_nm3_per_m3: float, temperature_c: float, ch4_frac: float = 0.8) -> float:
    """Rough bubble-point pressure of brine carrying dissolved CH4/CO2 at the given GLR.

    Henry-type estimate: methane solubility in saline water ~ 0.02 Nm3/m3/bar at 80-100 C,
    CO2 ~ 0.6 Nm3/m3/bar. Returns the pressure needed to keep the full GLR in solution.
    This is only used as a wellbore-degassing guard for ESP intake placement.
    """
    ch4 = glr_nm3_per_m3 * ch4_frac
    co2 = glr_nm3_per_m3 * (1.0 - ch4_frac)
    # mild temperature dependence (solubility of CH4 slightly rises above 80 C; ignore)
    k_ch4 = 0.022
    k_co2 = 0.55
    return max(ch4 / k_ch4, co2 / k_co2)
