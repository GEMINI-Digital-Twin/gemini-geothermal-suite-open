"""The roles of a plant: the closed table, and the units found by class and wiring."""

import gemini as gm
from gemini.errors import ValidationError
from gemini.modules import Module
from gemini.plants.roles import TABLE, reads, remembered, roles_of, supply_service, units_of
from tests.fixtures.errors import raises


def test_every_role_a_class_declares_is_a_role_of_the_table():
    """A module class declares its kind in ``plant_role``; the table lists it."""
    declared = {
        cls.plant_role for cls in Module.__subclasses__() if getattr(cls, "plant_role", None)
    }
    declared |= {
        cls.plant_role
        for cls in (gm.plants.Doublet, gm.modules.Boiler, gm.modules.CHP, gm.modules.HeatExchanger)
    }
    assert declared <= set(TABLE)


def test_the_table_lists_every_role_with_its_quantities_dimension_and_over():
    """The closed table: a dimension (None without one) and whether the quantity takes over."""
    table = gm.plants.roles()
    assert list(table) == [
        "doublet",
        "heat_pump",
        "boiler",
        "chp",
        "chiller",
        "heat_exchanger",
        "heating_supply",
        "cooling_supply",
        "plant",
    ]
    assert list(table["doublet"])[:2] == ["production_flow", "brine_cooling"]
    assert table["doublet"]["production_flow"] == {"dimension": "volume_flow", "over": True}
    assert table["doublet"]["pump_efficiency"] == {"dimension": None, "over": False}
    assert table["doublet"]["reinjection_ratio"] == {"dimension": None, "over": True}
    assert table["heating_supply"]["unmet_share"] == {"dimension": None, "over": False}
    assert "volume_imbalance" not in table["doublet"]
    table["doublet"].clear()
    assert gm.plants.roles()["doublet"]


def test_reading_a_quantity_the_role_lacks_lists_the_role_quantities():
    """``cop`` is not a quantity of a doublet."""
    with raises(gm.errors.ValidationError, "invalid_value") as caught:
        reads("doublet", "cop")
    assert "production_flow" in str(caught.value)


def test_units_are_found_by_class_whatever_their_name():
    """A plant of a class holds its doublets, boiler and consumer under any name."""
    plant = gm.plants.HeatingPlant()
    assert units_of(plant, "doublet") == ["d0"]
    assert units_of(plant, "boiler") == ["peak_boiler"]
    assert units_of(plant, "heating_supply") == ["heating_consumer"]
    assert units_of(plant, "chiller") == []


def test_a_heat_pump_is_a_chiller_when_it_feeds_the_cooling_grid():
    """The same class is a heat pump or a compression chiller, by the grid it reaches."""
    plant = gm.plants.HeatingHeatPumpCoolingPlant()
    assert units_of(plant, "heat_pump") == ["heat_pump"]
    assert units_of(plant, "chiller") == ["compression_chiller"]


def test_doublets_are_found_under_any_name():
    """A plant built by hand names its doublets as it likes."""
    plant = gm.Plant("site")
    plant.add(gm.plants.Doublet, "north")
    plant.add(gm.plants.Doublet, "south")
    assert units_of(plant, "doublet") == ["north", "south"]


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


def test_roles_read_once_in_a_block_are_the_roles_read_alone():
    """Inside ``remembered`` every role gives the same paths; outside, a plant is read again."""
    plant = gm.plants.HeatingCoolingPlant(doublets=2)
    roles = ("doublet", "heat_pump", "chiller", "boiler", "plant", "heat_exchanger")
    alone = {role: units_of(plant, role) for role in roles}
    with remembered():
        assert {role: units_of(plant, role) for role in roles} == alone
        units_of(plant, "doublet").append("changed by the caller")
        assert units_of(plant, "doublet") == alone["doublet"]
    other = gm.plants.HeatingCoolingPlant(doublets=3)
    assert len(units_of(other, "doublet")) == 3
