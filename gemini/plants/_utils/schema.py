"""The JSON Schema of the plant dict, the input schema of a tool that builds plants."""

from gemini._utils import registry
from gemini.plants._utils.factory import GROUPS

SECTION = {"type": "object", "additionalProperties": {"type": "object"}}
PATH = {"type": "string", "pattern": r"^[^.\s]+(\.[^.\s]+)*$"}
SIZE = {
    "type": "object",
    "description": 'The structural arguments of a class, as leaves: {"doublets": {"value": 2}}.',
    "additionalProperties": {"$ref": "#/$defs/leaf"},
}
PORT = {"type": "string", "pattern": r"^[^.\s]+(\.[^.\s]+)+$"}
SPREAD = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"min": {"type": "number"}, "max": {"type": "number"}},
}


def _leaf():
    """Return the schema of a leaf object: a value, its unit, and what the file says about it."""
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "value": {},
            "unit": {"type": "string"},
            "range": SPREAD,
            "options": {"type": "array", "items": {"type": "string"}, "minItems": 1},
            "history": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["valid_from"],
                    "additionalProperties": False,
                    "properties": {"valid_from": {}, "value": {}, "unit": {"type": "string"}},
                },
            },
        },
    }


def _tree():
    """Return the schema of the ``params`` tree: modules of modules, whose leaves are objects."""
    return {
        "type": "object",
        "additionalProperties": {"anyOf": [{"$ref": "#/$defs/leaf"}, {"$ref": "#/$defs/tree"}]},
    }


def _module():
    return {
        "type": "object",
        "required": ["type"],
        "additionalProperties": False,
        "properties": {
            "type": {"type": "string", "enum": registry.names() + sorted(GROUPS)},
            "size": {"type": "object"},
            "modules": {"type": "object", "additionalProperties": {"$ref": "#/$defs/module"}},
        },
    }


def _connection():
    return {
        "type": "object",
        "required": ["source", "target"],
        "additionalProperties": False,
        "properties": {
            "source": PORT,
            "target": PORT,
            "type": {"enum": ["state", None]},
        },
    }


def _output():
    two = {"type": "array", "items": PATH, "minItems": 2, "maxItems": 2}
    return {
        "type": "object",
        "minProperties": 1,
        "maxProperties": 1,
        "additionalProperties": False,
        "properties": {
            "difference": two,
            "ratio": two,
            "sum": {"type": "array", "items": PATH, "minItems": 2},
        },
    }


def _constraint():
    return {
        "type": "object",
        "required": ["target", "by", "bounds"],
        "additionalProperties": False,
        "properties": {
            "target": PATH,
            "equals": PATH,
            "at_least": PATH,
            "by": PATH,
            "bounds": {
                "anyOf": [
                    PATH,
                    {
                        "type": "array",
                        "items": {"anyOf": [PATH, {"type": "number"}]},
                        "minItems": 2,
                        "maxItems": 2,
                    },
                ]
            },
        },
    }


def _superstructure():
    """Return the properties of the superstructure: ``optional``, ``choices`` and ``bypass``."""
    return {
        "optional": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
        "choices": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "minProperties": 2,
                "additionalProperties": {"type": "array", "items": {"type": "string"}},
            },
        },
        "bypass": {
            "type": "object",
            "additionalProperties": {"type": "object", "additionalProperties": {"type": "string"}},
        },
    }


def schema():
    """Return the JSON Schema (draft 2020-12) of a plant file, generated from the code."""
    ports = {
        "type": "object",
        "additionalProperties": {"anyOf": [PORT, {"type": "array", "items": PORT}]},
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "GEMINI plant file",
        "type": "object",
        "required": ["format", "kind", "name"],
        "additionalProperties": False,
        "anyOf": [{"required": ["type"]}, {"required": ["modules", "connections"]}],
        "properties": {
            "format": {"const": 1},
            "kind": {"const": "plant"},
            "name": {"type": "string"},
            "about": {"type": "object"},
            "type": {"type": "string", "enum": registry.names("plants")},
            "size": SIZE,
            "modules": {"type": "object", "additionalProperties": {"$ref": "#/$defs/module"}},
            "connections": {"type": "array", "items": _connection()},
            "inlets": ports,
            "outlets": ports,
            "outputs": {"type": "object", "additionalProperties": _output()},
            "constraints": {"type": "array", "items": _constraint()},
            "params": {"$ref": "#/$defs/tree"},
            "fluids": SECTION,
            "boundary": SECTION,
        }
        | _superstructure(),
        "$defs": {"module": _module(), "leaf": _leaf(), "tree": _tree()},
    }
