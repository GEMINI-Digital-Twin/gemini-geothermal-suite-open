"""The JSON Schema (draft 2020-12) of ``case.json`` and ``economics.json``, from the field lists."""

import dataclasses

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
    "description": (
        "Deprecated on a case or economics leaf (a check reports it as a warning): the interval "
        "the value may take, in the unit of the leaf; either side optional."
    ),
    "properties": {
        "min": NUMBER | {"description": "The lowest value, in the unit of the leaf."},
        "max": NUMBER | {"description": "The highest value, in the unit of the leaf."},
    },
}
UNCERTAINTY = {
    "type": "object",
    "additionalProperties": False,
    "required": ["kind"],
    "description": (
        "The spread of the value that a sample or a sensitivity study draws from, in the unit of "
        "the leaf: min and max for uniform and triangular, std for normal."
    ),
    "properties": {
        "kind": {
            "enum": list(inputs.UNCERTAINTY_KINDS),
            "description": "The distribution: uniform, triangular (peak at value) or normal.",
        },
        "min": NUMBER | {"description": "The lowest value drawn (uniform, triangular)."},
        "max": NUMBER | {"description": "The highest value drawn (uniform, triangular)."},
        "std": NUMBER | {"description": "The standard deviation around the value (normal)."},
    },
}
WORDS = {
    "value": "The value, in its unit.",
    "unit": "The unit of the value and of its range and uncertainty.",
    "file": "The CSV file of the series, relative to the case file; its first column is time.",
    "column": "The column of the CSV file that holds the series.",
    "time_zone": (
        "The IANA time zone (such as Europe/Oslo) of the timestamps of the file that have no "
        "offset; without it every timestamp needs its offset."
    ),
}
"""The description of each key of a leaf, whatever the leaf."""
ABOUT = {
    "type": "object",
    "description": "Free notes on this part, such as its source; gemini keeps them and reads none.",
}
"""The ``about`` key every section and file has."""


def described(properties):
    """Return the leaf ``properties`` with the description of each key from ``WORDS``."""
    return {
        key: (
            item
            if "description" in item or key not in WORDS
            else item | {"description": WORDS[key]}
        )
        for key, item in properties.items()
    }


