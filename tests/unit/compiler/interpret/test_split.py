"""``split_of``: the part of a scan body that reads no state runs once, the rest at each row."""

import gemini as gm
from gemini.compiler.cache import GraphCache
from gemini.compiler.interpret.split import split_of
from tests.unit.compiler.conftest import Tank


def _scan_body(graph):
    return next(node for node in graph.nodes if node.kind == "scan").attributes["body"]


def test_a_node_that_reads_a_carry_is_stepwise_and_the_others_run_once():
    """Every node of the body is on one side; the carries are on the row side."""
    graph = GraphCache().graph(Tank(), {"fluid_in": gm.WATER}, stepped=True)
    body = _scan_body(graph)
    plan = split_of(graph, body, True)
    assert set(plan.once) | set(plan.stepwise) == set(body.nodes)
    assert not set(plan.once) & set(plan.stepwise)
    assert set(body.carries) <= plan.dependent and not set(plan.once) & plan.dependent


def test_without_a_partition_every_node_runs_at_each_row():
    """The Python backend does not split: nothing runs once."""
    graph = GraphCache().graph(Tank(), {"fluid_in": gm.WATER}, stepped=True)
    body = _scan_body(graph)
    plan = split_of(graph, body, False)
    assert plan.once == () and plan.stepwise == tuple(body.nodes) and plan.frontier == ()
