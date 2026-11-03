"""The parts of a genetic search: genes, random genomes, ranking, parent choice and children.

A genome is a 1-D float array with one value per gene. An integer gene holds a whole number and a
categorical gene the index of its option, both stored as floats. Every random choice comes from
the ``numpy.random.Generator`` passed in, in a fixed order, so the same seed gives the same result.
Objectives are minimised; a violation of 0 is a feasible genome.
"""

from dataclasses import dataclass

import numpy as np

CONTINUOUS = "continuous"
"""The kind of a gene that takes any value between its bounds."""
INTEGER = "integer"
"""The kind of a gene that takes a whole number between its bounds, both included."""
CATEGORICAL = "categorical"
"""The kind of a gene that is the index of an option, from 0 to the last option."""


@dataclass(frozen=True)
class Gene:
    """One variable of a genome: its ``name``, its ``kind`` and its bounds ``low`` and ``high``.

    ``kind`` is ``"continuous"``, ``"integer"`` or ``"categorical"``. An integer gene has whole
    bounds, both included. A categorical gene has ``low`` 0 and ``high`` the number of options
    less one, and its value is the index of the option.
    """

    name: str
    kind: str
    low: float
    high: float


def _bounds(genes):
    """Return the lower bounds, the upper bounds and the mask of the whole-number genes."""
    low = np.array([gene.low for gene in genes], dtype=float)
    high = np.array([gene.high for gene in genes], dtype=float)
    whole = np.array([gene.kind != CONTINUOUS for gene in genes], dtype=bool)
    return low, high, whole


def random_genomes(genes, count, rng):
    """Return ``count`` random genomes, one per row, uniform over the bounds of each gene.

    One draw ``rng.random((count, len(genes)))`` gives every value: a continuous gene is uniform
    in [low, high], an integer or categorical gene a uniform whole number in [low, high].
    """
    low, high, whole = _bounds(genes)
    draws = rng.random((count, len(genes)))
    continuous = low + draws * (high - low)
    counted = np.minimum(np.floor(low + draws * (high - low + 1)), high)
    return np.where(whole, counted, continuous)


def _dominance(objectives, violations):
    """Return the matrix whose ``[i, j]`` says that genome ``i`` dominates genome ``j``.

    A feasible genome dominates an infeasible one, of two infeasible genomes the smaller
    violation dominates, and of two feasible genomes the Pareto rule decides: no objective worse
    and one better.
    """
    feasible = violations <= 0
    first, second = objectives[:, None, :], objectives[None, :, :]
    pareto = np.all(first <= second, axis=2) & np.any(first < second, axis=2)
    both = feasible[:, None] & feasible[None, :]
    neither = ~feasible[:, None] & ~feasible[None, :]
    smaller = violations[:, None] < violations[None, :]
    return (feasible[:, None] & ~feasible[None, :]) | (neither & smaller) | (both & pareto)


def _fronts(dominates):
    """Return the front of each genome: 0 for those no genome dominates, then 1, 2, ..."""
    count = len(dominates)
    front = np.full(count, -1, dtype=int)
    beaten = dominates.sum(axis=0)
    level = 0
    while np.any(front < 0):
        current = (beaten == 0) & (front < 0)
        front[current] = level
        beaten = beaten - dominates[current].sum(axis=0)
        level += 1
    return front


def _crowding(objectives):
    """Return the crowding distance of each genome of one front.

    The two ends of each objective get infinity. A genome inside adds the gap between its
    neighbours divided by the range of the objective over the front; an objective whose range is
    0 or not finite adds nothing.
    """
    count, number = objectives.shape
    distance = np.zeros(count)
    for column in range(number):
        values = objectives[:, column]
        sorted_at = np.argsort(values, kind="stable")
        distance[sorted_at[[0, -1]]] = np.inf
        ends = values[sorted_at[[0, -1]]]
        if count < 3 or not np.isfinite(ends).all() or ends[1] == ends[0]:
            continue
        spread = ends[1] - ends[0]
        gaps = (values[sorted_at[2:]] - values[sorted_at[:-2]]) / spread
        distance[sorted_at[1:-1]] += gaps
    return distance


def rank(objectives, violations):
    """Return the front and the crowding distance of each genome, objectives minimised.

    ``objectives`` is an ``(n, m)`` array and ``violations`` an ``(n,)`` array, 0 for a feasible
    genome and more for an infeasible one. Fronts follow the constraint domination of Deb: every
    feasible front comes first, by the Pareto rule, then the infeasible genomes, one front per
    distinct violation, smallest first. The crowding distance is computed within each front. A
    caller gives a genome whose objectives could not be computed a violation above 0; a NaN
    objective still counts as +inf. With one objective the order is that of (violation,
    objective).
    """
    objectives = np.nan_to_num(np.asarray(objectives, dtype=float), nan=np.inf)
    violations = np.asarray(violations, dtype=float)
    front = _fronts(_dominance(objectives, violations))
    crowding = np.zeros(len(front))
    for level in np.unique(front):
        members = front == level
        crowding[members] = _crowding(objectives[members])
    return front, crowding


