"""The requirements of a case, checked against a finished run."""

import numpy as np

from gemini._utils.strings import join_path
from gemini.case import Requirement
from gemini.case._utils.node import si_unit_of
from gemini.case.roletable import reads
from gemini.evaluate._utils.co2_steps import emitted_steps
from gemini.evaluate._utils.columns import (
    field_of,
    fields,
    is_parameter,
    parameter_values,
    series,
)
from gemini.evaluate._utils.series import edge_power
from gemini.plants._utils.roles import delivery_ports, units_of
from gemini.run._utils.apply import apply_case
from gemini.types.shapes import check, measure

TOLERANCE = 1e-9
"""Relative margin of a limit: a value on the limit passes through its rounding; numerical."""

AGGREGATES = {"sum": np.sum, "mean": np.mean, "max": np.max, "min": np.min}
"""How a requirement with ``over`` other than ``each`` and ``duration`` reads the run."""

NO_VALUE = "no_value: the run gives no value of this field"
"""The reason when the field is not among the results."""

NO_FLOW = "the module carried no flow in this run"
"""The reason when ``when="running"`` leaves no step."""

DEMANDED = {"unmet_demand": "heating_demand", "unmet_sensible": "cooling_demand"}
"""The column of ``case.demand.frame`` holding the demand, for each unmet output of a consumer."""


def requirements(plant, case, results):
    """Check every requirement of ``case`` and the supply temperatures of its services.

    A ``Requirement`` is on a role and a quantity of it (``gm.case.roles()``); it applies to every
    unit of the role in ``plant`` on its own, the units being found by class and wiring. A result
    field is read over the run, a composite's through the leaves its formula names; with
    ``when="running"`` only the steps in which the module carried flow count, without ``when``
    every step counts. ``over`` gives how the run is read: ``each`` judges every step and reports
    the worst; ``sum``, ``mean``, ``max``
    and ``min`` judge one figure of the run; ``duration`` judges the total time of the steps
    that count. A parameter is judged once, or at each date inside the run when it changes over
    time, with the case applied to the plant. ``count`` of ``doublet`` is the number of doublets
    of the plant and ``unmet_share`` of a supply the unmet energy over the energy its service
    demanded in the run, each one figure of the period. ``reinjection_ratio`` is the injected over
    the produced liquid volume flow of the doublet. A value on a limit passes within
    ``TOLERANCE``, a
    duration within half a step.

    The service requirement is checked as well: each ``HeatingGrid`` must receive water at least at
    ``demand.heating.supply_temperature`` and each ``CoolingGrid`` at most at
    ``demand.cooling.supply_temperature``, in the steps in which it runs. A service without a
    supply temperature adds no check. A role with no unit in the plant gives one check with
    ``passed`` ``None`` and ``unit_path`` ``None``, whose value says ``no_value``.

    Parameters
    ----------
    plant : Module
        The plant of the run.
    case : Case
        The case whose requirements and services are checked, and that gives design values.
    results : Results
        A finished run.

    Returns
    -------
    list of dict
        One check ``{name, role, unit_path, quantity, passed, value, limit, worst_step}`` per unit
        and requirement: ``name`` is that of the requirement, ``role`` and ``quantity`` those of
        it, ``unit_path`` the path of the unit (``""`` for the plant, and for the role
        ``plant``, whose figures are named by the quantity alone). ``value`` is a
        ``Quantity`` (SI, ``s`` for ``duration``): the worst value of the run for ``each`` and the
        figure otherwise, and ``limit`` the bound that was violated, else the nearest.
        ``worst_step`` is the ISO 8601 time of the worst step, ``None`` for a figure of the run and
        for a parameter. ``passed`` is ``None``, with the reason in ``value``, for a unit that
        carried no flow, and with ``no_value`` for a field the run does not hold.

    Raises
    ------
    ValidationError
        With code ``unknown_name`` for a role quantity that a unit of the plant does not hold.
    """
    frame = results.to_frame()
    sited = apply_case(plant, case)
    checks = []
    for requirement in (*(case.requirements or ()), *_services(case)):
        checks += _checks(sited, case, results, frame, requirement)
    return checks


