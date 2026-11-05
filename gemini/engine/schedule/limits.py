"""The requirements a schedule enforces, found by their role and quantity.

A requirement of the case applies to every unit of its role on its own. The schedule reads three
forms of the role ``doublet``:

- flow range: ``production_flow``, ``over="each"``, ``when="running"``, ``min`` and ``max``,
  in one requirement or over several: the range is the largest ``min`` and the smallest ``max``
  of them all, so a minimum and a maximum stated as two rules make one range;
- maximum brine cooling: ``brine_cooling``, ``over="each"``, ``max``, the smallest of them all;
- operating duration: ``production_flow``, ``over="duration"``, ``when="running"``, ``max``.

Every other requirement, a duration with only ``min``, and a bound of a requirement that the form
does not read are left to the check of a run.
"""

from dataclasses import dataclass

import pandas as pd

from gemini._utils.strings import join_path
from gemini._utils.time import to_timedelta
from gemini.errors import ValidationError

BOUNDS = ("min", "max")
"""The bounds of a requirement."""
ROLE = "doublet"
"""The role whose units the schedule limits."""
FLOW = "production_flow"
"""The quantity of the flow of a doublet."""
COOLING = "brine_cooling"
"""The quantity of the cooling of its brine."""


@dataclass(frozen=True)
class DoubletLimits:
    """The limits of one doublet in SI: flows [m3/s], cooling [K] and the running time or None."""

    minimum_flow: float
    maximum_flow: float
    brine_cooling: float
    operating_time: pd.Timedelta | None


def _forms(requirement):
    """Return the forms ``requirement`` has."""
    if requirement.on != ROLE:
        return []
    forms = []
    flow = requirement.quantity == FLOW
    if flow and requirement.over == "each" and requirement.when == "running":
        if requirement.min is not None:
            forms.append("flow_min")
        if requirement.max is not None:
            forms.append("flow_max")
    if requirement.quantity == COOLING and requirement.over == "each":
        if requirement.max is not None:
            forms.append("cooling")
    if flow and requirement.over == "duration" and requirement.when == "running":
        if requirement.max is not None:
            forms.append("duration")
    return forms


def _duration(requirement):
    """Return the duration of a duration requirement as a ``Timedelta``."""
    bound = requirement.max
    try:
        return to_timedelta(bound)
    except ValueError as error:
        raise ValidationError(
            f"schedule: requirement {requirement.name} on {requirement.on} "
            f"{requirement.quantity} duration = {bound}; expected a duration",
            path="requirements",
            code="invalid_value",
        ) from error


def _missing(doublet, name, form):
    """Return the ``missing_value`` error of a limit that no requirement gives for ``doublet``."""
    return ValidationError(
        f"schedule: no requirement on {ROLE} gives {form} of {join_path(doublet, name)}; "
        "expected one, a limit has no default",
        path="requirements",
        code="missing_value",
    )


ENFORCED = {"flow_min": ("min",), "flow_max": ("max",), "cooling": ("max",), "duration": ("max",)}
"""The bounds of a requirement a schedule enforces in each form."""


def _left_over(requirement, enforced):
    """Return ``to_dict()`` of ``requirement`` less ``enforced``; ``None`` if no bound is left."""
    rest = {key: value for key, value in requirement.to_dict().items() if key not in enforced}
    if all(name not in rest for name in BOUNDS):
        return None
    return rest


TIGHTEST = {"flow_min": max, "flow_max": min, "cooling": min}
"""How the bounds of several requirements of one form combine: the tightest wins (QA-080)."""


def _found(requirements):
    """Return ``{form: [(index, requirement), ...]}``: every requirement of the flow and cooling
    forms, and the first of a duration."""
    found = {}
    for index, requirement in enumerate(requirements):
        for form in _forms(requirement):
            if form == "duration" and form in found:
                continue
            found.setdefault(form, []).append((index, requirement))
    return found


def _bound(found, form):
    """Return the tightest bound of ``form`` over its requirements."""
    side = ENFORCED[form][0]
    return TIGHTEST[form](getattr(requirement, side) for _, requirement in found[form])


def of_doublet(found, doublet):
    """Return ``(DoubletLimits, used)`` of the doublet at path ``doublet``.

    ``used`` maps the index of each requirement that gave a limit to the bounds the schedule
    enforces of it. A flow range or a brine cooling that no requirement gives raises
    ``ValidationError`` (code ``missing_value``).
    """
    if "flow_min" not in found or "flow_max" not in found:
        raise _missing(
            doublet,
            FLOW,
            "a flow range (over='each', when='running', min and max, in one requirement or two)",
        )
    if "cooling" not in found:
        raise _missing(doublet, COOLING, "a maximum (over='each', max)")
    minimum, maximum = _bound(found, "flow_min"), _bound(found, "flow_max")
    if minimum > maximum:
        names = ", ".join(item.name for form in ("flow_min", "flow_max") for _, item in found[form])
        raise ValidationError(
            f"schedule: the flow range of {join_path(doublet, FLOW)} is empty: the largest min "
            f"({minimum} m3/s) is above the smallest max ({maximum} m3/s) of {names}",
            path="requirements",
            code="invalid_value",
        )
    duration = found.get("duration")
    limits = DoubletLimits(
        minimum,
        maximum,
        _bound(found, "cooling"),
        None if duration is None else _duration(duration[0][1]),
    )
    used = {}
    for form, items in found.items():
        for index, _ in items:
            used[index] = tuple(sorted({*used.get(index, ()), *ENFORCED[form]}))
    return limits, used


def split(requirements, doublets):
    """Return ``({doublet: DoubletLimits}, check_only)`` for the doublet paths ``doublets``.

    ``check_only`` lists the ``to_dict()`` of every requirement the schedule did not enforce, and of
    one it enforced in part with only the bounds left: a duration of ``min`` and ``max`` runs to
    the maximum, so its entry keeps the minimum.
    """
    requirements = requirements or ()
    found = _found(requirements)
    limits, used = {}, {}
    for doublet in doublets:
        limits[doublet], taken = of_doublet(found, doublet)
        used |= taken
    left = [_left_over(item, used.get(index, ())) for index, item in enumerate(requirements)]
    return limits, [item for item in left if item is not None]
