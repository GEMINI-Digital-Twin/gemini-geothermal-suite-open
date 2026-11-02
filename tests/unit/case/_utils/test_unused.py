"""A ``range`` on a case or economics leaf is read, changes nothing, and is warned about."""

import copy
import json
import warnings

import pytest

import gemini as gm
from tests.fixtures.sample_cases import HACKATHON_2026, SHALLOW_DISTRICT, shallow_case

SPREAD = {"min": 5, "max": 20}
PLANT = SHALLOW_DISTRICT / "plants/HeatingHeatPumpCoolingPlant.json"


def with_range(data, files):
    """Return ``(data, files)`` with a ``range`` on a site value, an economics value, a series."""
    data = copy.deepcopy(data)
    data["site"]["ground"]["surface_temperature"]["range"] = SPREAD
    data["economics"]["discount_rate"]["range"] = {"min": 0.01, "max": 0.1}
    data["demand"]["heating"]["power"]["range"] = {"min": 0, "max": 5}
    return data, files


def deprecated(issues):
    """Return the paths of the ``deprecated`` issues."""
    return sorted(item.path for item in issues if item.kind == "deprecated")


def read(data, files):
    """Return the case of ``data``, recording the ``GeminiWarning`` messages emitted."""
    with pytest.warns(gm.errors.GeminiWarning) as caught:
        case = gm.Case.from_dict(data, files=files)
    return case, [str(item.message) for item in caught]


def test_a_case_and_an_economics_range_are_deprecated_issues_of_the_check(data, files):
    """The path is that of the range; the message says where a range belongs."""
    case, _ = read(*with_range(data, files))
    issues = case.check()
    assert deprecated(issues) == [
        "demand.heating.power.range",
        "economics.discount_rate.range",
        "site.ground.surface_temperature.range",
    ]
    assert all(
        item.code == "deprecated" or item.problem()["code"] == "deprecated" for item in issues
    )
    text = issues[0].message
    assert "plant leaf" in text and "uncertainty" in text and "later version" in text
    assert deprecated(case.economics.check()) == ["economics.discount_rate.range"]


def test_the_standalone_economics_and_a_referenced_economics_report_it(data, files):
    """An economics file in its own file gets the path of the economics."""
    economics = data["economics"]
    economics["capex"]["drilling"]["range"] = {"min": 100, "max": 2000}
    data = data | {"economics": "prices/economics.json"}
    files = files | {"prices/economics.json": json.dumps(economics).encode()}
    with pytest.warns(gm.errors.GeminiWarning, match="economics.capex.drilling.range"):
        case = gm.Case.from_dict(data, files=files)
    assert deprecated(case.check()) == ["economics.capex.drilling.range"]
    with pytest.warns(gm.errors.GeminiWarning):
        alone = gm.case.Economics.from_dict(economics)
    assert deprecated(alone.check()) == ["economics.capex.drilling.range"]


def test_reading_still_works_and_warns_once_per_range(data, files):
    """No ``ValidationError``; one ``GeminiWarning`` naming each path."""
    case, messages = read(*with_range(data, files))
    assert case.site.ground.surface_temperature == pytest.approx(285.15)
    assert len(messages) == 3
    assert "site.ground.surface_temperature.range" in " ".join(messages)
    assert all("later version" in message for message in messages)
    assert case.to_dict()["site"]["ground"]["surface_temperature"]["range"] == SPREAD


def test_a_range_in_a_series_leaf_is_the_same_case(data, files):
    """A column with a ``range`` reads and warns."""
    case, messages = read(*with_range(data, files))
    assert case.demand.heating.power is not None
    assert any("demand.heating.power.range" in message for message in messages)


def test_uncertainty_and_requirement_bounds_are_not_deprecated(data, files):
    """Only the key ``range`` is; ``min`` and ``max`` of requirements and uncertainty stay."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", gm.errors.GeminiWarning)
        case = gm.Case.from_dict(data, files=files)
    assert case.uncertainty and case.requirements and case.check() == []


def test_the_samples_give_no_warning():
    """No sample case and no sample economics carries a ``range``."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", gm.errors.GeminiWarning)
        for folder in (SHALLOW_DISTRICT, HACKATHON_2026):
            for path in sorted(folder.glob("case*.json")):
                assert gm.Case.from_json(path).check() == []


def test_gm_check_passes_the_warning_on_and_the_rest_unchanged():
    """The plant is ready: the list holds only the ``deprecated`` issue, which stops nothing."""
    data = shallow_case().to_dict()
    data["economics"] = shallow_case().economics.to_dict()
    data["site"]["air"]["temperature"]["range"] = {"min": -5, "max": 20}
    with pytest.warns(gm.errors.GeminiWarning):
        case = gm.Case.from_dict(data, files=shallow_case().files())
    issues = gm.check(gm.Plant.from_json(PLANT), case)
    assert [(item.kind, item.path) for item in issues] == [
        ("deprecated", "site.air.temperature.range")
    ]
    broken = gm.check(gm.Plant(), case)
    assert deprecated(broken) == ["site.air.temperature.range"] and len(broken) > 1
