"""The JSON Schema (draft 2020-12) of ``case.json`` and ``economics.json``, from the field lists."""

from gemini import units
from gemini.case._utils.node import Field
from gemini.plants.roles import TABLE
from gemini.units import inputs

DRAFT = "https://json-schema.org/draft/2020-12/schema"
NUMBER = {"type": "number"}
RANGE = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"min": NUMBER, "max": NUMBER},
}
UNCERTAINTY = {
    "type": "object",
    "additionalProperties": False,
    "required": ["kind"],
    "properties": {
        "kind": {"enum": list(inputs.UNCERTAINTY_KINDS)},
        "min": NUMBER,
        "max": NUMBER,
        "std": NUMBER,
    },
}
HEADER = {
    "format": {"const": inputs.FORMAT},
    "kind": {"type": "string"},
    "name": {"type": "string"},
}


def leaf(field):
    """Return the schema of the leaf of one ``Field``."""
    if field.keys is not None:
        item = leaf(Field(field.quantity, bounds=field.bounds))
        return closed({key: item for key in field.keys})
    value = {"type": "string"} if field.text else NUMBER
    properties = {"value": value, "range": RANGE, "uncertainty": UNCERTAINTY}
    required = ["value"]
    if field.quantity is not None:
        properties["unit"] = {"enum": units.names(field.quantity)}
        required.append("unit")
    form = closed(properties, required)
    if not field.series:
        return form
    series = {
        "file": {"type": "string"},
        "column": {"type": "string"},
        "unit": properties.get("unit"),
    }
    series = {key: item for key, item in series.items() if item is not None}
    return {"anyOf": [form, closed(series | {"range": RANGE}, list(series))]}


def closed(properties, required=()):
    """Return the schema of an object that accepts no other key."""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(required),
        "properties": properties,
    }


def section(cls, header=False):
    """Return the schema of a section class; ``header`` adds the keys every file starts with."""
    properties = {name: leaf(field) for name, field in cls.fields.items()}
    properties |= {name: section(sub) for name, sub in cls.sections.items()}
    properties["about"] = {"type": "object"}
    required = [name for name, field in cls.fields.items() if field.required]
    if header:
        return closed(HEADER | properties, ["format", "kind", "name"] + required)
    return closed(properties, required)


def requirement():
    """Return the schema of one requirement."""
    roles = list(TABLE)
    properties = {
        "name": {"type": "string", "pattern": "^[a-z][a-z0-9_]*$"},
        "on": {"enum": roles},
        "quantity": {"enum": sorted({q for quantities in TABLE.values() for q in quantities})},
        "unit": {"type": "string"},
        "over": {"enum": ["each", "sum", "mean", "max", "min", "duration"]},
        "when": {"enum": ["always", "running"]},
        "min": NUMBER,
        "max": NUMBER,
    }
    return closed(properties, ["name", "on", "quantity"])


def time():
    """Return the schema of the ``time`` section."""
    step = leaf(Field("duration"))
    properties = {"start": {"type": "string"}, "end": {"type": "string"}, "step": step}
    return closed(properties, list(properties))
