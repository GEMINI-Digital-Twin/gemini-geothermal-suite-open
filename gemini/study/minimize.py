"""Search of the design space a plant file states: its ranges and options, and its doublet count."""

from copy import deepcopy

import numpy as np
from scipy.optimize import differential_evolution

from gemini import units
from gemini._utils.jsonable import to_plain
from gemini.engine.check import check
from gemini.errors import ValidationError
from gemini.errors.base import raise_issues
from gemini.plants._utils.resize import resized
from gemini.study._utils.best import Best
from gemini.study._utils.parallel import mapped
from gemini.study._utils.progress import counting
from gemini.study._utils.shared import Shared
from gemini.study._utils.shown import difference_names, shown
from gemini.study._utils.target import quantity_of, unit_of
from gemini.study._utils.trial import LARGEST_VIOLATION, checked_metric, run_trials
from gemini.study._utils.variables import DOUBLETS, counts, variables
from gemini.units.shapes import Value, measure

POPULATION_PER_VARIABLE = 5
"""Candidates of a generation per variable: a small budget still sees several generations."""
SMALLEST_POPULATION = 5
"""The fewest candidates of a generation, which ``differential_evolution`` needs."""


NOT_A_NUMBER = "the objective is not a number"
"""The reason of a trial whose objective is NaN, which a run without failed steps can give."""


def _is_number(value):
    """Whether an objective is a finite number; ``None`` and NaN rank a trial as infeasible."""
    return value is not None and bool(np.isfinite(value))


def _ranked(sign, number, reason, violation):
    """Return the objective the search sees: feasible trials in (-1, 1), the others above 2.

    The map is monotone, so every feasible trial is better than every infeasible one, and the
    infeasible ones are ordered by their violation.
    """
    if reason is None:
        scaled = sign * number
        return scaled / (1 + abs(scaled))
    return 2 + violation / (1 + violation)


class Search(dict):
    """The result of ``minimize``: ``{best, feasible, history, evaluations}``, with ``to_dict``.

    It is the dict ``minimize`` has always returned; ``to_dict`` gives its plain JSON form, the one
    ``StudyResult.to_dict`` writes as ``found``, so that a caller can store or show the progress of
    a search without reading its parts.
    """

    def to_dict(self):
        """Return the result as plain JSON in display units, without the best plant.

        ``best`` and each entry of ``history`` are ``{"value", "unit", ...}`` with its
        ``parameters`` and ``violation``; ``best["plant"]`` is ``None`` (write the plant itself
        with ``found["best"]["plant"].to_json``).
        """
        best = self["best"].to_dict() | {"plant": None}
        return {
            "best": best,
            "feasible": self["feasible"],
            "evaluations": self["evaluations"],
            "history": [
                to_plain(shown(item, item.parts.get("differences", ()))) for item in self["history"]
            ],
        }


def _entry(parameters, metrics, name, reason, violation, lifts):
    """Return one line of the history: the objective, with the parameters and the violation.

    ``lifts`` names the parameters that are differences of temperature, listed when there are any.
    """
    metric = metrics.get(name, measure(None, "-", reason))
    extra = {"differences": lifts} if lifts else {}
    return Value(
        metric.value,
        metric.unit,
        reason or metric.reason,
        metric.parts | {"parameters": parameters, "violation": violation} | extra,
    )


def _generations(evaluations, count):
    """Return ``(population, generations after the first)`` that fit the budget."""
    population = max(SMALLEST_POPULATION, POPULATION_PER_VARIABLE * count)
    if evaluations < population:
        raise ValidationError(
            f"study.minimize: evaluations = {evaluations}; {count} variables need at least "
            f"{population}",
            path="evaluations",
        )
    return population, evaluations // population - 1


def _values(found, point):
    """Return ``{flat name: value}`` of the parameters a point of the search sets."""
    values = {}
    for variable, number in zip(found, point):
        chosen = _chosen(variable, float(number))
        values.update(dict.fromkeys(variable.paths, chosen))
    return values


def _chosen(variable, number):
    """Return the value of a variable at ``number``: a float, an integer or an option."""
    if variable.options is not None:
        return variable.options[int(round(number))]
    return int(round(number)) if variable.integer else number


