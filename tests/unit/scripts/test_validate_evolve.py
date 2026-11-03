"""The pure parts of the evolve acceptance harness: fronts, hypervolume, statistics, optima."""

import numpy as np
import pytest

from scripts import validate_evolve


def test_the_hypervolume_of_a_staircase_is_its_area():
    """Three points of a staircase below the reference (4, 4) dominate an area of 1 + 2 + 3."""
    points = [(1.0, 3.0), (2.0, 2.0), (3.0, 1.0)]
    assert validate_evolve.hypervolume_2d(points, (4.0, 4.0)) == pytest.approx(6.0)


def test_a_dominated_or_outside_point_adds_no_hypervolume():
    """A point behind the front or beyond the reference changes nothing."""
    points = [(1.0, 3.0), (2.0, 2.0), (3.0, 1.0), (2.5, 2.5), (5.0, 0.5)]
    assert validate_evolve.hypervolume_2d(points, (4.0, 4.0)) == pytest.approx(6.0)
    assert validate_evolve.hypervolume_2d([], (4.0, 4.0)) == 0.0


def test_the_true_front_has_a_hypervolume_ratio_of_one_and_a_part_of_it_less():
    """The ratio is one for the front itself and below one for one of its points."""
    front = [(1.0, 3.0), (2.0, 2.0), (3.0, 1.0)]
    assert validate_evolve.hypervolume_ratio(front, front) == pytest.approx(1.0)
    assert 0.0 < validate_evolve.hypervolume_ratio([(2.0, 2.0)], front) < 1.0
    assert validate_evolve.hypervolume_ratio([], front) == 0.0


def test_the_nondominated_filter_keeps_the_front_once():
    """A dominated point and a repeat of a front point go."""
    points = [(2.0, 2.0), (1.0, 3.0), (2.5, 2.5), (3.0, 1.0), (2.0, 2.0), (1.0, 4.0)]
    kept = validate_evolve.nondominated(points)
    assert sorted(points[index] for index in kept) == [(1.0, 3.0), (2.0, 2.0), (3.0, 1.0)]
    assert validate_evolve.nondominated([(3.0,), (1.0,), (2.0,)]) == [1]


def test_the_statistics_leave_out_what_is_no_number():
    """Median, quartiles and extremes of the numbers; ``None`` and NaN are not counted."""
    found = validate_evolve.statistics([4.0, None, 1.0, 3.0, float("nan"), 2.0])
    assert found["count"] == 4
    assert (found["min"], found["median"], found["max"]) == (1.0, 2.5, 4.0)
    assert (found["q1"], found["q3"], found["mean"]) == (1.75, 3.25, 2.5)
    assert validate_evolve.statistics([None])["median"] is None


def test_the_relative_gap_is_signed():
    """Above the truth is positive, below it negative."""
    assert validate_evolve.relative_gap(11.0, 10.0) == pytest.approx(0.1)
    assert validate_evolve.relative_gap(9.0, 10.0) == pytest.approx(-0.1)


@pytest.mark.parametrize("name", ["chain", "constrained"])
def test_no_random_design_beats_the_analytic_optimum(name):
    """The optimum of each structure is no worse than any feasible random genes in it."""
    spec = validate_evolve.SYNTHETIC[name]
    rng = np.random.default_rng(0)
    structures = validate_evolve.every_structure(spec)
    for structure in structures[:: max(1, len(structures) // 40)]:
        on = validate_evolve.modules_on(spec, structure)
        chosen = {choice: structure[choice] for choice in spec["choices"]}
        best = spec["optimum"](on, chosen)
        for _ in range(50):
            u = {name: rng.random() for name in spec["ranged"]}
            values, violation = spec["outcome"](on, chosen, u)
            if violation <= 0:
                assert best and best[0][0] <= values[0] + 1e-12


def test_a_loop_with_every_valve_off_is_invalid():
    """Of the 1536 structures of ``chain`` 693 keep a valve on in each of the four loops."""
    spec = validate_evolve.SYNTHETIC["chain"]
    every = validate_evolve.every_structure(spec)
    assert len(every) == 1536
    assert sum(validate_evolve.is_valid(spec, item) for item in every) == 693
