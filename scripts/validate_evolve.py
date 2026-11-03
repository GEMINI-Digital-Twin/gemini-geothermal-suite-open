"""Acceptance harness of ``gm.study.evolve``: how often it finds a brute-force true answer.

Usage::

    PYTHONPATH=. python scripts/validate_evolve.py --out .tmp/validation/baseline
    PYTHONPATH=. python scripts/validate_evolve.py --problem chain --seeds 3 --out .tmp/v/quick

For each problem it knows the true answer, then runs ``gm.study.evolve`` and a random search of the
same budget for every budget and seed, and scores each run against the truth.

Problems:

- ``hackathon``: ``examples/hackathon_superstructure`` sized by ``gm.study.size`` on the
  hackathon case, objectives ``lcts`` and ``co2``. The truth is a brute force over every valid
  structure: its own values, a full grid of ``--truth-levels`` values per variable (bounds
  included) and a Latin hypercube of ``--truth-samples`` designs; then, from the best feasible
  design of each structure on each objective, ``gm.study.minimize`` (budget ``5 x
  --truth-generations``, which it runs per variable) and a search one variable at a time over
  ``--truth-coordinate`` values. Each design is run by ``gm.simulate`` and judged by
  ``gm.evaluate.report``, feasible when its verdict is. The feasible designs are a narrow region
  at high doublet flow (about 8 % of the grid) that ``minimize`` from its own hypercube misses
  (it returns its start), hence the grid. The jobs run in parallel; cache the truth with
  ``--truth-cache``.
- ``chain``, ``pareto``, ``constrained``: superstructures of valves on closed loops with a cost that
  is an analytic function of the structure and the values, so the truth is exact. ``chain`` has
  ten structure genes (eight optional valves and two choices, 1536 structures of which 693 are
  valid: a loop with every valve off is refused by ``check``) and eight continuous genes, one
  objective; ``pareto`` has a known Pareto front shared by several structures; ``constrained``
  has its optimum on a constraint and its cheapest structures wholly infeasible. They replace
  the simulation of ``evolve`` through ``synthetic_adapter``, the one place that touches an
  internal of gemini.

Every evolve run uses ``polish=0`` and one process; the runs themselves go to ``--processes``
worker processes. The random search draws a valid structure and uniform values ``budget``
times. Scores per run: whether the best feasible point has the structure of the true best, the
relative gap of its first objective to the true best, the hypervolume of the feasible front over
that of the true front (objectives normalised by the true front's ideal and nadir, reference
point 1.1), the front size, the evaluations, the invalid candidates and the wall time.

The output folder ``--out`` gets ``truth.json``, ``results.json`` (every run and the summaries)
and ``results.md`` (the tables).
"""

import argparse
import contextlib
import importlib
import itertools
import json
import multiprocessing
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from copy import deepcopy
from pathlib import Path

import numpy as np
from scipy.stats import qmc

import gemini as gm
from gemini.units.shapes import measure

ROOT = Path(__file__).resolve().parents[1]
HACKATHON_CASE = ROOT / "examples/hackathon_2026/case.json"
HACKATHON_PLANT = ROOT / "examples/hackathon_superstructure/plants/HackathonSuperstructure.json"
REFERENCE = 1.1
"""The reference point of the hypervolume, in objectives normalised to the true front."""
TRUTH_GRID = 2001
"""Points of the continuous gene along each structure's own front of the ``pareto`` problem."""
TOLERANCE = 1e-9
"""Slack of the synthetic constraint, so that a point on the boundary is feasible."""
UNIT = "m3/h/bar^0.5"
"""The unit of the flow coefficient of the valves, the continuous genes of the synthetic plants."""

CHAIN_WEIGHT = {
    "v0": -0.6,
    "v1": -0.5,
    "v2": 0.3,
    "v3": -0.4,
    "v4": 0.2,
    "v5": 0.25,
    "v6": -0.3,
    "v7": -0.2,
}
CHAIN_TARGET = {
    "v0": 0.2,
    "v1": 0.8,
    "v2": 0.5,
    "v3": 0.7,
    "v4": 0.3,
    "v5": 0.6,
    "v6": 0.9,
    "v7": 0.15,
}
CHAIN_CHOICE = {"k1": {"a": -0.15, "b": 0.1, "none": 0.0}, "k2": {"a": 0.05, "none": 0.0}}
PARETO_A = {"v0": 0.05, "v1": 0.25, "v2": 0.0, "v3": 0.12, "a": 0.0, "b": 0.2, "none": 0.1}
PARETO_B = {"v0": -0.1, "v1": -0.4, "v2": 0.15, "v3": 0.0, "a": 0.1, "b": -0.2, "none": 0.0}
PARETO_TARGET = 0.35
CONSTRAINED_COST = {"v0": -0.5, "v1": -0.3, "v2": -0.4, "v3": 0.2, "a": -0.2, "b": 0.1, "none": 0}
CONSTRAINED_NEED = {"v0": 0.9, "v1": 0.4, "v2": 0.6, "v3": -0.3, "a": 0.5, "b": -0.2, "none": 0}
CONSTRAINED_BASE = 0.6


