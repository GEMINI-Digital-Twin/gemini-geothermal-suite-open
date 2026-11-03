"""Subsurface and doublet model built on GEMINI's own physics.

Layer A (resource assessment) and layer B (doublet) of the architecture.

From GEMINI (``src/gemini_model``, ``src/gemini_simulator``):
  * ``bottomhole_skin_dp``  reservoir pressure drop, Darcy radial flow + skin
                            (reservoir/reservoir_pressuredrop.py)
  * ``DPDT``                well pressure and temperature march
  * ``solve_injector_wellhead_pressure_bar``  injector solve (reported as-is)

Added here because GEMINI lacks it (see notes/gemini_gaps.md):
  * T and P vs depth (fact sheet gradient; anchored hydrostatic pressure)
  * drainage radius r_e = well spacing L (DoubletCalc 1.4 manual, Eq. 7, p. 27)
  * wellhead temperature by marching DPDT upward (gap 1)
  * brine properties in GEMINI's well models (gap 2)
  * injector friction sign correction (gap 11)
  * pump power dP*Q/eta with the brief's 70% (gap 10)
  * thermal breakthrough time (Gringarten & Sauty 1975, as given by
    Wallmeier, Vardon & Daniilidis 2025, Eq. 9)
"""

import math
import sys
from contextlib import contextmanager

import numpy as np

from .config import REPO_ROOT

