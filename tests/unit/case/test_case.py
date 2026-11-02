"""``gm.Case``: sections, SI storage, round trips, in-memory files, coverage and errors."""

import copy
import json

import pandas as pd
import pytest

import gemini as gm
from gemini.units import Quantity
from tests.fixtures.errors import raises
from tests.unit.case.conftest import codes, csv_text


def test_the_full_case_round_trips_through_a_dict_and_a_json_file(data, files, tmp_path):
    """to_dict, from_dict, to_json and from_json give an equal case."""
    case = gm.Case.from_dict(data, files=files)
    case.to_json(tmp_path / "out" / "case.json")
    assert gm.Case.from_dict(case.to_dict(), files=case.files()) == case
    assert gm.Case.from_json(tmp_path / "out" / "case.json") == case
    assert sorted(path.name for path in (tmp_path / "out").rglob("*") if path.is_file()) == [
        "case.json",
        "demand.csv",
    ]


def test_a_case_is_read_from_in_memory_files_without_a_folder(data, files):
    """A mapping of names to bytes serves the series, with no folder."""
    case = gm.Case.from_dict(data, files=files)
    assert case.demand.frame["heating_demand"].iloc[0] == pytest.approx(1e6)
    assert len(case.demand.frame) == 7


def test_an_economics_given_by_path_is_read_from_the_files_and_kept_a_path(data, files):
    """The case holds the economics and writes the path back, with the file next to it."""
    economics = data["economics"]
    data = {**data, "economics": "prices/economics.json"}
    files = {**files, "prices/economics.json": json.dumps(economics).encode()}
    case = gm.Case.from_dict(data, files=files)
    assert case.economics.currency == "EUR" and case.economics.name == "prices"
    assert case.to_dict()["economics"] == "prices/economics.json"
    assert json.loads(case.files()["prices/economics.json"]) == economics


def test_values_are_stored_in_si_and_written_as_given(case):
    """12 degC is 285.15 K inside and 12 degC in the file."""
    assert case.site.ground.surface_temperature == pytest.approx(285.15)
    assert case.demand.heating.supply_temperature == pytest.approx(373.15)
    assert case.to_dict()["site"]["ground"]["surface_temperature"] == {"value": 12, "unit": "degC"}
    assert list(case.to_dict()) == [
        "format",
        "kind",
        "name",
        "about",
        "time",
        "site",
        "demand",
        "utilities",
        "economics",
        "requirements",
    ]


def test_a_kw_series_keeps_its_unit_and_its_numbers_on_a_round_trip(tmp_path):
    """The old bug: a kW column came back as watts under the kW name, 1000 times too large."""
    data = {
        "format": 1,
        "kind": "case",
        "name": "kw",
        "time": {
            "start": "2026-01-12",
            "end": "2026-01-12T03:00:00Z",
            "step": {"value": 1, "unit": "h"},
        },
        "demand": {"heating": {"power": {"file": "data/d.csv", "column": "heat_kw", "unit": "kW"}}},
    }
    rows = ["2026-01-12T00:00:00Z,639", "2026-01-12T01:00:00Z,653", "2026-01-12T02:00:00Z,640"]
    text = "time,heat_kw\n" + "\n".join(rows) + "\n"
    case = gm.Case.from_dict(data, files={"data/d.csv": text.encode()})
    assert case.demand.frame["heating_demand"].tolist() == [639000.0, 653000.0, 640000.0]
    case.to_json(tmp_path / "case.json")
    written = pd.read_csv(tmp_path / "data" / "d.csv")
    assert written["heat_kw"].tolist() == [639.0, 653.0, 640.0]
    assert (
        json.loads((tmp_path / "case.json").read_text())["demand"]["heating"]["power"]["unit"]
        == "kW"
    )
    assert gm.Case.from_json(tmp_path / "case.json").demand.frame.equals(case.demand.frame)


def test_quantities_of_python_are_accepted_for_the_json_objects(data, files):
    """A ``Quantity`` is the Python form of ``{"value", "unit"}``."""
    data["site"]["ground"]["surface_temperature"] = Quantity(12, "degC")
    case = gm.Case.from_dict(data, files=files)
    assert case.to_dict()["site"]["ground"]["surface_temperature"] == {"value": 12, "unit": "degC"}


def test_an_old_section_is_refused_with_the_name_of_the_new_form(data, files):
    """environment, constraints and assumptions are old_format and name their replacement."""
    for old, new in (
        ("environment", "site"),
        ("constraints", "requirements"),
        ("assumptions", "economics"),
    ):
        with raises(gm.errors.ValidationError, "old_format") as caught:
            gm.Case.from_dict({**data, old: {}}, files=files)
        assert new in str(caught.value) and caught.value.path == old


def test_a_file_without_a_header_is_old_format(data, files):
    """The header `kind` tells the new shape."""
    del data["kind"]
    with raises(gm.errors.ValidationError, "old_format"):
        gm.Case.from_dict(data, files=files)
    data["kind"] = "plant"
    with raises(gm.errors.ValidationError, "invalid_format"):
        gm.Case.from_dict(data, files=files)


def test_every_issue_is_reported_in_one_error(data, files):
    """Two wrong values and an unknown key come back together."""
    data["site"]["ground"]["gradient"]["unit"] = "m"
    data["site"]["rock"] = {}
    data["demand"]["heating"]["supply_temperature"] = 100
    with pytest.raises(gm.errors.ValidationError) as caught:
        gm.Case.from_dict(data, files=files)
    assert sorted(codes(caught.value)) == sorted(
        [
            ("site.ground.gradient.unit", "invalid_unit"),
            ("site.rock", "unknown_name"),
            ("demand.heating.supply_temperature", "invalid_unit"),
        ]
    )
    assert len(caught.value.issues) == 3


