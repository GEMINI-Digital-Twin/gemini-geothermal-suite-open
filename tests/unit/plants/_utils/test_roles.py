"""The roles of a module, found from its class and its wiring."""

import gemini as gm
from gemini.errors import ValidationError
from gemini.plants._utils.roles import ROLES, roles_of, supply_service, units_of
from tests.fixtures.errors import raises


def test_the_roles_are_those_of_the_case_table():
    """One list of roles for the plants and the case."""
    assert set(ROLES) == set(gm.case.roles())


def test_a_machine_takes_its_role_from_the_grid_it_reaches():
    """The heat pump heats, the compression chiller cools."""
    plant = gm.plants.get("HeatingHeatPumpCoolingPlant")
    assert units_of(plant, "heat_pump") == ["heat_pump"]
    assert units_of(plant, "chiller") == ["compression_chiller"]
    module = plant.get_submodule("heat_pump")
    assert roles_of(plant, "heat_pump", module) == ["heat_pump"]


def test_a_plant_without_a_role_has_no_unit_of_it():
    """Nothing to find."""
    assert units_of(gm.plants.get("HeatingPlant"), "chiller") == []


def test_a_unit_is_on_a_supply_line_when_its_outlet_reaches_the_grid():
    """Heating units reach the ``HeatingGrid``, cooling units the ``CoolingGrid``."""
    plant = gm.plants.get("HeatingCoolingPlant")
    found = {
        path: supply_service(plant, path, module)
        for path, module in plant.named_modules()
        if hasattr(module, "supply_margin")
    }
    assert found == {
        "heat_pump": "heating",
        "peak_boiler": "heating",
        "absorption_chiller": "cooling",
        "adsorption_chiller": "cooling",
        "compression_chiller": "cooling",
    }


def test_a_unit_on_both_grids_is_refused():
    """A heat pump that heats the users and cools the building has one setpoint."""
    plant = gm.Plant("Both")
    plant.add("HeatPump", name="pump")
    plant.add("HeatingGrid", name="warm")
    plant.add("CoolingGrid", name="cold")
    plant.connect("pump.sink_out", "warm.supply_in")
    plant.connect("pump.source_out", "cold.supply_in")
    with raises(ValidationError, "invalid_design", match="both"):
        supply_service(plant, "pump", plant.pump)
