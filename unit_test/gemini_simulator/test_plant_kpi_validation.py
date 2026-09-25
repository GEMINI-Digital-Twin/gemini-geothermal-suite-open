"""Validate the Boiler + CHP secondary-network portion of the plant.

Validates ``simulator_examples/projects/doublet_plant.json`` against
directly reimplemented forward-calculation formulas for the doublet-A
example plant configuration values that the JSON project file mirrors.

Companion to ``test_surface_chain_validation.py`` (surface chain only); together
they cover the full surface + secondary chain wired up in
``simulator_examples/projects/doublet_plant.json``.
"""

import math
from pathlib import Path

import pytest

from gemini_simulator import kpi
from gemini_simulator.project_loader import load_project

PROJECT_PATH = (
    Path(__file__).resolve().parents[2] / "simulator_examples" / "projects" / "doublet_plant.json"
)

# Transcribed from application/doubletA/component_parameter.json
DOUBLET_A_CONFIG = {
    "Plant": {"T_s_in": 20, "Q_s": 140, "u": 80, "v": 80},
    "Separator": {"R1": 0.001, "dT": 1},
    "FilterA": {"R0": 0.01, "a": 0.005, "b": 1e-5, "dT": 1},
    "FilterB": {"R0": 0.001, "a": 0.005, "b": 1e-5, "dT": 1},
    "HeatExchanger": {"R1": 0, "type": "counter", "heat_transfer_coefficient": 250e3},
    "Boiler": {
        "caloric_value": 50,
        "efficiency_factor": 0.8,
        "gas_water_ratio": 0.5,
        "gas_emission_factor": 56.6,
    },
    "CHP": {
        "caloric_value": 50,
        "efficiency_factor": 0.8,
        "gas_water_ratio": 0.5,
        "gas_emission_factor": 56.6,
    },
}

PRIMARY_FLOW_M3H = 140.0
SECONDARY_FLOW_M3H = 140.0
WELLHEAD_PRESSURE_BAR = 3.0
WELLHEAD_TEMPERATURE_C = 80.0
GRID_GAS_FLOW_M3H = 0.0


def _reference_hex_secondary_out(primary_flow_m3h, wellhead_temperature_c):
    """Compute the derived heat-exchanger secondary outlet formula.

    Matches the value independently validated in
    test_surface_chain_validation.py.
    """
    rho, cw = 1050, 4200
    hex_cfg = DOUBLET_A_CONFIG["HeatExchanger"]
    plant_cfg = DOUBLET_A_CONFIG["Plant"]
    filter_a_cfg = DOUBLET_A_CONFIG["FilterA"]
    separator_cfg = DOUBLET_A_CONFIG["Separator"]

    t_sep_out = wellhead_temperature_c - separator_cfg["dT"]
    t_filta_out = t_sep_out - filter_a_cfg["dT"]

    v = plant_cfg["v"] / 100
    m_p = rho * primary_flow_m3h / 3600
    m_s = rho * SECONDARY_FLOW_M3H / 3600
    c_p = m_p * cw
    c_s = v * m_s * cw
    c_max, c_min = max(c_p, c_s), min(c_p, c_s)
    ntu = hex_cfg["heat_transfer_coefficient"] / c_min
    c_r = c_min / c_max
    h_max = c_min * abs(plant_cfg["T_s_in"] - t_filta_out)
    if c_r == 1:
        e = ntu / (1 + ntu)
    elif c_r < 0.01:
        e = 1 - math.exp(-ntu)
    else:
        e = (1 - math.exp(-ntu * (1 - c_r))) / (1 - c_r * math.exp(-ntu * (1 - c_r)))
    h = e * h_max
    return plant_cfg["T_s_in"] + h / cw / (v * m_s)


def _reference_boiler_forward(t_in, cfg, plant_cfg, q_p, q_s, q_gas_grid=0.0):
    """Independent forward-calculation formula for the boiler."""
    rho, cw, rho_gas = 1050, 4200, 0.7
    u = plant_cfg["u"] / 100
    v = plant_cfg["v"] / 100
    q_gas = cfg["gas_water_ratio"] * q_p / 3600
    q_gas_total = (q_gas + q_gas_grid / 3600) * rho_gas
    power = cfg["efficiency_factor"] * cfg["caloric_value"] * 1e6 * u * q_gas_total
    m_s = rho * q_s / 3600
    t_out = t_in + power / cw / (v * m_s)
    emission = cfg["gas_emission_factor"] * 1e-9 * cfg["caloric_value"] * 1e6 * u * q_gas_total
    return t_out, power, emission


