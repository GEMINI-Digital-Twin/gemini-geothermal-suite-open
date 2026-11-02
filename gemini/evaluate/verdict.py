"""Whether a finished run is acceptable: bounds, requirements, failed rows and the one verdict."""

from collections import Counter
from dataclasses import dataclass

import numpy as np
import pandas as pd

from gemini._utils.jsonable import to_plain
from gemini._utils.strings import join_path
from gemini.case import Requirement
from gemini.case._utils.node import si_unit_of
from gemini.engine.apply import apply_case
from gemini.errors.rows import SKIPPED
from gemini.evaluate._utils.co2_steps import emitted_steps
from gemini.evaluate._utils.columns import field_of, fields, is_parameter, parameter_values, series
from gemini.evaluate._utils.operating import breaches
from gemini.evaluate._utils.series import burned_gas, edge_power
from gemini.evaluate._utils.tally import tally
from gemini.evaluate.balances import energy_balance, mass_balance, plant_balance
from gemini.evaluate.summary import totals
from gemini.modules.declarations import Output
from gemini.plants.roles import delivery_ports, reads, units_of
from gemini.units.quantities import Temperature
from gemini.units.shapes import check, measure

_OUTSIDE = {
    "ge": np.less,
    "gt": np.less_equal,
    "le": np.greater,
    "lt": np.greater_equal,
}
"""For each limit of ``Declaration.limits``, the comparison that a violating value satisfies."""


_TEMPERATURE = Output(Temperature)
"""The declaration whose limits judge the temperature of a port."""


def _outside(values, limits):
    """Return how many values violate any of the ``limits``; a missing value never does."""
    array = values.to_numpy(dtype=float)
    violated = np.zeros(array.shape, dtype=bool)
    for key, limit in limits.items():
        violated |= _OUTSIDE[key](array, limit)
    return int(violated.sum())


def _limits(outputs, field):
    """Return the limits of a column: an output's, or those of a port's absolute temperature."""
    if field in outputs:
        return outputs[field].limits()
    return _TEMPERATURE.limits() if field.endswith(".temperature") else {}


def bounds(plant, case, results):
    """Check that every recorded output is inside the limits its module declares.

    The limits are those of the output's declaration (``ge``, ``gt``, ``le``, ``lt`` from its
    quantity and its bounds, see ``Declaration.limits``), read from the module at the
    column's path. Boolean and text columns, outputs without a limit and the health columns are
    not judged.

    Parameters
    ----------
    plant : Module
        The plant that produced ``results``; a path of the results it lacks raises
        ``ValidationError``.
    case : Case
        The case of the run; the check does not read it.
    results : Results
        A finished run.

    Returns
    -------
    dict
        ``{name: "bounds", passed, value, limit}``: ``value`` is the number of values outside
        their limits, over all columns and ticks, and ``limit`` is 0. ``passed`` is ``None``,
        with a ``reason`` in ``value``, when no recorded output has a limit.
    """
    frame = results.to_frame()
    judged, violations = 0, 0
    for path, names in results.names().items():
        outputs = plant.get_submodule(path).outputs(recurse=False)
        for field in names:
            column = frame[join_path(path, field)]
            limits = _limits(outputs, field)
            if limits and pd.api.types.is_numeric_dtype(column) and column.dtype != bool:
                judged += 1
                violations += _outside(column, limits)
    limit = measure(0, "-")
    if not judged:
        reason = "no recorded output has a declared limit"
        return check("bounds", None, measure(None, "-", reason), limit)
    return check("bounds", violations == 0, measure(violations, "-"), limit)


FIELDS = ("path", "code", "kind", "count", "first", "last", "message")
"""The columns of ``Failures.to_frame``, one row per group."""


