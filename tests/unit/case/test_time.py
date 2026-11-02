"""``gm.case.Time``: the period of a run, its end excluded."""

import pandas as pd
import pytest

import gemini as gm
from gemini.units import Quantity
from tests.fixtures.errors import raises


def make(start="2027-01-01", end="2028-01-01", step=Quantity(1, "d")):
    """Return a time from the three values."""
    return gm.case.Time.from_dict({"start": start, "end": end, "step": step})


def test_a_year_at_one_day_is_365_steps():
    """``end`` is excluded: 2027-01-01 to 2028-01-01 is 365 days."""
    time = make()
    assert len(time.index) == 365 and time.index[-1] == pd.Timestamp("2027-12-31", tz="UTC")
    assert time.index.name == "time" and time.step == 86400.0


def test_the_dict_round_trip_writes_the_time_as_given():
    """A date stays a date and the step keeps its unit."""
    time = make(end="2027-01-02", step=Quantity(1, "h"))
    assert time.to_dict() == {
        "start": "2027-01-01",
        "end": "2027-01-02",
        "step": {"value": 1, "unit": "h"},
    }
    assert gm.case.Time.from_dict(time.to_dict()) == time and time.step == 3600.0


def test_an_offset_moves_the_instant_to_utc():
    """A time with an offset is the same instant in UTC."""
    time = make(
        start="2027-01-01T01:00:00+01:00", end="2027-01-01T05:00:00Z", step=Quantity(1, "h")
    )
    assert time.start == pd.Timestamp("2027-01-01", tz="UTC") and len(time.index) == 5


def test_a_period_of_a_part_of_a_step_is_refused():
    """The end must follow the start by whole steps."""
    with raises(gm.errors.ValidationError, "invalid_value"):
        make(end="2027-01-02", step=Quantity(5, "h"))


def test_an_end_before_the_start_is_out_of_bounds():
    """An empty period is refused."""
    with raises(gm.errors.ValidationError, "out_of_bounds"):
        make(start="2027-01-02", end="2027-01-01")


def test_text_for_the_step_is_refused():
    """A step is a quantity, never text."""
    with raises(gm.errors.ValidationError, "invalid_unit") as caught:
        make(end="2027-01-08", step="1 d")
    assert caught.value.path == "time.step"


@pytest.mark.parametrize("value", ["not a date", 5])
def test_a_start_that_is_no_date_is_refused(value):
    """The start is ISO 8601 text."""
    with raises(gm.errors.ValidationError, "invalid_value"):
        make(start=value, end="2027-01-08")


def test_a_missing_key_and_an_unknown_key_are_reported_together():
    """Both come in one error."""
    with pytest.raises(gm.errors.ValidationError) as caught:
        gm.case.Time.from_dict({"start": "2027-01-01", "stop": "2027-01-02"})
    assert sorted(item["path"] for item in caught.value.problems) == [
        "time.end",
        "time.step",
        "time.stop",
    ]
