"""Daily plant dispatch and the annual (365-day) driver.

Brine cascade per day (hottest use first, identical doublets share flow equally):

    producer (ESP) -> [absorption chiller generator] -> [DH heat exchanger]
                   -> [heat pump evaporator] -> injector (pump)

District heating water: return T_r -> HEX -> heat pump condenser -> boiler -> 100 C.
Cooling: absorption chiller first (geothermal-driven), electric chiller for the rest.

Hard constraints enforced inside the dispatch: 50-300 m3/h per active doublet,
brine cooling <= 40 K (producer -> injector), production = injection volume.
Every component is a GEMINI model: ``HeatExchanger``, ``HeatpumpBasic`` (fixed
source-limited branch), ``AbsorptionChiller``/``ElectricChiller`` (new) and the
GEMINI-based doublet performance map (DPDT + IPR + injector nodal solve).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import brentq

from gemini_agent.physics.design import DesignSpec, load_economics
from gemini_agent.physics.site import Brief, Demand, gas_properties
from gemini_agent.physics.wells import WellSettings, doublet_map, thermal_breakthrough_years
from gemini_model.chiller import AbsorptionChiller, ElectricChiller
from gemini_model.heat_exchanger.heat_exchanger import HeatExchanger
from gemini_model.heatpump.heatpump_basic import HeatpumpBasic

MW = 1e6
UNMET_PENALTY_EUR_PER_MWH = 10_000.0


@dataclass
class DayResult:
    """One dispatched day (powers in MW, daily averages)."""

    n_on: int = 0
    flow_per_doublet_m3h: float = 0.0
    wellhead_t_c: float = float("nan")
    injection_t_c: float = float("nan")
    brine_dt_k: float = 0.0
    q_abs_cool: float = 0.0
    q_abs_gen: float = 0.0
    q_ech_cool: float = 0.0
    q_hex: float = 0.0
    q_hp: float = 0.0
    hp_el: float = 0.0
    hp_cop: float = float("nan")
    q_boiler: float = 0.0
    unmet_heat: float = 0.0
    unmet_cool: float = 0.0
    el_pumps: float = 0.0
    el_chillers: float = 0.0
    el_boiler: float = 0.0
    fuel_assoc_gas: float = 0.0  # MW LHV used in boiler
    fuel_grid_gas: float = 0.0  # MW LHV
    assoc_gas_flared: float = 0.0  # MW LHV
    co2_t: float = 0.0  # tonnes for the day
    cost_eur: float = 0.0  # operating cost incl. CO2 + unmet penalty

    @property
    def el_total(self) -> float:
        """Total electricity demand (MW)."""
        return self.el_pumps + self.el_chillers + self.hp_el + self.el_boiler


class PlantModel:
    """Plant built from a :class:`DesignSpec`; dispatches days and years."""

    def __init__(
        self,
        brief: Brief,
        spec: DesignSpec,
        econ: dict | None = None,
        flow_grid: int = 6,
        peak_heat_mw: float = 30.0,
    ):
        self.brief, self.spec = brief, spec
        self.peak_heat_mw = peak_heat_mw
        self.econ = (econ or load_economics())["values"]
        e = self.econ
        self.rho_b = brief.brine["density_kg_m3"]
        self.cp_b = brief.assumption("brine_specific_heat_j_per_kgk")
        self.rho_w = brief.assumption("network_water_density_kg_m3")
        self.cp_w = brief.assumption("network_water_specific_heat_j_per_kgk")
        self.max_dt = brief.constraints["max_brine_cooling_k"]
        self.qmin = brief.constraints["min_flow_m3h_per_doublet"]
        self.qmax = min(spec.max_flow_m3h, brief.constraints["max_flow_m3h_per_doublet"])
        self.gas = gas_properties(brief)
        self.reinject = spec.gas_handling == "keep_in_solution_reinject"
        whp = brief.assumption("min_wellhead_pressure_bar")
        if self.reinject:  # keep the loop above the gas bubble point
            whp = max(whp, e["gas_bubble_point_bar"])
        self.ws = WellSettings.from_brief(brief, min_wellhead_pressure_bar=whp)
        self.map = doublet_map(brief, spec.well_depth_m, 50.0, self.ws)
        self.flow_levels = list(np.linspace(self.qmin, self.qmax, flow_grid))

        self.hex = HeatExchanger()
        self.hex.update_parameters(
            {
                "flow_resistance": 0.0,
                "flow_configuration": "counter",
                "heat_transfer_coefficient": 1.0,
                "fluid_density": self.rho_b,
                "specific_heat": self.cp_b,
            }
        )
        self.ua_per_doublet = self._size_hex()

        self.hp = HeatpumpBasic()
        self.hp.update_parameters(
            {
                "mode": "lorenz",
                "eta_lorenz": e["heat_pump_eta_lorenz"],
                "Th_out_target": spec.heating_supply_temperature_c,
                "Cp_h": self.cp_w,
                "rho_h": self.rho_w,
                "Cp_s": self.cp_b,
                "rho_s": self.rho_b,
            }
        )
        self.abs = AbsorptionChiller()
        self.abs.update_parameters(
            {
                "nominal_cooling_capacity": spec.absorption_chiller_mw * MW,
                "hot_water_density": self.rho_b,
                "hot_water_specific_heat": self.cp_b,
            }
        )
        self.ech = ElectricChiller()
        self.ech.update_parameters({"nominal_cooling_capacity": spec.electric_chiller_mw * MW})

    # ------------------------------------------------------------------ sizing
    def _hex_run(self, ua, t_b_in, q_b_m3s, t_dh_in, m_dh_kg_s):
        """GEMINI HeatExchanger with the DH flow expressed as brine-equivalent flow."""
        self.hex.update_parameters({"heat_transfer_coefficient": max(ua, 1e-9)})
        q_dh_eq = m_dh_kg_s * self.cp_w / (self.rho_b * self.cp_b)
        self.hex.calculate_output(
            {
                "pressure_in": 10.0,
                "primary_flow_rate": q_b_m3s,
                "secondary_flow_rate": q_dh_eq,
                "primary_temperature_in": t_b_in,
                "secondary_temperature_in": t_dh_in,
            }
        )
        return self.hex.get_output()

    def _size_hex(self) -> float:
        """UA per doublet giving the design pinch (min terminal dT = approach) at peak.

        Design point: one doublet at maximum flow serving its share of the
        peak heating load. Works whichever side has the smaller heat-capacity
        flow (the pinch sits at the hot or the cold end accordingly).
        """
        s = self.spec
        t_wh = self.map.at(self.qmax)["wellhead_temperature_c"]
        t_r = s.dh_return_temperature_c
        m_dh = (
            max(self.peak_heat_mw, 1.0)
            * MW
            / (self.cp_w * (s.heating_supply_temperature_c - t_r))
            / s.n_doublets
        )
        q_b = self.qmax / 3600.0
        if t_wh <= t_r + s.hex_approach_k:
            return 1e3  # no useful direct exchange possible

        def pinch(ua):
            y = self._hex_run(ua, t_wh, q_b, t_r, m_dh)
            return min(t_wh - y["secondary_temperature_out"], y["primary_temperature_out"] - t_r)

        lo, hi = 1e3, 1e9
        if pinch(hi) > s.hex_approach_k:
            return hi
        return brentq(lambda ua: pinch(ua) - s.hex_approach_k, lo, hi, xtol=1e2)

    # --------------------------------------------------------------- one day
    def chain(
        self, heat_mw: float, cool_mw: float, n_on: int, f_m3h: float, cw_c: float | None = None
    ) -> DayResult:
        """Evaluate the cascade for ``n_on`` doublets at ``f_m3h`` each.

        ``cw_c`` is the day's cooling-tower water temperature (weather); defaults to the
        constant design assumption.
        """
        s, e = self.spec, self.econ
        cw = e["cooling_water_temperature_c"] if cw_c is None else cw_c
        r = DayResult(n_on=n_on, flow_per_doublet_m3h=f_m3h if n_on else 0.0)
        H, C = heat_mw * MW, cool_mw * MW
        t_sup = s.heating_supply_temperature_c
        t_r = s.dh_return_temperature_c

        if n_on > 0:
            perf = self.map.at(f_m3h)
            t_wh = perf["wellhead_temperature_c"]
            q_b = n_on * f_m3h / 3600.0  # m3/s total brine
            c_b = q_b * self.rho_b * self.cp_b  # W/K
            t_floor = t_wh - self.max_dt
            r.wellhead_t_c = t_wh
            r.el_pumps = n_on * self.map.pump_kw(f_m3h) / 1e3
            t_b = t_wh

            # (1) absorption chiller on the hottest brine
            if C > 0 and s.absorption_chiller_mw > 0:
                serve = C
                for _ in range(3):
                    self.abs.calculate_output(
                        {
                            "cooling_demand": serve,
                            "hot_water_temperature_in": t_b,
                            "hot_water_flow_rate": q_b,
                            "chilled_water_supply_temperature": s.cooling_supply_temperature_c,
                            "chilled_water_return_temperature": e["cooling_return_temperature_c"],
                            "cooling_water_temperature_in": cw,
                        }
                    )
                    ya = self.abs.get_output()
                    if (
                        ya["hot_water_temperature_out"] >= t_floor - 1e-6
                        or ya["generator_heat"] <= 0
                    ):
                        break
                    serve = (
                        ya["cooling_power"] * (c_b * (t_b - t_floor)) / ya["generator_heat"] * 0.999
                    )
                r.q_abs_cool = ya["cooling_power"] / MW
                r.q_abs_gen = ya["generator_heat"] / MW
                r.el_chillers += ya["power_el"] / MW
                t_b = ya["hot_water_temperature_out"]

            # (2) direct heat exchange to the DH return
            t_dh = t_r
            m_dh = H / (self.cp_w * (t_sup - t_r)) if H > 0 else 0.0
            if H > 0 and t_b > t_r:
                y = self._hex_run(self.ua_per_doublet * n_on, t_b, q_b, t_r, m_dh)
                q = y["heat_duty"]
                q = min(q, m_dh * self.cp_w * (t_sup - t_r))  # never overheat the DH water
                q = min(q, max(0.0, c_b * (t_b - t_floor)))  # brine 40 K cap
                r.q_hex = q / MW
                t_dh = t_r + q / (m_dh * self.cp_w)
                t_b = t_b - q / c_b

            # (3) heat pump: brine evaporator -> DH condenser (lift to supply temperature)
            if H > 0 and s.heat_pump_mw > 0 and t_dh < t_sup - 0.05 and t_b > t_floor + 0.05:
                self.hp.update_parameters({"Ts_in_minimum": t_floor})
                x = 1.0
                for _ in range(3):
                    self.hp.calculate_output(
                        {
                            "Th_in": t_dh,
                            "Ts_in": t_b,
                            "hot_flow_rate": x * m_dh / self.rho_w,
                            "source_flow_rate": q_b,
                        }
                    )
                    yh = self.hp.get_output()
                    if yh["Thermal_production"] <= s.heat_pump_mw * MW * 1.001:
                        break
                    x *= s.heat_pump_mw * MW / yh["Thermal_production"]
                q_hp = float(yh["Thermal_production"])
                r.q_hp, r.hp_el = q_hp / MW, float(yh["electrical_consumption"]) / MW
                r.hp_cop = float(yh["COP"])
                t_b = float(yh["Ts_out"])

            r.injection_t_c = t_b
            r.brine_dt_k = t_wh - t_b
            fuel_avail = 0.0 if self.reinject else q_b * self.gas.fuel_energy_mj_per_m3  # MW LHV
        else:
            fuel_avail = 0.0

        # (4) boiler closes the heat balance
        need = max(0.0, H / MW - r.q_hex - r.q_hp)
        r.q_boiler = min(need, s.backup_boiler_mw)
        r.unmet_heat = need - r.q_boiler
        if s.backup_fuel == "gas":
            fuel = r.q_boiler / e["boiler_efficiency_lhv"]
            r.fuel_assoc_gas = min(fuel, fuel_avail)
            r.fuel_grid_gas = fuel - r.fuel_assoc_gas
            r.assoc_gas_flared = fuel_avail - r.fuel_assoc_gas
        else:
            r.el_boiler = r.q_boiler / e["electric_boiler_efficiency"]
            r.assoc_gas_flared = fuel_avail

        # (5) electric chiller for the remaining cooling
        c_rem = max(0.0, cool_mw - r.q_abs_cool)
        if c_rem > 0 and s.electric_chiller_mw > 0:
            self.ech.calculate_output(
                {
                    "cooling_demand": c_rem * MW,
                    "chilled_water_supply_temperature": s.cooling_supply_temperature_c,
                    "cooling_water_temperature_in": cw,
                }
            )
            ye = self.ech.get_output()
            r.q_ech_cool = ye["cooling_power"] / MW
            r.el_chillers += ye["power_el"] / MW
        r.unmet_cool = max(0.0, c_rem - r.q_ech_cool)

        # (6) daily CO2 and cost
        hours = 24.0
        co2 = r.el_total * hours * e["electricity_kg_per_kwh"]  # MWh * kg/kWh = t
        co2 += r.fuel_grid_gas * hours * e["natural_gas_kg_per_kwh"]
        if n_on > 0 and not self.reinject:  # all liberated gas is combusted (boiler or flare)
            co2 += n_on * f_m3h * hours * self.gas.co2_if_burned_kg_per_m3 / 1000.0
        r.co2_t = co2
        r.cost_eur = (
            r.el_total * hours * e["electricity_eur_per_mwh"]
            + r.fuel_grid_gas * hours * e["natural_gas_eur_per_mwh"]
            + co2 * e["co2_eur_per_t"]
            + (r.unmet_heat + r.unmet_cool) * hours * UNMET_PENALTY_EUR_PER_MWH
        )
        return r

    def dispatch_day(
        self, heat_mw: float, cool_mw: float, n_avail: int, cw_c: float | None = None
    ) -> DayResult:
        """Cheapest feasible operating point (doublets on, flow) for one day."""
        best = self.chain(heat_mw, cool_mw, 0, 0.0, cw_c)
        for n_on in range(1, n_avail + 1):
            for f in self.flow_levels:
                r = self.chain(heat_mw, cool_mw, n_on, f, cw_c)
                if r.cost_eur < best.cost_eur - 1e-9:
                    best = r
        return best


# ------------------------------------------------------------------- annual
def maintenance_windows(
    spec: DesignSpec, demand: Demand, outage_days: int
) -> list[tuple[int, int]]:
    """Per-doublet outage windows [start, end). 'auto' = greedy, staggered, low-load season."""
    n = spec.n_doublets
    if spec.maintenance_start_days != "auto":
        return [(d, d + outage_days) for d in spec.maintenance_start_days]
    load = np.array(demand.heating_mw) + np.array(demand.cooling_mw) / (
        0.75 if spec.absorption_chiller_mw > 0 else 1e9
    )
    days = len(load)
    windows: list[tuple[int, int]] = []
    for _ in range(n):
        best, best_score = 0, np.inf
        for s in range(0, days - outage_days + 1):
            if any(not (s + outage_days <= a or s >= b) for a, b in windows):
                continue
            score = load[s : s + outage_days].sum()
            if score < best_score:
                best, best_score = s, score
        windows.append((best, best + outage_days))
    return windows


@dataclass
class AnnualResult:
    """Full-year simulation result."""

    spec: DesignSpec
    dates: list[str]
    heat_mw: list[float]
    cool_mw: list[float]
    days: list[DayResult]
    windows: list[tuple[int, int]]
    hex_ua_mw_per_k: float
    doublet_map: dict = field(default_factory=dict)

    def series(self, name: str) -> list[float]:
        """Per-day series of a DayResult attribute."""
        return [getattr(d, name) for d in self.days]

    def kpis(self) -> dict:
        """Annual KPIs (energies in GWh, CO2 in t)."""
        g = lambda name: float(sum(self.series(name))) * 24 / 1000  # noqa: E731
        heat, cool = sum(self.heat_mw) * 24 / 1000, sum(self.cool_mw) * 24 / 1000
        geo_heat = g("q_hex") + g("q_hp") - sum(d.hp_el for d in self.days) * 24 / 1000
        el = sum(d.el_total for d in self.days) * 24 / 1000
        hp_heat = g("q_hp")
        return {
            "heat_demand_gwh": round(heat, 3),
            "cool_demand_gwh": round(cool, 3),
            "heat_hex_gwh": round(g("q_hex"), 3),
            "heat_hp_gwh": round(hp_heat, 3),
            "heat_boiler_gwh": round(g("q_boiler"), 3),
            "cool_absorption_gwh": round(g("q_abs_cool"), 3),
            "cool_electric_gwh": round(g("q_ech_cool"), 3),
            "unmet_heat_mwh": round(sum(self.series("unmet_heat")) * 24, 3),
            "unmet_cool_mwh": round(sum(self.series("unmet_cool")) * 24, 3),
            "days_with_unmet": sum(1 for d in self.days if d.unmet_heat + d.unmet_cool > 1e-6),
            "geothermal_heat_gwh": round(geo_heat + g("q_abs_gen"), 3),
            "geothermal_share_of_heat_pct": (
                round(100 * (g("q_hex") + hp_heat) / heat, 2) if heat else 0
            ),
            "electricity_gwh": round(el, 3),
            "pump_electricity_gwh": round(g("el_pumps"), 3),
            "hp_spf": round(hp_heat / (g("hp_el") or float("nan")), 3) if hp_heat else None,
            "grid_gas_gwh": round(g("fuel_grid_gas"), 3),
            "assoc_gas_used_gwh": round(g("fuel_assoc_gas"), 3),
            "assoc_gas_flared_gwh": round(g("assoc_gas_flared"), 3),
            "co2_t": round(float(sum(self.series("co2_t"))), 1),
            "opex_energy_eur": round(sum(d.cost_eur for d in self.days if True), 0),
            "max_brine_dt_k": round(float(max(self.series("brine_dt_k"))), 3),
            "max_flow_m3h": round(max(self.series("flow_per_doublet_m3h")), 1),
            "doublet_operating_days": self.operating_days(),
            "hex_ua_mw_per_k_per_doublet": round(self.hex_ua_mw_per_k, 4),
        }

    def operating_days(self) -> list[int]:
        """Days each doublet is producing (doublets are switched on in index order)."""
        n = self.spec.n_doublets
        counts = [0] * n
        for i, d in enumerate(self.days):
            avail = [j for j in range(n) if not (self.windows[j][0] <= i < self.windows[j][1])]
            for j in avail[: d.n_on]:
                counts[j] += 1
        return counts


def simulate_year(
    brief: Brief,
    spec: DesignSpec,
    demand: Demand | None = None,
    econ: dict | None = None,
    flow_grid: int = 6,
    outage: dict | None = None,
    weather=None,
) -> AnnualResult:
    """Run the 365-day dispatch for a design.

    ``outage`` optionally forces extra unavailability, e.g.
    ``{"doublets": 1, "days": [27]}`` for an unplanned trip on the peak day.
    """
    demand = demand or brief.load_demand()
    plant = PlantModel(brief, spec, econ, flow_grid, peak_heat_mw=max(demand.heating_mw))
    outage_days = 365 - brief.constraints["geothermal_operating_days"]
    windows = maintenance_windows(spec, demand, outage_days)
    forced = outage or {}
    days = []
    cw_days = weather.cooling_water_c() if weather is not None else [None] * len(demand.heating_mw)
    for i, (h, c) in enumerate(zip(demand.heating_mw, demand.cooling_mw)):
        n_avail = sum(1 for a, b in windows if not (a <= i < b))
        if i in forced.get("days", []):
            n_avail = max(0, n_avail - forced.get("doublets", 1))
        days.append(plant.dispatch_day(h, c, n_avail, cw_days[i]))
    m = plant.map
    return AnnualResult(
        spec=spec,
        dates=demand.dates,
        heat_mw=demand.heating_mw,
        cool_mw=demand.cooling_mw,
        days=days,
        windows=windows,
        hex_ua_mw_per_k=plant.ua_per_doublet / MW,
        doublet_map={
            "flows_m3h": m.flows_m3h,
            "wellhead_temperature_c": [round(x, 2) for x in m.wellhead_temperature_c],
            "producer_pump_kw": [round(x, 1) for x in m.producer_pump_kw],
            "injector_pump_kw": [round(x, 1) for x in m.injector_pump_kw],
            "breakthrough_years_at_max_flow": round(
                thermal_breakthrough_years(brief, plant.qmax, plant.ws.spacing_m), 1
            ),
        },
    )
