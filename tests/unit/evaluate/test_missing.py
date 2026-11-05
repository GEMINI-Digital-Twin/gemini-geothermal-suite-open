"""``gm.evaluate.missing``: every value of the economics the costs of a run need, at once."""

import json

import pytest

import gemini as gm
from tests.fixtures.paths import EXAMPLES

SAMPLE = EXAMPLES / "hackathon_2026"


@pytest.fixture(scope="module")
def run():
    """Return the sample plant, its case and a run of it."""
    case = gm.Case.from_json(SAMPLE / "case.json")
    plant = gm.Plant.from_json(SAMPLE / "plants/HeatingCoolingPlant.json")
    return plant, case, gm.simulate(plant, case)


def _without(case, *names):
    """Return ``case`` with the economics lacking the top-level keys ``names``."""
    economics = {key: value for key, value in case.economics.to_dict().items() if key not in names}
    return gm.Case.from_dict(case.to_dict() | {"economics": economics}, files=case.files())


def test_a_complete_case_misses_nothing(run):
    """The sample case gives every value its costs need."""
    plant, case, results = run
    assert gm.evaluate.missing(plant, case, results) == []


def test_every_missing_value_is_listed_in_one_call(run):
    """Each cost raises its first missing value; the list holds all of them, as issues."""
    plant, case, results = run
    found = gm.evaluate.missing(plant, _without(case, "discount_rate", "capex", "revenue"), results)
    paths = [item.path for item in found]
    assert {"economics.discount_rate", "economics.revenue.heat"} <= set(paths)
    assert {"economics.capex.heat_pump", "economics.capex.boiler"} <= set(paths)
    assert len(paths) == len(set(paths))
    assert all(item.kind == "missing" and item.code == "missing_assumption" for item in found)
    with pytest.raises(gm.errors.ValidationError, match="discount_rate"):
        gm.evaluate.lcts(plant, _without(case, "discount_rate"), results)


def test_a_case_without_economics_starts_with_it(run):
    """The economics itself comes first, then what each cost needs from it."""
    plant, case, results = run
    data = {key: value for key, value in case.to_dict().items() if key != "economics"}
    bare = gm.Case.from_dict(data, files=case.files())
    paths = [item.path for item in gm.evaluate.missing(plant, bare, results)]
    assert paths[0] == "economics"
    assert {"economics.discount_rate", "economics.analysis_period"} <= set(paths)


def test_the_issues_are_plain_json(run):
    """An issue reads as the problem shape of every error."""
    plant, case, results = run
    found = gm.evaluate.missing(plant, _without(case, "discount_rate"), results)
    assert json.loads(json.dumps([item.problem() for item in found]))[0]["path"] == (
        "economics.discount_rate"
    )