def nondominated(points):
    """Return the indices of the points no other point dominates, all objectives minimised.

    Equal points are kept once. The points are taken in lexicographic order, in which no point
    dominates one before it, so each is compared with the ones kept so far only.
    """
    values = np.asarray(points, dtype=float).reshape(len(points), -1)
    kept = []
    for index in np.lexsort(values.T[::-1]):
        if kept and np.any(np.all(values[kept] <= values[index], axis=1)):
            continue
        kept.append(int(index))
    return kept


def hypervolume_2d(points, reference):
    """Return the area dominated by 2-D ``points`` and bounded by ``reference`` (minimised)."""
    inside = sorted(
        (float(x), float(y)) for x, y in points if x < reference[0] and y < reference[1]
    )
    area, ceiling = 0.0, float(reference[1])
    for x, y in inside:
        if y < ceiling:
            area += (reference[0] - x) * (ceiling - y)
            ceiling = y
    return area


def normalised(points, ideal, nadir):
    """Return ``points`` scaled so that ``ideal`` is 0 and ``nadir`` 1 on each objective.

    An objective on which the two are equal is scaled by the size of the ideal (or by one).
    """
    ideal, nadir = np.asarray(ideal, dtype=float), np.asarray(nadir, dtype=float)
    span = nadir - ideal
    span = np.where(span > 0, span, np.maximum(np.abs(ideal), 1.0))
    return (np.asarray(points, dtype=float).reshape(-1, len(ideal)) - ideal) / span


def hypervolume_ratio(found, truth):
    """Return the hypervolume of the ``found`` front over that of the ``truth`` front (2-D)."""
    truth = np.asarray(truth, dtype=float)
    ideal, nadir = truth.min(axis=0), truth.max(axis=0)
    reference = (REFERENCE, REFERENCE)
    whole = hypervolume_2d(normalised(truth, ideal, nadir), reference)
    if not len(found) or whole <= 0:
        return 0.0 if whole > 0 else None
    return hypervolume_2d(normalised(found, ideal, nadir), reference) / whole


def relative_gap(found, best):
    """Return ``(found - best) / |best|``; a negative gap beats the truth."""
    return (found - best) / abs(best) if best else found - best


def statistics(values):
    """Return the count, mean, median, quartiles, smallest and largest of the numbers given.

    ``None`` and NaN are left out; with none left every statistic is ``None``.
    """
    kept = np.array([value for value in values if value is not None and np.isfinite(value)])
    if not len(kept):
        return dict.fromkeys(("count", "mean", "median", "q1", "q3", "min", "max")) | {"count": 0}
    q1, median, q3 = np.percentile(kept, [25, 50, 75])
    return {
        "count": len(kept),
        "mean": float(kept.mean()),
        "median": float(median),
        "q1": float(q1),
        "q3": float(q3),
        "min": float(kept.min()),
        "max": float(kept.max()),
    }


def same_structure(one, other):
    """Return whether two structure dicts choose the same, whatever their order."""
    return sorted(one.items()) == sorted(other.items())


def chain_outcome(on, chosen, u):
    """Return the cost of the ``chain`` problem and no violation.

    Ten plus, for each valve that is on, its weight and three times the square of its distance
    to its target; plus the cost of each choice, plus one when ``v0`` and ``v1`` are both on.
    """
    cost = 10.0 + sum(
        CHAIN_WEIGHT[name] + 3.0 * (u[name] - CHAIN_TARGET[name]) ** 2
        for name in CHAIN_WEIGHT
        if name in on
    )
    cost += sum(CHAIN_CHOICE[choice][group] for choice, group in chosen.items())
    return [cost + (1.0 if {"v0", "v1"} <= on else 0.0)], 0.0


def chain_optimum(on, chosen):
    """Return the best cost of a ``chain`` structure: every valve at its target."""
    return [chain_outcome(on, chosen, CHAIN_TARGET)[0]]


def _offsets(table, on, chosen):
    """Return the sum of ``table`` over the valves that are on and the group of ``k1``."""
    return sum(value for name, value in table.items() if name in on) + table[chosen["k1"]]


def pareto_outcome(on, chosen, u):
    """Return the two objectives of the ``pareto`` problem and no violation.

    ``1 + a + x`` and ``1.5 + b + (1 - sqrt(x)) + 3 (y - 0.35)^2``, ``x`` and ``y`` the genes of
    the fixed valves ``f0`` and ``f1``, ``a`` and ``b`` sums over the structure.
    """
    first = 1.0 + sum(PARETO_A[name] for name in PARETO_A if name in on) + PARETO_A[chosen["k1"]]
    x, y = u["f0"], u["f1"]
    second = 1.5 + _offsets(PARETO_B, on, chosen) + (1.0 - np.sqrt(x))
    return [first + x, second + 3.0 * (y - PARETO_TARGET) ** 2], 0.0


