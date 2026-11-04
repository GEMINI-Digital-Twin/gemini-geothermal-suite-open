"""Trials of a search: the plant and the case with new values, run and read.

The trials of a batch share one plant (``gemini.study._utils.shared``) and run side by side
(``gemini.engine.lockstep``): each one sets its values, plans and prepares its run, the array
passes of all of them are one, and each reads its metrics from its own results. A trial alone
is a batch of one and gives the same numbers.
"""

from gemini._utils.strings import close_matches, did_you_mean, join_names
from gemini.engine.apply import applied_in_place
from gemini.engine.lockstep import Lane, lockstep
from gemini.engine.simulate import simulation_steps
from gemini.errors import GeminiError, ValidationError
from gemini.evaluate import annualised_cost, co2, lcoc, lcoh, lcts, totals, verdict
from gemini.evaluate.summary import KPI_NAMES
from gemini.evaluate.verdict import LARGEST_VIOLATION, failures, ranked
from gemini.study._utils import progress
from gemini.study._utils.shared import Shared
from gemini.study._utils.target import is_case_name, with_case_values
from gemini.units.shapes import measure

ECONOMICS = {
    "lcoh": lcoh,
    "lcoc": lcoc,
    "lcts": lcts,
    "annualised_cost": annualised_cost,
    "co2": co2,
}
"""The economic metrics of ``gm.evaluate``; the others are the KPIs of ``gm.evaluate.totals``."""

METRICS = (*KPI_NAMES, *ECONOMICS)
"""The names of every metric a study reads, in order: the one list ``gm.study.metrics`` shows."""


def checked_metric(name):
    """Return ``name`` when it is a metric the call can read, or raise with the close names."""
    known = list(METRICS)
    if name not in known:
        raise ValidationError(
            f"study: metric = {name!r}; expected one of {join_names(known)}"
            f"{did_you_mean(name, known)}",
            path="metric",
            code="unknown_name",
            suggestions=close_matches(name, known),
        )
    return name


def metric(plant, case, results, name):
    """Return one metric of a finished run; a value it cannot give is ``None`` with a reason."""
    if name in ECONOMICS:
        return ECONOMICS[name](plant, case, results, on_error="record")
    return totals(plant, case, results)[name]


def failure_reason(results):
    """Return the reason of a run with failed steps: their count and the most frequent failure.

    The failure is the group of ``gm.evaluate.failures`` with the most failed rows, as
    ``path code (rows): message``.
    """
    top = next(group for group in failures(results).groups if group["kind"] == "failed")
    return (
        f"{len(results.failures)} steps failed; most frequent: {top['path']} {top['code']} "
        f"({top['count']} rows): {top['message']}"
    )


STRUCTURAL = 1.0
"""The violation of a structural reason when the structure is searched: a service missing whole."""


def judged(plant, case, results, structural=False):
    """Return ``(reason, violation)`` of a finished run from its ``gm.evaluate.verdict``.

    The reasons a design variable can change are the ones with a ``violation`` (``ranked``): a
    failed requirement, an operating limit, a failed step, a balance out of its tolerance. The
    ``violation`` is their sum, at most ``LARGEST_VIOLATION``, and the ``reason`` is the first of
    them. A reason with none is structural (a service the plant has no unit for) and does not rank
    the trials: it stays in the verdict of the run that ``report`` gives. With ``structural``, for a
    search of the structure itself, a verdict that is not feasible only for such a reason is the
    reason with the violation ``STRUCTURAL``. A feasible run is ``(None, 0.0)``.
    """
    given = verdict(plant, case, results)
    found = ranked(given)
    if structural and not given["feasible"]:
        found = found or [given["reasons"][0] | {"violation": STRUCTURAL}]
    if not found:
        return None, 0.0
    return found[0], min(sum(item["violation"] for item in found), LARGEST_VIOLATION)


