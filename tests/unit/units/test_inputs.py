"""The shared formats of the input files: every leaf form, issue kind and the round trip."""

import json

import numpy as np
import pandas as pd
import pytest

from gemini.errors.base import ValidationError, raise_issues
from gemini.units import inputs

CSV = b"time,heat_kw,other\n2030-01-01T00:00:00Z,1000,1\n2030-01-01T01:00:00Z,2000,2\n"


def leaf(data, **kwargs):
    """Return ``(leaf, issues)`` of one read."""
    issues = []
    return inputs.from_leaf(data, "x", issues, **kwargs), issues


def kinds(issues):
    """Return the kinds of a list of issues."""
    return [issue.kind for issue in issues]


def test_a_quantity_keeps_its_unit_and_gives_si():
    """A quantity keeps its unit and gives si."""
    found, issues = leaf({"value": 3, "unit": "km"}, quantity="length")
    assert issues == []
    assert found.si == 3000 and found.unit == "km"
    assert inputs.to_json(found) == {"value": 3, "unit": "km"}


def test_a_dimensionless_and_a_choice_are_objects():
    """A dimensionless and a choice are objects."""
    assert leaf({"value": 0.7})[0].si == 0.7
    found, _ = leaf({"value": "counterflow"}, choices=("counterflow", "parallel"))
    assert inputs.to_json(found) == {"value": "counterflow"}


@pytest.mark.parametrize(
    "data, kwargs, kind",
    [
        (3000, {"quantity": "length"}, "unit"),
        ("150 m3/h", {"quantity": "volume_flow"}, "unit"),
        ({"value": 3}, {"quantity": "length"}, "unit"),
        ({"value": 3, "unit": "bar"}, {"quantity": "length"}, "unit"),
        ({"value": 3, "unit": "m"}, {}, "unit"),
        (0.7, {}, "missing"),
        ({"unit": "m"}, {"quantity": "length"}, "missing"),
        ({"value": "x"}, {"choices": ("a", "b")}, "not_allowed"),
        ({"value": "a", "range": {"min": 1}}, {"choices": ("a",)}, "incompatible"),
        ({"value": 1, "options": ["a"]}, {}, "incompatible"),
        ({"value": 1, "colour": 2}, {}, "unknown_key"),
        ({"value": True}, {}, "incompatible"),
    ],
)
def test_a_wrong_leaf_is_one_issue_of_its_kind(data, kwargs, kind):
    """A wrong leaf is one issue of its kind."""
    found, issues = leaf(data, **kwargs)
    assert found is None
    assert kinds(issues) == [kind]
    assert issues[0].path.startswith("x")


def test_a_unit_issue_names_the_quantity_and_the_accepted_units():
    """A unit issue names the quantity and the accepted units."""
    _, issues = leaf({"value": 3, "unit": "bar"}, quantity="length")
    assert issues[0].quantity == "length" and "m" in issues[0].accepted


def test_an_unknown_key_suggests_the_closest_and_about_is_kept():
    """An unknown key suggests the closest and about is kept."""
    _, issues = leaf({"value": 1, "rnge": {}})
    assert issues[0].suggestions == ("range",)
    found, issues = leaf({"value": 1, "about": {"note": "free"}})
    assert issues == [] and found is not None


def test_a_range_has_either_side_in_the_unit_of_the_leaf():
    """A range has either side in the unit of the leaf."""
    found, _ = leaf({"value": 2, "unit": "km", "range": {"min": 1}}, quantity="length")
    assert found.range_si.min == 1000 and found.range_si.max is None
    assert inputs.to_json(found)["range"] == {"min": 1}
    _, issues = leaf({"value": 2, "range": {"min": 3, "max": 1}})
    assert kinds(issues) == ["incompatible"]


def test_bounds_refuse_a_value_and_a_range_outside():
    """Bounds refuse a value and a range outside."""
    bounds = inputs.Range(0, 10)
    _, issues = leaf({"value": 20, "range": {"min": -1, "max": 5}}, bounds=bounds)
    assert kinds(issues) == ["out_of_bounds", "out_of_bounds"]


def test_options_are_a_subset_of_the_choices():
    """Options are a subset of the choices."""
    found, _ = leaf({"value": "a", "options": ["a", "b"]}, choices=("a", "b", "c"))
    assert found.options == ("a", "b")
    _, issues = leaf({"value": "a", "options": ["a", "z"]}, choices=("a", "b"))
    assert kinds(issues) == ["not_allowed"]