def order(rank, crowding):
    """Return the genome indices best first: lower front, then larger crowding, then index."""
    return np.lexsort((-np.asarray(crowding, dtype=float), np.asarray(rank)))


def tournament(rank, crowding, count, rng):
    """Return ``count`` parent indices, each the better of two genomes drawn uniformly.

    One draw ``rng.integers(0, n, size=(count, 2))`` picks the pairs. The second genome wins only
    when it has a lower front, or the same front and a larger crowding distance; a tie goes to the
    first.
    """
    rank = np.asarray(rank)
    crowding = np.asarray(crowding, dtype=float)
    drawn = rng.integers(0, len(rank), size=(count, 2))
    first, second = drawn[:, 0], drawn[:, 1]
    lower = rank[second] < rank[first]
    wider = (rank[second] == rank[first]) & (crowding[second] > crowding[first])
    return np.where(lower | wider, second, first)


def _spread_factor(u, beta, eta):
    """Return the spread factor of the bounded simulated binary crossover for draws ``u``."""
    alpha = 2 - beta ** -(eta + 1)
    base = np.where(u <= 1 / alpha, u * alpha, 1 / (2 - u * alpha))
    return base ** (1 / (eta + 1))


def _crossed(a, b, low, high, u, eta):
    """Return the child of ``a`` and ``b`` by bounded simulated binary crossover (Deb, Agrawal).

    Of the two children of the rule, the one on the side of ``a`` is kept: the lower one when
    ``a`` is at most ``b``, the upper one otherwise. Equal parents give ``a`` back.
    """
    smaller, larger = np.minimum(a, b), np.maximum(a, b)
    gap = larger - smaller
    safe = np.where(gap > 0, gap, 1)
    lower_beta = 1 + 2 * (smaller - low) / safe
    upper_beta = 1 + 2 * (high - larger) / safe
    middle = (smaller + larger) / 2
    lower = middle - _spread_factor(u, lower_beta, eta) * gap / 2
    upper = middle + _spread_factor(u, upper_beta, eta) * gap / 2
    child = np.where(a <= b, lower, upper)
    return np.where(gap > 0, child, a)


def _mutated(value, low, high, r, eta):
    """Return ``value`` moved by the bounded polynomial mutation of Deb for draws ``r``."""
    width = high - low
    safe = np.where(width > 0, width, 1)
    below = 1 - (value - low) / safe
    above = 1 - (high - value) / safe
    down = (2 * r + (1 - 2 * r) * below ** (eta + 1)) ** (1 / (eta + 1)) - 1
    up = 1 - (2 * (1 - r) + 2 * (r - 0.5) * above ** (eta + 1)) ** (1 / (eta + 1))
    step = np.where(r < 0.5, down, up)
    return np.where(width > 0, value + step * width, value)


def offspring(
    parents_a, parents_b, genes, rng, *, crossover, eta_crossover, eta_mutation, mutation
):
    """Return one child per pair of rows of ``parents_a`` and ``parents_b``.

    A pair crosses with probability ``crossover``, and then each gene with probability 0.5. A
    continuous or integer gene crosses by bounded simulated binary crossover with index
    ``eta_crossover``, keeping the child on the side of the gene of ``a``, and mutates with
    probability ``mutation`` by bounded polynomial mutation with index ``eta_mutation``; an
    integer gene is then rounded. A categorical gene that crosses takes the option of ``b``, and
    with probability ``mutation`` is reset to an option drawn uniformly. Every gene is clipped to
    its bounds. The draws are always made in this order, whatever the genes: ``rng.random(n)`` for
    the pairs that cross, then four ``rng.random((n, len(genes)))`` for the genes that cross, the
    crossover spread, the genes that mutate and the mutation step or new option.
    """
    a = np.asarray(parents_a, dtype=float)
    b = np.asarray(parents_b, dtype=float)
    low, high, whole = _bounds(genes)
    categorical = np.array([gene.kind == CATEGORICAL for gene in genes], dtype=bool)
    pairs = rng.random(len(a)) < crossover
    crosses = pairs[:, None] & (rng.random(a.shape) < 0.5)
    spread = rng.random(a.shape)
    mutates = rng.random(a.shape) < mutation
    step = rng.random(a.shape)
    numbers = np.where(crosses, _crossed(a, b, low, high, spread, eta_crossover), a)
    numbers = np.where(mutates, _mutated(numbers, low, high, step, eta_mutation), numbers)
    numbers = np.where(whole, np.rint(numbers), numbers)
    options = np.where(crosses, b, a)
    drawn = np.minimum(np.floor(low + step * (high - low + 1)), high)
    options = np.where(mutates, drawn, options)
    return np.clip(np.where(categorical, options, numbers), low, high)


def key(genome, genes, active):
    """Return the values of the ``active`` genes of ``genome`` as a tuple, to look a genome up.

    ``active`` lists gene indices. An integer or categorical gene is an ``int``, a continuous gene
    the exact ``float``; the other genes are left out.
    """
    return tuple(
        float(genome[index]) if genes[index].kind == CONTINUOUS else int(genome[index])
        for index in active
    )