def pareto_optimum(on, chosen):
    """Return the front of a ``pareto`` structure: ``y`` at its target, ``x`` along a grid."""
    return [
        pareto_outcome(on, chosen, {"f0": x, "f1": PARETO_TARGET})[0]
        for x in np.linspace(0.0, 1.0, TRUTH_GRID)
    ]


def constrained_outcome(on, chosen, u):
    """Return the cost of the ``constrained`` problem and its violation.

    ``5 + c + (x - 0.2)^2 + (y - 0.3)^2`` subject to ``x + y >= d``, ``c`` and ``d`` sums over
    the structure; the violation is the excess of ``d`` over ``x + y``.
    """
    x, y = u["f0"], u["f1"]
    cost = 5.0 + _offsets(CONSTRAINED_COST, on, chosen) + (x - 0.2) ** 2 + (y - 0.3) ** 2
    need = CONSTRAINED_BASE + _offsets(CONSTRAINED_NEED, on, chosen)
    return [cost], max(0.0, need - x - y - TOLERANCE)


def constrained_optimum(on, chosen):
    """Return the best cost of a ``constrained`` structure, none when it cannot be feasible."""
    need = CONSTRAINED_BASE + _offsets(CONSTRAINED_NEED, on, chosen)
    if need > 2.0:
        return []
    x, y = 0.2, 0.3
    if need > 0.5:
        x = min(max((need - 0.1) / 2.0, max(0.0, need - 1.0)), min(1.0, need))
        y = need - x
    return [constrained_outcome(on, chosen, {"f0": x, "f1": y})[0]]


CHAIN = {
    "loops": {
        "u1": ["v0", "v1", "k1a", "k1b"],
        "u2": ["v2", "v3", "k2a"],
        "u3": ["v4", "v5"],
        "u4": ["v6", "v7"],
    },
    "optional": [f"v{index}" for index in range(8)],
    "choices": {"k1": {"a": ["k1a"], "b": ["k1b"], "none": []}, "k2": {"a": ["k2a"], "none": []}},
    "ranged": [f"v{index}" for index in range(8)],
    "objectives": ["lcts"],
    "outcome": chain_outcome,
    "optimum": chain_optimum,
}
TWO_LOOPS = {
    "loops": {"u1": ["f0", "f1", "v0", "v1", "k1a", "k1b"], "u2": ["v2", "v3"]},
    "optional": ["v0", "v1", "v2", "v3"],
    "choices": {"k1": {"a": ["k1a"], "b": ["k1b"], "none": []}},
    "ranged": ["f0", "f1"],
}
SYNTHETIC = {
    "chain": CHAIN,
    "pareto": TWO_LOOPS
    | {"objectives": ["lcts", "co2"], "outcome": pareto_outcome, "optimum": pareto_optimum},
    "constrained": TWO_LOOPS
    | {"objectives": ["lcts"], "outcome": constrained_outcome, "optimum": constrained_optimum},
}
PROBLEMS = ["hackathon", *SYNTHETIC]


def modules_on(spec, structure):
    """Return the modules of a synthetic plant that are on in ``structure``."""
    in_choice = {
        name
        for groups in spec["choices"].values()
        for members in groups.values()
        for name in members
    }
    fixed = {
        name
        for loop in spec["loops"].values()
        for name in loop
        if name not in spec["optional"] and name not in in_choice
    }
    optional = {name for name in spec["optional"] if structure[name]}
    chosen = {
        name for choice, groups in spec["choices"].items() for name in groups[structure[choice]]
    }
    return fixed | optional | chosen


def every_structure(spec):
    """Return every structure of a synthetic plant, in the order of ``plant.structures()``."""
    keys = [*spec["optional"], *spec["choices"]]
    sides = [(True, False)] * len(spec["optional"]) + [tuple(g) for g in spec["choices"].values()]
    return [dict(zip(keys, chosen)) for chosen in itertools.product(*sides)]


def is_valid(spec, structure):
    """Return whether every loop of a synthetic plant keeps a module on in ``structure``."""
    on = modules_on(spec, structure)
    return all(any(name in on for name in loop) for loop in spec["loops"].values())


