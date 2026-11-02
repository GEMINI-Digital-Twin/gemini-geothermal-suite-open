"""One report of a finished run (totals, costs, CO2, failures, verdict), and report comparison."""

import json

import numpy as np
import pandas as pd

from gemini._utils.jsonable import to_plain
from gemini._utils.strings import close_matches, did_you_mean, join_names
from gemini.engine.apply import apply_case
from gemini.errors import ValidationError
from gemini.evaluate._utils.cost import equipment
from gemini.evaluate._utils.display import (
    DISPLAY,
    checked_or_map,
    display_units,
    in_unit,
    shown,
)
from gemini.evaluate._utils.ratings import rating_of
from gemini.evaluate._utils.series import energy
from gemini.evaluate._utils.tally import tally
from gemini.evaluate.costs import capex, lcoc, lcoh, lcts, opex
from gemini.evaluate.emissions import co2
from gemini.evaluate.summary import capacities, totals
from gemini.evaluate.verdict import failures, judged, requirements
from gemini.units import Quantity, si_unit
from gemini.units.display import by_si_unit
from gemini.units.shapes import measure


class Report(dict):
    """The report of a run: a dict of the figures of ``report``, with ``to_dict`` for plain JSON."""

    def to_dict(self, units=None):
        """Return the report as plain JSON in display units, a ``Quantity`` as ``{value, unit}``.

        The values inside the report stay SI; the dict shows them in the display table of
        ``gm.evaluate`` (energy in MWh, power in MW, money in MEUR, LCTS in EUR/MWh, CO2 in kt,
        flow in m3/h, temperature in degC), also inside ``capacities`` and ``requirements`` and in
        the parts of a value (annualised cost in MEUR/yr, energy per year in MWh/yr, mass in kt,
        durations in days; ``analysis_period`` and ``payback`` in yr, a
        temperature difference in K). A part that is dimensionless or text stays as it is.

        Parameters
        ----------
        units : dict, optional
            ``{metric: unit}`` that replaces the display unit of a metric of the report, and of
            every part of the same SI unit. A name that is not a metric with a display unit raises
            ``invalid_value``; a unit of another dimension raises ``invalid_unit``.
        """
        chosen = display_units(list(self), units)
        base = by_si_unit()
        return to_plain(
            {
                name: (
                    shown(item, base | {si_unit(DISPLAY[name][1]): chosen[name]})
                    if name in chosen
                    else shown(item, base)
                )
                for name, item in self.items()
            }
        )

    def __str__(self):
        """Return the report as the JSON text of ``to_dict()``."""
        return json.dumps(self.to_dict(), indent=2)


def report(plant, case, results):
    """Return the energy, capacities, costs, CO2, requirements, verdict and failures of a run.

    The costs are read with ``on_error="record"``: a cost that the case or the plant cannot give is
    a value ``None`` with a ``reason``, so that reports of many designs stay comparable.

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
    Report
        A dict with ``heat_delivered``, ``cold_delivered``, ``boiler_heat``,
        ``electricity_bought`` and ``gas_bought`` (J over the run, ``Quantity`` values;
        ``boiler_heat`` is the heat of the boilers), ``capacities`` (see ``capacities``), ``capex``,
        ``opex``, ``lcts``, ``lcoh``, ``lcoc`` and ``co2`` (values; ``capex`` and ``opex`` keep
        their parts, per module and per kind), ``requirements`` (the list of ``requirements``),
        ``passed`` (``False`` if any requirement failed, ``True`` if none failed and one passed,
        else ``None``), ``verdict`` (``gm.evaluate.verdict``, the one answer ``compare`` reads),
        ``failed_steps`` (the number of steps that failed), ``failures`` (the failed
        and skipped rows grouped by module path and code, see ``failures``; empty when nothing
        failed) and ``services`` (the services the case asks for, ``"heating"`` and ``"cooling"``).
        ``to_dict(units=None)`` gives plain JSON in display units.
    """
    sited = apply_case(plant, case)
    edge = totals(sited, case, results)
    checks = requirements(sited, case, results)
    return Report(
        heat_delivered=edge["heat_delivered"],
        cold_delivered=edge["cold_delivered"],
        boiler_heat=_boiler_heat(sited, results),
        electricity_bought=edge["electricity_bought"],
        gas_bought=edge["gas_bought"],
        capacities=capacities(sited, case, results),
        capex=capex(sited, case, "record"),
        opex=opex(sited, case, results, "record"),
        lcts=lcts(sited, case, results, on_error="record"),
        lcoh=lcoh(sited, case, results, on_error="record"),
        lcoc=lcoc(sited, case, results, on_error="record"),
        co2=co2(sited, case, results, "record"),
        requirements=checks,
        passed=tally([item["passed"] for item in checks]),
        verdict=judged(sited, case, results, checks, edge),
        failed_steps=len(results.errors()),
        failures=failures(results),
        services=_services(case),
    )