@dataclass(frozen=True)
class Failures:
    """The groups of failed and skipped rows of a run, the most frequent first.

    Each group is ``{path, code, kind, count, first, last, message}``: the module path, the code of
    ``gm.errors.ROW_CODES``, ``"skipped"`` or ``"failed"``, the number of rows, the time of the
    first and the last row, and the message of the first row. A run with no failed or skipped row
    has no group.
    """

    groups: tuple

    def __len__(self):
        """Count the groups."""
        return len(self.groups)

    @property
    def total(self):
        """The number of failed and skipped rows."""
        return sum(group["count"] for group in self.groups)

    def to_dict(self):
        """Return ``{total, groups}`` as plain JSON."""
        return {"total": self.total, "groups": [dict(group) for group in self.groups]}

    def to_frame(self):
        """Return the groups as a table with the columns ``FIELDS``, in the same order."""
        return pd.DataFrame(list(self.groups), columns=list(FIELDS))


def failures(results):
    """Group the failed and skipped rows of ``results`` by module path and error code.

    ``results`` is the ``Results`` of a run. Rows come from ``results.errors()``, which are in
    time order. The groups are sorted by count, largest first, then by path and code.
    """
    found = {}
    for row in results.errors():
        key = (row["path"], row["code"])
        group = found.get(key)
        if group is None:
            kind = "skipped" if row["code"] == SKIPPED else "failed"
            found[key] = {
                "path": row["path"],
                "code": row["code"],
                "kind": kind,
                "count": 1,
                "first": row["time"],
                "last": row["time"],
                "message": row["message"],
            }
        else:
            group["count"] += 1
            group["last"] = row["time"]
    ordered = sorted(
        found.values(), key=lambda group: (-group["count"], group["path"], group["code"])
    )
    return Failures(tuple(ordered))


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

    A ``Requirement`` is on a role and a quantity of it (``gm.plants.roles()``); it applies to every
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
    lower, upper = _requirement_limits(requirement)
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


def _requirement_limits(requirement):
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
    unit = "kg/s" if name == "gas_burned" else "W"
    found = burned_gas(plant, frame) if name == "gas_burned" else edge_power(plant, frame, name)
    if found is None:
        return np.empty(0), np.empty(0, dtype=bool), unit
    return found.to_numpy(dtype=float), _leaf_flags(plant, frame), unit


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
    lower, upper = _requirement_limits(requirement)
    limit = measure(lower if lower is not None else upper, unit)
    verdict = check(requirement.name, None, measure(None, unit, reason), limit)
    return verdict | _where(requirement, unit_path, None)


def _check(plant, case, results, frame, requirement, unit_path):
    """Return the check of one requirement on one unit of its role."""
    if reads(requirement.on, requirement.quantity).source == "share":
        return _share(plant, case, results, frame, requirement, unit_path)
    values, keep, unit, _, timed = _values(plant, case, results, frame, requirement, unit_path)
    unit = "s" if requirement.over == "duration" else unit
    bounds = _requirement_limits(requirement)
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


SERVICES = {"heating": "heat_delivered", "cooling": "cold_delivered"}
"""The figure that shows a service of the case being delivered."""

LARGEST_VIOLATION = 1e6
"""The violation of a failed step: above that of any design that ran."""

NOT_CONVERGED = "loop_not_converged"
"""The code of a failed row that is a numerical failure: an iteration that did not converge."""


class Verdict(dict):
    """The verdict of a run: ``feasible`` and the ``reasons`` it is not, with ``to_dict``."""

    def to_dict(self):
        """Return ``{feasible, reasons}`` as plain JSON, every ``Quantity`` as ``{value, unit}``."""
        return to_plain(dict(self))


