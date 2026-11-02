"""The operating limits of a module against a run."""

import pytest

import gemini as gm
from gemini.evaluate._utils.operating import breaches
from gemini.units import Quantity
from tests.fixtures.cases import make_case
from tests.unit.evaluate.test_totals import overflowing


def limited(sense, held):
    """Return the boiler plant with a limit on its fuel power and the run."""
    plant, run = overflowing()
    plant.boiler.capacity = Quantity(held, "W")
    plant.boiler.operating_limits = (("fuel", sense, "capacity"),)
    return gm.run._utils.apply.apply_case(plant, make_case()), run


def test_a_maximum_is_breached_above_and_a_minimum_below():
    """The boiler burns about 2.2 MW: a maximum of 1 MW is breached, a minimum of 1 MW is not."""
    plant, run = limited("max", 1e6)
    (found,) = breaches(plant, run.to_frame())
    assert found["path"] == "boiler" and found["output"] == "fuel" and found["sense"] == "max"
    assert found["worst"].value > found["limit"].value == pytest.approx(1e6)
    plant, run = limited("min", 1e6)
    assert breaches(plant, run.to_frame()) == []
    plant, run = limited("min", 1e7)
    assert len(breaches(plant, run.to_frame())) == 1


def test_a_module_without_limits_has_none():
    """The default is the empty tuple."""
    plant, run = overflowing()
    assert plant.boiler.operating_limits == () and breaches(plant, run.to_frame()) == []