def test_a_series_that_does_not_cover_the_period_is_a_coverage_issue(data):
    """The issue names the file, the column, the window covered and the window asked."""
    files = {"data/demand.csv": csv_text(days=4).encode()}
    with raises(gm.errors.ValidationError, "invalid_data") as caught:
        gm.Case.from_dict(data, files=files)
    issue = caught.value.issues[0]
    assert issue.kind == "coverage" and issue.path == "demand.heating.power"
    for text in (
        "data/demand.csv",
        "heat_MW",
        "2027-01-05T00:00:00+00:00",
        "2027-01-08T00:00:00+00:00",
    ):
        assert text in issue.message


def test_a_coarser_step_averages_and_a_finer_one_is_an_issue(data, files):
    """A daily series on a two-day step averages pairs; an hourly step is refused."""
    data["time"] = {"start": "2027-01-01", "end": "2027-01-07", "step": {"value": 2, "unit": "d"}}
    case = gm.Case.from_dict(data, files=files)
    heat = [1e6 * value for value in (1.0, 1.5, 2.0, 2.5, 3.0, 3.5)]
    assert case.demand.frame["heating_demand"].tolist() == pytest.approx(
        [(heat[0] + heat[1]) / 2, (heat[2] + heat[3]) / 2, (heat[4] + heat[5]) / 2]
    )
    data["time"] = {"start": "2027-01-01", "end": "2027-01-02", "step": {"value": 1, "unit": "h"}}
    with raises(gm.errors.ValidationError, "invalid_value") as caught:
        gm.Case.from_dict(data, files=files)
    assert caught.value.issues[0].kind == "incompatible"


def test_check_returns_the_issues_and_never_raises(case):
    """An object read from a file is ready; one changed to a bad value is not, and check says so."""
    assert case.check() == []
    bad = case.with_value("site.fluid.density", 1030.0)
    assert bad.check() == []
    with raises(gm.errors.ValidationError, "out_of_bounds"):
        case.with_value("site.reservoir.thickness", -5.0)


def test_a_value_is_replaced_by_its_path_and_a_series_becomes_a_constant(case):
    """with_value copies the case; the original stays."""
    changed = case.with_value("economics.energy.electricity", 3e-8)
    assert (
        changed.economics.energy.electricity == 3e-8 and case.economics.energy.electricity != 3e-8
    )
    constant = case.with_value("demand.heating.power", 5e6)
    assert constant.demand.frame["heating_demand"].tolist() == [5e6] * 7
    assert case.leaf("site.ground.gradient").unit == "K/km"
    assert case.field("site.ground.gradient").quantity == "temperature_gradient"
    with raises(gm.errors.ValidationError, "unknown_name"):
        case.with_value("site.nowhere", 1.0)


def test_the_uncertainty_of_each_value_is_indexed_by_its_path(case):
    """The declared uncertainty is in SI under the dotted path."""
    found = case.uncertainty
    assert list(found) == ["site.ground.gradient"]
    assert found["site.ground.gradient"].std == pytest.approx(0.002)
    assert found["site.ground.gradient"].min == pytest.approx(0.025)


def test_a_case_is_immutable(case):
    """No attribute can be set."""
    with pytest.raises(AttributeError):
        case.name = "other"
    with pytest.raises(AttributeError):
        case.site.ground.gradient = 1.0


def test_the_initial_state_is_a_map_of_modules_to_states(data, files):
    """Each state is a value with a unit the plant gives a dimension to."""
    data["initial_state"] = {
        "storage": {"temperature": {"value": 60, "unit": "degC"}, "fill": {"value": 0.5}}
    }
    case = gm.Case.from_dict(data, files=files)
    assert case.initial_state["storage"]["temperature"].si == pytest.approx(333.15)
    assert case.to_dict()["initial_state"] == data["initial_state"]
    data["initial_state"]["storage"]["fill"] = {"value": 0.5, "unit": "nope"}
    with raises(gm.errors.ValidationError, "invalid_unit"):
        gm.Case.from_dict(data, files=files)


def test_a_case_without_economics_or_requirements_is_a_pure_physics_case(data, files):
    """Both are absent, not empty."""
    for key in ("economics", "requirements"):
        del data[key]
    case = gm.Case.from_dict(data, files=files)
    assert case.economics is None and case.requirements is None
    assert "economics" not in case.to_dict() and case.check() == []


def test_the_old_choices_key_is_refused_naming_the_plant_range(data, files):
    """``choices`` moved to a ``range`` on the plant leaves."""
    data["choices"] = {"doublets": {"min": 1, "max": 3}}
    with raises(gm.errors.ValidationError, "old_format") as refused:
        gm.Case.from_dict(data, files=files)
    assert "range" in str(refused.value) and refused.value.path == "choices"


def test_the_unreadable_file_is_invalid_format(tmp_path):
    """A missing file and a non-object are invalid_format."""
    with raises(gm.errors.ValidationError, "invalid_format"):
        gm.Case.from_json(tmp_path / "none.json")
    (tmp_path / "case.json").write_text("[1]")
    with raises(gm.errors.ValidationError, "invalid_format"):
        gm.Case.from_json(tmp_path / "case.json")


def test_a_missing_series_file_is_a_missing_issue(data):
    """The path of the leaf and the name of the file."""
    with raises(gm.errors.ValidationError, "missing_value") as caught:
        gm.Case.from_dict(copy.deepcopy(data), files={})
    assert "data/demand.csv" in str(caught.value)
