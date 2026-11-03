"""Search of the structures and the values a plant states, by a genetic algorithm (NSGA-II)."""

from copy import deepcopy

import numpy as np

from gemini import units
from gemini._utils.jsonable import to_plain
from gemini.engine.check import check
from gemini.errors import ValidationError
from gemini.errors.base import raise_issues
from gemini.plants import Plant
from gemini.plants._utils import superstructure
from gemini.plants._utils.resize import resized
from gemini.study._utils import genetic
from gemini.study._utils.parallel import mapped_batches
from gemini.study._utils.progress import counting
from gemini.study._utils.shared import Shared
from gemini.study._utils.shown import shown
from gemini.study._utils.target import unit_of
from gemini.study._utils.trial import LARGEST_VIOLATION, checked_metric, run_trials
from gemini.study._utils.variables import DOUBLETS, _owner, _split, counts, variables
from gemini.study.minimize import NOT_A_NUMBER, POPULATION_PER_VARIABLE, minimize
from gemini.units.shapes import measure

CROSSOVER = 0.9
"""Probability that a pair of parents crosses: the value of Deb's NSGA-II."""
ETA_CROSSOVER = 15.0
"""Distribution index of the simulated binary crossover: children near their parents."""
ETA_MUTATION = 20.0
"""Distribution index of the polynomial mutation: small steps, now and then a large one."""
STALL = 10
"""Generations in a row without a new simulation after which the search ends: it has seen all."""
INVALID = LARGEST_VIOLATION + 1.0
"""The violation of a structure whose plant is not valid: worse than any trial that ran."""


class Design(dict):
    """One design of ``evolve``: ``{structure, plant, metrics, feasible, reason, parameters}``.

    ``structure`` is the dict ``with_structure`` takes, ``plant`` the ordinary plant that ran,
    ``metrics`` ``{name: Value}`` in SI, ``feasible`` whether it meets the requirements,
    ``reason`` why not (``None`` when feasible), ``parameters`` ``{name: Quantity or option}`` of
    the values the search set, and ``violation`` its total relative violation (0 when feasible).
    """

    def to_dict(self):
        """Return the design as plain JSON in display units, with the plant as its plant dict."""
        return {
            "structure": dict(self["structure"]),
            "feasible": self["feasible"],
            "reason": self["reason"],
            "violation": self["violation"],
            "metrics": {name: shown(value).to_dict() for name, value in self["metrics"].items()},
            "parameters": to_plain(shown(self["parameters"])),
            "plant": None if self["plant"] is None else self["plant"].to_dict(),
        }


class Evolution(dict):
    """The result of ``evolve``: ``{front, best, history, evaluations, invalid}``, with ``to_dict``.

    ``front`` is a list of ``Design``, ``best`` the ``Design`` best on the first objective,
    ``history`` one entry per generation and ``evaluations`` the number of simulations;
    ``invalid`` counts the candidates whose structure was refused before any simulation.
    """

    def to_dict(self):
        """Return the result as plain JSON: every design of the front, the best and the history."""
        return {
            "best": self["best"].to_dict(),
            "front": [item.to_dict() for item in self["front"]],
            "history": to_plain(self["history"]),
            "evaluations": self["evaluations"],
            "invalid": self["invalid"],
        }


