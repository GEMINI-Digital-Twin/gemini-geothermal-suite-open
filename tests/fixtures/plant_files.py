"""Read and build the plant file form in tests: its leaves as flat values, and the other way."""

import gemini as gm
from gemini.errors import ValidationError
from gemini.plants._utils import form


def leaves(spec):
    """Return ``{flat name: value}`` of the ``params`` of a plant file, in file order.

    A value with a unit is ``{"value", "unit"}``, any other the bare value; a leaf without a value
    is left out.
    """
    found = {}
    form._walk(spec.get("params", {}), "", found, [])
    values = {form.flat_name(path): form.flat_value(node) for path, node in found.items()}
    return {path: value for path, value in values.items() if value is not form.MISSING}


def tree(values):
    """Return the ``params`` tree of ``{flat name: value}``: each value a leaf object."""
    nodes = {}
    for name, value in values.items():
        quantity = isinstance(value, dict) and set(value) == {"value", "unit"}
        nodes[form.file_path(name)] = dict(value) if quantity else {"value": value}
    return form._nest(nodes)


def file_of(name="plant", **parts):
    """Return a plant file with the header, ``parts`` and ``params`` as a tree if given flat."""
    return {"format": 1, "kind": "plant", "name": name} | parts


def issues(data):
    """Return the issues ``Plant.from_dict`` raises for ``data``, empty when it reads."""
    try:
        gm.Plant.from_dict(data)
    except ValidationError as error:
        return list(error.issues)
    return []
