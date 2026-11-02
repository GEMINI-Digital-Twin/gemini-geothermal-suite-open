"""``scan_result``: the states after the last row and the error of a failed row of a scan."""

import numpy as np

import gemini as gm
from gemini.compiler.cache import GraphCache
from gemini.compiler.interpret.scanresult import scan_result
from tests.unit.compiler.conftest import Tank


def test_a_scan_result_holds_the_state_tree_after_the_last_row():
    """The final state of each carry is in the tree the result gives back."""
    module = Tank()
    graph = GraphCache().graph(module, {"fluid_in": gm.WATER}, stepped=True)
    feeds = {name: np.full(3, 1.0) for name in graph.inputs}
    feeds["dt"] = np.full(3, 60.0)
    feeds["fluid_in.p"] = np.full(3, 1e5)
    feeds["fluid_in.T"] = np.full(3, 300.0)
    feeds["state.level"] = 1.0
    evaluation = scan_result(graph, module, feeds, 3, "numpy")
    assert set(evaluation.states) == {"level"} and not evaluation.failed.any()
