"""Read the leaves of a plant file against the declarations of the plant they set."""

from dataclasses import replace

from gemini import units
from gemini._utils.strings import close_matches, did_you_mean, join_names
from gemini.errors import ValidationError
from gemini.errors.base import raise_issues
from gemini.modules._utils import description
from gemini.modules.declarations import holds_list
from gemini.plants._utils import plant_inputs
from gemini.plants._utils.form import MARKERS, file_path, flat_name, is_leaf, issue
from gemini.units import bare, inputs

SCALARS = ("number", "integer")


def table_of(plant):
    """Return ``{flat name: declaration}`` of every parameter, control and boundary of the plant."""
    return dict(plant.named_parameters()) | plant.inputs()


def numeric_paths(plant):
    """Return the paths of the leaves of ``params`` that hold a number, so may state a ``range``.

    Every parameter, control and boundary of the plant that is a number or a whole number, as
    ``params.<path>`` in the order of ``table_of``; a choice, a text and an array take no range.
    """
    return [
        f"params.{file_path(name)}"
        for name, declaration in table_of(plant).items()
        if _kind(declaration) == "number"
    ]


def declaration_of(plant, path, table=None):
    """Return the declaration a leaf path sets: a parameter, a control, a boundary, or a field."""
    name = flat_name(path)
    found = (table if table is not None else table_of(plant)).get(name)
    return found if found is not None else plant_inputs.declaration(plant, name)


def _kind(declaration):
    if description._enum(declaration):
        return "choice"
    shape = description._value_schema(declaration)
    if declaration.schema.get("type") == "array" or any(
        item.get("type") == "array" for item in declaration.schema.get("anyOf", ())
    ):
        return "array"
    return {"number": "number", "integer": "number", "string": "label"}.get(
        shape.get("type"), "other"
    )


def _quantity(declaration, node=None):
    """Return the quantity a leaf is read in: a dimensionless value takes a unit only if given."""
    if declaration.unit is None or (declaration.unit == "-" and "unit" not in (node or {})):
        return None
    return declaration.quantity


def _bounds(declaration):
    limits = declaration.limits()
    low = limits.get("ge", limits.get("gt"))
    high = limits.get("le", limits.get("lt"))
    return None if low is None and high is None else inputs.Range(low, high)


def _probe(node, kind):
    """Return ``node`` with a stand-in value when it has none, so its other keys are read."""
    if "value" in node:
        return node
    history = node.get("history")
    if isinstance(history, list) and history and isinstance(history[0], dict):
        return node | {"value": history[0].get("value")}
    options = node.get("options")
    if kind == "choice" and isinstance(options, list) and options:
        return node | {"value": options[0]}
    spread = node.get("range")
    if isinstance(spread, dict):
        for side in ("min", "max"):
            if isinstance(spread.get(side), (int, float)):
                return node | {"value": spread[side]}
    return node | {"value": 0}


def _extra_keys(node, path, issues):
    bad = [key for key in node if key not in MARKERS]
    if bad:
        inputs.check_keys({key: node[key] for key in bad}, (), path, issues)
    if "uncertainty" in node:
        issue(
            issues, f"{path}.uncertainty", "unknown_key", f"{path}: a plant leaf has no uncertainty"
        )


def _array_items(node, declaration, path, issues):
    """Append the issues of a list leaf: its one unit once, then each item.

    A list of one quantity takes one unit for all its items; a wrong or missing unit is one
    issue at ``<path>.unit``, and the items are then judged as numbers only.
    """
    items = node.get("value")
    if not isinstance(items, (list, tuple)):
        issue(issues, f"{path}.value", "incompatible", f"{path}.value = {items!r}; expected a list")
        return
    bounds = _bounds(declaration)
    unit = node.get("unit")
    unit_read = True
    quantity = _quantity(declaration, node)
    if quantity is not None and holds_list(declaration):
        before = len(issues)
        probe = {"value": 0} | ({"unit": unit} if "unit" in node else {})
        inputs.from_leaf(probe, path, issues, quantity=quantity)
        unit_read = len(issues) == before
        if not unit_read:
            unit, bounds = None, None
    for index, item in enumerate(items):
        probe = {"value": item} | ({"unit": unit} if unit else {})
        inputs.from_leaf(
            probe,
            f"{path}.value[{index}]",
            issues,
            quantity=_quantity(declaration, probe) if unit_read else None,
            bounds=bounds,
        )


