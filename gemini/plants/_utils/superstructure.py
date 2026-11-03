"""The superstructure of a plant: modules that may be off, and choices of one group among several.

A plant states which of its modules may be absent (``set_optional``) and which groups of modules
are alternatives (``set_choice``). A structure says, for each optional module, whether it is on and,
for each choice, which group is on. ``concrete`` returns the ordinary plant of a structure: every
module that is off is taken out and bypassed, each stream inlet joined to its outlet of the same
path, so that what fed the module feeds what the module fed. A module's bypass is its pairs
``<name>_in`` -> ``<name>_out``, or the ``bypass`` its class declares; its power ports and its
other ports are dropped with it. A module with no pair and no declared bypass cannot be off.
"""

from copy import deepcopy
from itertools import product

from gemini._utils.strings import close_matches, did_you_mean, join_names, join_path
from gemini.errors import GeminiError, ValidationError
from gemini.errors.base import Issue
from gemini.plants._utils.plan import is_group, split_end
from gemini.plants._utils.serialization import tree_params

OPTIONAL = "optional"
CHOICES = "choices"
KEYS = (OPTIONAL, CHOICES)
"""The keys of the plant file that state a superstructure."""
OWN = {"control", "dispatch", "outages", "backup"}
"""The values of a plant without a class, which the plant of a structure keeps."""


def _module_paths(plant):
    """Return the paths of the modules of ``plant`` that have ports, in the order of the tree."""
    return [path for path, module in plant.named_modules() if path and not is_group(module)]


def _known(plant, name, where):
    """Return the module at ``name``, or raise ``unknown_name`` with the close paths."""
    paths = _module_paths(plant)
    if name not in paths:
        raise ValidationError(
            f"{where}: module = {name!r}; expected a module of the plant"
            f"{did_you_mean(name, paths)}",
            path=where,
            code="unknown_name",
            suggestions=close_matches(name, paths),
        )
    return plant.get_submodule(name)


def pairs(module, name):
    """Return ``{inlet: outlet}``, the bypass of the module at ``name``, or raise.

    The class's ``bypass`` when it declares one, else every stream inlet ``<x>_in`` with a stream
    outlet ``<x>_out``. A module with neither cannot be bypassed: which outlet an inlet joins is
    ambiguous, and ``invalid_design`` asks for a ``bypass`` on the class.
    """
    inlets, outlets = module.inlets(), module.outlets()
    declared = getattr(type(module), "bypass", None)
    if declared is not None:
        found = dict(declared)
        unknown = [p for p in found if p not in inlets] + [
            p for p in found.values() if p not in outlets
        ]
        if unknown:
            raise ValidationError(
                f"{name}: {type(module).__name__}.bypass names {join_names(unknown)}; expected "
                "inlets and outlets of the module",
                path=name,
                code="invalid_design",
            )
        return found
    found = {}
    for port, declaration in inlets.items():
        if not port.endswith("_in") or not declaration.carries_stream:
            continue
        partner = port[: -len("_in")] + "_out"
        if partner in outlets and outlets[partner].carries_stream:
            found[port] = partner
    if not found:
        raise ValidationError(
            f"{name}: a {type(module).__name__} has no stream inlet <name>_in with an outlet "
            "<name>_out, so how to bypass it is ambiguous; expected a class that declares "
            "bypass = {inlet: outlet}",
            path=name,
            code="invalid_design",
        )
    return found


def _declared(plant):
    """Return ``{module: where}`` of every module the superstructure of ``plant`` names."""
    found = {name: OPTIONAL for name in plant._optional}
    for choice, groups in plant._choices.items():
        for members in groups.values():
            found |= {name: f"{CHOICES}.{choice}" for name in members}
    return found


def _free(plant, name, where, ignore=None):
    """Raise when ``name`` is already named by the superstructure or overlaps a named module."""
    for other, owner in _declared(plant).items():
        if owner == ignore:
            continue
        if other == name:
            raise ValidationError(
                f"{where}: module {name!r} is already in {owner}; a module is optional or in one "
                "choice",
                path=where,
                code="invalid_design",
            )
        if other.startswith(name + ".") or name.startswith(other + "."):
            raise ValidationError(
                f"{where}: module {name!r} contains or is inside {other!r} of {owner}; expected "
                "modules apart",
                path=where,
                code="invalid_design",
            )