@pytest.mark.parametrize(
    "spread",
    [
        {"kind": "uniform", "min": 1, "max": 3},
        {"kind": "triangular", "min": 1, "max": 3},
        {"kind": "normal", "std": 0.5},
        {"kind": "normal", "std": 0.5, "min": 1, "max": 3},
    ],
)
def test_every_uncertainty_kind_round_trips(spread):
    """Every uncertainty kind round trips."""
    found, issues = leaf({"value": 2, "uncertainty": spread})
    assert issues == [] and inputs.to_json(found)["uncertainty"] == spread


@pytest.mark.parametrize(
    "spread, kind",
    [
        ({"kind": "gauss"}, "not_allowed"),
        ({"kind": "uniform", "min": 1}, "missing"),
        ({"kind": "normal"}, "missing"),
        ({"kind": "normal", "std": 0}, "out_of_bounds"),
        ({"kind": "uniform", "min": 3, "max": 1}, "incompatible"),
        ({"kind": "uniform", "min": 3, "max": 4}, "out_of_bounds"),
        ({"kind": "uniform", "min": 1, "max": 3, "std": 1}, "unknown_key"),
    ],
)
def test_a_wrong_uncertainty_is_an_issue(spread, kind):
    """A wrong uncertainty is an issue."""
    _, issues = leaf({"value": 2, "uncertainty": spread})
    assert kinds(issues) == [kind]


def test_uncertainty_in_si_converts_bounds_and_scales_std():
    """Uncertainty in si converts bounds and scales std."""
    found, _ = leaf(
        {"value": 20, "unit": "degC", "uncertainty": {"kind": "normal", "std": 2}},
        quantity="temperature",
    )
    assert found.uncertainty_si.std == pytest.approx(2)


def test_a_series_reads_from_a_mapping_and_from_disk_by_one_path(tmp_path):
    """A series reads from a mapping and from disk by one path."""
    spec = {"file": "data/d.csv", "column": "heat_kw", "unit": "kW"}
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "d.csv").write_bytes(CSV)
    from_disk, _ = leaf(spec, quantity="power", source=inputs.Source(root=tmp_path))
    from_memory, _ = leaf(spec, quantity="power", source=inputs.Source(files={"data/d.csv": CSV}))
    assert np.array_equal(from_disk.si, from_memory.si)
    assert list(from_disk.si) == [1e6, 2e6]


def test_a_series_in_kw_round_trips_exactly():
    """A series in kw round trips exactly."""
    spec = {"file": "d.csv", "column": "heat_kw", "unit": "kW"}
    found, _ = leaf(spec, quantity="power", source=inputs.Source(files={"d.csv": CSV}))
    assert inputs.to_json(found) == spec
    again, issues = leaf(
        spec,
        quantity="power",
        source=inputs.Source(files={"d.csv": found.series.to_csv().encode()}),
    )
    assert issues == []
    assert list(again.series.values) == [1000.0, 2000.0] and again.series.unit == "kW"
    assert list(again.si) == [1e6, 2e6]


@pytest.mark.parametrize(
    "csv, kind",
    [
        (b"when,heat_kw\n2030-01-01T00:00:00Z,1\n", "incompatible"),
        (b"time,heat_kw\n2030-01-01T00:00:00,1\n", "incompatible"),
        (b"time,heat_kw\nyesterday,1\n", "incompatible"),
        (b"time,heat_kw\n2030-01-01T00:00:00Z,1\n2030-01-01T00:00:00Z,2\n", "incompatible"),
        (b"time,heat_kw\n2030-01-01T01:00:00Z,1\n2030-01-01T00:00:00Z,2\n", "incompatible"),
        (b"time,heat_kw\n2030-01-01T00:00:00Z,\n", "missing"),
        (b"time,heat_kw\n2030-01-01T00:00:00Z,abc\n", "incompatible"),
        (b"time,heat_kw\n", "missing"),
        (b"time,other\n2030-01-01T00:00:00Z,1\n", "unknown_key"),
    ],
)
def test_a_wrong_csv_is_an_issue(csv, kind):
    """A wrong csv is an issue."""
    spec = {"file": "d.csv", "column": "heat_kw", "unit": "kW"}
    found, issues = leaf(spec, quantity="power", source=inputs.Source(files={"d.csv": csv}))
    assert found is None and kinds(issues) == [kind]


def test_a_missing_file_is_an_issue():
    """A missing file is an issue."""
    spec = {"file": "no.csv", "column": "c", "unit": "kW"}
    _, issues = leaf(spec, quantity="power", source=inputs.Source())
    assert kinds(issues) == ["missing"]


def test_the_offset_of_a_timestamp_is_kept_as_utc():
    """The offset of a timestamp is kept as utc."""
    csv = b"time,v\n2030-01-01T01:00:00+01:00,5\n"
    found, _ = leaf({"file": "d.csv", "column": "v"}, source=inputs.Source(files={"d.csv": csv}))
    assert found.series.time[0] == pd.Timestamp("2030-01-01T00:00:00Z")


