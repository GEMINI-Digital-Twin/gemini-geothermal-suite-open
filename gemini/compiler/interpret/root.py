"""The root-break interpreter: a module that cannot be traced is called for real, row by row."""

from gemini.compiler.interpret.graphresult import GraphResult
from gemini.engine import chunkresult
from gemini.engine.rowwise import call_rows


def root_result(graph, module, feeds, rows, context):
    """Return the ``GraphResult`` of the root-break ``graph`` called on ``module`` row by row."""
    result, failed, error, states = call_rows(
        module, graph.inlet_fluids, feeds, rows, context, graph.stepped
    )
    return GraphResult(
        graph, rows, failed, None if result is None else chunkresult.typed(result), error, states
    )
