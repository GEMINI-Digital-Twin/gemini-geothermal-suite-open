"""A gas from its composition: densities, heating value, CO2 and the gas-liquid ratio."""

import pytest

from gemini import ops
from gemini.errors import PhysicsError
from gemini.physics import combustion, constants, gas
from tests.fixtures.equivalence import assert_function_matches, assert_same_error
from tests.fixtures.gas import GRID_COMPOSITION

METHANE = {"CH4": 1.0}
PRODUCED = {"CH4": 0.8, "CO2": 0.2}


def test_molar_mass_is_the_mole_weighted_sum():
    """80 % CH4 and 20 % CO2 weigh 21.636 g/mol."""
    assert gas.molar_mass(METHANE) == pytest.approx(float(combustion.METHANE_MOLAR_MASS))
    assert gas.molar_mass(PRODUCED) == pytest.approx(0.0216364, rel=1e-5)


def test_ideal_gas_density():
    """Methane at normal conditions is 0.7158 kg/m3 as an ideal gas."""
    assert gas.ideal_gas_density(101325.0, 273.15, 0.016043) == pytest.approx(0.7158, abs=1e-3)
    rows = [(101325.0, 273.15, 0.016043), (2e5, 300.0, 0.0216364)]
    assert_function_matches(gas.ideal_gas_density, rows)


def test_normal_density_of_the_produced_gas():
    """A gas of 80 % CH4 and 20 % CO2 by mole is about 0.97 kg/Nm3."""
    assert gas.normal_density(PRODUCED) == pytest.approx(0.9653, abs=1e-3)


def test_the_reference_conditions_of_a_normal_density_are_arguments():
    """DIN 1343 normal conditions by default; the ISO 13443 standard ones, 15 degC, on request."""
    assert gas.normal_density(PRODUCED) == gas.normal_density(PRODUCED, 273.15, 101325.0)
    standard = gas.normal_density(PRODUCED, 288.15, 101325.0)
    assert standard == pytest.approx(gas.normal_density(PRODUCED) * 273.15 / 288.15)


def test_heating_value_of_methane_is_the_constant_of_combustion():
    """802.3 kJ/mol over 16.043 g/mol is the 50 MJ/kg of the existing flare constant."""
    assert gas.lower_heating_value(METHANE) == pytest.approx(combustion.METHANE_HEATING_VALUE, 1e-3)
    assert gas.lower_heating_value({"CO2": 0.5, "N2": 0.5}) == 0


def test_combustion_co2_counts_burnt_carbon_only():
    """A mole of methane forms a mole of CO2; the CO2 carried in the gas is not formed."""
    assert gas.combustion_co2(METHANE) == pytest.approx(
        float(constants.CO2_MOLAR_MASS) / float(combustion.METHANE_MOLAR_MASS)
    )
    assert gas.combustion_co2({"CO2": 1.0}) == 0
    assert gas.mass_fraction({"CO2": 1.0}, "CO2") == 1
    assert gas.mass_fraction(PRODUCED, "CO2") == pytest.approx(0.2 * 0.04401 / 0.0216364, 1e-4)
    assert gas.mass_fraction(PRODUCED, "N2") == 0


def test_grid_gas_agrees_with_its_published_analysis():
    """The lumped default keeps the published molar mass and CO2 factor within 1 %."""
    composition = GRID_COMPOSITION
    assert sum(composition.values()) == pytest.approx(1)
    assert gas.molar_mass(composition) == pytest.approx(0.0187155, rel=1e-2)
    factor = gas.combustion_co2(composition) / gas.lower_heating_value(composition)
    assert factor + gas.mass_fraction(composition, "CO2") / gas.lower_heating_value(
        composition
    ) == pytest.approx(56.474e-9, rel=1e-2)


