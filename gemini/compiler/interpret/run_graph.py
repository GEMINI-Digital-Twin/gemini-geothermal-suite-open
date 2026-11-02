"""``run_graph``: one evaluation of a graph over the rows of a chunk, on either backend.

``run_graph(graph, feeds, rows, context, module=...)`` is used by ``gemini.compiler.run`` and the
engine. The backend is the one of ``gm.runtime.settings(backend=...)``, NumPy by default: NumPy
evaluates the graph in one pass over arrays of ``rows`` (``numpy.py``); Python evaluates the same
graph row by row with Python floats and lists and stacks the nodes into the same arrays
(``python.py``). Both go through the same ``Interpreter`` and the same reached-code computation
(``Interpreter.reached``). A root break graph calls the real ``module`` row by row (see
``rootbreak`` and ``root.py``), and so does a break node for its own module below ``module``: the
graph holds no module, so ``module`` is the root the graph is evaluated for, any module of the
structure it was traced from. ``feeds`` maps graph inputs to arrays over the rows or scalars,
which broadcast; ``context`` may hold ``dt`` and ``states`` for a stepped root break.
"""

import numpy as np

from gemini.compiler.interpret.numpy import numpy_result
from gemini.compiler.interpret.python import python_result
from gemini.compiler.interpret.root import root_result
from gemini.ops import kernels


def run_graph(graph, feeds, rows, context=None, module=None):
    """Evaluate ``graph`` on ``feeds`` over ``rows`` rows and return a ``GraphResult``.

    ``module`` is the root module of the call; a graph with a break node or a root break needs
    it, a graph of a plain function does not.
    """
    context = context or {}
    with np.errstate(all="ignore"):
        if graph.root_break:
            return root_result(graph, module, feeds, rows, context)
        if kernels.forced_name() == "python":
            return python_result(graph, module, feeds, rows)
        return numpy_result(graph, module, feeds, rows)
