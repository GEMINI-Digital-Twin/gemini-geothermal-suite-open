"""The base of the sections: reading through the shared leaf reader, the writer and the copies."""

import numpy as np
import pytest

import gemini as gm
from gemini.case._utils import node
from gemini.errors import ValidationError
from gemini.types import inputs
from tests.fixtures.errors import raises


class Tiny(node.Node):
    """A section of every kind of field."""

    where = "tiny"
    fields = {
        "length": node.Field("length", bounds=inputs.Range(min=0.0)),
        "share": node.Field(),
        "label": node.Field(text=True),
        "count": node.Field(integer=True),
        "mix": node.Field(keys=("a", "b"), total=1.0),
        "need": node.Field("power", series=True, required=True),
    }
    old = {"gone": "length"}


NEED = {"value": 1, "unit": "kW"}


def test_a_section_stores_si_and_writes_the_leaves_as_given():
    """Km stays km in the file; the attribute is in metres."""
    data = {
        "length": {"value": 2, "unit": "km"},
        "share": {"value": 0.5},
        "label": {"value": "x"},
        "count": {"value": 3},
        "mix": {"a": {"value": 0.25}, "b": {"value": 0.75}},
        "need": NEED,
        "about": {"note": 1},
    }
    found = Tiny.from_dict(data)
    assert (found.length, found.share, found.label, found.count) == (2000.0, 0.5, "x", 3)
    assert (
        found.mix == {"a": 0.25, "b": 0.75} and found.need == 1000.0 and found.about == {"note": 1}
    )
    assert found.to_dict() == data and Tiny.from_dict(found.to_dict()) == found


def test_every_problem_is_an_issue_and_none_raises_in_check():
    """Unknown and old keys, a required leaf, a bad count, a mix that does not add up."""
    data = {
        "length": {"value": -1, "unit": "m"},
        "count": {"value": 1.5},
        "mix": {"a": {"value": 0.5}},
        "gone": 1,
        "zzz": 1,
    }
    with pytest.raises(ValidationError) as caught:
        Tiny.from_dict(data)
    found = {(item["path"], item["code"]) for item in caught.value.problems}
    assert ("tiny.gone", "old_format") in found and ("tiny.zzz", "unknown_name") in found
    assert ("tiny.length", "out_of_bounds") in found and ("tiny.count", "invalid_value") in found
    assert ("tiny.mix", "out_of_bounds") in found and ("tiny.need", "missing_value") in found


def test_a_series_is_refused_where_none_is_allowed():
    """Only a field with series=True takes a file."""
    data = {"need": NEED, "length": {"file": "a.csv", "column": "m", "unit": "m"}}
    with raises(ValidationError, "invalid_value") as caught:
        Tiny.from_dict(data, files={"a.csv": b"time,m\n"})
    assert "no series" in str(caught.value)


def test_series_files_are_merged_one_csv_per_file():
    """Two columns of one file are written to one CSV with both columns."""
    series = [
        inputs.Series("d.csv", "a", "kW", _index(2), np.array([1.0, 2.0])),
        inputs.Series("d.csv", "b", "kW", _index(2), np.array([3.0, 4.0])),
    ]
    files = node.files_of(series, "sub")
    assert list(files) == ["sub/d.csv"]
    assert files["sub/d.csv"].decode().splitlines() == [
        "time,a,b",
        "2027-01-01T00:00:00+00:00,1.0,3.0",
        "2027-01-02T00:00:00+00:00,2.0,4.0",
    ]


def _index(days):
    """Return a UTC daily index."""
    import pandas as pd

    return pd.date_range("2027-01-01", periods=days, freq="D", tz="UTC")


def test_with_value_copies_and_refuses_values_out_of_bounds():
    """The copy is new, the original stays, a map key can be set."""
    found = Tiny.from_dict({"need": NEED, "mix": {"a": {"value": 1.0}}})
    other = found.with_value("length", 5.0).with_value("mix.b", 0.0)
    assert other.length == 5.0 and found.length is None and other.mix == {"a": 1.0, "b": 0.0}
    with raises(ValidationError, "out_of_bounds"):
        found.with_value("length", -1.0)
    with raises(ValidationError, "unknown_name"):
        found.with_value("nowhere", 1.0)
    assert Tiny.field("mix.a").keys == ("a", "b") and found.leaf("mix.a").value == 1.0


def test_a_quantity_of_python_is_turned_into_its_json_object():
    """plain() walks dicts and lists."""
    q = gm.units.Quantity(2, "km")
    assert node.plain({"a": [q], "b": q}) == {
        "a": [{"value": 2, "unit": "km"}],
        "b": {"value": 2, "unit": "km"},
    }


def test_a_section_cannot_be_changed():
    """Assignment and deletion are refused."""
    found = Tiny.from_dict({"need": NEED})
    with pytest.raises(AttributeError):
        found.length = 1.0
    with pytest.raises(AttributeError):
        del found.length


def test_load_and_write_round_trip_a_json_file(tmp_path):
    """Write puts the files next to the JSON; load refuses what is no object."""
    node.write(tmp_path / "a" / "x.json", {"k": 1}, {"data/d.csv": b"time\n"})
    assert node.load(tmp_path / "a" / "x.json") == {"k": 1}
    assert (tmp_path / "a" / "data" / "d.csv").read_bytes() == b"time\n"
    with raises(ValidationError, "invalid_format"):
        node.load(tmp_path / "a" / "data" / "d.csv")
