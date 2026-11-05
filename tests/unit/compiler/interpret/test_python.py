"""The Python interpreter evaluates the same graph row by row and agrees with NumPy."""

import numpy as np
import pytest

import gemini as gm
from gemini.compiler.cache import GraphCache
from gemini.compiler.interpret.numpy import numpy_result
from gemini.compiler.interpret.python import python_result
from gemini.compiler.run import graph_feeds


def test_python_rows_equal_numpy_rows(line):
    """Values and failing rows are those of the NumPy pass."""
    inlet = gm.Stream(
        m_dot=gm.units.Quantity(np.ones(3), "kg/s"),
        T=gm.units.Quantity(np.full(3, 300.0), "K"),
        p=gm.units.Quantity(np.full(3, 1e5), "Pa"),
        fluid=gm.WATER,
    )
    graph = GraphCache().graph(line, {"fluid_in": gm.WATER})
    feeds = graph_feeds(graph, line, {"fluid_in": inlet}, {"boost": np.array([1.0, -1.0, 2.0])})
    fast, slow = numpy_result(graph, line, feeds, 3), python_result(graph, line, feeds, 3)
    assert slow.failed.tolist() == fast.failed.tolist() == [False, True, False]
    ok = ~fast.failed
    assert slow.result.outputs["rise"][ok] == pytest.approx(fast.result.outputs["rise"][ok])
