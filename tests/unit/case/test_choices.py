"""``gm.case.Choices``: what a study may vary, each as a range."""

import copy

import gemini as gm
from tests.fixtures.errors import raises


def test_the_ranges_are_whole_counts_and_lengths_in_metres(case):
    """Counts as given, depth in SI, written as given."""
    assert isinstance(case.choices.doublets, gm.case.Range)
    assert (case.choices.depth.min, case.choices.depth.max) == (2000.0, 3500.0)
    assert case.to_dict()["choices"]["depth"]["min"] == {"value": 2000, "unit": "m"}


def test_a_depth_in_kilometres_is_converted_and_written_back_in_kilometres(data, files):
    """The unit given is kept."""
    data["choices"]["depth"] = {
        "min": {"value": 2, "unit": "km"},
        "max": {"value": 3.5, "unit": "km"},
    }
    case = gm.Case.from_dict(data, files=files)
    assert case.choices.depth.max == 3500.0
    assert case.to_dict()["choices"]["depth"]["max"] == {"value": 3.5, "unit": "km"}


def test_bad_ranges_are_refused(data, files):
    """A count below one, a fraction, an inverted range and a depth that is no length."""
    for key, value in (
        ("doublets", {"min": 0, "max": 3}),
        ("doublets", {"min": 1.5, "max": 3}),
        ("doublets", {"min": 3, "max": 1}),
        ("depth", {"min": {"value": 3, "unit": "m"}, "max": {"value": 1, "unit": "m"}}),
        ("depth", {"min": {"value": 3, "unit": "bar"}, "max": {"value": 5, "unit": "bar"}}),
        ("depth", {"min": 1, "max": 2}),
    ):
        bad = copy.deepcopy(data)
        bad["choices"][key] = value
        with raises(gm.errors.ValidationError, bad_code(key, value)):
            gm.Case.from_dict(bad, files=files)


def bad_code(key, value):
    """Return the code of the first issue of a bad range."""
    if key == "doublets":
        return "out_of_bounds" if value["min"] in (0, 1.5) else "invalid_value"
    return "invalid_unit" if value["min"] == 1 or value["min"]["unit"] == "bar" else "invalid_value"
