"""The Python interpreter: the same graph, row by row with Python floats and lists."""

import numpy as np

from gemini.compiler.interpret.graphresult import assembled
from gemini.compiler.interpret.interpreter import Interpreter
from gemini.compiler.interpret.rowerror import RowView, row_error
from gemini.engine.rowwise import stack_column
from gemini.ops import kernels


def python_result(graph, module, feeds, rows):
    """Return the ``GraphResult`` of ``graph`` evaluated on Python scalars, one row at a time."""
    interpreter = Interpreter(graph, kernels.get("python"), module)
    row_values, row_codes = [], []
    for row in range(rows):
        values, errors = interpreter.execute(_row_feeds(graph, feeds, rows, row))
        codes = interpreter.reached(errors)
        row_values.append(values)
        row_codes.append(0 if codes is None else int(codes[0]))
    codes = np.array(row_codes, dtype=int)

    def column(node):
        return stack_column([values[node] for values in row_values])

    def error(row):
        return row_error(graph.checks[codes[row] - 1], RowView(row_values[row], 0, feeds))

    return assembled(graph, rows, codes, column, error)


def _row_feeds(graph, feeds, rows, row):
    """Return the Python scalars of one row; a vector parameter is a Python list."""
    values = {}
    for name, value in feeds.items():
        shape = graph.inputs[name].shape
        values[name] = np.broadcast_to(np.asarray(value), (rows, *shape))[row].tolist()
    return values
