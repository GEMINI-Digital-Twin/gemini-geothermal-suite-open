"""``compile(plant)``: the entry of the compiler, the executor an ``Engine(compile=True)`` runs."""

from gemini.compiler.cache import graph_cache
from gemini.compiler.executor import GraphExecutor


def compile(plant):
    """Return the executor that runs ``plant`` through its computation graphs."""
    return GraphExecutor(graph_cache())
