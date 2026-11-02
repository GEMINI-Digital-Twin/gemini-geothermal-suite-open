"""``gm.case.Requirement``: the role-based rule of a third party."""

import pytest

import gemini as gm
from tests.fixtures.errors import raises


def read(item, data, files):
    """Return the requirements of the shared case with ``item`` as the only one."""
    return gm.Case.from_dict({**data, "requirements": [item]}, files=files).requirements[0]


FLOW = {
    "name": "flow",
    "on": "doublet",
    "quantity": "production_flow",
    "unit": "m3/h",
    "over": "each",
}


def test_a_requirement_is_read_in_si_and_written_as_given(case):
    """Bounds in the unit of the rule, SI inside."""
    first = case.requirements[0]
    assert (first.on, first.quantity, first.over, first.when) == (
        "doublet",
        "production_flow",
        "each",
        "running",
    )
    assert first.min == pytest.approx(50 / 3600) and first.max == pytest.approx(300 / 3600)
    assert first.dimension == "volume_flow"
    assert first.to_dict() == case.to_dict()["requirements"][0]


def test_a_duration_rule_has_bounds_that_are_durations(case):
    """Over duration the unit is of time, not of the quantity."""
    rule = case.requirements[1]
    assert rule.dimension == "duration" and rule.max == 5 * 86400.0 and rule.min is None


def test_an_exact_rule_is_min_equal_to_max(case):
    """The pump efficiency is a property: no over, no when."""
    rule = case.requirements[2]
    assert (rule.min, rule.max, rule.over, rule.when) == (0.7, 0.7, None, None)
    assert "unit" not in rule.to_dict()


def test_equals_is_refused_with_min_and_max(data, files):
    """One form: the range."""
    item = {"name": "eff", "on": "doublet", "quantity": "pump_efficiency", "equals": 0.7}
    with raises(gm.errors.ValidationError, "old_format") as caught:
        read(item, data, files)
    assert '"min" and "max"' in str(caught.value) and caught.value.path == "requirements[0].equals"


def test_a_per_step_quantity_needs_over(data, files):
    """A missing over is a missing issue."""
    item = {k: v for k, v in FLOW.items() if k != "over"} | {"min": 1}
    with raises(gm.errors.ValidationError, "missing_value") as caught:
        read(item, data, files)
    assert caught.value.path == "requirements[0].over"


def test_a_window_quantity_takes_no_over_and_no_when(data, files):
    """Over the whole period there are no steps to reduce or to select."""
    item = {"name": "u", "on": "heating_supply", "quantity": "unmet_share", "max": 0.01}
    assert read(item, data, files).over is None
    for extra in ({"over": "sum"}, {"when": "running"}):
        with raises(gm.errors.ValidationError, "invalid_value"):
            read(item | extra, data, files)


def test_the_role_quantities_of_the_samples_exist(data, files):
    """reinjection_ratio and count of a doublet."""
    ratio = {
        "name": "r",
        "on": "doublet",
        "quantity": "reinjection_ratio",
        "over": "each",
        "when": "running",
        "min": 0.99,
        "max": 1.01,
    }
    assert read(ratio, data, files).dimension is None
    count = {"name": "c", "on": "doublet", "quantity": "count", "min": 1, "max": 3}
    assert read(count, data, files).over is None


def test_a_unit_is_present_if_and_only_if_the_bounds_have_a_dimension(data, files):
    """A missing unit and a unit on a number are both unit issues."""
    with raises(gm.errors.ValidationError, "invalid_unit"):
        read({k: v for k, v in FLOW.items() if k != "unit"} | {"min": 1}, data, files)
    item = {"name": "e", "on": "doublet", "quantity": "pump_efficiency", "unit": "K", "min": 0.7}
    with raises(gm.errors.ValidationError, "invalid_unit"):
        read(item, data, files)
    with raises(gm.errors.ValidationError, "invalid_unit"):
        read(FLOW | {"unit": "K", "min": 1}, data, files)


def test_the_name_is_snake_case_and_unique(data, files):
    """Names identify a requirement in the verdict."""
    with raises(gm.errors.ValidationError, "invalid_value"):
        read(FLOW | {"name": "Flow Range", "min": 1}, data, files)
    twice = [FLOW | {"min": 1}, FLOW | {"max": 2}]
    with raises(gm.errors.ValidationError, "duplicate_name"):
        gm.Case.from_dict({**data, "requirements": twice}, files=files)


def test_a_role_and_a_quantity_must_be_in_the_table(data, files):
    """The error lists the closed names and suggests the close one."""
    with raises(gm.errors.ValidationError, "invalid_value") as caught:
        read(FLOW | {"on": "doublets", "min": 1}, data, files)
    assert "doublet" in str(caught.value) and caught.value.issues[0].suggestions == ("doublet",)
    with raises(gm.errors.ValidationError, "invalid_value"):
        read(FLOW | {"quantity": "cop", "min": 1}, data, files)


def test_a_rule_needs_a_bound_in_order(data, files):
    """Min above max is refused, and so is no bound."""
    with raises(gm.errors.ValidationError, "invalid_value"):
        read(FLOW | {"min": 5, "max": 1}, data, files)
    with raises(gm.errors.ValidationError, "missing_value"):
        read(FLOW, data, files)


def test_a_requirement_is_built_alone_from_a_dict():
    """The same reader serves a requirement outside a case."""
    found = gm.case.Requirement.from_dict(FLOW | {"max": 1})
    assert found.max == pytest.approx(1 / 3600) and found.name == "flow"
    with raises(gm.errors.ValidationError, "unknown_name"):
        gm.case.Requirement.from_dict(FLOW | {"max": 1, "extra": 2})
