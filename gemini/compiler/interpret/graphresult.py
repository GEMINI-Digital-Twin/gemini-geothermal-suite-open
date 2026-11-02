"""``GraphResult``: the result of evaluating a graph over the rows of a chunk.

A ``GraphResult`` is a ``gemini.engine.chunkresult.ChunkResult`` that also keeps its ``graph``.
Each interpreter of this folder (``numpy``, ``python``, ``root``) builds one through ``assembled``.
"""

import numpy as np

from gemini.compiler.ir import Node
from gemini.compiler.trace.proxy import Proxy
from gemini.engine import chunkresult


class GraphResult(chunkresult.ChunkResult):
    """The result of evaluating a graph over ``rows`` rows."""

    def __init__(self, graph, rows, failed, result, errors, states=None, convert=None):
        """Keep the mapped ``result``, the ``failed`` mask and ``errors``, a function of a row."""
        super().__init__(rows, failed, result, errors, states, graph.stepped, graph.breaks)
        self.graph = graph
        self._convert = convert

    def output(self, name):
        """Return the array of the graph output ``outputs.<name>`` or ``outlets.<port>.<field>``."""
        return self._convert(self.graph.outputs[name])


def assembled(graph, rows, codes, column, error):
    """Return the ``GraphResult`` of per-node ``column`` values and reached ``codes``."""
    failed = np.zeros(rows, dtype=bool) if codes is None else codes != 0
    convert = chunkresult.converter(rows, (Node, Proxy), lambda value: column(_node(value)))
    result = None if graph.result is None else chunkresult.typed(graph.result.mapped(convert))
    return GraphResult(graph, rows, failed, result, error, convert=convert)


def _node(value):
    return value.node if isinstance(value, Proxy) else value
