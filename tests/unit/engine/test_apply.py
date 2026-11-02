"""The values of a case reach the modules of a plant by class, on a copy."""

import pytest

import gemini as gm
from gemini.engine.apply import applied_in_place, apply_case
from gemini.units import Quantity
from tests.fixtures.errors import raises
from tests.fixtures.sample_cases import sample_case, sample_json, template_dict


def sample_plant():
    """Return the sample design without any value of the case."""
    return gm.Plant.from_dict(template_dict("HeatingCoolingPlant"))


def without(case, *path):
    """Return ``case`` as it reads without the value (or section) at ``path`` of its dict."""
    data = case.to_dict()
    node = data
    for part in path[:-1]:
        node = node[part]
    del node[path[-1]]
    return gm.Case.from_dict(data, files=case.files())


def test_the_plant_of_the_user_never_changes():
    """The values are set on a copy."""
    plant = sample_plant()
    before = plant.state_dict()
    applied = apply_case(plant, sample_case())
    assert plant.state_dict() == before and applied is not plant
    assert plant.d0.gradient is None and applied.d0.gradient == pytest.approx(0.03)


def test_the_ground_and_the_reservoir_reach_every_doublet_at_its_depth():
    """Temperature and pressure are the rules of the case at the depth of the doublet."""
    case = sample_case()
    plant = sample_plant()
    plant.set_params("", {"depth": Quantity(3000, "m")})
    applied = apply_case(plant, case)
    for doublet in (applied.d0, applied.d1):
        assert doublet.reservoir.temperature == pytest.approx(case.site.temperature_at(3000))
        assert doublet.sink.pressure == pytest.approx(case.site.pressure_at(3000))
        assert doublet.reservoir.permeability == case.site.reservoir.permeability


def test_the_brine_of_the_case_is_the_fluid_of_every_doublet_module():
    """Density, viscosity and the dissolved gas of ``site.fluid``."""
    applied = apply_case(sample_plant(), sample_case())
    fluid = applied.d1.well.fluid
    assert fluid.density == 1030.0 and fluid.gas_liquid_ratio == 0.8
    assert fluid.gas_composition == {"CH4": 0.8, "CO2": 0.2}


def test_the_same_plant_on_two_reservoirs_gives_two_production_temperatures():
    """Only the case differs."""
    plant = sample_plant()
    hot = apply_case(plant, sample_case().with_value("site.ground.gradient", 0.04))
    cold = apply_case(plant, sample_case())
    assert hot.d0.reservoir.temperature > cold.d0.reservoir.temperature


def test_a_given_reservoir_temperature_anchors_the_geotherm():
    """The measured temperature at the reference depth is shifted by the gradient."""
    case = sample_case().with_value("site.reservoir.temperature", 350.0)
    applied = apply_case(sample_plant(), case)
    assert applied.d0.reservoir.temperature == pytest.approx(350.0)


def test_the_air_is_an_input_of_every_atmosphere_and_a_profile_waits_for_the_plan():
    """A constant is set on the copy; a profile is no input."""
    applied = apply_case(sample_plant(), sample_case())
    assert applied.input_value("atmosphere.temperature") == pytest.approx(283.15)
    assert sample_plant().input_value("atmosphere.temperature") is None


def test_the_return_and_the_required_supply_reach_the_consumers():
    """Heating asks a minimum supply, cooling a maximum; both return temperatures are set."""
    applied = apply_case(sample_plant(), sample_case())
    assert applied.heating_consumer.return_temperature == pytest.approx(333.15)
    assert applied.heating_consumer.minimum_supply_temperature == pytest.approx(373.15)
    assert applied.cooling_consumer.return_temperature == pytest.approx(298.15)
    assert applied.cooling_consumer.maximum_supply_temperature == pytest.approx(293.15)


def test_a_formation_outside_a_doublet_gets_the_ground():
    """``Formation`` takes the gradient and the surface temperature."""
    plant = gm.plants.NodalDoublet()
    applied = apply_case(plant, sample_case())
    assert applied.formation.geothermal_gradient == pytest.approx(0.03)
    assert applied.formation.surface_temperature == pytest.approx(285.15)


def test_a_value_the_plant_needs_and_the_case_lacks_is_named_by_its_path():
    """A plant without its site raises ``missing_value`` naming the path in the case."""
    case = without(sample_case(), "site")
    with raises(gm.errors.ValidationError, "missing_value") as caught:
        apply_case(sample_plant(), case)
    assert caught.value.path == "site.fluid.density"
    case = without(sample_case(), "site", "ground", "gradient")
    with raises(gm.errors.ValidationError, "missing_value") as caught:
        apply_case(sample_plant(), case)
    assert caught.value.path == "site.ground.gradient"


def test_a_copy_that_carries_the_case_is_not_copied_again():
    """``applied_in_place`` sets the values on the plant; ``apply_case`` of that case keeps it."""
    case = sample_case()
    plant = gm.Plant.from_dict(template_dict("HeatingCoolingPlant"))
    applied = applied_in_place(plant, case)
    assert applied is plant and plant.d0.gradient == pytest.approx(0.03)
    assert apply_case(plant, case) is plant
    other = gm.Case.from_dict(case.to_dict(), files=case.files())
    assert apply_case(plant, other) is not plant
    assert apply_case(sample_plant(), case) is not plant


