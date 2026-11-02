"""Trials of a study share one plant and run side by side: each gives what it gives alone."""

from copy import deepcopy

import pytest

import gemini as gm
from gemini.engine.apply import applied_in_place
from gemini.engine.simulate import simulate
from gemini.study._utils import parallel, trial
from gemini.study._utils.shared import Shared
from gemini.study._utils.target import is_case_name, with_case_values
from tests.unit.engine.schedule.test_schedule import FULL, case_of, demand, plant_of_two
from tests.unit.engine.test_failed_steps import COLD

GRADIENT = "case.site.ground.gradient"
CAPACITY = "boiler.capacity"


def _case():
    return case_of(demand(FULL, 0.5 * FULL, FULL))


def _alone(plant, case, values, names):
    """Return the outcome of one trial as a trial always was: its own copy, run by ``simulate``."""
    copy = deepcopy(plant)
    for name, number in values.items():
        if not is_case_name(name):
            path, _, parameter = name.rpartition(".")
            copy._set_si_params(path, {parameter: number})
    changed = with_case_values(case, {k: v for k, v in values.items() if is_case_name(k)})
    copy = applied_in_place(copy, changed)
    results = simulate(copy, changed)
    metrics = {name: trial.metric(copy, changed, results, name) for name in names}
    return (metrics, *trial.judged(copy, changed, results))


def _numbers(outcome):
    metrics, reason, violation = outcome
    return {k: (v.value, v.reason) for k, v in metrics.items()}, reason, violation


def _equal(first, second):
    """Return whether two outcomes agree: the same reasons, the numbers within 1e-9."""
    (one, why, big), (two, other, great) = _numbers(first), _numbers(second)
    close = all(
        (a is None and b is None) or a == pytest.approx(b, rel=1e-9)
        for k in one
        for a, b in [(one[k][0], two[k][0])]
    )
    return close and one.keys() == two.keys() and why == other and big == pytest.approx(great)


VALUED = [{GRADIENT: 0.03, CAPACITY: 2e7}, {GRADIENT: COLD}]


def test_trials_run_together_give_what_each_gives_alone():
    """A parameter and a number of the case; the cold reservoir has failed steps, the other none."""
    plant, case, names = plant_of_two(), _case(), ["lcts", "peak_heat"]
    together = trial.run_trials(Shared(plant), case, None, VALUED, names, True)
    for values, found in zip(VALUED, together):
        assert _equal(found, _alone(plant, case, values, names))
    reasons = [outcome[1] for outcome in together]
    assert reasons[0] is None and reasons[1]["kind"] == "failed_step"
    assert together[1][2] > 0 and together[0][2] == 0.0


def test_a_trial_alone_equals_the_same_trial_in_a_batch():
    """The order and the company of a trial change nothing in its numbers."""
    plant, case, names = plant_of_two(), _case(), ["peak_heat"]
    shared = Shared(plant)
    together = trial.run_trials(shared, case, None, VALUED, names, False)
    for values, found in zip(VALUED, together):
        assert trial.run_trials(shared, case, None, [values], names, False) == [found]


def test_a_plant_with_a_graph_break_runs_each_trial_alone_with_equal_numbers(monkeypatch):
    """A pre-hook makes its module a break: no array pass, the trials run one at a time."""
    plant, case, names = plant_of_two(), _case(), ["peak_heat"]
    plant.get_submodule("hx").register_forward_pre_hook(lambda module, inputs, inlets, state: None)
    sizes = []
    import gemini.compiler.executor as executor

    real = executor.batch_results
    monkeypatch.setattr(executor, "batch_results", lambda *a: sizes.append(len(a[2])) or real(*a))
    together = trial.run_trials(Shared(plant), case, None, VALUED, names, True)
    assert sizes == []
    for values, found in zip(VALUED, together):
        assert _equal(found, _alone(plant, case, values, names))


def test_the_split_of_a_batch_over_processes_keeps_the_order(monkeypatch):
    """The parts are consecutive, none empty, and join back in the order of the items."""
    with gm.runtime.settings(processes=3):
        assert [len(part) for part in parallel.split(list(range(7)))] == [3, 2, 2]
        assert parallel.split([1, 2]) == [[1], [2]]
    assert parallel.split(list(range(4))) == [[0, 1, 2, 3]]
    assert parallel.split([]) == [[]]
    with gm.runtime.settings(processes=2):
        assert parallel.mapped_batches(_doubled, "x", [1, 2, 3, 4, 5]) == [2, 4, 6, 8, 10]


def _doubled(shared, part):
    return [2 * item for item in part]
