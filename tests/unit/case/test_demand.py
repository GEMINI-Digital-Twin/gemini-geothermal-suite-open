"""``gm.case.Demand``: services, their conditions, and the frame in watts."""

import pytest

import gemini as gm
from tests.fixtures.errors import raises


def test_the_frame_is_in_watts_on_the_steps_of_time(case):
    """Columns for the services given, W, a UTC ``time`` index."""
    frame = case.demand.frame
    assert list(frame) == ["heating_demand", "cooling_demand"]
    assert frame.index.equals(case.time.index) and frame.index.name == "time"
    assert frame["heating_demand"].iloc[-1] == pytest.approx(4e6)
    assert frame.attrs["units"] == {"heating_demand": "W", "cooling_demand": "W"}


def test_a_demand_with_one_service_has_one_column(data, files):
    """Cooling alone is allowed."""
    del data["demand"]["heating"]
    assert list(gm.Case.from_dict(data, files=files).demand.frame) == ["cooling_demand"]


def test_a_demand_without_a_service_is_refused(data, files):
    """At least one of heating and cooling."""
    data["demand"] = {}
    with raises(gm.errors.ValidationError, "missing_value"):
        gm.Case.from_dict(data, files=files)


def test_the_conditions_of_the_consumer_are_read(data, files):
    """Return pressure, return limits and the state of the building, in SI."""
    heating, cooling = data["demand"]["heating"], data["demand"]["cooling"]
    heating["return_pressure"] = {"value": 5, "unit": "bar"}
    heating["maximum_return_temperature"] = {"value": 70, "unit": "degC"}
    cooling["indoor_temperature"] = {"value": 24, "unit": "degC"}
    cooling["indoor_relative_humidity"] = {"value": 0.5}
    cooling["dew_point_margin"] = {"value": 2, "unit": "K"}
    demand = gm.Case.from_dict(data, files=files).demand
    assert demand.heating.return_pressure == pytest.approx(5e5)
    assert demand.heating.maximum_return_temperature == pytest.approx(343.15)
    assert demand.cooling.indoor_relative_humidity == 0.5 and demand.cooling.dew_point_margin == 2.0
    data["demand"]["heating"]["indoor_temperature"] = {"value": 20, "unit": "degC"}
    with raises(gm.errors.ValidationError, "unknown_name"):
        gm.Case.from_dict(data, files=files)


def test_the_old_form_of_the_demand_is_refused_with_the_new_one(data, files):
    """file, time_column, column and unit are old_format."""
    data["demand"]["file"] = "demand.csv"
    data["demand"]["heating"]["column"] = "heat"
    with raises(gm.errors.ValidationError, "old_format") as caught:
        gm.Case.from_dict(data, files=files)
    assert [item["path"] for item in caught.value.problems] == [
        "demand.file",
        "demand.heating.column",
    ]
    assert "power" in str(caught.value)


def test_a_constant_power_is_a_series_of_that_value(data, files):
    """A demand may be a flat number."""
    data["demand"]["heating"]["power"] = {"value": 2, "unit": "MW"}
    case = gm.Case.from_dict(data, files=files)
    assert case.demand.frame["heating_demand"].tolist() == [2e6] * 7


def test_a_negative_demand_is_out_of_bounds(data):
    """A series is judged against the bounds of the value."""
    text = "time,heat_MW,cold_MW\n" + "".join(f"2027-01-0{n}T00:00:00Z,-1,1\n" for n in range(1, 8))
    with raises(gm.errors.ValidationError, "out_of_bounds"):
        gm.Case.from_dict(data, files={"data/demand.csv": text.encode()})
