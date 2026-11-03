"""The union of plants: one superstructure whose structures give back each plant.

``union(plants, name=...)`` matches the modules of several concrete plants by name (the same name
and type are one module), keeps the modules every plant has as fixed and makes the others optional
or alternatives of a choice. Each plant is read as modules and connections (a plant of a class with
every value of its modules stated, as ``with_structure`` does). A **chain** of a plant starts at an
outlet of a fixed module (or a plant inlet), passes through the bypass pairs of modules that are not
fixed and ends at the first other inlet. The chains of the plants between the same two ends are
merged into one series, so that the bypass of the modules that are off gives back each plant's
wiring. The other connections are taken as they are. The result is verified: the structure of each
plant gives its modules and connections, or ``invalid_design`` names the plant and the connection.
"""

import math
from copy import deepcopy

from gemini import units
from gemini._utils.strings import join_names, join_path
from gemini.errors import GeminiError, ValidationError
from gemini.plants._utils import superstructure
from gemini.plants._utils.form import is_leaf
from gemini.plants._utils.plan import is_group, split_end
from gemini.plants.plant import Plant

SECTIONS = ("fluids", "boundary", "outputs")
"""The sections of the plant file merged by key, the first plant's entry kept."""


def union(plants, *, name):
    """Return one superstructure plant whose structures give back each of ``plants``.

    Modules match by name: one name with two types raises ``invalid_design`` naming both. A
    module of every plant is fixed. One of only some plants is optional, or a group of a choice
    when the plants put different modules at one place of a circuit (between the same two fixed
    modules); the modules that are always present with a group join it. Alternatives of one place
    sit in series, so that the bypass of those that are off restores each plant's wiring; a module
    that is not fixed needs a stream pair ``<x>_in``/``<x>_out``, a class ``bypass`` or a bypass
    one of the plants states for it (``set_bypass``), which the union keeps.

    A value stated differently in two plants keeps the first plant's value, its options joined
    and its range widened to cover every plant's range. The returned plant has the attribute
    ``union``: ``{"structures": {plant name: structure}, "notes": [{path, kept, values}]}``, where
    ``with_structure(union["structures"][n])`` has the modules and connections of the plant ``n``
    and ``notes`` lists each value the plants state differently (``values`` by plant name).
    Plants that no such superstructure reproduces raise ``invalid_design`` naming the plants and
    the connection.
    """
    labels = _inputs(plants, name)
    files = [_plain(plant) for plant in plants]
    present = {label: _leaves(plant) for label, plant in zip(labels, plants)}
    _same_types(plants, labels)
    nonfixed = _nonfixed(present, labels)
    bypass = _bypasses(plants, labels, present, nonfixed)
    walks = {
        label: _walk(superstructure._edges(data), nonfixed, bypass)
        for label, data in zip(labels, files)
    }
    lanes, order = _lanes(walks, labels)
    edges = _wiring(lanes, order, labels, present, bypass)
    choices, optional = _superstructure(lanes, labels, present, nonfixed)
    notes = []
    data = _file(files, labels, name, edges, notes)
    data["optional"] = optional
    data["choices"] = {key: dict(groups) for key, (groups, _) in choices.items()}
    declared = {path: p._bypass[path] for p in plants for path in p._bypass if path in nonfixed}
    data.pop("bypass", None)
    if declared:
        data["bypass"] = {path: dict(pairs) for path, pairs in declared.items()}
    try:
        merged = Plant.from_dict(data)
    except GeminiError as error:
        raise _design(f"union: the merged plant {name!r} cannot be read: {error}") from error
    structures = {
        label: {key: key in present[label] for key in optional}
        | {key: chosen[label] for key, (_, chosen) in choices.items()}
        for label in labels
    }
    for label, data_of in zip(labels, files):
        _verify(merged, label, structures[label], present[label], data_of)
    merged.union = {"structures": structures, "notes": notes}
    return merged


