"""The root-break interpreter: a module that cannot be traced is called for real, row by row."""

import numpy as np

from gemini.compiler.interpret.graphresult import GraphResult
from gemini.engine import chunkresult
from gemini.engine.rowwise import run_rows, stacked


def root_result(graph, module, feeds, rows, context):
    """Return the ``GraphResult`` of the root-break ``graph`` called on ``module`` row by row."""
    results, errors, states = run_rows(
        module, graph.inlet_fluids, feeds, rows, context, graph.stepped
    )
    failed = np.ones(rows, dtype=bool)
    failed[list(results)] = False
    result = stacked(results, rows)
    return GraphResult(
        graph,
        rows,
        failed,
        None if result is None else chunkresult.typed(result),
        errors.__getitem__,
        states,
    )
