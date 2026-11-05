"""CPU-time measure behind the one-second budget of a fast-tier test call, and its calibration.

The budget is one second of CPU on a machine at reference speed. CPU time is steadier than
elapsed time but still grows when the machine is busy (threads share caches and land on slower
cores), so a test that needs 0.4 s alone can read 1.0 s inside a full parallel run. The budget is
therefore scaled by how slow the machine is right now, measured in the same worker: a fixed CPU
workload (``reference_work``) is timed, and its time over ``REFERENCE_S`` is the slowdown. The
limit is never raised for the code: a test that is slow on an idle machine still fails.
"""

import math
import statistics
from contextlib import contextmanager
from os import times
from time import monotonic, process_time

import numpy as np

BUDGET_S = 1.0
REFERENCE_S = 0.027
"""CPU seconds of ``reference_work`` on a machine at reference speed (idle, one process)."""
MAX_SLOWDOWN = 4.0
"""The largest slowdown the budget follows; a machine slower than this fails the test."""
RUNS = 3
"""Timings of the workload that one reading takes the median of."""
PERIOD_S = 5.0
"""Elapsed seconds after which a worker reads the machine speed again."""
WINDOW_S = 30.0
"""Elapsed seconds a reading still counts for: the machine was that slow during a test."""


class CpuSeconds:
    """CPU seconds of the process consumed inside a ``measure_cpu`` block."""

    seconds = 0.0


def cpu_seconds():
    """Return the CPU seconds of this process and of its waited-for children."""
    clock = times()
    return process_time() + clock.children_user + clock.children_system


@contextmanager
def measure_cpu(clock=cpu_seconds):
    """Measure the CPU time of the whole process around a block, not its elapsed time.

    ``process_time`` adds the user and system time of every thread of the process, so work a test
    hands to its own threads or to the NumPy thread pool still counts, while time spent waiting
    (sleeping, descheduled by a busy machine, blocked on a lock) does not. ``thread_time`` would
    miss that delegated work and let a heavy test pass. The block must be one test call, which a
    pytest-xdist worker runs alone in its process. The user and system time of child processes
    the test started and waited for (a process pool of parallel trials) is added from
    ``os.times``, so work handed to other processes counts too.
    """
    result = CpuSeconds()
    started = clock()
    try:
        yield result
    finally:
        result.seconds = clock() - started


def reference_work():
    """Run the fixed CPU workload the machine speed is read from: Python loops and NumPy.

    The mix is that of the tests: scalar arithmetic in Python, small array operations and a
    dense product. It depends on nothing but the machine.
    """
    total = 0.0
    for index in range(1, 100000):
        total += math.sqrt(index) * math.sin(index) / (1.0 + index % 7)
    grid = np.linspace(0.0, 1.0, 160)
    matrix = np.exp(-np.subtract.outer(grid, grid) ** 2)
    for _ in range(12):
        matrix = matrix @ matrix
        matrix /= np.abs(matrix).max()
    return total + float(matrix.sum())


def exceeds_budget(cpu_time, slowdown=1.0):
    """Return whether ``cpu_time`` is over the budget of a machine ``slowdown`` times slower."""
    return cpu_time > BUDGET_S * slowdown


class MachineSpeed:
    """How slow the machine is now, read from the time of ``reference_work`` in this process.

    ``slowdown`` is the median time of a few runs of the workload over ``REFERENCE_S``, at least 1
    (a faster machine keeps the one-second rule) and at most ``MAX_SLOWDOWN``. ``sample`` takes a
    reading when none is recent, so a test that has just run can be judged by the slowest the
    machine was while it ran (``WINDOW_S``). All three clocks and the workload are arguments, so a
    test can drive them with fake ones.
    """

    def __init__(
        self,
        work=reference_work,
        cpu=cpu_seconds,
        wall=monotonic,
        reference=REFERENCE_S,
        runs=RUNS,
    ):
        """Set the workload, the CPU clock, the elapsed clock and the reference time."""
        self.work, self.cpu, self.wall = work, cpu, wall
        self.reference, self.runs = reference, runs
        self.readings = []

    def measure(self):
        """Read the slowdown now, remember it with the time, and return it."""
        durations = []
        for _ in range(self.runs):
            with measure_cpu(self.cpu) as spent:
                self.work()
            durations.append(spent.seconds)
        slowdown = statistics.median(durations) / self.reference
        slowdown = min(max(slowdown, 1.0), MAX_SLOWDOWN)
        self.readings.append((self.wall(), slowdown))
        return slowdown

    def sample(self):
        """Take a reading when the last one is older than ``PERIOD_S``."""
        if not self.readings or self.wall() - self.readings[-1][0] >= PERIOD_S:
            self.measure()

    def slowdown(self):
        """Return the largest of a reading taken now and those of the last ``WINDOW_S``."""
        now = self.measure()
        horizon = self.wall() - WINDOW_S
        return max([now] + [value for when, value in self.readings if when >= horizon])


MACHINE_SPEED = MachineSpeed()
"""The speed of the machine as this process sees it; each xdist worker has its own."""
