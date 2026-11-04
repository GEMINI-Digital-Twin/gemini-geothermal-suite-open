"""Subsurface and well-engineering evaluation built on the GEMINI digital-twin models.

Uses, directly from ``gemini_model`` (no Flask / Docker / databases required):

* ``reservoir.reservoir_pressuredrop.bottomhole_skin_dp`` - radial Darcy inflow / outflow
  (productivity and injectivity from permeability, thickness, radius, skin)
* ``reservoir.inflow_performance.IPR``                     - linear IPR / IIR
* ``well.pressure_drop.DPDT``                              - wellbore pressure & temperature
  (Darcy-Weisbach friction, gravity, heat loss to the formation)
* ``pump.esp.ESP``                                         - ESP head curve (stage / frequency)
* ``corrosion.co2_corrosion.CO2Corrosion``                 - CO2 corrosion rate of tubing
* ``erosion.erosion_model.ErosionModel``                   - API RP14E erosional velocity
* ``fluid.pvt_water_stp.PVTConstantSTP``                   - constant brine PVT

The DPDT model takes one ambient temperature for all segments, so the well is marched
segment by segment with the ambient temperature set from the geothermal gradient.
"""

from __future__ import annotations

import math
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

# make the GEMINI models importable
_HERE = Path(__file__).resolve().parent
# GEMINI source lookup: GEMINI_SRC env var, a sibling checkout, or (when this package lives
# inside the GEMINI repository) any parent directory holding src/gemini_model.
_cands = [Path(os.environ["GEMINI_SRC"])] if os.environ.get("GEMINI_SRC") else []
_cands += [_HERE.parent.parent / "gemini-geothermal-suite-open-main" / "src",
           _HERE.parent / "gemini-geothermal-suite-open-main" / "src"]
_cands += [anc / "src" for anc in _HERE.parents if (anc / "src" / "gemini_model").exists()]
for cand in _cands:
    if cand.exists() and str(cand) not in sys.path:
        sys.path.insert(0, str(cand))

from gemini_model.corrosion.co2_corrosion import CO2Corrosion  # noqa: E402
from gemini_model.erosion.erosion_model import ErosionModel  # noqa: E402
from gemini_model.fluid.pvt_water_stp import PVTConstantSTP  # noqa: E402
from gemini_model.pump.esp import ESP  # noqa: E402
from gemini_model.reservoir.inflow_performance import IPR  # noqa: E402
from gemini_model.reservoir.reservoir_pressuredrop import bottomhole_skin_dp  # noqa: E402
from gemini_model.well.pressure_drop import DPDT  # noqa: E402

from .components import bubble_point_estimate_bar  # noqa: E402
from .spec import HackathonSpec, SPEC  # noqa: E402

K0 = 273.15
MD_TO_M2 = 9.869233e-16
G = 9.80665

# HC27000-type ESP stage curve shipped with the GEMINI unit tests (Q in bbl/d, head ft, BHP)
ESP_HEAD_COEFF = [83.08389282, -0.000460444, -1.19e-07, 1.69e-11, -6.36e-16, 6.69e-21]
ESP_POWER_COEFF = [10.02089977, -0.000160233, 6.52e-08, -2.13e-12, 1.71e-17, 1.38e-23]

# Casing / tubing options (nominal OD -> ID in m)
WELL_ID_OPTIONS = {
    "7in": 0.1595,
    "9-5/8in": 0.2168,
    "10-3/4in": 0.2445,
}


@dataclass
class WellDesign:
    """Design variables for one doublet (producer and injector are mirror images)."""

    reservoir_midpoint_m: float = 2500.0
    production_id_m: float = 0.2168       # casing ID in which the ESP sits / tubing above
    injection_id_m: float = 0.2168
    esp_depth_m: float = 800.0
    esp_frequency_hz: float = 50.0        # nominal; VSD modulates 30-65 Hz
    esp_stages: int = 0                   # 0 -> sized automatically at the BEP flow
    esp_bep_m3_h: float = 220.0           # pump size: best-efficiency-point flow (affinity-scaled curve)
    skin_production: float = 0.0
    skin_injection: float = 2.0           # injectors usually pick up some damage / fines
    drainage_radius_m: float = 1000.0     # radius at which pressure = reservoir pressure
    wellbore_radius_m: float = 0.108      # 8.5 inch open hole
    surface_pressure_required_bar: float = 12.0  # keep gas in solution through the plant
    plant_pressure_drop_bar: float = 6.0  # degasser + filters + HX + piping
    roughness_m: float = 2.0e-5

    @property
    def well_md_m(self) -> float:
        # slightly deviated wells: MD ~ 1.08 x TVD to reach the reservoir target
        return self.reservoir_midpoint_m * 1.08


