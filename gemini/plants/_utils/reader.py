"""Read a plant dict into a plant, collecting every problem with its path in the dict."""

import re
from copy import deepcopy

from gemini._utils import registry
from gemini._utils.strings import close_matches, did_you_mean, join_path
from gemini.errors import GeminiError, ValidationError
from gemini.errors.base import Issue, problem, raise_issues
from gemini.modules._utils import design
from gemini.modules._utils.serialization import (
    SECTIONS,
    Report,
    format_error,
    from_params,
    from_sections,
    located,
    tree_params,
)
from gemini.plants._utils import form, inputs, leaves, outputs
from gemini.plants._utils.factory import built, make_module
from gemini.plants._utils.plan import is_group, unconnected_port

TYPES = {
    "name": str,
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
    "param_history": dict,
}
KEYS = ("format", *TYPES)


def _unknown(module, name):
    """Return the error of a leaf that is no parameter, control or boundary of ``module``."""
    names = [*(path for path, _ in module.named_parameters()), *module.inputs()]
    return ValidationError(
        f"{module.path}: unknown parameter or control {name!r}{did_you_mean(name, names)}",
        path=name,
        suggestions=close_matches(name, names),
        code="unknown_name",
    )


def _declaration(module, name):
    """Return the declaration of ``name`` or ``None`` when the name is not a parameter."""
    try:
        return design.parameter(module, name)
    except GeminiError as error:
        if error.code == "unknown_name":
            raise _unknown(module, name) from error
        return None


def _refuse_owned(declaration, name):
    """Raise ``invalid_value`` for a leaf on a value the case gives, naming its case path."""
    if declaration is not None and getattr(declaration, "case", None) is not None:
        raise ValidationError(
            f"{name} is not a design value of the plant; give it in the case, at "
            f"{declaration.case}",
            path=name,
            code="invalid_value",
        )


def _checked_params(module, params, report, prefix):
    """Return the ``params`` that fit, reporting each other as ``invalid_value``.

    A value the case holds is refused, naming where it lives, and so is a number with a unit that
    is no ``{"value", "unit"}``.
    """
    kept = {}
    for name, value in params.items():
        with report.guard(prefix):
            declaration = _declaration(module, name)
            _refuse_owned(declaration, name)
            if declaration is not None:
                design.refuse_bare(declaration, value, name)
            kept[name] = value
    return kept


def _shape(data, report):
    """Return ``data`` without the keys that are unknown or of the wrong JSON type."""
    clean = {}
    for key, value in data.items():
        if key not in KEYS:
            error = ValidationError(
                f"unknown key {key!r}; valid: {', '.join(KEYS)}{did_you_mean(key, KEYS)}",
                path=key,
                code="invalid_format",
                suggestions=close_matches(key, KEYS),
            )
            report.items.append(located("", error))
        elif key in TYPES and not isinstance(value, TYPES[key]):
            error = ValidationError(
                f"{key} = {type(value).__name__}; expected {TYPES[key].__name__}",
                path=key,
                code="invalid_format",
            )
            report.items.append(located("", error))
        else:
            clean[key] = value
    return clean


def _entry(plant, prefix, name, entry, report, path):
    with report.guard(path):
        if not isinstance(entry, dict) or not isinstance(entry.get("type"), str):
            raise ValidationError(
                f"{name}: expected {{type, params}}", path="type", code="invalid_format"
            )
        key = join_path(prefix, name)
        try:
            module, _ = make_module(entry["type"], entry.get("size"))
        except GeminiError:
            report.broken.add(key)
            raise
        if is_group(module):
            plant._attach(key, module, None, {})
            for child, item in entry.get("modules", {}).items():
                _entry(plant, key, child, item, report, f"{path}.modules.{child}")
            return
        baseline = tree_params(module)
        controls = module.inputs()
        given = entry.get("params", {})
        values = {name: value for name, value in given.items() if name not in controls}
        params = _checked_params(module, values, report, f"{path}.params")
        from_params(module.set_params, params, report, f"{path}.params")
        plant._attach(key, module, deepcopy(values) if "params" in entry else None, baseline)
        _set_inputs(
            plant,
            {join_path(key, name): value for name, value in given.items() if name in controls},
            report,
        )