class _Trial:
    """One trial of a batch: its values, its metrics to read and the lane it runs in."""

    def __init__(self, shared, case, plan, values, names, judge, flag=False, structural=False):
        """Prepare the trial of ``values`` on ``shared``.

        ``judge`` adds the verdict to the read; ``flag``, for a trial that is not judged, adds
        whether the run is feasible.
        """
        self.shared, self.case, self.plan = shared, case, plan
        self.values, self.names, self.judge, self.flag = values, names, judge, flag
        self.structural = structural
        self.held = None
        self.lane = Lane(self._steps(), self._restore)

    def _restore(self):
        """Put the shared plant back as this trial has it."""
        if self.held is not None:
            self.held.restore()

    def _steps(self):
        """Run the trial; return ``(metrics, reason)`` or, judged, ``(metrics, reason, violation)``.

        A run that fails has its reason (``failure_reason`` for a failed step, with every metric
        ``None``) and, judged, the largest violation. A flagged trial gives ``(metrics, reason,
        feasible)`` with the metrics of the unjudged read; a run that fails is not feasible.
        """
        try:
            trial, changed, results = yield from self._simulated()
            if self.judge:
                metrics = {item: metric(trial, changed, results, item) for item in self.names}
                return (metrics, *judged(trial, changed, results, self.structural))
            if results.failures:
                reason = failure_reason(results)
                found = {item: measure(None, "-", reason) for item in self.names}, reason
                return (*found, False) if self.flag else found
            found = {item: metric(trial, changed, results, item) for item in self.names}, None
            if self.flag:
                return (*found, verdict(trial, changed, results)["feasible"])
            return found
        except GeminiError as error:
            if self.judge:
                return {}, str(error), LARGEST_VIOLATION
            return ({}, str(error), False) if self.flag else ({}, str(error))

    def _simulated(self):
        """Set the values on the shared plant and run it; return ``(plant, case, results)``.

        ``values`` are SI numbers by name: a parameter of the plant, or ``case.<path>`` for a
        number of the case, which this trial's copy of the case takes.
        """
        self.shared.reset()
        plant = self.shared.plant
        for name, number in self.values.items():
            if not is_case_name(name):
                path, _, parameter = name.rpartition(".")
                plant._set_si_params(path, {parameter: number})
        changed = with_case_values(
            self.case, {k: v for k, v in self.values.items() if is_case_name(k)}
        )
        plant = applied_in_place(plant, changed)
        self.held = self.shared.capture(changed)
        results = yield from simulation_steps(plant, changed, self.plan)
        return plant, changed, results


def run_trials(shared, case, plan, valued, names, judge, *, flag=False, structural=False):
    """Return the outcome of each of the trials ``valued`` (a list of ``{name: SI number}``).

    The outcome is ``(metrics, reason)``, or ``(metrics, reason, violation)`` when ``judge``: a
    run that fails is infeasible with its message as the reason and ``LARGEST_VIOLATION``. With
    ``flag`` and no ``judge``, the outcome is ``(metrics, reason, feasible)``, the metrics being
    those of the unjudged read; ``structural`` judges as ``judged`` says. The trials run together
    on ``shared`` (a ``Shared``) and each gives what it gives alone. Each trial that ends is
    counted for ``gemini.study._utils.progress``.
    """
    trials = [
        _Trial(shared, case, plan, values, names, judge, flag, structural) for values in valued
    ]
    return lockstep([trial.lane for trial in trials], lambda lane: progress.finished())


def drawn_trials(shared, valued):
    """Return ``run_trials`` of ``valued`` with the ``(plant, case, plan, names)`` it shares.

    Each outcome is ``(metrics, reason, feasible)``: the draws and the ends are not judged, but
    each says whether its run is feasible.

    The function ``gemini.study._utils.parallel.mapped`` runs in a worker process, which copies
    the plant once for its trials.
    """
    plant, case, plan, names = shared
    return run_trials(Shared(plant), case, plan, valued, names, False, flag=True)