class _Space:
    """The genes of a superstructure: its structure, its doublet count, then its variables."""

    def __init__(self, plant):
        """Read the genes of ``plant``: one per optional module, choice, count and variable."""
        self.plant = plant
        self.genes, self.sides = [], []
        for name in plant._optional:
            self._add(name, genetic.CATEGORICAL, 0, 1, (True, False))
        for name, groups in plant._choices.items():
            self._add(name, genetic.CATEGORICAL, 0, len(groups) - 1, tuple(groups))
        self.structural = len(self.genes)
        sizes = counts(plant)
        self.counted = sizes != [None]
        if self.counted:
            self._add(DOUBLETS, genetic.INTEGER, sizes[0], sizes[-1], None)
        self.ties = {}
        for count in sizes:
            design = plant if count is None else resized(plant, count)
            for variable in variables(design):
                tie = _tie(design, variable)
                if tie in self.ties:
                    continue
                self.ties[tie] = len(self.genes)
                if variable.options is not None:
                    kind, high = genetic.CATEGORICAL, len(variable.options) - 1
                    self._add(variable.name, kind, 0, high, variable.options, variable)
                else:
                    kind = genetic.INTEGER if variable.integer else genetic.CONTINUOUS
                    self._add(variable.name, kind, variable.low, variable.high, None, variable)
        self.variables = {}

    def _add(self, name, kind, low, high, options, variable=None):
        """Add a gene and what it stands for."""
        self.genes.append(genetic.Gene(name, kind, float(low), float(high)))
        self.sides.append((options, variable))

    def structure(self, genome):
        """Return the structure dict of a genome."""
        return {
            gene.name: self.sides[index][0][int(genome[index])]
            for index, gene in enumerate(self.genes[: self.structural])
        }

    def count(self, genome):
        """Return the doublet count of a genome, ``None`` for a plant without one."""
        return int(genome[self.structural]) if self.counted else None

    def base(self, count):
        """Return the plant on ``count`` doublets and the genes of its variables."""
        if count not in self.variables:
            design = self.plant if count is None else resized(self.plant, count)
            found = [(self.ties[_tie(design, item)], item) for item in variables(design)]
            self.variables[count] = (design, found)
        return self.variables[count]

    def active(self, genome, off):
        """Return the indices of the genes that matter to a genome: those of modules that stay."""
        design, found = self.base(self.count(genome))
        kept = list(range(self.structural + int(self.counted)))
        kept += sorted(
            {index for index, item in found if any(_stays(path, off) for path in item.paths)}
        )
        return design, found, kept

    def values(self, genome, found):
        """Return ``{flat name: SI value}`` of the variables of a genome."""
        values = {}
        for index, variable in found:
            values.update(dict.fromkeys(variable.paths, _chosen(variable, genome[index])))
        return values

    def start(self, structure):
        """Return the genome of the plant's own values, clipped, in ``structure``.

        A variable that ties several modules takes the value of its first module that stays.
        """
        genome = np.zeros(len(self.genes))
        for index, name in enumerate(structure):
            genome[index] = self.sides[index][0].index(structure[name])
        count = self.plant.size.get("doublets")
        if self.counted:
            genome[self.structural] = min(
                max(count, self.genes[self.structural].low), self.genes[self.structural].high
            )
        design, found = self.base(self.count(genome))
        off = superstructure.off(self.plant, structure)
        for index, variable in found:
            staying = [flat for flat in variable.paths if _stays(flat, off)] or variable.paths
            path, _, parameter = staying[0].rpartition(".")
            held = getattr(design.get_submodule(path), parameter, None)
            gene = self.genes[index]
            if variable.options is not None:
                genome[index] = variable.options.index(held) if held in variable.options else 0
            elif isinstance(held, (int, float)):
                genome[index] = min(max(float(held), gene.low), gene.high)
            else:
                genome[index] = (gene.low + gene.high) / 2
        return genome


def _tie(design, variable):
    """Return what makes a variable the same over doublet counts: name, owner, range, options."""
    flat = variable.paths[0]
    return (_split(flat)[1], _owner(design, flat)[0], variable.low, variable.high, variable.options)


def _stays(path, off):
    """Return whether the module of the flat name ``path`` stays in a structure."""
    module = path.rpartition(".")[0]
    return not any(module == name or module.startswith(name + ".") for name in off)


def _chosen(variable, number):
    """Return the value of a variable at ``number``: a float, an integer or an option."""
    if variable.options is not None:
        return variable.options[int(number)]
    return int(round(number)) if variable.integer else float(number)


def _built(design, values, structure):
    """Return the plant of a structure with ``values`` set: the values first, then the bypass."""
    valued = deepcopy(design)
    for flat, number in values.items():
        path, _, parameter = flat.rpartition(".")
        valued._set_si_params(path, {parameter: number})
    return superstructure.concrete(valued, structure, Plant)


