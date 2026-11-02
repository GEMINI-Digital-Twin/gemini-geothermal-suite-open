"""The graph executor: trace a plant once, then run whole time series of it.

``compile(plant)`` (``compile.py``) returns the ``GraphExecutor`` of ``plant``, which the engine
runs when it is built with ``compile=True``. The executor keeps the traced graphs in the
process-wide ``GraphCache`` (``graph_cache``), which holds a graph by the structure of the
plant: a second executor, a second engine and a copy of the plant with other numeric values trace
nothing again until a guard of the cache changes. A prepared call keeps the plant it was prepared
for, and the graph is evaluated for that plant.

A stepped call of a stateful plant is one ``scan`` over the rows: ``context`` holds the step
length of each row (``dt``) and the state tree the first row starts from (``states``), and the
result holds the state tree after the last row that worked.
"""

from gemini._utils.mappings import get_nested
from gemini.compiler.interpret.run_graph import run_graph
from gemini.compiler.run import graph_feeds
from gemini.engine.executor import Executor
from gemini.engine.rowwise import started
from gemini.errors import ValidationError

_ABSENT = object()


class GraphExecutor(Executor):
    """Run a module as a computation graph: trace once, evaluate over all the rows."""

    def __init__(self, cache):
        """Trace into ``cache``, a ``GraphCache``."""
        self.cache = cache

    def prepare(self, module, streams, inputs, stepped):
        """Return the graph of ``module`` for the fluids of ``streams`` and its feeds."""
        fluids = {port: stream.fluid for port, stream in streams.items()}
        graph = self.cache.graph(module, fluids, stepped)
        return graph, graph_feeds(graph, module, streams, inputs), module, fluids

    def run(self, prepared, rows, context):
        """Return the ``GraphResult`` of the graph over ``rows`` rows."""
        graph, feeds, module, fluids = prepared
        if graph.states:
            start = started(module, fluids, feeds, context.get("states"))
            feeds = feeds | _scan_feeds(graph, context["dt"], start)
        return run_graph(graph, feeds, rows, context, module)


def _scan_feeds(graph, steps, start):
    """Return the step lengths and the first state of every carry of a scan graph."""
    feeds = {"dt": steps}
    start = start or {}
    for leaf, name in graph.states:
        value = get_nested(start, leaf, _ABSENT)
        if value is _ABSENT:
            raise ValidationError(
                f"{graph.module_path}: state {'.'.join(leaf)} has no value; expected it in the "
                "state tree the run starts from",
                code="missing_value",
            )
        feeds[name] = value
    return feeds
