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
    scan = next(value for value in values.values() if hasattr(value, "snapshots"))

    def column(node):
        return np.broadcast_to(np.asarray(values[node]), (rows, *node.shape))

    def error(row):
        view = RowView(scan.snapshots[row], 0, feeds) if row in scan.snapshots else None
        view = view or RowView(values, row, feeds)
        return row_error(graph.checks[int(codes[row]) - 1], view)

    states = state_tree(
        [leaf for leaf, _ in graph.states], [np.asarray(values[final.node]).item() for final in graph.finals]
    )
    return assembled(graph, rows, codes, column, error, states)


def _plain(graph, name, value):
    """Return a feed for the Python backend: a column stays an array, the others are Python."""
    if graph.inputs[name].role in TIMED:
        return value
    return np.asarray(value).tolist()