def _evaluated(shared, items):
    """Return the outcome ``(metrics, reason, violation)`` of each ``(design, values, structure)``.

    It runs in a worker process when the runtime has several.
    """
    case, plan, names = shared
    found = []
    for design, values, structure in items:
        plant = _built(design, values, structure)
        found.append(run_trials(Shared(plant), case, plan, [{}], names, True)[0])
    return found


def _judged(outcome, names):
    """Return ``(metrics, reason, violation)`` with an objective that is no number infeasible."""
    metrics, reason, violation = outcome
    for name in names:
        value = metrics.get(name, measure(None, "-", reason)).value
        if reason is None and (value is None or not np.isfinite(value)):
            reason, violation = metrics[name].reason or NOT_A_NUMBER, LARGEST_VIOLATION
    return metrics, reason, violation


class _Archive:
    """Every candidate the search judged, by the key of its active genes."""

    def __init__(self, space, case, plan, names, signs):
        """Judge candidates of ``space`` on ``case``, reading ``names`` with their ``signs``."""
        self.space, self.case, self.plan = space, case, plan
        self.names, self.signs = names, signs
        self.outcomes, self.entries, self.valid = {}, {}, {}
        self.evaluations = self.invalid = 0

    def _validity(self, design, structure, count):
        """Return whether a structure gives a valid plant, judged once per count."""
        key = (count, tuple(structure.values()))
        if key not in self.valid:
            self.valid[key] = not superstructure.is_valid(design, structure, Plant)[1]
        return self.valid[key]

    def judge(self, genomes, budget):
        """Return the objectives and violations of ``genomes``, simulating at most ``budget``."""
        keys, waiting = [], {}
        for genome in genomes:
            structure = self.space.structure(genome)
            off = superstructure.off(self.space.plant, structure)
            design, found, active = self.space.active(genome, off)
            key = genetic.key(genome, self.space.genes, active)
            keys.append(key)
            if key in self.outcomes or key in waiting:
                continue
            if not self._validity(design, structure, self.space.count(genome)):
                self.invalid += 1
                self.outcomes[key] = None
                continue
            if len(waiting) < budget:
                values = self.space.values(genome, found)
                waiting[key] = (design, values, structure, genome)
        items = [entry[:3] for entry in waiting.values()]
        shared = (self.case, self.plan, set(self.names))
        for key, outcome in zip(waiting, mapped_batches(_evaluated, shared, items)):
            self.outcomes[key] = _judged(outcome, self.names)
            self.entries[key] = waiting[key]
        self.evaluations += len(items)
        return keys, len(items)

    def scores(self, keys):
        """Return ``(objectives, violations)`` of judged keys; one not judged is the worst."""
        objectives, violations = [], []
        for key in keys:
            outcome = self.outcomes.get(key)
            if outcome is None:
                objectives.append([np.inf] * len(self.names))
                violations.append(INVALID)
                continue
            metrics, reason, violation = outcome
            objectives.append(
                [
                    np.inf if reason is not None else sign * metrics[name].value
                    for name, sign in zip(self.names, self.signs)
                ]
            )
            violations.append(violation if reason is not None else 0.0)
        return np.array(objectives, dtype=float), np.array(violations, dtype=float)

    def design(self, key):
        """Return the ``Design`` of a judged key."""
        design, values, structure, genome = self.entries[key]
        metrics, reason, violation = self.outcomes[key]
        return _design(
            self.space,
            self.case,
            design,
            values,
            structure,
            genome,
            outcome=(
                metrics,
                reason,
                violation,
            ),
        )


def _design(space, case, design, values, structure, genome, outcome):
    """Return the ``Design`` of a candidate: its plant, its metrics and its parameters."""
    metrics, reason, violation = outcome
    plant = _built(design, values, structure)
    parameters = dict(structure)
    if space.counted:
        parameters[DOUBLETS] = units.Quantity(space.count(genome), "-")
    for index, variable in space.base(space.count(genome))[1]:
        if not any(
            _stays(path, superstructure.off(space.plant, structure)) for path in variable.paths
        ):
            continue
        chosen = _chosen(variable, genome[index])
        if variable.options is None:
            chosen = units.Quantity(chosen, unit_of(design, case, variable.paths[0]))
        parameters[variable.name] = chosen
    return Design(
        structure=dict(structure),
        plant=plant,
        metrics=metrics,
        feasible=reason is None,
        reason=reason,
        violation=float(violation) if reason is not None else 0.0,
        parameters=parameters,
    )