def set_optional(plant, name, optional):
    """State that the module ``name`` may be off (``optional``), or that it is always on."""
    if not isinstance(optional, bool):
        raise ValidationError(
            f"set_optional: optional = {optional!r}; expected true or false",
            path=OPTIONAL,
            code="invalid_value",
        )
    if not optional:
        plant._optional = [item for item in plant._optional if item != name]
        return
    if name in plant._optional:
        return
    pairs(_known(plant, name, OPTIONAL), name)
    _free(plant, name, OPTIONAL)
    if name in plant._choices:
        raise ValidationError(
            f"{OPTIONAL}: {name!r} is the name of a choice; expected a module apart from them",
            path=OPTIONAL,
            code="invalid_design",
        )
    plant._optional = [*plant._optional, name]


def set_choice(plant, name, groups):
    """State the choice ``name`` among ``groups`` ``{group: [modules]}``; ``None`` removes it."""
    where = f"{CHOICES}.{name}"
    if groups is None:
        plant._choices = {key: value for key, value in plant._choices.items() if key != name}
        return
    if not isinstance(name, str) or not name:
        raise ValidationError(
            f"set_choice: name = {name!r}; expected a text", path=CHOICES, code="invalid_value"
        )
    if not isinstance(groups, dict) or len(groups) < 2:
        raise ValidationError(
            f"{where}: groups = {groups!r}; expected at least two groups {{name: [modules]}}",
            path=where,
            code="invalid_value",
        )
    if name in plant._optional:
        raise ValidationError(
            f"{where}: {name!r} is an optional module; expected another name for the choice",
            path=where,
            code="invalid_design",
        )
    seen = set()
    for group, members in groups.items():
        at = f"{where}.{group}"
        if not isinstance(group, str) or not isinstance(members, (list, tuple)):
            raise ValidationError(
                f"{at}: expected a group name with a list of modules", path=at, code="invalid_value"
            )
        for member in members:
            pairs(_known(plant, member, at), member)
            _free(plant, member, at, ignore=where)
            if member in seen:
                raise ValidationError(
                    f"{at}: module {member!r} is in two groups; expected groups apart",
                    path=at,
                    code="invalid_design",
                )
            seen.add(member)
    plant._choices = plant._choices | {name: {key: list(value) for key, value in groups.items()}}


def keys(plant):
    """Return the keys of a structure of ``plant``: its optional modules, then its choices."""
    return [*plant._optional, *plant._choices]


def every(plant):
    """Return every structure of ``plant``, valid or not, in a fixed order."""
    sides = [(True, False)] * len(plant._optional) + [tuple(g) for g in plant._choices.values()]
    return [dict(zip(keys(plant), chosen)) for chosen in product(*sides)]


def _named(plant, structure):
    """Raise unless ``structure`` is a dict that gives a value for every key and no other key."""
    if not isinstance(structure, dict):
        raise ValidationError(
            f"with_structure: structure = {structure!r}; expected a dict",
            path="structure",
            code="invalid_value",
        )
    expected = keys(plant)
    missing = [key for key in expected if key not in structure]
    unknown = [key for key in structure if key not in expected]
    if unknown:
        raise ValidationError(
            f"structure: unknown {join_names(unknown)}; expected {join_names(expected) or 'none'}",
            path=f"structure.{unknown[0]}",
            code="unknown_name",
            suggestions=close_matches(unknown[0], expected),
        )
    if missing:
        raise ValidationError(
            f"structure: {join_names(missing)} not given; expected a value for each of "
            f"{join_names(expected)}",
            path=f"structure.{missing[0]}",
            code="missing_value",
        )


def off(plant, structure):
    """Return the modules a structure turns off, after checking it names every key once."""
    _named(plant, structure)
    found = []
    for name in plant._optional:
        if not isinstance(structure[name], bool):
            raise ValidationError(
                f"structure.{name} = {structure[name]!r}; expected true or false",
                path=f"structure.{name}",
                code="invalid_value",
            )
        if not structure[name]:
            found.append(name)
    for name, groups in plant._choices.items():
        if structure[name] not in groups:
            raise ValidationError(
                f"structure.{name} = {structure[name]!r}; expected one of {join_names(groups)}",
                path=f"structure.{name}",
                code="invalid_value",
                suggestions=close_matches(str(structure[name]), list(groups)),
            )
        found += [
            m for group, members in groups.items() if group != structure[name] for m in members
        ]
    return found