def _read(node, declaration, path, issues):
    """Return the ``Leaf`` of a dict ``node`` read against ``declaration``, else ``None``."""
    kind = _kind(declaration)
    plain = {key: value for key, value in _probe(node, kind).items() if key != "history"}
    missing = "value" not in node and not node.get("history")
    unset = [item.get("value") for item in node.get("history") or () if isinstance(item, dict)]
    only_unset = "value" not in node and bool(unset) and all(v is None for v in unset)
    if (only_unset or ("value" in node and node["value"] is None)) and declaration.accepts_none():
        _extra_keys(node, path, issues)
        return inputs.Leaf(None)
    if kind == "array":
        _extra_keys(node, path, issues)
        if "value" in node:
            _array_items(node, declaration, path, issues)
        return inputs.Leaf(node.get("value"), node.get("unit"))
    if kind == "label" or kind == "other":
        _extra_keys(node, path, issues)
        return inputs.Leaf(node.get("value"))
    before = len(issues)
    choices = tuple(description._enum(declaration) or ()) if kind == "choice" else None
    leaf = inputs.from_leaf(
        plain,
        path,
        issues,
        quantity=_quantity(declaration, plain),
        choices=choices,
        bounds=_bounds(declaration),
    )
    if missing:
        issue(issues, f"{path}.value", "missing", f"{path}.value: value is missing")
    if "uncertainty" in node:
        _extra_keys({"uncertainty": 1}, path, issues)
    if len(issues) > before and not missing:
        return None
    return replace(leaf, value=None) if "value" not in node and leaf is not None else leaf


def _history(node, declaration, path, issues):
    for index, item in enumerate(node.get("history") or ()):
        here = f"{path}.history[{index}]"
        if not isinstance(item, dict) or "valid_from" not in item:
            issue(issues, here, "missing", f"{here}: expected {{'valid_from': ..., 'value': ...}}")
            continue
        body = {key: value for key, value in item.items() if key != "valid_from"}
        if body.get("value") is None and declaration.accepts_none():
            continue
        if "unit" not in body and "unit" in node:
            body["unit"] = node["unit"]
        _read(body, declaration, here, issues)


def leaf_at(plant, path, node, issues, table=None):
    """Return the ``Leaf`` of the file leaf at ``path``, appending every issue; else ``None``."""
    found = declaration_of(plant, path, table)
    if found is None:
        return None
    here = f"params.{path}"
    quantity = _quantity(found, node if isinstance(node, dict) else None)
    if not isinstance(node, dict) or not is_leaf(node):
        issue(
            issues,
            here,
            "unit" if quantity else "missing",
            f"{here} = {node!r}; expected an object like {units_form(quantity, found)}",
        )
        return None
    leaf = _read(node, found, here, issues)
    _history(node, found, here, issues)
    return leaf


def _size(plant, name, node, issues):
    """Return the ``Leaf`` of one structural size, a count or a choice of the class."""
    path = f"size.{name}"
    choices = plant.size_choices.get(name)
    if not isinstance(node, dict):
        return None
    before = len(issues)
    leaf = inputs.from_leaf(
        _probe(node, "choice" if choices else "number"),
        path,
        issues,
        choices=choices,
        bounds=None if choices else inputs.Range(1, None),
    )
    if leaf is None:
        return None
    numbers = [leaf.value, *(leaf.range.to_json().values() if leaf.range else ())]
    if not choices and any(not isinstance(number, int) for number in numbers):
        issue(issues, path, "incompatible", f"{path}: expected whole numbers, got {numbers}")
    return leaf if len(issues) == before else None