def _design(message):
    """Return the ``invalid_design`` error of a union."""
    return ValidationError(message, path="plants", code="invalid_design")


def _inputs(plants, name):
    """Return the names of ``plants``, after checking the call."""
    if not isinstance(name, str) or not name:
        raise ValidationError(
            f"union: name = {name!r}; expected the name of the new plant",
            path="name",
            code="invalid_value",
        )
    if not isinstance(plants, (list, tuple)) or len(plants) < 2:
        raise ValidationError(
            f"union: plants = {plants!r}; expected a list of at least two gm.Plant",
            path="plants",
            code="invalid_value",
        )
    for index, plant in enumerate(plants):
        if not isinstance(plant, Plant):
            raise ValidationError(
                f"union: plants[{index}] is a {type(plant).__name__}; expected a gm.Plant",
                path=f"plants[{index}]",
                code="invalid_value",
            )
        if plant._optional or plant._choices:
            raise ValidationError(
                f"union: plants[{index}] ({plant.name!r}) has optional modules or choices; "
                "expected a concrete plant (with_structure gives one)",
                path=f"plants[{index}]",
                code="invalid_value",
            )
    labels = [plant.name for plant in plants]
    twice = sorted({label for label in labels if labels.count(label) > 1})
    if twice:
        raise ValidationError(
            f"union: two plants are named {join_names(twice)}; expected distinct names, the "
            "keys of the structures",
            path="plants",
            code="invalid_value",
        )
    return labels


def _plain(plant):
    """Return the plant file of ``plant`` as modules and connections, every module value stated."""
    data = superstructure._plain_file(plant, Plant)
    for key in superstructure.KEYS:
        data.pop(key, None)
    return data


def _leaves(plant):
    """Return ``{path: type name}`` of the modules of ``plant`` that have ports."""
    return {
        path: type(module).__name__
        for path, module in plant.named_modules()
        if path and not is_group(module)
    }


def _same_types(plants, labels):
    """Raise when one module name has two types in two plants (groups included)."""
    seen = {}
    for label, plant in zip(labels, plants):
        for path, module in plant.named_modules():
            if not path:
                continue
            kind = type(module).__name__
            first = seen.setdefault(path, (label, kind))
            if first[1] != kind:
                raise _design(
                    f"union: module {path!r} is a {first[1]} in {first[0]!r} and a {kind} in "
                    f"{label!r}; expected one type per name (rename one of them)"
                )


def _nonfixed(present, labels):
    """Return the module paths that some plants lack, in the order the plants list them."""
    found = []
    for label in labels:
        for path in present[label]:
            if path not in found and not all(path in present[other] for other in labels):
                found.append(path)
    return found


def _bypasses(plants, labels, present, nonfixed):
    """Return ``{module: {inlet: outlet}}`` of each module that is not fixed, or raise."""
    found, missing = {}, []
    for path in nonfixed:
        owner = next(i for i, label in enumerate(labels) if path in present[label])
        declared = next((p._bypass[path] for p in plants if path in p._bypass), None)
        try:
            module = plants[owner].get_submodule(path)
            found[path] = superstructure.pairs(module, path, declared)
        except ValidationError:
            missing.append(f"{path} ({present[labels[owner]][path]})")
    if missing:
        raise _design(
            f"union: {join_names(missing)}: in some of the plants only, so each must be optional, "
            "and none has a stream inlet <x>_in with an outlet <x>_out to bypass it; merging these "
            "plants needs a bypass stated for each (set_bypass)"
        )
    return found


def _owner(end):
    """Return the module path of a ``"path.port"`` end; ``None`` for a plant port."""
    return split_end(end)[0] if isinstance(end, str) else None


def _show(end):
    """Return an end as text: ``"path.port"``, or ``inlets.<name>`` for a plant port."""
    return end if isinstance(end, str) else ".".join(end)


