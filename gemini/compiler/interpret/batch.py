"""Several runs of one graph as one array pass: the trials of a study, each with its own values.

``batch_results(graph, module, feeds_list, rows)`` evaluates the graph once over ``trials * rows``
rows: trial ``i`` owns the rows ``[i * rows, (i + 1) * rows)``. Every graph input becomes a column
over those rows, the same value in every row of a trial: a parameter is the batch axis of the
vector parameters too (``(trials * rows, n)``, which ``getitem`` indexes on the last axis), and an
input that all the trials share stays as it is, so nothing is copied for it. The rows of the graph
do not depend on each other (a loop iterates every row under its own mask and a scan carries one
state for each trial), so the rows of a trial are those of a run of that trial alone.
The result is one ``GraphResult`` for each trial, whose errors are worded with that trial's feeds.
"""

import numpy as np

from gemini import runtime
from gemini.compiler.interpret.graphresult import assembled
from gemini.compiler.interpret.interpreter import Interpreter
from gemini.compiler.interpret.rowerror import RowView, row_error
from gemini.compiler.interpret.scan import TIMED
from gemini.compiler.interpret.scanresult import scan_trial
from gemini.ops import kernels

MAX_ROWS = 40000
"""The most rows one array pass holds, for the memory of its values; never a change of results."""


def batchable(graph):
    """Return whether the trials of ``graph`` can run as one array pass on the current backend."""
    return not graph.root_break and not graph.breaks and kernels.forced_name() != "python"


def batch_size(rows):
    """Return how many trials of ``rows`` rows one array pass holds."""
    return max(1, MAX_ROWS // max(rows, 1))


def batch_results(graph, module, feeds_list, rows):
    """Return the ``GraphResult`` of every trial of ``feeds_list``, from one array pass.

    Each item of ``feeds_list`` is the feeds of one trial, the step lengths and first states of a
    scan graph included.
    """
    count = len(feeds_list)
    feeds = stacked(graph, feeds_list, rows)
    interpreter = Interpreter(graph, kernels.get("numpy"), module, rows, count)
    with runtime.settings(backend="numpy"), np.errstate(all="ignore"):
        values, errors = interpreter.execute(feeds)
    codes = interpreter.reached(errors)
    make = scan_trial if graph.states else _trial_result
    return [
        make(graph, values, codes, feeds_list[index], rows, index, count) for index in range(count)
    ]


def stacked(graph, feeds_list, rows):
    """Return the feeds of the batch: each input as one column over the rows of all the trials."""
    feeds = {}
    for name in feeds_list[0]:
        arrays = [np.asarray(feeds_item[name]) for feeds_item in feeds_list]
        node = graph.inputs.get(name)
        timed = node is not None and node.role in TIMED
        shared = all(_same(arrays[0], other) for other in arrays[1:])
        if shared and not (timed and arrays[0].ndim):
            feeds[name] = feeds_list[0][name]
        elif node is not None and node.role == "state":
            feeds[name] = np.array([float(array) for array in arrays])
        else:
            feeds[name] = np.concatenate([_column(array, rows, timed) for array in arrays])
    return feeds


def _same(first, other):
    """Return whether two feeds are the same array or number."""
    return first is other or (first.shape == other.shape and np.array_equal(first, other))


def _column(array, rows, timed):
    """Return one trial's feed as rows: a column as it is, a parameter repeated over the rows."""
    if timed and array.ndim and len(array) == rows:
        return array
    return np.broadcast_to(array, (rows, *array.shape))


def _trial_result(graph, values, codes, feeds, rows, index, count):
    """Return the ``GraphResult`` of trial ``index`` from the values of the whole batch."""
    own = slice(index * rows, (index + 1) * rows)
    total = rows * count

    def column(node):
        value = np.asarray(values[node])
        if value.ndim == len(node.shape) + 1 and value.shape[0] == total:
            return value[own]
        return np.broadcast_to(value, (rows, *node.shape))

    own_codes = None if codes is None else codes[own]

    def error(row):
        view = RowView(values, index * rows + row, feeds)
        return row_error(graph.checks[int(own_codes[row]) - 1], view)

    return assembled(graph, rows, own_codes, column, error)