def _inside(path, names):
    """Return whether ``path`` is one of the module paths ``names`` or below one."""
    return any(path == name or path.startswith(name + ".") for name in names)


def _edges(data):
    """Return the edges of a plant dict: ``(source, target, state)``; a plant port is a tuple."""
    found = [
        (item["source"], item["target"], item.get("type") == "state")
        for item in data.get("connections", [])
    ]
    for name, ends in data.get("inlets", {}).items():
        found += [(("inlets", name), end, False) for end in _listed(ends)]
    for name, ends in data.get("outlets", {}).items():
        found += [(end, ("outlets", name), False) for end in _listed(ends)]
    return found


def _listed(ends):
    """Return the ends of a plant port as a list."""
    return list(ends) if isinstance(ends, list) else [ends]


def _off_end(end, names):
    """Return whether ``end``, a ``"path.port"`` or a plant port, is on a module that is off."""
    return isinstance(end, str) and _inside(split_end(end)[0], names)


def _bypassed(edges, bypass, names):
    """Return the edges between the modules that stay, each joined through the bypassed ones."""
    leaving = {}
    for source, target, state in edges:
        leaving.setdefault(source, []).append((target, state))

    def reached(target, state, seen):
        if not _off_end(target, names):
            return [(target, state)]
        path, port = split_end(target)
        outlet = bypass[path].get(port)
        if outlet is None or (path, port) in seen:
            return []
        seen = seen | {(path, port)}
        return [
            found
            for after, step in leaving.get(join_path(path, outlet), [])
            for found in reached(after, state or step, seen)
        ]

    kept = []
    for source, target, state in edges:
        if _off_end(source, names):
            continue
        for item in reached(target, state, frozenset()):
            joined = item[0] != target
            if joined and _same_module(source, item[0]):
                continue
            if (source, *item) not in kept:
                kept.append((source, *item))
    return kept


def _same_module(source, target):
    """Return whether two module ends belong to one module: a bypass that would loop it to itself.

    Such a join (the air of a dry cooler that is off, from the atmosphere back to it) carries
    nothing, so the bypass drops it.
    """
    if not (isinstance(source, str) and isinstance(target, str)):
        return False
    return split_end(source)[0] == split_end(target)[0]


def _rewired(data, edges):
    """Set the connections and the plant ports of ``data`` from ``edges``."""
    data["connections"] = [
        {"source": s, "target": t} | ({"type": "state"} if state else {})
        for s, t, state in edges
        if isinstance(s, str) and isinstance(t, str)
    ]
    for side in ("inlets", "outlets"):
        if side not in data:
            continue
        ports = {}
        for source, target, _ in edges:
            port, end = (source, target) if side == "inlets" else (target, source)
            if isinstance(port, tuple) and port[0] == side:
                ports.setdefault(port[1], []).append(end)
        data[side] = {
            name: ends if isinstance(data[side][name], list) else ends[0]
            for name, ends in ports.items()
            if name in data[side]
        }
        if not data[side]:
            del data[side]


def _drop_tree(tree, path):
    """Remove the node at the dotted ``path`` of a nested ``tree``, if it is there."""
    *parents, last = path.split(".")
    for part in parents:
        tree = tree.get(part)
        if not isinstance(tree, dict):
            return
    tree.pop(last, None)


def _drop_module(modules, path):
    """Remove the module at ``path`` from the ``modules`` of a plant file."""
    *parents, last = path.split(".")
    for part in parents:
        modules = modules.get(part, {}).get("modules", {})
    modules.pop(last, None)


def _mentions(value, names):
    """Return whether a constraint or an output mentions a path of a module that is off."""
    if isinstance(value, str):
        return _inside(value, names) or _inside(value.rpartition(".")[0], names)
    if isinstance(value, dict):
        return any(_mentions(item, names) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_mentions(item, names) for item in value)
    return False


def _pinned(plant):
    """Return a copy of a plant of a class with every value of its modules stated as it is.

    A plant of a class derives values of its modules from its own; without the class those values
    must be stated, or the plant file of the structure loses them.
    """
    copy = deepcopy(plant)
    for key, stated in copy._stated.items():
        if key:
            copy._stated[key] = tree_params(copy.get_submodule(key)) | stated
    return copy


