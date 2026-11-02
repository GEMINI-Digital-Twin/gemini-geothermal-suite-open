"""The NumPy interpreter evaluates a graph in one pass over the rows."""

import numpy as np

import gemini as gm
from gemini.compiler.cache import GraphCache
from gemini.compiler.interpret.graphresult import GraphResult
from gemini.compiler.interpret.numpy import numpy_result
from gemini.compiler.run import graph_feeds


def test_a_graph_is_evaluated_over_all_rows_at_once(line):
    """The result holds one value per row and marks the failing row with its own exception."""
    inlet = gm.Stream(
        m_dot=gm.units.Quantity(np.ones(3), "kg/s"),
        T=gm.units.Quantity(np.full(3, 300.0), "K"),
        p=gm.units.Quantity(np.full(3, 1e5), "Pa"),
        fluid=gm.WATER,
    )
    graph = GraphCache().graph(line, {"fluid_in": gm.WATER})
    feeds = graph_feeds(graph, line, {"fluid_in": inlet}, {"boost": np.array([1.0, -1.0, 2.0])})
    result = numpy_result(graph, line, feeds, 3)
    assert isinstance(result, GraphResult) and result.failed.tolist() == [False, True, False]
    assert result.result.outputs["rise"].shape == (3,)
