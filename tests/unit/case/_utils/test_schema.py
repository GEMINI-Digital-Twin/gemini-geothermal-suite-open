"""The JSON Schema of the case files, written from the field lists."""

import pytest

import gemini as gm
from gemini.case._utils import schema


def keys_known(data, node):
    """Return the dotted paths of the keys of ``data`` that the schema ``node`` does not list."""
    if isinstance(node, dict) and "anyOf" in node:
        options = [keys_known(data, option) for option in node["anyOf"]]
        return min(options, key=len)
    if isinstance(data, list):
        return [x for item in data for x in keys_known(item, node.get("items", {}))]
    if not isinstance(data, dict) or "properties" not in node:
        return []
    properties = node["properties"]
    found = [key for key in data if key not in properties]
    return found + [
        x
        for key, item in data.items()
        if key in properties
        for x in keys_known(item, properties[key])
    ]


def test_every_key_of_a_full_case_is_in_the_schema(case):
    """The written case, its economics and its requirements are described."""
    assert keys_known(case.to_dict(), gm.Case.schema()) == []
    assert keys_known(case.economics.to_dict(), gm.case.Economics.schema()) == []


def test_the_schemas_are_closed_objects_with_a_required_header():
    """The kind and the name are required; an unknown key is refused."""
    for found in (gm.Case.schema(), gm.case.Economics.schema()):
        assert found["additionalProperties"] is False
        assert {"format", "kind", "name"} <= set(found["required"])
    assert gm.Case.schema()["properties"]["requirements"]["items"]["required"] == [
        "name",
        "on",
        "quantity",
    ]


def test_a_series_field_accepts_a_leaf_or_a_file_and_a_plain_one_only_a_leaf():
    """Power may be a column; a depth may not."""
    assert "anyOf" in schema.leaf(gm.case.Service.fields["power"])
    assert "anyOf" not in schema.leaf(gm.case.Reservoir.fields["thickness"])


def test_each_file_schema_names_the_one_kind_it_reads(case):
    """The header is a constant: a generated document has a kind the reader accepts."""
    assert gm.Case.schema()["properties"]["kind"] == {"type": "string", "const": "case"}
    assert gm.case.Economics.schema()["properties"]["kind"]["const"] == "economics"
    assert gm.plants.schema()["properties"]["kind"]["const"] == "plant"
    assert gm.Study.schema()["properties"]["kind"]["const"] == "study"
    for found in (gm.Case.schema(), gm.case.Economics.schema(), gm.Study.schema()):
        assert found["properties"]["format"]["const"] == 1
    for wrong in ({"kind": "economics"}, {"kind": None}):
        with pytest.raises(gm.errors.ValidationError) as caught:
            gm.Case.from_dict({**case.to_dict(), **wrong})
        assert caught.value.problems[0]["path"] == "case.kind"
    header = {"format": 1, "kind": "case", "name": "x"}
    assert gm.case.missing({k: v for k, v in header.items() if k != "kind"})[0].path == "kind"


def test_a_leaf_tells_a_form_its_quantity_its_units_its_limits_and_a_fraction():
    """``x-`` keys beside the existing ones, from the one unit table."""
    power = schema.leaf(gm.case.Service.fields["power"])
    assert power["x-quantity"] == "power" and power["x-units"] == gm.units.names("power")
    assert power["x-limits"] == {"min": 0.0, "unit": "W"}
    share = schema.leaf(gm.case.CoolingService.fields["indoor_relative_humidity"])
    assert share["x-fraction"] is True and share["x-limits"] == {"min": 0.0, "max": 1.0}
    assert "x-quantity" not in share
    assert "x-fraction" not in power
    composition = schema.leaf(gm.case.Gas.fields["composition"])
    assert composition["x-fraction"] is True and "anyOf" not in composition


def test_the_file_schemas_list_the_units_of_every_quantity_they_use():
    """``x-quantities`` is a map from quantity to units, none missing from the leaves."""
    found = gm.Case.schema()["x-quantities"]
    assert found["power"] == gm.units.names("power") and found["duration"]
    assert set(gm.case.Economics.schema()["x-quantities"]) <= set(found)
    assert {"money_per_energy", "temperature", "permeability"} <= set(found)
