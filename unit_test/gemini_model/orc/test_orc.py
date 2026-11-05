"""Tests for the ORC power unit model."""

import math

import pytest

from gemini_model.orc.orc import OrganicRankineCycle
from gemini_simulator.registry import COMPONENT_REGISTRY

FLOW = 300.0 / 3600.0  # m3/s
RHO_CP = 1030.0 * 4180.0


def _run(rating=5e6, penalty=0.0, **u):
    m = OrganicRankineCycle()
    m.update_parameters({"capacity_net": rating, "plr_min": 0.0, "part_load_penalty": penalty})
    m.calculate_output(
        {
            "hot_temperature_in": 102.4,
            "hot_flow_rate": FLOW,
            "air_temperature": 10.0,
            "hot_temperature_out_min": 62.4,
            **u,
        }
    )
    return m.output


def test_registered():
    """The model is in GEMINI's component registry."""
    assert COMPONENT_REGISTRY["orc"] is OrganicRankineCycle


def test_matches_cycle_model_at_102c():
    """102.4 degC brine cooled 40 K, 10 degC air: ~7.2 % net (CoolProp cycle 7.21 %)."""
    out = _run()
    assert out["hot_temperature_out"] == pytest.approx(62.4)
    assert out["efficiency"] == pytest.approx(0.072, abs=0.003)
    assert out["power_el"] == pytest.approx(1.03e6, rel=0.03)


def test_energy_balance_and_second_law():
    """Heat in = brine heat drop = power + heat rejected; efficiency below Carnot."""
    for t_in, air in ((95.0, 0.0), (102.4, 20.0), (141.5, 10.0)):
        out = _run(hot_temperature_in=t_in, air_temperature=air, hot_temperature_out_min=t_in - 40)
        assert out["heat_in"] == pytest.approx(RHO_CP * FLOW * (t_in - out["hot_temperature_out"]))
        assert out["power_el"] + out["heat_rejected"] == pytest.approx(out["heat_in"])
        assert 0 < out["efficiency"] < out["carnot_efficiency"]


def test_hotter_brine_and_colder_air_give_more_power():
    """Efficiency rises with brine temperature and falls with air temperature."""
    base = _run()["efficiency"]
    assert _run(hot_temperature_in=120.0, hot_temperature_out_min=80.0)["efficiency"] > base
    assert _run(air_temperature=25.0)["efficiency"] < base


def test_outlet_floor_and_cap_respected():
    """The brine never leaves below the caller's minimum or the condensing floor."""
    out = _run(hot_temperature_out_min=90.0)
    assert out["hot_temperature_out"] == pytest.approx(90.0)
    out = _run(hot_temperature_in=70.0, hot_temperature_out_min=30.0, air_temperature=20.0)
    assert out["hot_temperature_out"] == pytest.approx(20.0 + 15.0 + 20.0)


def test_part_load_lowers_efficiency():
    """A unit far above the day's heat runs at part load, less efficiently."""
    full = _run(rating=1.04e6, penalty=0.15)
    big = _run(rating=4e6, penalty=0.15)
    assert big["efficiency"] < full["efficiency"]


def test_rating_caps_output():
    """At the rating the brine leaves warmer and power equals the rating."""
    out = _run(rating=0.5e6)
    assert out["power_el"] == pytest.approx(0.5e6, rel=1e-6)
    assert out["hot_temperature_out"] > 62.4


def test_minimum_part_load_and_no_flow():
    """Below plr_min (or with no flow, or too cold brine) the unit is off."""
    m = OrganicRankineCycle()
    m.update_parameters({"capacity_net": 5e6, "plr_min": 0.3})
    m.calculate_output(
        {"hot_temperature_in": 102.4, "hot_flow_rate": FLOW, "air_temperature": 10.0}
    )
    assert m.output["power_el"] == 0.0 and m.output["hot_temperature_out"] == 102.4
    for u in ({"hot_flow_rate": 0.0}, {"hot_temperature_in": 50.0}):
        out = _run(**u)
        assert out["power_el"] == 0.0 and out["heat_in"] == 0.0


def test_zero_rating_is_off():
    """No unit installed: nothing happens."""
    out = _run(rating=0.0)
    assert out["power_el"] == 0.0
    assert not math.isnan(out["efficiency"])
