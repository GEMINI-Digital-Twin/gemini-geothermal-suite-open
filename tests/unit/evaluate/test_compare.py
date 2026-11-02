"""Ranking and the Pareto front of several reports."""

import json

import pytest

import gemini as gm
from gemini.evaluate.compare import Comparison
from gemini.types.shapes import measure
from gemini.units import Quantity
from tests.fixtures.errors import raises


def reports():
    """Return four designs by cost and emissions; the third is beaten by the first."""
    figures = [(10.0, 5.0), (8.0, 9.0), (12.0, 6.0), (20.0, 1.0)]
    return [{"lcts": measure(cost, "currency/J"), "co2": co2} for cost, co2 in figures]


def test_one_metric_ranks_the_reports_and_its_best_is_the_front():
    """The smaller cost is rank 1; with one metric the front is its best."""
    found = gm.evaluate.compare(reports(), "lcts")
    assert [entry["ranks"]["lcts"] for entry in found] == [2, 1, 3, 4]
    assert [entry["pareto"] for entry in found] == [False, True, False, False]


def test_two_metrics_mark_the_pareto_front():
    """Design 2 (12, 6) is beaten by design 0 (10, 5); the others trade cost for emissions."""
    found = gm.evaluate.compare(reports(), ["lcts", "co2"])
    assert [entry["pareto"] for entry in found] == [True, True, False, True]
    assert [entry["ranks"] for entry in found][2] == {"lcts": 3, "co2": 3}
    assert found[0]["values"] == {"lcts": Quantity(10.0, "currency/J"), "co2": 5.0}


def test_a_value_is_a_quantity_in_si_and_the_comparison_is_json():
    """A report value in a display unit is stored in SI; to_dict dumps and from_dict restores."""
    given = [{"lcts": Quantity(50.0, "EUR/MWh").to("EUR/MWh"), "co2": measure(2.0, "kg")}]
    found = gm.evaluate.compare(given, ["lcts", "co2"])
    lcts = found[0]["values"]["lcts"]
    assert isinstance(lcts, Quantity) and str(lcts.unit) == "currency/J"
    assert lcts.value == pytest.approx(50.0 / 3.6e9)
    plain = found.to_dict()
    assert json.loads(json.dumps(plain, allow_nan=False)) == plain
    assert plain[0]["values"]["co2"] == {"value": 2.0, "unit": "kg"}
    again = Comparison.from_dict(plain)
    assert again[0]["values"] == found[0]["values"] and again[0]["ranks"] == found[0]["ranks"]


def test_a_metric_can_be_preferred_larger():
    """With the cost to minimise and the emissions to maximise, the front changes."""
    found = gm.evaluate.compare(reports(), {"lcts": "min", "co2": "max"})
    assert [entry["pareto"] for entry in found] == [False, True, False, False]


def test_equal_values_share_a_rank_and_both_stay_on_the_front():
    """Two identical designs do not dominate each other."""
    twins = [{"x": 1.0, "y": 2.0}, {"x": 1.0, "y": 2.0}, {"x": 2.0, "y": 3.0}]
    found = gm.evaluate.compare(twins, ["x", "y"])
    assert [entry["ranks"]["x"] for entry in found] == [1, 1, 3]
    assert [entry["pareto"] for entry in found] == [True, True, False]


def test_a_report_without_a_value_ranks_last_and_is_off_the_front():
    """A cost the case could not give."""
    mixed = reports() + [{"lcts": measure(None, "currency/J", "no cost"), "co2": 0.0}]
    found = gm.evaluate.compare(mixed, ["lcts", "co2"])
    assert found[4]["ranks"]["lcts"] == 5 and found[4]["values"]["lcts"] is None
    assert found[4]["pareto"] is False


def test_to_frame_has_a_row_per_report():
    """The metrics, their ranks and the front."""
    frame = gm.evaluate.compare(reports(), ["lcts", "co2"]).to_frame()
    assert list(frame.columns) == [
        "lcts [EUR/MWh]",
        "co2 [kt]",
        "rank_lcts",
        "rank_co2",
        "pareto",
        "feasible",
    ]
    assert frame.loc[1, "lcts [EUR/MWh]"] == pytest.approx(8.0 * 3.6e9)
    assert frame.loc[1, "co2 [kt]"] == pytest.approx(9e-6) and bool(frame.loc[3, "pareto"])


def test_to_frame_takes_the_units_given_and_keeps_a_metric_without_a_unit_in_si():
    """A unit replaces the display unit; the column carries it."""
    found = gm.evaluate.compare(reports() + [{"lcts": 1.0, "co2": 0.0, "n": 3.0}], ["lcts", "n"])
    frame = found.to_frame({"lcts": "EUR/kWh"})
    assert frame.loc[1, "lcts [EUR/kWh]"] == pytest.approx(8.0 * 3.6e6)
    assert "n" in frame.columns


def test_to_frame_refuses_a_unit_that_does_not_fit():
    """An unknown metric, a unit of another dimension, an unknown unit."""
    found = gm.evaluate.compare(reports(), ["lcts", "co2"])
    with raises(gm.errors.ValidationError, "invalid_value", match="units.lct"):
        found.to_frame({"lct": "EUR/MWh"})
    with raises(gm.errors.ValidationError, "invalid_unit"):
        found.to_frame({"lcts": "kt"})
    with raises(gm.errors.ValidationError, "invalid_unit"):
        found.to_frame({"co2": "nothing"})


def reason(name, kind="requirement"):
    """Return a reason of a verdict."""
    return {"kind": kind, "name": name, "message": f"{name} failed"}


def served(cost, *reasons, **parts):
    """Return a report of a given cost whose verdict has the given reasons."""
    verdict = {"feasible": not reasons, "reasons": list(reasons)}
    return {"lcts": measure(cost, "currency/J"), "verdict": verdict} | parts


def test_an_infeasible_report_is_never_on_the_front_and_ranks_after_the_feasible():
    """The cheapest report has a reason: it is not feasible, with the reason as given."""
    item = reason("heat.unmet")
    cheap = served(1.0, item)
    found = gm.evaluate.compare([cheap, served(5.0), served(9.0)], "lcts")
    assert [entry["pareto"] for entry in found] == [False, True, False]
    assert [entry["ranks"]["lcts"] for entry in found] == [3, 1, 2]
    assert found[0]["feasible"] is False and found[0]["reasons"] == [item]
    assert found[1]["feasible"] is True and "reasons" not in found[1]


def test_a_report_without_a_verdict_is_a_plain_table_and_is_feasible():
    """Only the verdict decides: a dict of figures has none."""
    found = gm.evaluate.compare([{"lcts": 3.0, "passed": False}, served(5.0)], "lcts")
    assert [entry["feasible"] for entry in found] == [True, True]


def test_the_infeasible_are_ordered_by_their_number_of_reasons_then_by_the_metric():
    """Two reasons rank after one, whatever the cost."""
    one = reason("a")
    many = served(1.0, one, one)
    few = served(9.0, one)
    found = gm.evaluate.compare([many, few, served(7.0)], "lcts")
    assert [entry["ranks"]["lcts"] for entry in found] == [3, 2, 1]


def test_an_unknown_metric_or_sense_is_refused():
    """The names that exist are suggested."""
    with raises(gm.errors.ValidationError, "unknown_name", match="lcts"):
        gm.evaluate.compare(reports(), ["lct"])
    with raises(gm.errors.ValidationError, "invalid_value", match="by.lcts"):
        gm.evaluate.compare(reports(), {"lcts": "smallest"})
    with raises(gm.errors.ValidationError, "invalid_value"):
        gm.evaluate.compare(reports(), [])