def _shown(plant, case, found, point):
    """Return ``{variable name: Quantity or option}`` of a point, in the SI unit of each."""
    shown = {}
    for variable, number in zip(found, point):
        chosen = _chosen(variable, float(number))
        if variable.options is None:
            chosen = units.Quantity(chosen, unit_of(plant, case, variable.paths[0]))
        shown[variable.name] = chosen
    return shown


def _lifts(plant, case, found):
    """Return the names of the variables that are differences of temperature."""
    paths = {item.name: item.paths[0] for item in found if item.options is None}
    parameters = {
        name: units.Quantity(0.0, unit_of(plant, case, path)) for name, path in paths.items()
    }
    return difference_names(parameters, lambda name: quantity_of(plant, case, paths[name]))


def _design(plant, parameters):
    """Return a copy of ``plant`` on the doublet count and with the values of a trial."""
    count = parameters.get(DOUBLETS)
    design = deepcopy(plant) if count is None else resized(plant, int(count.value))
    for variable in variables(design):
        chosen = parameters[variable.name]
        number = chosen if variable.options is not None else chosen.value
        for flat in variable.paths:
            path, _, parameter = flat.rpartition(".")
            design._set_si_params(path, {parameter: number})
    return design


def _best(history, sign, plant):
    """Return ``(Best, feasible)``: the best feasible trial, else the least violating one.

    A trial that ran but broke a limit is returned, with its ``reason``, only when none is
    feasible; with no trial that ran, ``Best`` has no value and no plant.
    """
    ran = [item for item in history if item.value is not None]
    feasible = [item for item in ran if item.reason is None]
    if not ran:
        reason = "every trial failed"
        return Best(None, "-", reason, {"parameters": None}, None), False
    if feasible:
        found = min(feasible, key=lambda item: sign * item.value)
    else:
        found = min(ran, key=lambda item: item.parts["violation"])
    design = _design(plant, found.parts["parameters"])
    return Best(found.value, found.unit, found.reason, found.parts, design), bool(feasible)


def _start(design, found):
    """Return the point of the design itself, each value clipped to the bounds of its variable.

    A variable takes the value the design has for its first parameter; a choice, the index of its
    value among the options; a parameter with no number takes the middle of its bounds.
    """
    point = []
    for variable in found:
        path, _, parameter = variable.paths[0].rpartition(".")
        held = getattr(design.get_submodule(path), parameter, None)
        if variable.options is not None:
            point.append(float(variable.options.index(held)) if held in variable.options else 0.0)
            continue
        number = (variable.low + variable.high) / 2 if not isinstance(held, (int, float)) else held
        point.append(min(max(float(number), variable.low), variable.high))
    return point


def _bounds(found):
    """Return the ``(low, high)`` of every variable for the search; a choice is an index."""
    return [
        (0.0, float(len(item.options) - 1)) if item.options is not None else (item.low, item.high)
        for item in found
    ]


def _discrete(found):
    """Return the ``integrality`` of the variables, or ``None`` when all are continuous."""
    flags = [item.options is not None or item.integer for item in found]
    return np.array(flags) if any(flags) else None


def _search(evaluated, found, evaluations, start, seed, generations=None):
    """Run the search of the variables from ``start``; with none, evaluate once.

    ``generations`` is the number of generations after the first; without it, what the budget
    allows. With ``0`` only the first population is evaluated, which is how the points of the
    first generation are known before the search runs.
    """
    if not found:
        evaluated(np.empty(0))
        return
    population, allowed = _generations(evaluations, len(found))
    differential_evolution(
        evaluated,
        _bounds(found),
        maxiter=allowed if generations is None else generations,
        popsize=population,
        x0=start,
        tol=0,
        polish=False,
        seed=seed,
        integrality=_discrete(found),
    )


