"""``gm.plants.capabilities``: what each plant class contains, plans and lets a study search."""

import json

import pytest

import gemini as gm
from tests.fixtures.paths import EXAMPLES


@pytest.fixture(scope="module")
def found():
    """Return the capabilities of every plant class."""
    return gm.plants.capabilities()


def test_every_plant_class_is_listed(found):
    """The keys are the registered plant classes."""
    assert list(found) == gm.plants.names()


def test_the_roles_are_roles_of_the_case(found):
    """Every role is a key of ``gm.plants.roles()``,."""
    assert all(set(item["roles"]) <= set(gm.plants.roles()) for item in found.values())


def test_a_heating_cooling_plant_has_what_it_is_made_of(found):
    """The roles by class and wiring."""
    roles = set(found["HeatingHeatPumpCoolingPlant"]["roles"])
    assert roles >= {
        "doublet",
        "heat_pump",
        "boiler",
        "chiller",
        "heating_supply",
        "cooling_supply",
    }
    assert "heat_pump" not in found["HeatingFullCoolingPlant"]["roles"]


def test_the_schedule_plans_plants_with_doublets_and_a_grid(found):
    """A substation has no doublet, a doublet alone is no child: not planned."""
    planned = {name for name, item in found.items() if item["schedulable"]}
    assert (
        "DoubletHeatPlant" in planned
        and "HeatingPlant" in planned
        and "HeatingCoolingPlant" in planned
    )
    assert not planned & {"ATESPlant", "HeatingSubstation", "Doublet"}


def test_the_ranges_follow_the_class(found):
    """Doublets need the structural size, depth a depth parameter."""
    assert found["HeatingPlant"]["ranges"][:2] == ["size.doublets", "params.depth"]
    assert found["Doublet"]["ranges"][0] == "params.depth"
    assert "size.doublets" not in found["DoubletHeatPlant"]["ranges"]
    assert "params.valve.flow_coefficient" in found["HeatingSubstation"]["ranges"]


def test_every_numeric_leaf_of_a_plant_file_may_state_a_range(found):
    """``params.<path>`` for each number of the plant, and ``set_range`` takes each one.

    The leaves are those of the largest size, ``d2`` included, so the plant is built at it.
    """
    plant = gm.plants.HeatingPlant(doublets=3)
    ranges = found["HeatingPlant"]["ranges"]
    assert ranges[:2] == ["size.doublets", "params.depth"]
    assert {"params.d0.depth", "params.d0.gradient"} <= set(ranges)
    assert len(ranges) > 50 and len(set(ranges)) == len(ranges)
    for path in ranges[::20]:
        plant.set_range(path.removeprefix("params."), None, None)
    assert not any("dispatch" in path or "outages" in path for path in ranges)


def _stated_ranges(node, path):
    """Yield the path of every leaf of a plant file that states a ``range``."""
    if isinstance(node, dict):
        if "range" in node:
            yield path
        for key, value in node.items():
            if key != "range":
                yield from _stated_ranges(value, f"{path}.{key}")


def test_every_range_of_the_example_plant_files_is_listed(found):
    """A range at any size of a stored plant, ``d1`` and ``d2`` included, is a listed leaf.

    A plant file of no class (its structure written out) has no entry to look in.
    """
    files = sorted(EXAMPLES.glob("*/plants*/*.json"))
    assert files
    for file in files:
        data = json.loads(file.read_text())
        if "type" not in data:
            continue
        stated = list(_stated_ranges(data.get("params", {}), "params"))
        stated += list(_stated_ranges(data.get("size", {}), "size"))
        missing = [path for path in stated if path not in found[data["type"]]["ranges"]]
        assert missing == [], file.name
