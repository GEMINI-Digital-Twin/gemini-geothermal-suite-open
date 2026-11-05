"""Writing a built plant: stated values stay as written while they are true."""

import gemini as gm
from gemini.plants._utils.serialization import tree_params
from tests.fixtures import si
from tests.fixtures.designs import with_values


def test_a_stated_unit_string_stays_while_the_value_is_unchanged():
    """The stated unit is kept; a changed value is a quantity in SI; unstated defaults stay out."""
    plant = gm.Plant("Units")
    plant.add("Pipe", "pipe", params={"length": {"value": 100, "unit": "ft"}})
    assert plant.to_dict()["params"] == {"pipe": {"length": {"value": 100, "unit": "ft"}}}
    si.set_params(plant, "pipe", {"length": 1500.0})
    assert plant.to_dict()["params"] == {"pipe": {"length": {"value": 1500.0, "unit": "m"}}}


def test_a_value_set_since_is_added():
    """A parameter nobody stated is written once it differs from its starting value."""
    plant = gm.Plant("Added")
    plant.add("Pipe", "pipe")
    assert plant.to_dict()["modules"]["pipe"] == {"type": "Pipe"}
    assert plant.to_dict()["params"] == {}
    si.set_params(plant, "pipe", {"inner_diameter": 0.3})
    assert plant.to_dict()["params"] == {"pipe": {"inner_diameter": {"value": 0.3, "unit": "m"}}}


def test_a_group_writes_its_children_and_a_plant_its_registered_name():
    """Groups nest ``modules``; a nested plant is written by name."""
    plant = gm.Plant("Groups")
    plant.add("ModuleDict", "filters")
    plant.add("Filter", "filters.hot")
    plant.add("Doublet", "doublet")
    modules = plant.to_dict()["modules"]
    assert modules["filters"] == {"type": "ModuleDict", "modules": {"hot": {"type": "Filter"}}}
    assert modules["doublet"]["type"] == "Doublet"


def test_baseline_is_the_starting_values_of_the_tree():
    """A nested plant's baseline holds its dotted parameter names."""
    assert "reservoir.skin" in tree_params(with_values(gm.plants.get("Doublet")))


def test_a_doublet_depth_the_plant_gives_stays_linked_after_a_round_trip():
    """QA-278: ``d0.depth`` was written whole, so a reloaded plant's depth left its wells."""
    from pathlib import Path

    import gemini as gm

    folder = Path(__file__).parents[4] / "examples" / "hackathon_2026" / "plants"
    plant = gm.Plant.from_json(folder / "HeatingCoolingPlant.json")
    again = gm.Plant.from_dict(plant.to_dict(structure=True))
    again._set_si_params("", {"depth": 2200.0})
    assert again.d0.depth == 2200.0
    own = gm.Plant.from_dict(plant.to_dict(structure=True))
    own._set_si_params("", {"d0.depth": 2100.0})
    assert gm.Plant.from_dict(own.to_dict(structure=True)).d0.depth == 2100.0