DAILY = b"time,heating_demand_MWth\n2027-01-01,24.313\n2027-01-02,22.984\n2027-01-03,23.5\n"
"""The shape of the daily demand of the hackathon: dates without an offset."""


def test_a_time_zone_reads_dates_without_an_offset_as_local_times():
    """``time_zone`` makes a date or a time without an offset local in the named zone."""
    spec = {"file": "d.csv", "column": "heating_demand_MWth", "time_zone": "Europe/Oslo"}
    found, issues = leaf(spec, source=inputs.Source(files={"d.csv": DAILY}))
    assert issues == []
    assert found.series.time[0] == pd.Timestamp("2026-12-31T23:00:00Z")
    assert list(found.series.values) == [24.313, 22.984, 23.5]
    assert found.series.to_json()["time_zone"] == "Europe/Oslo"
    utc, _ = leaf(spec | {"time_zone": "UTC"}, source=inputs.Source(files={"d.csv": DAILY}))
    assert utc.series.time[0] == pd.Timestamp("2027-01-01T00:00:00Z")
    hours = b"time,v\n2030-07-01T00:00,1\n2030-07-01T01:00:00+00:00,2\n"
    mixed, _ = leaf(
        {"file": "d.csv", "column": "v", "time_zone": "Europe/Oslo"},
        source=inputs.Source(files={"d.csv": hours}),
    )
    assert list(mixed.series.time) == [
        pd.Timestamp("2030-06-30T22:00:00Z"),
        pd.Timestamp("2030-07-01T01:00:00Z"),
    ]


def test_without_a_time_zone_a_time_without_an_offset_is_refused():
    """No default zone: the file as today is refused."""
    spec = {"file": "d.csv", "column": "heating_demand_MWth"}
    found, issues = leaf(spec, source=inputs.Source(files={"d.csv": DAILY}))
    assert found is None and "has no offset" in issues[0].message
    assert (
        "time_zone"
        not in leaf(
            {"file": "d.csv", "column": "v"},
            source=inputs.Source(files={"d.csv": b"time,v\n2030-01-01T00:00:00Z,1\n"}),
        )[0].series.to_json()
    )


@pytest.mark.parametrize(
    "time", ["2027-03-28T02:30", "2027-10-31T02:30"], ids=["nonexistent", "ambiguous"]
)
def test_a_local_time_the_clock_does_not_show_once_is_refused(time):
    """A time skipped or repeated at a change of the clock in the zone is an issue."""
    csv = f"time,v\n{time},1\n".encode()
    spec = {"file": "d.csv", "column": "v", "time_zone": "Europe/Oslo"}
    found, issues = leaf(spec, source=inputs.Source(files={"d.csv": csv}))
    assert found is None and "ambiguous or does not exist in Europe/Oslo" in issues[0].message


@pytest.mark.parametrize("zone", ["Mars/Olympus", "", 5])
def test_an_unknown_time_zone_is_refused(zone):
    """A name that is no IANA zone is an issue at ``time_zone``."""
    spec = {"file": "d.csv", "column": "heating_demand_MWth", "time_zone": zone}
    found, issues = leaf(spec, source=inputs.Source(files={"d.csv": DAILY}))
    assert found is None and issues[0].path == "x.time_zone"


def series(step_hours, count, value=lambda i: float(i)):
    """Return a dimensionless series of ``count`` steps."""
    time = pd.date_range("2030-01-01", periods=count, freq=f"{step_hours}h", tz="UTC")
    return inputs.Series("d.csv", "v", None, time, np.array([value(i) for i in range(count)]))


def test_align_averages_a_coarser_target_step():
    """Align averages a coarser target step."""
    issues = []
    index = pd.date_range("2030-01-01", periods=2, freq="2h", tz="UTC")
    got = inputs.align(series(1, 4), index, pd.Timedelta("2h"), "x", issues)
    assert issues == [] and list(got) == [0.5, 2.5]


def test_align_returns_the_same_step_and_refuses_a_finer_one():
    """Align returns the same step and refuses a finer one."""
    index = pd.date_range("2030-01-01", periods=3, freq="1h", tz="UTC")
    issues = []
    assert list(inputs.align(series(1, 3), index, pd.Timedelta("1h"), "x", issues)) == [0, 1, 2]
    fine = pd.date_range("2030-01-01", periods=2, freq="30min", tz="UTC")
    assert inputs.align(series(1, 3), fine, pd.Timedelta("30min"), "x", issues) is None
    assert kinds(issues) == ["incompatible"]