def _connection(plant, item, report):
    if not isinstance(item, dict) or not all(
        isinstance(item.get(k), str) for k in ("source", "target")
    ):
        raise ValidationError("expected {source, target, type?}", path="", code="invalid_format")
    usable = [end for end in ("source", "target") if not report.skips(item[end])]
    if len(usable) == 2:
        plant._link(item["source"], item["target"], item.get("type"), explicit=True)
        return
    for end in usable:
        plant._candidates(item[end], end, explicit=True)


def _port(plant, side, name, ends, report):
    """Name one plant port; several ends share a power port or the air."""
    for end in ends if isinstance(ends, list) else [ends]:
        if not isinstance(end, str):
            raise ValidationError(f"{name}: expected 'path.port'", code="invalid_format")
        if report.skips(end):
            continue
        if side == "inlets":
            plant._link(name, end, None, explicit=True)
        else:
            plant._link(end, name, None, explicit=True)


def _outputs(plant, entries, report):
    plant._output_entries = {}
    for name, data in outputs.ordered(entries):
        with report.guard(f"outputs.{name}"):
            if not isinstance(data, dict):
                raise ValidationError(f"{name}: expected a mapping", code="invalid_format")
            key, paths = outputs.check(name, data)
            if any(report.skips(path) for path in paths):
                continue
            plant._register_declaration(name, outputs.declare(plant, name, data))


def _ends(data):
    """Return every port the dict names, also those of an entry that failed to read."""
    connections = [item for item in data.get("connections", []) if isinstance(item, dict)]
    ends = {item.get(end) for item in connections for end in ("source", "target")}
    for side in ("inlets", "outlets"):
        for named in data.get(side, {}).values():
            ends |= set(named) if isinstance(named, list) else {named}
    return ends


def _check_ports(plant, data, report):
    """Report each port no entry of ``data`` names; a named port that failed has its problem."""
    named = _ends(data)
    for _, path, port in plant._unconnected_ports():
        end = join_path(path, port)
        if end not in named and not report.skips(end):
            with report.guard(""):
                raise unconnected_port(end)


def root_problems(data):
    """Return a problem for each plant port of a root plant.

    Every edge of a root plant is a module, so it has no plant ports. A registered plant is a
    building block for other plants: its ports are its interface.
    """
    if not isinstance(data, dict) or data.get("name") in registry.names():
        return []
    return [
        problem(
            f"{side}.{name}",
            "root_plant_port",
            f"{name}: a root plant has no plant ports; connect it to a module of the grids or "
            "the environment",
        )
        for side in ("inlets", "outlets")
        for name in data.get(side, {})
    ]


def _is_input(plant, path):
    return path in plant.inputs() or inputs._port_field(plant, path) is not None


def _root_values(plant, params, report):
    """Set the plant-level ``params``: parameters of the tree, controls and plant inlet fields."""
    given = {path: value for path, value in params.items() if _is_input(plant, path)}
    rest = {path: value for path, value in params.items() if path not in given}
    checked = _checked_params(plant, rest, report, "params")
    from_params(plant.set_params, checked, report)
    _set_inputs(plant, given, report)


def _set_inputs(plant, values, report):
    """Set controls and boundaries by path, each path its own problem."""
    for path, value in values.items():
        if report.skips(path):
            continue
        with report.guard("params"):
            _refuse_owned(inputs.declaration(plant, path), path)
            inputs.refuse_bare(plant, path, value)
            inputs.refuse_fluid(plant, path, value)
            plant._set_si_inputs({path: value})


def populate(plant, data, report):
    """Add the modules, connections, ports, outputs and sections of ``data`` to ``plant``."""
    for name, entry in data.get("modules", {}).items():
        _entry(plant, "", name, entry, report, f"modules.{name}")
    for index, item in enumerate(data.get("connections", [])):
        with report.guard(f"connections[{index}]"):
            _connection(plant, item, report)
    for side in ("inlets", "outlets"):
        for name, end in data.get(side, {}).items():
            with report.guard(f"{side}.{name}"):
                _port(plant, side, name, end, report)
    _check_ports(plant, data, report)
    if "outputs" in data:
        _outputs(plant, data["outputs"], report)
    for index, item in enumerate(data.get("constraints", [])):
        with report.guard(f"constraints[{index}]"):
            plant.constrain(**item)
    _root_values(plant, data.get("params", {}), report)
    from_sections(plant, data, report)
    set_sections(plant, data)