def _walk(edges, nonfixed, bypass):
    """Return the items of one plant's edges, in their order.

    A chain is ``(source, elements, target, marks)``: ``elements`` the ``(module, inlet)`` pairs it
    passes through, ``target`` ``None`` when it ends at an outlet left open, and ``marks`` the
    points (the source or an element) after which the connection is a ``state`` one. An item is
    ``("chains", [chain, ...])`` at the first edge of the chains that start there, or
    ``("edge", edge)`` for an edge on no chain.
    """
    leaving = {}
    for index, (source, _, _) in enumerate(edges):
        leaving.setdefault(source, []).append(index)
    used, starts = set(), {}
    for index, (source, _, _) in enumerate(edges):
        if _owner(source) not in nonfixed:
            found = _follow(edges, leaving, bypass, index)
            starts[index] = [chain for chain, _ in found]
            used.update(i for _, ids in found for i in ids)
    items = []
    for index, edge in enumerate(edges):
        if index in starts:
            items.append(("chains", starts[index]))
        elif index not in used:
            items.append(("edge", edge))
    return items


def _follow(edges, leaving, bypass, start):
    """Return ``[(chain, edge indices)]`` of the chains that begin with the edge ``start``."""
    source, target, state = edges[start]
    found, stack = [], [(target, (), {source} if state else set(), (start,))]
    while stack:
        target, elements, marks, ids = stack.pop()
        path, port = split_end(target) if isinstance(target, str) else (None, None)
        element = (path, port)
        if port not in bypass.get(path, {}) or element in elements:
            found.append(((source, elements, target, frozenset(marks)), ids))
            continue
        elements = (*elements, element)
        after = leaving.get(join_path(path, bypass[path][port]), [])
        if not after:
            found.append(((source, elements, None, frozenset(marks)), ids))
        for index in reversed(after):
            _, following, step = edges[index]
            mark = {element} if step else set()
            stack.append((following, elements, marks | mark, (*ids, index)))
    return found


def _key(chain):
    """Return the place of a chain: its two ends, or the chain itself for a loop back to a module.

    A chain that leaves a module and comes back to it (the air of a cooler, from the atmosphere
    back to it) is dropped by the bypass when its modules are off: such chains sit side by side.
    """
    source, elements, target, _ = chain
    if elements and _owner(source) is not None and _owner(source) == _owner(target):
        return (source, target, elements)
    return (source, target)


def _lanes(walks, labels):
    """Return ``({key: {plant: chain}}, order)``: the chains by place and the order of the file."""
    lanes, order = {}, []
    for label in labels:
        for kind, item in walks[label]:
            if kind == "edge":
                found = [("edge", item)]
            else:
                found = [("lane", _held(lanes, label, chain)) for chain in item]
            order += [entry for entry in found if entry not in order]
    return lanes, order


def _held(lanes, label, chain):
    """Hold ``chain`` of the plant ``label`` at its place in ``lanes``; return the place."""
    key = _key(chain)
    held = lanes.setdefault(key, {})
    if label in held and len(key) == 2:
        raise _design(
            f"union: {label!r} has two paths from {_show(key[0])} to "
            f"{_show(key[1]) if key[1] else 'an open outlet'} through modules that other plants "
            "lack; expected one path, alternatives in series"
        )
    held[label] = chain
    return key


def _wiring(lanes, order, labels, present, bypass):
    """Return the edges of the union: every place merged into one series, the rest as stated."""
    placed, merged = {}, {}
    for key, held in lanes.items():
        merged[key] = _series(key, held, labels, present)
        for element in merged[key]:
            other = placed.setdefault(element, key)
            if other != key:
                raise _design(
                    f"union: {element[0]}.{element[1]} sits {_place(other)} in "
                    f"{_quoted(lanes[other])} and {_place(key)} in {_quoted(held)}; "
                    "expected one place for a module port"
                )
    edges = []
    for kind, item in order:
        found = [item] if kind == "edge" else _chain_edges(item, merged[item], lanes, bypass)
        edges += [edge for edge in found if edge not in edges]
    return edges


