"""A last-bit change of a calculation moves no number of a plant beyond its loop tolerance.

CPUs and NumPy builds differ in the last bit of ``exp`` and ``log``, so a formula that amplifies
such a bit gives other numbers on another machine. The wrapper below stands in for that difference:
it rounds each tear stream field of a pass one way or the other at random.
"""

import numpy as np
import pytest

import gemini as gm
from gemini.plants._utils import loops
from tests.fixtures.sample_cases import HACKATHON_2026, sample_case

pytestmark = pytest.mark.slow

SHIFT = 1e-16
"""Relative change of a tear field, under one unit in the last place."""

TOLERANCE = 1e-9
"""Largest relative change allowed: the loops close to about this, as ``loops.TOLERANCE`` in K."""

COLUMNS = (
    "peak_boiler.fuel",
    "heat_exchanger.duty",
    "heat_exchanger.log_mean_temperature_difference",
    "heat_pump.power_in",
)


def _frame():
    plant = gm.Plant.from_json(HACKATHON_2026 / "plants/HeatingCoolingPlant.json")
    return gm.simulate(plant, sample_case()).to_frame()


@pytest.mark.parametrize("seed", [1, 2])
def test_a_last_bit_does_not_move_the_split_of_the_heat(monkeypatch, seed):
    """Heat exchanger, heat pump and boiler keep their share on every day of the year."""
    expected = _frame()
    generator = np.random.default_rng(seed)
    exact = loops.wegstein

    def rounded(current, image, previous, previous_image):
        moved = exact(current, image, previous, previous_image)
        return moved * (1 + SHIFT * generator.choice([-1.0, 1.0], size=np.shape(current)))

    monkeypatch.setattr(loops, "wegstein", rounded)
    found = _frame()
    for column in COLUMNS:
        np.testing.assert_allclose(found[column], expected[column], rtol=TOLERANCE, atol=1e-6)
