"""The JSON Schema (draft 2020-12) of ``case.json`` and ``economics.json``, from the field lists."""

from gemini import units
from gemini.case._utils.node import Field
from gemini.case.site import FRACTION
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


def header(kind):
    """Return the properties every file starts with; ``kind`` is the one value this file has."""
    return {
        "format": {"const": inputs.FORMAT},
        "kind": {"type": "string", "const": kind},
        "name": {"type": "string"},
    }


def limits(bounds, quantity):
    """Return the numeric limits of a leaf in SI: ``min``, ``max`` and the SI ``unit`` if any."""
    found = bounds.to_json()
    if quantity is not None:
        found["unit"] = units.si_unit(units.names(quantity)[0])
    return found


def marks(field):
    """Return the ``x-`` keys that describe a leaf to a form: quantity, units, limits, fraction.

    ``x-quantity`` is the quantity of the unit and ``x-units`` the units it accepts, both from
    ``gm.units``; ``x-limits`` are the bounds of the value in SI, with their unit; ``x-fraction``
    marks a dimensionless share between 0 and 1, which a form may show as a percentage.
    """
    found = {}
    if field.quantity is not None:
        found["x-quantity"] = field.quantity
        found["x-units"] = units.names(field.quantity)
    if field.bounds is not None:
        found["x-limits"] = limits(field.bounds, field.quantity)
    if field.quantity is None and field.bounds == FRACTION:
        found["x-fraction"] = True
    return found


def leaf(field):
    """Return the schema of the leaf of one ``Field``."""
    if field.keys is not None:
        item = leaf(Field(field.quantity, bounds=field.bounds))
        return closed({key: item for key in field.keys}) | marks(field)
    value = {"type": "string"} if field.text else NUMBER
    properties = {"value": value, "range": RANGE, "uncertainty": UNCERTAINTY}
    required = ["value"]
    if field.quantity is not None:
        properties["unit"] = {"enum": units.names(field.quantity)}
        required.append("unit")
    form = closed(properties, required)
    if not field.series:
        return form | marks(field)
    series = {
        "file": {"type": "string"},
        "column": {"type": "string"},
        "unit": properties.get("unit"),
    }
    series = {key: item for key, item in series.items() if item is not None}
    return {"anyOf": [form, closed(series | {"range": RANGE}, list(series))]} | marks(field)


def closed(properties, required=()):
    """Return the schema of an object that accepts no other key."""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(required),
        "properties": properties,
    }


def quantities(cls):
    """Return ``{quantity: units}`` of every leaf below a section class, from the one unit table."""
    found = {field.quantity for field in cls.fields.values() if field.quantity is not None}
    for sub in cls.sections.values():
        found |= set(quantities(sub))
    return {quantity: units.names(quantity) for quantity in sorted(found)}


def section(cls, kind=None):
    """Return the schema of a section class; a ``kind`` adds the keys every file starts with.

    The file schema also lists, as ``x-quantities``, the units of every quantity it uses.
    """
    properties = {name: leaf(field) for name, field in cls.fields.items()}
    properties |= {name: section(sub) for name, sub in cls.sections.items()}
    properties["about"] = {"type": "object"}
    required = [name for name, field in cls.fields.items() if field.required]
    if kind is not None:
        found = closed(header(kind) | properties, ["format", "kind", "name"] + required)
        return found | {"x-quantities": quantities(cls)}
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
