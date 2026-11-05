"""The table of quantity -> display unit and the conversion of a result to it."""

import pytest

from gemini.units import Quantity
from gemini.units.display import DISPLAY_UNITS, by_si_unit, shown
from gemini.units.shapes import measure


def test_the_display_unit_of_an_si_unit_comes_from_the_one_table():
    """Flow in m3/h, temperature in degC, energy in MWh."""
    table = by_si_unit()
    assert table["m3/s"] == "m3/h" and table["K"] == "degC" and table["J"] == "MWh"
    assert set(table.values()) == set(DISPLAY_UNITS.values())


def test_every_quantity_of_a_result_is_converted_through_mappings_lists_and_values():
    """A temperature in a list, an energy in a dict and the parts of a value."""
    found = shown(
        {"t": [Quantity(293.15, "K")], "e": measure(3.6e9, "J", part=measure(7.2e9, "J"))},
        by_si_unit(),
    )
    assert found["t"][0].value == pytest.approx(20.0)
    assert found["e"].value == pytest.approx(1.0) and str(found["e"].unit) == "MWh"
    assert found["e"].parts["part"].value == pytest.approx(2.0)


def test_a_unit_not_in_the_table_and_a_plain_number_stay_as_they_are():
    """A pressure has no display unit here, a bare number is not a quantity."""
    pressure = Quantity(2.0, "Pa")
    assert shown([pressure, 3.0, "text"], by_si_unit()) == [pressure, 3.0, "text"]


def test_the_caller_adjusts_the_table_of_a_name():
    """``adjust`` returns the table for one key of a mapping: here a span stays in seconds."""

    def adjust(owner, key, table):
        return {} if key == "span" else table

    found = shown({"span": Quantity(60.0, "s"), "t": Quantity(300.0, "K")}, by_si_unit(), adjust)
    assert str(found["span"].unit) == "s" and str(found["t"].unit) == "degC"


def test_displayed_values_give_a_quantity_in_the_display_unit():
    """A power in W is MW, a difference keeps K, a value without a display unit stays in SI."""
    from gemini.units.display import DisplayedValues

    values = DisplayedValues()
    assert (values.value(2e6, "W", "power").value, values.value(2e6, "W", "power").unit) == (
        2.0,
        "MW",
    )
    assert values.value(5.0, "K", "temperature_difference").unit == "K"
    assert values.value(5.0, "K", "temperature").unit == "degC"
    assert values.value(5.0, "m", "length").unit == "m"
    missing = values.value(None, "W", "power", "no run")
    assert missing.value is None and missing.reason == "no run"