def _quoted(labels):
    """Return plant names as text, each quoted."""
    return join_names([repr(label) for label in labels])


def _place(key):
    """Return the place of a chain as text."""
    target = _show(key[1]) if key[1] is not None else "an open outlet"
    return f"between {_show(key[0])} and {target}"


def _series(key, held, labels, present):
    """Return the elements of a place in one series that gives back each plant's chain."""
    if len(key) == 3:
        return list(key[2])
    if key[1] is not None:
        _lacking(key, held, labels, present)
    elements = []
    for chain in held.values():
        elements += [item for item in chain[1] if item not in elements]
    _one_place(key, held, present, elements)
    return _ordered(key, held, elements)


def _lacking(key, held, labels, present):
    """Raise when a plant with both ends of a place does not connect them."""
    source, target = key[0], key[1]
    needs = {_owner(end) for end in (source, target) if _owner(end) is not None}
    lacking = [label for label in labels if needs <= set(present[label]) and label not in held]
    if lacking:
        via = [f"{m}.{p}" for m, p in next(iter(held.values()))[1]]
        raise _design(
            f"union: {_quoted(held)} connect {_show(source)} to {_show(target)}"
            f"{' through ' + join_names(via) if via else ''}, {lacking[0]!r} does not; "
            "expected the same connections between the modules every plant has (only modules "
            "some plants lack may sit between them)"
        )


def _one_place(key, held, present, elements):
    """Raise when a plant has a module of a place but puts its port elsewhere."""
    for label, chain in held.items():
        for module, port in elements:
            if module in present[label] and (module, port) not in chain[1]:
                having = [lb for lb, other in held.items() if (module, port) in other[1]]
                raise _design(
                    f"union: {module}.{port} sits {_place(key)} in {_quoted(having)} but not in "
                    f"{label!r}, which has {module!r} elsewhere; expected one place for a module "
                    "port"
                )


def _ordered(key, held, elements):
    """Return ``elements`` in an order that keeps the order of each plant's chain, or raise."""
    before = {item: set() for item in elements}
    for chain in held.values():
        for earlier, later in zip(chain[1], chain[1][1:]):
            before[later].add(earlier)
    ordered = []
    while len(ordered) < len(elements):
        ready = [item for item in elements if item not in ordered and before[item] <= set(ordered)]
        if not ready:
            left = [module for module, port in elements if (module, port) not in ordered]
            raise _design(
                f"union: {join_names(left)} sit {_place(key)} in another order in "
                f"{_quoted(held)}; expected one order of the modules in series"
            )
        ordered.append(ready[0])
    return ordered


def _chain_edges(key, elements, lanes, bypass):
    """Return the edges of one place: its source, each element in series, then its target."""
    source, target = key[0], key[1]
    marks = frozenset().union(*(chain[3] for chain in lanes[key].values()))
    points = [source, *elements]
    sources = [source] + [join_path(m, bypass[m][p]) for m, p in elements]
    targets = [join_path(m, p) for m, p in elements] + ([target] if target is not None else [])
    return [(s, t, point in marks) for s, t, point in zip(sources, targets, points)]


def _superstructure(lanes, labels, present, nonfixed):
    """Return ``(choices, optional)``.

    ``choices`` is ``{name: (groups, chosen)}``, ``groups`` ``{group: [modules]}`` and ``chosen``
    ``{plant: group}``; ``optional`` lists the other modules that are not fixed.
    """
    taken, choices = set(), {}
    for key, held in lanes.items():
        if len(key) == 3 or key[1] is None or len(held) < len(labels):
            continue
        if any(_owner(end) in nonfixed for end in key[:2]):
            continue
        found = _choice(held, labels)
        if found is None or taken & {m for members in found[0].values() for m in members}:
            continue
        named, chosen = found
        choice = "_or_".join(group for group, members in named.items() if members)
        while choice in choices or choice in present[labels[0]]:
            choice += "_choice"
        choices[choice] = (named, chosen)
        taken |= {m for members in named.values() for m in members}
    for path in nonfixed:
        if path not in taken and _companion(path, choices, labels, present):
            taken.add(path)
    return choices, [path for path in nonfixed if path not in taken]


