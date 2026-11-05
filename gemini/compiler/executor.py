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
from gemini.compiler.interpret.batch import batch_results, batch_size, batchable
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
        feeds = _with_scan_feeds(graph, feeds, module, fluids, context)
        return run_graph(graph, feeds, rows, context, module)

    def batchable(self, prepared):
        """Return whether the graph has nothing that runs a module for real (a break node)."""
        return batchable(prepared[0])

    def run_batch(self, calls):
        """Return the result or the error of each call, the calls of one graph as one array pass.

        The calls that share a graph and a row count are evaluated together, the rows of each
        trial one after the other, and give what each gives alone. A batch that raises runs one
        call at a time, so a call that fails gives its own exception only.
        """
        answers = [None] * len(calls)
        groups = {}
        for index, (prepared, rows, _) in enumerate(calls):
            groups.setdefault((id(prepared[0]), rows), []).append(index)
        for members in groups.values():
            rows = calls[members[0]][1]
            size = batch_size(rows)
            for first in range(0, len(members), size):
                self._answer(calls, members[first : first + size], answers)
        return answers

    def _answer(self, calls, members, answers):
        """Fill ``answers`` for ``members``: together when there are several, else alone."""
        if len(members) > 1:
            try:
                self._together(calls, members, answers)
                return
            except Exception:
                pass
        for index in members:
            try:
                answers[index] = self.run(*calls[index])
            except Exception as error:
                answers[index] = error

    def _together(self, calls, members, answers):
        """Evaluate the calls of ``members`` as one array pass and keep each one's result."""
        prepared, rows, _ = calls[members[0]]
        graph, _, module, _ = prepared
        feeds = [
            _with_scan_feeds(graph, calls[i][0][1], module, calls[i][0][3], calls[i][2])
            for i in members
        ]
        for index, result in zip(members, batch_results(graph, module, feeds, rows)):
            answers[index] = result


def _with_scan_feeds(graph, feeds, module, fluids, context):
    """Return ``feeds`` with the step lengths and first states of a scan graph."""
    if not graph.states:
        return feeds
    start = started(module, fluids, feeds, context.get("states"))
    return feeds | _scan_feeds(graph, context["dt"], start)


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