def test_the_grid_gas_is_the_composition_of_the_case_and_is_required():
    """``utilities.gas.composition`` reaches every ``GasGrid``; without it the path is named."""
    case = sample_case()
    applied = apply_case(sample_plant(), case)
    assert applied.gas_grid.composition == case.utilities.gas.composition
    with raises(gm.errors.ValidationError, "missing_value") as caught:
        apply_case(sample_plant(), without(case, "utilities", "gas"))
    assert caught.value.path == "utilities.gas.composition"


def test_the_consumer_conditions_come_from_the_demand():
    """Return pressure, the dew point margin and the indoor state are the consumer's."""
    applied = apply_case(sample_plant(), sample_case())
    assert applied.heating_consumer.return_pressure == pytest.approx(6e5)
    assert applied.cooling_consumer.return_pressure == pytest.approx(4e5)
    assert applied.cooling_consumer.dew_point_margin == pytest.approx(1.0)
    assert applied.input_value("cooling_consumer.indoor_temperature") == pytest.approx(299.15)
    assert applied.input_value("cooling_consumer.indoor_relative_humidity") == 0.5
    assert sample_plant().cooling_consumer.dew_point_margin is None


def test_a_return_limit_of_the_demand_reaches_the_consumer():
    """The limits are optional: given, they are set."""
    case = sample_case().with_value("demand.heating.minimum_return_temperature", 303.15)
    case = case.with_value("demand.cooling.maximum_return_temperature", 291.15)
    applied = apply_case(sample_plant(), case)
    assert applied.heating_consumer.minimum_return_temperature == pytest.approx(303.15)
    assert applied.cooling_consumer.maximum_return_temperature == pytest.approx(291.15)


def test_the_air_pressure_is_required_where_there_is_an_atmosphere():
    """``site.air.pressure`` reaches every ``Atmosphere``; a plant without one needs none."""
    case = sample_case()
    assert apply_case(sample_plant(), case).atmosphere.pressure == 101325.0
    bare = without(case, "site", "air", "pressure")
    with raises(gm.errors.ValidationError, "missing_value") as caught:
        apply_case(sample_plant(), bare)
    assert caught.value.path == "site.air.pressure"
    assert apply_case(gm.plants.NodalDoublet(), bare).formation is not None


def test_the_sand_of_the_brine_is_the_boundary_of_every_desander():
    """``site.fluid.sand_concentration`` in kg/m3 (20 mg/l is 0.02 kg/m3)."""
    plant = gm.Plant.from_dict(sample_json("plants/HackathonPlant.json"))
    applied = apply_case(plant, sample_case().with_value("site.fluid.sand_concentration", 0.02))
    assert applied.input_value("desander.sand_concentration") == pytest.approx(0.02)
    assert plant.input_value("desander.sand_concentration") is None


def test_the_connection_limits_of_the_grid_are_the_utilities_of_the_case():
    """Given, ``import_limit`` and ``export_limit`` reach the electricity grid; else unlimited."""
    free = apply_case(sample_plant(), sample_case())
    assert free.electricity_grid.import_limit is None and free.electricity_grid.export_limit is None
    case = sample_case().with_value("utilities.electricity.import_limit", 6e6)
    case = case.with_value("utilities.electricity.export_limit", 2e6)
    limited = apply_case(sample_plant(), case)
    assert limited.electricity_grid.import_limit == 6e6
    assert limited.electricity_grid.export_limit == 2e6


def test_a_unit_on_a_supply_line_regulates_to_the_supply_temperature_plus_its_margin():
    """Heating adds the margin, cooling takes it; 0 K gives the supply temperature itself."""
    plant = sample_plant()
    applied = apply_case(plant, sample_case())
    assert applied.input_value("heat_pump.temperature_setpoint") == 373.15
    assert applied.input_value("peak_boiler.temperature_setpoint") == 373.15
    assert applied.input_value("compression_chiller.temperature_setpoint") == 293.15
    assert plant.input_value("heat_pump.temperature_setpoint") is None
    plant.set_params("", {"heat_pump.supply_margin": Quantity(5, "K")})
    plant.set_params("", {"compression_chiller.supply_margin": Quantity(2, "K")})
    applied = apply_case(plant, sample_case())
    assert applied.input_value("heat_pump.temperature_setpoint") == pytest.approx(378.15)
    assert applied.input_value("compression_chiller.temperature_setpoint") == pytest.approx(291.15)


def test_a_cooler_keeps_its_own_setpoint():
    """A setpoint that equals no value of the case is an absolute control of the plant."""
    applied = apply_case(sample_plant(), sample_case())
    assert applied.input_value("compression_cooler.temperature_setpoint") == pytest.approx(298.15)


def test_a_margin_on_a_unit_that_is_on_no_supply_line_is_refused():
    """The boiler feeds nothing: its margin has nothing to refer to."""
    plant = gm.Plant("Alone")
    plant.add("Boiler", name="boiler", params={"supply_margin": Quantity(0, "K")})
    with raises(gm.errors.ValidationError, "invalid_design") as caught:
        apply_case(plant, sample_case())
    assert caught.value.path == "boiler.supply_margin"


def test_a_margin_needs_the_supply_temperature_of_the_case():
    """Without ``demand.heating.supply_temperature`` the margin has nothing to add to."""
    bare = without(sample_case(), "demand", "heating", "supply_temperature")
    with raises(gm.errors.ValidationError, "missing_value") as caught:
        apply_case(sample_plant(), bare)
    assert caught.value.path == "demand.heating.supply_temperature"
