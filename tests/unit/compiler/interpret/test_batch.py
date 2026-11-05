"""Trials run as one array pass: each gives the numbers, failed rows and errors it gives alone."""

import numpy as np

import gemini as gm
from gemini.compiler.cache import GraphCache
from gemini.compiler.executor import GraphExecutor
from gemini.compiler.interpret.batch import batch_results
from gemini.compiler.interpret.run_graph import run_graph
from gemini.compiler.run import graph_feeds
from gemini.units import Quantity
from tests.fixtures.engine_plants import Booster
from tests.unit.compiler.test_loops import FULL, ROWS, _circuit, _compiled

LEVELS = [np.array([1.0, 2.0, 3.0]), np.array([4.0, -1.0, 2.0]), np.array([0.5, 0.5, 9.0])]
GAINS = [2.0, 5.0, 7.0]


def _booster(gain):
    module = Booster()
    module.gain = gain
    return module


def _streams(rows=3):
    fields = dict(m_dot=np.full(rows, 1.0), T=np.full(rows, 300.0), p=np.full(rows, 1e5))
    return {
        "fluid_in": gm.Stream(
            **{k: Quantity(v, u) for (k, v), u in zip(fields.items(), "kg/s K Pa".split())},
            fluid=gm.WATER,
        )
    }


def _call(gain, level):
    module = _booster(gain)
    executor = GraphExecutor(gm.compiler.cache.graph_cache())
    return executor, executor.prepare(module, _streams(), {"level": level}, False), 3, {}


def test_trials_with_other_parameters_and_a_failed_row_give_what_each_gives_alone():
    """One array pass over three trials; the second has a row that fails its check."""
    calls = [_call(gain, level) for gain, level in zip(GAINS, LEVELS)]
    executor = calls[0][0]
    together = executor.run_batch([call[1:] for call in calls])
    for call, found in zip(calls, together):
        alone = executor.run(*call[1:])
        assert found.failed.tolist() == alone.failed.tolist()
        for name in ("rise", "power", "inverse"):
            np.testing.assert_array_equal(found.result.outputs[name], alone.result.outputs[name])
        for row in np.flatnonzero(alone.failed):
            assert str(found.error(int(row))) == str(alone.error(int(row)))
    assert together[1].failed.tolist() == [False, True, False]
    assert "gain" not in str(together[0].failed) and not together[0].failed.any()


def test_a_call_that_raises_is_its_own_answer_and_the_others_still_run():
    """A call that the batch cannot take gives its exception; the others give results."""
    calls = [_call(2.0, LEVELS[0]), _call(5.0, LEVELS[0])]
    executor, bad = calls[0][0], calls[1][1]
    broken = (bad[0], bad[1] | {"level": np.array([1.0])}, bad[2], bad[3])
    answers = executor.run_batch([calls[0][1:], (broken, 3, {})])
    assert not answers[0].failed.any()
    assert isinstance(answers[1], Exception) or answers[1].rows == 3


def test_a_loop_of_trials_equals_the_loops_alone():
    """Each row of a loop settles under its own mask; trials of a ring with other pump flows."""
    plants = []
    for flow in (2.0, 3.5):
        plant = _circuit()
        plant.pump.set_params("", {"flow": Quantity(flow, "kg/s")})
        plants.append(plant)
    cache = GraphCache()
    graphs = [_compiled(plant, FULL, cache=cache)[0] for plant in plants]
    assert graphs[0] is graphs[1]
    feeds = [graph_feeds(graphs[0], plant, {}, FULL) for plant in plants]
    together = batch_results(graphs[0], plants[0], feeds, ROWS)
    for plant, feed, found in zip(plants, feeds, together):
        alone = run_graph(graphs[0], feed, ROWS, module=plant)
        np.testing.assert_allclose(
            found.result.children["pump"].inlets.fluid_in.T,
            alone.result.children["pump"].inlets.fluid_in.T,
            rtol=1e-12,
        )
        assert found.failed.tolist() == alone.failed.tolist()