class _Population:
    """The first population of a search, run as one batch, and the trials after it one by one.

    ``differential_evolution`` with ``updating="immediate"`` (the default, and the trial sequence
    this search has always had) builds each candidate of a generation from the members replaced
    before it, so only the first population, which is drawn before any trial is known, is one
    batch; its points are found by a search of zero generations that records them. A point that
    was run in the batch is read from there when the search asks for it, in the order the search
    asks, so the history, the order and the random draws are those of a search that runs every
    trial alone.
    """

    def __init__(self, shared, case, plan, name, found):
        """Run the trials on ``shared``, the plant of the search, judged on ``name``."""
        self.shared, self.case, self.plan, self.name, self.found = shared, case, plan, name, found
        self.known = {}

    def prepare(self, evaluations, start, seed):
        """Run the first population of the search that ``evaluations`` and ``seed`` describe."""
        points = []

        def record(point):
            points.append(np.array(point, dtype=float))
            return 0.0

        _search(record, self.found, evaluations, start, seed, generations=0)
        outcomes = self.run([_values(self.found, point) for point in points])
        for point, outcome in zip(points, outcomes):
            self.known.setdefault(point.tobytes(), []).append(outcome)

    def run(self, valued):
        """Return the outcome ``(metrics, reason, violation)`` of the trials of ``valued``."""
        if not valued:
            return []
        return run_trials(self.shared, self.case, self.plan, valued, {self.name}, True)

    def outcome(self, point):
        """Return the outcome of the trial at ``point``: the batch's, else one trial alone.

        A trial of the batch is read once, so a point asked twice is run twice, as it is alone.
        """
        waiting = self.known.get(np.asarray(point, dtype=float).tobytes())
        if waiting:
            return waiting.pop(0)
        return self.run([_values(self.found, point)])[0]


def _counted(shared, count):
    """Return the history of the search on ``count`` doublets, ``None`` for the plant as it is."""
    plant, case, plan, name, sign, evaluations, seed = shared
    design = plant if count is None else resized(plant, count)
    chosen = {} if count is None else {DOUBLETS: units.Quantity(count, "-")}
    found = variables(design)
    history = []
    lifts = _lifts(design, case, found)
    population = _Population(Shared(design), case, plan, name, found)

    def evaluated(point):
        metrics, reason, violation = population.outcome(point)
        if reason is None and not _is_number(metrics[name].value):
            reason, violation = metrics[name].reason or NOT_A_NUMBER, LARGEST_VIOLATION
            metrics = metrics | {name: measure(None, metrics[name].unit, reason)}
        shown = chosen | _shown(design, case, found, point)
        history.append(_entry(shown, metrics, name, reason, violation, lifts))
        return _ranked(sign, history[-1].value, reason, violation)

    start = _start(design, found)
    if found:
        population.prepare(evaluations, start, seed)
    _search(evaluated, found, evaluations, start, seed)
    return history


def trials_of(plant, evaluations):
    """Return the number of trials ``minimize`` runs on ``plant``: the sum over its doublet counts.

    A count with variables runs whole populations, as many as the budget allows; one without
    runs the design once. A search that ends before its budget runs fewer.
    """
    total = 0
    for count in counts(plant):
        found = variables(plant if count is None else resized(plant, count))
        if not found:
            total += 1
            continue
        population, allowed = _generations(evaluations, len(found))
        total += population * (allowed + 1)
    return total


