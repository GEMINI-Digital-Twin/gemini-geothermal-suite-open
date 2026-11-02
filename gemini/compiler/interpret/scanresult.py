"""``scan_result``: the result of a graph with a ``scan`` node on one backend, with its states."""

import numpy as np

from gemini.compiler.interpret.graphresult import assembled
from gemini.compiler.interpret.interpreter import Interpreter
from gemini.compiler.interpret.rowerror import RowView, row_error
from gemini.compiler.interpret.scan import TIMED
from gemini.compiler.trace.states import state_tree


def scan_result(graph, module, feeds, rows, backend):
    """Return the ``GraphResult`` of a graph with a scan, evaluated on ``backend``."""
    interpreter = Interpreter(graph, backend, module, rows)
    if interpreter.scalar:
        feeds = {name: _plain(graph, name, value) for name, value in feeds.items()}
    values, errors = interpreter.execute(feeds)
    codes = interpreter.reached(errors)
    return scan_trial(graph, values, codes, feeds, rows, 0, 1)


def scan_trial(graph, values, codes, feeds, rows, index, count):
    """Return the ``GraphResult`` of trial ``index`` of ``count`` from the values of a scan graph.

    ``feeds`` are the trial's own, to word its errors; ``values`` and ``codes`` hold the rows of
    all the trials one after the other.
    """
    own = slice(index * rows, (index + 1) * rows)
    total = rows * count
    scan = next(value for value in values.values() if hasattr(value, "snapshots"))

    def column(node):
        value = np.asarray(values[node])
        if value.ndim == len(node.shape) + 1 and value.shape[0] == total:
            return value[own]
        return np.broadcast_to(value, (rows, *node.shape))

    own_codes = None if codes is None else codes[own]

    def error(row):
        where = index * rows + row
        view = RowView(scan.snapshots[where], 0, feeds) if where in scan.snapshots else None
        view = view or RowView(values, where, feeds)
        return row_error(graph.checks[int(own_codes[row]) - 1], view)

    finals = [np.asarray(values[final.node]).reshape(-1) for final in graph.finals]
    states = state_tree(
        [leaf for leaf, _ in graph.states],
        [final[index] if len(final) > 1 else final[0] for final in finals],
    )
    return assembled(graph, rows, own_codes, column, error, states)


def _plain(graph, name, value):
    """Return a feed for the Python backend: a column stays an array, the others are Python."""
    if graph.inputs[name].role in TIMED:
        return value
    return np.asarray(value).tolist()
