"""The plant file: a header, the structure and a tree of leaf objects, to and from the flat dict.

The file (``kind: plant``) holds ``type`` or ``modules`` and ``connections``, ``size`` beside
``params``, and ``params`` as a tree that mirrors the module tree whose every leaf is an object
``{"value", "unit", "range", "options", "history"}``. ``parse`` turns it into the flat plant dict
the reader builds a plant from, and ``render`` turns the flat dict a plant writes back into the
file, so there is one reader and one writer of the flat dict and one pair for the file.
"""

from dataclasses import dataclass, field

from gemini import units
from gemini._utils.strings import close_matches, join_path
from gemini.errors.base import Issue
from gemini.units import display, inputs

FLAT_FORMAT = 2
ALLOWED = (
    "format",
    "kind",
    "name",
    "type",
    "size",
    "modules",
    "connections",
    "inlets",
    "outlets",
    "outputs",
    "constraints",
    "params",
    "fluids",
    "boundary",
    "optional",
    "choices",
    "bypass",
)
TYPES = {
    "type": str,
    "size": dict,
    "modules": dict,
    "connections": list,
    "inlets": dict,
    "outlets": dict,
    "outputs": dict,
    "constraints": list,
    "params": dict,
    "fluids": dict,
    "boundary": dict,
    "optional": list,
    "choices": dict,
    "bypass": dict,
}
MARKERS = {"value", "unit", "range", "options", "history", "uncertainty"}
CONTROL = "control"
CONTROLS = ("dispatch", "outages")
"""The plant-level controls: ``params.control.<name>`` in the file, parameter ``<name>``."""
MISSING = object()
GONE = {
    "bindings": "bindings are not part of a plant file; set them in memory with set_bindings",
    "inputs": "a control or a boundary is a leaf of params, at the path of its module",
}


@dataclass
class Parsed:
    """What ``parse`` makes of a plant file."""

    header: inputs.Header
    flat: dict
    leaves: dict = field(default_factory=dict)
    sizes: dict = field(default_factory=dict)
    structure: dict | None = None
    superstructure: dict = field(default_factory=dict)


def issue(issues, path, kind, message, **details):
    """Append one ``Issue``."""
    issues.append(Issue(path, kind, message, **details))


def is_leaf(node):
    """Return whether ``node`` is a leaf object rather than the subtree of a module."""
    return isinstance(node, dict) and bool(MARKERS & set(node))


def flat_name(path):
    """Return the flat name of a leaf path: ``a.control.dispatch`` is ``a.dispatch``."""
    parts = path.split(".")
    if len(parts) > 1 and parts[-2] == CONTROL and parts[-1] in CONTROLS:
        del parts[-2]
    return ".".join(parts)


def file_path(name):
    """Return the leaf path of a flat name: a plant-level control sits under ``control``."""
    parts = name.split(".")
    if parts[-1] in CONTROLS:
        parts.insert(len(parts) - 1, CONTROL)
    return ".".join(parts)


def flat_value(node):
    """Return the flat value of a leaf object: ``{"value", "unit"}`` or the value; else MISSING."""
    if not isinstance(node, dict) or "value" not in node:
        return MISSING
    if "unit" in node:
        return {"value": node["value"], "unit": node["unit"]}
    return node["value"]


def _walk(tree, prefix, found, issues):
    """Collect ``{leaf path: node}`` of ``tree`` in file order; a node that is no object is kept."""
    for key, node in tree.items():
        path = join_path(prefix, key)
        if "." in key:
            _dotted(path, key, issues)
        elif not isinstance(node, dict) or is_leaf(node):
            found[path] = node
        elif key == CONTROL:
            _controls(node, path, found, issues)
        else:
            _walk(node, path, found, issues)


def _dotted(path, key, issues):
    """Append the issue of a key of ``params`` that is a path: the tree has one level for each."""
    parts = key.split(".")
    nested = "".join(f'{{"{part}": ' for part in parts) + "..." + "}" * len(parts)
    issue(
        issues,
        f"params.{path}",
        "not_allowed",
        f"params.{path}: a key is one name, not a path; expected the nested form {nested}",
    )


def _controls(node, path, found, issues):
    for name, leaf in node.items():
        if name in CONTROLS:
            found[join_path(path, name)] = leaf
            continue
        issue(
            issues,
            join_path(path, name),
            "unknown_key",
            f"{join_path(path, name)}: unknown control; expected one of {', '.join(CONTROLS)}",
            suggestions=tuple(close_matches(name, CONTROLS)),
        )


def _sizes(data, issues):
    found = {}
    for name, node in data.items():
        found[name] = node
        if not isinstance(node, dict):
            issue(
                issues,
                f"size.{name}",
                "missing",
                f"size.{name} = {node!r}; expected an object like {{'value': 2}}",
            )
    return found