def _of_class(cls, data, report):
    """Return the plant of a class: ``data`` names it and holds its size and its values."""
    with report.guard("type"):
        found = cls if cls.__name__ == data["type"] else registry.get(data["type"])
        if found is not cls and registry.category(data["type"]) != "plants":
            raise ValidationError(
                f"type = {data['type']!r}; expected a plant class: wrap a module in a plant",
                code="invalid_value",
            )
        plant = built(found, data.get("size"))
        _root_values(plant, data.get("params", {}), report)
        from_sections(plant, data, report)
        set_sections(plant, data)
        return plant
    return None


def build(cls, data):
    """Return ``(plant or None, problems)`` of a plant dict; problems are empty when it is valid."""
    report = Report()
    error = format_error(data)
    if error is not None:
        report.items.append(located("", error))
        return None, report.items
    data = _shape(data, report)
    if "type" in data:
        plant = _of_class(cls, data, report)
    else:
        plant = cls._empty(data.get("name", "plant"))
        populate(plant, data, report)
    return plant, report.items


def set_sections(plant, data):
    """Keep a copy of the sections of ``data`` on ``plant``, which stores them as stated."""
    plant._sections = {key: deepcopy(data.get(key, {})) for key in SECTIONS}


KINDS = {
    "missing_value": "missing",
    "unknown_name": "unknown_key",
    "invalid_unit": "unit",
    "out_of_bounds": "out_of_bounds",
    "invalid_value": "incompatible",
    "invalid_data": "coverage",
}
MODULE_PARAMS = re.compile(r"modules\.(.+?)\.params(?:\.(.+))?")


def _file_path(path):
    """Return where a problem of the flat dict sits in the plant file."""
    found = MODULE_PARAMS.fullmatch(path)
    if found:
        key = found.group(1).replace(".modules.", ".")
        return ".".join(part for part in ("params", key, found.group(2)) if part)
    if path == "type.size":
        return "size"
    if path.startswith("params."):
        return join_path("params", form.file_path(path[len("params.") :]))
    return path


def issue_of(item):
    """Return the ``Issue`` of a problem ``{path, code, message, suggestions}``."""
    kind = KINDS.get(item["code"])
    return Issue(
        _file_path(item["path"]),
        kind or "incompatible",
        item["message"],
        suggestions=tuple(item["suggestions"]),
        code=None if kind else item["code"],
    )


def _skeleton(plant):
    modules = {path: type(m).__name__ for path, m in plant.named_modules() if path}
    connections = sorted((c["source"], c["target"], c.get("type")) for c in plant._connections)
    ports = {side: {k: str(v) for k, v in ends.items()} for side, ends in plant._listed.items()}
    return modules, connections, ports, plant._output_entries or {}


def _agree(cls, plant, structure, issues):
    """Append an issue when the stated modules and connections are not those of the class."""
    other, _ = build(cls, structure)
    if other is not None and _skeleton(other) != _skeleton(plant):
        form.issue(
            issues,
            "modules",
            "incompatible",
            f"modules and connections: they differ from those of {plant.name}; give the type or "
            "the structure, or make them agree",
        )


def _reported(path, marked):
    """Return whether an issue of a leaf already covers the flat problem at ``path``."""
    if path.startswith("param_history."):
        owner = join_path("params", path[len("param_history.") :]) + "."
        return any(item.startswith(owner) and ".history[" in item for item in marked)
    return any(item == path or item.startswith(path + ".") for item in marked)


def read(cls, data, ports=False):
    """Return ``(plant or None, issues)`` of a plant file; the issues are empty when it is valid.

    ``ports`` also reports the plant ports of a root plant, which has none.
    """
    issues = []
    parsed = form.parse(data, issues)
    if parsed is None:
        return None, issues
    plant, items = build(cls, parsed.flat)
    items = items + (root_problems(parsed.flat) if ports else [])
    found = []
    if plant is not None:
        leaves.apply(plant, parsed, found)
        if parsed.structure is not None:
            _agree(cls, plant, parsed.structure, found)
    marked = [item.path for item in found]
    kept = [item for item in map(issue_of, items) if not _reported(item.path, marked)]
    return plant, issues + kept + found


def tolerated(item):
    """Return whether an issue is a parameter or size a template leaves for ``size`` to compute."""
    return item.kind == "missing" and item.path.endswith(".value") and "history[" not in item.path


def from_dict(cls, data):
    """Return the plant of ``data``, or raise a ``ValidationError`` that carries every issue."""
    plant, issues = read(cls, data)
    raise_issues([item for item in issues if not tolerated(item)])
    return plant
