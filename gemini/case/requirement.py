"""One rule of a third party on the outcome: a quantity of a role, with its band."""

import dataclasses
import math
import re

from gemini import units
from gemini._utils.strings import close_matches, join_names
from gemini.case._utils.node import Frozen, issue, plain, refuse_replaced
from gemini.errors.base import raise_issues
from gemini.plants.roles import TABLE, dimension
from gemini.units import inputs

KEYS = ("name", "on", "quantity", "unit", "over", "when", "min", "max")
OVERS = ("each", "sum", "mean", "max", "min", "duration")
WHENS = ("always", "running")
NAME = re.compile(r"^[a-z][a-z0-9_]*$")


class Requirement(Frozen):
    """A rule on a quantity of a role; it applies to every unit of the role on its own.

    ``on`` and ``quantity`` come from ``gm.plants.roles()``. A per-step quantity states ``over``:
    ``each`` (every step), ``sum``, ``mean``, ``max`` or ``min`` (one figure of the run) or
    ``duration`` (the total time of the steps where ``when`` holds, with bounds that are durations),
    and may state ``when``: ``always`` or ``running``, the steps where the unit carries flow, and
    every step when absent. A window quantity or a property takes neither. ``unit`` is present if
    and only if the bounds have a dimension, and ``min`` and ``max`` are numbers in it; an exact
    rule is ``min`` = ``max``.

    Attributes
    ----------
    name : str
        Unique, snake_case.
    on, quantity : str
        The role and its quantity.
    over, when : str or None
        How the run is read, and which steps count.
    min, max : float or None
        The bounds, SI.
    """

    def __init__(self, given, **values):
        """Build from what ``read`` found; use ``Case.from_dict`` to build from data."""
        self._set(_given=given, **values)

    @property
    def dimension(self):
        """The quantity of the bounds: a duration over ``duration``, else the role's quantity."""
        if self.over == "duration":
            return "duration"
        return dimension(TABLE[self.on][self.quantity].dimension)

    def to_dict(self):
        """Return the requirement as it was read."""
        return dict(self._given)

    def __eq__(self, other):
        """Equal when written alike."""
        if not isinstance(other, Requirement):
            return NotImplemented
        return self._given == other._given

    __hash__ = None

    @classmethod
    def from_dict(cls, data):
        """Return the requirement of ``data``; raises ``ValidationError`` carrying every issue."""
        issues = []
        found = cls.read(plain(data), "requirement", issues)
        raise_issues(issues)
        return found

    @classmethod
    def read(cls, data, path, issues):
        """Return the requirement of ``data`` or ``None`` with issues appended."""
        if not isinstance(data, dict):
            issue(issues, path, "incompatible", f"{path} = {data!r}; expected an object")
            return None
        before = len(issues)
        refuse_replaced({"equals": '"min" and "max" with the same number'}, data, path, issues)
        inputs.check_keys({k: v for k, v in data.items() if k != "equals"}, KEYS, path, issues)
        name = _name(data.get("name"), path, issues)
        reads = _reads(data, path, issues)
        over = _over(data, reads, path, issues) if reads else None
        when = _when(data, reads, path, issues) if reads else None
        bounds = _bounds(data, reads, over, path, issues) if reads else None
        if len(issues) > before:
            return None
        return cls(
            {key: data[key] for key in KEYS if key in data},
            name=name,
            on=data["on"],
            quantity=data["quantity"],
            over=over,
            when=when,
            min=bounds[0],
            max=bounds[1],
        )


def _name(name, path, issues):
    """Return the name, or ``None`` with an issue unless it is snake_case text."""
    if not isinstance(name, str) or not NAME.match(name):
        issue(
            issues,
            f"{path}.name",
            "missing" if name is None else "incompatible",
            f"{path}.name = {name!r}; expected a snake_case name",
        )
        return None
    return name


def _reads(data, path, issues):
    """Return the ``Reads`` of ``on`` and ``quantity``, or ``None`` with issues."""
    role, quantity = data.get("on"), data.get("quantity")
    if role not in TABLE:
        _closed(issues, f"{path}.on", role, "role", TABLE)
        return None
    if quantity not in TABLE[role]:
        _closed(issues, f"{path}.quantity", quantity, f"quantity of {role}", TABLE[role])
        return None
    return TABLE[role][quantity]


def _closed(issues, path, value, what, table):
    """Append the ``not_allowed`` issue of a name that is no key of ``table``."""
    near = tuple(close_matches(str(value), list(table)))
    hint = f"; did you mean {near[0]!r}?" if near else ""
    issue(
        issues,
        path,
        "missing" if value is None else "not_allowed",
        f"{path} = {value!r} is no {what}; expected one of {join_names(list(table))}{hint}",
        accepted=tuple(table),
        suggestions=near,
    )


def _over(data, reads, path, issues):
    """Return ``over``: required for a per-step quantity, refused for the others."""
    over = data.get("over")
    if not reads.over:
        if "over" in data:
            issue(
                issues,
                f"{path}.over",
                "incompatible",
                f"{path}.over: {data['quantity']} is read over the whole period; expected no over",
            )
        return None
    if over is None:
        issue(
            issues,
            f"{path}.over",
            "missing",
            f"{path}.over is missing; expected one of {join_names(OVERS)}",
        )
    elif over not in OVERS:
        _closed(issues, f"{path}.over", over, "over", OVERS)
        return None
    return over


def _when(data, reads, path, issues):
    """Return ``when`` (``None`` for every step), refused for a quantity read over the period."""
    when = data.get("when")
    if when is None and "when" not in data:
        return None
    if not reads.over:
        issue(
            issues,
            f"{path}.when",
            "incompatible",
            f"{path}.when: {data['quantity']} is read over the whole period; expected no when",
        )
    elif when not in WHENS:
        _closed(issues, f"{path}.when", when, "when", WHENS)
    return when


def _bounds(data, reads, over, path, issues):
    """Return ``(min, max)`` in SI, or ``None`` with issues."""
    before = len(issues)
    given = {side: data[side] for side in ("min", "max") if side in data}
    for side, number in given.items():
        if not _is_number(number):
            issue(
                issues,
                f"{path}.{side}",
                "incompatible",
                f"{path}.{side} = {number!r}; expected a number",
            )
    if not given:
        issue(issues, path, "missing", f"{path}: min or max is missing; expected one of them")
    if len(issues) > before:
        return None
    name = "duration" if over == "duration" else reads.dimension
    quantity = dimension(name)
    return _in_si(data, given, quantity, path, issues)


def _in_si(data, given, quantity, path, issues):
    """Return ``(min, max)`` in SI, the unit and the order checked by the shared leaf reader."""
    first = next(iter(given.values()))
    probe = {"value": first, "range": dict(given)}
    if "unit" in data:
        probe["unit"] = data["unit"]
    scratch = []
    leaf = inputs.from_leaf(probe, path, scratch, quantity=quantity)
    for found in scratch:
        issues.append(_renamed(found))
    if leaf is None:
        return None
    return tuple(None if side not in given else _si(given[side], leaf) for side in ("min", "max"))


def _renamed(found):
    """Return the issue with the path and message of the requirement, not of its probe leaf."""
    path = found.path.removesuffix(".value").replace(".range", "")
    return dataclasses.replace(found, path=path, message=found.message.replace(".range", ""))


def _si(number, leaf):
    """Return ``number``, given in the unit of ``leaf``, in SI."""
    return number if leaf.unit is None else units.to_si(number, leaf.unit, leaf.quantity)


def _is_number(value):
    """Whether ``value`` is a finite number that is no boolean."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
