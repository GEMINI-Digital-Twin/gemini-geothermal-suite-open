"""Subsurface and doublet model built on GEMINI's own physics.

Layer A (resource assessment) and layer B (doublet) of the architecture.

What comes from GEMINI (``src/gemini_model`` and ``src/gemini_simulator``):
  * ``DPDT``   well pressure and temperature march (gravity, Darcy-Weisbach
               friction, heat loss to formation)
  * ``IPR``    linear reservoir inflow, used through GEMINI's injector solver
  * ``solve_injector_wellhead_pressure_bar``  injector nodal solve

What we add, and why (these are GEMINI gaps, see notes/gemini_gaps.md):
  * Reservoir temperature and pressure from depth (gap: not in GEMINI).
  * Productivity index from k, h, mu with Darcy radial flow (gap 6: PI is an
    input in GEMINI).
  * Wellhead temperature by marching GEMINI's DPDT *upward* from the
    reservoir, segment by segment, with the formation temperature of each
    segment as ambient (gap 1: wellhead T is a boundary input in GEMINI, and
    ambient is one constant).
  * Brine properties instead of GEMINI's pure-water constants (gap 2).
  * Pump power at a target flow from dP*Q/eta with the brief's 70%
    efficiency. GEMINI's example ESP curve gives negative head above
    ~270 m3/h at 65 Hz, so it cannot represent a 300 m3/h design (gap 10).
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
from gemini_model.well.pressure_drop import DPDT  # noqa: E402

G = 9.81
K0 = 273.15


# ---------------------------------------------------------------- brine PVT
def _brine_pvt_class(cfg):
    """PVTConstantSTP subclass carrying the hackathon brine constants."""

    class BrinePVT(PVTConstantSTP):
        def __init__(self):
            super().__init__()
            self.parameters.update(
                {"RHOL": cfg.rho, "VISL": cfg.mu, "CPL": cfg.cp, "temperature_max": 200 + K0}
            )

    return BrinePVT


@contextmanager
def brine_properties(cfg):
    """Make every GEMINI well model built inside this block use brine, not water.

    GEMINI creates ``PVTConstantSTP()`` internally (well_flow._build_dpdt and the
    registry's post-init hook), so we swap the class those modules look up.
    """
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
    """Fact-sheet pressure at the reference depth, hydrostatic gradient elsewhere."""
    return cfg.ref_pressure_bar + cfg.rho * G * (depth_m - cfg.ref_depth_m) / 1e5


def productivity_index_m3h_bar(cfg):
    """Darcy radial steady-state PI: 2*pi*k*h / (mu * (ln(re/rw) + S)).

    Steady state (constant-pressure outer boundary) suits a doublet, where the
    injector supports pressure. r_e = half the well spacing. Same value is used
    as the injectivity index.
    """
    re = cfg.well_spacing_m / 2
    rw = cfg.well_id_m / 2
    pi_si = 2 * math.pi * cfg.permeability_m2 * cfg.thickness_m / (
        cfg.mu * (math.log(re / rw) + cfg.skin)
    )  # m3/s per Pa
    return pi_si * 3600 * 1e5


def _vertical_dpdt(cfg, length_m, n_seg=1):
    w = DPDT()
    w.update_parameters(
        {
            "diameter": np.full(n_seg, cfg.well_id_m),
            "length": np.full(n_seg, length_m / n_seg),
            "angle": np.deg2rad(np.full(n_seg, 90.0)),
            "roughness": np.full(n_seg, 1e-4),
            "friction_correlation": "darcy_weisbach",
            "friction_correlation_2p": "BeggsBrill",
            "correction_factors": [1, 0],
        }
    )
    w.PVT = _brine_pvt_class(cfg)()
    return w


def wellhead_temperature_c(cfg, depth_m, flow_m3h, n_seg=25):
    """Brine temperature at the wellhead, marching GEMINI's DPDT upward.

    Each segment uses the undisturbed formation temperature at its midpoint
    as ambient. GEMINI's DPDT has a fixed U = 10 W/m2K; that is a steady,
    conservative heat loss (Ramey-type transient loss falls over years).
    """
    t = reservoir_temperature_c(cfg, depth_m)
    seg = depth_m / n_seg
    for i in range(n_seg):
        z_mid = depth_m - (i + 0.5) * seg
        w = _vertical_dpdt(cfg, seg)
        w.calculate_output(
            {
                "pressure": 400e5,  # high dummy pressure: properties are constant,
                "temperature": t + K0,  # so pressure does not affect the heat balance
                "temperature_ambient": reservoir_temperature_c(cfg, z_mid) + K0,
                "flowrate": flow_m3h / 3600,
                "direction": "up",
            },
            None,
        )
        t = w.get_output()["temperature_output"] - K0
    return t


# ------------------------------------------------------------------- doublet
def producer_hydraulics(cfg, depth_m, flow_m3h):
    """Pump duty to produce ``flow_m3h`` to the wellhead pressure.

    Bottomhole flowing pressure from the IPR, required bottomhole pressure
    from GEMINI's DPDT walked down from the wellhead (GEMINI's own nodal
    convention); the pump closes the gap.
    """
    p_res = reservoir_pressure_bar(cfg, depth_m)
    pi = productivity_index_m3h_bar(cfg)
    p_bh_reservoir = p_res - flow_m3h / pi
    w = _vertical_dpdt(cfg, depth_m)
    w.calculate_output(
        {
            "pressure": cfg.wellhead_pressure_bar * 1e5,
            "temperature": reservoir_temperature_c(cfg, depth_m) + K0,
            "temperature_ambient": reservoir_temperature_c(cfg, depth_m) + K0,
            "flowrate": flow_m3h / 3600,
            "direction": "down",
        },
        None,
    )
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


def _injector_wellhead_pressure_corrected_bar(cfg, depth_m, flow_m3h, injection_temp_c):
    """Injector wellhead pressure with friction acting against the downward flow.

    GEMINI's DPDT always adds friction when walking 'down'. That is right for
    a producer (walking against the flow) but wrong for an injector, where
    the walk follows the flow (gap 11: GEMINI understates the injector
    wellhead pressure by 2x friction). DarcyWeisbach uses |u|*u, so passing a
    negative flow rate gives friction the correct sign.
    """
    p_bh = reservoir_pressure_bar(cfg, depth_m) + flow_m3h / productivity_index_m3h_bar(cfg)
    w = _vertical_dpdt(cfg, depth_m)
    p0 = 100.0
    w.calculate_output(
        {
            "pressure": p0 * 1e5,
            "temperature": injection_temp_c + K0,
            "temperature_ambient": injection_temp_c + K0,
            "flowrate": -flow_m3h / 3600,
            "direction": "down",
        },
        None,
    )
    dp_down = w.get_output()["pressure_output"] / 1e5 - p0  # gravity - friction
    return p_bh - dp_down


def injector_hydraulics(cfg, depth_m, flow_m3h, injection_temp_c, surface_pressure_bar=None,
                        use_gemini_as_is=False):
    """Injector wellhead pressure and injection pump duty.

    Uses the friction-corrected injector by default and reports GEMINI's
    as-is value alongside it.
    """
    if surface_pressure_bar is None:
        surface_pressure_bar = max(1.0, cfg.wellhead_pressure_bar - 2.0)  # after surface losses
    inj_cfg = {
        "reservoir_pressure_bar": reservoir_pressure_bar(cfg, depth_m),
        "productivity_index_m3h_per_bar": productivity_index_m3h_bar(cfg),
        "trajectory_table": [
            {"MD": 0, "TVD": 0, "ID": cfg.well_id_m},
            {"MD": depth_m, "TVD": depth_m, "ID": cfg.well_id_m},
        ],
        "roughness_m": 1e-4,
    }
    with brine_properties(cfg):
        p_wh_gemini = gemini_well_flow.solve_injector_wellhead_pressure_bar(
            inj_cfg, flow_m3h, injection_temp_c, pressure_bracket_bar=(1e-3, 500.0)
        )
    p_wh_corr = _injector_wellhead_pressure_corrected_bar(cfg, depth_m, flow_m3h, injection_temp_c)
    p_wh = p_wh_gemini if use_gemini_as_is else p_wh_corr
    dp = max(0.0, p_wh - surface_pressure_bar)
    return {
        "injector_wellhead_pressure_gemini_as_is_bar": p_wh_gemini,
        "injector_wellhead_pressure_corrected_bar": p_wh_corr,
        "injector_wellhead_pressure_bar": p_wh,
        "injection_pump_dp_bar": dp,
        "injection_pump_power_mw": dp * 1e5 * flow_m3h / 3600 / cfg.pump_eff / 1e6,
    }


def doublet_performance(cfg, depth_m, flow_m3h, injection_temp_c=None):
    """One doublet at one operating point: temperatures, pumps, heat on offer.

    ``injection_temp_c`` defaults to the coldest the brief allows
    (wellhead T minus the 40 K cap).
    """
    t_wh = wellhead_temperature_c(cfg, depth_m, flow_m3h)
    if injection_temp_c is None:
        injection_temp_c = t_wh - cfg.dt_brine_max
    prod = producer_hydraulics(cfg, depth_m, flow_m3h)
    inj = injector_hydraulics(cfg, depth_m, flow_m3h, injection_temp_c)
    m_dot = cfg.rho * flow_m3h / 3600
    gas_nm3h = cfg.glr * cfg.gas_liberation_fraction * flow_m3h
    out = {
        "depth_m": depth_m,
        "flow_m3h": flow_m3h,
        "reservoir_temperature_c": reservoir_temperature_c(cfg, depth_m),
        "wellhead_temperature_c": t_wh,
        "injection_temperature_c": injection_temp_c,
        "brine_mass_flow_kg_s": m_dot,
        "heat_per_kelvin_mw_per_k": m_dot * cfg.cp / 1e6,
        "geothermal_heat_mw": m_dot * cfg.cp * (t_wh - injection_temp_c) / 1e6,
        "gas_nm3h": gas_nm3h,
        "gas_ch4_fuel_mw": gas_nm3h * cfg.x_ch4 * cfg.ch4_lhv_mj_nm3 / 3600,
        **prod,
        **inj,
    }
    out["total_pump_power_mw"] = out["pump_power_mw"] + out["injection_pump_power_mw"]
    return out


def thermal_breakthrough_years(cfg, spacing_m, flow_m3h):
    """Doublet thermal breakthrough time (Gringarten-type analytical estimate).

    t_b = pi * h * L^2 * (rho c)_reservoir / (3 * Q * (rho c)_brine).
    Homogeneous confined layer, no heat from cap/base rock (conservative).
    (rho c)_reservoir = (1 - phi) rho_grain c_grain + phi rho_brine c_brine.
    """
    if flow_m3h <= 0:
        return float("inf")
    rc_res = (1 - cfg.porosity) * cfg.rock_density * cfg.rock_cp + cfg.porosity * cfg.rho * cfg.cp
    rc_w = cfg.rho * cfg.cp
    t_s = math.pi * cfg.thickness_m * spacing_m ** 2 * rc_res / (3 * (flow_m3h / 3600) * rc_w)
    return t_s / (365.25 * 86400)


def gas_properties(cfg):
    """Associated-gas mixture: density and heating value per kg (gap 9).

    GEMINI's boiler/CHP default caloric_value is 50 MJ/kg (pure methane).
    With 20 mol% CO2 the mixture is much leaner.
    """
    rho_ch4, rho_co2 = 0.7175, 1.9768  # kg/Nm3 at 0 C, 1.01325 bar
    rho_mix = cfg.x_ch4 * rho_ch4 + cfg.x_co2 * rho_co2
    lhv_mj_kg = cfg.x_ch4 * cfg.ch4_lhv_mj_nm3 / rho_mix
    return {"density_kg_nm3": rho_mix, "lhv_mj_per_kg": lhv_mj_kg,
            "lhv_mj_per_nm3": cfg.x_ch4 * cfg.ch4_lhv_mj_nm3}