def test_the_gas_liquid_ratio_and_the_mass_fraction_are_inverses():
    """0.8 Nm3/m3 of a 0.9653 kg/Nm3 gas in 1030 kg/m3 brine is 7.49e-4 of the mass."""
    fraction = gas.gas_mass_fraction(0.8, 0.9653, 1030.0)
    assert fraction == pytest.approx(7.492e-4, rel=1e-3)
    assert gas.gas_liquid_ratio(fraction, 0.9653, 1030.0) == pytest.approx(0.8)
    rows = [(0.8, 0.9653, 1030.0), (0.0, 0.9653, 1030.0)]
    assert_function_matches(gas.gas_mass_fraction, rows)
    assert_function_matches(gas.gas_liquid_ratio, [(7.49e-4, 0.9653, 1030.0), (0.0, 0.9, 1000.0)])


def test_species_flow_without_composition_is_zero_for_any_flow():
    """No composition gives zero, also for an infinite or NaN flow."""
    assert gas.species_flow(float("inf"), None, "CO2") == 0.0
    assert gas.species_flow(float("nan"), None, "CO2") == 0.0


def test_isentropic_and_actual_stage_temperatures():
    """Air (k = 1.4) at a pressure ratio of 8 from 300 K reaches 543.4 K isentropically."""
    ideal = gas.isentropic_outlet_temperature(300, 8, 1.4)
    assert ideal == pytest.approx(543.43, abs=0.01)
    assert gas.stage_outlet_temperature(300, 8, 1.4, 0.8) == pytest.approx(
        300 + (ideal - 300) / 0.8
    )
    assert gas.stage_outlet_temperature(300, 1, 1.4, 0.8) == 300


def test_multistage_work_splits_the_ratio_equally():
    """N intercooled stages do N times the work of one stage at the N-th root ratio."""
    one = gas.specific_compression_work(300, 4, 1.4, 1005, 0.8, 1)
    two = gas.specific_compression_work(300, 16, 1.4, 1005, 0.8, 2)
    assert two == pytest.approx(2 * one)
    assert two < gas.specific_compression_work(300, 16, 1.4, 1005, 0.8, 1)
    assert gas.specific_compression_work(300, 1, 1.4, 1005, 0.8, 3) == 0


@pytest.mark.parametrize(
    "arguments, match",
    [
        ((300, 0.5, 1.4, 1005, 0.8, 1), "pressure_ratio = 0.5"),
        ((0, 2, 1.4, 1005, 0.8, 1), "inlet_temperature = 0"),
        ((300, 2, 1.0, 1005, 0.8, 1), "heat_capacity_ratio = 1.0"),
        ((300, 2, 1.4, 1005, 0, 1), "isentropic_efficiency = 0"),
        ((300, 2, 1.4, 0.0, 0.8, 1), "specific_heat = 0"),
        ((300, 2, 1.4, 1005, 0.8, 0.0), "stages = 0"),
    ],
)
def test_out_of_domain_inputs_raise(arguments, match):
    """Expansion, nonpositive temperatures and invalid gas or machine data raise."""
    with pytest.raises(PhysicsError, match=match):
        gas.specific_compression_work(*arguments)


def test_functions_match_on_arrays():
    """Each compression function on arrays equals one call per row."""
    assert_function_matches(
        gas.isentropic_outlet_temperature, [(300, 8, 1.4), (350, 1, 1.3), (280, 2.5, 1.67)]
    )
    assert_function_matches(gas.stage_outlet_temperature, [(300, 8, 1.4, 0.8), (350, 1, 1.3, 1.0)])
    assert_function_matches(
        gas.specific_compression_work,
        [(300, 4, 1.4, 1005, 0.8, 1), (300, 16, 1.4, 1005, 0.8, 2), (320, 1, 1.3, 2000, 0.7, 3)],
    )


