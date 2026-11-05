"""The union of plants: one superstructure whose structures give back each plant."""

import pytest

import gemini as gm
from gemini.errors import ValidationError
from gemini.plants._utils import superstructure
from gemini.units import Quantity
from tests.fixtures.errors import raises
from tests.fixtures.sample_cases import HACKATHON_2026


def loop(name, first=(), second=(), kinds=None, loss="air"):
    """Return a water loop: users -> ``second`` -> x (pump) -> ``first`` -> boiler -> users.

    ``first`` and ``second`` are names of valves in series; ``kinds`` gives another type to a name.
    The pump draws power from ``grid`` and loses heat to ``loss`` (``air`` or ``air2``, both
    atmospheres); the boiler burns gas of ``gas``.
    """
    kinds = kinds or {}
    plant = gm.Plant(name)
    for kind, module in (
        ("HeatingGrid", "users"),
        ("CirculationPump", "x"),
        ("Boiler", "boiler"),
        ("ElectricityGrid", "grid"),
        ("Atmosphere", "air"),
        ("Atmosphere", "air2"),
        ("GasGrid", "gas"),
    ):
        plant.add(kind, module)
    chain_a = ["users.return_out"]
    for valve in second:
        plant.add(kinds.get(valve, "Valve"), valve)
        chain_a += [f"{valve}.fluid_in", f"{valve}.fluid_out"]
    chain_b = ["x.fluid_out"]
    for valve in first:
        plant.add(kinds.get(valve, "Valve"), valve)
        chain_b += [f"{valve}.fluid_in", f"{valve}.fluid_out"]
    for chain, end in ((chain_a, "x.fluid_in"), (chain_b, "boiler.fluid_in")):
        chain.append(end)
        for source, target in zip(chain[::2], chain[1::2]):
            plant.connect(source, target)
    plant.connect("boiler.fluid_out", "users.supply_in", type="state")
    plant.connect("grid.power_out", "x.power_in")
    plant.connect("x.loss_out", f"{loss}.heat_in")
    plant.connect("gas.gas_out", "boiler.fuel_in")
    plant.connect("boiler.flue_out", "air.gas_in")
    plant.connect("boiler.loss_out", "air.heat_in")
    return plant


def edges(plant):
    """Return the connections of a plant as a set of ``(source, target, state)``."""
    return set(superstructure._edges(superstructure._plain_file(plant, gm.Plant)))


def modules(plant):
    """Return ``{path: type}`` of the modules of a plant."""
    return {path: type(module).__name__ for path, module in plant.named_modules() if path}


def refused(plants, *texts):
    """Assert that the union of ``plants`` raises ``invalid_design`` with each of ``texts``."""
    with raises(ValidationError, code="invalid_design") as caught:
        gm.plants.union(plants, name="u")
    assert all(text in str(caught.value) for text in texts), str(caught.value)


def gives_back(merged, plants):
    """Assert that the structure of each plant gives its modules and connections."""
    for plant in plants:
        found = merged.with_structure(merged.union["structures"][plant.name])
        assert modules(found) == modules(plant)
        assert edges(found) == edges(plant)


def test_a_module_of_some_plants_is_optional_and_placed_in_series():
    """``y`` in one plant, ``y`` then ``z`` in the other: both optional, in that order."""
    plants = [loop("one", first=["y"]), loop("two", first=["y", "z"]), loop("bare")]
    merged = gm.plants.union(plants, name="all")
    assert merged.name == "all" and merged.optional == ["y", "z"] and merged.choices == {}
    assert merged.union["structures"] == {
        "one": {"y": True, "z": False},
        "two": {"y": True, "z": True},
        "bare": {"y": False, "z": False},
    }
    assert merged.target_of("x.fluid_out") == "y.fluid_in"
    assert merged.target_of("z.fluid_out") == "boiler.fluid_in"
    gives_back(merged, plants)
    assert all(s in merged.structures() for s in merged.union["structures"].values())


