"""The public list of metrics."""

import json

import gemini as gm
from gemini.evaluate._utils.display import METRICS


def test_metrics_are_the_private_list_with_quantity_and_unit():
    """Names and order of the private table, a display unit for each."""
    listed = gm.evaluate.metrics()
    assert [item["name"] for item in listed] == list(METRICS)
    assert {item["name"]: item["quantity"] for item in listed} == METRICS
    units = {item["name"]: item["unit"] for item in listed}
    assert units["heat_delivered"] == "MWh" and units["payback"] == "yr"
    assert json.loads(json.dumps(listed)) == listed


def test_a_metric_has_a_title_and_says_whether_it_is_an_objective():
    """Costs and emissions are targets; a temperature, a flow, a delivered energy is not."""
    found = {item["name"]: item for item in gm.evaluate.metrics()}
    assert found["lcoh"]["title"] == "Cost of heat" and found["lcoh"]["objective"] is True
    assert all(
        found[name]["objective"] is False for name in ("temperature", "flow", "heat_delivered")
    )
    assert all(isinstance(item["title"], str) and item["title"] for item in found.values())


def test_every_objective_is_a_metric_that_minimize_reads():
    """A metric flagged as an objective never fails in ``checked_metric``."""
    from gemini.study._utils.trial import checked_metric

    for item in gm.evaluate.metrics():
        if item["objective"]:
            assert checked_metric(item["name"]) == item["name"]