def minimize(plant, case, objective, evaluations, seed, *, plan=None, on_progress=None):
    """Return the design of a plant that minimises a metric, searched in the space the plant states.

    The variables are the plant's own: every leaf with a ``range`` (continuous, or integer when
    the parameter is) and every leaf with ``options`` (a choice among strings), and the number of
    doublets when ``size.doublets`` has a ``range``. Leaves with the same parameter name, the same
    role and an equal range are one variable (three chillers of one range are one capacity); the
    order is that of the file. ``gm.check`` runs first and raises its issues, so a plant is sized
    first (``gm.study.size`` completes a template plant).

    Each trial copies the plant, sets the variables, simulates the copy on the case
    (``gm.simulate`` plans the demand on that design) and reads the objective from
    ``gm.evaluate``. The variables are searched with ``scipy.optimize.differential_evolution``
    from a Latin hypercube with the given ``seed``; the integers and the choices are searched as
    integers. One member is the plant as it is given (its own values, clipped to the bounds), so a
    start inside the bounds is among the trials and the best is never worse than it. It needs no
    gradient and its population gives the exact number of simulations. The number of doublets is
    a discrete variable: the search runs once for each count, from the lowest to the highest, on
    a new plant of that size, and the best trial of all counts wins; with
    ``gm.runtime.settings(processes=n)`` the searches of the counts run in ``n`` worker processes
    and give the same result. The plant and the case themselves are not changed.

    A trial is feasible when its ``gm.evaluate.verdict`` has no reason a design can change (the
    reasons with a ``violation``): no failed step, every requirement of the case passes, the
    supply temperatures of the services included, no operating limit breached. A reason no variable
    can change (a service the plant has no unit for) is not held against a trial; the verdict of
    the best plant, from ``gm.evaluate.report``, keeps it. A
    trial that does not run (a physics error, say at some depth) is infeasible with the largest
    violation. The search sees feasible trials as better than infeasible ones, and infeasible
    ones ordered by their total relative violation, so it moves towards feasibility. The best
    feasible trial is ``best``; with none, ``best`` is the least violating trial and ``feasible``
    is ``False``.

    Parameters
    ----------
    plant : Plant
        A plant with parameter values, and the ranges and options to search.
    case : Case
        What the plant is asked to do: its demand is planned for each trial, so a variable that
        changes the design changes the plan, and its economics give the prices.
    objective : str
        The metric to minimise, a KPI of ``gm.evaluate.totals`` or ``lcoh``, ``lcoc``, ``lcts``,
        ``annualised_cost`` or ``co2``; a metric to maximise is given with a leading ``"-"``.
    evaluations : int
        The largest number of simulations for each doublet count; at least five per variable, and
        at least five. It has no default.
    seed : int
        Seed of the search; the same call gives the same trials. It has no default.
    plan : DataFrame, optional
        The run input held fixed over the trials, for a building block with no demand; without it
        each trial is planned from the case.
    on_progress : callable, optional
        ``on_progress(done, total)``, called in the calling process after each finished trial,
        also when the searches run in worker processes; ``total`` is the number of trials the
        budget gives, and ``done`` reaches it at the end even when a search ends early. Raising
        ``gm.errors.Cancelled`` from it stops the search: no later trial starts, the workers are
        stopped and the exception propagates. The trials, their order and the result do not
        depend on it; any other exception it raises propagates too.

    Returns
    -------
    dict
        ``{best, feasible, history, evaluations}``. ``best`` is the objective as a ``Value`` in
        SI, whose ``parts["parameters"]`` are ``{name: Quantity}`` (an option is its string) and
        whose ``["plant"]`` is the best plant: a ``Plant`` with the best doublet count and the
        values set, whose ``to_json`` is a plant file that runs. ``feasible`` is whether ``best``
        is feasible; if not, ``best`` is the least violating trial that ran and its ``reason``
        says why. ``history`` lists the same as ``best`` for every trial, with
        ``parts["violation"]`` (0 when feasible) and a ``reason`` for an infeasible trial: the
        first reason of its verdict (its dict), a text for a failed run.
        ``evaluations`` is the number of simulations. With no trial that ran, ``best`` has no
        value and no plant, and gives a ``reason``. It is a ``Search``, a dict whose ``to_dict()``
        gives the JSON form with the history.

    Raises
    ------
    ValidationError
        The issues of ``gm.check``; ``invalid_design`` when the plant states nothing to search;
        ``missing_value`` for a range with one side only.
    """
    raise_issues(check(plant, case))
    name = checked_metric(objective.removeprefix("-"))
    sign = -1.0 if objective.startswith("-") else 1.0
    sizes = counts(plant)
    if sizes == [None] and not variables(plant):
        raise ValidationError(
            "study.minimize: the plant states no range and no options; expected at least one "
            "leaf with a range or options to search",
            path="params",
            code="invalid_design",
        )
    if sizes != [None]:
        resized(plant, sizes[0])
    shared = (plant, case, plan, name, sign, evaluations, seed)
    total = None if on_progress is None else trials_of(plant, evaluations)
    with counting(on_progress, total) as count:
        history = [entry for found in mapped(_counted, shared, sizes) for entry in found]
        if count is not None:
            count.reach(total)
    best, feasible = _best(history, sign, plant)
    return Search(best=best, feasible=feasible, history=history, evaluations=len(history))