def synthetic_plant(spec):
    """Return the superstructure of a synthetic problem: valves on closed heating loops.

    Each loop runs from a heating grid's return through its valves back to its supply, the last
    connection a state. A loop whose valves are all off joins the grid to itself, which
    ``check`` refuses, so such structures are invalid. Each ranged valve has its own range of
    the flow coefficient, so no two of them are tied into one variable.
    """
    plant = gm.Plant("Synthetic")
    for user, valves in spec["loops"].items():
        plant.add("HeatingGrid", name=user)
        source = f"{user}.return_out"
        for name in valves:
            low, high = _range_of(spec, name)
            params = {
                "flow_coefficient": gm.units.Quantity((low + high) / 2.0, UNIT),
                "characteristic": "linear",
                "rangeability": 50.0,
            }
            plant.add("Valve", name=name, params=params)
            plant.connect(source, f"{name}.fluid_in")
            source = f"{name}.fluid_out"
        plant.connect(source, f"{user}.supply_in", type="state")
    for name in spec["optional"]:
        plant.set_optional(name)
    for name, groups in spec["choices"].items():
        plant.set_choice(name, groups)
    for name in spec["ranged"]:
        low, high = _range_of(spec, name)
        plant.set_range(
            f"{name}.flow_coefficient", gm.units.Quantity(low, UNIT), gm.units.Quantity(high, UNIT)
        )
    return plant


def _range_of(spec, name):
    """Return the range of the flow coefficient of a valve: apart from every other valve's."""
    index = spec["ranged"].index(name) if name in spec["ranged"] else 0
    return 1.0 + 0.5 * index, 20.0 + 0.5 * index


def synthetic_case():
    """Return the hackathon case without requirements: ``gm.check`` must pass, nothing runs."""
    data = json.loads(HACKATHON_CASE.read_text())
    data.pop("requirements", None)
    return gm.Case.from_dict(data, folder=HACKATHON_CASE.parent)


class Synthetic:
    """A synthetic problem: its superstructure, its analytic outcome and its exact truth."""

    def __init__(self, name):
        """Build the plant and the case of the synthetic problem ``name``."""
        self.name, self.spec = name, SYNTHETIC[name]
        self.objectives = self.spec["objectives"]
        self.plant = synthetic_plant(self.spec)
        self.case = synthetic_case()
        self.ranges = {flat: (item.min, item.max) for flat, item in self.plant.ranges.items()}
        self.every = every_structure(self.spec)
        self.structures = [item for item in self.every if is_valid(self.spec, item)]

    def evaluated(self, structure, u):
        """Return ``(objectives, violation)`` of a structure at the unit genes ``u``."""
        chosen = {choice: structure[choice] for choice in self.spec["choices"]}
        return self.spec["outcome"](modules_on(self.spec, structure), chosen, u)

    def outcome(self, structure, values):
        """Return what ``evolve._evaluated`` returns for one item: metrics, reason, violation."""
        u = {
            flat.partition(".")[0]: (values[flat] - low) / (high - low)
            for flat, (low, high) in self.ranges.items()
            if flat in values
        }
        objectives, violation = self.evaluated(structure, u)
        metrics = {name: measure(value, "-") for name, value in zip(self.objectives, objectives)}
        if violation > 0:
            return metrics, "synthetic constraint", violation
        return metrics, None, 0.0

    def random_point(self, rng):
        """Return a point of a valid structure drawn at random with uniform genes."""
        structure = self.structures[rng.integers(len(self.structures))]
        u = {name: rng.random() for name in self.spec["ranged"]}
        objectives, violation = self.evaluated(structure, u)
        return point(structure, objectives, violation <= 0)

    def design_point(self, design):
        """Return the point of an evolve ``Design``: its metrics are those of the adapter."""
        values = [design["metrics"][name].value for name in self.objectives]
        return point(design["structure"], values, design["feasible"])

    def truth(self):
        """Return the exact truth, after checking the valid structures against the plant's."""
        start, points = time.perf_counter(), []
        listed = self.plant.structures()
        if sorted(map(_key, listed)) != sorted(map(_key, self.structures)):
            raise RuntimeError(f"{self.name}: the valid structures differ from plant.structures()")
        for structure in self.structures:
            chosen = {choice: structure[choice] for choice in self.spec["choices"]}
            optimum = self.spec["optimum"](modules_on(self.spec, structure), chosen)
            points += [point(structure, values, True) for values in optimum]
        return truth_of(self, points, time.perf_counter() - start, 0)


def _key(structure):
    """Return a structure as a sortable tuple of its items."""
    return tuple(sorted((name, str(value)) for name, value in structure.items()))


def point(structure, objectives, feasible, **extra):
    """Return a judged design: its structure, its objectives and whether it is feasible."""
    values = [float(value) if value is not None else float("nan") for value in objectives]
    feasible = bool(feasible) and all(np.isfinite(values))
    return {"structure": dict(structure), "objectives": values, "feasible": feasible} | extra


