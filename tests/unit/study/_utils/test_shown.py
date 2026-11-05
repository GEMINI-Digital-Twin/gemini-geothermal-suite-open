"""A study result in the display units of the one table."""

import pytest

from gemini.study._utils.shown import difference_names, display_quantity, display_text, shown
from gemini.units import Quantity
from gemini.units.shapes import measure


def test_a_mapping_of_values_is_converted_by_the_unit_of_each():
    """Energy in J is MWh, power in W is MW, a length has no display unit."""
    found = shown({"e": Quantity(3.6e9, "J"), "p": Quantity(2e6, "W"), "d": Quantity(5, "m")})
    assert (found["e"].value, found["e"].unit) == (pytest.approx(1.0), "MWh")
    assert (found["p"].value, found["p"].unit) == (pytest.approx(2.0), "MW")
    assert (found["d"].value, found["d"].unit) == (5, "m")


def test_a_value_keeps_its_reason_and_its_parts_in_display_units():
    """A value that is ``None`` stays so, and the parts are converted too."""
    value = measure(None, "J", "no run", heat=Quantity(7.2e9, "J"))
    found = shown(value)
    assert found.value is None and found.reason == "no run"
    assert found.parts["heat"].unit == "MWh"


def test_a_name_listed_as_a_difference_keeps_kelvin():
    """Only the listed name keeps K; the others go to degC."""
    found = shown({"a.lift": Quantity(5.0, "K"), "a.outlet": Quantity(300.0, "K")}, ["a.lift"])
    assert (found["a.lift"].value, found["a.lift"].unit) == (5.0, "K")
    assert found["a.outlet"].unit == "degC"


def test_a_span_named_like_a_long_duration_is_in_years():
    """The last part of a dotted name decides: ``analysis_period`` is shown in yr."""
    found = shown({"case.economics.analysis_period": Quantity(20 * 365.25 * 86400, "s")})
    assert found["case.economics.analysis_period"].unit == "yr"
    assert found["case.economics.analysis_period"].value == pytest.approx(20.0)


def test_a_quantity_and_a_text_of_one_number():
    """The helpers of the notes of ``size``: a Quantity and ``4.7 MW``."""
    assert display_quantity(4.7e6, "W").unit == "MW"
    assert display_text(4.7e6, "W") == "4.7 MW"
    assert display_text(0.05, "m3/s") == "180 m3/h"
    assert display_text(12.0, "K", difference=True) == "12 K"
    assert display_text(300.0, "K") == "26.85 degC"


def test_only_a_value_in_kelvin_with_a_difference_quantity_is_a_difference():
    """The quantity of the name decides; a value in another unit is never one."""
    parameters = {
        "x.lift": Quantity(5.0, "K"),
        "x.outlet": Quantity(300.0, "K"),
        "x.flow": Quantity(1.0, "m3/s"),
        "x.pump": "option",
    }
    quantities = {
        "x.lift": "temperature_difference",
        "x.outlet": "temperature",
        "x.flow": "volume_flow",
        "x.pump": None,
    }
    assert difference_names(parameters, quantities.get) == ["x.lift"]
