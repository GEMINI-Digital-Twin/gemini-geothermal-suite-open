"""The best trial of a search: a value with its plant."""

import json

import pytest

import gemini as gm
from gemini.study._utils.best import Best
from gemini.units import Quantity


def test_the_plant_is_a_key_and_its_plant_dict_in_the_json():
    """``best["plant"]`` is the plant, the rest are parts; the JSON holds its plant dict."""
    plant = gm.Plant("Empty")
    best = Best(3.0, "W", None, {"parameters": {}}, plant)
    assert best["plant"] is plant and best["parameters"] == {}
    assert best.to_dict()["plant"] == plant.to_dict()


def test_a_conversion_keeps_the_plant():
    """Only the unit changes."""
    plant = gm.Plant("Empty")
    best = Best(3000.0, "W", None, {}, plant).to("kW")
    assert best.value == 3.0 and best.plant is plant


def test_the_json_shows_the_display_units_and_reads_back_the_same_value():
    """An objective in J and a power in W are shown in MWh and MW; ``from_dict`` is equal."""
    plant = gm.Plant("Empty")
    parameters = {"d.capacity": Quantity(2.5e6, "W"), "depth": Quantity(1500.0, "m")}
    best = Best(3.6e9, "J", None, {"parameters": parameters}, plant)
    plain = best.to_dict()
    assert (plain["value"], plain["unit"]) == (pytest.approx(1.0), "MWh")
    assert plain["parameters"]["d.capacity"] == {"value": pytest.approx(2.5), "unit": "MW"}
    assert plain["parameters"]["depth"] == {"value": 1500.0, "unit": "m"}
    again = Best.from_dict(json.loads(json.dumps(plain)))
    assert again.si == pytest.approx(best.si)
    assert again.parts["parameters"]["d.capacity"].si == pytest.approx(2.5e6)


def test_a_difference_keeps_kelvin_and_a_long_span_is_in_years():
    """A parameter listed as a difference is not shifted to degC; a name of ``YEARS`` is in yr."""
    year = 365.25 * 86400
    parameters = {
        "x.approach": Quantity(5.0, "K"),
        "x.outlet": Quantity(300.0, "K"),
        "case.economics.analysis_period": Quantity(20 * year, "s"),
    }
    best = Best(1.0, "-", None, {"parameters": parameters, "differences": ["x.approach"]}, None)
    shown = best.to_dict()["parameters"]
    assert shown["x.approach"] == {"value": 5.0, "unit": "K"}
    assert shown["x.outlet"]["unit"] == "degC"
    assert shown["x.outlet"]["value"] == pytest.approx(26.85)
    assert shown["case.economics.analysis_period"]["unit"] == "yr"
    assert shown["case.economics.analysis_period"]["value"] == pytest.approx(20.0)
    again = Best.from_dict(best.to_dict())
    assert again.to_dict() == best.to_dict()
