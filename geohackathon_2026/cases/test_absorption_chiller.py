"""Hand-calculation tests for the absorption chiller model."""

import pytest
from absorption_chiller import AbsorptionChiller


def test_calibration_point_matches_published_cop():
    """At 85 C generator, 6 C evaporator and 35 C rejection, COP should be about 0.7."""
    chiller = AbsorptionChiller()
    chiller.update_parameters(
        {"cop_cap": 1.0, "evaporator_approach_c": 0.0, "hot_water_outlet_c": 85.0}
    )
    # 0.5 * (1 - 308.15 / 358.15) * 279.15 / 29 = 0.672
    assert chiller.calculate_cop(85.0, 6.0) == pytest.approx(0.672, abs=0.001)


def test_warm_chilled_water_reaches_the_cap():
    """A 20 C chilled supply should reach the capped COP with 100 C hot water."""
    chiller = AbsorptionChiller()
    assert chiller.calculate_cop(100.0, 20.0) == pytest.approx(0.67)


def test_energy_balance():
    """Rejected heat should equal cooling plus drive heat."""
    chiller = AbsorptionChiller()
    chiller.calculate_output({"cooling_w": 10e6, "hot_water_in_c": 100.0, "chilled_supply_c": 20.0})
    output = chiller.get_output()
    assert output["drive_heat_w"] == pytest.approx(10e6 / 0.67)
    assert output["heat_rejected_w"] == pytest.approx(10e6 + 10e6 / 0.67)
    assert output["power_el"] == pytest.approx(0.4e6)


def test_cop_stays_below_ideal():
    """COP should never exceed the ideal three-temperature COP."""
    chiller = AbsorptionChiller()
    chiller.update_parameters({"cop_cap": 10.0})
    for hot_water_c in (75.0, 85.0, 95.0, 105.0):
        generator = (hot_water_c + 70.0) / 2 + 273.15
        ideal = (1 - 308.15 / generator) * 288.15 / 20.0
        assert chiller.calculate_cop(hot_water_c, 20.0) < ideal


def test_too_cold_drive_is_rejected():
    """A drive below the minimum generator temperature should raise an error."""
    chiller = AbsorptionChiller()
    assert chiller.minimum_generator_temperature(20.0) == pytest.approx(65.0)
    with pytest.raises(ValueError):
        chiller.calculate_output({"cooling_w": 1e6, "hot_water_in_c": 55.0, "chilled_supply_c": 20.0})


def test_cop_rises_with_drive_temperature_below_the_cap():
    """Below the cap, hotter drive water should give a higher COP."""
    chiller = AbsorptionChiller()
    chiller.update_parameters({"cop_cap": 10.0})
    assert chiller.calculate_cop(90.0, 20.0) > chiller.calculate_cop(75.0, 20.0)
