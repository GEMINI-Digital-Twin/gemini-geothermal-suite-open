"""The public spec functions: round trip, JSON safety and the shared name pair."""

import json

import pytest

import gemini as gm
from tests.fixtures.plant_files import file_of, issues
from tests.fixtures.sample_cases import example_plant, filled_plant, treatment_plant

HISTORY = [
    {"valid_from": "2020-01-01T00:00:00Z", "value": 30.48},
    {"valid_from": "2021-01-01T00:00:00Z", "value": 200},
]
"""The dated lengths of the pipe in the file below, as a leaf states them."""


def test_from_dict_builds_a_plant_of_any_class():
    """``gm.Plant.from_dict`` gives the class of the dict, and a class-less plant without one."""
    typed = gm.Plant.from_dict(example_plant("Doublet").to_dict())
    assert isinstance(typed, gm.plants.Doublet)
    assert not hasattr(gm.plants, "from_dict")


def test_the_stored_plant_file_round_trips_exactly():
    """``to_dict(from_dict(x)) == x`` for the migrated example plant, JSON-safe."""
    spec = example_plant("DoubletHeatPlant").to_dict()
    plant = gm.Plant.from_dict(spec)
    assert plant.to_dict() == spec
    assert json.loads(json.dumps(plant.to_dict(), allow_nan=False)) == spec


def test_a_spec_with_unit_strings_and_sections_round_trips_exactly():
    """Units stay as written; fluids and the history of a leaf are kept."""
    spec = file_of(
        "DoubletHeatPlant",
        modules={"pipe": {"type": "Pipe"}, "valve": {"type": "Valve"}},
        connections=[{"source": "pipe.fluid_out", "target": "valve.fluid_in"}],
        inlets={"feed": "pipe.fluid_in", "air": "pipe.air_in"},
        outlets={"product": "valve.fluid_out", "loss": "pipe.loss_out"},
        params={
            "pipe": {
                "length": {"value": 100, "unit": "ft", "history": HISTORY[1:]},
                "inner_diameter": {"value": 0.1, "unit": "m"},
            }
        },
        fluids={"pipe": gm.WATER._to_dict()},
    )
    plant = gm.Plant.from_dict(spec)
    written = plant.to_dict()
    assert written["params"]["pipe"]["inner_diameter"] == {"value": 0.1, "unit": "m"}
    assert written["params"]["pipe"]["length"]["unit"] == "ft"
    assert written == {key: spec[key] for key in written}
    assert gm.Plant.from_dict(written).to_dict() == written


def test_a_nested_spec_and_a_group_round_trip_and_run_parameters_through():
    """A child of plant type takes nested params; a group nests children."""
    spec = file_of(
        "DoubletHeatPlant",
        modules={
            "doublet": {"type": "Doublet"},
            "filters": {"type": "ModuleDict", "modules": {"hot": {"type": "Filter"}}},
        },
        connections=[{"source": "doublet.supply_out", "target": "filters.hot.fluid_in"}],
        inlets={"return_in": "doublet.return_in", "power_in": "doublet.power_in"},
        outlets={"product": "filters.hot.fluid_out"},
        params={"doublet": {"esp": {"stage_count": {"value": 12}}}},
    )
    plant = gm.Plant.from_dict(spec)
    assert plant.doublet.esp.stage_count == 12
    assert plant.to_dict() == spec


def test_an_opened_plant_round_trips_its_nested_wiring():
    """The shipped heat plant opens its doublet and still writes it as one child."""
    plant = gm.plants.get("DoubletHeatPlant")
    spec = plant.to_dict(structure=True)
    assert spec["modules"]["doublet"] == {"type": "Doublet"}
    assert gm.Plant.from_dict(spec).to_dict(structure=True) == spec


def test_a_plant_reports_a_root_port_that_has_no_outer_name():
    """``check`` of a plant reports a root port, and a bad unit is refused at once."""
    plant = gm.Plant("Same")
    plant.add("Pipe", "pipe", params={"length": gm.units.Quantity(5.0, "m")})
    plant.connect("feed", "pipe.fluid_in")
    plant.connect("air", "pipe.air_in")
    plant.connect("pipe.fluid_out", "product")
    plant.connect("pipe.loss_out", "loss")
    found = [item for item in plant.check() if item.kind != "missing"]
    assert {item.problem()["code"] for item in found} == {"root_plant_port"}
    with pytest.raises(gm.errors.ValidationError):
        plant.add("Pipe", "bad", params={"length": {"value": 5, "unit": "bar"}})


def test_a_raised_error_carries_every_issue_of_the_file():
    """``from_dict`` raises one error with every issue, in the order of the file."""
    spec = file_of(
        "DoubletHeatPlant",
        modules={"a": {"type": "Boilr"}, "pipe": {"type": "Pipe"}},
        connections=[],
        inlets={"feed": "pipe.fluid_in", "air": "pipe.air_in"},
        outlets={"product": "pipe.fluid_out", "loss": "pipe.loss_out"},
        params={"pipe": {"length": {"value": -5.0, "unit": "m"}}},
    )
    found = issues(spec)
    assert [item.path for item in found] == ["modules.a.type", "params.pipe.length"]
    with pytest.raises(gm.errors.ValidationError) as caught:
        gm.Plant.from_dict(spec)
    assert list(caught.value.issues) == found and caught.value.code == found[0].problem()["code"]


