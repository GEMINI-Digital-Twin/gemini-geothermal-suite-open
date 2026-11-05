"""The NumPy interpreter: the graph evaluated in one pass over arrays of ``rows``."""

import numpy as np

from gemini.compiler.interpret.graphresult import assembled
from gemini.compiler.interpret.interpreter import Interpreter
from gemini.compiler.interpret.rowerror import RowView, row_error
from gemini.compiler.interpret.scanresult import scan_result
from gemini.ops import kernels


def numpy_result(graph, module, feeds, rows):
    """Return the ``GraphResult`` of ``graph`` evaluated on NumPy over ``rows`` rows."""
    if graph.states:
        return scan_result(graph, module, feeds, rows, kernels.get("numpy"))
    interpreter = Interpreter(graph, kernels.get("numpy"), module)
    values, errors = interpreter.execute(feeds)
    codes = interpreter.reached(errors)

    def column(node):
        shape = (rows, *node.shape)
        return np.broadcast_to(np.asarray(values[node]), shape)

    def error(row):
        return row_error(graph.checks[int(codes[row]) - 1], RowView(values, row, feeds))

    return assembled(graph, rows, codes, column, error)