class Hackathon:
    """The hackathon superstructure, sized on its case, judged by a real run."""

    objectives = ["lcts", "co2"]

    def __init__(self):
        """Read and size the superstructure and list its valid structures."""
        self.name = "hackathon"
        self.case = gm.Case.from_json(HACKATHON_CASE)
        self.plant = gm.study.size(gm.Plant.from_json(HACKATHON_PLANT), self.case)
        self.structures = self.plant.structures()
        self.every = self.structures
        self.found = {}

    def judged(self, plant, structure, **extra):
        """Return the point of ``plant`` by ``gm.simulate`` and the verdict of its report."""
        try:
            report = gm.evaluate.report(plant, self.case, gm.simulate(plant, self.case))
        except Exception as error:
            values = [None] * len(self.objectives)
            return point(structure, values, False, reason=f"{type(error).__name__}: {error}")
        values = [report[name].value for name in self.objectives]
        reasons = [item["name"] for item in report["verdict"]["reasons"]]
        return point(structure, values, report["verdict"]["feasible"], reasons=reasons, **extra)

    def variables(self, structure):
        """Return the variables of a structure: ``(paths, low, high)``, tied as ``evolve`` ties.

        Paths with the same parameter and the same range are one variable, the tie of
        ``minimize`` and ``evolve`` for this plant (its roles add nothing here).
        """
        if _key(structure) not in self.found:
            tied = {}
            for flat, item in self.plant.with_structure(structure).ranges.items():
                tied.setdefault((flat.rpartition(".")[2], item.min, item.max), []).append(flat)
            self.found[_key(structure)] = [
                (paths, low, high) for (_, low, high), paths in tied.items()
            ]
        return self.found[_key(structure)]

    def valued(self, structure, numbers):
        """Return the plant of ``structure`` with its variables at the SI ``numbers``.

        As ``evolve`` builds a candidate: the values are set on the superstructure, then the
        structure is taken.
        """
        plant = deepcopy(self.plant)
        for (paths, _, _), number in zip(self.variables(structure), numbers):
            for flat in paths:
                path, _, parameter = flat.rpartition(".")
                plant._set_si_params(path, {parameter: float(number)})
        return plant.with_structure(structure)

    def random_point(self, rng):
        """Return a run of a valid structure drawn at random with uniform values."""
        structure = self.structures[rng.integers(len(self.structures))]
        found = self.variables(structure)
        numbers = [low + rng.random() * (high - low) for _, low, high in found]
        return self.judged(self.valued(structure, numbers), structure)

    def design_point(self, design):
        """Return the point of an evolve ``Design`` run again, with what evolve claimed."""
        claimed = [design["metrics"][name].value for name in self.objectives]
        return self.judged(
            design["plant"],
            design["structure"],
            claimed=claimed,
            claimed_feasible=design["feasible"],
        )


_PROBLEMS = {}


def problem_of(name):
    """Return the problem ``name``, built once per process."""
    if name not in _PROBLEMS:
        _PROBLEMS[name] = Hackathon() if name == "hackathon" else Synthetic(name)
    return _PROBLEMS[name]


@contextlib.contextmanager
def synthetic_adapter(problem):
    """Replace the simulation of ``evolve`` by the analytic outcome of ``problem``, then restore.

    The one internal of gemini this harness touches. ``gemini.study.evolve._evaluated(shared,
    items)`` gets ``shared = (case, plan, names)`` and ``items``, a list of ``(design_plant,
    values, structure)`` with ``values`` ``{flat parameter name: SI value}``, and returns one
    ``(metrics, reason, violation)`` per item: ``metrics`` ``{name: Value}``, ``reason`` ``None``
    when feasible, ``violation`` 0 when feasible. Run ``evolve`` with one process inside it.
    """
    module = importlib.import_module("gemini.study.evolve")
    held = module._evaluated
    module._evaluated = lambda shared, items: [
        problem.outcome(structure, values) for _, values, structure in items
    ]
    try:
        yield
    finally:
        module._evaluated = held


def evolve_job(name, budget, seed, population):
    """Return one run of ``gm.study.evolve`` on problem ``name``: its front and best as points."""
    problem = problem_of(name)
    adapter = synthetic_adapter(problem) if name in SYNTHETIC else contextlib.nullcontext()
    start = time.perf_counter()
    with adapter, gm.runtime.settings(processes=1):
        found = gm.study.evolve(
            problem.plant,
            problem.case,
            problem.objectives,
            budget,
            seed,
            population=population,
            polish=0,
        )
    wall = time.perf_counter() - start
    designs = list({id(item): item for item in [*found["front"], found["best"]]}.values())
    points = [problem.design_point(item) for item in designs]
    return {
        "method": "evolve",
        "problem": name,
        "budget": budget,
        "seed": seed,
        "evaluations": found["evaluations"],
        "invalid": found["invalid"],
        "wall": wall,
        "best_claimed": found["best"]["feasible"],
        "points": points,
    }


def random_job(name, budget, seed):
    """Return one random search of ``budget`` evaluations on problem ``name``."""
    problem = problem_of(name)
    rng = np.random.default_rng(seed)
    start = time.perf_counter()
    points = [problem.random_point(rng) for _ in range(budget)]
    return {
        "method": "random",
        "problem": name,
        "budget": budget,
        "seed": seed,
        "evaluations": budget,
        "invalid": 0,
        "wall": time.perf_counter() - start,
        "points": points,
    }