def apply(plant, parsed, issues):
    """Read every leaf of ``parsed`` against ``plant``; keep the ranges and options it states."""
    search = {}
    for name, node in parsed.sizes.items():
        leaf = _size(plant, name, node, issues)
        if leaf is not None and (leaf.range or leaf.options):
            search[f"size.{name}"] = leaf
    table = table_of(plant)
    for path, node in parsed.leaves.items():
        leaf = leaf_at(plant, path, node, issues, table)
        if leaf is not None and (leaf.range or leaf.options):
            search[path] = leaf
    plant._search = search
    plant._file = {"name": parsed.header.name, "about": parsed.header.about}


def units_form(quantity, declaration=None):
    """Return the shape of a leaf, with its unit when the value has a dimension.

    A list with a dimension (of ``declaration``) has one unit for its numbers.
    """
    if quantity and declaration is not None and holds_list(declaration):
        return bare.LIST_FORM
    return units.QUANTITY_FORM if quantity else "{'value': ...}"


def _located(plant, path):
    """Return ``(declaration or None, choices)`` of a search path, or raise ``unknown_name``."""
    if path.startswith("size."):
        name = path[len("size.") :]
        if name in plant._size:
            return None, plant.size_choices.get(name)
    else:
        found = declaration_of(plant, path)
        if found is not None:
            choices = description._enum(found)
            return found, tuple(choices) if choices else None
    names = [f"size.{name}" for name in plant._size] + [
        file_path(name) for name, _ in plant.named_parameters()
    ]
    raise ValidationError(
        f"{plant.path}: unknown path {path!r}; valid: {join_names(names)}"
        f"{did_you_mean(path, names)}",
        path=path,
        suggestions=close_matches(path, names),
        code="unknown_name",
    )


def stated_unit(plant, path, declaration):
    """Return the unit the leaf at ``path`` is written in: its stated one, else the SI one."""
    if path in plant._search and plant._search[path].unit is not None:
        return plant._search[path].unit
    node = plant.to_dict().get("params", {})
    for part in path.split("."):
        node = node.get(part, {}) if isinstance(node, dict) else {}
    if isinstance(node, dict) and "unit" in node:
        return node["unit"]
    return None if declaration is None or _quantity(declaration) is None else declaration.unit


def _side(path, name, value, unit):
    if value is None:
        return None
    if isinstance(value, units.Quantity):
        if unit is None:
            raise ValidationError(
                f"{path}.{name}: this value has no unit", path=path, code="invalid_unit"
            )
        return value.to(unit).value
    if unit is not None:
        bare.refuse(f"{path}.{name}", value, unit, None)
    return value


def _store(plant, path, old, **changes):
    new = replace(old or inputs.Leaf(), **changes)
    if new.range is None and new.options is None:
        plant._search.pop(path, None)
    else:
        plant._search[path] = new


def set_range(plant, path, low, high):
    """Store the search range of the leaf at ``path`` after the checks a file's range has."""
    declaration, _ = _located(plant, path)
    unit = stated_unit(plant, path, declaration)
    sides = {"min": _side(path, "min", low, unit), "max": _side(path, "max", high, unit)}
    sides = {key: value for key, value in sides.items() if value is not None}
    old = plant._search.get(path)
    if not sides:
        _store(plant, path, old, range=None)
        return
    node = {"range": sides} | ({"unit": unit} if unit else {})
    issues = []
    if declaration is None:
        probe = node | {"value": next(iter(sides.values()))}
        leaf = inputs.from_leaf(probe, path, issues, bounds=inputs.Range(1, None))
    else:
        leaf = _read(node, declaration, path, issues)
    raise_issues([item for item in issues if item.kind != "missing"])
    _store(plant, path, old, range=leaf.range, unit=unit, quantity=leaf.quantity)


def set_options(plant, path, options):
    """Store the options of the choice at ``path``, a subset of its closed list."""
    _, choices = _located(plant, path)
    if choices is None:
        raise ValidationError(f"{path}: only a choice has options", path=path, code="invalid_value")
    issues = []
    found = inputs.from_options(list(options), f"{path}.options", choices, issues)
    raise_issues(issues)
    _store(plant, path, plant._search.get(path), options=found)