def test_a_valid_file_has_no_issues():
    """Nothing is raised for a plant without problems; ``check`` is empty."""
    plant = gm.Plant("Empty")
    assert issues(plant.to_dict(structure=True)) == plant.check() == []


def test_a_file_with_bindings_or_inputs_is_refused():
    """Bindings are set in memory; a control is a leaf of ``params``, not an ``inputs`` key."""
    spec = file_of("Broken", modules={"pipe": {"type": "Pipe"}}, connections=[])
    for key in ("bindings", "inputs"):
        found = [item for item in issues(spec | {key: {}}) if item.path == key]
        assert [(item.path, item.kind) for item in found] == [(key, "unknown_key")]
    plant = gm.Plant("Kept")
    plant.add("Pipe", name="pipe")
    plant.set_bindings("pipe", {"velocity": "v"})
    assert "bindings" not in plant.to_dict(structure=True)
    assert plant.bindings["pipe"].controls == {} or plant.bindings["pipe"]


def test_a_broken_module_does_not_hide_the_other_end_of_a_connection():
    """Every problem comes at once, also on a connection with one good end."""
    spec = file_of(
        "DoubletHeatPlant",
        modules={"a": {"type": "Boilr"}, "pipe": {"type": "Pipe"}},
        connections=[
            {"source": "a.fluid_out", "target": "b.fluid_in"},
            {"source": "a.fluid_out", "target": "pipe.inlt"},
        ],
    )
    assert {item.path for item in issues(spec)} == {
        "modules.a.type",
        "connections[0].target",
        "connections[1].target",
        "pipe.fluid_in",
        "pipe.fluid_out",
        "pipe.air_in",
        "pipe.loss_out",
    }


@pytest.mark.parametrize("name", gm.plants.names())
def test_every_plant_rebuilds_from_its_dict_with_the_same_values(name):
    """The class form and the full form give the same plant file, without the case's values."""
    plant = filled_plant(name)
    data, structure = plant.to_dict(), plant.to_dict(structure=True)
    assert "modules" not in data and data["type"] == name
    rebuilt = gm.Plant.from_dict(data)
    assert type(rebuilt) is type(plant) and rebuilt.to_dict() == data
    assert gm.Plant.from_dict(structure).to_dict(structure=True) == structure


def test_a_size_is_stored_next_to_the_type():
    """A structural argument rebuilds the same shape."""
    data = gm.plants.MultiWellPlant(producers=3, injectors=2).to_dict()
    assert data["size"] == {"producers": {"value": 3}, "injectors": {"value": 2}}
    assert len(gm.Plant.from_dict(data).producers) == 3
    assert gm.plants.MultiWellPlant(producers=3, injectors=2).size == {
        "producers": 3,
        "injectors": 2,
    }


def test_a_class_plant_edited_by_hand_stores_its_structure():
    """A plant that left its class has no type to name."""
    plant = gm.plants.get("Doublet")
    plant.add("Filter", "extra")
    assert "modules" in plant.to_dict()


def test_a_root_of_a_class_is_checked_with_its_structure():
    """The full form of a plant reads without issues, whichever form it stores."""
    assert issues(example_plant("DoubletHeatPlant").to_dict(structure=True)) == []


def test_a_wrong_size_is_a_problem_of_the_dict():
    """A size the class does not take is reported on its path, not raised as a ``TypeError``."""
    data = file_of("W", type="MultiWellPlant", size={"wells": {"value": 3}})
    found = issues(data)
    assert [(item.path, item.problem()["code"]) for item in found] == [("size", "invalid_value")]
    entry = {"type": "DistrictNetwork", "size": {"streets": 2}}
    data = file_of("Nested", modules={"network": entry}, connections=[])
    assert [item.problem()["code"] for item in issues(data)] == ["invalid_value"]


def test_a_type_at_the_root_must_be_a_plant():
    """The root of a plant file is a plant class; a module is wrapped in a plant."""
    found = issues(file_of("E", type="ESP"))
    assert [(item.path, item.problem()["code"]) for item in found] == [("type", "invalid_value")]


def test_a_file_in_the_old_shape_is_refused_naming_the_new_header():
    """A file with no ``kind`` is of format 2: ``old_format``."""
    (item,) = issues({"format": 2, "type": "Doublet", "params": {}})
    assert item.problem()["code"] == "old_format" and '"kind": "plant"' in item.message


def test_both_a_type_and_a_structure_must_agree():
    """Giving ``type`` with modules and connections that are not the class's is an issue."""
    data = gm.plants.get("Doublet").to_dict(structure=True)
    assert issues(data) == []
    data["modules"] = {"pipe": {"type": "Pipe"}}
    assert [item.path for item in issues(data)] == ["modules"]


def test_the_competition_plant_survives_a_file_write_and_read(tmp_path):
    """Written with a design and read back: the same plant, in both forms."""
    plant = treatment_plant()
    for structure in (False, True):
        path = tmp_path / f"plant_{structure}.json"
        plant.to_json(path, structure=structure)
        assert gm.Plant.from_json(path).to_dict(structure) == plant.to_dict(structure)