def _objectives(objectives):
    """Return ``(names, signs)`` of one objective or a list of them; a ``-`` maximises."""
    given = [objectives] if isinstance(objectives, str) else objectives
    if (
        not isinstance(given, (list, tuple))
        or not given
        or not all(isinstance(item, str) for item in given)
    ):
        raise ValidationError(
            f"study.evolve: objectives = {objectives!r}; expected a metric or a list of metrics",
            path="objectives",
            code="invalid_value",
        )
    names = [checked_metric(item.removeprefix("-")) for item in given]
    if len(set(names)) != len(names):
        raise ValidationError(
            f"study.evolve: objectives = {given!r}; expected each metric once",
            path="objectives",
            code="invalid_value",
        )
    return names, [-1.0 if item.startswith("-") else 1.0 for item in given]


def _whole(name, value, low):
    """Return ``value`` when it is an integer of at least ``low``, else raise."""
    if isinstance(value, bool) or not isinstance(value, int) or value < low:
        raise ValidationError(
            f"study.evolve: {name} = {value!r}; expected an integer of at least {low}",
            path=name,
            code="invalid_value",
        )
    return value


def _polished(archive, designs, polish, population, seed, plan):
    """Return ``(designs, simulations)`` of a ``minimize`` of each of the first ``polish``.

    Each search starts from the design and searches the ranges its plant keeps on the first
    objective, ``population`` simulations for each doublet count; its best plant is run once
    more to read every objective, and joins the front.
    """
    found, simulations = [], 0
    name, sign = archive.names[0], archive.signs[0]
    for design in designs[:polish]:
        plant = design["plant"]
        if not variables(plant) and counts(plant) == [None]:
            continue
        objective = name if sign > 0 else f"-{name}"
        search = minimize(plant, archive.case, objective, population, seed, plan=plan)
        simulations += search["evaluations"]
        best = search["best"]["plant"]
        if best is None:
            continue
        outcome = run_trials(Shared(best), archive.case, plan, [{}], set(archive.names), True)[0]
        simulations += 1
        metrics, reason, violation = _judged(outcome, archive.names)
        found.append(
            Design(
                structure=dict(design["structure"]),
                plant=best,
                metrics=metrics,
                feasible=reason is None,
                reason=reason,
                violation=float(violation) if reason is not None else 0.0,
                parameters=dict(design["parameters"])
                | {key: value for key, value in search["best"].parts["parameters"].items()},
            )
        )
    return found, simulations


def _final(archive, designs):
    """Return ``(front, best)`` of the designs: the first front, the best on the first objective."""
    signs = archive.signs
    objectives = np.array(
        [
            [
                np.inf if not item["feasible"] else sign * item["metrics"][name].value
                for name, sign in zip(archive.names, signs)
            ]
            for item in designs
        ],
        dtype=float,
    )
    violations = np.array([item["violation"] for item in designs], dtype=float)
    front, crowding = genetic.rank(objectives, violations)
    ordered = [index for index in genetic.order(front, crowding) if front[index] == 0]
    if len(archive.names) == 1 or violations[ordered[0]] > 0:
        ordered = ordered[:1]
    ordered.sort(key=lambda index: objectives[index][0])
    chosen = [designs[index] for index in ordered]
    best = min(
        range(len(designs)), key=lambda index: (violations[index], objectives[index][0], index)
    )
    return chosen, designs[best]