def _services(case):
    """Return the services that the demand of the case asks for."""
    if case.demand is None:
        return []
    return [name for name in ("heating", "cooling") if getattr(case.demand, name) is not None]


def _boiler_heat(plant, results):
    """Return the heat [J] that the boilers of ``plant`` gave over the run, as a value."""
    frame = results.to_frame()
    boilers = [
        (path, module)
        for path, module in equipment(plant).items()
        if module.equipment_kind in ("boiler", "electric_boiler")
    ]
    if not boilers:
        return measure(None, "J", "the plant has no boiler")
    powers = [rating_of(module).use(frame, path) for path, module in boilers]
    shown = [power for power in powers if power is not None]
    if not shown:
        return measure(None, "J", "the run shows no use of the boilers")
    return measure(sum(energy(power, results.durations) for power in shown), "J")


SENSES = ("min", "max")
"""The two ways to prefer a metric: the smaller or the larger value."""


class Comparison(list):
    """A list of ``{index, values, ranks, pareto, feasible}``, one per report in the order given."""

    def to_frame(self, units=None):
        """Return one row per report: its metrics, its ``rank_<metric>``, ``pareto``, ``feasible``.

        Parameters
        ----------
        units : dict, optional
            ``{metric: unit}``. A metric is shown in its display unit (energy in MWh, power in
            MW, money in MEUR, LCTS in EUR/MWh, mass in kt) unless a unit is given; its column is
            named ``<metric> [<unit>]``. A metric without a display unit stays in SI under its
            own name. A name that is not a metric, or a unit of another dimension, raises
            ``invalid_value`` or ``invalid_unit``.
        """
        names = list(self[0]["values"]) if self else []
        shown = display_units(names, units)
        rows = [
            {
                **{
                    _label(name, shown): (
                        in_unit(name, _number(entry["values"][name]), shown[name])
                        if name in shown
                        else _number(entry["values"][name])
                    )
                    for name in names
                },
                **{f"rank_{name}": rank for name, rank in entry["ranks"].items()},
                "pareto": entry["pareto"],
                "feasible": entry["feasible"],
            }
            for entry in self
        ]
        return pd.DataFrame(rows, index=pd.Index([entry["index"] for entry in self], name="index"))

    def to_dict(self, units=None):
        """Return the entries as plain JSON: every ``Quantity`` as ``{value, unit}``.

        Parameters
        ----------
        units : {"si", "display"} or dict, optional
            ``None`` or ``"si"`` (the default) keeps SI. ``"display"`` shows each metric in its display unit
            (as ``to_frame``, the table of ``gm.units.display``); a dict ``{metric: unit}`` does
            too and replaces the unit of the metrics it names. A name that is not a metric, or a
            unit of another dimension, raises ``invalid_value`` or ``invalid_unit``.
        """
        if units is None or checked_or_map(units) == "si":
            return to_plain(list(self))
        names = list(self[0]["values"]) if self else []
        chosen = display_units(names, units if isinstance(units, dict) else None)
        base = by_si_unit()
        return to_plain(
            [
                {
                    **entry,
                    "values": {
                        name: (
                            shown(item, base | {si_unit(DISPLAY[name][1]): chosen[name]})
                            if name in chosen
                            else shown(item, base)
                        )
                        for name, item in entry["values"].items()
                    },
                }
                for entry in self
            ]
        )

    @classmethod
    def from_dict(cls, data):
        """Return the ``Comparison`` of what ``to_dict`` gave; a metric is a ``Quantity`` again.

        The ``reasons`` stay plain dicts, as ``to_dict`` wrote them.
        """
        return cls(
            {
                **entry,
                "values": {
                    name: Quantity.from_dict(item) if isinstance(item, dict) else item
                    for name, item in entry["values"].items()
                },
            }
            for entry in data
        )


def _number(value):
    """Return the SI number of a comparison value: a ``Quantity``, a plain number or ``None``."""
    return value.si if isinstance(value, Quantity) else value


def _label(name, shown):
    """Return the column name of a metric: with its unit in brackets when it has one."""
    return f"{name} [{shown[name]}]" if name in shown else name