def _plain_file(plant, cls):
    """Return the plant file of ``plant`` as modules and connections, without its class.

    The values of the plant itself other than ``OWN`` belong to its class and go.
    """
    if type(plant) is cls:
        return plant.to_dict()
    data = _pinned(plant).to_dict(structure=True)
    data.pop("type", None)
    data.pop("size", None)
    names = {path.split(".")[0] for path in _module_paths(plant)}
    params = data.get("params", {})
    data["params"] = {key: value for key, value in params.items() if key in names | OWN}
    return data


def concrete(plant, structure, cls):
    """Return the plant of ``structure``: the modules that are off taken out and bypassed.

    ``cls`` is ``Plant``, the class of a plant without a class. With no
    module off the plant is a copy of its class; else it is a plant of modules and connections.
    """
    names = off(plant, structure)
    if not names:
        copy = deepcopy(plant)
        copy._optional, copy._choices = [], {}
        return copy
    bypass = {name: pairs(plant.get_submodule(name), name) for name in names}
    data = _plain_file(plant, cls)
    for key in KEYS:
        data.pop(key, None)
    _rewired(data, _bypassed(_edges(data), bypass, names))
    for name in names:
        _drop_module(data.get("modules", {}), name)
        _drop_tree(data.get("params", {}), name)
        for section in ("fluids", "boundary"):
            if section in data:
                data[section] = {
                    key: value for key, value in data[section].items() if not _inside(key, names)
                }
    if "outputs" in data:
        data["outputs"] = {k: v for k, v in data["outputs"].items() if not _mentions(v, names)}
    if "constraints" in data:
        data["constraints"] = [item for item in data["constraints"] if not _mentions(item, names)]
    return cls.from_dict(data)


def is_valid(plant, structure, cls):
    """Return ``(plant or None, issues)`` of a structure: invalid when it has an error.

    A plant that cannot be read has the issues of its ``ValidationError``, and one whose run cannot
    be planned (a loop with no connection to cut) the error of the plan. A missing value is not
    held against a structure: every structure has it, and sizing or ``gm.check`` reports it.
    """
    try:
        found = concrete(plant, structure, cls)
    except GeminiError as error:
        problems = getattr(error, "problems", None) or [
            {"path": "", "code": error.code, "message": str(error)}
        ]
        return None, [
            Issue(item["path"] or "", "incompatible", item["message"]) for item in problems
        ]
    issues = [item for item in found.check() if not item.is_warning and item.kind != "missing"]
    if not issues:
        try:
            found._compiled()
        except GeminiError as error:
            issues = [Issue("connections", "incompatible", str(error), code="invalid_design")]
    return found, issues


def valid(plant, cls):
    """Return every structure of ``plant`` whose plant has no error, in the order of ``every``."""
    return [item for item in every(plant) if not is_valid(plant, item, cls)[1]]


def none_valid(plant, cls):
    """Return the issue of a superstructure with no valid structure, or none."""
    if valid(plant, cls):
        return []
    return [
        Issue(
            OPTIONAL if plant._optional else CHOICES,
            "incompatible",
            "no structure of the optional modules and choices gives a valid plant; expected at "
            "least one (see with_structure(...).check())",
            code="invalid_design",
        )
    ]


def from_file(plant, stated, issues):
    """Read the ``optional`` and ``choices`` of a plant file onto ``plant``; append each issue."""
    optional = stated.get(OPTIONAL, [])
    choices = stated.get(CHOICES, {})
    if not isinstance(optional, list):
        issues.append(Issue(OPTIONAL, "incompatible", "optional: expected a list of modules"))
        optional = []
    if not isinstance(choices, dict):
        issues.append(Issue(CHOICES, "incompatible", "choices: expected {name: {group: [...]}}"))
        choices = {}
    for index, name in enumerate(optional):
        try:
            set_optional(plant, name, True)
        except ValidationError as error:
            issues.append(_issue(f"{OPTIONAL}[{index}]", error))
    for name, groups in choices.items():
        try:
            set_choice(plant, name, groups)
        except ValidationError as error:
            issues.append(_issue(f"{CHOICES}.{name}", error))


def _issue(path, error):
    """Return the ``Issue`` of a refused declaration of the superstructure."""
    kind = "unknown_key" if error.code == "unknown_name" else "incompatible"
    return Issue(path, kind, str(error), suggestions=tuple(error.suggestions or ()))