def evolve(
    plant,
    case,
    objectives,
    evaluations,
    seed,
    *,
    population,
    polish,
    plan=None,
    on_progress=None,
):
    """Return the best structures and designs of a superstructure, by a genetic algorithm.

    The genome holds every choice the plant states: whether each optional module is on
    (``set_optional``), the group of each choice (``set_choice``), the number of doublets when
    ``size.doublets`` has a range, and the variables of ``gm.study.minimize`` (every ``range``
    and ``options`` of a leaf, tied by role). A gene of a module that is off is ignored. With one
    objective it is a genetic algorithm; with two or more it is NSGA-II: the candidates are
    ranked in fronts of non-domination and, within a front, by crowding distance. A feasible
    candidate beats every infeasible one, and infeasible ones are ranked by their violation, as
    in ``minimize``. Parents are chosen by binary tournament; continuous and integer genes cross
    by simulated binary crossover and mutate by polynomial mutation, the choices cross uniformly
    and mutate by a random reset; each generation keeps the best of the parents and children.

    The first generation is the plant's own values (clipped to the ranges) in each valid structure,
    in the order of ``plant.structures()`` while they fit, then random candidates. A candidate whose
    structure gives no valid plant (``plant.with_structure(...).check()`` has an error) is
    refused before any simulation and counted in ``invalid``. A candidate equal to one judged
    before in the genes that matter is not simulated again. The trials of a generation run in the
    worker processes of ``gm.runtime.settings(processes=n)``; the same seed gives the same result,
    whatever ``n``. Each trial is judged as in ``minimize``. The search ends when ``evaluations``
    simulations have run, or after a number of generations in a row (``STALL``) without a new one.

    With ``polish`` above 0, each of the first ``polish`` designs of the result (ordered by the
    first objective) is searched again by ``gm.study.minimize`` in the ranges its plant keeps,
    on the first objective, with ``population`` evaluations for each doublet count (the budget of
    ``minimize``) and the same seed; its best plant is run once more for every objective and joins
    the designs. These simulations come on top of ``evaluations`` and count in the result.

    Parameters
    ----------
    plant : Plant
        A plant with values, with optional modules and choices and the ranges and options to
        search; a plant with neither is searched in its values alone.
    case : Case
        What the plant is asked to do, as for ``minimize``.
    objectives : str or list of str
        The metric to minimise, or several (``["lcts", "co2"]``); a leading ``"-"`` maximises.
    evaluations : int
        The largest number of simulations of the genetic search, at least ``population``.
    seed : int
        Seed of the search; the same call gives the same result.
    population : int
        Candidates in each generation, at least 2.
    polish : int
        The number of designs searched again by ``minimize``; 0 for none. ``population`` must
        then be at least five per variable of the plant, the budget ``minimize`` needs.
    plan : DataFrame, optional
        The run input held fixed over the trials, as for ``minimize``.
    on_progress : callable, optional
        ``on_progress(done, total)`` after each finished trial of the genetic search, ``total``
        being ``evaluations``; ``done`` reaches it when the search ends, before ``polish``.
        Raising ``gm.errors.Cancelled`` stops the search.

    Returns
    -------
    Evolution
        ``{front, best, history, evaluations, invalid}``: ``front`` the designs no other beats
        on every objective (the best one alone for one objective), each a ``Design``
        ``{structure, plant, metrics, feasible, reason, violation, parameters}``; ``best`` the
        design best on the first objective (the least violating one when none is feasible);
        ``history`` per generation ``{generation, evaluations, best, front}``: the simulations so
        far, the best value of each objective among the feasible candidates so far (``None``
        without one) and the size of the first front; ``evaluations`` the number of simulations;
        ``invalid`` the candidates refused for their structure.

    Raises
    ------
    ValidationError
        The issues of ``gm.check``; ``invalid_design`` when no structure is valid or the plant
        states nothing to search; ``invalid_value`` for a setting out of its range.
    """
    raise_issues(check(plant, case))
    names, signs = _objectives(objectives)
    space = _checked(plant, evaluations, seed, population, polish)
    archive = _Archive(space, case, plan, names, signs)
    with counting(on_progress, evaluations) as count:
        history = _search(archive, np.random.default_rng(seed), population, evaluations)
        if count is not None:
            count.reach(evaluations)
    designs = [archive.design(key) for key in archive.entries]
    if not designs:
        raise ValidationError(
            "study.evolve: no candidate was simulated; every structure drawn was refused",
            path="optional",
            code="invalid_design",
        )
    polished, extra = _polished(archive, _ordered(archive, designs), polish, population, seed, plan)
    front, best = _final(archive, designs + polished)
    return Evolution(
        front=front,
        best=best,
        history=history,
        evaluations=archive.evaluations + extra,
        invalid=archive.invalid,
    )


