"""Unit tests for the absorption and electric chiller models."""

import pytest

from gemini_model.chiller import AbsorptionChiller, ElectricChiller


def _abs(cap=10e6):
    m = AbsorptionChiller()
    m.update_parameters({"nominal_cooling_capacity": cap})
    return m


def _abs_inputs(**kw):
    u = {
        "cooling_demand": 5e6,
        "hot_water_temperature_in": 85.0,
        "hot_water_flow_rate": 0.1,
        "chilled_water_supply_temperature": 20.0,
        "chilled_water_return_temperature": 26.0,
        "cooling_water_temperature_in": 27.0,
    }
    u.update(kw)
    return u


def test_absorption_energy_balance_and_hot_water_outlet():
    """Rejected heat = cooling + generator heat; hot-water outlet from Q_G = m cp dT."""
    m = _abs()
    m.calculate_output(_abs_inputs())
    y = m.get_output()
    assert y["cooling_power"] == pytest.approx(5e6)
    assert y["rejected_heat"] == pytest.approx(y["cooling_power"] + y["generator_heat"])
    dt = y["generator_heat"] / (0.1 * 1030 * 4000)
    assert y["hot_water_temperature_out"] == pytest.approx(85.0 - dt)
    assert 0.4 < y["COP"] <= 0.75


def test_absorption_capacity_rises_with_driving_temperature():
    """Hotter driving water gives more capacity (characteristic equation)."""
    m = _abs(cap=10e6)
    caps = []
    for t in (70.0, 80.0, 90.0):
        m.calculate_output(_abs_inputs(cooling_demand=50e6, hot_water_temperature_in=t))
        caps.append(m.get_output()["cooling_power"])
    assert caps[0] < caps[1] < caps[2]


def test_absorption_no_demand_no_heat():
    """Zero cooling demand draws no heat."""
    m = _abs()
    m.calculate_output(_abs_inputs(cooling_demand=0.0))
    y = m.get_output()
    assert y["generator_heat"] == 0.0 and y["hot_water_temperature_out"] == 85.0


def test_absorption_unmet_when_too_cold():
    """Below the driving threshold the chiller cannot deliver cooling."""
    m = _abs()
    m.calculate_output(_abs_inputs(hot_water_temperature_in=40.0))
    y = m.get_output()
    assert y["cooling_power"] == 0.0 and y["unmet_cooling"] == pytest.approx(5e6)


def test_electric_chiller_cop_and_capacity_limit():
    """Carnot-fraction COP for 20 C chilled water; capacity is capped."""
    m = ElectricChiller()
    m.update_parameters({"nominal_cooling_capacity": 4e6})
    m.calculate_output(
        {
            "cooling_demand": 5e6,
            "chilled_water_supply_temperature": 20.0,
            "cooling_water_temperature_in": 27.0,
        }
    )
    y = m.get_output()
    assert y["cooling_power"] == pytest.approx(4e6)
    assert y["unmet_cooling"] == pytest.approx(1e6)
    t_ev, t_co = 17 + 273.15, 36 + 273.15
    assert y["COP"] == pytest.approx(min(9.0, 0.5 * t_ev / (t_co - t_ev)))
    assert y["power_el"] > y["cooling_power"] / y["COP"]  # auxiliaries included
