"""The CPU time of a daily year of the sample plant, eager: a large regression fails it."""

import pytest

import gemini as gm
from tests.cpu_budget import MACHINE_SPEED, measure_cpu
from tests.fixtures.sample_cases import SAMPLE_PLANT, sample_case, template_plant

pytestmark = pytest.mark.e2e

EAGER_YEAR_S = 0.34
"""Median of 5 eager runs after a warm-up of ``gm.simulate`` on the daily year (365 rows) of the
sample ``HeatingCoolingPlant``, on an Intel Core i5-8257U (8 threads), at a load average of 15."""
BUDGET_S = 3 * EAGER_YEAR_S
CALLS = 3


def _year(case):
    plant = template_plant(SAMPLE_PLANT)
    with measure_cpu() as cpu:
        gm.simulate(plant, case, compile=False)
    return cpu.seconds


def test_a_daily_year_of_the_sample_plant_runs_within_three_times_its_measured_time():
    """The best of three calls stays within ``BUDGET_S`` of CPU time, scaled by the machine speed.

    Elapsed time grows with the load of the machine without any extra work, so the call is timed
    in CPU seconds, and a call over ``BUDGET_S`` is judged against the budget times how slow the
    machine is now (``tests/cpu_budget.py``).
    """
    case = sample_case()
    _year(case)
    best = min(_year(case) for _ in range(CALLS))
    if best >= BUDGET_S:
        allowed = BUDGET_S * MACHINE_SPEED.slowdown()
        assert best < allowed, f"{best:.2f} s of CPU against {allowed:.2f} s"