def _checked(plant, evaluations, seed, population, polish):
    """Return the ``_Space`` of ``plant`` after checking the settings of ``evolve``."""
    _whole("population", population, 2)
    _whole("evaluations", evaluations, population)
    _whole("polish", polish, 0)
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValidationError(
            f"study.evolve: seed = {seed!r}; expected an integer", path="seed", code="invalid_value"
        )
    space = _Space(plant)
    if not space.genes:
        raise ValidationError(
            "study.evolve: the plant states no optional module, choice, range or options; expected "
            "at least one to search",
            path="params",
            code="invalid_design",
        )
    if polish and population < POPULATION_PER_VARIABLE * (len(space.genes) - space.structural):
        raise ValidationError(
            f"study.evolve: population = {population}; polish searches with minimize, which needs "
            f"at least {POPULATION_PER_VARIABLE} per variable",
            path="population",
            code="invalid_value",
        )
    space.valid = superstructure.valid(plant, Plant)
    if not space.valid:
        raise ValidationError(
            "study.evolve: no structure of the optional modules and choices gives a valid plant",
            path="optional",
            code="invalid_design",
        )
    return space


def _search(archive, rng, population, evaluations):
    """Run the generations until the budget is spent or the search stalls; return the history.

    The draws are, in order: the random part of the first generation, then for each generation
    the two tournaments and the children (``genetic.offspring``).
    """
    genes = archive.space.genes
    own = [archive.space.start(item) for item in archive.space.valid[:population]]
    members = np.vstack([own, genetic.random_genomes(genes, population - len(own), rng)])
    keys, _ = archive.judge(members, evaluations)
    history, stalled = [_generation(archive, 0, keys)], 0
    while archive.evaluations < evaluations and stalled < STALL:
        front, crowding = genetic.rank(*archive.scores(keys))
        first = genetic.tournament(front, crowding, population, rng)
        second = genetic.tournament(front, crowding, population, rng)
        children = genetic.offspring(
            members[first],
            members[second],
            genes,
            rng,
            crossover=CROSSOVER,
            eta_crossover=ETA_CROSSOVER,
            eta_mutation=ETA_MUTATION,
            mutation=1.0 / len(genes),
        )
        child_keys, ran = archive.judge(children, evaluations - archive.evaluations)
        stalled = 0 if ran else stalled + 1
        pooled, pooled_keys = np.vstack([members, children]), keys + child_keys
        front, crowding = genetic.rank(*archive.scores(pooled_keys))
        kept = genetic.order(front, crowding)[:population]
        members, keys = pooled[kept], [pooled_keys[index] for index in kept]
        history.append(_generation(archive, len(history), keys))
    return history


def _ordered(archive, designs):
    """Return the designs best first on the first objective, the feasible ones first."""
    name, sign = archive.names[0], archive.signs[0]
    return sorted(
        designs,
        key=lambda item: (
            item["violation"],
            sign * item["metrics"][name].value if item["feasible"] else 0.0,
        ),
    )


def _generation(archive, number, keys):
    """Return the history entry of a generation: simulations so far, best values, front size."""
    feasible = [
        archive.outcomes[key]
        for key in archive.outcomes
        if archive.outcomes[key] is not None and archive.outcomes[key][1] is None
    ]
    best = {}
    for name, sign in zip(archive.names, archive.signs):
        values = [sign * outcome[0][name].value for outcome in feasible]
        best[name] = None if not values else sign * min(values)
    objectives, violations = archive.scores(list(dict.fromkeys(keys)))
    front, _ = genetic.rank(objectives, violations)
    return {
        "generation": number,
        "evaluations": archive.evaluations,
        "best": best,
        "front": int(np.sum((front == 0) & (violations == 0))),
    }