def _checks(plant, case, results, frame, requirement):
    """Return the checks of one requirement: one per unit of its role, or one for a count."""
    found = units_of(plant, requirement.on)
    if reads(requirement.on, requirement.quantity).source == "count":
        return [_count(requirement, len(found))]
    if not found:
        return [_no_unit(requirement)]
    return [_check(plant, case, results, frame, requirement, path) for path in found]


def _unit_of(requirement):
    """Return the SI unit of the figure a requirement judges."""
    if requirement.over == "duration":
        return "s"
    return "-" if requirement.dimension is None else si_unit_of(requirement.dimension)


def _no_unit(requirement):
    """Return the undecided check of a requirement whose role has no unit in the plant."""
    reason = f"no_value: the plant has no unit of the role {requirement.on!r}"
    return _undecided(requirement, None, reason, _unit_of(requirement))


def _count(requirement, number):
    """Return the check of the number of units of the role of ``requirement``."""
    return _judged(requirement, "", None, float(number), 0.0, "-")


def _judged(requirement, unit_path, step, measured, margin, unit):
    """Return the check of one figure against the bounds of ``requirement``."""
    lower, upper = _bounds(requirement)
    passed = (lower is None or measured >= lower - margin) and (
        upper is None or measured <= upper + margin
    )
    limit = measure(_nearest(measured, lower, upper), unit)
    verdict = check(requirement.name, bool(passed), measure(measured, unit), limit)
    return verdict | _where(requirement, unit_path, step)


def _services(case):
    """Return the requirements that the supply temperatures of the services of ``case`` make."""
    demand = case.demand
    if demand is None:
        return []
    required = [
        (demand.heating, "heating_supply", "min"),
        (demand.cooling, "cooling_supply", "max"),
    ]
    return [
        Requirement.from_dict(
            {
                "name": f"{role}_temperature",
                "on": role,
                "quantity": "temperature",
                "unit": "K",
                "over": "each",
                "when": "running",
                bound: service.supply_temperature,
            }
        )
        for service, role, bound in required
        if service is not None and service.supply_temperature is not None
    ]


def _bounds(requirement):
    """Return ``(lower, upper)`` of a requirement."""
    return requirement.min, requirement.max


def _over(requirement):
    """Return how the run is read: a property or a window quantity is judged once, as ``each``."""
    return requirement.over or "each"


def _reading(plant, frame, requirement, path, name):
    """Return ``(values, keep)`` of a field: its values and the steps that count."""
    if is_parameter(plant, path, name):
        values = parameter_values(plant, frame, path, name)
        return values, np.isfinite(values)
    values, active = series(plant, frame, path, name)
    keep = np.isfinite(values)
    return values, keep & active if requirement.when == "running" else keep


def _worst_index(values, lower, upper):
    """Return the position of the value furthest out, or nearest the limit inside."""
    if upper is None:
        return int(values.argmin())
    if lower is None:
        return int(values.argmax())
    low, high = int(values.argmin()), int(values.argmax())
    return low if lower - values[low] > values[high] - upper else high


def _measure(requirement, values, keep, durations, bounds):
    """Return ``(measured, margin, position)``; ``position`` is the worst step of ``each``."""
    over = _over(requirement)
    if over == "duration":
        return float(durations[keep].sum()), float(np.median(durations)) / 2, None
    judged = values[keep]
    if over == "each":
        worst = _worst_index(judged, *bounds)
        return float(judged[worst]), TOLERANCE * abs(judged[worst]), int(keep.nonzero()[0][worst])
    measured = float(AGGREGATES[over](judged))
    return measured, TOLERANCE * abs(measured), None


def _nearest(measured, lower, upper):
    """Return the bound that was violated, else the one nearest to ``measured``."""
    if lower is None or upper is None:
        return upper if lower is None else lower
    if measured < lower or measured > upper:
        return lower if measured < lower else upper
    return lower if measured - lower <= upper - measured else upper


def _no_reason(values, keep, over):
    """Return why nothing can be judged, or ``None``."""
    if not values.size or np.isnan(values).all():
        return NO_VALUE
    if over != "duration" and not keep.any():
        return NO_FLOW
    return None


def _leaf_flags(plant, frame):
    """Return, per step, whether any leaf of the plant carried flow."""
    columns = [
        join_path(path, "operating")
        for path, module in plant.named_modules()
        if module.is_leaf and join_path(path, "operating") in frame
    ]
    if not columns:
        return np.zeros(len(frame), dtype=bool)
    return frame[columns].to_numpy(dtype=bool).any(axis=1)