def _typed(data, issues):
    for key, expected in TYPES.items():
        if key in data and not isinstance(data[key], expected):
            issue(
                issues,
                key,
                "incompatible",
                f"{key} = {type(data[key]).__name__}; expected {expected.__name__}",
            )
            data = {k: v for k, v in data.items() if k != key}
    return data


def _keys(data, issues):
    for key, message in GONE.items():
        if key in data:
            issue(issues, key, "unknown_key", f"{key}: {message}")
    rest = {key: value for key, value in data.items() if key not in GONE}
    inputs.check_keys(rest, ALLOWED, "", issues)
    return {key: value for key, value in rest.items() if key in ALLOWED}


def _history(leaves):
    """Return ``{module path: [{valid_from, params}]}`` of the ``history`` of the leaves."""
    found = {}
    for path, node in leaves.items():
        if not is_leaf(node) or not isinstance(node.get("history"), list):
            continue
        module, _, name = flat_name(path).rpartition(".")
        for item in node["history"]:
            if not isinstance(item, dict) or "valid_from" not in item:
                continue
            unit = item.get("unit", node.get("unit"))
            value = item.get("value")
            stamped = {"value": value, "unit": unit} if unit else value
            entries = found.setdefault(module, [])
            entry = next((e for e in entries if e["valid_from"] == item["valid_from"]), None)
            if entry is None:
                entry = {"valid_from": item["valid_from"], "params": {}}
                entries.append(entry)
            entry["params"][name] = stamped
    return found


def _module_keys(entries, prefix=""):
    """Return the paths of the modules of a ``modules`` mapping that are no groups."""
    found = []
    for name, entry in entries.items():
        key = join_path(prefix, name)
        nested = entry.get("modules") if isinstance(entry, dict) else None
        if isinstance(nested, dict):
            found += _module_keys(nested, key)
        else:
            found.append(key)
    return found


def _owner(path, keys):
    """Return the module key a leaf path belongs to, else ``None``."""
    owners = [key for key in keys if path.startswith(key + ".")]
    return max(owners, key=len) if owners else None


def _entries(entries, params, keys, prefix=""):
    """Return the flat ``modules`` mapping: each entry with the local params of its module."""
    result = {}
    for name, entry in entries.items():
        if not isinstance(entry, dict):
            result[name] = entry
            continue
        key = join_path(prefix, name)
        item = {k: v for k, v in entry.items() if k != "modules"}
        if isinstance(entry.get("modules"), dict):
            item["modules"] = _entries(entry["modules"], params, keys, key)
        else:
            item["params"] = params.get(key, {})
        result[name] = item
    return result


def _split(flat_params, keys):
    """Return ``({module key: local params}, root params)`` of the absolute flat params."""
    local, root = {}, {}
    for path, value in flat_params.items():
        key = _owner(path, keys)
        if key is None:
            root[path] = value
        else:
            local.setdefault(key, {})[path[len(key) + 1 :]] = value
    return local, root


def _flat_params(leaves):
    found = {}
    for path, node in leaves.items():
        value = flat_value(node)
        if value is not MISSING:
            found[flat_name(path)] = value
    return found


def _sections(data, leaves):
    kept = {key: data[key] for key in ("fluids", "boundary") if key in data}
    history = _history(leaves)
    return kept | ({"param_history": history} if history else {})


def _structure(data, name, flat_params, sections):
    keys = _module_keys(data.get("modules", {}))
    local, root = _split(flat_params, keys)
    flat = {"format": FLAT_FORMAT, "name": name}
    flat["modules"] = _entries(data.get("modules", {}), local, keys)
    for key in ("connections", "inlets", "outlets", "outputs", "constraints"):
        if key in data:
            flat[key] = data[key]
    return flat | ({"params": root} if root else {}) | sections


def parse(data, issues):
    """Return the ``Parsed`` file ``data``, or ``None`` with the header issues; others append."""
    header = inputs.from_header(data, "plant", "", issues)
    if header is None:
        return None
    data = _typed(_keys(data, issues), issues)
    leaves = {}
    _walk(data.get("params", {}), "", leaves, issues)
    sizes = _sizes(data.get("size", {}), issues)
    flat_params = _flat_params(leaves)
    sections = _sections(data, leaves)
    has_type, has_structure = "type" in data, "modules" in data or "connections" in data
    if not has_type and not has_structure:
        issue(
            issues,
            "type",
            "missing",
            "type: expected a plant class, or modules and connections that state the structure",
        )
    flat, structure = {"format": FLAT_FORMAT, "name": header.name}, None
    if has_type:
        flat |= {"type": data["type"], "params": flat_params} | sections
        flat |= {"size": {n: flat_value(node) for n, node in sizes.items()}} if sizes else {}
        flat["size"] = {n: v for n, v in flat.get("size", {}).items() if v is not MISSING}
        if has_structure:
            structure = _structure(data, header.name, flat_params, sections)
    else:
        flat = _structure(data, header.name, flat_params, sections)
    stated = {key: data[key] for key in ("optional", "choices", "bypass") if key in data}
    return Parsed(header, flat, leaves, sizes, structure, stated)


