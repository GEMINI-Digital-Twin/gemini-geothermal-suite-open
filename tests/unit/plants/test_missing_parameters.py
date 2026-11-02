"""A plant says what it still needs: each missing path with its quantity, units and meaning."""

import pytest

import gemini as gm
from tests.fixtures.errors import raises


def test_a_bare_plant_lists_every_missing_path_with_a_description():
    """``check`` has one ``missing`` issue per unset parameter, and each says what it means."""
    plant = gm.plants.HeatingPlant()
    missing = plant.check()
    paths = [item.path for item in missing]
    assert {
        "params.d0.esp.stage_count",
        "params.peak_boiler.capacity",
        "params.heat_exchanger.thermal_conductance",
    } <= set(paths)
    assert {item.kind for item in missing} == {"missing"}
    assert all(": " in item.message.split("no value", 1)[1] for item in missing)
    stages = missing[paths.index("params.d0.esp.stage_count")]
    assert stages.quantity == "count"
    capacity = missing[paths.index("params.peak_boiler.capacity")]
    assert "[W]" in capacity.message and "kW" in capacity.accepted
    assert all(isinstance(unit, str) for item in missing for unit in item.accepted)


def test_a_missing_value_error_lists_every_path_at_once():
    """Reading one unset value names all of them, each with its meaning."""
    plant = gm.plants.HeatingPlant()
    paths = [item.path.removeprefix("params.") for item in plant.check()]
    with pytest.raises(gm.errors.ValidationError) as caught:
        plant.d0.esp.power_function(0.01, 50)
    error = caught.value
    assert error.code == "missing_value"
    assert [item["path"] for item in error.problems] == paths
    assert "Number of stages of the pump" in str(error)


def test_a_set_value_leaves_the_list():
    """A parameter that has a value is no longer missing."""
    plant = gm.plants.Doublet()
    plant.esp.stage_count = 10
    assert "params.esp.stage_count" not in [item.path for item in plant.check()]
    with raises(gm.errors.ValidationError, "missing_value", match="uninitialized"):
        plant.esp.power_function(0.01, 50)


REMOVED_DEFAULTS = {
    "degasser.nominal_pressure_drop": "Pressure drop across the vessel at the nominal flow",
    "degasser.separation_efficiency": (
        "Share of the inlet free gas that leaves through the gas outlet"
    ),
    "filters.hot.nominal_mass_flow": "Mass flow at which the clean-filter pressure drop holds",
    "heat_exchanger.arrangement": "Flow arrangement of the two streams",
    "heating_return_pipe.roughness": "Absolute roughness of the inner pipe wall",
    "flare.combustion_efficiency": "Share of the flared gas burned completely",
    "d0.drainage_radius": "Radius of the drainage area around each well",
    "d0.well.heat_transfer_coefficient": (
        "Overall heat transfer coefficient from the fluid to the soil"
    ),
    "d0.reservoir.skin": "Dimensionless skin factor of the near-well zone",
}


def test_a_value_the_modules_no_longer_default_is_missing_with_its_description():
    """A design value left out is listed and named in the error, never filled in silently."""
    plant = gm.plants.HeatingPlant()
    described = {item.path.removeprefix("params."): item.message for item in plant.check()}
    for path, description in REMOVED_DEFAULTS.items():
        assert described[path].endswith(description)
    with raises(gm.errors.ValidationError, "missing_value") as caught:
        plant.degasser.nominal_pressure_drop
    named = {item["path"] for item in caught.value.problems}
    assert set(REMOVED_DEFAULTS) <= named


def test_a_switch_is_empty_and_means_off_until_it_is_set():
    """A threshold has no value, not a number: no alarm, and no missing parameter."""
    plant = gm.plants.HeatingPlant()
    paths = {item.path.removeprefix("params.") for item in plant.check()}
    assert plant.heat_exchanger.fouling_threshold is None
    assert plant.filters.hot.clogging_pressure_drop is None
    assert plant.d0.reservoir.decline_threshold is None
    assert not {"heat_exchanger.fouling_threshold", "d0.reservoir.decline_threshold"} & paths


def test_a_tank_has_no_start_of_its_own():
    """The start of a tank is a state of the case, not a parameter: without it a run raises."""
    tank = gm.modules.ThermalStorage()
    assert "initial_temperature" not in dict(tank.named_parameters())
    with raises(gm.errors.ValidationError, "missing_value", match="case.initial_state"):
        tank.initial_state()