def test_align_on_the_same_step_returns_each_sample_with_no_rounding_from_its_neighbours():
    """A cumulative sum would turn a value after a large one into the difference of two sums."""
    values = [16.777, 4.017, 4.108, 0.1, 22.984]
    time = pd.date_range("2030-01-01", periods=5, freq="1h", tz="UTC")
    held = inputs.Series("d.csv", "v", "MW", time, np.array(values), "power")
    index = pd.date_range("2030-01-01", periods=5, freq="1h", tz="UTC")
    got = inputs.align(held, index, pd.Timedelta("1h"), "x", [])
    assert list(got) == list(np.array(values) * 1e6)


def test_align_reports_coverage_naming_file_column_and_both_windows():
    """Align reports coverage naming file column and both windows."""
    issues = []
    index = pd.date_range("2030-01-01", periods=5, freq="1h", tz="UTC")
    assert inputs.align(series(1, 3), index, pd.Timedelta("1h"), "x", issues) is None
    message = issues[0].message
    assert kinds(issues) == ["coverage"]
    assert (
        "d.csv" in message and "'v'" in message and "03:00:00" in message and "05:00:00" in message
    )


def test_a_header_of_the_right_kind_is_read_and_written():
    """A header of the right kind is read and written."""
    issues = []
    head = inputs.from_header(
        {"format": 1, "kind": "case", "name": "n", "about": {"site": "s"}}, "case", "f", issues
    )
    assert issues == []
    assert inputs.to_json(head) == {
        "format": 1,
        "kind": "case",
        "name": "n",
        "about": {"site": "s"},
    }


@pytest.mark.parametrize(
    "data, code",
    [
        ({"format": 2, "name": "n"}, "old_format"),
        ({"format": 1, "kind": "plant", "name": "n"}, "invalid_format"),
        ({"format": 7, "kind": "case", "name": "n"}, "old_format"),
    ],
)
def test_a_wrong_header_is_refused_naming_the_new_form(data, code):
    """A wrong header is refused naming the new form."""
    issues = []
    assert inputs.from_header(data, "case", "f", issues) is None
    assert (
        issues[0].problem()["code"] == code
        and '"format": 1' in issues[0].message
        or code == "invalid_format"
    )


def test_a_header_without_a_name_is_missing():
    """A header without a name is missing."""
    issues = []
    inputs.from_header({"format": 1, "kind": "case"}, "case", "f", issues)
    assert kinds(issues) == ["missing"]


def test_a_section_is_an_object_or_a_path_relative_to_its_file(tmp_path):
    """A section is an object or a path relative to its file."""
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "eco.json").write_text(json.dumps({"a": 1}))
    issues = []
    data, source = inputs.from_section(
        "sub/eco.json", "case.economics", inputs.Source(tmp_path), issues
    )
    assert data == {"a": 1} and source.base == "sub" and issues == []
    mapped = inputs.Source(files={"sub/eco.json": b'{"a": 2}'})
    assert inputs.from_section("sub/eco.json", "p", mapped, issues)[0] == {"a": 2}
    assert inputs.from_section({"b": 1}, "p", mapped, issues)[0] == {"b": 1}
    assert inputs.from_section("gone.json", "p", mapped, issues)[0] is None
    assert kinds(issues) == ["missing"]


def test_a_section_path_inside_a_section_file_starts_from_its_folder():
    """A section path inside a section file starts from its folder."""
    files = {"sub/eco.json": b'{"s": "../top.json"}', "top.json": b'{"t": 1}'}
    source = inputs.Source(files=files)
    issues = []
    _, inner = inputs.from_section("sub/eco.json", "p", source, issues)
    assert inputs.from_section("../top.json", "p", inner, issues)[0] == {"t": 1}


def test_every_issue_of_a_file_is_reported_at_once():
    """Every issue of a file is reported at once."""
    issues = []
    inputs.from_leaf({"value": 1, "unit": "m"}, "a", issues)
    inputs.from_leaf(5, "b", issues, quantity="length")
    inputs.from_leaf({"value": "z"}, "c", issues, choices=("y",))
    with pytest.raises(ValidationError) as caught:
        raise_issues(issues)
    error = caught.value
    assert [problem["path"] for problem in error.problems] == ["a.unit", "b", "c.value"]
    assert [issue.kind for issue in error.issues] == ["unit", "unit", "not_allowed"]
    assert error.code == "invalid_unit" and error.path == "a.unit"


def test_check_keys_reports_every_unknown_key():
    """Check keys reports every unknown key."""
    issues = []
    assert not inputs.check_keys({"vlaue": 1, "zzz": 2}, ("value",), "p", issues)
    assert [issue.path for issue in issues] == ["p.vlaue", "p.zzz"]
    assert issues[0].suggestions == ("value",)
