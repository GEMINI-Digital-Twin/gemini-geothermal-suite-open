"""Closed-loop geothermal management over the project life.

The design agent sizes the system for year 1. Real geothermal doublets drift: the cold
injected front eventually reaches the producer (thermal breakthrough), injectivity declines as
fines and scale build skin, and ESP efficiency erodes between workovers. This module closes the
loop between the digital twin and operations:

    observe (twin state: produced temperature, skin, ESP efficiency)
      -> re-simulate the annual dispatch with the GEMINI well models (``overrides``)
      -> detect constraint violations / KPI drift
      -> decide interventions (acid stimulation, ESP workover, heat-pump retrofit, re-spacing)
      -> apply and continue to the next year

The reservoir thermal model is the Gringarten-Sauty doublet breakthrough estimate with a
smooth post-breakthrough tail; it is lumped on purpose so the loop is transparent and fast.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict

import numpy as np

from .demand import DemandProfile
from .spec import HackathonSpec, SPEC
from .system import SystemDesign, evaluate_design


@dataclass
class ReservoirThermalModel:
    well_spacing_m: float = 1500.0
    porosity: float = 0.20
    rock_volumetric_heat_capacity_j_m3_k: float = 2.2e6
    thickness_m: float = 100.0

    def aquifer_heat_capacity(self, spec: HackathonSpec) -> float:
        rc_w = spec.brine.density_kg_m3 * spec.brine.specific_heat_j_kg_k
        return self.porosity * rc_w + (1 - self.porosity) * self.rock_volumetric_heat_capacity_j_m3_k

    def breakthrough_years(self, mean_flow_m3_h: float, spec: HackathonSpec) -> float:
        """Gringarten & Sauty (1975): t_b = pi L^2 h (rho c)_a / (3 Q (rho c)_w)."""
        if mean_flow_m3_h <= 0:
            return float("inf")
        q = mean_flow_m3_h / 3600.0
        rc_w = spec.brine.density_kg_m3 * spec.brine.specific_heat_j_kg_k
        t_b = math.pi * self.well_spacing_m ** 2 * self.thickness_m * self.aquifer_heat_capacity(spec) / (3 * q * rc_w)
        return t_b / (365.25 * 86400)

    def spacing_for_lifetime(self, mean_flow_m3_h: float, years: float, spec: HackathonSpec) -> float:
        q = mean_flow_m3_h / 3600.0
        rc_w = spec.brine.density_kg_m3 * spec.brine.specific_heat_j_kg_k
        t = years * 365.25 * 86400
        return math.sqrt(3 * q * rc_w * t / (math.pi * self.thickness_m * self.aquifer_heat_capacity(spec)))

    def produced_temperature(self, t_res: float, t_inj_mean: float, year: float, t_b_years: float) -> float:
        if year <= t_b_years:
            return t_res
        tau = max(0.5 * t_b_years, 1.0)
        return t_res - (t_res - t_inj_mean) * (1 - math.exp(-(year - t_b_years) / tau))


@dataclass
class YearRecord:
    year: int
    t_produced_c: float
    skin_injection_extra: float
    esp_efficiency_factor: float
    feasible: bool
    hard_violations: list[str]
    electricity_gwh: float
    system_cop: float
    unmet_heat_gwh: float
    unmet_cool_gwh: float
    injection_whp_bar: float
    esp_power_mw: float
    heat_pump_mw: float
    actions: list[str] = field(default_factory=list)
    intervention_cost_meur: float = 0.0


@dataclass
class ManagementPolicy:
    skin_growth_per_year: float = 0.6
    esp_efficiency_loss_per_year: float = 0.02
    esp_min_efficiency_factor: float = 0.90
    stimulate_when_whp_fraction: float = 0.85      # of the injection WHP limit
    stimulate_when_skin_extra: float = 3.0
    acid_job_cost_meur: float = 0.6
    esp_workover_cost_meur: float = 1.0
    heat_pump_retrofit_cost_meur_per_mw: float = 0.75
    electricity_eur_per_mwh: float = 120.0


class GeothermalManagementLoop:
    def __init__(self, design: SystemDesign, demand: DemandProfile, spec: HackathonSpec = SPEC,
                 years: int = 25, thermal: ReservoirThermalModel | None = None,
                 policy: ManagementPolicy | None = None, log=print):
        self.design = design
        self.demand = demand
        self.spec = spec
        self.years = years
        self.thermal = thermal or ReservoirThermalModel(thickness_m=spec.reservoir.gross_thickness_m)
        self.policy = policy or ManagementPolicy()
        self.log = log
        self.records: list[YearRecord] = []

    def run(self, year1_result=None) -> dict:
        p, ds = self.policy, self.design.copy()
        t_res0 = self.spec.reservoir.temperature_at_depth(ds.well.reservoir_midpoint_m)
        base = year1_result or evaluate_design(ds, self.demand, self.spec, fast=True)
        mean_flow = base.kpis["mean_flow_per_doublet_m3_h"]
        t_inj_mean = float(np.mean(base.daily["t_injection"]))
        t_b = self.thermal.breakthrough_years(mean_flow, self.spec)
        l_req = self.thermal.spacing_for_lifetime(mean_flow, self.years * 1.2, self.spec)
        self.log(f"[closed-loop] mean flow {mean_flow:.0f} m3/h/doublet, mean injection T {t_inj_mean:.0f} C, "
                 f"breakthrough at {self.thermal.well_spacing_m:.0f} m spacing after {t_b:.1f} yr; "
                 f"spacing for {self.years * 1.2:.0f} yr without breakthrough: {l_req:.0f} m")
        design_feedback = []
        if t_b < self.years:
            design_feedback.append(
                f"Thermal breakthrough predicted after {t_b:.1f} years at {self.thermal.well_spacing_m:.0f} m spacing; "
                f"increase producer-injector spacing to >= {l_req:.0f} m at reservoir level (1.2 x lifetime margin).")
        skin_extra, esp_eff = 0.0, 1.0
        year1_whp = base.kpis["injection_whp_at_300_bar"]
        total_interventions = 0.0
        for yr in range(1, self.years + 1):
            t_prod = self.thermal.produced_temperature(t_res0, t_inj_mean, yr, t_b)
            ov = {"t_res": round(t_prod, 2), "skin_injection_extra": round(skin_extra, 2),
                  "esp_efficiency_factor": round(esp_eff, 3)}
            res = evaluate_design(ds, self.demand, self.spec, overrides=ov, fast=True)
            actions, cost = [], 0.0
            k = res.kpis
            hard = [v.code for v in res.violations if v.severity == "hard"]
            # ---- controller decisions from twin feedback
            if (k["injection_whp_at_300_bar"] > p.stimulate_when_whp_fraction * self.spec.constraints.max_wellhead_pressure_bar
                    or skin_extra >= p.stimulate_when_skin_extra):
                actions.append(f"acid stimulation of injectors (skin +{skin_extra:.1f} -> 0; WHP {k['injection_whp_at_300_bar']:.0f} bar)")
                cost += p.acid_job_cost_meur * ds.n_doublets
                skin_extra = 0.0
            if esp_eff <= p.esp_min_efficiency_factor:
                actions.append(f"ESP workover / replacement (efficiency factor {esp_eff:.2f} -> 1.00)")
                cost += p.esp_workover_cost_meur * ds.n_doublets
                esp_eff = 1.0
            if k["unmet_heat_gwh"] > 0.01:
                add = math.ceil(max(res.daily["unmet_heat"]) * 1.1 * 2) / 2
                ds = ds.copy(heat_pump_mw=ds.heat_pump_mw + add)
                actions.append(f"heat-pump retrofit +{add:.1f} MW (produced T fell to {t_prod:.1f} C, "
                               f"{k['unmet_heat_gwh']:.2f} GWh heat unmet)")
                cost += p.heat_pump_retrofit_cost_meur_per_mw * add
            if k["unmet_cool_gwh"] > 0.01 and ds.electric_chiller_mw < self.demand.summary()["cooling_peak_mw"]:
                add = math.ceil(max(res.daily["unmet_cool"]) * 1.1 * 2) / 2
                ds = ds.copy(electric_chiller_mw=ds.electric_chiller_mw + add)
                actions.append(f"electric chiller retrofit +{add:.1f} MW (absorption driving temperature fell to {t_prod:.1f} C)")
                cost += 0.25 * add
            total_interventions += cost
            rec = YearRecord(yr, t_prod, ov["skin_injection_extra"], ov["esp_efficiency_factor"], res.feasible, hard,
                             k["electricity_gwh"], k["system_cop"], k["unmet_heat_gwh"], k["unmet_cool_gwh"],
                             k["injection_whp_at_300_bar"], k["esp_power_at_300_mw"], ds.heat_pump_mw, actions, cost)
            self.records.append(rec)
            self.log(f"[closed-loop] year {yr:2d}: Tprod {t_prod:6.1f} C  skin+{ov['skin_injection_extra']:.1f}  "
                     f"ESP eff {ov['esp_efficiency_factor']:.2f}  el {k['electricity_gwh']:5.1f} GWh  COP {k['system_cop']:5.1f}  "
                     f"feasible={res.feasible}  {'; '.join(actions) if actions else ''}")
            # ---- degradation to next year
            skin_extra += p.skin_growth_per_year
            esp_eff -= p.esp_efficiency_loss_per_year
        el = [r.electricity_gwh for r in self.records]
        return {
            "records": [asdict(r) for r in self.records],
            "breakthrough_years": t_b,
            "spacing_recommended_m": l_req,
            "spacing_sensitivity": [(sp, ReservoirThermalModel(sp, self.thermal.porosity,
                                                               self.thermal.rock_volumetric_heat_capacity_j_m3_k,
                                                               self.thermal.thickness_m).breakthrough_years(mean_flow, self.spec))
                                    for sp in (600.0, 800.0, 1000.0, 1200.0, 1500.0, 2000.0)],
            "design_feedback": design_feedback,
            "final_design": ds,
            "lifetime_electricity_gwh": float(sum(el)),
            "lifetime_electricity_cost_meur": float(sum(el)) * 1000 * p.electricity_eur_per_mwh / 1e6,
            "lifetime_intervention_cost_meur": total_interventions,
            "years_with_hard_violations": [r.year for r in self.records if r.hard_violations],
        }