def verdict(plant, case, results):
    """Return whether a finished run is feasible, and why not.

    The one place that decides feasibility; ``report``, ``compare`` and the study use it. A run is
    feasible when it has no reason. A reason has a ``kind``:

    - ``requirement``: a requirement of the case, or a supply temperature of a service, that
      failed (``requirements``); no requirement could be checked; when some passed and none
      failed, each one that could not be judged (without a ``violation``), except an idle unit
      and the supply of a service reported as not delivered; a service of the case that the run
      does not deliver.
    - ``failed_step``: rows of the run that failed or were skipped.
    - ``numerical``: a mass or energy residual above the tolerances of ``mass_balance``,
      ``energy_balance`` and ``plant_balance``, or a loop that did not converge.
    - ``bound``: a recorded output outside the limits its module declares (``bounds``), or an
      output past an operating limit of a module (``Module.operating_limits``) in the steps in
      which the module carried flow.

    The case is applied to the plant once; the plant of the user never changes.

    Parameters
    ----------
    plant : Module
        The plant of the run.
    case : Case
        The case of the run.
    results : Results
        A finished run.

    Returns
    -------
    Verdict
        A dict ``{feasible, reasons}`` (``to_dict()`` gives plain JSON). A reason is ``{kind,
        name, message}`` and, when it has them, ``path`` (the module or the output), ``value``,
        ``limit`` (values) and ``worst_step`` (ISO 8601). A ``requirement`` reason of a check also
        has its ``role`` and ``quantity``.
    """
    sited = apply_case(plant, case)
    checks = requirements(sited, case, results)
    return judged(sited, case, results, checks, totals(sited, case, results))


def judged(plant, case, results, checks, edge):
    """Return the ``Verdict`` of a run whose ``checks`` and ``edge`` totals are already read.

    ``plant`` carries the case (``apply_case``); ``report`` calls this with what it read, so that
    no figure is computed twice.
    """
    rows = results.errors()
    found = [
        *_requirement_reasons(case, checks, edge),
        *_failed_rows(rows),
        *_balances(plant, case, results, rows),
        *_bounds(plant, case, results),
    ]
    found = _distinct(found)
    return Verdict(feasible=not found, reasons=found)


def _distinct(found):
    """Return the reasons with one for each name, the first; a missing service says it once."""
    names = {}
    for item in found:
        names.setdefault(item["name"], item)
    return list(names.values())


def ranked(found):
    """Return the reasons of a verdict that a design variable can change: those with a violation.

    A search ranks a trial by the ``violation`` of these (their sum, at most
    ``LARGEST_VIOLATION``). A reason without one is structural, such as a service the plant has no
    unit for, and stays in the verdict of the run without ranking the trials of a search.
    """
    return [item for item in found["reasons"] if "violation" in item]


def excess(value, limit):
    """Return how far ``value`` is from ``limit``, relative to the larger of the two.

    A value the run could not give (NaN: its steps failed) is the largest violation.
    """
    if np.isnan(value.value) or np.isnan(limit.value):
        return LARGEST_VIOLATION
    return abs(value.value - limit.value) / (max(abs(value.value), abs(limit.value)) or 1.0)


def reason(kind, name, message, **parts):
    """Return one reason: ``kind``, ``name`` and ``message``, then the parts that are given.

    ``violation`` is the relative size of the breach for a reason a design can change, absent for
    a structural one.
    """
    return {"kind": kind, "name": name, "message": message} | {
        key: item for key, item in parts.items() if item is not None
    }


def _text(item):
    """Return a value as text for a message: its number and unit."""
    if item.value is None:
        return "no value"
    return f"{item.value:.6g} {item.unit}"


def _requirement_reasons(case, checks, edge):
    """Return the requirement reasons: failed or undecided checks, none checked, a missing service.

    A check that could not be judged is a reason when another one passed and none failed, unless
    the unit never ran or its service is already reported as not delivered. It has no
    ``violation``.
    """
    found = [_failed(item) for item in checks if item["passed"] is False]
    outcome = tally([item["passed"] for item in checks])
    if checks and outcome is None:
        found.append(reason("requirement", "requirements", "no requirement could be checked"))
    missing = {
        service: key
        for service, key in SERVICES.items()
        if _asked(case, service) and edge[key].value is None
    }
    if outcome:
        skipped = {f"{service}_supply" for service in missing}
        found.extend(_unjudged(item) for item in checks if _unjudgeable(item, skipped))
    for service, key in missing.items():
        found.append(reason("requirement", key, f"the run gives no {key} for the {service}"))
    return found


