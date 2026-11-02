"""``compile`` gives the executor of a plant and shares the graph cache of the process."""

import gemini as gm
from gemini.compiler.cache import graph_cache
from gemini.compiler.compile import compile
from gemini.compiler.executor import GraphExecutor
from tests.fixtures.engine_plants import Booster


def test_compile_gives_a_graph_executor_on_the_process_cache():
    """The executor keeps the one ``GraphCache`` of the process."""
    executor = compile(Booster())
    assert isinstance(executor, GraphExecutor) and executor.cache is graph_cache()
    assert gm.compiler.compile is compile