def header(kind):
    """Return the properties every file starts with; ``kind`` is the one value this file has."""
    return {
        "format": {"const": inputs.FORMAT, "description": "The version of the file format."},
        "kind": {"type": "string", "const": kind, "description": f"The kind of file: {kind}."},
        "name": {"type": "string", "description": "The name of this file's content."},
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
    marks a dimensionless share between 0 and 1, which a form may show as a percentage. A field
    with a ``description`` also gets the standard ``description`` key. A field that accepts other
    quantities, its unit telling which, lists ``x-bases``: each quantity with its units, the main
    one (``x-quantity``) first, and ``x-units`` is the units of them all. A dimensionless value
    that may state a unit (``unit_of``) lists the units in ``x-units``.
    """
    found = {} if field.description is None else {"description": field.description}
    if field.quantity is not None:
        found["x-quantity"] = field.quantity
        found["x-units"] = accepted_units(field)
    if field.unit_of is not None:
        found["x-units"] = units.names(field.unit_of)
    if field.alternatives:
        found["x-bases"] = {name: units.names(name) for name in field.accepted()}
    if field.bounds is not None:
        found["x-limits"] = limits(field.bounds, field.quantity)
    if field.quantity is None and field.bounds == FRACTION:
        found["x-fraction"] = True
    return found


def accepted_units(field):
    """Return the units a leaf of ``field`` accepts: those of its quantity and its alternatives."""
    names = field.accepted() if field.alternatives else (field.quantity,)
    return [unit for name in names for unit in units.names(name)]


def leaf(field):
    """Return the schema of the leaf of one ``Field``.

    A series of a dimensionless field that may state a unit (``unit_of``, the relative humidity)
    needs no ``unit``: without one its values are fractions 0 to 1, as in 0.5.0, whose schema the
    API keeps (0.6.5 had made it required).
    """
    if field.keys is not None:
        items = {
            key: leaf(
                Field(
                    field.quantity,
                    bounds=field.bounds,
                    unit_of=field.unit_of,
                    alternatives=field.of_key(key).alternatives,
                    description=f"The entry of this map for {key}.",
                )
            )
            for key in field.keys
        }
        every = field.alternatives if field.alternative_keys is None else ()
        return closed(items) | marks(dataclasses.replace(field, alternatives=every))
    value = {"type": "string"} if field.text else NUMBER
    properties = {"value": value, "range": RANGE, "uncertainty": UNCERTAINTY}
    required = ["value"]
    if field.quantity is not None:
        properties["unit"] = {"enum": accepted_units(field)}
        required.append("unit")
    if field.unit_of is not None:
        properties["unit"] = {"enum": units.names(field.unit_of)}
    form = closed(described(properties), required)
    if not field.series:
        return form | marks(field)
    series = {
        "file": {"type": "string"},
        "column": {"type": "string"},
        "unit": properties.get("unit"),
    }
    series = {key: item for key, item in series.items() if item is not None}
    optional = {"range": RANGE, "time_zone": {"type": "string"}}
    required = [key for key in series if key != "unit" or field.quantity is not None]
    return {"anyOf": [form, closed(described(series | optional), required)]} | marks(field)


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
    found |= {name for field in cls.fields.values() for name in field.alternatives}
    for sub in cls.sections.values():
        found |= set(quantities(sub))
    return {quantity: units.names(quantity) for quantity in sorted(found)}


def section(cls, kind=None):
    """Return the schema of a section class; a ``kind`` adds the keys every file starts with.

    The file schema also lists, as ``x-quantities``, the units of every quantity it uses. A section
    with a ``description`` gets the standard ``description`` key.
    """
    properties = {name: leaf(field) for name, field in cls.fields.items()}
    properties |= {name: section(sub) for name, sub in cls.sections.items()}
    properties["about"] = ABOUT
    required = [name for name, field in cls.fields.items() if field.required]
    described = {} if cls.description is None else {"description": cls.description}
    if kind is not None:
        found = closed(header(kind) | properties, ["format", "kind", "name"] + required)
        return found | described | {"x-quantities": quantities(cls)}
    return closed(properties, required) | described


def requirement():
    """Return the schema of one requirement: a rule of a third party on a quantity of a role."""
    roles = list(TABLE)
    properties = {
        "name": {
            "type": "string",
            "pattern": "^[a-z][a-z0-9_]*$",
            "description": "A unique snake_case name for the rule.",
        },
        "on": {"enum": roles, "description": "The role the rule applies to (gm.plants.roles())."},
        "quantity": {
            "enum": sorted({q for quantities in TABLE.values() for q in quantities}),
            "description": "The quantity of the role the rule bounds.",
        },
        "unit": {
            "type": "string",
            "description": (
                "The unit of min and max; present only when the bounds have a dimension."
            ),
        },
        "over": {
            "enum": ["each", "sum", "mean", "max", "min", "duration"],
            "description": (
                "How a per-step quantity is read: each step, one figure of the run (sum, mean, "
                "max, min), or the total time of the steps where when holds (duration)."
            ),
        },
        "when": {
            "enum": ["always", "running"],
            "description": "The steps that count: always, or running (the unit carries flow).",
        },
        "min": NUMBER | {"description": "The lowest value allowed, in unit."},
        "max": NUMBER | {"description": "The highest value allowed, in unit."},
    }
    return closed(properties, ["name", "on", "quantity"])


def time():
    """Return the schema of the ``time`` section: ``end`` is excluded from the period."""
    step = leaf(Field("duration")) | {"description": "The length of one step of the run."}
    properties = {
        "start": {
            "type": "string",
            "description": "The first instant of the period, ISO 8601; without an offset UTC.",
        },
        "end": {
            "type": "string",
            "description": (
                "The end of the period, ISO 8601, excluded: the last step starts one step before "
                "it, so 2027-01-01 to 2028-01-01 at one day is 365 steps and 2028-01-01 itself is "
                "not run. Without an offset UTC."
            ),
        },
        "step": step,
    }
    return closed(properties, list(properties)) | {
        "description": "The period of the case and its step; every series lies on its steps."
    }
