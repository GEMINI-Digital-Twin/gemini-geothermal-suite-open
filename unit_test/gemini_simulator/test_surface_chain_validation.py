"""Validate the surface-chain portion of the doublet plant project.

Validates ``simulator_examples/projects/doublet_plant.json`` against
directly reimplemented forward-calculation formulas for the doublet-A
example plant configuration values that the JSON project file mirrors.
"""

import math
from pathlib import Path

from gemini_simulator.project_loader import load_project

PROJECT_PATH = (
    Path(__file__).resolve().parents[2] / "simulator_examples" / "projects" / "doublet_plant.json"
)

DOUBLET_A_CONFIG = {
    "Plant": {"T_s_in": 20, "Q_s": 140, "u": 80, "v": 80},
    "Separator": {"R1": 0.001, "dT": 1},
    "FilterA": {"R0": 0.01, "a": 0.005, "b": 1e-5, "dT": 1},
    "FilterB": {"R0": 0.001, "a": 0.005, "b": 1e-5, "dT": 1},
    "HeatExchanger": {"R1": 0, "type": "counter", "heat_transfer_coefficient": 250e3},
}

PRIMARY_FLOW_M3H = 140.0
SECONDARY_FLOW_M3H = 140.0
WELLHEAD_PRESSURE_BAR = 3.0
WELLHEAD_TEMPERATURE_C = 80.0


def _reference_separator_forward(pin, tin, q, cfg):
    """Independent forward-calculation formula for a separator's pressure/temperature drop."""
    pout = pin - q * cfg["R1"]
    tout = tin - cfg["dT"]
    return pout, tout


def _reference_filter_forward(pin, tin, q, cfg):
    """Independent forward-calculation formula for a filter's pressure/temperature drop."""
    r1 = cfg["a"] * (1 - math.exp(-cfg["b"] * q)) + cfg["R0"]
    pout = pin - q * r1
    tout = tin - cfg["dT"]
    return pout, tout


def _reference_heat_exchanger_forward_t(t_p_in, t_s_in, q_p, q_s, v, cfg):
    """Independent effectiveness-NTU forward-calculation formula for a heat exchanger."""
    rho = 1050
    cw = 4200
    v_frac = v / 100
    m_p = rho * q_p / 3600
    m_s = rho * q_s / 3600
    c_p = m_p * cw
    c_s = v_frac * m_s * cw
    c_max = max(c_p, c_s)
    c_min = min(c_p, c_s)
    ntu = cfg["heat_transfer_coefficient"] / c_min
    c_r = c_min / c_max
    h_max = c_min * abs(t_s_in - t_p_in)
    # Always take the counter-flow effectiveness branch, matching the
    # counter-flow configuration used in the project file.
    if c_r == 1:
        e = ntu / (1 + ntu)
    elif c_r < 0.01:
        e = 1 - math.exp(-ntu)
    else:
        e = (1 - math.exp(-ntu * (1 - c_r))) / (1 - c_r * math.exp(-ntu * (1 - c_r)))
    h = e * h_max
    t_p = t_p_in - h / cw / m_p
    t_s = t_s_in + h / cw / (v_frac * m_s)
    return t_p, t_s


def test_surface_chain_pressure_and_temperature_match_reference_formulas():
    """Surface-chain pressure/temperature outputs should match reference formulas."""
    solver = load_project(PROJECT_PATH)
    solver.run()

    # The producer well is wired into the same Solver graph (see
    # gemini_simulator.well_components.ProducerWell), so the primary
    # flow rate/wellhead pressure/temperature driving the surface chain
    # are whatever the well's own nodal solve produced -- read them back
    # from the solver rather than assuming fixed values, so this oracle
    # chains from the same actual boundary the solver used.
    primary_flow_m3h = solver.get_output("producer_well", "flow_rate")
    wellhead_pressure_bar = solver.get_output("producer_well", "pressure_out")
    wellhead_temperature_c = solver.get_output("producer_well", "temperature_out")

    # --- independent formula oracle, chained by hand ---
    p_sep_out, t_sep_out = _reference_separator_forward(
        wellhead_pressure_bar,
        wellhead_temperature_c,
        primary_flow_m3h,
        DOUBLET_A_CONFIG["Separator"],
    )
    p_filta_out, t_filta_out = _reference_filter_forward(
        p_sep_out, t_sep_out, primary_flow_m3h, DOUBLET_A_CONFIG["FilterA"]
    )
    p_hex_out = p_filta_out - primary_flow_m3h * DOUBLET_A_CONFIG["HeatExchanger"]["R1"]
    t_hex_p_out, t_hex_s_out = _reference_heat_exchanger_forward_t(
        t_filta_out,
        DOUBLET_A_CONFIG["Plant"]["T_s_in"],
        primary_flow_m3h,
        SECONDARY_FLOW_M3H,
        DOUBLET_A_CONFIG["Plant"]["v"],
        DOUBLET_A_CONFIG["HeatExchanger"],
    )
    p_filtb_out, t_filtb_out = _reference_filter_forward(
        p_hex_out, t_hex_p_out, primary_flow_m3h, DOUBLET_A_CONFIG["FilterB"]
    )

    assert solver.get_output("separator", "pressure_out") == pytest_approx(p_sep_out)
    assert solver.get_output("separator", "temperature_out") == pytest_approx(t_sep_out)
    assert solver.get_output("filter_a", "pressure_out") == pytest_approx(p_filta_out)
    assert solver.get_output("filter_a", "temperature_out") == pytest_approx(t_filta_out)
    assert solver.get_output("heat_exchanger", "pressure_out") == pytest_approx(p_hex_out)
    assert solver.get_output("heat_exchanger", "primary_temperature_out") == pytest_approx(
        t_hex_p_out
    )
    assert solver.get_output("heat_exchanger", "secondary_temperature_out") == pytest_approx(
        t_hex_s_out
    )
    assert solver.get_output("filter_b", "pressure_out") == pytest_approx(p_filtb_out)
    assert solver.get_output("filter_b", "temperature_out") == pytest_approx(t_filtb_out)


def pytest_approx(value):
    """Return a pytest.approx wrapper with a tight relative tolerance."""
    import pytest

    return pytest.approx(value, rel=1e-9)
