"""The fast-tier budget measures CPU time, so waiting never fails and heavy work always does."""

import multiprocessing
import threading
import time

import pytest

from tests.cpu_budget import (
    BUDGET_S,
    MAX_SLOWDOWN,
    PERIOD_S,
    REFERENCE_S,
    WINDOW_S,
    MachineSpeed,
    exceeds_budget,
    measure_cpu,
)


def burn(seconds):
    """Spin on the calling thread until its CPU clock has advanced by ``seconds``."""
    deadline = time.thread_time() + seconds
    while time.thread_time() < deadline:
        pass


def test_sleeping_longer_than_the_budget_uses_no_cpu():
    """A test that only waits for more than a second of elapsed time stays within budget."""
    started = time.perf_counter()
    with measure_cpu() as cpu:
        time.sleep(BUDGET_S + 0.05)
    assert time.perf_counter() - started > BUDGET_S
    assert not exceeds_budget(cpu.seconds)


def test_burning_cpu_is_measured():
    """CPU work is counted: a quarter second burned reads as at least a quarter second."""
    with measure_cpu() as cpu:
        burn(0.25)
    assert 0.25 <= cpu.seconds < 0.5


def test_work_in_another_thread_is_counted():
    """Process CPU time includes threads, so delegating the work does not hide it."""
    worker = threading.Thread(target=burn, args=(0.25,))
    with measure_cpu() as cpu:
        worker.start()
        worker.join()
    assert cpu.seconds >= 0.25


def test_budget_boundary_is_one_second_of_cpu():
    """The budget is exactly one second: equal passes, over fails."""
    assert BUDGET_S == 1.0
    assert not exceeds_budget(1.0)
    assert exceeds_budget(1.01)


def test_work_in_a_child_process_is_counted():
    """CPU time of a child process the test waited for is counted: a pool hides nothing."""
    child = multiprocessing.get_context("spawn").Process(target=burn, args=(0.25,))
    with measure_cpu() as cpu:
        child.start()
        child.join()
    assert cpu.seconds >= 0.25


class FakeMachine:
    """Fake CPU and elapsed clocks; the workload advances both by the cost the test sets next."""

    def __init__(self):
        """Start both clocks at zero with a workload that costs the reference time."""
        self.cpu_time, self.wall_time, self.costs = 0.0, 0.0, [REFERENCE_S]

    def cpu(self):
        """Return the CPU clock."""
        return self.cpu_time

    def wall(self):
        """Return the elapsed clock."""
        return self.wall_time

    def work(self):
        """Run the workload: spend the next cost (the last one repeats)."""
        cost = self.costs.pop(0) if len(self.costs) > 1 else self.costs[0]
        self.cpu_time += cost
        self.wall_time += cost

    def speed(self):
        """Return a ``MachineSpeed`` driven by these clocks."""
        return MachineSpeed(work=self.work, cpu=self.cpu, wall=self.wall)


def test_a_machine_at_reference_speed_keeps_the_one_second_rule():
    """The slowdown is 1, so equal passes and over fails, exactly as without calibration."""
    machine = FakeMachine()
    assert machine.speed().slowdown() == pytest.approx(1.0)
    assert not exceeds_budget(1.0, 1.0) and exceeds_budget(1.01, 1.0)


def test_a_machine_twice_as_slow_gets_twice_the_budget():
    """The same code reads twice the CPU seconds, and the budget follows the machine."""
    machine = FakeMachine()
    machine.costs = [2 * REFERENCE_S]
    slowdown = machine.speed().slowdown()
    assert slowdown == pytest.approx(2.0)
    assert not exceeds_budget(1.9, slowdown) and exceeds_budget(2.1, slowdown)


def test_a_faster_machine_never_gets_a_smaller_budget():
    """Half the reference time still allows one second, not half a second."""
    machine = FakeMachine()
    machine.costs = [REFERENCE_S / 2]
    assert machine.speed().slowdown() == pytest.approx(1.0)


def test_the_budget_follows_the_machine_only_up_to_a_limit():
    """A machine far slower than the reference fails the test: the budget is capped."""
    machine = FakeMachine()
    machine.costs = [100 * REFERENCE_S]
    slowdown = machine.speed().slowdown()
    assert slowdown == MAX_SLOWDOWN and exceeds_budget(5.0, slowdown)


def test_one_disturbed_run_does_not_move_the_reading():
    """The median of the runs ignores a single outlier."""
    machine = FakeMachine()
    machine.costs = [REFERENCE_S, 9 * REFERENCE_S, REFERENCE_S]
    assert machine.speed().measure() == pytest.approx(1.0)


def test_code_twice_as_slow_on_an_idle_machine_still_fails():
    """Scaling is by the machine: a test at 2 s on a machine at reference speed is over budget."""
    machine = FakeMachine()
    assert exceeds_budget(2.0, machine.speed().slowdown())


def test_a_reading_is_taken_once_per_period_and_counts_for_the_window():
    """``sample`` skips a recent reading; a slow spell still counts after the machine recovers."""
    machine = FakeMachine()
    speed = machine.speed()
    machine.costs = [3 * REFERENCE_S]
    speed.sample()
    assert len(speed.readings) == 1
    speed.sample()
    assert len(speed.readings) == 1
    machine.costs = [REFERENCE_S]
    machine.wall_time += PERIOD_S
    speed.sample()
    assert len(speed.readings) == 2
    assert speed.slowdown() == pytest.approx(3.0)
    machine.wall_time += WINDOW_S
    assert speed.slowdown() == pytest.approx(1.0)
