"""Doublet well hydraulics built on GEMINI's own reservoir and well models.

For a given production flow rate (the controlled variable in a geothermal
doublet: the ESP speed is set to hit it) this module computes, using
``gemini_model.reservoir.inflow_performance.IPR`` and
``gemini_model.well.pressure_drop.DPDT``:

* producer bottomhole pressure, ESP intake/discharge pressure and the ESP's
  required pressure rise and electrical power (challenge rule: 70% hydraulic
  efficiency),
* wellhead temperature after heat loss up the well (GEMINI's U*A heat-loss
  correlation, evaluated per 100 m segment against the undisturbed geotherm),
* injector wellhead pressure needed to put the same volume back.

Two deliberate deviations from GEMINI defaults, both disclosed:

1. Fluid properties are set to the challenge brine (1,030 kg/m3, 0.40 mPa.s);
   GEMINI's ``PVTConstantSTP`` defaults to fresh water (1,000 kg/m3, 1 mPa.s).
2. Injection friction sign: ``DPDT`` with ``direction="down"`` always ADDS
   friction, which is right when walking down a producing well but wrong for
   fluid flowing down an injector (friction then opposes the flow and lowers
   the bottomhole pressure). Passing a negative flow rate makes DPDT's
   ``|u|*u`` friction term negative, which gives the physically correct sign
   (and the correct heat-exchange direction). See ``check_injection_sign``.
"""

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from gemini_model.fluid.pvt_water_stp import PVTConstantSTP
from gemini_model.reservoir.inflow_performance import IPR
from gemini_model.well.pressure_drop import DPDT

from agentic_design.config import (
    CHALLENGE,
    Assumptions,
    ambient_temperature_c,
    reservoir_pressure_bar,
    reservoir_temperature_c,
)

K0 = 273.15
MD_TO_M2 = 9.869233e-16


def brine_pvt(assumptions: Assumptions) -> PVTConstantSTP:
    pvt = PVTConstantSTP()
    pvt.update_parameters(
        {
            "RHOL": CHALLENGE["brine_density_kg_m3"],
            "VISL": CHALLENGE["brine_viscosity_pa_s"],
            "CPL": assumptions.brine_specific_heat_j_kgk,
            "GMF": 0.0,  # gas kept in solution in the wells (wellhead pressure set above bubble point)
            "temperature_max": 200 + K0,
        }
    )
    return pvt


def productivity_index_m3h_per_bar(a: Assumptions) -> float:
    """Steady-state radial Darcy inflow: PI = 2*pi*k*h / (mu * (ln(re/rw) - 0.75 + S))."""
    k = CHALLENGE["permeability_md"] * MD_TO_M2
    h = CHALLENGE["reservoir_gross_thickness_m"] * a.net_to_gross
    mu = CHALLENGE["brine_viscosity_pa_s"]
    denom = mu * (np.log(a.drainage_radius_m / a.wellbore_radius_m) - 0.75 + a.skin)
    pi_si = 2 * np.pi * k * h / denom  # m3/s per Pa
    return pi_si * 3600 * 1e5


@dataclass(frozen=True)
class WellDesign:
    """Geometry/operating choices for one doublet (both wells identical, vertical)."""

    depth_m: float = CHALLENGE["reservoir_midpoint_depth_m"]
    inner_diameter_m: float = 0.20
    esp_depth_m: float = 650.0

    def segments(self, a: Assumptions):
        """Vertical 100 m segments from surface to depth: list of (top, bottom)."""
        edges = set(np.arange(0.0, self.depth_m, a.segment_length_m).round(6))
        edges |= {round(float(self.esp_depth_m), 6), round(float(self.depth_m), 6)}
        edges = sorted(e for e in edges if 0.0 <= e <= self.depth_m)
        return list(zip(edges[:-1], edges[1:]))


def _segment_model(length_m, diameter_m, a: Assumptions) -> DPDT:
    w = DPDT()
    w.update_parameters(
        {
            "diameter": np.array([diameter_m]),
            "length": np.array([length_m]),
            "angle": np.array([np.pi / 2]),
            "roughness": np.array([a.casing_roughness_m]),
            "friction_correlation": "darcy_weisbach",
            "friction_correlation_2p": "BeggsBrill",
            "correction_factors": [1, 0],
            "heat_transfer_coefficient": a.well_heat_transfer_u_w_m2k,  # GEMINI issue 12: was hard-coded to 10
        }
    )
    w.PVT = brine_pvt(a)
    return w


