"""The JSON Schema of the plant spec."""

import json

import gemini as gm
from tests.fixtures.sample_cases import example_plant


def test_the_schema_is_plain_json_listing_every_module_type_and_group():
    """Types are an enumeration of the registry and the two groups."""
    schema = gm.plants.schema()
    assert json.loads(json.dumps(schema)) == schema
    assert schema["$schema"].endswith("2020-12/schema")
    types = schema["$defs"]["module"]["properties"]["type"]["enum"]
    assert {"Filter", "Doublet", "ModuleDict", "ModuleList"} <= set(types)


def test_the_schema_requires_the_header_and_a_type_or_a_structure():
    """A plant of a class names it; any other plant states its modules and connections."""
    schema = gm.plants.schema()
    assert schema["required"] == ["format", "kind", "name"]
    assert schema["properties"]["kind"] == {"const": "plant"}
    assert schema["anyOf"] == [{"required": ["type"]}, {"required": ["modules", "connections"]}]
    assert set(schema["properties"]["type"]["enum"]) == set(gm.plants.names())


def test_the_schema_accepts_only_the_keys_a_plant_file_holds():
    """Every key a plant writes is declared, in both forms."""
    schema = gm.plants.schema()
    plant = example_plant("NodalDoublet")
    assert set(plant.to_dict()) <= set(schema["properties"])
    assert set(plant.to_dict(structure=True)) <= set(schema["properties"])
    assert not {"inputs", "bindings", "param_history"} & set(schema["properties"])


def test_the_schema_describes_a_leaf_with_its_range_options_and_history():
    """Every leaf is one object; ``params`` is a tree of them."""
    leaf = gm.plants.schema()["$defs"]["leaf"]
    assert set(leaf["properties"]) == {"value", "unit", "range", "options", "history"}
    assert leaf["additionalProperties"] is False


def test_the_schema_lists_the_forms_of_an_output_and_nothing_removed():
    """Outputs are the three combinations."""
    forms = gm.plants.schema()["properties"]["outputs"]["additionalProperties"]["properties"]
    assert set(forms) == {"difference", "ratio", "sum"}