def _unjudgeable(item, skipped):
    """Return whether an undecided check is a gap: not an idle unit, not a ``skipped`` role."""
    return (
        item["passed"] is None and item["value"].reason != NO_FLOW and item["role"] not in skipped
    )


def _unjudged(item):
    """Return the reason of a requirement check that could not be judged."""
    return reason(
        "requirement",
        item["name"],
        f"{item['name']}: {item['value'].reason}",
        path=item["unit_path"] or None,
        value=item["value"],
        limit=item["limit"],
        role=item["role"],
        quantity=item["quantity"],
    )


def _asked(case, service):
    """Return whether the demand of the case asks for ``service``."""
    return case.demand is not None and getattr(case.demand, service) is not None


def _failed(item):
    """Return the reason of a requirement check that failed."""
    message = f"{item['name']}: {_text(item['value'])} against the limit {_text(item['limit'])}"
    return reason(
        "requirement",
        item["name"],
        message,
        path=item["unit_path"] or None,
        value=item["value"],
        limit=item["limit"],
        worst_step=item["worst_step"],
        role=item["role"],
        quantity=item["quantity"],
        violation=excess(item["value"], item["limit"]),
    )


def _failed_rows(rows):
    """Return the reason of the rows that failed or were skipped, apart from the loops."""
    failed = [row for row in rows if row["code"] != NOT_CONVERGED]
    count = len(failed)
    if not count:
        return []
    top = Counter((row["path"], row["code"]) for row in failed).most_common(1)[0]
    first = next(row for row in failed if (row["path"], row["code"]) == top[0])
    message = (
        f"{count} steps failed; most frequent: {top[0][0]} {top[0][1]} ({top[1]} rows): "
        f"{first['message']}"
    )
    return [
        reason(
            "failed_step",
            "failed_steps",
            message,
            value=measure(count, "-"),
            violation=LARGEST_VIOLATION,
        )
    ]


def _balances(plant, case, results, rows):
    """Return the numerical reasons: balances out of their tolerance, loops not converged."""
    loops = sum(row["code"] == NOT_CONVERGED for row in rows)
    found = []
    if loops:
        message = f"{loops} steps did not converge"
        found.append(
            reason(
                "numerical",
                NOT_CONVERGED,
                message,
                value=measure(loops, "-"),
                violation=LARGEST_VIOLATION,
            )
        )
    checks = [
        mass_balance(plant, case, results),
        energy_balance(plant, case, results),
        *plant_balance(plant, case, results),
    ]
    for item in checks:
        if item["passed"] is False:
            message = f"{item['name']}: {_text(item['value'])} above {_text(item['limit'])}"
            found.append(
                reason(
                    "numerical",
                    item["name"],
                    message,
                    value=item["value"],
                    limit=item["limit"],
                    violation=excess(item["value"], item["limit"]),
                )
            )
    return found


def _bounds(plant, case, results):
    """Return the bound reasons: declared limits of the outputs and operating limits of modules."""
    found = []
    declared = bounds(plant, case, results)
    if declared["passed"] is False:
        count = int(declared["value"].value)
        message = f"{count} recorded values are outside the limits their module declares"
        found.append(reason("bound", "bounds", message, value=declared["value"], violation=1.0))
    for breach in breaches(plant, results.to_frame()):
        found.append(_breach(breach))
    return found


def _breach(breach):
    """Return the bound reason of an operating limit that a run breaches."""
    word = "below" if breach["sense"] == "min" else "above"
    step = breach["step"].isoformat()
    message = (
        f"{breach['path']}.{breach['output']}: {_text(breach['worst'])} {word} the limit "
        f"{_text(breach['limit'])} at {step}"
    )
    return reason(
        "bound",
        breach["output"],
        message,
        path=breach["path"],
        value=breach["worst"],
        limit=breach["limit"],
        worst_step=step,
        violation=excess(breach["worst"], breach["limit"]),
    )
