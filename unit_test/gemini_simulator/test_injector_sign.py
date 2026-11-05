"""Injection friction sign in the nodal solver, and the new registry entries."""

import pytest

from gemini_simulator import nodal_solver
from gemini_simulator.registry import create_component
from gemini_simulator.well_flow import _build_dpdt, solve_injector_wellhead_pressure_bar

TUBING_ID_M, ROUGHNESS_M = 0.1778, 4.5e-5
TRAJECTORY = [{"angle": 90.0, "depth": 100.0, "diameter": TUBING_ID_M}] * 25  # vertical, 2500 m


def test_injection_friction_lowers_bottomhole_pressure():
    """Injecting 300 m3/h down a vertical well: bottomhole pressure sits below the static column."""
    dpdt = _build_dpdt(TRAJECTORY, roughness=ROUGHNESS_M)
    p_bh = nodal_solver._well_bottomhole_pressure_injection(dpdt, 300 / 3600, 1e5, 50 + 273.15)
    p_static = 1e5 + dpdt.get_output()["pressuredrop_grav_output"]
    assert p_bh < p_static


def test_injector_wellhead_pressure_includes_friction():
    """300 m3/h into 250 bar at 10 m3/h/bar needs 47.25 bar at the wellhead, friction included.

    Friction in the tubing is 12.5 bar. With friction added (fixed sign) the wellhead needs
    47.25 bar; with friction subtracted (old sign) it needs 22.25 bar, so
    47.25 = 22.25 + 2 x 12.5 bar.
    """
    cfg = {
        "reservoir_pressure_bar": 250.0,
        "productivity_index_m3h_per_bar": 10.0,
        "roughness_m": ROUGHNESS_M,
        "welltrajectory": TRAJECTORY,
    }
    assert solve_injector_wellhead_pressure_bar(cfg, 300.0, 50.0) == pytest.approx(47.25, abs=0.05)


@pytest.mark.parametrize("name", ["esp_affinity", "heatpump", "heatpump_lift"])
def test_registry_entries(name):
    """The new component types resolve from the registry."""
    assert create_component(name) is not None