def compare(reports, by):
    """Rank reports by the given metrics and mark the Pareto front of the feasible ones.

    A report is feasible when its ``verdict`` (``gm.evaluate.verdict``) has no reason; compare
    decides nothing itself. A dict without a ``verdict`` raises ``missing_value``: there is no
    silent feasible. Feasible reports rank before all infeasible ones; the infeasible are
    ordered by their number of reasons, then by the metrics.

    Parameters
    ----------
    reports : list of dict
        Reports as ``gm.evaluate.report`` returns them, each with its ``verdict``.
    by : str, list of str or dict
        The metrics, keys of the reports whose value is a ``Quantity`` or a number. A name or a list
        prefers the smaller value of each; a dict ``{metric: "min" or "max"}`` says which. A report
        without a value of a metric (``None``) ranks last for it and is never on the front.

    Returns
    -------
    Comparison
        One entry per report, in the order given: ``index`` (its position), ``values`` (the
        metrics as ``gm.units.Quantity`` in SI; a plain number stays a float; ``None`` for no
        value), ``ranks`` (1 is best; equal values share a rank), ``pareto`` (whether no other
        feasible report is at least as good in every metric and better in one; an infeasible
        report is never on it), ``feasible`` and, when not feasible,
        ``reasons``: those of the ``verdict`` of the report.
        With one metric the front is its best reports. ``to_frame()`` gives a table in display
        units and ``to_dict()`` plain JSON.
    """
    senses = _senses(by, reports)
    values = {name: [_value(report, name) for report in reports] for name in senses}
    quantities = {name: [_quantity(report, name) for report in reports] for name in senses}
    reasons = [_reasons(report, position) for position, report in enumerate(reports)]
    feasible = [not found for found in reasons]
    ranks = {name: _ranks(values[name], senses[name], reasons) for name in senses}
    front = _front(values, senses, feasible)
    return Comparison(
        {
            "index": position,
            "values": {name: quantities[name][position] for name in senses},
            "ranks": {name: ranks[name][position] for name in senses},
            "pareto": bool(front[position]),
            "feasible": feasible[position],
            **({} if feasible[position] else {"reasons": reasons[position]}),
        }
        for position in range(len(reports))
    )


def _reasons(report, position):
    """Return why a report is not feasible: the reasons of its verdict; a report needs one."""
    found = report.get("verdict")
    if found is None:
        raise ValidationError(
            f"reports[{position}]: verdict is missing; expected the report of gm.evaluate.report",
            path=f"reports[{position}].verdict",
            code="missing_value",
        )
    return list(found["reasons"])


def _senses(by, reports):
    """Return ``{metric: "min" or "max"}`` and check the names against the reports."""
    senses = _normal(by)
    if not senses:
        raise ValidationError(
            "by = []; expected at least one metric", path="by", code="invalid_value"
        )
    known = sorted({name for report in reports for name in report})
    for name, sense in senses.items():
        if sense not in SENSES:
            raise ValidationError(
                f"by.{name} = {sense!r}; expected one of {join_names(SENSES)}",
                path=f"by.{name}",
                code="invalid_value",
            )
        if reports and not any(name in report for report in reports):
            raise ValidationError(
                f"by = {name!r}; expected a key of the reports" f"{did_you_mean(name, known)}",
                path="by",
                code="unknown_name",
                suggestions=close_matches(name, known),
            )
    return senses


def _normal(by):
    """Return ``by`` as ``{metric: sense}``."""
    if isinstance(by, str):
        return {by: "min"}
    return dict(by) if isinstance(by, dict) else dict.fromkeys(by, "min")


def _value(report, name):
    """Return the SI number of metric ``name`` of a report, or ``None``."""
    found = report.get(name)
    if found is None:
        return None
    number = getattr(found, "si", found)
    return None if number is None else float(number)


def _quantity(report, name):
    """Return metric ``name`` of a report as a ``Quantity`` in SI, a plain number, or ``None``."""
    found = report.get(name)
    number = _value(report, name)
    if number is None or not isinstance(found, Quantity):
        return number
    return Quantity(number, si_unit(str(found.unit)))


def _worse(values, sense):
    """Return the values as numbers where a smaller one is better; no value or NaN is infinite."""
    sign = 1.0 if sense == "min" else -1.0
    missing = [value is None or np.isnan(value) for value in values]
    return np.array([np.inf if gap else sign * value for gap, value in zip(missing, values)])


def _ranks(values, sense, reasons):
    """Return the rank of each report, 1 for the best; the infeasible come after the feasible.

    Equal reports share the lowest rank. The infeasible are ordered by their number of reasons,
    then by the metric.
    """
    keys = list(zip((len(found) for found in reasons), _worse(values, sense)))
    return [1 + sum(other < key for other in keys) for key in keys]


def _front(values, senses, feasible):
    """Return which feasible reports no other feasible report dominates."""
    table = np.column_stack([_worse(values[name], senses[name]) for name in senses])
    front = np.zeros(len(feasible), dtype=bool)
    allowed = np.asarray(feasible)
    rivals = table[allowed]
    for position in np.flatnonzero(allowed):
        valued = np.isfinite(table[position]).all()
        beaten = (
            (rivals <= table[position]).all(axis=1) & (rivals < table[position]).any(axis=1)
        ).any()
        front[position] = valued and not beaten
    return front
