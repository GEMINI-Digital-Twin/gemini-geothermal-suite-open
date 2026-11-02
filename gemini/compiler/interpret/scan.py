"""Evaluate a ``scan`` node: run its body once per row, carrying the states from row to row.

The rows of a scan are the steps of a run. Before the loop the inlets, controls, boundaries and
step lengths of the graph are columns over the rows. The part of the body that reads no state is
evaluated once on all the rows (``split``); each row then runs the rest on one row of everything
(a Python number on the Python backend, an array of one row on the others, so the body is the one
the rest of the interpreter evaluates). The states are carried: the next value of each is the image
the body computes, except that a row with an error in a watched node (a value that fails a step, see
``Graph.scan``) does not advance them, leaves ``NaN`` in every stacked value and takes the code of
its error, which ``Interpreter.reached`` reports like any row. The values that message the error are
kept for the rows that failed, so ``scanresult`` words it as a plain call does. A loop in the body
(``fixed_point``) runs inside the part it belongs to.

The trials of a study run together: with ``Interpreter.trials`` trials, the columns hold the rows
of every trial one after the other (trial ``i`` owns ``[i * rows, (i + 1) * rows)``), a step takes
one row of each trial (arrays of one value per trial instead of one value) and each trial has its
own carries, error codes and failed rows. A trial alone is the case of one.
"""

import numpy as np

from gemini.compiler.interpret.codes import NONE, raised_codes
from gemini.compiler.interpret.split import split_of
from gemini.compiler.ir import traced_nodes

TIMED = ("inlet", "control", "boundary", "dt")
"""The roles of the graph inputs that hold one value per row.

An input of another role is one too when the trials of a study give it other values (a parameter
of each trial), except the first value of a state.
"""


class Scanned:
    """The values of a scan: the stacked values, the states after the last row and the codes."""

    def __init__(self, emits, finals, codes, snapshots):
        """Keep the stacked values, final states and codes by position, and failed rows' values."""
        self.emits = emits
        self.finals = finals
        self.codes = codes
        self.snapshots = snapshots

    def column(self, key):
        """Return the stacked values of ``("emit", index)`` or the final ``("state", index)``."""
        kind, index = key
        return self.emits[index] if kind == "emit" else self.finals[index]


def evaluate_scan(interpreter, node, operands, values, feeds):
    """Run the body of the ``scan`` ``node`` over the rows of the graph; return a ``Scanned``."""
    body = node.attributes["body"]
    rows, scalar, trials = interpreter.rows, interpreter.scalar, interpreter.trials
    total = rows * trials
    plan = split_of(interpreter.graph, body, not scalar)
    columns = _columns(interpreter.graph, values)
    once_codes = _run_once(interpreter, plan, body, values, feeds)
    sliced = {
        frontier: values[frontier]
        for frontier in plan.frontier
        if _per_row(frontier, values, total)
    }
    seeds = {
        frontier: np.broadcast_to(once_codes[frontier], (total,))
        for frontier in plan.frontier
        if frontier in once_codes
    }
    seeds.update(_guard_seeds(plan, once_codes, values, total))
    steps = _Steps(interpreter, plan, body, values, feeds)
    steps.columns, steps.sliced, steps.seeds = columns, sliced, seeds
    steps.emitted = _emitted_once(plan, body, values, total)
    steps.watched = _watched_once(plan, body, once_codes, total)
    steps.carry = [_start(operand, scalar, trials) for operand in operands]
    interpreter.active = set(plan.stepwise) | set(plan.frontier) | set(plan.checks)
    for row in range(rows):
        steps.run(row)
    interpreter.active = None
    values.update(columns)
    values.update(sliced)
    steps.emitted[:, steps.codes != NONE] = np.nan
    if np.any(steps.codes != NONE):
        interpreter.seeds[None] = {output: steps.codes for output in body.outputs}
    finals = [np.asarray(value).item() if scalar else np.asarray(value) for value in steps.carry]
    return Scanned(list(steps.emitted), finals, steps.codes, steps.snapshots)


def _columns(graph, values):
    """Return the inputs that hold one value per row: the roles of ``TIMED``, or a trial's own."""
    columns = {}
    for input_node in graph.inputs.values():
        column = np.asarray(values[input_node])
        own = input_node.role != "state" and column.ndim > len(input_node.shape)
        if input_node.role in TIMED or own:
            columns[input_node] = column
    return columns


def _emitted_once(plan, body, values, total):
    """Return the stacked values with those that read no state filled in, the others ``NaN``."""
    emitted = np.full((len(body.emits), total), np.nan)
    for index, emit in enumerate(body.emits):
        if emit not in plan.dependent:
            emitted[index] = np.broadcast_to(np.asarray(values[emit], dtype=float), (total,))
    return emitted


