"""``gm.case.missing``: what a case or a partial case document still lacks."""

import gemini as gm
from gemini.errors.base import Issue


def paths(found):
    """Return the paths of a list of issues."""
    return [item.path for item in found]


def test_an_empty_document_lacks_the_header_and_the_time():
    """The three header keys and the three keys of time, in the order of the file."""
    found = gm.case.missing({})
    assert paths(found) == ["format", "kind", "name", "time.start", "time.end", "time.step"]
    assert all(isinstance(item, Issue) and item.kind == "missing" for item in found)


def test_a_value_with_a_dimension_names_its_quantity_and_its_units():
    """The step is a duration; the units are those of the one table."""
    step = gm.case.missing({})[-1]
    assert step.quantity == "duration" and step.accepted == tuple(gm.units.names("duration"))
    assert step.problem()["code"] == "missing_value"


def test_a_given_section_needs_its_required_leaves_and_an_absent_one_nothing():
    """The power of a service; a requirement needs its name, role and quantity."""
    data = {
        "format": 1,
        "kind": "case",
        "name": "x",
        "time": {"start": "2020-01-01", "end": "2020-01-02", "step": {"value": 1, "unit": "h"}},
        "demand": {"heating": {}, "cooling": {"power": {"value": 1, "unit": "kW"}}},
        "requirements": [{"name": "a"}, "text"],
    }
    found = gm.case.missing(data)
    assert paths(found) == [
        "demand.heating.power",
        "requirements[0].on",
        "requirements[0].quantity",
    ]
    assert found[0].quantity == "power" and "kW" in found[0].accepted
    assert gm.case.missing({k: v for k, v in data.items() if k != "demand"})[0].path == (
        "requirements[0].on"
    )


def test_an_economics_in_the_case_needs_its_header_and_a_file_name_is_not_looked_into():
    """An inline economics has a header; the path of a file is left to the reader."""
    assert paths(gm.case.missing({"economics": {}}))[-3:] == [
        "economics.format",
        "economics.kind",
        "economics.name",
    ]
    assert not any(
        p.startswith("economics") for p in paths(gm.case.missing({"economics": "e.json"}))
    )


def test_a_complete_case_lacks_nothing_and_nothing_raises():
    """A ``Case`` gives an empty list; whatever is not a document gives the header and time."""
    from tests.fixtures.cases import make_case

    assert gm.case.missing(make_case()) == []
    assert len(gm.case.missing(None)) == 6 == len(gm.case.missing(["x"]))
    assert gm.case.missing({"time": 3, "site": "file.json", "demand": 4}) == gm.case.missing({})[
        :3
    ] + [item for item in gm.case.missing({}) if item.path.startswith("time.")]