_SRC = str(REPO_ROOT / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import gemini_simulator.registry as gemini_registry  # noqa: E402
import gemini_simulator.well_flow as gemini_well_flow  # noqa: E402
from gemini_model.fluid.pvt_water_stp import PVTConstantSTP  # noqa: E402
from gemini_model.reservoir.reservoir_pressuredrop import bottomhole_skin_dp  # noqa: E402
from gemini_model.well.pressure_drop import DPDT  # noqa: E402

G = 9.81
K0 = 273.15


# ---------------------------------------------------------------- brine PVT
def _brine_pvt_class(cfg):
    """PVTConstantSTP subclass with the fact-sheet brine constants."""

    class BrinePVT(PVTConstantSTP):
        def __init__(self):
            super().__init__()
            self.parameters.update(
                {"RHOL": cfg.rho, "VISL": cfg.mu, "CPL": cfg.cp, "temperature_max": 200 + K0}
            )

    return BrinePVT


@contextmanager
def brine_properties(cfg):
    """Make GEMINI well models built inside this block use brine, not water."""
    brine = _brine_pvt_class(cfg)
    old_wf = gemini_well_flow.PVTConstantSTP
    old_hook = gemini_registry._POST_INIT_HOOKS.get("well")
    gemini_well_flow.PVTConstantSTP = brine
    gemini_registry._POST_INIT_HOOKS["well"] = lambda c: setattr(c, "PVT", brine())
    try:
        yield brine
    finally:
        gemini_well_flow.PVTConstantSTP = old_wf
        if old_hook is not None:
            gemini_registry._POST_INIT_HOOKS["well"] = old_hook


# ------------------------------------------------------- resource assessment
def reservoir_temperature_c(cfg, depth_m):
    """T_res = T_surface + gradient * depth (fact sheet)."""
    return cfg.surface_temp_c + cfg.gradient_c_per_m * depth_m


def reservoir_pressure_bar(cfg, depth_m):
    """Fact-sheet 250 bar at 2,500 m, hydrostatic gradient elsewhere (A3)."""
    return cfg.ref_pressure_bar + cfg.rho * G * (depth_m - cfg.ref_depth_m) / 1e5


def productivity_index_m3h_bar(cfg, spacing_m=None, skin=None):
    """PI from GEMINI's bottomhole_skin_dp with r_e = well spacing L.

    Steady-state radial Darcy flow with skin (pengtools; skin term as in
    Whitson): dP = Q mu [ln(L/r_w) + S] / (2 pi k h). L as drainage radius
    follows DoubletCalc 1.4 (TNO 2014), Eq. 7. Evaluated at a unit flow.
    """
    spacing_m = spacing_m or cfg.well_spacing_m
    skin = cfg.skin_producer if skin is None else skin
    m = bottomhole_skin_dp()
    m.update_parameters({
        "reservoir_pressure": 0.0, "reservoir_radius": spacing_m,
        "reservoir_permeability": cfg.permeability_m2, "reservoir_thickness": cfg.thickness_m,
        "reservoir_top": 0.0,
    })
    m.calculate_output({"flow": 1.0, "viscosity": cfg.mu, "density": cfg.rho,
                        "well_radius": cfg.well_id_m / 2, "skin_factor": skin}, None)
    o = m.get_output()
    dp_pa_per_m3s = o["bottomhole_dp"] + o["skin_dp"]
    return 1.0 / dp_pa_per_m3s * 3600 * 1e5  # m3/h per bar


def _vertical_dpdt(cfg, length_m, n_seg=1):
    w = DPDT()
    w.update_parameters({
        "diameter": np.full(n_seg, cfg.well_id_m),
        "length": np.full(n_seg, length_m / n_seg),
        "angle": np.deg2rad(np.full(n_seg, 90.0)),
        "roughness": np.full(n_seg, cfg.roughness_m),
        "friction_correlation": "darcy_weisbach",
        "friction_correlation_2p": "BeggsBrill",
        "correction_factors": [1, 0],
    })
    w.PVT = _brine_pvt_class(cfg)()
    return w


def wellhead_temperature_c(cfg, depth_m, flow_m3h, n_seg=25):
    """Brine temperature at the wellhead: GEMINI DPDT marched upward (gap 1).

    Each segment uses the formation temperature at its midpoint as ambient.
    GEMINI's DPDT heat-loss coefficient (U = 10 W/m2K) is used unchanged.
    """
    t = reservoir_temperature_c(cfg, depth_m)
    seg = depth_m / n_seg
    for i in range(n_seg):
        z_mid = depth_m - (i + 0.5) * seg
        w = _vertical_dpdt(cfg, seg)
        w.calculate_output({
            "pressure": 400e5,  # dummy: constant properties, pressure does not affect heat balance
            "temperature": t + K0,
            "temperature_ambient": reservoir_temperature_c(cfg, z_mid) + K0,
            "flowrate": flow_m3h / 3600,
            "direction": "up",
        }, None)
        t = w.get_output()["temperature_output"] - K0
    return t


# ------------------------------------------------------------------- doublet
def producer_hydraulics(cfg, depth_m, flow_m3h, spacing_m=None):
    """Pump duty to produce ``flow_m3h`` to the wellhead pressure."""
    p_res = reservoir_pressure_bar(cfg, depth_m)
    pi = productivity_index_m3h_bar(cfg, spacing_m, cfg.skin_producer)
    p_bh_reservoir = p_res - flow_m3h / pi
    w = _vertical_dpdt(cfg, depth_m)
    t_res = reservoir_temperature_c(cfg, depth_m) + K0
    w.calculate_output({"pressure": cfg.wellhead_pressure_bar * 1e5, "temperature": t_res,
                        "temperature_ambient": t_res, "flowrate": flow_m3h / 3600,
                        "direction": "down"}, None)
    p_bh_required = w.get_output()["pressure_output"] / 1e5
    dp_pump = max(0.0, p_bh_required - p_bh_reservoir)
    return {
        "reservoir_pressure_bar": p_res,
        "productivity_index_m3h_bar": pi,
        "drawdown_bar": flow_m3h / pi,
        "bottomhole_flowing_pressure_bar": p_bh_reservoir,
        "bottomhole_required_pressure_bar": p_bh_required,
        "pump_dp_bar": dp_pump,
        "pump_power_mw": dp_pump * 1e5 * flow_m3h / 3600 / cfg.pump_eff / 1e6,
    }


def _injector_wellhead_pressure_corrected_bar(cfg, depth_m, flow_m3h, injection_temp_c,
                                              spacing_m=None):
    """Injector WHP with friction against the downward flow (gap 11 correction).

    DarcyWeisbach uses |u|*u, so a negative flow gives friction the right sign.
    """
    ii = productivity_index_m3h_bar(cfg, spacing_m, cfg.skin_injector)
    p_bh = reservoir_pressure_bar(cfg, depth_m) + flow_m3h / ii
    w = _vertical_dpdt(cfg, depth_m)
    p0 = 100.0
    w.calculate_output({"pressure": p0 * 1e5, "temperature": injection_temp_c + K0,
                        "temperature_ambient": injection_temp_c + K0,
                        "flowrate": -flow_m3h / 3600, "direction": "down"}, None)
    dp_down = w.get_output()["pressure_output"] / 1e5 - p0  # gravity - friction
    return p_bh - dp_down


def injector_hydraulics(cfg, depth_m, flow_m3h, injection_temp_c, spacing_m=None,
                        use_gemini_as_is=False):
    """Injector wellhead pressure and injection pump duty.

    Surface pressure entering the injection pump = wellhead pressure minus
    the GEMINI template's surface loss (1.55 bar).
    """
    surface_p = cfg.wellhead_pressure_bar - cfg.surface_loss_bar
    ii = productivity_index_m3h_bar(cfg, spacing_m, cfg.skin_injector)
    inj_cfg = {
        "reservoir_pressure_bar": reservoir_pressure_bar(cfg, depth_m),
        "productivity_index_m3h_per_bar": ii,
        "trajectory_table": [{"MD": 0, "TVD": 0, "ID": cfg.well_id_m},
                             {"MD": depth_m, "TVD": depth_m, "ID": cfg.well_id_m}],
        "roughness_m": cfg.roughness_m,
    }
    with brine_properties(cfg):
        p_wh_gemini = gemini_well_flow.solve_injector_wellhead_pressure_bar(
            inj_cfg, flow_m3h, injection_temp_c, pressure_bracket_bar=(1e-3, 500.0))
    p_wh_corr = _injector_wellhead_pressure_corrected_bar(cfg, depth_m, flow_m3h,
                                                          injection_temp_c, spacing_m)
    p_wh = p_wh_gemini if use_gemini_as_is else p_wh_corr
    dp = max(0.0, p_wh - surface_p)
    return {
        "injectivity_index_m3h_bar": ii,
        "injector_wellhead_pressure_gemini_as_is_bar": p_wh_gemini,
        "injector_wellhead_pressure_corrected_bar": p_wh_corr,
        "injector_wellhead_pressure_bar": p_wh,
        "injection_pump_dp_bar": dp,
        "injection_pump_power_mw": dp * 1e5 * flow_m3h / 3600 / cfg.pump_eff / 1e6,
    }


def gas_properties(cfg):
    """Associated-gas mixture (gap 9): density and heating value.

    GEMINI's 50 MJ/kg is methane; with 20 mol% CO2 the mixture is leaner.
    """
    rho_mix = cfg.x_ch4 * cfg.ch4_density + cfg.x_co2 * cfg.co2_density
    lhv_nm3 = cfg.x_ch4 * cfg.ch4_lhv_mj_nm3
    return {"density_kg_nm3": rho_mix, "lhv_mj_per_nm3": lhv_nm3,
            "lhv_mj_per_kg": lhv_nm3 / rho_mix}


def doublet_performance(cfg, depth_m, flow_m3h, spacing_m=None, injection_temp_c=None):
    """One doublet at one operating point: temperatures, pumps, heat and gas."""
    spacing_m = spacing_m or cfg.well_spacing_m
    t_wh = wellhead_temperature_c(cfg, depth_m, flow_m3h)
    if injection_temp_c is None:
        injection_temp_c = t_wh - cfg.dt_brine_max
    prod = producer_hydraulics(cfg, depth_m, flow_m3h, spacing_m)
    inj = injector_hydraulics(cfg, depth_m, flow_m3h, injection_temp_c, spacing_m)
    m_dot = cfg.rho * flow_m3h / 3600
    gas_nm3h = cfg.glr * cfg.gas_liberation_fraction * flow_m3h
    out = {
        "depth_m": depth_m, "flow_m3h": flow_m3h, "spacing_m": spacing_m,
        "reservoir_temperature_c": reservoir_temperature_c(cfg, depth_m),
        "wellhead_temperature_c": t_wh,
        "injection_temperature_c": injection_temp_c,
        "brine_mass_flow_kg_s": m_dot,
        "heat_per_kelvin_mw_per_k": m_dot * cfg.cp / 1e6,
        "geothermal_heat_mw": m_dot * cfg.cp * (t_wh - injection_temp_c) / 1e6,
        "gas_nm3h": gas_nm3h,
        "gas_ch4_fuel_mw": gas_nm3h * cfg.x_ch4 * cfg.ch4_lhv_mj_nm3 / 3600,
        **prod, **inj,
    }
    out["total_pump_power_mw"] = out["pump_power_mw"] + out["injection_pump_power_mw"]
    return out


def thermal_breakthrough_years(cfg, spacing_m, flow_m3h):
    """Doublet thermal breakthrough time (Gringarten & Sauty 1975).

    t_b = pi * h * L^2 * (rho c)_res / (3 * Q * (rho c)_brine); confined
    homogeneous layer, no heat from confining layers (conservative), as stated
    by Wallmeier, Vardon & Daniilidis (2025), Eq. 9, p. 4-5.
    (rho c)_res = (1 - phi) rho_grain c_grain + phi rho_brine c_brine.
    """
    if flow_m3h <= 0:
        return float("inf")
    rc_res = (1 - cfg.porosity) * cfg.rock_density * cfg.rock_cp + cfg.porosity * cfg.rho * cfg.cp
    rc_w = cfg.rho * cfg.cp
    t_s = math.pi * cfg.thickness_m * spacing_m ** 2 * rc_res / (3 * (flow_m3h / 3600) * rc_w)
    return t_s / (365.25 * 86400)
