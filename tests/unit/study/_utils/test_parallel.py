"""Trials in worker processes give the numbers and the order of a serial run."""

import multiprocessing
import time

import pytest

import gemini as gm
from gemini.study._utils import parallel, progress
from tests.unit.study.conftest import shallow_case, shallow_plant

PRICE = "case.economics.energy.electricity"
DECLARED = {"economics.energy.electricity": {"kind": "uniform", "min": 90, "max": 150}}


def settings_seen(shared, item):
    """Return the item, the shared value and the settings a worker runs with."""
    return item, shared, gm.runtime.get_processes(), gm.runtime.get_precision()


def test_the_results_come_back_in_the_order_of_the_items():
    """Items run in turn without processes and in workers with them, in the same order."""
    items = list(range(5))
    serial = parallel.mapped(settings_seen, "shared", items)
    assert [item for item, *_ in serial] == items and serial[0][2] == 1
    with gm.runtime.settings(processes=2, precision="float64"):
        workers = parallel.mapped(settings_seen, "shared", items)
    assert [(item, shared) for item, shared, *_ in workers] == [(i, "shared") for i in items]
    assert {(count, precision) for *_, count, precision in workers} == {(1, "float64")}


def test_one_item_runs_here_whatever_the_processes():
    """A single item needs no worker."""
    with gm.runtime.settings(processes=4):
        assert parallel.mapped(settings_seen, "x", [7]) == [(7, "x", 4, "float64")]


@pytest.fixture(scope="module")
def tiny(tmp_path_factory):
    """Return a one day case, its plant and the serial sample, which also warms the graph."""
    case = shallow_case(days=1, folder=tmp_path_factory.mktemp("day"), uncertain=DECLARED)
    plant = shallow_plant()
    return case, plant, gm.study.sample(plant, case, ["peak_heat"], 2, 4)


def test_a_sample_in_workers_equals_the_serial_sample(tiny):
    """The same draws give the same metrics, parameters and summary in processes as in turn."""
    case, plant, serial = tiny
    with gm.runtime.settings(processes=2):
        workers = gm.study.sample(plant, case, ["peak_heat"], 2, 4)
    assert workers.to_dict() == serial.to_dict()


def finishes(shared, item):
    """Finish ``item`` trials, as a worker does, and return the item."""
    for _ in range(item):
        progress.finished()
    time.sleep(0.05)
    return item


def test_the_trials_a_worker_finishes_are_counted_in_the_parent():
    """Three items of 1, 2 and 3 trials in two workers: six calls, counted one by one."""
    calls = []
    with gm.runtime.settings(processes=2), progress.counting(lambda *told: calls.append(told), 6):
        assert parallel.mapped(finishes, None, [1, 2, 3]) == [1, 2, 3]
    assert calls == [(number, 6) for number in range(1, 7)]


def test_cancelling_from_the_parent_stops_the_workers():
    """The exception of the callback is raised and no worker is left running."""

    def cancel(done, total):
        raise gm.errors.Cancelled("stop")

    with gm.runtime.settings(processes=2), progress.counting(cancel, 6):
        with pytest.raises(gm.errors.Cancelled):
            parallel.mapped(finishes, None, [3, 3, 3, 3])
    assert not multiprocessing.active_children()


def test_a_sample_in_workers_is_counted(tiny):
    """The draws finished by the workers are told to the caller."""
    case, plant, serial = tiny
    calls = []
    with gm.runtime.settings(processes=2):
        found = gm.study.sample(
            plant, case, ["peak_heat"], 2, 4, on_progress=lambda *told: calls.append(told)
        )
    assert calls == [(1, 2), (2, 2)] and found.to_dict() == serial.to_dict()
