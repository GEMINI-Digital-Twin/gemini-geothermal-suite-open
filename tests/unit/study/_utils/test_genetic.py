"""The parts of a genetic search: ranking, parent choice, children and the cache key."""

import numpy as np
import pytest

from gemini.study._utils.genetic import (
    Gene,
    key,
    offspring,
    order,
    random_genomes,
    rank,
    tournament,
)

GENES = (
    Gene("rate", "continuous", 10.0, 20.0),
    Gene("wells", "integer", 1.0, 6.0),
    Gene("fluid", "categorical", 0.0, 2.0),
)
SETTINGS = {"crossover": 0.9, "eta_crossover": 15.0, "eta_mutation": 20.0, "mutation": 0.3}


def _children(seed, count=50):
    """Return the children of two random populations drawn from one seed."""
    rng = np.random.default_rng(seed)
    a = random_genomes(GENES, count, rng)
    b = random_genomes(GENES, count, rng)
    return offspring(a, b, GENES, rng, **SETTINGS)


def test_the_fronts_and_crowding_of_a_hand_example():
    """Four points trade off, one is dominated by two of them, one by every other point.

    The front ends get infinity; inside, each objective adds the gap of the neighbours over the
    range: (3 - 1) / 3 + (5 - 2) / 4 and (4 - 2) / 3 + (3 - 1) / 4.
    """
    objectives = np.array([[1, 5], [2, 3], [3, 2], [4, 1], [3, 4], [5, 5]], dtype=float)
    front, crowding = rank(objectives, np.zeros(6))
    assert front.tolist() == [0, 0, 0, 0, 1, 2]
    assert np.isinf(crowding[[0, 3, 4, 5]]).all()
    assert crowding[1] == pytest.approx(2 / 3 + 3 / 4)
    assert crowding[2] == pytest.approx(2 / 3 + 2 / 4)
    assert order(front, crowding).tolist() == [0, 3, 1, 2, 4, 5]


def test_a_feasible_genome_beats_an_infeasible_one_and_violations_order_the_rest():
    """The infeasible genomes have better objectives but come after, smallest violation first."""
    objectives = np.array([[5.0, 5.0], [0.0, 0.0], [1.0, 1.0], [0.0, 0.0]])
    front, _ = rank(objectives, np.array([0.0, 3.0, 1.0, 2.0]))
    assert front.tolist() == [0, 3, 1, 2]


def test_one_objective_sorts_by_violation_then_objective():
    """Feasible genomes by objective, then infeasible ones by violation whatever their objective."""
    objectives = np.array([[4.0], [-1.0], [2.0], [0.5], [9.0], [-7.0]])
    violations = np.array([0.0, 2.0, 0.0, 0.5, 0.0, 1.0])
    front, crowding = rank(objectives, violations)
    expected = sorted(range(6), key=lambda index: (violations[index], objectives[index, 0]))
    assert order(front, crowding).tolist() == expected


def test_a_nan_objective_counts_as_infinity():
    """A NaN objective is worse than any number: that genome falls behind the one it ties."""
    objectives = np.array([[1.0, np.nan], [2.0, 2.0], [1.0, 3.0], [3.0, 1.0]])
    front, crowding = rank(objectives, np.zeros(4))
    assert front.tolist() == [1, 0, 0, 0]
    assert not np.isnan(crowding).any()


def test_the_same_seed_gives_the_same_children_and_another_seed_others():
    """Every draw comes from the generator passed in."""
    assert np.array_equal(_children(3), _children(3))
    assert not np.array_equal(_children(3), _children(4))


def test_genomes_and_children_stay_within_bounds_and_whole_genes_stay_whole():
    """Over many draws every gene keeps to its bounds and integer and option genes to integers."""
    rng = np.random.default_rng(7)
    low = np.array([gene.low for gene in GENES])
    high = np.array([gene.high for gene in GENES])
    population = random_genomes(GENES, 200, rng)
    for _ in range(20):
        population = offspring(population, population[rng.permutation(200)], GENES, rng, **SETTINGS)
        assert (population >= low).all() and (population <= high).all()
        assert np.array_equal(population[:, 1:], np.rint(population[:, 1:]))
    assert set(population[:, 2]) == {0.0, 1.0, 2.0}


def test_random_genomes_cover_every_whole_value():
    """Both bounds of an integer gene are drawn."""
    genomes = random_genomes(GENES, 300, np.random.default_rng(1))
    assert set(genomes[:, 1]) == {1.0, 2.0, 3.0, 4.0, 5.0, 6.0}


def test_the_tournament_picks_the_better_genome():
    """A lower front wins, and in the same front a larger crowding distance."""
    rng = np.random.default_rng(0)
    chosen = tournament(np.array([1, 0]), np.array([np.inf, 0.0]), 100, rng)
    assert set(chosen.tolist()) <= {0, 1} and chosen.tolist().count(1) > 50
    chosen = tournament(np.array([0, 0]), np.array([0.5, 2.0]), 100, rng)
    assert chosen.tolist().count(1) > 50
    assert tournament(np.array([0, 1]), np.zeros(2), 50, rng).tolist().count(1) < 20


def test_the_key_keeps_only_the_active_genes_with_their_exact_values():
    """Inactive genes do not change the key; whole genes are ints and the rest exact floats."""
    genome = np.array([12.345678901234567, 4.0, 2.0])
    other = np.array([12.345678901234567, 5.0, 2.0])
    found = key(genome, GENES, (0, 2))
    assert found == key(other, GENES, (0, 2)) == (12.345678901234567, 2)
    assert isinstance(found[1], int) and isinstance(found[0], float)
    assert {found: 1}[found] == 1
