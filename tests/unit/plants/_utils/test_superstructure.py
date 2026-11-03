"""The superstructure of a plant: optional modules, choices, their structures and their plants."""

import json

import pytest

import gemini as gm
from gemini._utils import registry
from gemini.errors import ValidationError
from gemini.modules import Port
from gemini.modules.module import Module
from gemini.plants._utils import superstructure
from gemini.plants._utils.serialization import tree_params
from gemini.streams.fluid import Fluid
from gemini.streams.kinds import Direction, Flow, Level, Phase
from gemini.units import Quantity
from tests.fixtures import json_schema
from tests.fixtures.errors import raises
from tests.fixtures.sample_cases import HACKATHON_2026

HEATING_PLANT = HACKATHON_2026 / "plants/HeatingPlant.json"


def loop(state=False):
    """Return a closed water loop: users -> a -> x (pump) -> y -> boiler -> users.

    The pump ``x`` draws power from ``grid`` and loses heat to ``air``; the boiler burns gas of
    ``gas``, so turning the boiler off leaves ``gas.gas_out`` unconnected. ``state`` makes the
    connection into the pump a state connection.
    """
    plant = gm.Plant()
    for kind, name in (
        ("HeatingGrid", "users"),
        ("Valve", "a"),
        ("CirculationPump", "x"),
        ("Valve", "y"),
        ("Boiler", "boiler"),
        ("ElectricityGrid", "grid"),
        ("Atmosphere", "air"),
        ("GasGrid", "gas"),
    ):
        plant.add(kind, name)
    plant.connect("users.return_out", "a.fluid_in")
    plant.connect("a.fluid_out", "x.fluid_in", **({"type": "state"} if state else {}))
    plant.connect("x.fluid_out", "y.fluid_in")
    plant.connect("y.fluid_out", "boiler.fluid_in")
    plant.connect("boiler.fluid_out", "users.supply_in", type="state")
    plant.connect("grid.power_out", "x.power_in")
    plant.connect("x.loss_out", "air.heat_in")
    plant.connect("gas.gas_out", "boiler.fuel_in")
    plant.connect("boiler.flue_out", "air.gas_in")
    plant.connect("boiler.loss_out", "air.heat_in")
    return plant


def valued(plant):
    """Return ``plant`` with values and ranges on the pump ``x`` and the valve ``a``."""
    plant.set_params("x", {"flow": Quantity(3, "kg/s")})
    plant.set_range("x.flow", min=Quantity(1, "kg/s"), max=Quantity(5, "kg/s"))
    plant.set_params("a", {"rangeability": 30.0})
    plant.set_range("a.rangeability", min=10, max=50)
    return plant


def superplant():
    """Return the valued loop with ``x`` and ``boiler`` optional and the choice ``trim``."""
    plant = valued(loop())
    plant.set_optional("x").set_optional("boiler")
    return plant.set_choice("trim", {"valve": ["y"], "none": []})


def links(plant):
    """Return the connections of a plant as ``{(source, target): type}``."""
    return {(i["source"], i["target"]): i.get("type") for i in plant.to_dict()["connections"]}


class Crossed(Module):
    """A test module whose inlet ``left_in`` leaves by ``right_out``: it declares its bypass."""

    bypass = {"left_in": "right_out"}

    def __init__(self):
        """Declare one inlet and two outlets, none of a matching name."""
        super().__init__()
        any_stream = dict(fluid=Fluid.ANY, phase=Phase.ANY, level=Level.ANY, flow=Flow.IMPOSED)
        self.left_in = Port(Direction.IN, **any_stream)
        self.right_out = Port(Direction.OUT, **any_stream)
        self.spare_out = Port(Direction.OUT, **any_stream)

    def forward(self, inputs, inlets, state):
        """Pass the stream on."""
        return {}, {"right_out": inlets.left_in, "spare_out": inlets.left_in}


class Wrong(Crossed):
    """A test module whose declared bypass names a port it does not have."""

    bypass = {"left_in": "missing_out"}


@pytest.fixture
def crossed(monkeypatch):
    """Register the test classes ``Crossed`` and ``Wrong`` for this test only."""
    for cls in (Crossed, Wrong):
        monkeypatch.setitem(registry._entries, cls.__name__, registry._Entry("piping", cls))


@pytest.mark.parametrize("kind", ["HeatPump", "Boiler", "HeatExchanger", "CirculationPump"])
def test_a_module_with_inlet_and_outlet_pairs_may_be_optional(kind):
    """Each ``<x>_in`` with its ``<x>_out`` is the bypass; the module is listed once."""
    plant = gm.Plant()
    module = plant.add(kind, "m")
    assert plant.set_optional("m") is plant and plant.set_optional("m").optional == ["m"]
    found = superstructure.pairs(module, "m")
    assert found and all(
        plant.m.inlets()[i] and o == i[: -len("_in")] + "_out" for i, o in found.items()
    )