def _leaf_node(value, extra, written_unit):
    """Return the leaf object of a flat value and the search leaf ``extra`` of its path."""
    node = {}
    if value is not MISSING:
        node = dict(value) if _is_quantity(value) else {"value": value}
        written_unit = node.get("unit")
    elif extra is not None and extra.unit is not None:
        written_unit = display.written_unit(extra.unit, extra.quantity)
        node = {"unit": written_unit}
    if extra is not None and extra.range is not None:
        node["range"] = _range_in(extra, written_unit)
    if extra is not None and extra.options is not None:
        node["options"] = list(extra.options)
    return node


def _is_quantity(value):
    return isinstance(value, dict) and set(value) == {"value", "unit"}


def _range_in(extra, unit):
    """Return the range of ``extra`` in ``unit``, as stated when the unit is the same."""
    if unit is None or unit == extra.unit:
        return extra.range.to_json()
    return {
        side: units.convert(number, extra.unit, unit, extra.quantity)
        for side, number in extra.range.to_json().items()
    }


def _history_item(entry, value, node):
    """Return the item of a leaf's ``history`` for one dated ``value`` of the leaf ``node``."""
    item = {"valid_from": entry["valid_from"]}
    if not _is_quantity(value):
        return item | {"value": value}
    if "value" not in node and "unit" not in node:
        node["unit"] = value["unit"]
    item["value"] = value["value"]
    return item | ({"unit": value["unit"]} if value["unit"] != node.get("unit") else {})


def _history_into(nodes, histories):
    for module, entries in histories.items():
        for entry in entries:
            for name, value in entry["params"].items():
                node = nodes.setdefault(join_path(module, name), {})
                node.setdefault("history", []).append(_history_item(entry, value, node))


def _module_params(entries, prefix=""):
    found = {}
    for name, entry in entries.items():
        key = join_path(prefix, name)
        for local, value in entry.get("params", {}).items():
            found[join_path(key, local)] = value
        found |= _module_params(entry.get("modules", {}), key)
    return found


def _skeleton(entries):
    result = {}
    for name, entry in entries.items():
        item = {"type": entry["type"]}
        if entry.get("size"):
            item["size"] = entry["size"]
        if entry.get("modules"):
            item["modules"] = _skeleton(entry["modules"])
        result[name] = item
    return result


def _nest(nodes):
    tree = {}
    for path, node in nodes.items():
        *parents, last = path.split(".")
        at = tree
        for part in parents:
            at = at.setdefault(part, {})
        at[last] = node
    return tree


def _params_tree(plant, flat):
    values = dict(flat.get("params", {})) | _module_params(flat.get("modules", {}))
    values |= flat.get("inputs", {})
    nodes = {}
    search = {path: extra for path, extra in plant._search.items() if not path.startswith("size.")}
    for path, extra in search.items():
        name = flat_name(path)
        nodes[path] = _leaf_node(values.pop(name, MISSING), extra, None)
    for name, value in values.items():
        nodes[file_path(name)] = _leaf_node(value, None, None)
    _history_into(nodes, flat.get("param_history", {}))
    return _nest(nodes)


def _size_tree(plant, flat):
    found = {}
    for name, value in flat.get("size", {}).items():
        extra = plant._search.get(f"size.{name}")
        quantity = None if extra is None else extra.quantity
        found[name] = _leaf_node(display.written(value, quantity), extra, None)
    return found


def _superstructure(plant):
    """Return the ``optional``, ``choices`` and ``bypass`` of the plant file, none when empty."""
    found = {"optional": list(plant._optional)} if plant._optional else {}
    if plant._choices:
        found["choices"] = {
            name: {group: list(members) for group, members in groups.items()}
            for name, groups in plant._choices.items()
        }
    if plant._bypass:
        found["bypass"] = {name: dict(pairs) for name, pairs in plant._bypass.items()}
    return found


def render(plant, flat):
    """Return the plant file of the flat dict ``flat`` that ``plant`` writes."""
    file = plant._file
    doc = {"format": inputs.FORMAT, "kind": "plant", "name": file.get("name") or flat["name"]}
    if file.get("about") is not None:
        doc["about"] = file["about"]
    if "type" in flat:
        doc["type"] = flat["type"]
    if flat.get("size"):
        doc["size"] = _size_tree(plant, flat)
    if "modules" in flat:
        doc["modules"] = _skeleton(flat["modules"])
    for key in ("connections", "inlets", "outlets", "outputs", "constraints"):
        if key in flat:
            doc[key] = flat[key]
    doc["params"] = _params_tree(plant, flat)
    for key in ("fluids", "boundary"):
        if flat.get(key):
            doc[key] = flat[key]
    return doc | _superstructure(plant)