def designs_job(index, rows, source):
    """Return the points of hackathon structure ``index`` at each row of SI ``rows``."""
    problem = problem_of("hackathon")
    structure = problem.structures[index]
    if rows is None:
        plant = problem.plant.with_structure(structure)
        return [problem.judged(plant, structure, source=source, values=None)]
    return [
        problem.judged(problem.valued(structure, row), structure, source=source, values=list(row))
        for row in rows
    ]


def _better(candidate, held, objective):
    """Return whether a feasible ``candidate`` beats ``held`` on the objective at ``objective``."""
    return (
        candidate["feasible"] and candidate["objectives"][objective] < held["objectives"][objective]
    )


def refine_job(index, objective, start, generations, seed, levels):
    """Return the points of a search of structure ``index`` on one objective from ``start``.

    ``gm.study.minimize`` from the design ``start`` (a point with its SI ``values``), with
    the budget ``5 x generations`` (at least ``5 x variables``), which it runs per variable;
    then a search one variable at a time over ``levels`` values between its bounds, twice over,
    keeping each improvement. The second search also reaches the bounds, which ``minimize``
    (differential evolution) does not try.
    """
    problem = problem_of("hackathon")
    structure, name = problem.structures[index], problem.objectives[objective]
    plant, found = problem.valued(structure, start["values"]), problem.variables(structure)
    budget = 5 * max(generations, len(found))
    search = gm.study.minimize(plant, problem.case, name, budget, seed)
    points = [problem.judged(search["best"]["plant"], structure, source=f"minimize {name}")]
    held = start
    for _, variable in itertools.product(range(2), range(len(found))):
        for number in np.linspace(found[variable][1], found[variable][2], levels):
            row = list(held["values"])
            row[variable] = float(number)
            points += designs_job(index, [row], f"coordinate {name}")
            if _better(points[-1], held, objective):
                held = points[-1]
    return points


def truth_of(problem, points, wall, evaluations):
    """Return the truth of a problem from its judged points: the true best and the true front."""
    feasible = [item for item in points if item["feasible"]]
    if not feasible:
        raise RuntimeError(f"{problem.name}: no feasible point; the truth is unknown")
    best = min(feasible, key=lambda item: tuple(item["objectives"]))
    front = [feasible[index] for index in nondominated([item["objectives"] for item in feasible])]
    front.sort(key=lambda item: item["objectives"])
    return {
        "problem": problem.name,
        "objectives": list(problem.objectives),
        "structures": len(problem.structures),
        "all_structures": len(problem.every),
        "points": len(points),
        "feasible_points": len(feasible),
        "best": best,
        "front": [item["objectives"] for item in front],
        "front_structures": [
            dict(s) for s in {_key(i["structure"]): i["structure"] for i in front}.values()
        ],
        "evaluations": evaluations,
        "wall": wall,
    }


def _rows(found, levels, samples, seed):
    """Return the designs of a structure: a grid with the bounds, and a Latin hypercube.

    The grid has ``levels`` values per variable, the hypercube ``samples`` designs.
    """
    low = np.array([item[1] for item in found])
    high = np.array([item[2] for item in found])
    grid = [list(row) for row in itertools.product(*np.linspace(low, high, levels).T)]
    draws = qmc.LatinHypercube(d=len(found), rng=np.random.default_rng(seed)).random(samples)
    return [("grid", grid), ("hypercube", [list(low + row * (high - low)) for row in draws])]


def _chunks(rows, size):
    """Return ``rows`` in consecutive lists of at most ``size``."""
    return [rows[start : start + size] for start in range(0, len(rows), size)]


def _first_points(pool, problem, args):
    """Return the points of every structure: its own values, the grid and the hypercube."""
    jobs = []
    for index, structure in enumerate(problem.structures):
        jobs.append(pool.submit(designs_job, index, None, "own"))
        found = problem.variables(structure)
        if not found:
            continue
        for source, rows in _rows(found, args.truth_levels, args.truth_samples, index):
            jobs += [pool.submit(designs_job, index, part, source) for part in _chunks(rows, 50)]
    return [item for job in jobs for item in job.result()]