def test_alternatives_at_one_place_are_a_choice_with_their_companions():
    """``y`` or ``z`` between the pump and the boiler is a choice; ``w`` goes with ``y``."""
    plants = [loop("one", first=["y"], second=["w"]), loop("two", first=["z"]), loop("bare")]
    merged = gm.plants.union(plants, name="all")
    assert merged.optional == []
    assert merged.choices == {"y_or_z": {"y": ["y", "w"], "z": ["z"], "none": []}}
    assert {k: v["y_or_z"] for k, v in merged.union["structures"].items()} == {
        "one": "y",
        "two": "z",
        "bare": "none",
    }
    gives_back(merged, plants)


def test_differing_values_keep_the_first_and_widen_the_range():
    """The first plant's value stays, the ranges join and the note lists each plant's value."""
    one, two = loop("one", first=["y"]), loop("two", first=["y"])
    one.set_params("y", {"rangeability": 30.0}).set_range("y.rangeability", min=10, max=40)
    two.set_params("y", {"rangeability": 50.0}).set_range("y.rangeability", min=20, max=60)
    one.set_params("x", {"flow": Quantity(3, "kg/s")})
    two.set_params("x", {"flow": Quantity(3, "kg/s")})
    merged = gm.plants.union([one, two], name="both")
    assert merged.y.rangeability == 30.0
    assert merged.ranges["y.rangeability"].to_json() == {"min": 10, "max": 60}
    (note,) = merged.union["notes"]
    assert note["path"] == "params.y.rangeability"
    assert note["kept"] == {"value": 30.0, "range": {"min": 10, "max": 60}}
    assert {k: v["value"] for k, v in note["values"].items()} == {"one": 30.0, "two": 50.0}


def test_one_name_with_two_types_raises():
    """``y`` a valve in one plant and a pump in the other: the message names both."""
    plants = [loop("one", first=["y"]), loop("two", first=["y"], kinds={"y": "CirculationPump"})]
    refused(plants, "'y'", "Valve", "CirculationPump")


def test_a_module_without_a_bypass_pair_asks_for_set_bypass():
    """A mixer in one plant only cannot be bypassed: the message names it and set_bypass."""
    two = loop("two")
    two.add("Mixer", "m")
    refused([loop("one"), two], "m (Mixer)", "set_bypass")


def test_wiring_no_series_gives_raises_naming_the_plants_and_the_connection():
    """Two orders of the same valves, or another connection between fixed modules, raise."""
    orders = [loop("one", first=["y", "z"]), loop("two", first=["z", "y"]), loop("bare")]
    refused(orders, "another order", "'one'")
    other = loop("two", loss="air2")
    refused([loop("one"), other], "x.loss_out", "air.heat_in", "'two' does not")


@pytest.mark.parametrize(
    "plants, name, code",
    [
        ("loops", None, "invalid_value"),
        ("one", "u", "invalid_value"),
        ("twins", "u", "invalid_value"),
        ("text", "u", "invalid_value"),
        ("super", "u", "invalid_value"),
    ],
)
def test_the_call_is_checked(plants, name, code):
    """A name, at least two plants, distinct names, no superstructure among them."""
    given = {
        "loops": [loop("a"), loop("b")],
        "one": [loop("a")],
        "twins": [loop("a"), loop("a")],
        "text": [loop("a"), "b"],
        "super": [loop("a", first=["y"]).set_optional("y"), loop("b")],
    }[plants]
    with raises(ValidationError, code=code):
        gm.plants.union(given, name=name)


def test_three_hackathon_plants_with_a_drive_circuit_merge_and_give_each_back():
    """Three plants of the sample merge: the heat pump and two chillers with their coolers vary."""
    names = ["HeatingCoolingPlant", "HeatingFullCoolingPlant", "HeatingAbsorptionCoolingPlant"]
    plants = [gm.Plant.from_json(HACKATHON_2026 / f"plants/{n}.json") for n in names]
    merged = gm.plants.union(plants, name="cooling")
    assert merged.optional == [
        "heat_pump",
        "adsorption_chiller",
        "compression_chiller",
        "adsorption_cooler",
        "compression_cooler",
    ]
    gives_back(merged, plants)


def test_the_six_hackathon_plants_need_a_bypass_for_their_splitters_and_mixers():
    """The six plants of the sample raise: their splitters, mixers and grids have no pair."""
    plants = [gm.Plant.from_json(path) for path in sorted((HACKATHON_2026 / "plants").glob("*"))]
    refused(plants, "drive_splitter (Splitter)", "drive_mixer (Mixer)", "set_bypass")
