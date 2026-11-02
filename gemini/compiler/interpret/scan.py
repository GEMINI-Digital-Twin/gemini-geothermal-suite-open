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
"""

import numpy as np

from gemini.compiler.interpret.codes import NONE, raised_codes
from gemini.compiler.interpret.split import split_of
from gemini.compiler.ir import traced_nodes

TIMED = ("inlet", "control", "boundary", "dt")
"""The roles of the graph inputs that hold one value per row."""


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
    rows, scalar = interpreter.rows, interpreter.scalar
    plan = split_of(interpreter.graph, body, not scalar)
    columns = {
        input_node: np.asarray(values[input_node])
        for input_node in interpreter.graph.inputs.values()
        if input_node.role in TIMED
    }
    once_codes = _run_once(interpreter, plan, body, values, feeds)
    sliced = {
        frontier: values[frontier] for frontier in plan.frontier if _per_row(frontier, values, rows)
    }
    seeds = {
        frontier: np.broadcast_to(once_codes[frontier], (rows,))
        for frontier in plan.frontier
        if frontier in once_codes
    }
    seeds.update(_guard_seeds(plan, once_codes, values, rows))
    emitted = np.full((len(body.emits), rows), np.nan)
    for index, emit in enumerate(body.emits):
        if emit not in plan.dependent:
            emitted[index] = np.broadcast_to(np.asarray(values[emit], dtype=float), (rows,))
    steps = _Steps(interpreter, plan, body, values, feeds)
    steps.columns, steps.sliced, steps.seeds, steps.emitted = columns, sliced, seeds, emitted
    steps.watched = _watched_once(plan, body, once_codes, rows)
    steps.carry = [_start(operand, scalar) for operand in operands]
    interpreter.active = set(plan.stepwise) | set(plan.frontier) | set(plan.checks)
    for row in range(rows):
        steps.run(row)
    interpreter.active = None
    values.update(columns)
    values.update(sliced)
    emitted[:, steps.codes != NONE] = np.nan
    if np.any(steps.codes != NONE):
        interpreter.seeds[None] = {output: steps.codes for output in body.outputs}
    finals = [np.asarray(value).item() for value in steps.carry]
    return Scanned(list(emitted), finals, steps.codes, steps.snapshots)


class _Steps:
    """The rows of one scan: the carries, the stacked values and the failed rows so far."""

    def __init__(self, interpreter, plan, body, values, feeds):
        """Start without a failed row; the caller sets the columns, seeds and first carries."""
        self.interpreter, self.plan, self.body = interpreter, plan, body
        self.values, self.feeds = values, feeds
        self.codes = np.full(interpreter.rows, NONE, dtype=np.uint32)
        self.snapshots = {}

    def run(self, row):
        """Evaluate the stepwise part on one row; a failed row keeps the carries and gets a code."""
        interpreter, plan, body, values = self.interpreter, self.plan, self.body, self.values
        for input_node, column in self.columns.items():
            values[input_node] = _at(column, row, interpreter.scalar)
        for frontier, column in self.sliced.items():
            values[frontier] = column[row : row + 1]
        values.update(zip(body.carries, self.carry))
        seed = {frontier: code[row : row + 1] for frontier, code in self.seeds.items()}
        interpreter.seeds[body] = seed
        interpreter.run_nodes(plan.stepwise, values, self.feeds)
        errors = interpreter.propagate(plan.stepwise, plan.checks, values, seed)
        code = _lowest([_first_error(errors, body.watch), self.watched[row]])
        if code is not None:
            self.codes[row] = code
            check = interpreter.graph.checks[code]
            self.snapshots[row] = _snapshot(check, values, row, self.sliced, interpreter.rows)
            return
        for index, emit in enumerate(body.emits):
            if emit in plan.dependent:
                self.emitted[index, row] = np.asarray(values[emit]).item()
        self.carry = [_value(image, values, interpreter.scalar) for image in body.images]


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
        return [None] * rows
    return [None if code == NONE else int(code) for code in np.minimum.reduce(codes)]


def _per_row(node, values, rows):
    """Return whether the value of ``node`` is a column over the rows rather than one value."""
    value = values[node]
    return (
        isinstance(value, np.ndarray) and value.ndim >= 1 and not node.shape and len(value) == rows
    )


def _start(operand, scalar):
    """Return the first value of a carry: a Python number, or an array of one row."""
    number = float(np.asarray(operand).item())
    return number if scalar else np.full(1, number)


def _at(column, row, scalar):
    """Return one row of an input column; a column of one value for every row stays as it is."""
    if column.ndim == 0:
        return column.item() if scalar else column
    return column[row].item() if scalar else column[row : row + 1]


def _value(image, values, scalar):
    """Return the next value of a carry: the image node, or the literal that stands for it."""
    value = values[image] if hasattr(image, "index") else image
    return float(np.asarray(value).item()) if scalar else np.array(value, dtype=float).reshape(1)


def _first_error(errors, watch):
    """Return the lowest error code among the watched nodes of a step, or ``None`` without one."""
    codes = [int(np.min(errors[node])) for node in watch if node in errors]
    lowest = min(codes, default=None)
    return None if lowest is None or lowest == int(NONE) else lowest


def _lowest(codes):
    """Return the lowest of the codes that are not ``None``, else ``None``."""
    return min((code for code in codes if code is not None), default=None)


def _snapshot(check, values, row, sliced, rows):
    """Return the values that word the error of ``check`` at this row, each as one row."""
    nodes = traced_nodes(list(check.attributes.get("values", {}).values()))
    nodes.extend(node for node in [check.attributes.get("break")] if node is not None)
    snapshot = {}
    for node in nodes:
        if node not in values:
            continue
        value = values[node]
        if node not in sliced and _per_row(node, values, rows) and node.op != "input":
            value = value[row : row + 1]
        snapshot[node] = value
    return snapshot
