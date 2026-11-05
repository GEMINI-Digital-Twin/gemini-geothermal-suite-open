"""Design-level well performance built on GEMINI's well and reservoir models.

For a candidate well depth and production rate this module answers the
questions the design agent needs, using GEMINI models only for the physics:

- ``DPDT`` (gemini_model.well.pressure_drop): friction + gravity pressure
  profile and wellbore heat loss,
- ``IPR`` (gemini_model.reservoir.inflow_performance): reservoir drawdown,
- ``solve_injection_wellhead_pressure`` (gemini_simulator.nodal_solver):
  injector nodal balance.

Pumps follow the brief's simplified model: electrical power = Q * dp / eta
with eta = 0.70 (hydraulic efficiency). The producer pump (ESP) supplies
whatever the reservoir + well column cannot deliver to reach the minimum
wellhead pressure; the injector pump supplies the wellhead pressure the
injector needs above the surface loop pressure.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from functools import lru_cache

import numpy as np

from gemini_agent.physics.site import Brief, reservoir_state
from gemini_model.reservoir.inflow_performance import IPR
from gemini_simulator.well_flow import (
    _build_dpdt,
    _trajectory_table_to_segments,
    solve_injector_wellhead_pressure_bar,
)

K = 273.15


@dataclass(frozen=True)
class WellSettings:
    """Well completion settings (defaults come from the brief's assumptions)."""

    tubing_id_m: float
    roughness_m: float
    spacing_m: float
    wellbore_radius_m: float
    skin: float
    min_wellhead_pressure_bar: float
    min_esp_intake_pressure_bar: float
    station_step_m: float = 100.0

    @classmethod
    def from_brief(cls, brief: Brief, **overrides) -> "WellSettings":
        """Settings from the brief's documented assumptions, with optional overrides."""
        base = dict(
            tubing_id_m=brief.assumption("well_tubing_inner_diameter_m"),
            roughness_m=brief.assumption("well_roughness_m"),
            spacing_m=brief.assumption("doublet_well_spacing_m"),
            wellbore_radius_m=brief.assumption("wellbore_radius_m"),
            skin=brief.assumption("skin"),
            min_wellhead_pressure_bar=brief.assumption("min_wellhead_pressure_bar"),
            min_esp_intake_pressure_bar=brief.assumption("min_esp_intake_pressure_bar"),
        )
        base.update(overrides)
        return cls(**base)


def gemini_well_config(brief: Brief, depth_m: float, ws: WellSettings) -> dict:
    """GEMINI ``producer_well``/``injector_well`` parameter dict for a vertical well.

    This is exactly the shape GEMINI's ``well_flow`` functions and the
    ``ProducerWell``/``InjectorWell`` simulator components expect, so the same
    dict is reused when compiling a full GEMINI project JSON.
    """
    rs = reservoir_state(
        brief,
        depth_m,
        well_spacing_m=ws.spacing_m,
        wellbore_radius_m=ws.wellbore_radius_m,
        skin=ws.skin,
    )
    n = max(1, int(math.ceil(depth_m / ws.station_step_m)))
    stations = [
        {"MD": round(depth_m * i / n, 3), "TVD": round(depth_m * i / n, 3), "ID": ws.tubing_id_m}
        for i in range(n + 1)
    ]
    return {
        "reservoir_pressure_bar": rs.pressure_bar,
        "productivity_index_m3h_per_bar": rs.productivity_index_m3h_per_bar,
        "trajectory_table": stations,
        "roughness_m": ws.roughness_m,
        "pvt": {"RHOL": brief.brine["density_kg_m3"], "VISL": brief.brine["viscosity_pa_s"]},
        "ambient_temperature_c": 0.5
        * (brief.reservoir["surface_temperature_c"] + rs.temperature_c),
    }


def _dpdt(cfg: dict):
    return _build_dpdt(
        _trajectory_table_to_segments(cfg["trajectory_table"]),
        roughness=cfg["roughness_m"],
        pvt_parameters=cfg["pvt"],
    )


@dataclass
class ProducerPoint:
    """Producer operating point at a fixed flow rate."""

    depth_m: float
    flow_m3h: float
    reservoir_temperature_c: float
    reservoir_pressure_bar: float
    productivity_index_m3h_per_bar: float
    bottomhole_pressure_bar: float  # flowing, from IPR
    drawdown_bar: float
    friction_loss_bar: float
    required_bottomhole_pressure_bar: float  # to lift Q to the min wellhead pressure
    pump_dp_bar: float
    pump_power_kw: float
    wellhead_temperature_c: float
    wellbore_heat_loss_k: float
    esp_setting_depth_m: float | None  # shallowest depth with intake >= min intake pressure
    feasible: bool
    note: str = ""

    def as_dict(self) -> dict:
        """Plain dict (rounded) for tools/ledger."""
        return {k: (round(v, 3) if isinstance(v, float) else v) for k, v in asdict(self).items()}


def producer_point(
    brief: Brief, depth_m: float, flow_m3h: float, ws: WellSettings | None = None
) -> ProducerPoint:
    """Producer + ESP operating point for a production rate (GEMINI DPDT + IPR)."""
    ws = ws or WellSettings.from_brief(brief)
    cfg = gemini_well_config(brief, depth_m, ws)
    q = flow_m3h / 3600.0
    t_res = (
        brief.reservoir["surface_temperature_c"]
        + brief.reservoir["geothermal_gradient_c_per_km"] * depth_m / 1000.0
    )
    eta = brief.constraints["pump_efficiency"]

    # Reservoir side (GEMINI IPR): flowing bottomhole pressure at rate q.
    ipr = IPR()
    ipr.update_parameters(
        {
            "type": "production_reservoir",
            "reservoir_pressure": cfg["reservoir_pressure_bar"] * 1e5,
            "productivity_index": cfg["productivity_index_m3h_per_bar"] / 3.6e8,
        }
    )
    ipr.calculate_output({"flow": q}, None)
    p_bh_res = ipr.get_output()["bottomhole_pressure"]

    # Well side (GEMINI DPDT), walked down from the minimum wellhead pressure:
    # bottomhole pressure needed to push q up to that wellhead pressure.
    down = _dpdt(cfg)
    down.calculate_output(
        {
            "pressure": ws.min_wellhead_pressure_bar * 1e5,
            "temperature": t_res + K,
            "temperature_ambient": t_res + K,  # no heat exchange in this hydraulic pass
            "flowrate": q,
            "direction": "down",
        },
        None,
    )
    p_bh_req = down.get_output()["pressure_output"]
    friction = down.get_output()["pressuredrop_fric_output"]
    pump_dp = max(0.0, p_bh_req - p_bh_res)

    # Thermal pass (GEMINI DPDT, upward) from reservoir temperature, heat loss to
    # the formation at the mean formation temperature.
    up = _dpdt(cfg)
    up.calculate_output(
        {
            "pressure": p_bh_res,
            "temperature": t_res + K,
            "temperature_ambient": cfg["ambient_temperature_c"] + K,
            "flowrate": q,
            "direction": "up",
        },
        None,
    )
    t_wh = up.get_output()["temperature_output"] - K

    # ESP setting depth: flowing pressure profile below the pump follows the
    # reservoir-side column; find the shallowest station with enough intake pressure.
    sec_p = np.array(up.get_output()["section_pressure_output"]) / 1e5  # bottom -> top
    stations_md = [s["MD"] for s in cfg["trajectory_table"]][1:][::-1]
    esp_depth = None
    for md, p in zip(stations_md, sec_p):
        if p >= ws.min_esp_intake_pressure_bar:
            esp_depth = md
        else:
            break

    feasible = p_bh_res > 0 and esp_depth is not None
    note = "" if feasible else "drawdown exceeds reservoir pressure or no valid ESP depth"
    return ProducerPoint(
        depth_m=depth_m,
        flow_m3h=flow_m3h,
        reservoir_temperature_c=t_res,
        reservoir_pressure_bar=cfg["reservoir_pressure_bar"],
        productivity_index_m3h_per_bar=cfg["productivity_index_m3h_per_bar"],
        bottomhole_pressure_bar=p_bh_res / 1e5,
        drawdown_bar=cfg["reservoir_pressure_bar"] - p_bh_res / 1e5,
        friction_loss_bar=friction / 1e5,
        required_bottomhole_pressure_bar=p_bh_req / 1e5,
        pump_dp_bar=pump_dp / 1e5,
        pump_power_kw=q * pump_dp / eta / 1e3,
        wellhead_temperature_c=t_wh,
        wellbore_heat_loss_k=t_res - t_wh,
        esp_setting_depth_m=esp_depth,
        feasible=feasible,
        note=note,
    )


@dataclass
class InjectorPoint:
    """Injector operating point at a fixed flow rate and injection temperature."""

    depth_m: float
    flow_m3h: float
    injection_temperature_c: float
    required_wellhead_pressure_bar: float
    surface_loop_pressure_bar: float
    pump_dp_bar: float
    pump_power_kw: float

    def as_dict(self) -> dict:
        """Plain dict (rounded) for tools/ledger."""
        return {k: (round(v, 3) if isinstance(v, float) else v) for k, v in asdict(self).items()}


def injector_point(
    brief: Brief,
    depth_m: float,
    flow_m3h: float,
    injection_temperature_c: float,
    ws: WellSettings | None = None,
) -> InjectorPoint:
    """Injector + injection pump operating point (GEMINI injector nodal solve)."""
    ws = ws or WellSettings.from_brief(brief)
    cfg = gemini_well_config(brief, depth_m, ws)
    p_wh = solve_injector_wellhead_pressure_bar(
        cfg, flow_m3h=flow_m3h, wellhead_temperature_c=injection_temperature_c
    )
    p_surface = ws.min_wellhead_pressure_bar
    dp = max(0.0, p_wh - p_surface)
    eta = brief.constraints["pump_efficiency"]
    return InjectorPoint(
        depth_m=depth_m,
        flow_m3h=flow_m3h,
        injection_temperature_c=injection_temperature_c,
        required_wellhead_pressure_bar=p_wh,
        surface_loop_pressure_bar=p_surface,
        pump_dp_bar=dp,
        pump_power_kw=flow_m3h / 3600.0 * dp * 1e5 / eta / 1e3,
    )


@dataclass
class DoubletMap:
    """Performance map of one doublet vs flow (screening fidelity).

    Built from GEMINI well runs on a flow grid; linear interpolation in between.
    """

    depth_m: float
    flows_m3h: list[float]
    wellhead_temperature_c: list[float]
    producer_pump_kw: list[float]
    injector_pump_kw: list[float]
    feasible: list[bool]

    def at(self, flow_m3h: float) -> dict:
        """Interpolated performance at ``flow_m3h``."""
        f = self.flows_m3h
        return {
            "wellhead_temperature_c": float(np.interp(flow_m3h, f, self.wellhead_temperature_c)),
            "producer_pump_kw": float(np.interp(flow_m3h, f, self.producer_pump_kw)),
            "injector_pump_kw": float(np.interp(flow_m3h, f, self.injector_pump_kw)),
        }

    def pump_kw(self, flow_m3h: float) -> float:
        """Total pumping power of the doublet (ESP + injection pump), kW."""
        p = self.at(flow_m3h)
        return p["producer_pump_kw"] + p["injector_pump_kw"]


@lru_cache(maxsize=256)
def _doublet_map_cached(brief_key: str, depth_m: float, inj_t_c: float, settings: WellSettings):
    brief = _BRIEFS[brief_key]
    flows = [50.0, 100.0, 150.0, 200.0, 250.0, 300.0]
    wht, pp, ip, ok = [], [], [], []
    for fl in flows:
        p = producer_point(brief, depth_m, fl, settings)
        i = injector_point(brief, depth_m, fl, inj_t_c, settings)
        wht.append(p.wellhead_temperature_c)
        pp.append(p.pump_power_kw)
        ip.append(i.pump_power_kw)
        ok.append(p.feasible)
    return DoubletMap(depth_m, flows, wht, pp, ip, ok)


_BRIEFS: dict[str, Brief] = {}


def _brief_key(brief: Brief) -> str:
    """Content hash of the brief (cache key; never object identity)."""
    return hashlib.sha1(json.dumps(brief.raw, sort_keys=True, default=str).encode()).hexdigest()


def doublet_map(
    brief: Brief,
    depth_m: float,
    injection_temperature_c: float = 50.0,
    ws: WellSettings | None = None,
) -> DoubletMap:
    """Cached GEMINI-based performance map for a doublet at ``depth_m``."""
    key = _brief_key(brief)
    _BRIEFS[key] = brief
    ws = ws or WellSettings.from_brief(brief)
    return _doublet_map_cached(key, float(depth_m), float(injection_temperature_c), ws)


def thermal_breakthrough_years(
    brief: Brief, flow_m3h: float, spacing_m: float, porosity: float = 0.2
) -> float:
    """Doublet thermal breakthrough time (Gringarten & Sauty 1975 / Lippmann & Tsang).

    t_b = pi * h * L^2 * (rho c)_a / (3 * Q * (rho c)_w), with the aquifer
    volumetric heat capacity (rho c)_a = phi (rho c)_w + (1 - phi) (rho c)_r.
    A model missing from GEMINI; used to check doublet spacing for lifetime.
    """
    h = brief.reservoir["gross_thickness_m"]
    rho_c_w = brief.brine["density_kg_m3"] * brief.assumption("brine_specific_heat_j_per_kgk")
    rho_c_rock = 2650.0 * 850.0
    rho_c_a = porosity * rho_c_w + (1 - porosity) * rho_c_rock
    q = flow_m3h / 3600.0
    t_s = math.pi * h * spacing_m**2 * rho_c_a / (3 * q * rho_c_w)
    return t_s / (365.25 * 86400)
