"""The plant file: header, nested ``params`` of leaf objects, ``size``, ranges and options."""

import pytest

import gemini as gm
from gemini.plants._utils import form
from tests.fixtures.plant_files import file_of, issues, leaves, tree


def test_a_leaf_is_an_object_and_a_module_is_a_subtree():
    """An object with a value, a unit, a range, options or a history is a leaf."""
    assert form.is_leaf({"value": 1}) and form.is_leaf({"unit": "W", "range": {"min": 1}})
    assert not form.is_leaf({"esp": {"stage_count": {"value": 3}}})


def test_the_plant_level_controls_sit_under_control():
    """``dispatch`` and ``outages`` are written as ``control.dispatch`` at any depth."""
    assert form.file_path("dispatch") == "control.dispatch"
    assert form.file_path("heating.outages") == "heating.control.outages"
    assert form.flat_name("heating.control.outages") == "heating.outages"
    assert form.file_path("backup") == "backup"


def test_parse_collects_the_leaves_in_file_order():
    """The flat dict has the values with their units; a leaf without a value is left out."""
    data = file_of(
        "x",
        type="Doublet",
        params={
            "depth": {"unit": "m", "range": {"min": 1.0}},
            "esp": {"stage_count": {"value": 4}},
        },
    )
    found = []
    parsed = form.parse(data, found)
    assert found == [] and list(parsed.leaves) == ["depth", "esp.stage_count"]
    assert parsed.flat["params"] == {"esp.stage_count": 4}


def test_a_plant_writes_its_ranges_first_in_the_order_they_were_set():
    """``size`` then the leaves with a range, in file order; the values follow."""
    plant = gm.plants.HeatingPlant(doublets=2)
    plant.set_range("size.doublets", min=1, max=3)
    plant.set_range("depth", min=gm.units.Quantity(1.0, "km"), max=gm.units.Quantity(2.0, "km"))
    data = plant.to_dict()
    assert data["size"]["doublets"] == {"value": 2, "range": {"min": 1, "max": 3}}
    assert list(data["params"])[0] == "depth"
    assert data["params"]["depth"] == {"unit": "m", "range": {"min": 1000.0, "max": 2000.0}}
    assert list(plant.ranges) == ["size.doublets", "depth"]
    again = gm.Plant.from_dict(data)
    assert again.to_dict() == data and list(again.ranges) == list(plant.ranges)


def test_a_range_keeps_the_unit_it_was_written_in():
    """A leaf in MW with a range in MW writes back the same numbers."""
    data = (
        gm.plants.HeatingPlant(doublets=1)
        .set_params("", {"peak_boiler.capacity": {"value": 5, "unit": "MW"}})
        .to_dict()
    )
    data["params"]["peak_boiler"]["capacity"]["range"] = {"min": 1.5, "max": 5.0}
    plant = gm.Plant.from_dict(data)
    assert plant.ranges["peak_boiler.capacity"].min == 1.5e6
    assert plant.to_dict() == data


def test_set_range_and_set_options_check_what_a_file_checks():
    """The path must exist, the range lie within the bounds and the options in the list."""
    plant = gm.plants.HeatingPlant(doublets=1)
    with pytest.raises(gm.errors.ValidationError) as unknown:
        plant.set_range("depht", min=gm.units.Quantity(1.0, "km"))
    assert unknown.value.code == "unknown_name" and "depth" in unknown.value.suggestions
    with pytest.raises(gm.errors.ValidationError) as bounds:
        plant.set_range("peak_boiler.capacity", min=gm.units.Quantity(-1.0, "MW"))
    assert bounds.value.issues[0].kind == "out_of_bounds"
    with pytest.raises(gm.errors.ValidationError):
        plant.set_range("peak_boiler.capacity", min=5.0)
    with pytest.raises(gm.errors.ValidationError) as listed:
        plant.set_options("heat_exchanger.arrangement", ["counterflow", "nope"])
    assert listed.value.issues[0].kind == "not_allowed"
    plant.set_options("heat_exchanger.arrangement", ["counterflow", "parallel"])
    assert plant.options == {"heat_exchanger.arrangement": ("counterflow", "parallel")}
    plant.set_range("size.doublets", min=1, max=2).set_range("size.doublets")
    assert "size.doublets" not in plant.ranges


def test_the_options_are_in_the_file_and_the_range_must_be_whole_for_a_count():
    """An option is a leaf key; a count range holds whole numbers."""
    plant = gm.plants.HeatingPlant(doublets=1).set_options(
        "heat_exchanger.arrangement", ["parallel"]
    )
    data = plant.to_dict()
    assert data["params"]["heat_exchanger"]["arrangement"] == {"options": ["parallel"]}
    data["size"]["doublets"]["range"] = {"min": 1.5, "max": 2}
    assert [item.path for item in issues(data)] == ["size.doublets"]


def test_the_file_of_a_full_form_and_the_class_form_read_the_same_values():
    """``structure=True`` writes the type and the modules; reading it gives the same leaves."""
    plant = gm.plants.get("Doublet")
    full = plant.to_dict(structure=True)
    assert {"type", "modules", "connections"} <= set(full)
    assert leaves(gm.Plant.from_dict(full).to_dict()) == leaves(plant.to_dict())
    assert tree({"dispatch": 1}) == {"control": {"dispatch": {"value": 1}}}


def test_the_control_leaves_read_and_write():
    """``params.control.dispatch`` sets the plant parameter; ``backup`` stays at the top."""
    plant = gm.plants.HeatingPlant(doublets=1).set_params(
        "", {"dispatch": "least_cost", "backup": "peak"}
    )
    data = plant.to_dict()
    assert data["params"]["control"] == {"dispatch": {"value": "least_cost"}}
    assert data["params"]["backup"] == {"value": "peak"}
    assert gm.Plant.from_dict(data).dispatch == "least_cost"


def test_a_dotted_key_in_params_is_refused_and_names_the_nested_form():
    """``params`` mirrors the module tree: ``d0.depth`` is ``d0`` holding ``depth``."""
    data = file_of("x", type="Doublet", params={"d0.depth": {"value": 1, "unit": "m"}})
    found = issues(data)
    (item,) = found
    assert item.path == "params.d0.depth" and item.kind == "not_allowed"
    assert '{"d0": {"depth": ...}}' in item.message