def _reference_chp_forward(t_in, cfg, plant_cfg, q_p, q_s, q_gas_grid=0.0):
    """Independent forward-calculation formula for the CHP unit."""
    rho, cw, rho_gas = 1050, 4200, 0.7
    u = plant_cfg["u"] / 100
    v = plant_cfg["v"] / 100
    q_gas = cfg["gas_water_ratio"] * q_p / 3600
    q_gas_total = (q_gas + q_gas_grid / 3600) * rho_gas
    power = cfg["efficiency_factor"] * cfg["caloric_value"] * 1e6 * (1 - u) * q_gas_total
    power_elec = power / 3
    power_heat = 2 * power / 3
    m_s = rho * q_s / 3600
    t_out = t_in + power_heat / cw / ((1 - v) * m_s)
    emission = (
        cfg["gas_emission_factor"] * 1e-9 * cfg["caloric_value"] * 1e6 * (1 - u) * q_gas_total
    )
    return t_out, power_elec, power_heat, emission


def test_boiler_chp_and_secondary_outlet_temperature_match_reference_formulas():
    """Boiler/CHP outputs and secondary outlet temp should match reference formulas."""
    solver = load_project(PROJECT_PATH)
    solver.run()

    primary_flow_m3h = solver.get_output("producer_well", "flow_rate")
    wellhead_temperature_c = solver.get_output("producer_well", "temperature_out")

    plant_cfg = DOUBLET_A_CONFIG["Plant"]
    v = plant_cfg["v"] / 100

    t_hex_s_out = _reference_hex_secondary_out(primary_flow_m3h, wellhead_temperature_c)
    t_boiler_expected, boiler_power_th_expected, boiler_emission_expected = (
        _reference_boiler_forward(
            t_hex_s_out, DOUBLET_A_CONFIG["Boiler"], plant_cfg, primary_flow_m3h, SECONDARY_FLOW_M3H
        )
    )
    t_chp_expected, chp_power_el_expected, chp_power_th_expected, chp_emission_expected = (
        _reference_chp_forward(
            plant_cfg["T_s_in"],
            DOUBLET_A_CONFIG["CHP"],
            plant_cfg,
            primary_flow_m3h,
            SECONDARY_FLOW_M3H,
        )
    )
    t_s_out_expected = v * t_boiler_expected + (1 - v) * t_chp_expected

    assert solver.get_output("boiler", "temperature_out") == pytest.approx(t_boiler_expected)
    assert solver.get_output("boiler", "power_th") == pytest.approx(boiler_power_th_expected)
    assert solver.get_output("boiler", "emission") == pytest.approx(boiler_emission_expected)

    assert solver.get_output("chp", "temperature_out") == pytest.approx(t_chp_expected)
    assert solver.get_output("chp", "power_el") == pytest.approx(chp_power_el_expected)
    assert solver.get_output("chp", "power_th") == pytest.approx(chp_power_th_expected)
    assert solver.get_output("chp", "emission") == pytest.approx(chp_emission_expected)

    assert kpi.secondary_outlet_temperature(solver) == pytest.approx(t_s_out_expected)


def test_plant_thermal_power_matches_reference_power_plant_formula():
    """Plant thermal power should match the reference power_plant formula."""
    solver = load_project(PROJECT_PATH)
    solver.run()

    plant_cfg = DOUBLET_A_CONFIG["Plant"]
    t_s_out = kpi.secondary_outlet_temperature(solver)

    # power_plant = Q_s/3600 * rho * Cw * (T_s_out - T_s_in)  [W]
    expected = (SECONDARY_FLOW_M3H / 3600) * 1050 * 4200 * (t_s_out - plant_cfg["T_s_in"])
    actual = kpi.plant_thermal_power_w(
        solver,
        secondary_flow_m3s=SECONDARY_FLOW_M3H / 3600,
        secondary_temperature_in=plant_cfg["T_s_in"],
    )
    assert actual == pytest.approx(expected)
