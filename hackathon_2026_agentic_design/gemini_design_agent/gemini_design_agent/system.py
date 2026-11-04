"""System-level design, daily dispatch, constraint checks and costing.

A ``SystemDesign`` holds every design variable the agent can change. ``evaluate_design`` runs
the 365-day power/energy balance: for each day it finds the minimum brine flow that meets the
heating and cooling demand with the available doublets (one doublet at a time can be in its
35-day maintenance window), evaluates the wells with the GEMINI models at that flow, and
records every constraint violation.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, asdict

import numpy as np

from .components import (AbsorptionChiller, ElectricChiller, GasHandling, HeatExchanger, HeatPump,
                         brine_heat_capacity_mw_per_k)
from .demand import DemandProfile
from .spec import HackathonSpec, SPEC
from .subsurface import DoubletModel, WellDesign


# ============================================================================================
# Design definition
# ============================================================================================
@dataclass
class SystemDesign:
    name: str = "design"
    n_doublets: int = 1
    well: WellDesign = field(default_factory=WellDesign)
    heat_pump_mw: float = 0.0              # HTHP rated output (0 = none)
    absorption_chiller_mw: float = 0.0     # brine-driven absorption chiller capacity
    electric_chiller_mw: float = 0.0       # electric chiller capacity
    district_return_c: float = 60.0        # heating network return temperature
    maintenance_start_days: list[int] = field(default_factory=list)  # per doublet, day index
    corrosion_mitigation: str = "inhibitor+GRE-lined tubing"
    rationale: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "SystemDesign":
        d = dict(d)
        well = d.pop("well", {})
        return cls(well=WellDesign(**well), **d)

    def copy(self, **changes) -> "SystemDesign":
        import copy as _c
        new = _c.deepcopy(self)
        for k, v in changes.items():
            if k.startswith("well."):
                setattr(new.well, k[5:], v)
            else:
                setattr(new, k, v)
        return new


# ============================================================================================
# Surface plant dispatch for one day
# ============================================================================================
@dataclass
class PlantState:
    heat_direct_mw: float = 0.0
    heat_hp_mw: float = 0.0
    hp_source_mw: float = 0.0
    hp_el_mw: float = 0.0
    hp_cop: float = 0.0
    cool_abs_mw: float = 0.0
    abs_driving_mw: float = 0.0
    abs_cop: float = 0.0
    cool_el_mw: float = 0.0
    chiller_el_mw: float = 0.0
    t_injection_c: float = 0.0
    brine_dt_c: float = 0.0
    unmet_heat_mw: float = 0.0
    unmet_cool_mw: float = 0.0
    geothermal_heat_extracted_mw: float = 0.0
    heating_fraction: float = 1.0


class Plant:
    def __init__(self, design: SystemDesign, spec: HackathonSpec = SPEC):
        self.ds = design
        self.spec = spec
        self.hx = HeatExchanger()
        self.hp = HeatPump(capacity_mw_th=design.heat_pump_mw)
        self.abs = AbsorptionChiller(capacity_mw_cool=design.absorption_chiller_mw)
        self.ech = ElectricChiller(capacity_mw_cool=design.electric_chiller_mw)
        self.gas = GasHandling(glr_nm3_per_m3=spec.brine.glr_nm3_per_m3, ch4_frac=spec.brine.ch4_mol_frac,
                               co2_frac=spec.brine.co2_mol_frac)

    def _heating_branch(self, q: float, t_wh: float, heat_demand: float, st: PlantState) -> float:
        """Direct plate HX then heat-pump evaporator in series. Returns branch outlet temperature."""
        c = self.spec.constraints
        cap = brine_heat_capacity_mw_per_k(q, self.spec.brine.density_kg_m3, self.spec.brine.specific_heat_j_kg_k)
        t = t_wh
        t_floor = max(t_wh - c.max_brine_cooling_c, c.min_injection_temperature_c)
        rem = heat_demand
        if q <= 0 or cap <= 0:
            st.unmet_heat_mw = rem
            return t_wh
        if rem > 0 and self.hx.direct_supply_possible(t, c.heating_supply_temperature_c):
            t_out_min = max(self.hx.max_brine_outlet_c(self.ds.district_return_c), t_floor)
            q_max = max(0.0, cap * (t - t_out_min) * self.hx.effectiveness)
            qd = min(rem, q_max)
            st.heat_direct_mw = qd
            t -= qd / cap
            rem -= qd
        if rem > 1e-9 and self.hp.capacity_mw_th > 0 and t > t_floor + 0.5:
            source_mean = 0.5 * (t + t_floor)
            cop = self.hp.cop(source_mean, c.heating_supply_temperature_c)
            if cop > 1.0:
                q_src_max = cap * (t - t_floor)
                heat_max = q_src_max * cop / (cop - 1.0)
                heat = min(rem, self.hp.capacity_mw_th, heat_max)
                q_src, w = self.hp.split(heat, cop)
                st.heat_hp_mw, st.hp_source_mw, st.hp_el_mw, st.hp_cop = heat, q_src, w, cop
                t -= q_src / cap
                rem -= heat
        st.unmet_heat_mw = max(0.0, rem)
        return t

    def _cooling_branch(self, q: float, t_wh: float, cool_demand: float, st: PlantState) -> float:
        """Absorption-chiller generator fed with wellhead-temperature brine. Returns outlet T."""
        c = self.spec.constraints
        cap = brine_heat_capacity_mw_per_k(q, self.spec.brine.density_kg_m3, self.spec.brine.specific_heat_j_kg_k)
        t = t_wh
        t_floor = max(t_wh - c.max_brine_cooling_c, c.min_injection_temperature_c)
        if q > 0 and cool_demand > 0 and self.abs.capacity_mw_cool > 0:
            cop = self.abs.cop(t)
            if cop > 0:
                t_out_min = max(self.abs.min_generator_outlet_c, t_floor)
                q_gen_max = max(0.0, cap * (t - t_out_min))
                cool = min(self.abs.capacity_mw_cool, q_gen_max * cop, cool_demand)
                q_gen = cool / cop
                st.cool_abs_mw, st.abs_driving_mw, st.abs_cop = cool, q_gen, cop
                t -= q_gen / cap
        rem = cool_demand - st.cool_abs_mw
        if rem > 1e-9 and self.ech.capacity_mw_cool > 0:
            st.cool_el_mw = min(rem, self.ech.capacity_mw_cool)
        st.unmet_cool_mw = max(0.0, cool_demand - st.cool_abs_mw - st.cool_el_mw)
        st.chiller_el_mw = (self.abs.electricity_mw(st.cool_abs_mw, st.abs_driving_mw)
                            + self.ech.electricity_mw(st.cool_el_mw))
        return t

    def dispatch_split(self, flow_total_m3_h: float, t_wh_c: float, heat_demand_mw: float,
                       cool_demand_mw: float, heating_fraction: float) -> PlantState:
        """Parallel plant topology: the brine is split between the heating train (direct HX +
        heat pump) and the cooling train (absorption generator), then re-mixed and injected."""
        st = PlantState()
        qh = flow_total_m3_h * heating_fraction
        qc = flow_total_m3_h - qh
        th = self._heating_branch(qh, t_wh_c, heat_demand_mw, st)
        tc = self._cooling_branch(qc, t_wh_c, cool_demand_mw, st)
        t_mix = (qh * th + qc * tc) / flow_total_m3_h if flow_total_m3_h > 0 else t_wh_c
        st.t_injection_c = t_mix
        st.brine_dt_c = t_wh_c - t_mix
        cap = brine_heat_capacity_mw_per_k(flow_total_m3_h, self.spec.brine.density_kg_m3,
                                           self.spec.brine.specific_heat_j_kg_k)
        st.geothermal_heat_extracted_mw = cap * st.brine_dt_c
        st.heating_fraction = heating_fraction
        return st

    def dispatch(self, flow_total_m3_h: float, t_wh_c: float, heat_demand_mw: float,
                 cool_demand_mw: float) -> PlantState:
        """Choose the brine split that minimises unmet demand (then minimises electricity)."""
        if cool_demand_mw <= 0 or self.abs.capacity_mw_cool <= 0:
            return self.dispatch_split(flow_total_m3_h, t_wh_c, heat_demand_mw, cool_demand_mw, 1.0)
        if heat_demand_mw <= 0:
            return self.dispatch_split(flow_total_m3_h, t_wh_c, heat_demand_mw, cool_demand_mw, 0.0)
        best = None
        for f in np.linspace(0.0, 1.0, getattr(self, 'split_points', 41)):
            st = self.dispatch_split(flow_total_m3_h, t_wh_c, heat_demand_mw, cool_demand_mw, float(f))
            key = (st.unmet_heat_mw + st.unmet_cool_mw, st.hp_el_mw + st.chiller_el_mw)
            if best is None or key < best[0]:
                best = (key, st)
        return best[1]


# ============================================================================================
# Evaluation result
# ============================================================================================
@dataclass
class Violation:
    code: str
    severity: str          # "hard" | "soft"
    message: str
    days: int = 0
    worst_value: float = 0.0


@dataclass
class EvaluationResult:
    design: SystemDesign
    feasible: bool
    violations: list[Violation]
    kpis: dict
    daily: dict                       # arrays for plotting
    well_points: list[dict]           # subsurface table at reference flows
    cost: dict

    def summary(self) -> dict:
        return {"name": self.design.name, "feasible": self.feasible,
                "violations": [v.__dict__ for v in self.violations], "kpis": self.kpis, "cost": self.cost}


# ============================================================================================
# Maintenance scheduling
# ============================================================================================
def schedule_maintenance(demand: DemandProfile, n_doublets: int, outage_days: int) -> list[int]:
    """Choose non-overlapping outage windows in the lowest-load period of the year.

    Load proxy = heating + cooling demand. Windows are placed greedily from the lowest-load
    window outward, never overlapping, so at most one doublet is down on any day.
    """
    load = demand.heating_mw + demand.cooling_mw
    n = len(load)
    cs = np.concatenate([[0.0], np.cumsum(load)])
    window = np.array([cs[i + outage_days] - cs[i] for i in range(n - outage_days + 1)])
    order = np.argsort(window)
    taken = np.zeros(n, dtype=bool)
    starts: list[int] = []
    for s in order:
        s = int(s)
        if taken[s:s + outage_days].any():
            continue
        starts.append(s)
        taken[s:s + outage_days] = True
        if len(starts) == n_doublets:
            break
    return sorted(starts)


# ============================================================================================
# Cost model (transparent assumptions, EUR)
# ============================================================================================
COST = {
    "well_fixed_eur": 1.5e6,
    "well_per_m_md_eur": 1800.0,
    "esp_eur_per_doublet": 0.9e6,
    "injection_pump_eur_per_doublet": 0.3e6,
    "surface_base_eur": 2.5e6,                 # degasser, filters, HX, gas treatment, civil
    "surface_eur_per_mw_th": 0.12e6,
    "heat_pump_eur_per_mw": 0.75e6,
    "absorption_eur_per_mw": 0.40e6,
    "electric_chiller_eur_per_mw": 0.25e6,
    "cooling_tower_eur_per_mw_rejected": 0.08e6,
    "electricity_eur_per_mwh": 120.0,
    "om_fraction_of_capex": 0.025,
    "discount_rate": 0.06,
    "lifetime_years": 25,
    "esp_workover_eur_per_year_per_doublet": 0.25e6,   # ESP run-life ~4-5 years
}


def crf(rate: float, years: int) -> float:
    return rate * (1 + rate) ** years / ((1 + rate) ** years - 1)


def cost_design(ds: SystemDesign, kpis: dict) -> dict:
    wells = 2 * ds.n_doublets
    capex_wells = wells * (COST["well_fixed_eur"] + COST["well_per_m_md_eur"] * ds.well.well_md_m)
    capex_pumps = ds.n_doublets * (COST["esp_eur_per_doublet"] + COST["injection_pump_eur_per_doublet"])
    peak_th = kpis["peak_geothermal_extraction_mw"]
    capex_surface = COST["surface_base_eur"] + COST["surface_eur_per_mw_th"] * peak_th
    capex_hp = COST["heat_pump_eur_per_mw"] * ds.heat_pump_mw
    rejected = ds.absorption_chiller_mw * (1 + 1 / 0.7) + ds.electric_chiller_mw * (1 + 1 / 5.5)
    capex_cool = (COST["absorption_eur_per_mw"] * ds.absorption_chiller_mw
                  + COST["electric_chiller_eur_per_mw"] * ds.electric_chiller_mw
                  + COST["cooling_tower_eur_per_mw_rejected"] * rejected)
    capex = capex_wells + capex_pumps + capex_surface + capex_hp + capex_cool
    annual_el = kpis["electricity_gwh"] * 1000 * COST["electricity_eur_per_mwh"]
    annual_om = COST["om_fraction_of_capex"] * capex + COST["esp_workover_eur_per_year_per_doublet"] * ds.n_doublets
    annuity = crf(COST["discount_rate"], COST["lifetime_years"]) * capex
    total_annual = annuity + annual_el + annual_om
    delivered_mwh = (kpis["heat_delivered_gwh"] + kpis["cool_delivered_gwh"]) * 1000
    return {
        "capex_wells_meur": capex_wells / 1e6, "capex_pumps_meur": capex_pumps / 1e6,
        "capex_surface_meur": capex_surface / 1e6, "capex_heat_pump_meur": capex_hp / 1e6,
        "capex_cooling_meur": capex_cool / 1e6, "capex_total_meur": capex / 1e6,
        "annual_electricity_meur": annual_el / 1e6, "annual_om_meur": annual_om / 1e6,
        "annualised_capex_meur": annuity / 1e6, "total_annual_cost_meur": total_annual / 1e6,
        "levelised_cost_eur_per_mwh": total_annual / delivered_mwh if delivered_mwh > 0 else float("inf"),
    }


# ============================================================================================
# Full evaluation
# ============================================================================================
_DM_CACHE: dict = {}


def get_doublet_model(ds: SystemDesign, spec: HackathonSpec, overrides: dict | None = None) -> DoubletModel:
    """Cache DoubletModel instances (the well evaluation is the expensive part)."""
    key = (json.dumps(asdict(ds.well), sort_keys=True), json.dumps(overrides or {}, sort_keys=True), id(spec))
    dm = _DM_CACHE.get(key)
    if dm is None:
        dm = DoubletModel(ds.well, spec, overrides=overrides)
        _DM_CACHE[key] = dm
    return dm


def evaluate_design(ds: SystemDesign, demand: DemandProfile, spec: HackathonSpec = SPEC,
                    overrides: dict | None = None, fast: bool = False, day_stride: int = 1) -> EvaluationResult:
    """Run the annual power / energy balance for a design.

    ``overrides`` feeds twin feedback from the closed-loop operations layer into the well model
    (e.g. ``{"t_res": 110.0, "skin_injection_extra": 3.0, "esp_efficiency_factor": 0.9}``).
    """
    c = spec.constraints
    n_days = demand.n_days
    outage = n_days - c.operating_days_per_year
    if not ds.maintenance_start_days or len(ds.maintenance_start_days) != ds.n_doublets:
        ds.maintenance_start_days = schedule_maintenance(demand, ds.n_doublets, outage)

    dm = get_doublet_model(ds, spec, overrides)
    plant = Plant(ds, spec)
    plant.split_points = 11 if fast else 41
    n_bisect = 9 if fast else 14
    viol: dict[str, Violation] = {}

    def add(code, severity, msg, value=0.0):
        v = viol.get(code)
        if v is None:
            viol[code] = Violation(code, severity, msg, days=1, worst_value=value)
        else:
            v.days += 1
            v.worst_value = max(v.worst_value, value)

    avail = np.full(n_days, ds.n_doublets, dtype=int)
    for s in ds.maintenance_start_days:
        avail[s:s + outage] -= 1

    cols = {k: np.zeros(n_days) for k in [
        "flow_per_doublet", "flow_total", "t_wellhead", "t_injection", "brine_dt", "heat_direct", "heat_hp",
        "hp_el", "cool_abs", "cool_el", "chiller_el", "esp_el", "inj_el", "total_el", "unmet_heat",
        "unmet_cool", "geo_extracted", "doublets_available", "esp_freq", "gas_nm3_h", "co2_kg_h"]}

    q_min, q_max = c.min_flow_m3_h_per_doublet, c.max_flow_m3_h_per_doublet

    last_i = None
    for i in range(n_days):
        if day_stride > 1 and i % day_stride != 0 and last_i is not None and avail[i] == avail[last_i]:
            # fast inner-loop mode: fill forward from the last simulated day
            for kk in cols:
                cols[kk][i] = cols[kk][last_i]
            continue
        last_i = i
        hd, cd, n_av = demand.heating_mw[i], demand.cooling_mw[i], int(avail[i])
        cols["doublets_available"][i] = n_av
        if n_av <= 0:
            add("no_doublet_available", "hard", "All doublets in maintenance simultaneously")
            cols["unmet_heat"][i], cols["unmet_cool"][i] = hd, cd
            continue

        def shortfall(q_per):
            wp = dm.evaluate(q_per)
            st = plant.dispatch(q_per * n_av, wp.wellhead_temperature_c, hd, cd)
            return st.unmet_heat_mw + st.unmet_cool_mw, wp, st

        # minimum flow that meets demand (monotone), bisection on per-doublet flow
        sf_max, wp, st = shortfall(q_max)
        if sf_max > 1e-6:
            q_per = q_max
        else:
            sf_min, wp_min, st_min = shortfall(q_min)
            if sf_min <= 1e-6:
                q_per, wp, st = q_min, wp_min, st_min
            else:
                lo, hi = q_min, q_max
                for _ in range(n_bisect):
                    mid = 0.5 * (lo + hi)
                    sf, wpm, stm = shortfall(mid)
                    if sf <= 1e-6:
                        hi, wp, st = mid, wpm, stm
                    else:
                        lo = mid
                q_per = hi
                sf, wp, st = shortfall(q_per)
        # re-evaluate the injector with the actual injection temperature
        wp = dm.evaluate(q_per, st.t_injection_c)

        # ---- record
        cols["flow_per_doublet"][i] = q_per
        cols["flow_total"][i] = q_per * n_av
        cols["t_wellhead"][i] = wp.wellhead_temperature_c
        cols["t_injection"][i] = st.t_injection_c
        cols["brine_dt"][i] = st.brine_dt_c
        cols["heat_direct"][i] = st.heat_direct_mw
        cols["heat_hp"][i] = st.heat_hp_mw
        cols["hp_el"][i] = st.hp_el_mw
        cols["cool_abs"][i] = st.cool_abs_mw
        cols["cool_el"][i] = st.cool_el_mw
        cols["chiller_el"][i] = st.chiller_el_mw
        cols["esp_el"][i] = wp.esp_power_mw * n_av
        cols["inj_el"][i] = wp.injection_pump_power_mw * n_av
        cols["total_el"][i] = cols["esp_el"][i] + cols["inj_el"][i] + st.hp_el_mw + st.chiller_el_mw
        cols["unmet_heat"][i] = st.unmet_heat_mw
        cols["unmet_cool"][i] = st.unmet_cool_mw
        cols["geo_extracted"][i] = st.geothermal_heat_extracted_mw
        cols["esp_freq"][i] = wp.esp_frequency_hz
        g = plant.gas.rates(q_per * n_av)
        cols["gas_nm3_h"][i] = g["gas_nm3_h"]
        cols["co2_kg_h"][i] = g["co2_kg_h"]

        # ---- constraint checks (hard caps from the challenge)
        if st.unmet_heat_mw > 1e-6:
            add("unmet_heating", "hard", "Heating demand not met at max flow / plant capacity", st.unmet_heat_mw)
        if st.unmet_cool_mw > 1e-6:
            add("unmet_cooling", "hard", "Cooling demand not met at max flow / chiller capacity", st.unmet_cool_mw)
        if q_per > q_max + 1e-6:
            add("flow_above_max", "hard", "Production flow above 300 m3/h per doublet", q_per)
        if q_per < q_min - 1e-6:
            add("flow_below_min", "hard", "Production flow below 50 m3/h per doublet", q_per)
        if st.brine_dt_c > c.max_brine_cooling_c + 1e-6:
            add("brine_cooling_above_max", "hard", "Brine cooled by more than 40 C", st.brine_dt_c)
        if st.t_injection_c < c.min_injection_temperature_c - 1e-6:
            add("injection_too_cold", "soft", "Injection temperature below practical minimum", st.t_injection_c)
        if wp.esp_intake_pressure_bar < wp.bubble_point_bar + 5.0:
            add("esp_intake_below_bubble_point", "hard",
                "ESP intake pressure within 5 bar of the gas bubble point - free gas at the pump",
                wp.bubble_point_bar + 5.0 - wp.esp_intake_pressure_bar)
        if wp.notes:
            add("esp_head_shortfall", "hard", "ESP stages cannot deliver the required head at 65 Hz")
        if wp.esp_power_mw * 1000 > c.max_esp_power_kw:
            add("esp_power_above_envelope", "soft", "ESP motor power above typical envelope", wp.esp_power_mw * 1000)
        if wp.injection_whp_bar > c.max_wellhead_pressure_bar:
            add("injection_whp_above_limit", "hard", "Injection wellhead pressure above limit", wp.injection_whp_bar)
        if wp.tubing_velocity_m_s > wp.erosional_velocity_m_s:
            add("erosional_velocity", "hard", "Tubing velocity above API RP14E erosional velocity", wp.tubing_velocity_m_s)
        bep_ratio = q_per / ds.well.esp_bep_m3_h
        if bep_ratio < 0.4 or bep_ratio > 1.35:
            add("esp_outside_operating_window", "soft",
                "ESP operating outside 40-135 % of BEP (below 40 % a recirculation line keeps the pump in its window)", bep_ratio)

    # ---- annual energy balance / KPIs
    h = 24.0 / 1000.0  # MW-day -> GWh
    heat_del = (cols["heat_direct"] + cols["heat_hp"]).sum() * h
    cool_del = (cols["cool_abs"] + cols["cool_el"]).sum() * h
    el = cols["total_el"].sum() * h
    geo = cols["geo_extracted"].sum() * h
    ref = dm.evaluate(300.0)
    if ref.corrosion_rate_mm_yr > 0.3 and "inhibitor" not in ds.corrosion_mitigation:
        viol["corrosion"] = Violation("corrosion", "soft",
                                      "Un-mitigated CO2 corrosion rate exceeds 0.3 mm/yr", 365, ref.corrosion_rate_mm_yr)
    kpis = {
        "heat_demand_gwh": demand.heating_gwh, "cool_demand_gwh": demand.cooling_gwh,
        "heat_delivered_gwh": heat_del, "cool_delivered_gwh": cool_del,
        "heat_direct_gwh": cols["heat_direct"].sum() * h, "heat_hp_gwh": cols["heat_hp"].sum() * h,
        "cool_abs_gwh": cols["cool_abs"].sum() * h, "cool_el_gwh": cols["cool_el"].sum() * h,
        "geothermal_heat_extracted_gwh": geo, "electricity_gwh": el,
        "electricity_esp_gwh": cols["esp_el"].sum() * h, "electricity_injection_gwh": cols["inj_el"].sum() * h,
        "electricity_heat_pump_gwh": cols["hp_el"].sum() * h, "electricity_chillers_gwh": cols["chiller_el"].sum() * h,
        "system_cop": (heat_del + cool_del) / el if el > 0 else float("inf"),
        # share of delivered energy that is not electricity (i.e. supplied by the geothermal brine)
        "geothermal_share": (heat_del + cool_del - el) / (heat_del + cool_del) if (heat_del + cool_del) > 0 else 0.0,
        "unmet_heat_gwh": cols["unmet_heat"].sum() * h, "unmet_cool_gwh": cols["unmet_cool"].sum() * h,
        "peak_flow_per_doublet_m3_h": float(cols["flow_per_doublet"].max()),
        "mean_flow_per_doublet_m3_h": float(cols["flow_per_doublet"][avail > 0].mean()),
        "days_at_max_flow": int((cols["flow_per_doublet"] >= q_max - 1e-6).sum()),
        "days_at_min_flow": int((cols["flow_per_doublet"] <= q_min + 1e-6).sum()),
        "peak_geothermal_extraction_mw": float(cols["geo_extracted"].max()),
        "peak_electricity_mw": float(cols["total_el"].max()),
        "max_brine_dt_c": float(cols["brine_dt"].max()),
        "min_injection_t_c": float(cols["t_injection"][avail > 0].min()),
        "annual_produced_volume_mm3": float(cols["flow_total"].sum() * 24 / 1e6),
        "annual_injected_volume_mm3": float(cols["flow_total"].sum() * 24 / 1e6),  # equal by design
        "annual_gas_mnm3": float(cols["gas_nm3_h"].sum() * 24 / 1e6),
        "annual_co2_t": float(cols["co2_kg_h"].sum() * 24 / 1000),
        "reservoir_temperature_c": dm.t_res, "reservoir_pressure_bar": dm.p_res,
        "wellhead_temperature_at_300_c": ref.wellhead_temperature_c,
        "productivity_index_m3_h_bar": ref.productivity_index_m3_h_bar,
        "injectivity_index_m3_h_bar": ref.injectivity_index_m3_h_bar,
        "esp_stages": ref.esp_stages, "esp_power_at_300_mw": ref.esp_power_mw,
        "esp_intake_pressure_at_300_bar": ref.esp_intake_pressure_bar, "bubble_point_bar": ref.bubble_point_bar,
        "injection_whp_at_300_bar": ref.injection_whp_bar,
        "corrosion_rate_unmitigated_mm_yr": ref.corrosion_rate_mm_yr,
        "tubing_velocity_at_300_m_s": ref.tubing_velocity_m_s, "erosional_velocity_m_s": ref.erosional_velocity_m_s,
        "maintenance_windows": [(str(demand.dates[s].date()), str(demand.dates[min(s + outage - 1, n_days - 1)].date()))
                                for s in ds.maintenance_start_days],
    }
    cost = cost_design(ds, kpis)
    violations = sorted(viol.values(), key=lambda v: (v.severity != "hard", -v.days))
    feasible = not any(v.severity == "hard" for v in violations)
    well_points = [{k: (float(v) if isinstance(v, (int, float, np.floating)) else v)
                    for k, v in wp.__dict__.items() if k != "notes"} for wp in dm.table()]
    daily = {k: v.tolist() for k, v in cols.items()}
    daily["date"] = [str(d.date()) for d in demand.dates]
    daily["heat_demand"] = demand.heating_mw.tolist()
    daily["cool_demand"] = demand.cooling_mw.tolist()
    return EvaluationResult(ds, feasible, violations, kpis, daily, well_points, cost)
