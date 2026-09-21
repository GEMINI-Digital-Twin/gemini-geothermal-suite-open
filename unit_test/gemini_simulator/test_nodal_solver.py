"""Unit tests for gemini_simulator.nodal_solver.

Uses the same well parameterization conventions as
unit_test/gemini_model/well/test_pressure_drop.py (single vertical DPDT
segment) combined with a simple IPR reservoir, in consistent SI units
(Pa, K, m3/s), to verify the nodal (production/injection flow-rate)
solver converges to a flow rate where the well-side and reservoir-side
bottomhole pressures match.
"""

import numpy as np

from gemini_model.fluid.pvt_water_stp import PVTConstantSTP
from gemini_model.pump.esp import ESP
from gemini_model.reservoir.inflow_performance import IPR
from gemini_model.well.pressure_drop import DPDT
from gemini_simulator.nodal_solver import (
    solve_injection_flow_rate,
    solve_production_flow_rate,
)


def _make_well(diameter_in=8.535, length=2200):
    well_param = {
        "diameter": np.array([diameter_in * 0.0254]),
        "length": np.array([length]),
        "angle": np.array([90 * np.pi / 180]),
        "roughness": np.array([0.01e-3]),
        "friction_correlation": "darcy_weisbach",
        "friction_correlation_2p": "BeggsBrill",
        "correction_factors": [1, 0],
    }
    well = DPDT()
    well.update_parameters(well_param)
    well.PVT = PVTConstantSTP()
    return well


def _make_esp():
    esp = ESP()
    esp.update_parameters(
        {
            "pump_name": "HC27000",
            "no_stages": 12,
            "head_coeff": [
                83.08389282,
                -0.000460444,
                -1.19e-07,
                1.69e-11,
                -6.36e-16,
                6.69e-21,
            ],
            "power_coeff": [
                10.02089977,
                -0.000160233,
                6.52e-08,
                -2.13e-12,
                1.71e-17,
                1.38e-23,
            ],
        }
    )
    return esp


def _make_ipr(reservoir_type, reservoir_pressure_pa, index_value):
    ipr = IPR()
    params = {"reservoir_pressure": reservoir_pressure_pa, "type": reservoir_type}
    if reservoir_type == "production_reservoir":
        params["productivity_index"] = index_value
    else:
        params["injectivity_index"] = index_value
    ipr.update_parameters(params)
    return ipr


def test_solve_production_flow_rate_balances_pressures():
    """Solved production flow rate should balance well/reservoir pressures."""
    well = _make_well()
    # productivity_index in (m3/s)/Pa, chosen so a physically reasonable flow
    # rate solution exists between the reservoir pressure and a lower
    # wellhead pressure.
    ipr = _make_ipr("production_reservoir", reservoir_pressure_pa=250e5, index_value=5e-8)

    flow_rate = solve_production_flow_rate(
        ipr,
        well,
        wellhead_pressure=10e5,
        wellhead_temperature=80 + 273.15,
        ambient_temperature=20 + 273.15,
        flow_bracket=(1e-6, 0.1),
    )

    assert 0 < flow_rate < 0.1

    # residual should be ~0 at the solved flow rate
    well.calculate_output(
        {
            "pressure": 10e5,
            "temperature": 80 + 273.15,
            "temperature_ambient": 20 + 273.15,
            "flowrate": flow_rate,
            "direction": "down",
        },
        None,
    )
    p_well = well.get_output()["pressure_output"]
    ipr.calculate_output({"flow": flow_rate}, None)
    p_reservoir = ipr.get_output()["bottomhole_pressure"]

    assert abs(p_well - p_reservoir) < 1.0


def test_solve_production_flow_rate_balances_pressures_with_esp():
    """Solved production flow rate (with ESP) should balance pressures."""
    dpdt_top = _make_well(length=500)
    dpdt_bottom = _make_well(length=500)
    esp = _make_esp()
    ipr = _make_ipr("production_reservoir", reservoir_pressure_pa=85e5, index_value=5e-6)

    flow_rate = solve_production_flow_rate(
        ipr,
        dpdt_top,
        wellhead_pressure=10e5,
        wellhead_temperature=80 + 273.15,
        ambient_temperature=20 + 273.15,
        dpdt_bottom=dpdt_bottom,
        esp=esp,
        esp_freq=60,
        flow_bracket=(1e-6, 0.1),
    )

    assert 0 < flow_rate < 0.1

    dpdt_top.calculate_output(
        {
            "pressure": 10e5,
            "temperature": 80 + 273.15,
            "temperature_ambient": 20 + 273.15,
            "flowrate": flow_rate,
            "direction": "down",
        },
        None,
    )
    y_top = dpdt_top.get_output()
    esp.calculate_output({"pump_freq": 60, "pump_flow": flow_rate}, None)
    pump_head = esp.get_output()["pump_head"]
    intake_pressure = max(0.0, y_top["pressure_output"] - pump_head)
    dpdt_bottom.calculate_output(
        {
            "pressure": intake_pressure,
            "temperature": y_top["temperature_output"],
            "temperature_ambient": 20 + 273.15,
            "flowrate": flow_rate,
            "direction": "down",
        },
        None,
    )
    p_well = dpdt_bottom.get_output()["pressure_output"]
    ipr.calculate_output({"flow": flow_rate}, None)
    p_reservoir = ipr.get_output()["bottomhole_pressure"]

    assert abs(p_well - p_reservoir) < 1.0


def test_solve_injection_flow_rate_balances_pressures():
    """Solved injection flow rate should balance well/reservoir pressures."""
    well = _make_well()
    ipr = _make_ipr("injection_reservoir", reservoir_pressure_pa=21.0e6, index_value=7e-8)

    flow_rate = solve_injection_flow_rate(
        ipr,
        well,
        wellhead_pressure=1e5,
        wellhead_temperature=60 + 273.15,
        flow_bracket=(1e-6, 0.1),
    )

    assert 0 < flow_rate < 0.1

    well.calculate_output(
        {
            "pressure": 1e5,
            "temperature": 60 + 273.15,
            "temperature_ambient": 60 + 273.15,
            "flowrate": flow_rate,
            "direction": "down",
        },
        None,
    )
    p_well = well.get_output()["pressure_output"]
    ipr.calculate_output({"flow": flow_rate}, None)
    p_reservoir = ipr.get_output()["bottomhole_pressure"]

    assert abs(p_well - p_reservoir) < 1.0
