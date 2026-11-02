"""The graph executor: trace a plant once, then evaluate whole time series of it.

``compile(plant)`` (``compile.py``) returns the ``GraphExecutor`` of ``plant``, which the engine
runs when it is built with ``compile=True``. The executor keeps the traced graphs in the
process-wide ``GraphCache`` (``graph_cache``), which holds a graph by the structure of the
plant: a second executor, a second engine and a copy of the plant with other numeric values trace
nothing again until a guard of the cache changes. A prepared call keeps the plant it was prepared
for, and the graph is evaluated for that plant.
"""

from gemini.compiler.interpret.run_graph import run_graph
from gemini.compiler.run import graph_feeds
from gemini.engine.executor import Executor


class GraphExecutor(Executor):
    """Evaluate a module as a computation graph: trace once, evaluate over all the rows."""

    def __init__(self, cache):
        """Trace into ``cache``, a ``GraphCache``."""
        self.cache = cache

    def prepare(self, module, streams, inputs, stepped):
        """Return the graph of ``module`` for the fluids of ``streams`` and its feeds."""
        fluids = {port: stream.fluid for port, stream in streams.items()}
        graph = self.cache.graph(module, fluids, stepped)
        return graph, graph_feeds(graph, module, streams, inputs), module

    def evaluate(self, prepared, rows, context):
        """Return the ``GraphResult`` of the graph over ``rows`` rows."""
        graph, feeds, module = prepared
        return run_graph(graph, feeds, rows, context, module)