def _plant_values(plant, case, results, frame, name):
    """Return ``(values, active, unit)`` of a figure of the plant as a whole."""
    if name == "co2":
        return emitted_steps(plant, case, results), _leaf_flags(plant, frame), "kg"
    found = edge_power(plant, frame, name)
    if found is None:
        return np.empty(0), np.empty(0, dtype=bool), "W"
    return found.to_numpy(dtype=float), _leaf_flags(plant, frame), "W"


def _delivery_values(plant, frame, requirement, path):
    """Return ``(values, active)`` of the power a unit delivers: its two ports less one another."""
    ports = delivery_ports(plant.get_submodule(path), requirement.on)
    first, second = (f"{port}.enthalpy_flow" for port in ports)
    one, active = series(plant, frame, path, first)
    other, _ = series(plant, frame, path, second)
    if not one.size or not other.size:
        return np.empty(0), np.empty(0, dtype=bool)
    return one - other, active


def _values(plant, case, results, frame, requirement, unit_path):
    """Return ``(values, keep, unit, label, timed)`` of what a requirement reads on one unit."""
    read = reads(requirement.on, requirement.quantity)
    label = join_path(unit_path, read.path)
    if read.source == "plant":
        values, active, unit = _plant_values(plant, case, results, frame, read.path)
        keep = np.isfinite(values) & (active if requirement.when == "running" else True)
        return values, keep, unit, label, True
    if read.source == "delivery":
        values, active = _delivery_values(plant, frame, requirement, unit_path)
        keep = np.isfinite(values) & (active if requirement.when == "running" else True)
        return values, keep, si_unit_of("power"), label, True
    path, name = field_of(plant, label)
    values, keep = _reading(plant, frame, requirement, path, name)
    return (
        values,
        keep,
        fields(plant, path)[name][0],
        join_path(path, name),
        not is_parameter(plant, path, name),
    )


def _share(plant, case, results, frame, requirement, unit_path):
    """Return the check of the unmet energy over the demand of the case for one supply unit.

    A service that demands nothing has nothing unmet: its share is 0.
    """
    read = reads(requirement.on, requirement.quantity)
    unmet, _ = series(plant, frame, unit_path, read.path)
    if not unmet.size:
        return _undecided(requirement, unit_path, NO_VALUE, "-")
    column = DEMANDED[read.path]
    demand = case.demand.frame[column].to_numpy(dtype=float)
    wanted = float((demand * results.durations).sum())
    spent = float((unmet * results.durations).sum())
    measured = spent / wanted if wanted > 0 else 0.0
    return _judged(requirement, unit_path, None, measured, TOLERANCE * abs(measured), "-")


def _undecided(requirement, unit_path, reason, unit):
    """Return the check of a figure that cannot be judged, with the ``reason``."""
    lower, upper = _bounds(requirement)
    limit = measure(lower if lower is not None else upper, unit)
    verdict = check(requirement.name, None, measure(None, unit, reason), limit)
    return verdict | _where(requirement, unit_path, None)


def _check(plant, case, results, frame, requirement, unit_path):
    """Return the check of one requirement on one unit of its role."""
    if reads(requirement.on, requirement.quantity).source == "share":
        return _share(plant, case, results, frame, requirement, unit_path)
    values, keep, unit, _, timed = _values(plant, case, results, frame, requirement, unit_path)
    unit = "s" if requirement.over == "duration" else unit
    bounds = _bounds(requirement)
    reason = _no_reason(values, keep, _over(requirement))
    if reason:
        return _undecided(requirement, unit_path, reason, unit)
    measured, margin, position = _measure(requirement, values, keep, results.durations, bounds)
    step = None if position is None or not timed else frame.index[position]
    return _judged(requirement, unit_path, step, measured, margin, unit)


def _where(requirement, unit_path, step):
    """Return the keys of a check: its role, unit and quantity, and the time of the worst step."""
    return {
        "role": requirement.on,
        "unit_path": unit_path,
        "quantity": requirement.quantity,
        "worst_step": None if step is None else step.isoformat(),
    }