@dataclass
class WellPoint:
    """Hydraulic / thermal state of one doublet at a given flow."""

    flow_m3_h: float
    reservoir_temperature_c: float
    reservoir_pressure_bar: float
    productivity_index_m3_h_bar: float
    injectivity_index_m3_h_bar: float
    production_bhp_bar: float
    esp_intake_pressure_bar: float
    esp_intake_temperature_c: float
    esp_head_bar: float
    esp_frequency_hz: float
    esp_stages: int
    esp_power_mw: float
    wellhead_pressure_bar: float
    wellhead_temperature_c: float
    bubble_point_bar: float
    injection_bhp_required_bar: float
    injection_whp_bar: float
    injection_pump_power_mw: float
    injection_bottomhole_temperature_c: float
    tubing_velocity_m_s: float
    erosional_velocity_m_s: float
    corrosion_rate_mm_yr: float
    notes: list[str] = field(default_factory=list)


class DoubletModel:
    """Wraps the GEMINI models to evaluate a doublet at any flow rate."""

    def __init__(self, design: WellDesign, spec: HackathonSpec = SPEC, overrides: dict | None = None):
        """``overrides`` carries closed-loop twin feedback: ``t_res`` (C), ``skin_injection_extra``,
        ``skin_production_extra``, ``esp_efficiency_factor`` (1.0 = new pump)."""
        self.d = design
        self.spec = spec
        self.res = spec.reservoir
        self.brine = spec.brine
        ov = overrides or {}
        self.t_res = ov.get("t_res", self.res.temperature_at_depth(design.reservoir_midpoint_m))
        self.p_res = self.res.pressure_at_depth(design.reservoir_midpoint_m, self.brine.density_kg_m3)
        self.esp_eff_factor = ov.get("esp_efficiency_factor", 1.0)
        self._skin_extra = (ov.get("skin_production_extra", 0.0), ov.get("skin_injection_extra", 0.0))
        self.pvt = PVTConstantSTP()
        self.pvt.update_parameters({"RHOL": self.brine.density_kg_m3, "VISL": self.brine.viscosity_pa_s,
                                    "CPL": self.brine.specific_heat_j_kg_k})
        self._cache: dict[tuple, WellPoint] = {}
        self._pi = self._index(design.skin_production + self._skin_extra[0])
        self._ii = self._index(design.skin_injection + self._skin_extra[1])
        self._v_er = self._erosional_velocity()

    # ---------------------------------------------------------------- reservoir
    def _index(self, skin: float) -> float:
        """Productivity / injectivity index (m3/h/bar) from the GEMINI radial Darcy model."""
        m = bottomhole_skin_dp()
        m.update_parameters({
            "reservoir_pressure": self.p_res * 1e5,
            "reservoir_radius": self.d.drainage_radius_m,
            "reservoir_permeability": self.res.permeability_md * MD_TO_M2,
            "reservoir_thickness": self.res.gross_thickness_m,
            "reservoir_top": self.d.reservoir_midpoint_m - self.res.gross_thickness_m / 2,
        })
        q = 100.0 / 3600.0
        m.calculate_output({"flow": q, "viscosity": self.brine.viscosity_pa_s,
                            "density": self.brine.density_kg_m3,
                            "well_radius": self.d.wellbore_radius_m, "skin_factor": skin}, None)
        y = m.get_output()
        dp_pa = y["bottomhole_dp"] + y["skin_dp"]
        return 100.0 / (dp_pa / 1e5)

    def _bhp(self, kind: str, index: float, flow_m3_h: float) -> float:
        m = IPR()
        if kind == "production":
            m.update_parameters({"type": "production_reservoir", "reservoir_pressure": self.p_res,
                                 "productivity_index": index})
        else:
            m.update_parameters({"type": "injection_reservoir", "reservoir_pressure": self.p_res,
                                 "injectivity_index": index})
        m.calculate_output({"flow": flow_m3_h}, None)
        return float(m.get_output()["bottomhole_pressure"])

    # ---------------------------------------------------------------- wellbore
    def _march(self, p_bar: float, t_c: float, flow_m3_h: float, depth_from: float, depth_to: float,
               diameter: float, direction: str, step: float = 100.0) -> tuple[float, float, float]:
        """March the DPDT model segment-wise so ambient follows the geothermal gradient.

        Returns (pressure bar, temperature C, friction bar).
        """
        md_ratio = self.d.well_md_m / self.d.reservoir_midpoint_m
        angle = math.asin(1.0 / md_ratio)   # constant inclination equivalent
        n = max(1, int(round(abs(depth_to - depth_from) / step)))
        tvd_step = (depth_to - depth_from) / n
        p, t, fric = p_bar * 1e5, t_c + K0, 0.0
        q = flow_m3_h / 3600.0 if direction == "up" else -flow_m3_h / 3600.0
        w = DPDT()
        w.PVT = self.pvt
        for i in range(n):
            mid = depth_from + (i + 0.5) * tvd_step
            t_amb = self.res.temperature_at_depth(mid) + K0
            w.update_parameters({
                "length": np.array([abs(tvd_step) * md_ratio]),
                "diameter": np.array([diameter]),
                "angle": np.array([angle]),
                "roughness": np.array([self.d.roughness_m]),
                "friction_correlation": "darcy_weisbach",
                "friction_correlation_2p": "BeggsBrill",
                "correction_factors": [1, 0],
            })
            w.calculate_output({"pressure": p, "temperature": t, "flowrate": q,
                                "temperature_ambient": t_amb, "direction": direction}, None)
            y = w.get_output()
            p, t = y["pressure_output"], y["temperature_output"]
            fric += abs(y["pressuredrop_fric_output"])
        return p / 1e5, t - K0, fric / 1e5

    # ---------------------------------------------------------------- ESP
    ESP_REF_BEP_M3_H = 130.0  # BEP of the HC27000 reference curve (GEMINI example project)

    def _esp_head_bar(self, stages: int, freq: float, flow_m3_h: float) -> float:
        """Head of the GEMINI ESP curve, affinity-scaled to a pump of BEP ``esp_bep_m3_h``.

        A geometrically similar larger pump has the same head per stage at the same fraction
        of BEP flow, so the reference curve is evaluated at flow * (130 / BEP).
        """
        e = ESP()
        e.update_parameters({"pump_name": "HC27000-scaled", "no_stages": stages,
                             "head_coeff": ESP_HEAD_COEFF, "power_coeff": ESP_POWER_COEFF})
        q_eq = flow_m3_h * self.ESP_REF_BEP_M3_H / self.d.esp_bep_m3_h
        e.calculate_output({"pump_freq": freq, "pump_flow": q_eq / 3600.0})
        return max(0.0, float(e.get_output()["pump_head"]) / 1e5)

    def size_esp_stages(self, flow_m3_h: float, head_bar: float) -> int:
        per_stage = self._esp_head_bar(1, self.d.esp_frequency_hz, flow_m3_h)
        if per_stage <= 0:
            return 999
        return int(math.ceil(head_bar / per_stage * 1.10))  # 10 % design margin

    def required_head_bar(self, flow_m3_h: float) -> float:
        """ESP head needed at a flow to deliver the required surface pressure."""
        d = self.d
        bhp = self._bhp("production", self._pi, flow_m3_h)
        p_in, t_in, _ = self._march(bhp, self.t_res, flow_m3_h, d.reservoir_midpoint_m, d.esp_depth_m,
                                    d.production_id_m, "up")
        _, _, fric_up = self._march(max(p_in, 50.0), t_in, flow_m3_h, d.esp_depth_m, 0.0, d.production_id_m, "up")
        p_disc_req = d.surface_pressure_required_bar + self.brine.density_kg_m3 * G * d.esp_depth_m / 1e5 + fric_up
        return max(0.0, p_disc_req - p_in)

    # ---------------------------------------------------------------- integrity
    def _corrosion(self, p_bar: float, t_c: float) -> float:
        c = CO2Corrosion()
        c.update_parameters({"corrosion_model": "DLM"})
        c.calculate_output({"co2_fraction": self.brine.co2_mol_frac, "pressure": p_bar, "temperature": t_c}, None)
        return float(c.get_output()["corrosion_rate"])

    def _erosional_velocity(self) -> float:
        er = ErosionModel()
        er.update_parameters({"erosion_model": "API"})
        er.calculate_output({"rho_fluid": self.brine.density_kg_m3}, None)
        return float(er.get_output()["erosion_velocity_ms"])

    # ---------------------------------------------------------------- full evaluation
    def evaluate(self, flow_m3_h: float, t_injection_c: float = 45.0) -> WellPoint:
        key = (round(flow_m3_h, 2), round(t_injection_c, 0))
        if key in self._cache:
            return self._cache[key]
        d, notes = self.d, []
        pi, ii = self._pi, self._ii

        # --- producer: reservoir -> ESP intake
        bhp = self._bhp("production", pi, flow_m3_h)
        p_in, t_in, _ = self._march(bhp, self.t_res, flow_m3_h, d.reservoir_midpoint_m, d.esp_depth_m,
                                    d.production_id_m, "up")
        pb = bubble_point_estimate_bar(self.brine.glr_nm3_per_m3, t_in, self.brine.ch4_mol_frac)

        # --- ESP: discharge pressure needed = required WHP + hydrostatic + friction above the ESP
        _, _, fric_up = self._march(max(p_in, 50.0), t_in, flow_m3_h, d.esp_depth_m, 0.0, d.production_id_m, "up")
        p_disc_req = d.surface_pressure_required_bar + self.brine.density_kg_m3 * G * d.esp_depth_m / 1e5 + fric_up
        head_req = max(0.0, p_disc_req - p_in)
        # stages sized at the top of the pump frame's window (1.35 x BEP), capped at the 300 m3/h limit;
        # a day needing more flow than that raises an "esp_head_shortfall" violation for the agent
        q_design = min(self.spec.constraints.max_flow_m3_h_per_doublet, 1.35 * d.esp_bep_m3_h)
        stages = d.esp_stages or self.size_esp_stages(q_design, self.required_head_bar(q_design))
        # find the VSD frequency giving the required head at this flow
        lo, hi = 30.0, 65.0
        if self._esp_head_bar(stages, hi, flow_m3_h) < head_req:
            freq = hi
            notes.append("ESP cannot deliver required head at 65 Hz - stages undersized")
        else:
            for _ in range(40):
                mid = 0.5 * (lo + hi)
                if self._esp_head_bar(stages, mid, flow_m3_h) >= head_req:
                    hi = mid
                else:
                    lo = mid
            freq = hi
        head = self._esp_head_bar(stages, freq, flow_m3_h)
        p_wh, t_wh, _ = self._march(p_in + head, t_in, flow_m3_h, d.esp_depth_m, 0.0, d.production_id_m, "up")
        esp_power = (flow_m3_h / 3600.0 * head * 1e5 / self.spec.constraints.pump_hydraulic_efficiency
                     / self.esp_eff_factor / 1e6)

        # --- injector: surface -> reservoir
        p_after_plant = max(1.0, p_wh - d.plant_pressure_drop_bar)
        bhp_inj_req = self._bhp("injection", ii, flow_m3_h)
        # bisection on injection WHP so that bottomhole pressure matches the required injection BHP
        lo, hi = 0.0, 150.0
        for _ in range(30):
            mid = 0.5 * (lo + hi)
            p_bh, _, _ = self._march(mid, t_injection_c, flow_m3_h, 0.0, d.reservoir_midpoint_m,
                                     d.injection_id_m, "down")
            if p_bh >= bhp_inj_req:
                hi = mid
            else:
                lo = mid
        whp_inj = hi
        _, t_bh_inj, _ = self._march(whp_inj, t_injection_c, flow_m3_h, 0.0, d.reservoir_midpoint_m,
                                     d.injection_id_m, "down")
        dp_pump = max(0.0, whp_inj - p_after_plant)
        inj_power = flow_m3_h / 3600.0 * dp_pump * 1e5 / self.spec.constraints.pump_hydraulic_efficiency / 1e6

        # --- integrity
        area = math.pi * d.production_id_m ** 2 / 4
        vel = flow_m3_h / 3600.0 / area
        corr = self._corrosion(d.surface_pressure_required_bar, t_wh)

        wp = WellPoint(
            flow_m3_h=flow_m3_h, reservoir_temperature_c=self.t_res, reservoir_pressure_bar=self.p_res,
            productivity_index_m3_h_bar=pi, injectivity_index_m3_h_bar=ii, production_bhp_bar=bhp,
            esp_intake_pressure_bar=p_in, esp_intake_temperature_c=t_in, esp_head_bar=head,
            esp_frequency_hz=freq, esp_stages=stages, esp_power_mw=esp_power,
            wellhead_pressure_bar=p_wh, wellhead_temperature_c=t_wh, bubble_point_bar=pb,
            injection_bhp_required_bar=bhp_inj_req, injection_whp_bar=whp_inj,
            injection_pump_power_mw=inj_power, injection_bottomhole_temperature_c=t_bh_inj,
            tubing_velocity_m_s=vel, erosional_velocity_m_s=self._v_er, corrosion_rate_mm_yr=corr, notes=notes,
        )
        self._cache[key] = wp
        return wp

    def table(self, flows=(50, 100, 150, 200, 250, 300)) -> list[WellPoint]:
        return [self.evaluate(float(q)) for q in flows]
