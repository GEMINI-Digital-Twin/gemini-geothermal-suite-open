"""``gm.study.metrics``: the metrics a study reads, with their unit and meaning."""

import json

import pytest

import gemini as gm
from gemini.errors import ValidationError
from gemini.study._utils.trial import checked_metric, metric
from tests.unit.study.conftest import shallow_case, shallow_plant


def test_the_list_is_exactly_what_a_study_accepts():
    """Every listed name is accepted, the settings offer the same names, and nothing else passes."""
    found = gm.study.metrics()
    names = [item["name"] for item in found]
    assert len(names) == len(set(names)) and all(checked_metric(name) == name for name in names)
    settings = {item["kind"]: item["settings"] for item in gm.study.kinds()}
    assert settings["sample"]["properties"]["metrics"]["items"]["enum"] == names
    with pytest.raises(ValidationError) as error:
        checked_metric("not_a_metric")
    assert all(name in str(error.value) for name in names)
    objectives = settings["minimize"]["properties"]["objective"]["enum"]
    assert {item["name"] for item in found if item["objective"]} == set(objectives)


def test_each_metric_has_a_unit_a_title_a_description_and_a_direction():
    """Plain JSON, a new list on each call."""
    found = gm.study.metrics()
    for item in found:
        assert set(item) == {"name", "title", "unit", "description", "better", "objective"}
        assert item["title"] and item["description"].endswith(".")
        assert item["better"] in ("lower", "higher", None)
    assert json.loads(json.dumps(found)) == found and gm.study.metrics() is not found


def test_the_unit_is_the_unit_a_run_reports(tmp_path):
    """The unit of each metric is the unit of the value a study records for it."""
    plant, case = shallow_plant(), shallow_case(days=2, folder=tmp_path)
    results = gm.simulate(plant, case)
    for item in gm.study.metrics():
        assert metric(plant, case, results, item["name"]).unit == item["unit"], item["name"]


def test_a_title_is_the_title_a_table_shows():
    """A metric a table of ``gm.evaluate`` also shows has the same title there."""
    shown = {item["name"]: item["title"] for item in gm.evaluate.metrics()}
    for item in gm.study.metrics():
        assert shown.get(item["name"], item["title"]) == item["title"]
