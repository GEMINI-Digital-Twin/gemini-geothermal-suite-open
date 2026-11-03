"""Injector bottomhole pressure with the friction sign GEMINI's own DPDT test uses.

Why: DPDT takes a signed flow, dp_fric = f rho L/D |u| u / 2, and GEMINI's test_pressure_drop.py injects with
flowrate = -10/3600 and direction "down" (friction -6264.02 Pa). The simulator's injector call sites pass +q with
"down", so friction is added on the way down and the bottomhole pressure comes out too high. The fix is to hand
DPDT -q; the API keeps a positive injection rate, and the IPR still gets +q.

Drop-in versions of gemini_simulator.nodal_solver._well_bottomhole_pressure_injection,
nodal_solver.solve_injection_wellhead_pressure and well_flow.solve_injector_wellhead_pressure_bar,
same signatures. Upstream only the first needs a one-line change (PATCH.md); the other two inherit it.
"""
from scipy.optimize import brentq

from gemini_model.reservoir.inflow_performance import IPR
from gemini_simulator.nodal_solver import _reservoir_bottomhole_pressure
from gemini_simulator.well_flow import CELSIUS_TO_KELVIN, _build_dpdt, _resolve_trajectory_segments


def _well_bottomhole_pressure_injection(dpdt, flow_rate, wellhead_pressure, wellhead_temperature):
    """Bottomhole pressure (Pa) from injecting flow_rate (m3/s, positive) down the well."""
    u = {
        "pressure": wellhead_pressure,
        "temperature": wellhead_temperature,
        "temperature_ambient": wellhead_temperature,
        "flowrate": -flow_rate,  # signed: flow goes down, so friction opposes it
        "direction": "down",
    }
    dpdt.calculate_output(u, None)
    return dpdt.get_output()["pressure_output"]


def solve_injection_wellhead_pressure(ipr, dpdt, flow_rate, wellhead_temperature, pressure_bracket=(1e3, 1e8)):
    """Wellhead pressure (Pa) that injects flow_rate (m3/s); the bracket floor if gravity alone is enough."""
    p_reservoir = _reservoir_bottomhole_pressure(ipr, flow_rate)

    def residual(wellhead_pressure):
        return _well_bottomhole_pressure_injection(dpdt, flow_rate, wellhead_pressure, wellhead_temperature) - p_reservoir

    if residual(pressure_bracket[0]) >= 0:
        return pressure_bracket[0]
    return brentq(residual, pressure_bracket[0], pressure_bracket[1])


def solve_injector_wellhead_pressure_bar(injector_well_config, flow_m3h, wellhead_temperature_c,
                                         pressure_bracket_bar=(0.001, 500.0)):
    """Injector wellhead pressure (bar) for a known flow (m3/h), from an "injector_well" config dict."""
    ipr = IPR()
    ipr.update_parameters({
        "type": "injection_reservoir",
        "reservoir_pressure": injector_well_config["reservoir_pressure_bar"] * 1e5,
        "injectivity_index": injector_well_config["productivity_index_m3h_per_bar"] / 3.6e8,
    })
    dpdt = _build_dpdt(_resolve_trajectory_segments(injector_well_config),
                       roughness=injector_well_config.get("roughness_m", 0.01))
    p_pa = solve_injection_wellhead_pressure(
        ipr, dpdt, flow_rate=flow_m3h / 3600.0,
        wellhead_temperature=wellhead_temperature_c + CELSIUS_TO_KELVIN,
        pressure_bracket=(pressure_bracket_bar[0] * 1e5, pressure_bracket_bar[1] * 1e5))
    return p_pa / 1e5
