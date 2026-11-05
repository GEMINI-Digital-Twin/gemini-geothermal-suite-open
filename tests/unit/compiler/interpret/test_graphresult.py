"""A graph result is a chunk result that also names the graph and reads its outputs."""

import numpy as np

import gemini as gm
from gemini.compiler.cache import GraphCache
from gemini.compiler.interpret.graphresult import GraphResult
from gemini.compiler.interpret.run_graph import run_graph
from gemini.compiler.run import graph_feeds
from gemini.engine.chunkresult import ChunkResult


def test_a_graph_result_gives_the_array_of_a_named_output(line):
    """``output`` converts the node behind the name to an array over the rows."""
    inlet = gm.Stream(
        m_dot=gm.units.Quantity(np.ones(2), "kg/s"),
        T=gm.units.Quantity(np.full(2, 300.0), "K"),
        p=gm.units.Quantity(np.full(2, 1e5), "Pa"),
        fluid=gm.WATER,
    )
    graph = GraphCache().graph(line, {"fluid_in": gm.WATER})
    feeds = graph_feeds(graph, line, {"fluid_in": inlet}, {"boost": np.array([1.0, 2.0])})
    result = run_graph(graph, feeds, 2, module=line)
    assert isinstance(result, GraphResult) and isinstance(result, ChunkResult)
    assert result.graph is graph
    assert np.asarray(result.output("outputs.rise")).shape == (2,)