def _choice(held, labels):
    """Return ``(groups, chosen)`` when the plants put disjoint groups at a place, else ``None``."""
    groups = {label: list(dict.fromkeys(m for m, _ in held[label][1])) for label in labels}
    distinct = []
    for members in groups.values():
        if members not in distinct:
            distinct.append(members)
    flat = [m for members in distinct for m in members]
    if len([members for members in distinct if members]) < 2 or len(flat) != len(set(flat)):
        return None
    named = {(members[0] if members else "none"): members for members in distinct}
    chosen = {label: next(g for g, m in named.items() if m == groups[label]) for label in labels}
    return named, chosen


def _companion(path, choices, labels, present):
    """Add ``path`` to the group of a choice chosen by exactly the plants that have it."""
    having = {label for label in labels if path in present[label]}
    for named, chosen in choices.values():
        for group, members in named.items():
            if members and {label for label in labels if chosen[label] == group} == having:
                members.append(path)
                return True
    return False


def _file(files, labels, name, edges, notes):
    """Return the plant file of the union, its modules, values and sections merged."""
    data = {"format": files[0].get("format", 1), "kind": files[0].get("kind", "plant")}
    data["name"] = name
    data["modules"] = {}
    for item in files:
        _add_modules(data["modules"], item.get("modules", {}))
    data["connections"] = [
        {"source": s, "target": t} | ({"type": "state"} if state else {})
        for s, t, state in edges
        if isinstance(s, str) and isinstance(t, str)
    ]
    for side in ("inlets", "outlets"):
        ports = {}
        for source, target, _ in edges:
            port, end = (source, target) if side == "inlets" else (target, source)
            if isinstance(port, tuple) and port[0] == side:
                ports.setdefault(port[1], []).append(end)
        listed = {
            key
            for item in files
            for key, ends in item.get(side, {}).items()
            if isinstance(ends, list)
        }
        if ports:
            data[side] = {
                key: ends if key in listed or len(ends) > 1 else ends[0]
                for key, ends in ports.items()
            }
    trees = [(label, item.get("params", {})) for label, item in zip(labels, files)]
    data["params"] = _merge_tree(trees, "params", notes)
    for section in SECTIONS:
        held = [(label, item[section]) for label, item in zip(labels, files) if section in item]
        if held:
            data[section] = _merge_entries(held, section, notes)
    constraints = []
    for item in files:
        constraints += [c for c in item.get("constraints", []) if c not in constraints]
    if constraints:
        data["constraints"] = constraints
    return data


def _add_modules(into, entries):
    """Add the module entries of one plant file to ``into``; a group gathers its children."""
    for key, entry in entries.items():
        if key not in into:
            into[key] = deepcopy(entry)
        elif "modules" in entry:
            _add_modules(into[key].setdefault("modules", {}), entry["modules"])


def _merge_entries(held, section, notes):
    """Return the entries of a section by key, the first plant's kept and a difference noted."""
    merged = {}
    for key in dict.fromkeys(k for _, entries in held for k in entries):
        values = {label: entries[key] for label, entries in held if key in entries}
        kept = next(iter(values.values()))
        merged[key] = deepcopy(kept)
        if any(value != kept for value in values.values()):
            notes.append({"path": f"{section}.{key}", "kept": deepcopy(kept), "values": values})
    return merged


