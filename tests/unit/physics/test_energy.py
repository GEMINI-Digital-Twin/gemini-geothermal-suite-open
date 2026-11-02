"""Energy conversion through an efficiency."""

import pytest

from gemini.physics import energy
from tests.fixtures.equivalence import assert_function_matches


def test_input_power_is_the_useful_power_over_the_efficiency():
    """A 90 % converter draws 1000 W for 900 W."""
    assert energy.input_power(900.0, 0.9) == 1000
    assert_function_matches(energy.input_power, [(900.0, 0.9), (0.0, 0.8)])


def test_the_circuit_flow_is_the_heat_over_its_capacity_rate():
    """A heat balance."""
    assert energy.circuit_flow(4e6, 4000.0, 40.0) == pytest.approx(25)
    assert_function_matches(energy.circuit_flow, [(4e6, 4000.0, 40.0), (0.0, 4000.0, 40.0)])


def test_the_temperature_moves_with_the_duty():
    """At a constant flow, a quarter of the duty is a quarter of the way."""
    assert energy.temperature_after(298.0, 290.0, 0.25) == 296
    assert_function_matches(energy.temperature_after, [(298.0, 290.0, 0.25), (280.0, 280.0, 1.0)])
