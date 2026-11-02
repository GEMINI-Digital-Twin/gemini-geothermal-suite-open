"""The unit in which a metric is shown in a table."""

import pytest

import gemini as gm
from gemini.evaluate._utils.display import display_units, in_unit
from tests.fixtures.errors import raises


def test_a_metric_is_shown_in_its_unit_or_the_one_given():
    """Metrics without a display unit are left out."""
    assert display_units(["lcts", "co2", "cop"]) == {"lcts": "EUR/MWh", "co2": "kt"}
    assert display_units(["lcts"], {"lcts": "EUR/kWh"}) == {"lcts": "EUR/kWh"}


def test_a_number_is_converted_from_si():
    """1 currency/J is 3.6e9 EUR/MWh; 1e6 kg is 1 kt."""
    assert in_unit("lcts", 1.0, "EUR/MWh") == pytest.approx(3.6e9)
    assert in_unit("co2", 1e6, "kt") == pytest.approx(1.0)
    assert in_unit("co2", None, "kt") is None


def test_a_unit_that_does_not_fit_is_refused():
    """A name that is not a shown metric; a unit of another dimension."""
    with raises(gm.errors.ValidationError, "invalid_value", match="units.cop"):
        display_units(["lcts"], {"cop": "kt"})
    with raises(gm.errors.ValidationError, "invalid_unit"):
        display_units(["co2"], {"co2": "MWh"})


def test_the_display_unit_of_an_si_unit_comes_from_the_one_table():
    """Flow in m3/h, temperature in degC, energy in MWh."""
    from gemini.evaluate._utils.display import by_si_unit, shown
    from gemini.units import Quantity

    table = by_si_unit()
    assert table["m3/s"] == "m3/h" and table["K"] == "degC" and table["J"] == "MWh"
    assert shown({"t": [Quantity(293.15, "K")]}, table)["t"][0].value == pytest.approx(20.0)


def _check(role, quantity, value, limit, unit):
    """Return a failed check of a requirement, in SI."""
    return {
        "name": f"{role}_{quantity}",
        "role": role,
        "quantity": quantity,
        "passed": False,
        "value": gm.units.Quantity(value, unit),
        "limit": gm.units.Quantity(limit, unit),
    }


def test_a_temperature_difference_shows_in_kelvin_and_a_temperature_in_celsius():
    """40 K of lift is 40 K, not -233 degC; the supply temperature of the same report is degC."""
    from gemini.evaluate._utils.display import by_si_unit, shown

    found = shown(
        [
            _check("heat_pump", "lift", 40.0, 30.0, "K"),
            _check("heating_supply", "temperature", 333.15, 343.15, "K"),
        ],
        by_si_unit(),
    )
    assert (found[0]["value"].value, str(found[0]["value"].unit)) == (40.0, "K")
    assert (found[0]["limit"].value, str(found[0]["limit"].unit)) == (30.0, "K")
    assert str(found[1]["value"].unit) == "degC"
    assert found[1]["value"].value == pytest.approx(60.0)


def test_a_difference_is_kept_in_the_dict_of_a_report():
    """The plain JSON of a report holds the lift in K."""
    from gemini.evaluate.report import Report

    plain = Report(requirements=[_check("heat_pump", "lift", 40.0, 30.0, "K")]).to_dict()
    assert plain["requirements"][0]["value"] == {"value": 40.0, "unit": "K"}


def test_long_durations_show_in_years_and_operating_durations_in_days():
    """The analysis period and the payback in yr, the time a requirement counts in d."""
    from gemini.evaluate.report import Report
    from gemini.units import SECONDS_PER_YEAR, Quantity

    plain = Report(
        analysis_period=Quantity(25 * SECONDS_PER_YEAR, "s"),
        payback=Quantity(6.5, "yr"),
        running=Quantity(10 * 86400.0, "s"),
    ).to_dict()
    assert plain["analysis_period"] == {"value": pytest.approx(25.0), "unit": "yr"}
    assert plain["payback"] == {"value": pytest.approx(6.5), "unit": "yr"}
    assert plain["running"] == {"value": pytest.approx(10.0), "unit": "d"}


def test_the_years_a_result_carries_stay_years():
    """``lifetime_years`` of a net present value is in yr, not days."""
    from gemini.evaluate._utils.display import by_si_unit, shown
    from gemini.types.shapes import measure

    npv = measure(1.0, "currency", lifetime_years=measure(25.0, "yr"))
    assert shown({"npv": npv}, by_si_unit())["npv"].parts["lifetime_years"].unit == "yr"
