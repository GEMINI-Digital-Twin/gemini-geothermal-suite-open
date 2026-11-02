"""The variables of a search: every ``range`` and every ``options`` of the plant, tied by role."""

from dataclasses import dataclass

from gemini._utils.strings import join_path
from gemini.errors import ValidationError
from gemini.plants._utils import form
from gemini.plants.roles import roles_of

DOUBLETS = "size.doublets"
"""The path of the number of doublets, a structural size of the plant class."""


@dataclass(frozen=True)
class Variable:
    """One variable of a search.

    ``name`` is the path of the leaf, or ``<role>.<parameter>`` for leaves tied by their role;
    ``paths`` are the flat names of the parameters it sets (``d0.nominal_flow``). A continuous or
    integer variable has its SI ``low`` and ``high``; a choice has its ``options``.
    """

    name: str
    paths: tuple
    low: float | None = None
    high: float | None = None
    options: tuple | None = None
    integer: bool = False


def _split(flat):
    """Return ``(module path, parameter)`` of a flat name."""
    path, _, parameter = flat.rpartition(".")
    return path, parameter


def _owner(plant, flat):
    """Return ``(group, name)`` of the module owning a leaf: its roles, else its own path."""
    path, parameter = _split(flat)
    module = plant.get_submodule(path)
    roles = tuple(roles_of(plant, path, module))
    if not roles:
        return (path,), flat
    return roles, join_path(roles[0], parameter)


def _integer(plant, flat):
    """Return whether the parameter at ``flat`` is an integer."""
    schema = plant.get(flat).schema
    kinds = [schema.get("type"), *(item.get("type") for item in schema.get("anyOf", ()))]
    return "integer" in kinds


def _whole(path, spread):
    """Return the two ends of a range for a search, or raise when one side is open."""
    if spread.min is None or spread.max is None:
        raise ValidationError(
            f"{path}: range = {spread}; expected both min and max to search it",
            path=path,
            code="missing_value",
        )
    if not spread.min < spread.max:
        raise ValidationError(
            f"{path}: range min = {spread.min}, max = {spread.max}; expected min below max",
            path=path,
            code="invalid_value",
        )
    return float(spread.min), float(spread.max)


def variables(plant):
    """Return the variables of a search of ``plant`` in order, without the number of doublets.

    A variable is the leaves with the same parameter name, the same role (the plant itself is the
    role ``plant``; a module with no role is tied to nothing) and an equal range, or equal options.
    The order is the first appearance of a member in ``plant.ranges``, then ``plant.options``.
    """
    groups = {}
    for path, spread in plant.ranges.items():
        if path == DOUBLETS:
            continue
        flat = form.flat_name(path)
        owner, name = _owner(plant, flat)
        key = (_split(flat)[1], owner, _whole(path, spread), None)
        groups.setdefault(key, (path, name, []))[2].append(flat)
    for path, options in plant.options.items():
        flat = form.flat_name(path)
        owner, name = _owner(plant, flat)
        key = (_split(flat)[1], owner, None, tuple(options))
        groups.setdefault(key, (path, name, []))[2].append(flat)
    return [_variable(plant, key, *group) for key, group in groups.items()]


def _variable(plant, key, path, name, members):
    """Return the ``Variable`` of a group of leaves that are tied."""
    _, _, ends, options = key
    shown = path if len(members) == 1 else name
    if options is not None:
        return Variable(shown, tuple(members), options=options)
    return Variable(shown, tuple(members), *ends, integer=_integer(plant, members[0]))


def counts(plant):
    """Return the numbers of doublets to search, every integer of the range, or ``[None]``.

    ``[None]`` is the plant as it is, when its file states no range for ``size.doublets``.
    """
    spread = plant.ranges.get(DOUBLETS)
    if spread is None:
        return [None]
    return list(range(int(spread.min), int(spread.max) + 1))


def searchable(plant):
    """Return whether the plant states anything to search: a doublet range, a range or options."""
    return counts(plant) != [None] or bool(variables(plant))
