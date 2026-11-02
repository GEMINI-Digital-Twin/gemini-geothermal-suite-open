"""The JSON Schema of the case files, written from the field lists."""

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