def hackathon_truth(pool, args):
    """Return the hackathon truth: a grid and a hypercube of every structure, then a search.

    Each structure's best feasible design on each objective is searched further by
    ``refine_job``; every design run counts.
    """
    problem = problem_of("hackathon")
    start = time.perf_counter()
    points = _first_points(pool, problem, args)
    jobs = []
    for index, structure in enumerate(problem.structures):
        mine = [
            item
            for item in points
            if item.get("values") and same_structure(item["structure"], structure)
        ]
        for objective in range(len(problem.objectives)):
            feasible = [item for item in mine if item["feasible"]]
            if not feasible:
                continue
            best = min(feasible, key=lambda item: item["objectives"][objective])
            jobs.append(
                pool.submit(
                    refine_job,
                    index,
                    objective,
                    best,
                    args.truth_generations,
                    args.truth_seed,
                    args.truth_coordinate,
                )
            )
    points += [item for job in jobs for item in job.result()]
    truth = truth_of(problem, points, time.perf_counter() - start, len(points))
    truth["settings"] = {
        "levels": args.truth_levels,
        "samples": args.truth_samples,
        "generations": args.truth_generations,
        "coordinate": args.truth_coordinate,
        "seed": args.truth_seed,
    }
    truth["structure_points"] = points
    return truth


def scored(run, truth):
    """Return the scores of a run against the truth, without its points."""
    feasible = [item for item in run["points"] if item["feasible"]]
    scores = {key: value for key, value in run.items() if key != "points"}
    scores |= {"found_best": False, "gap": None, "hv_ratio": None, "front_points": 0}
    scores["claim_mismatch"] = sum(
        item["claimed_feasible"] != item["feasible"]
        for item in run["points"]
        if "claimed_feasible" in item
    )
    if not feasible:
        return scores
    best = min(feasible, key=lambda item: tuple(item["objectives"]))
    front = [
        feasible[index]["objectives"]
        for index in nondominated([item["objectives"] for item in feasible])
    ]
    scores["found_best"] = same_structure(best["structure"], truth["best"]["structure"])
    scores["gap"] = relative_gap(best["objectives"][0], truth["best"]["objectives"][0])
    scores["best"] = best
    scores["front_points"] = len(front)
    if len(truth["objectives"]) == 2:
        scores["hv_ratio"] = hypervolume_ratio(front, truth["front"])
    return scores


def summarised(scores):
    """Return one summary per problem, method and budget of the scored runs."""
    groups = {}
    for item in scores:
        groups.setdefault((item["problem"], item["method"], item["budget"]), []).append(item)
    summaries = []
    for (problem, method, budget), runs in sorted(groups.items()):
        summaries.append(
            {
                "problem": problem,
                "method": method,
                "budget": budget,
                "runs": len(runs),
                "success": float(np.mean([item["found_best"] for item in runs])),
                "gap": statistics([item["gap"] for item in runs]),
                "hv_ratio": statistics([item["hv_ratio"] for item in runs]),
                "front_points": statistics([item["front_points"] for item in runs]),
                "evaluations": statistics([item["evaluations"] for item in runs]),
                "invalid": statistics([item["invalid"] for item in runs]),
                "wall": statistics([item["wall"] for item in runs]),
                "beat_truth": sum((item["gap"] or 0.0) < -1e-9 for item in runs),
                "claim_mismatch": sum(item["claim_mismatch"] for item in runs),
                "no_feasible": sum(item["gap"] is None for item in runs),
            }
        )
    return summaries


def _number(value, digits=3):
    """Return a number for a table, or a dash for none."""
    return "-" if value is None else f"{value:.{digits}g}"


def _percent(value):
    """Return a relative gap as a percentage for a table, or a dash for none."""
    return "-" if value is None else f"{100 * value:.2f}%"


def label(structure):
    """Return a structure as one line: the optional modules and choices that are on."""
    return ", ".join(
        name if value is True else f"{name}={value}"
        for name, value in structure.items()
        if value is not False
    )


def truth_table(truths):
    """Return the markdown table of the truths."""
    lines = [
        "| problem | valid / all structures | true best structure | true best objectives "
        "| truth front points (structures) | truth evaluations | truth wall s |",
        "|---|---|---|---|---|---|---|",
    ]
    for truth in truths.values():
        best = truth["best"]
        lines.append(
            f"| {truth['problem']} | {truth['structures']} / {truth['all_structures']} "
            f"| {label(best['structure'])} "
            f"| {', '.join(_number(value, 6) for value in best['objectives'])} "
            f"| {len(truth['front'])} ({len(truth['front_structures'])}) "
            f"| {truth['evaluations']} | {truth['wall']:.1f} |"
        )
    return lines