@pytest.mark.parametrize(
    "function, rows",
    [
        (gas.isentropic_outlet_temperature, [(300, 2, 1.4), (300, 2, 1.0)]),
        (gas.isentropic_outlet_temperature, [(300, 2, 1.4), (0.0, 2.0, 1.4)]),
        (gas.isentropic_outlet_temperature, [(300, 2, 1.4), (300, 0.5, 1.4)]),
        (gas.stage_outlet_temperature, [(300, 2, 1.4, 0.8), (300, 2, 1.4, 1.5)]),
        (
            gas.specific_compression_work,
            [(300, 2, 1.4, 1005, 0.8, 1.0), (300, 2, 1.4, 0.0, 0.8, 1.0)],
        ),
        (
            gas.specific_compression_work,
            [(300, 2, 1.4, 1005.0, 0.8, 1.0), (300, 2, 1.4, 1005.0, 0.8, 0.0)],
        ),
    ],
)
def test_checks_match_on_arrays(function, rows):
    """A failing row raises the same error and message on arrays and on floats."""
    assert_same_error(function, rows, PhysicsError)


@ops.physics
def _work_when_running(running, specific_heat):
    """Return the work of a compressor that is off (zero heat capacity) on some rows."""
    work = gas.specific_compression_work(300.0, 4.0, 1.4, specific_heat, 0.8, 2.0)
    return ops.where(running > 0, work, 0.0)


def test_a_failing_check_in_an_unselected_branch_is_dropped():
    """A stopped row with an invalid heat capacity gives zero on floats and on arrays."""
    rows = [(1.0, 1005.0), (0.0, 0.0), (0.0, -1.0)]
    assert_function_matches(_work_when_running, rows)


def test_stage_pressure_ratio_is_the_root_of_the_overall_ratio():
    """Four equal stages of ratio 2 give an overall ratio of 16."""
    assert gas.stage_pressure_ratio(16.0, 4) == pytest.approx(2.0)
    assert gas.stage_pressure_ratio(7.0, 1) == 7.0
    rows = [(16.0, 4.0), (7.0, 1.0), (1.0, 3.0), (30.0, 2.0)]
    assert_function_matches(gas.stage_pressure_ratio, rows)


def test_overall_ratio_power_and_heat_rejected():
    """A 4 bar to 12 bar machine has ratio 3; 2 kg/s at 100 kJ/kg is 200 kW and rejects 0.5 P/N."""
    assert gas.overall_pressure_ratio(12e5, 4e5) == pytest.approx(3)
    assert gas.shaft_power(2.0, 1e5) == pytest.approx(2e5)
    assert gas.heat_rejected(250e3, 200e3, 2) == pytest.approx(150e3)
    rows = [(250e3, 200e3), (0.0, 0.0)]
    assert_function_matches(gas.heat_rejected, rows, stages=2)
    assert_function_matches(gas.shaft_power, rows)
    assert_function_matches(gas.overall_pressure_ratio, [(12e5, 4e5), (1e5, 1e5)])


def test_hydrogen_sulfide_burns_to_so2_and_water_and_carries_no_carbon():
    """34.08 g/mol; LHV 518.1 kJ/mol from the formation enthalpies; no CO2 formed."""
    molar_mass, heating_value, carbon = gas.SPECIES["H2S"]
    assert molar_mass == pytest.approx(0.034081, rel=1e-4)
    assert heating_value == pytest.approx(-(-296.84 - 241.826 + 20.6) * 1e3, rel=1e-4)
    assert carbon == 0
    sour = {"CH4": 0.9, "H2S": 0.1}
    assert gas.lower_heating_value(sour) == pytest.approx(
        (0.9 * 802.3e3 + 0.1 * 518.07e3) / gas.molar_mass(sour), rel=1e-4
    )
    assert gas.combustion_co2({"H2S": 1.0}) == 0


def test_every_species_a_case_names_is_a_species_of_the_gas_code():
    """One source: the case reader never accepts a species that a stream would refuse."""
    from gemini.case._utils import kinds

    assert set(kinds.GAS_SPECIES) <= set(gas.SPECIES)
    assert tuple(kinds.GRID_GAS_SPECIES) == tuple(gas.SPECIES)