def _walk(segments, p_start_bar, t_start_c, flow_m3s, direction, diameter_m, a):
    """Walk segment by segment with GEMINI DPDT, ambient = local geotherm.

    ``direction='up'``: start at the bottom of the deepest segment (production).
    ``direction='down'``: start at the top of the shallowest segment.
    Returns final pressure (bar), final temperature (C), min pressure seen (bar),
    friction (bar) and gravity (bar) totals.
    """
    order = segments[::-1] if direction == "up" else segments
    p, t = p_start_bar * 1e5, t_start_c + K0
    p_min = p
    fric = grav = 0.0
    for top, bottom in order:
        w = _segment_model(bottom - top, diameter_m, a)
        t_amb = float(ambient_temperature_c(0.5 * (top + bottom))) + K0
        w.calculate_output(
            {
                "pressure": p,
                "temperature": t,
                "temperature_ambient": t_amb,
                "flowrate": flow_m3s,
                "direction": direction,
            },
            None,
        )
        out = w.get_output()
        p, t = out["pressure_output"], out["temperature_output"]
        fric += out["pressuredrop_fric_output"]
        grav += out["pressuredrop_grav_output"]
        p_min = min(p_min, p)
    return p / 1e5, t - K0, p_min / 1e5, fric / 1e5, grav / 1e5


def producer(q_m3h: float, design: WellDesign, a: Assumptions) -> dict:
    """Producer + ESP at a fixed production rate (m3/h)."""
    q = q_m3h / 3600.0
    pi = productivity_index_m3h_per_bar(a)
    p_res = reservoir_pressure_bar(design.depth_m)
    t_res = reservoir_temperature_c(design.depth_m)

    ipr = IPR()
    ipr.update_parameters(
        {"type": "production_reservoir", "reservoir_pressure": p_res * 1e5, "productivity_index": pi / 3.6e8}
    )
    ipr.calculate_output({"flow": q}, None)
    p_bh = ipr.get_output()["bottomhole_pressure"] / 1e5

    segs = design.segments(a)
    below = [(t, b) for t, b in segs if t >= design.esp_depth_m]
    above = [(t, b) for t, b in segs if b <= design.esp_depth_m]
    if len(above) + len(below) != len(segs):
        raise ValueError("ESP depth must be inside the well (0 < esp_depth < depth).")

    # reservoir -> ESP intake
    p_in, t_in, pmin_b, fric_b, _ = _walk(below, p_bh, t_res, q, "up", design.inner_diameter_m, a)
    # wellhead -> ESP discharge (pressure needed to lift to the wellhead pressure)
    p_out, _, _, fric_t, _ = _walk(above, a.producer_wellhead_pressure_bar, t_in, q, "down",
                                   design.inner_diameter_m, a)
    dp_esp = max(0.0, p_out - p_in)
    rho_cp = CHALLENGE["brine_density_kg_m3"] * a.brine_specific_heat_j_kgk
    eff = CHALLENGE["pump_hydraulic_efficiency"]
    hydraulic_w = q * dp_esp * 1e5
    esp_power_w = hydraulic_w / eff
    # pump/motor losses end up in the brine (submersible motor is fluid-cooled)
    t_after_esp = t_in + (esp_power_w - hydraulic_w) / (q * rho_cp)
    # ESP -> wellhead temperature (pressure from this walk is a consistency check)
    p_wh_check, t_wh, _, _, _ = _walk(above, p_out, t_after_esp, q, "up", design.inner_diameter_m, a)

    return {
        "q_m3h": q_m3h,
        "reservoir_pressure_bar": p_res,
        "reservoir_temperature_c": t_res,
        "productivity_index_m3h_bar": pi,
        "bottomhole_pressure_bar": p_bh,
        "drawdown_bar": p_res - p_bh,
        "esp_intake_pressure_bar": p_in,
        "esp_discharge_pressure_bar": p_out,
        "esp_dp_bar": dp_esp,
        "esp_power_mw": esp_power_w / 1e6,
        "friction_bar": fric_b + fric_t,
        "wellhead_temperature_c": t_wh,
        "wellhead_pressure_bar": a.producer_wellhead_pressure_bar,
        "wellhead_pressure_check_bar": p_wh_check,
        "pressure_floor_hit": bool(pmin_b < 0.01),  # DPDT clamps at 0.001 Pa silently
    }


