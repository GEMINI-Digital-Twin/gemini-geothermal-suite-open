"""``gm.case.Economics``: all money, usable alone and held by the case."""

import copy
import json

import pytest

import gemini as gm
from tests.fixtures.errors import raises
from tests.unit.case.conftest import economics


@pytest.fixture
def money():
    """Return the economics dictionary."""
    return economics()


def test_the_economics_is_read_alone_and_written_back_as_given(money, tmp_path):
    """from_json and to_json on a file; every value as given, in SI inside."""
    first = gm.case.Economics.from_dict(money)
    assert first.currency == "EUR" and first.price_year == 2015 and first.discount_rate == 0.05
    assert first.analysis_period == pytest.approx(25 * 365.25 * 86400)
    assert first.capex.heat_pump == 0.67 and first.opex.fixed == {"heat_pump": 0.02}
    assert first.to_dict() == money
    first.to_json(tmp_path / "economics.json")
    assert gm.case.Economics.from_json(tmp_path / "economics.json") == first
    assert json.loads((tmp_path / "economics.json").read_text()) == money


def test_the_conventions_and_the_subsidy_are_read(money):
    """Allocation, the GWP standard named by the file, and the subsidy."""
    found = gm.case.Economics.from_dict(money)
    assert found.accounting.allocation.heat_cost_share == 0.8
    assert found.accounting.gwp.standard == "IPCC AR6" and found.accounting.gwp.CH4 == 29.8
    assert found.revenue.subsidy.amount == 1e6
    assert found.revenue.subsidy.duration == pytest.approx(10 * 31557600)
    assert found.carbon.price == pytest.approx(0.08)


def test_a_wrong_header_is_refused(money):
    """Kind and format are checked."""
    with raises(gm.errors.ValidationError, "invalid_format"):
        gm.case.Economics.from_dict({**money, "kind": "case"})
    del money["kind"]
    with raises(gm.errors.ValidationError, "old_format"):
        gm.case.Economics.from_dict(money)


def test_the_price_year_is_a_whole_number(money):
    """2015.5 is no year."""
    money["price_year"] = {"value": 2015.5}
    with raises(gm.errors.ValidationError, "invalid_value"):
        gm.case.Economics.from_dict(money)


def test_the_drilling_cost_is_a_rate_or_a_table_by_depth(money):
    """A constant is returned as it is; a table is interpolated linearly."""
    assert gm.case.Economics.from_dict(money).drilling_cost_per_metre(3000.0) == 1239.0
    money["capex"]["drilling"] = {
        "depth": {"value": [1000, 2000, 4000], "unit": "m"},
        "cost_per_metre": {"value": [1000, 1500, 3500], "unit": "EUR/m"},
    }
    found = gm.case.Economics.from_dict(money)
    assert found.drilling_cost_per_metre(1500.0) == pytest.approx(1250.0)
    assert found.drilling_cost_per_metre(3000.0) == pytest.approx(2500.0)
    assert found.drilling_cost_per_metre(4000.0) == pytest.approx(3500.0)
    assert found.to_dict() == money


def test_a_length_outside_the_depth_table_is_refused_without_extrapolation(money):
    """Out of bounds on both sides."""
    money["capex"]["drilling"] = {
        "depth": {"value": [1000, 2000], "unit": "m"},
        "cost_per_metre": {"value": [1000, 1500], "unit": "EUR/m"},
    }
    found = gm.case.Economics.from_dict(money)
    for length in (999.0, 2001.0):
        with raises(gm.errors.ValidationError, "out_of_bounds"):
            found.drilling_cost_per_metre(length)


def test_a_depth_table_must_rise_and_agree(money):
    """Same length, rising depth, units of the right dimension."""
    drilling = {
        "depth": {"value": [2000, 1000], "unit": "m"},
        "cost_per_metre": {"value": [1000, 1500], "unit": "EUR/m"},
    }
    for change in (
        {},
        {"cost_per_metre": {"value": [1000], "unit": "EUR/m"}},
        {"depth": {"value": [1, 2], "unit": "kg"}},
    ):
        money["capex"]["drilling"] = drilling | change
        with pytest.raises(gm.errors.ValidationError):
            gm.case.Economics.from_dict(money)


def test_an_absent_cost_is_missing_assumption(money):
    """No drilling, no cost."""
    del money["capex"]["drilling"]
    with raises(gm.errors.ValidationError, "missing_assumption") as caught:
        gm.case.Economics.from_dict(money).drilling_cost_per_metre(1000.0)
    assert caught.value.path == "economics.capex.drilling"


def test_a_price_series_needs_the_time_of_a_case(money):
    """Alone, a series has no steps to lie on; with a time it is aligned."""
    money["energy"]["electricity"] = {"file": "p.csv", "column": "eur", "unit": "EUR/MWh"}
    text = b"time,eur\n2027-01-01T00:00:00Z,10\n2027-01-02T00:00:00Z,20\n"
    with raises(gm.errors.ValidationError, "missing_value"):
        gm.case.Economics.from_dict(money, files={"p.csv": text})
    time = gm.case.Time.from_dict(
        {"start": "2027-01-01", "end": "2027-01-03", "step": {"value": 1, "unit": "d"}}
    )
    found = gm.case.Economics.from_dict(money, files={"p.csv": text}, time=time)
    assert found.energy.electricity.tolist() == pytest.approx([10 / 3.6e9, 20 / 3.6e9])
    assert found.files()["p.csv"].decode().splitlines()[1] == "2027-01-01T00:00:00+00:00,10.0"


def test_the_old_names_of_the_prices_are_unknown_keys(money):
    """opex.electricity is energy.electricity."""
    money["opex"]["electricity"] = copy.deepcopy(money["energy"]["electricity"])
    with raises(gm.errors.ValidationError, "unknown_name"):
        gm.case.Economics.from_dict(money)


def test_check_judges_a_changed_value_like_a_file(money):
    """A rate above one hundred percent of a share is out of bounds through check."""
    found = gm.case.Economics.from_dict(money)
    assert found.check() == []
    with raises(gm.errors.ValidationError, "out_of_bounds"):
        found.with_value("accounting.allocation.heat_cost_share", 1.5)


def test_a_later_cost_of_a_depth_table_is_checked_like_the_first(money):
    """A negative cost in the second row is refused, naming the cost column."""
    money["capex"]["drilling"] = {
        "depth": {"value": [1000, 2000], "unit": "m"},
        "cost_per_metre": {"value": [1000, -100], "unit": "EUR/m"},
    }
    with raises(gm.errors.ValidationError, "out_of_bounds", match="capex.drilling.cost_per_metre"):
        gm.case.Economics.from_dict(money)
