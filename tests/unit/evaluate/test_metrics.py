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