def injector(q_m3h: float, t_inj_c: float, design: WellDesign, a: Assumptions) -> dict:
    """Injector at a fixed injection rate: wellhead pressure needed (bar).

    Negative flow passed to DPDT -> friction correctly opposes downward flow.
    Pressure increments are independent of absolute pressure (constant-density
    PVT), so one walk from a reference wellhead pressure is exact.
    """
    q = q_m3h / 3600.0
    ii = productivity_index_m3h_per_bar(a)  # same reservoir, injectivity = productivity
    p_res = reservoir_pressure_bar(design.depth_m)
    ipr = IPR()
    ipr.update_parameters(
        {"type": "injection_reservoir", "reservoir_pressure": p_res * 1e5, "injectivity_index": ii / 3.6e8}
    )
    ipr.calculate_output({"flow": q}, None)
    p_bh_req = ipr.get_output()["bottomhole_pressure"] / 1e5

    p_ref = 100.0  # bar, avoids DPDT's pressure floor
    p_bot, t_bot, _, fric, grav = _walk(design.segments(a), p_ref, t_inj_c, -q, "down",
                                        design.inner_diameter_m, a)
    column_gain = p_bot - p_ref  # gravity minus friction
    p_wh_req = p_bh_req - column_gain
    return {
        "q_m3h": q_m3h,
        "required_bottomhole_pressure_bar": p_bh_req,
        "required_wellhead_pressure_bar": p_wh_req,
        "friction_bar": -fric,
        "gravity_bar": grav,
        "bottomhole_temperature_c": t_bot,
        "vacuum_risk": p_wh_req < 1.0,  # column alone over-delivers -> needs back-pressure/choke
    }


@lru_cache(maxsize=64)
def _curve_cached(design: WellDesign, a_items: tuple, t_inj_c: float, q_grid: tuple):
    a = Assumptions(**dict(a_items))
    rows = []
    for q in q_grid:
        p = producer(q, design, a)
        i = injector(q, t_inj_c, design, a)
        rows.append(
            (q, p["wellhead_temperature_c"], p["esp_power_mw"], p["esp_dp_bar"],
             p["esp_intake_pressure_bar"], p["bottomhole_pressure_bar"], i["required_wellhead_pressure_bar"],
             float(p["pressure_floor_hit"]))
        )
    return np.array(rows)


CURVE_COLUMNS = [
    "q_m3h", "wellhead_temperature_c", "esp_power_mw", "esp_dp_bar",
    "esp_intake_pressure_bar", "producer_bhp_bar", "injector_whp_required_bar", "pressure_floor_hit",
]


def hydraulic_curve(design: WellDesign, a: Assumptions, t_inj_c: float = 50.0, q_grid=None) -> dict:
    """Doublet performance vs flow, from the GEMINI models, for fast daily lookup."""
    if q_grid is None:
        q_grid = tuple(np.arange(10.0, CHALLENGE["max_flow_m3h_per_doublet"] + 0.1, 10.0))
    a_items = tuple(sorted((k, tuple(v) if isinstance(v, list) else v) for k, v in a.to_dict().items()))
    arr = _curve_cached(design, a_items, float(t_inj_c), tuple(q_grid))
    return {c: arr[:, j] for j, c in enumerate(CURVE_COLUMNS)}


def interp(curve: dict, key: str, q_m3h):
    if key == "wellhead_temperature_c":
        return interp_wellhead_temperature(curve, q_m3h)
    return np.interp(q_m3h, curve["q_m3h"], curve[key])


def interp_wellhead_temperature(curve: dict, q_m3h):
    """Heat lost on the way up scales roughly with 1/flow, so interpolate in 1/q, not q.

    Linear interpolation in q on a 10 m3/h grid was up to 0.11 degC off at 50-60 m3/h (found when
    GEMINI verification picked a low-flow day); in 1/q it is exact for a pure 1/q loss."""
    x = 1.0 / np.asarray(curve["q_m3h"], dtype=float)
    return np.interp(1.0 / np.asarray(q_m3h, dtype=float), x[::-1], np.asarray(curve["wellhead_temperature_c"])[::-1])


def check_injection_sign(design: WellDesign = WellDesign(), a: Assumptions = Assumptions(), q_m3h=300.0):
    """Show the friction-sign issue: GEMINI positive-flow vs corrected negative-flow walk."""
    q = q_m3h / 3600.0
    segs = design.segments(a)
    p_pos, *_ = _walk(segs, 100.0, 50.0, +q, "down", design.inner_diameter_m, a)
    p_neg, *_ = _walk(segs, 100.0, 50.0, -q, "down", design.inner_diameter_m, a)
    p_static, *_ = _walk(segs, 100.0, 50.0, 1e-9, "down", design.inner_diameter_m, a)
    return {
        "bhp_gemini_positive_flow_bar": p_pos,
        "bhp_corrected_negative_flow_bar": p_neg,
        "bhp_static_bar": p_static,
        "friction_bar": p_static - p_neg,
    }