@pytest.mark.parametrize("kind", ["Doublet", "Mixer", "Degasser", "Splitter", "ElectricityGrid"])
def test_a_module_without_a_pair_cannot_be_optional(kind):
    """No ``<x>_in`` with a stream outlet ``<x>_out``: the bypass is ambiguous."""
    plant = gm.Plant()
    plant.add(kind, "m")
    with raises(ValidationError, "invalid_design", match="bypass"):
        plant.set_optional("m")
    assert plant.optional == []


def test_an_unknown_module_is_named_with_the_close_ones():
    """A typo gives ``unknown_name`` and a suggestion."""
    plant = loop()
    with raises(ValidationError, "unknown_name") as caught:
        plant.set_optional("boiller")
    assert "boiler" in caught.value.suggestions


def test_a_module_in_a_choice_cannot_be_optional_and_false_makes_it_fixed():
    """A module is optional or in one choice; ``False`` removes it from the optional ones."""
    plant = loop().set_choice("trim", {"valve": ["y"], "none": []})
    with raises(ValidationError, "invalid_design", match="choices.trim"):
        plant.set_optional("y")
    plant.set_optional("x").set_optional("boiler")
    assert plant.set_optional("x", False).optional == ["boiler"]
    with raises(ValidationError, "invalid_value"):
        plant.set_optional("boiler", "yes")


def test_a_class_that_declares_its_bypass_is_honoured(crossed):
    """``bypass`` pairs ``left_in`` with ``right_out``, names no pattern could find."""
    plant = gm.Plant()
    module = plant.add(Crossed, "c")
    plant.set_optional("c")
    assert superstructure.pairs(module, "c") == {"left_in": "right_out"}
    plant.add(Wrong, "w")
    with raises(ValidationError, "invalid_design", match="missing_out"):
        plant.set_optional("w")


def test_a_declared_bypass_rewires_the_plant_of_a_structure(crossed):
    """What fed ``left_in`` feeds what ``right_out`` fed; ``spare_out`` goes with the module."""
    plant = gm.Plant()
    plant.add("Valve", "a")
    plant.add(Crossed, "c")
    plant.add("Valve", "b")
    plant.connect("feed", "a.fluid_in")
    plant.connect("a.fluid_out", "c.left_in")
    plant.connect("c.right_out", "b.fluid_in")
    plant.connect("c.spare_out", "spare")
    plant.connect("b.fluid_out", "product")
    data = plant.set_optional("c").with_structure({"c": False}).to_dict()
    assert data["connections"] == [{"source": "a.fluid_out", "target": "b.fluid_in"}]
    assert data["outlets"] == {"product": "b.fluid_out"} and "c" not in data["modules"]


def test_a_choice_has_groups_apart_and_none_may_be_empty():
    """Two groups or more, each a list; ``None`` removes the choice."""
    plant = loop()
    plant.set_choice("trim", {"valve": ["y"], "pump": ["x"], "none": []})
    assert plant.choices == {"trim": {"valve": ["y"], "pump": ["x"], "none": []}}
    with raises(ValidationError, "invalid_design", match="two groups"):
        plant.set_choice("other", {"one": ["boiler"], "two": ["boiler"]})
    with raises(ValidationError, "invalid_design", match="already in"):
        plant.set_choice("other", {"one": ["y"], "none": []})
    assert plant.set_choice("trim", None).choices == {}


def test_a_choice_of_fewer_than_two_groups_is_refused():
    """One group is no choice; a list is not a dict of groups."""
    plant = loop()
    for groups in ({"valve": ["y"]}, {}, ["y"]):
        with raises(ValidationError, "invalid_value"):
            plant.set_choice("trim", groups)
    with raises(ValidationError, "invalid_value"):
        plant.set_choice("", {"valve": ["y"], "none": []})
    assert plant.choices == {}


def test_an_optional_module_cannot_be_in_a_choice():
    """Nor can a choice take the name of an optional module."""
    plant = loop().set_optional("x")
    with raises(ValidationError, "invalid_design", match="already in optional"):
        plant.set_choice("trim", {"pump": ["x"], "none": []})
    with raises(ValidationError, "invalid_design"):
        plant.set_choice("x", {"valve": ["y"], "none": []})
    with raises(ValidationError, "invalid_design"):
        plant.set_choice("trim", {"well": ["users"], "none": []})


