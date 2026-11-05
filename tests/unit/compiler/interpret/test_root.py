"""A root-break graph calls the real module on each row."""

import numpy as np

import gemini as gm
from gemini.compiler.interpret.root import root_result
from gemini.compiler.run import graph_feeds
from gemini.compiler.trace.rootbreak import root_break_graph
from tests.unit.compiler.conftest import Chain, Opaque


def test_a_root_break_gives_the_results_of_direct_calls():
    """The rows are real result trees, so the outputs equal a direct call."""
    chain = Chain(Opaque())
    inlet = gm.Stream(
        m_dot=gm.units.Quantity(np.arange(1.0, 4.0), "kg/s"),
        T=gm.units.Quantity(np.full(3, 300.0), "K"),
        p=gm.units.Quantity(np.full(3, 1e5), "Pa"),
        fluid=gm.WATER,
    )
    graph = root_break_graph(chain, {"fluid_in": gm.WATER}, False, "not traceable")
    feeds = graph_feeds(graph, chain, {"fluid_in": inlet}, {"drive": 1.0})
    result = root_result(graph, chain, feeds, 3, {})
    assert result.failed.tolist() == [False] * 3 and result.breaks == graph.breaks
