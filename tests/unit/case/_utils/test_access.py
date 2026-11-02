"""Reading a value of a case, or the error that names its path."""

import numpy as np
import pytest

import gemini as gm
from gemini.case._utils import access
from tests.fixtures.errors import raises


def test_a_present_value_is_returned(case):
    """Paths walk attributes and dicts."""
    assert access.require(case, "site.reservoir.thickness") == 100.0
    assert access.require(case, "economics.opex.fixed.heat_pump") == pytest.approx(0.02)


def test_an_absent_value_names_its_path(case):
    """``missing_value`` outside the economics."""
    with raises(gm.errors.ValidationError, "missing_value") as caught:
        access.require(case, "site.reservoir.temperature")
    assert caught.value.path == "site.reservoir.temperature"
    assert "has no default" in str(caught.value)


def test_an_absent_assumption_is_missing_assumption(case):
    """The code follows the first part of the path."""
    with raises(gm.errors.ValidationError, "missing_assumption") as caught:
        access.require(case, "economics.capex.boiler")
    assert caught.value.path == "economics.capex.boiler"
    with raises(gm.errors.ValidationError, "missing_assumption"):
        access.require(case, "economics.opex.fixed.boiler")


def test_a_prefix_completes_the_path(case):
    """A section read on its own still names the whole path."""
    with raises(gm.errors.ValidationError, "missing_value") as caught:
        access.require(case.site, "air.humidity", "site")
    assert caught.value.path == "site.air.humidity"


def test_a_series_repeats_a_constant_on_every_step(case):
    """The air is constant in the sample; the result has one value per step."""
    values = access.series(case, "site.air.temperature")
    assert np.allclose(values, 283.15) and len(values) == 7