def test_the_bypass_joins_a_chain_through_two_modules_off():
    """``a -> x -> y -> boiler`` with ``x`` and ``y`` off gives ``a -> boiler``."""
    plant = loop().set_optional("x").set_choice("trim", {"valve": ["y"], "none": []})
    found = plant.with_structure({"x": False, "trim": "none"})
    names = {name for name, _ in found.named_modules() if name}
    assert {"x", "y"}.isdisjoint(names) and {"a", "boiler", "grid"} <= names
    assert links(found)[("a.fluid_out", "boiler.fluid_in")] is None
    one = plant.with_structure({"x": False, "trim": "valve"})
    assert ("a.fluid_out", "y.fluid_in") in links(one)


def test_the_power_and_other_ports_go_with_the_module():
    """The grid and the air no longer reach the pump that is off; nothing else changes."""
    plant = loop().set_optional("x")
    found = plant.with_structure({"x": False})
    assert not any("x." in s or "x." in t for s, t in links(found))
    kept = {key: kind for key, kind in links(loop()).items() if "x." not in key[0] + key[1]}
    assert {k: v for k, v in links(found).items() if k != ("a.fluid_out", "y.fluid_in")} == kept


def test_a_state_connection_stays_a_state_connection():
    """``a -> x`` is a state connection: the joined ``a -> y`` is one too."""
    plant = loop(state=True).set_optional("x")
    assert links(plant.with_structure({"x": False}))[("a.fluid_out", "y.fluid_in")] == "state"


def test_a_plant_port_on_a_module_off_is_dropped():
    """A plant inlet that fed only the power of the module that is off goes with it."""
    plant = gm.Plant()
    plant.add("Valve", "a")
    plant.add("CirculationPump", "x")
    plant.add("Valve", "b")
    plant.connect("feed", "a.fluid_in")
    plant.connect("a.fluid_out", "x.fluid_in")
    plant.connect("x.fluid_out", "b.fluid_in")
    plant.connect("b.fluid_out", "product")
    plant.connect("power", "x.power_in")
    plant.connect("x.loss_out", "loss")
    data = plant.set_optional("x").with_structure({"x": False}).to_dict()
    assert data["inlets"] == {"feed": "a.fluid_in"} and data["outlets"] == {
        "product": "b.fluid_out"
    }
    assert data["connections"] == [{"source": "a.fluid_out", "target": "b.fluid_in"}]


def test_structures_are_in_a_fixed_order_and_only_the_valid_ones():
    """On before off, the groups in their order; the boiler off leaves the gas unconnected."""
    plant = superplant()
    assert plant.structures() == [
        {"x": True, "boiler": True, "trim": "valve"},
        {"x": True, "boiler": True, "trim": "none"},
        {"x": False, "boiler": True, "trim": "valve"},
        {"x": False, "boiler": True, "trim": "none"},
    ]
    assert len(superstructure.every(plant)) == 8
    with pytest.raises(ValidationError, match="gas.gas_out: unconnected port"):
        plant.with_structure({"x": True, "boiler": False, "trim": "none"})
    assert gm.Plant().structures() == [{}] and loop().with_structure({}).to_dict() == (
        loop().to_dict()
    )


def test_a_structure_names_every_key_with_a_value_it_allows():
    """A missing key, an unknown key and a value out of the list each have their code."""
    plant = superplant()
    with raises(ValidationError, "missing_value"):
        plant.with_structure({"x": True, "boiler": True})
    with raises(ValidationError, "unknown_name"):
        plant.with_structure({"x": True, "boiler": True, "trim": "none", "pump": True})
    with raises(ValidationError, "invalid_value"):
        plant.with_structure({"x": "on", "boiler": True, "trim": "none"})
    with raises(ValidationError, "invalid_value") as caught:
        plant.with_structure({"x": True, "boiler": True, "trim": "nnoe"})
    assert list(caught.value.suggestions) == ["none"]
    with raises(ValidationError, "invalid_value"):
        plant.with_structure([True, True, "none"])


def test_the_plant_of_a_structure_keeps_what_its_modules_state():
    """No optional or choice; the ranges and values of the modules that stay, not the others."""
    plant = superplant()
    on = plant.with_structure({"x": True, "boiler": True, "trim": "none"})
    off = plant.with_structure({"x": False, "boiler": True, "trim": "none"})
    for found in (on, off):
        assert found.optional == [] and found.choices == {}
        assert "optional" not in found.to_dict() and "choices" not in found.to_dict()
        assert found.a.rangeability == 30.0
    assert set(on.ranges) == {"x.flow", "a.rangeability"} and on.x.flow == 3.0
    assert set(off.ranges) == {"a.rangeability"}
    assert "x" not in off.to_dict()["params"] and "x" in on.to_dict()["params"]
    assert plant.optional == ["x", "boiler"] and "x" in plant.to_dict()["modules"]


