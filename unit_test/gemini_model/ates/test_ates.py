"""Tests for the ATES (aquifer cold store) model."""

import pytest

from gemini_model.ates.ates import ATES
from gemini_simulator.registry import COMPONENT_REGISTRY

RHO_CP = 1000.0 * 4186.0


def _model(**params):
    """ATES model with test parameters."""
    m = ATES()
    m.update_parameters({"well_pairs": 2, "loss_fraction_per_day": 0.0, **params})
    return m


def test_registered():
    """The model is in GEMINI's component registry."""
    assert COMPONENT_REGISTRY["ates"] is ATES


def test_charge_fills_the_cold_store():
    """A cold day moves warm-well water through the dry cooler into the cold well."""
    m = _model()
    state = m.initialize_state(None)
    state.update({"warm_volume_m3": 1e6, "warm_temperature_c": 20.0})
    m.calculate_output({**state, "mode": "charge", "air_temperature": 2.0})
    y = m.get_output()
    q = 2 * 150.0 / 3600.0
    assert y["injection_temperature_c"] == pytest.approx(7.0)
    assert y["charge_power"] == pytest.approx(q * RHO_CP * (20.0 - 7.0))
    assert y["cold_volume_m3"] == pytest.approx(q * 86400.0)
    assert y["warm_volume_m3"] == pytest.approx(1e6 - q * 86400.0)
    assert y["fan_power"] == pytest.approx(0.03 * y["charge_power"])
    assert y["power_el"] == pytest.approx(y["pump_power"] + y["fan_power"])


def test_no_charge_when_air_is_too_warm():
    """No charging when the dry cooler cannot get the water 2 K below the warm well."""
    m = _model()
    state = m.initialize_state(None)
    m.calculate_output({**state, "mode": "charge", "air_temperature": 9.0})  # 14 > 11 - 2
    assert m.get_output()["charge_power"] == 0.0


def test_discharge_energy_balance_and_limits():
    """Cooling equals the groundwater heat pickup and never undershoots the supply."""
    m = _model()
    state = {
        "cold_volume_m3": 5e5,
        "cold_temperature_c": 8.0,
        "warm_volume_m3": 0.0,
        "warm_temperature_c": 11.0,
    }
    chilled_flow = 8e6 / (RHO_CP * 6.0)  # 8 MW at 26 -> 20 degC
    u = {
        **state,
        "mode": "discharge",
        "chilled_temperature_in": 26.0,
        "chilled_flow_rate": chilled_flow,
        "chilled_temperature_out_target": 20.0,
    }
    m.calculate_output(u)
    y = m.get_output()
    q = y["groundwater_flow_m3h"] / 3600.0
    assert y["injection_temperature_c"] == pytest.approx(24.5)  # 26 - 1.5 K approach
    assert y["cooling_power"] == pytest.approx(q * RHO_CP * (24.5 - 8.0))
    assert y["chilled_temperature_out"] >= 20.0 - 1e-9
    assert q <= 2 * 150.0 / 3600.0 + 1e-12
    assert y["warm_temperature_c"] == pytest.approx(24.5)


def test_flow_limit_and_request():
    """flow_fraction and cooling_request both cap the cooling."""
    m = _model()
    state = {
        "cold_volume_m3": 5e6,
        "cold_temperature_c": 8.0,
        "warm_volume_m3": 0.0,
        "warm_temperature_c": 11.0,
    }
    base = {
        **state,
        "mode": "discharge",
        "chilled_temperature_in": 26.0,
        "chilled_flow_rate": 10e6 / (RHO_CP * 6.0),
        "chilled_temperature_out_target": 20.0,
    }
    m.calculate_output({**base, "flow_fraction": 0.5})
    half = m.get_output()["groundwater_flow_m3h"]
    assert half == pytest.approx(150.0)
    m.calculate_output({**base, "cooling_request": 1e6})
    assert m.get_output()["cooling_power"] == pytest.approx(1e6)


def test_native_groundwater_after_the_cold_store_is_used():
    """With an empty cold store the well gives undisturbed groundwater."""
    m = _model()
    state = m.initialize_state(None)
    m.calculate_output(
        {
            **state,
            "mode": "discharge",
            "chilled_temperature_in": 26.0,
            "chilled_flow_rate": 1e6 / (RHO_CP * 6.0),
            "chilled_temperature_out_target": 20.0,
        }
    )
    assert m.get_output()["extraction_temperature_c"] == pytest.approx(11.0)


def test_standing_loss_relaxes_to_groundwater():
    """Idle days pull both store temperatures towards groundwater."""
    m = _model(loss_fraction_per_day=0.1)
    m.calculate_output(
        {
            "cold_volume_m3": 1e5,
            "cold_temperature_c": 6.0,
            "warm_volume_m3": 1e5,
            "warm_temperature_c": 21.0,
            "mode": "idle",
        }
    )
    y = m.get_output()
    assert y["cold_temperature_c"] == pytest.approx(6.5)
    assert y["warm_temperature_c"] == pytest.approx(20.0)
    assert y["loss_mwh"] == pytest.approx(RHO_CP * 1e5 * (0.5 + 1.0) / 3.6e9)


def test_bad_mode():
    """An unknown mode raises."""
    m = _model()
    with pytest.raises(ValueError):
        m.calculate_output({**m.initialize_state(None), "mode": "boost"})