class _Steps:
    """The rows of one scan: the carries, the stacked values and the failed rows so far."""

    def __init__(self, interpreter, plan, body, values, feeds):
        """Start without a failed row; the caller sets the columns, seeds and first carries."""
        self.interpreter, self.plan, self.body = interpreter, plan, body
        self.values, self.feeds = values, feeds
        self.trials = interpreter.trials
        self.codes = np.full(interpreter.rows * self.trials, NONE, dtype=np.uint32)
        self.snapshots = {}

    def run(self, row):
        """Evaluate the stepwise part on one row of every trial.

        A trial whose row failed keeps its carries and gets a code; the others go on.
        """
        interpreter, plan, body, values = self.interpreter, self.plan, self.body, self.values
        trials, scalar = self.trials, interpreter.scalar
        for input_node, column in self.columns.items():
            values[input_node] = _at(column, row, scalar, trials)
        for frontier, column in self.sliced.items():
            values[frontier] = _across(column, row, trials)
        values.update(zip(body.carries, self.carry))
        seed = {frontier: _across(code, row, trials) for frontier, code in self.seeds.items()}
        interpreter.seeds[body] = seed
        interpreter.run_nodes(plan.stepwise, values, self.feeds)
        errors = interpreter.propagate(plan.stepwise, plan.checks, values, seed)
        code = np.minimum(
            _first_errors(errors, body.watch, trials), _across(self.watched, row, trials)
        )
        failed = code != NONE
        if failed.any():
            self._fail(row, code, failed)
        if failed.all():
            return
        for index, emit in enumerate(body.emits):
            if emit in plan.dependent:
                emits = self.emitted[index].reshape(trials, -1)
                emits[~failed, row] = _per_trial(values[emit], trials)[~failed]
        following = [_value(image, values, scalar, trials) for image in body.images]
        if failed.any():
            following = [np.where(failed, old, new) for old, new in zip(self.carry, following)]
        self.carry = following

    def _fail(self, row, code, failed):
        """Record the code and the values that word the error of every trial that failed here."""
        interpreter, rows = self.interpreter, self.interpreter.rows
        for trial in np.flatnonzero(failed):
            where = int(trial) * rows + row
            self.codes[where] = code[trial]
            check = interpreter.graph.checks[int(code[trial])]
            self.snapshots[where] = _snapshot(
                check, self.values, where, int(trial), self.sliced, rows * self.trials, self.trials
            )


def _run_once(interpreter, plan, body, values, feeds):
    """Evaluate the nodes that read no state on all the rows; return their error codes."""
    if not plan.once:
        return {}
    interpreter.active = set(plan.once)
    interpreter.run_nodes(plan.once, values, feeds)
    checks = [check for check in body.checks if check in interpreter.active]
    return interpreter.propagate(plan.once, checks, values, {})


def _guard_seeds(plan, once_codes, values, rows):
    """Return the error codes that checks run once put on nodes that run at each row."""
    failing = {}
    for check in {check for checks in plan.guards.values() for check in checks}:
        raised = raised_codes(values[check])
        if np.any(raised != NONE):
            failing[check] = np.broadcast_to(raised, (rows,))
    seeds = {}
    for node, checks in plan.guards.items():
        codes = [failing[check] for check in checks if check in failing]
        if codes:
            seeds[node] = np.minimum.reduce(codes)
    return seeds


def _watched_once(plan, body, once_codes, rows):
    """Return, for each row, the lowest error code in a watched node that reads no state."""
    codes = [
        np.broadcast_to(once_codes[node], (rows,))
        for node in body.watch
        if node in once_codes and node not in plan.dependent
    ]
    if not codes:
        return np.full(rows, NONE, dtype=np.uint32)
    return np.minimum.reduce(codes)


def _per_row(node, values, rows):
    """Return whether the value of ``node`` is a column over the rows rather than one value."""
    value = values[node]
    return (
        isinstance(value, np.ndarray) and value.ndim >= 1 and not node.shape and len(value) == rows
    )


def _start(operand, scalar, trials):
    """Return the first value of a carry: a Python number, or an array with one value per trial."""
    if scalar:
        return float(np.asarray(operand).item())
    return np.array(np.broadcast_to(np.asarray(operand, dtype=float).reshape(-1), (trials,)))


def _across(column, row, trials):
    """Return row ``row`` of every trial of a column over all the rows of the trials."""
    return column.reshape(trials, -1)[:, row]


def _at(column, row, scalar, trials):
    """Return one row of an input column; a column of one value for every row stays as it is."""
    if column.ndim == 0:
        return column.item() if scalar else column
    if scalar:
        return column[row].item()
    return column.reshape(trials, -1, *column.shape[1:])[:, row]


def _value(image, values, scalar, trials):
    """Return the next value of a carry: the image node, or the literal that stands for it."""
    value = values[image] if hasattr(image, "index") else image
    if scalar:
        return float(np.asarray(value).item())
    return _per_trial(value, trials).copy()


def _per_trial(value, trials):
    """Return ``value`` as one float for each trial."""
    return np.broadcast_to(np.asarray(value, dtype=float).reshape(-1), (trials,))


def _first_errors(errors, watch, trials):
    """Return the lowest error code of the watched nodes of a step for each trial."""
    codes = np.full(trials, NONE, dtype=np.uint32)
    for node in watch:
        if node in errors:
            codes = np.minimum(codes, np.broadcast_to(np.atleast_1d(errors[node]), (trials,)))
    return codes


def _snapshot(check, values, where, trial, sliced, total, trials):
    """Return the values that word the error of ``check`` at a row of a trial, each as one row."""
    nodes = traced_nodes(list(check.attributes.get("values", {}).values()))
    nodes.extend(node for node in [check.attributes.get("break")] if node is not None)
    snapshot = {}
    for node in nodes:
        if node not in values:
            continue
        value = values[node]
        if isinstance(value, np.ndarray) and value.ndim >= 1 and not node.shape:
            if len(value) == total and node not in sliced and node.op != "input":
                value = value[where : where + 1]
            elif len(value) == trials and trials > 1:
                value = value[trial : trial + 1]
        snapshot[node] = value
    return snapshot