def _merge_tree(held, prefix, notes):
    """Return the params tree of the plants in ``held`` ``[(plant, tree)]``, merged leaf by leaf."""
    merged = {}
    for key in dict.fromkeys(k for _, tree in held for k in tree):
        present = [(label, tree[key]) for label, tree in held if key in tree]
        path = join_path(prefix, key)
        nodes = [node for _, node in present]
        if all(isinstance(node, dict) and not is_leaf(node) for node in nodes):
            merged[key] = _merge_tree(present, path, notes)
        elif all(is_leaf(node) for node in nodes):
            merged[key] = _merge_leaf(present, path, notes)
        else:
            merged[key] = deepcopy(nodes[0])
            if any(node != nodes[0] for node in nodes):
                notes.append({"path": path, "kept": deepcopy(nodes[0]), "values": dict(present)})
    return merged


def _merge_leaf(present, path, notes):
    """Return one leaf: the first value, the options joined and the ranges widened."""
    first = present[0][1]
    kept = deepcopy(first)
    unit = first.get("unit")
    nodes = [node for _, node in present]
    differs = any(not _same(first, node) for node in nodes[1:])
    ranges = [_range_in(node, unit) for node in nodes if isinstance(node.get("range"), dict)]
    if ranges:
        kept["range"] = {
            side: pick(item[side] for item in ranges if item.get(side) is not None)
            for side, pick in (("min", min), ("max", max))
            if any(item.get(side) is not None for item in ranges)
        }
    options = [node["options"] for node in nodes if isinstance(node.get("options"), list)]
    if options:
        kept["options"] = list(dict.fromkeys(o for listed in options for o in listed))
    if (
        differs
        or kept.get("range") != first.get("range")
        or kept.get("options") != first.get("options")
    ):
        notes.append({"path": path, "kept": deepcopy(kept), "values": dict(present)})
    return kept


def _in_unit(number, unit, to):
    """Return ``number`` of ``unit`` in the unit ``to``; a number without unit stays."""
    if not isinstance(number, (int, float)) or unit is None or to is None or unit == to:
        return number
    return units.convert(number, unit, to)


def _same(first, node):
    """Return whether two leaves state the same value (in the first leaf's unit)."""
    if first.get("unit") != node.get("unit") and (first.get("unit") is None) != (
        node.get("unit") is None
    ):
        return False
    value = _in_unit(node.get("value"), node.get("unit"), first.get("unit"))
    kept = first.get("value")
    if isinstance(kept, (int, float)) and isinstance(value, (int, float)):
        return math.isclose(kept, value, rel_tol=1e-12, abs_tol=0.0)
    return kept == value


def _range_in(node, unit):
    """Return the range of a leaf in ``unit``."""
    return {
        side: _in_unit(number, node.get("unit"), unit) for side, number in node["range"].items()
    }


def _verify(merged, label, structure, present, data):
    """Raise unless the plant of ``structure`` has the modules and connections of the plant."""
    try:
        plant = merged.with_structure(structure)
    except GeminiError as error:
        raise _design(
            f"union: the structure {structure} of {label!r} gives no plant: {error}"
        ) from error
    found = _leaves(plant)
    if found != present:
        extra = sorted(set(found) - set(present))
        lost = sorted(set(present) - set(found))
        raise _design(
            f"union: the structure {structure} does not give back {label!r}: modules "
            f"{join_names(extra) or 'none'} added, {join_names(lost) or 'none'} lost"
        )
    want = set(superstructure._edges(data))
    got = set(superstructure._edges(plant.to_dict()))
    if want != got:
        lost = sorted(want - got, key=str)
        extra = sorted(got - want, key=str)
        said = [f"{_show(s)} -> {_show(t)} lost" for s, t, _ in lost[:1]]
        said += [f"{_show(s)} -> {_show(t)} added" for s, t, _ in extra[:1]]
        raise _design(
            f"union: the structure {structure} does not give back {label!r}: connection "
            f"{' and '.join(said)}; the plants wire these modules in ways no series of optional "
            "modules can give"
        )