def results_table(summaries):
    """Return the markdown table of the summaries."""
    lines = [
        "| problem | budget | method | runs | success | gap median | gap min | gap max "
        "| HV ratio median | HV ratio IQR | front points | evaluations | invalid | no feasible "
        "| wall s |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for item in summaries:
        gap, hv = item["gap"], item["hv_ratio"]
        iqr = "-" if hv["q1"] is None else f"{hv['q1']:.3f}-{hv['q3']:.3f}"
        lines.append(
            f"| {item['problem']} | {item['budget']} | {item['method']} | {item['runs']} "
            f"| {item['success']:.0%} | {_percent(gap['median'])} | {_percent(gap['min'])} "
            f"| {_percent(gap['max'])} | {_number(hv['median'])} | {iqr} "
            f"| {_number(item['front_points']['median'])} | {_number(item['evaluations']['mean'])} "
            f"| {_number(item['invalid']['mean'])} | {item['no_feasible']} "
            f"| {_number(item['wall']['mean'])} |"
        )
    return lines


def markdown(truths, summaries, settings):
    """Return the report: the settings, the truth table and the results table."""
    lines = [
        "# Validation of gm.study.evolve",
        "",
        f"gemini {gm.__version__}; " + ", ".join(f"{k} {v}" for k, v in settings.items()),
        "",
        "Success: the best feasible point has the structure of the true best. Gap: relative gap of"
        " the first objective to the true best (negative beats the truth). HV ratio: hypervolume"
        " of the feasible front over the true front's, normalised by its ideal and nadir,"
        f" reference point {REFERENCE}.",
        "",
        "## Truth",
        "",
        *truth_table(truths),
        "",
        "## Results",
        "",
        *results_table(summaries),
        "",
    ]
    return "\n".join(lines)


def known_truths(path):
    """Return the truths cached at ``path``, none when there is no such file."""
    if path is None or not Path(path).exists():
        return {}
    return json.loads(Path(path).read_text())


def run_jobs(pool, args, problems):
    """Return every evolve and random run, the longest submitted first."""
    jobs = []
    for budget in sorted(args.budgets, reverse=True):
        for name, seed in itertools.product(problems, range(args.seeds)):
            jobs.append(pool.submit(evolve_job, name, budget, seed, args.population))
            jobs.append(pool.submit(random_job, name, budget, seed))
    runs = []
    for job in as_completed(jobs):
        runs.append(job.result())
        item = runs[-1]
        print(
            f"[{len(runs)}/{len(jobs)}] {item['problem']} {item['method']} budget "
            f"{item['budget']} seed {item['seed']}: {item['wall']:.1f} s",
            flush=True,
        )
    return runs


def parsed(argv):
    """Return the command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__.partition("\n")[0])
    parser.add_argument("--problem", nargs="+", choices=[*PROBLEMS, "all"], default=["all"])
    parser.add_argument("--seeds", type=int, default=10, help="seeds 0 .. N-1 of each budget")
    parser.add_argument("--budgets", type=int, nargs="+", default=[64, 128, 256])
    parser.add_argument("--population", type=int, default=16)
    parser.add_argument("--processes", type=int, default=min(32, os.cpu_count() or 1))
    parser.add_argument("--out", type=Path, required=True, help="folder of the outputs")
    parser.add_argument("--truth-cache", type=Path, help="truth JSON to reuse, written if absent")
    parser.add_argument("--truth-levels", type=int, default=7, help="grid values per variable")
    parser.add_argument("--truth-generations", type=int, default=10)
    parser.add_argument("--truth-coordinate", type=int, default=21)
    parser.add_argument("--truth-samples", type=int, default=128)
    parser.add_argument("--truth-seed", type=int, default=0)
    args = parser.parse_args(argv)
    if "all" in args.problem:
        args.problem = list(PROBLEMS)
    return args


def truths_of(pool, args):
    """Return the truth of every problem asked for, from the cache or computed and cached."""
    truths = known_truths(args.truth_cache)
    for name in args.problem:
        if name in truths:
            continue
        print(f"truth of {name} ...", flush=True)
        truths[name] = (
            hackathon_truth(pool, args) if name == "hackathon" else problem_of(name).truth()
        )
        print(f"truth of {name}: {truths[name]['wall']:.1f} s", flush=True)
        if args.truth_cache is not None:
            args.truth_cache.parent.mkdir(parents=True, exist_ok=True)
            args.truth_cache.write_text(json.dumps(truths, indent=1))
    return {name: truths[name] for name in args.problem}


def main(argv=None):
    """Compute or reuse the truths, run every search, score them and write the report."""
    args = parsed(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    context = multiprocessing.get_context("spawn")
    start = time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.processes, mp_context=context) as pool:
        truths = truths_of(pool, args)
        runs = run_jobs(pool, args, args.problem)
    scores = [scored(run, truths[run["problem"]]) for run in runs]
    scores.sort(key=lambda item: (item["problem"], item["method"], item["budget"], item["seed"]))
    summaries = summarised(scores)
    settings = {
        "seeds": args.seeds,
        "budgets": args.budgets,
        "population": args.population,
        "processes": args.processes,
        "wall_s": round(time.perf_counter() - start, 1),
    }
    (args.out / "truth.json").write_text(json.dumps(truths, indent=1))
    results = {"settings": settings, "summaries": summaries, "runs": scores}
    (args.out / "results.json").write_text(json.dumps(results, indent=1))
    report = markdown(truths, summaries, settings)
    (args.out / "results.md").write_text(report)
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
