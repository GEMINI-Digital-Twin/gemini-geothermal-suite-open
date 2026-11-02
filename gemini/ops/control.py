"""``scan``: time stepping with a carried state, one step after the other.

``scan(body, init, xs, length)`` calls ``body(state, x)`` for each of ``length`` steps, carries the
state it returns to the next step and collects what it returns for each step. A step that fails
(``body`` raises) is a failed step: its values are NaN, its error is kept, and the next step starts
from the state before it, so a failed step never advances the state. In a trace the call records a
``scan`` node of the graph (``Graph.scan``); outside one it runs the loop, which is the reference
of every other implementation.
"""

from typing import NamedTuple

import numpy as np

from gemini.ops import scope
from gemini.ops.registry import register

register("scan", "scan", 3)


class Scanned(NamedTuple):
    """What a scan gives: the ``final`` state, the stacked values ``ys``, the failed steps.

    ``ys`` is a list of arrays, one per value ``body`` returns, with the steps on the first axis
    and NaN at a failed step. ``failed`` is a boolean array over the steps and ``errors(step)``
    the exception of a failed one.
    """

    final: object
    ys: list
    failed: np.ndarray
    errors: object


def scan(body, init, xs, length, halt=None):
    """Return the ``Scanned`` of ``body`` over ``length`` steps from the state ``init``.

    ``xs`` maps a name to its values over the steps (the first axis, or one value for all) and
    ``body(state, x)`` gets ``x``, the same names at one step, and returns ``(state, values)``
    where ``values`` is a flat list of numbers, lists of numbers or ``None``. ``halt(error)``,
    when given, tells that a failed step ends the scan: the steps after it are failed with the
    same error and the state stays as it was before it.
    """
    graph = scope.traced_graph()
    if graph is not None:
        return graph.scan(body, init, xs, length, halt)
    return _run(body, init, xs, length, halt)


def _run(body, init, xs, length, halt):
    """Run the loop of ``scan`` on Python values."""
    columns = {name: _steps(value, length) for name, value in xs.items()}
    state, values, errors = init, [], {}
    stopped = None
    for step in range(length):
        if stopped is not None:
            errors[step] = stopped
            values.append(None)
            continue
        try:
            state, found = body(
                state, {name: _at(column, step) for name, column in columns.items()}
            )
        except Exception as error:
            errors[step] = error
            values.append(None)
            if halt is not None and halt(error):
                stopped = error
            continue
        values.append(found)
    failed = np.zeros(length, dtype=bool)
    failed[list(errors)] = True
    return Scanned(state, _stacked(values, length), failed, errors.__getitem__)


def _steps(value, length):
    """Return a list of the values of ``xs`` over the steps, or the one value for all."""
    array = np.asarray(value)
    return array.tolist() if array.ndim and len(array) == length else array.item()


def _at(column, step):
    return column[step] if type(column) is list else column


def _stacked(values, length):
    """Return the values of the steps as arrays over the steps; a failed step is NaN."""
    first = next((found for found in values if found is not None), None)
    if first is None:
        return []
    absent = [_missing(item) for item in first]
    table = [absent if found is None else found for found in values]
    return [_column(list(column)) for column in zip(*table)] if length else []


def _missing(item):
    """Return what a failed step holds where ``item`` is: NaN, or a list of them."""
    return [np.nan] * len(item) if isinstance(item, (list, tuple)) else np.nan


def _column(items):
    """Return the items of one value over the steps as an array; ``None`` is NaN."""
    return np.array([np.nan if item is None else item for item in items])