def test_a_plant_of_a_class_with_a_module_off_becomes_a_plant_of_modules():
    """The file reads back, and every value of a module that stays is the one the class gave."""
    plant = gm.Plant.from_json(HEATING_PLANT)
    plant.set_optional("heating_supply_pipe")
    found = plant.with_structure({"heating_supply_pipe": False})
    assert type(found) is gm.Plant and "type" not in found.to_dict()
    again = gm.Plant.from_dict(json.loads(json.dumps(found.to_dict())))
    assert again.to_dict() == found.to_dict()
    names = [name for name, _ in plant.named_modules() if name and "." not in name]
    assert "heating_supply_pipe" not in dict(found.named_modules())
    for name in names:
        if name != "heating_supply_pipe":
            given = tree_params(plant.get_submodule(name))
            assert tree_params(again.get_submodule(name)) == given, name
    assert ("peak_boiler.fluid_out", "heating_consumer.supply_in") in links(found)


def test_a_plant_of_a_class_with_nothing_off_keeps_its_class():
    """With every module on, the plant is a copy of its class, without the superstructure."""
    plant = gm.Plant.from_json(HEATING_PLANT)
    plant.set_optional("heating_supply_pipe")
    found = plant.with_structure({"heating_supply_pipe": True})
    assert type(found) is type(plant) and found is not plant and found.optional == []
    assert found.to_dict() == gm.Plant.from_json(HEATING_PLANT).to_dict()
    assert plant.optional == ["heating_supply_pipe"]


def test_optional_and_choices_round_trip_through_the_file(tmp_path):
    """``to_dict``/``from_dict`` and ``to_json``/``from_json`` keep both, in their order."""
    plant = superplant()
    data = plant.to_dict()
    assert data["optional"] == ["x", "boiler"]
    assert data["choices"] == {"trim": {"valve": ["y"], "none": []}}
    again = gm.Plant.from_dict(json.loads(json.dumps(data)))
    assert again.optional == ["x", "boiler"] and again.choices == plant.choices
    assert again.to_dict() == data
    plant.to_json(tmp_path / "super.json")
    read = gm.Plant.from_json(tmp_path / "super.json")
    assert read.to_dict() == data and read.structures() == plant.structures()
    assert "optional" not in loop().to_dict() and "choices" not in loop().to_dict()


def test_a_plant_of_a_class_writes_its_superstructure():
    """The short form of a class plant carries ``optional`` too."""
    plant = gm.Plant.from_json(HEATING_PLANT).set_optional("heating_supply_pipe")
    data = plant.to_dict()
    assert data["type"] == "HeatingPlant" and data["optional"] == ["heating_supply_pipe"]
    assert gm.Plant.from_dict(data).optional == ["heating_supply_pipe"]


def test_a_bad_declaration_in_a_file_is_an_issue_with_its_path():
    """An unknown module, a module with no bypass, a choice of one group, wrong shapes."""
    data = loop().to_dict() | {
        "optional": ["boiller", "users"],
        "choices": {"trim": {"valve": ["y"]}},
    }
    with pytest.raises(ValidationError) as caught:
        gm.Plant.from_dict(data)
    found = {item.path: item.kind for item in caught.value.issues}
    assert found == {
        "optional[0]": "unknown_key",
        "optional[1]": "incompatible",
        "choices.trim": "incompatible",
    }
    issues = []
    superstructure.from_file(gm.Plant(), {"optional": "x", "choices": []}, issues)
    assert [item.path for item in issues] == ["optional", "choices"]


def test_check_reports_a_superstructure_without_a_valid_structure():
    """Every structure leaves the gas unconnected: ``invalid_design`` at ``optional``."""
    plant = loop()
    plant.add("GasGrid", "spare_gas")
    plant.set_optional("x")
    found = [item for item in plant.check() if item.kind != "missing"]
    assert [item.code for item in found if item.path == "optional"] == ["invalid_design"]
    assert plant.structures() == []
    good = superplant()
    assert not [item for item in good.check() if item.kind != "missing"]


def test_the_schema_accepts_the_superstructure_keys():
    """``optional`` is a list of names and ``choices`` a dict of groups, in the plant schema."""
    schema = gm.plants.schema()
    assert {"optional", "choices"} <= set(schema["properties"])
    assert json_schema.check(superplant().to_dict(), schema) == []
    bad = superplant().to_dict() | {"optional": "x"}
    assert json_schema.check(bad, schema)


def test_a_bypass_that_joins_a_module_to_itself_is_dropped():
    """The users' loop through a pump that is off would feed them their own return: it goes."""
    plant = gm.Plant()
    plant.add("HeatingGrid", "users")
    plant.add("Valve", "v")
    plant.connect("users.return_out", "v.fluid_in")
    plant.connect("v.fluid_out", "users.supply_in", type="state")
    plant.set_optional("v")
    assert plant.structures() == [{"v": True}]
    with pytest.raises(ValidationError, match="users.return_out: unconnected port"):
        plant.with_structure({"v": False})
