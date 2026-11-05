"""Search of the structures and the values a plant states, by a genetic algorithm (NSGA-II)."""

import time
from copy import deepcopy
from dataclasses import replace

import numpy as np
import pandas as pd

from gemini import units
from gemini._utils.jsonable import to_plain
from gemini.engine.check import check
from gemini.errors import Cancelled, ValidationError
from gemini.errors.base import raise_issues
from gemini.plants import Plant
from gemini.plants._utils import superstructure
from gemini.plants._utils.resize import resized
from gemini.study._utils import evolution, genetic
from gemini.study._utils.parallel import mapped_batches
from gemini.study._utils.progress import counting
from gemini.study._utils.shared import Shared
from gemini.study._utils.shown import shown
from gemini.study._utils.target import unit_of
from gemini.study._utils.trial import LARGEST_VIOLATION, checked_metric, run_trials
from gemini.study._utils.variables import DOUBLETS, _owner, _split, counts, variables
from gemini.study.minimize import NOT_A_NUMBER, POPULATION_PER_VARIABLE, minimize, trials_of
from gemini.units.shapes import measure

CROSSOVER = 0.9
"""Probability that a pair of parents crosses: the value of Deb's NSGA-II."""
ETA_CROSSOVER = 15.0
"""Distribution index of the simulated binary crossover: children near their parents."""
ETA_MUTATION = 20.0
"""Distribution index of the polynomial mutation: small steps, now and then a large one."""
STALL = 10
"""Generations in a row without a new simulation after which the search ends: it has seen all."""
RETRIES = 5
"""Times a child equal to a candidate judged before is mutated again before it is kept as it is."""
INVALID = LARGEST_VIOLATION + 1.0
"""The violation of a structure whose plant is not valid: worse than any trial that ran."""
LOCAL_SHARE = 0.5
"""The share of a generation's children that are local steps from the best candidates: half."""
STEP = 0.25
"""The first local step, a share of the range of a value; it halves once both directions failed."""
SMALLEST_STEP = 0.01
"""The smallest local step: below it the step starts again from ``STEP``."""
ENUMERATED = 256
"""The most structures judged one by one before the search; above, each is judged when drawn."""
STOP_KEYS = ("generations", "seconds")
"""The keys of ``stop``: generations without a new design on the front, and a time limit."""
_PLANTS = {}
"""The plants of the structures built in this process during one ``evolve``, by design id,
structure and the values of the plant itself: a structure is read once, not once per batch."""


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
            "reason": to_plain(shown(self["reason"])),
            "violation": self["violation"],
            "metrics": {name: shown(value).to_dict() for name, value in self["metrics"].items()},
            "parameters": to_plain(shown(self["parameters"])),
            "plant": None if self["plant"] is None else self["plant"].to_dict(),
        }


class Evolution(dict):
    """The result of ``evolve``: ``{front, best, history, evaluations, invalid, ...}``.

    ``front`` is a list of ``Design``, ``best`` the ``Design`` best on the first objective,
    ``history`` one entry per generation and ``evaluations`` the number of simulations;
    ``invalid`` counts the candidates drawn with a refused structure (moved to the nearest valid
    structure when one is known, else refused before any simulation).
    ``structures`` gives the best design of each valid structure, ``rejected`` each structure
    refused with its reasons, ``objectives`` the objectives as given and ``budget`` what was spent
    and why the search stopped. ``to_dict`` gives it all as plain JSON, ``to_frame`` the front as
    a table and ``explain`` a short text.
    """

    def to_dict(self):
        """Return the result as plain JSON in display units; a design's plant as its plant file.

        ``structures`` holds no plant: the plant of a structure's best design is that structure
        with its parameters.
        """
        return {
            "objectives": list(self["objectives"]),
            "best": self["best"].to_dict(),
            "front": [item.to_dict() for item in self["front"]],
            "structures": [_summary(item) for item in self["structures"]],
            "rejected": to_plain(self["rejected"]),
            "history": to_plain(self["history"]),
            "budget": dict(self["budget"]),
            "evaluations": self["evaluations"],
            "invalid": self["invalid"],
        }

    def to_frame(self):
        """Return the front as a table: one row per design, a column per structure key and metric.

        The metrics are in display units, the column named ``<metric> [<unit>]``, then
        ``feasible`` and ``reason``.
        """
        rows = []
        for design in self["front"]:
            row = dict(design["structure"])
            for name, value in design["metrics"].items():
                plain = shown(value)
                row[f"{name} [{plain.unit}]"] = plain.value
            rows.append(row | {"feasible": design["feasible"], "reason": design["reason"]})
        return pd.DataFrame(rows)

    def explain(self):
        """Return a short text of the search: budget, front, best, each structure and why."""
        return evolution.explained(self.to_dict())


def structure_plant(plant, structure, parameters):
    """Return the ordinary plant of one structure of an ``evolve`` study, with its parameters.

    ``plant`` is the superstructure the study searched (as given to ``evolve``), ``structure`` a
    design's ``structure`` and ``parameters`` its ``parameters``, both as ``Evolution.to_dict``
    gives them (a quantity as ``{value, unit}`` in display units, an option as itself) or as the
    ``Design`` holds them. The plant is built as ``evolve`` built it: the structure's doublet count,
    each value the search set, then the modules the structure leaves out bypassed. It is a new
    plant; ``plant`` is not changed.

    Parameters
    ----------
    plant : Plant
        The superstructure of the study.
    structure : dict
        ``{optional module or choice: value}``, as ``Design["structure"]``.
    parameters : dict
        ``{name: quantity or option}``, as ``Design["parameters"]``; a value the structure does not
        use may be absent.

    Returns
    -------
    Plant
        The plant of that structure.

    Raises
    ------
    ValidationError
        ``invalid_value`` for a structure the superstructure does not have, ``missing_value`` for
        a parameter the structure uses that ``parameters`` lacks.
    """
    space = _Space(plant)
    names = space.structure_names
    if set(structure) != set(names):
        raise ValidationError(
            f"structure_plant: structure = {sorted(structure)}; expected the keys {names}",
            code="invalid_value",
        )
    for index, name in enumerate(names):
        if structure[name] not in space.sides[index][0]:
            raise ValidationError(
                f"structure_plant: structure.{name} = {structure[name]!r}; expected one of "
                f"{list(space.sides[index][0])}",
                code="invalid_value",
            )
    count = None
    if space.counted:
        count = int(round(_si(parameters, DOUBLETS)))
    design, found = space.base(count)
    off = superstructure.off(plant, structure)
    values = {}
    for _, variable in found:
        staying = [path for path in variable.paths if _stays(path, off)]
        if not staying:
            continue
        if variable.options is not None:
            if variable.name not in parameters:
                raise ValidationError(
                    f"structure_plant: parameters.{variable.name} is missing; expected one of "
                    f"{list(variable.options)}",
                    code="missing_value",
                )
            chosen = parameters[variable.name]
        else:
            chosen = _si(parameters, variable.name)
            chosen = int(round(chosen)) if variable.integer else chosen
        values.update({path: chosen for path in staying})
    return _built(design, values, structure)


def _si(parameters, name):
    """Return the SI number of one parameter: a ``Quantity``, its dict, or a plain number."""
    if name not in parameters:
        raise ValidationError(
            f"structure_plant: parameters.{name} is missing; expected the value the study set",
            code="missing_value",
        )
    value = parameters[name]
    if isinstance(value, dict):
        value = units.Quantity.from_dict(value)
    if isinstance(value, units.Quantity):
        return float(value.si)
    return float(value)


def _summary(item):
    """Return the plain form of the summary of one structure, its best design without a plant."""
    best = None if item["best"] is None else item["best"].to_dict() | {"plant": None}
    return {key: value for key, value in item.items() if key != "best"} | {"best": best}


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
        self.places = _places(plant)
        self.ties = {}
        for count in sizes:
            design = plant if count is None else resized(plant, count)
            for tie, variable in self._untied(design):
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
        self.valid, self.rejected = [], []

    def _add(self, name, kind, low, high, options, variable=None):
        """Add a gene and what it stands for."""
        self.genes.append(genetic.Gene(name, kind, float(low), float(high)))
        self.sides.append((options, variable))

    def _untied(self, design):
        """Return ``(tie, variable)`` of the variables of ``design``, split by structure place.

        ``minimize`` ties the leaves of one role and range (three chillers, one capacity); here
        leaves of modules that are on and off in different structures are apart, so that two
        alternatives keep their own sizes.
        """
        found = []
        for variable in variables(design):
            groups = {}
            for flat in variable.paths:
                groups.setdefault(self.places.get(_module(flat)), []).append(flat)
            for place, paths in groups.items():
                name = variable.name if len(groups) == 1 else _split_name(variable, place, paths)
                part = replace(variable, name=name, paths=tuple(paths))
                found.append(((_tie(design, variable), place), part))
        return found

    def structure(self, genome):
        """Return the structure dict of a genome."""
        return {
            gene.name: self.sides[index][0][int(genome[index])]
            for index, gene in enumerate(self.genes[: self.structural])
        }

    @property
    def structure_names(self):
        """Return the names of the structure genes, in order."""
        return [gene.name for gene in self.genes[: self.structural]]

    def start_structure(self, structure):
        """Return the structure genes of a structure dict."""
        return [self.sides[index][0].index(structure[name]) for index, name in enumerate(structure)]

    def count(self, genome):
        """Return the doublet count of a genome, ``None`` for a plant without one."""
        return int(genome[self.structural]) if self.counted else None

    def base(self, count):
        """Return the plant on ``count`` doublets and the genes of its variables."""
        if count not in self.variables:
            design = self.plant if count is None else resized(self.plant, count)
            found = [(self.ties[tie], item) for tie, item in self._untied(design)]
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

    def values(self, genome, found, off):
        """Return ``{flat name: SI value}`` of the variables of a genome, of modules that stay."""
        values = {}
        for index, variable in found:
            chosen = _chosen(variable, genome[index])
            values.update({path: chosen for path in variable.paths if _stays(path, off)})
        return values

    def start(self, structure):
        """Return the genome of the plant's own values, clipped, in ``structure``.

        A variable takes the value of its first module that stays.
        """
        genome = np.zeros(len(self.genes))
        for index, name in enumerate(structure):
            genome[index] = self.sides[index][0].index(structure[name])
        count = self.plant.size.get("doublets")
        if self.counted:
            gene = self.genes[self.structural]
            genome[self.structural] = min(max(count, gene.low), gene.high)
        design, found = self.base(self.count(genome))
        off = superstructure.off(self.plant, structure)
        for index, variable in found:
            genome[index] = self._own(design, variable, off, self.genes[index])
        return genome

    @staticmethod
    def _own(design, variable, off, gene):
        """Return the gene value of the plant's own value of a variable, clipped to its range."""
        staying = [flat for flat in variable.paths if _stays(flat, off)] or variable.paths
        path, _, parameter = staying[0].rpartition(".")
        held = getattr(design.get_submodule(path), parameter, None)
        if variable.options is not None:
            return variable.options.index(held) if held in variable.options else 0
        if isinstance(held, (int, float)):
            return min(max(float(held), gene.low), gene.high)
        return (gene.low + gene.high) / 2

    def normalised(self, genome, active):
        """Return ``genome`` with every gene that does not matter set to its plant's own value."""
        if not hasattr(self, "_neutral"):
            first = self.valid[0] if self.valid else superstructure.every(self.plant)[0]
            self._neutral = self.start(first)
        found = np.array(genome, dtype=float)
        unused = [index for index in range(len(self.genes)) if index not in set(active)]
        found[unused] = self._neutral[unused]
        return found


def _places(plant):
    """Return ``{module: place}``: the optional module, or ``(choice, group)``, a module is in."""
    found = {name: name for name in plant._optional}
    for choice, groups in plant._choices.items():
        for group, members in groups.items():
            found |= {member: f"{choice}={group}" for member in members}
    return found


def _module(flat):
    """Return the module path of a flat parameter name."""
    return flat.rpartition(".")[0]


def _split_name(variable, place, paths):
    """Return the name of the part of a tied variable at one place of the structure."""
    if len(paths) == 1:
        return paths[0]
    return f"{variable.name}@{place or 'fixed'}"


def _tie(design, variable):
    """Return what makes a variable the same over doublet counts: name, owner, range, options."""
    flat = variable.paths[0]
    return (_split(flat)[1], _owner(design, flat)[0], variable.low, variable.high, variable.options)


def _stays(path, off):
    """Return whether the module of the flat name ``path`` stays in a structure."""
    module = _module(path)
    return not any(module == name or module.startswith(name + ".") for name in off)


def _chosen(variable, number):
    """Return the value of a variable at ``number``: a float, an integer or an option."""
    if variable.options is not None:
        return variable.options[int(number)]
    return int(round(number)) if variable.integer else float(number)


def _structured(design, own, structure):
    """Return the plant of a structure with the values ``own`` of the plant itself, built once.

    The plant is shared: a caller copies it before it changes it (``Shared`` does).
    """
    key = (id(design), tuple(structure.items()), tuple(sorted(own.items())))
    if key not in _PLANTS:
        _PLANTS[key] = _built(design, own, structure)
    return _PLANTS[key]


def _built(design, values, structure):
    """Return the plant of a structure with ``values`` set: the values first, then the bypass."""
    valued = deepcopy(design)
    for flat, number in values.items():
        path, _, parameter = flat.rpartition(".")
        valued._set_si_params(path, {parameter: number})
    return superstructure.concrete(valued, structure, Plant)


def _failed(error):
    """Return the outcome of a candidate that could not be built or run: infeasible, its reason."""
    if isinstance(error, Cancelled):
        raise error
    return {}, f"{type(error).__name__}: {error}", LARGEST_VIOLATION


def _evaluated(shared, items):
    """Return the outcome ``(metrics, reason, violation)`` of each ``(design, values, structure)``.

    The candidates of one design and structure run as one batch on one plant (the values of the
    plant itself, a class plant's, set first, as they change the plant of the structure), each
    with what it gives alone. A candidate whose plant cannot be built or whose run raises is
    infeasible with the error as its reason. It runs in a worker process when the runtime has
    several.
    """
    case, plan, names = shared
    groups = {}
    for index, (design, values, structure) in enumerate(items):
        own = {k: v for k, v in values.items() if "." not in k}
        key = (id(design), tuple(structure.items()), tuple(sorted(own.items())))
        groups.setdefault(key, (design, own, structure, []))[3].append(index)
    found = [None] * len(items)
    for design, own, structure, members in groups.values():
        valued = [{k: v for k, v in items[i][1].items() if "." in k} for i in members]
        for index, outcome in zip(members, _batch(design, own, structure, valued, shared)):
            found[index] = outcome
    return found


def _batch(design, own, structure, valued, shared):
    """Return the outcomes of the values ``valued`` on the plant of one structure."""
    case, plan, names = shared
    try:
        plant = _structured(design, own, structure)
        return run_trials(Shared(plant), case, plan, valued, names, True, structural=True)
    except Exception as error:
        if len(valued) == 1:
            return [_failed(error)]
    found = []
    for values in valued:
        try:
            plant = _structured(design, own, structure)
            found.append(
                run_trials(Shared(plant), case, plan, [values], names, True, structural=True)[0]
            )
        except Exception as error:
            found.append(_failed(error))
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
        self.steps, self.moves, self.tried = {}, {}, set()

    def _validity(self, design, structure, count):
        """Return whether a structure gives a valid plant, judged once per count.

        On the plant's own doublet count the structures judged before the search are known.
        """
        key = (count, tuple(structure.values()))
        own = count == self.space.plant.size.get("doublets")
        if key not in self.valid and own and self.space.enumerated:
            self.valid[key] = structure in self.space.valid
        if key not in self.valid and own:
            self.valid[key] = _judged_structure(design, self.space, structure)
        if key not in self.valid:
            self.valid[key] = not superstructure.is_valid(design, structure, Plant)[1]
        return self.valid[key]

    def known(self, structure, count):
        """Return whether a structure is valid on ``count`` doublets; ``None`` when not judged."""
        if count == self.space.plant.size.get("doublets") and self.space.enumerated:
            return structure in self.space.valid
        return self.valid.get((count, tuple(structure.values())))

    def repaired(self, genomes, rng):
        """Return ``(genomes, repaired)``: refused structures moved to the nearest valid one.

        ``repaired`` is the mask of the genomes whose structure is known to be refused and was
        moved; a refused structure with no valid one known stays, and the search judges it.

        The valid structures are those enumerated before the search, or those judged valid on the
        same doublet count so far. The nearest changes the fewest structure genes; a tie is broken
        by a draw ``rng.integers``, made only for a refused genome with a tie.
        """
        space, found = self.space, np.array(genomes, dtype=float)
        refused = np.zeros(len(found), dtype=bool)
        for row, genome in enumerate(found):
            structure, count = space.structure(genome), space.count(genome)
            if self.known(structure, count) is not False:
                continue
            choices = self._valid_structures(count)
            if not choices:
                continue
            refused[row] = True
            genes = np.array([space.start_structure(item) for item in choices])
            distance = (genes != genome[: space.structural]).sum(axis=1)
            nearest = np.flatnonzero(distance == distance.min())
            chosen = nearest[int(rng.integers(len(nearest)))] if len(nearest) > 1 else nearest[0]
            found[row, : space.structural] = genes[chosen]
        return found, refused

    def _valid_structures(self, count):
        """Return the structures known to be valid on ``count`` doublets, in a fixed order."""
        if count == self.space.plant.size.get("doublets") and self.space.enumerated:
            return list(self.space.valid)
        return [
            dict(zip(self.space.structure_names, key[1]))
            for key, valid in self.valid.items()
            if valid and key[0] == count
        ]

    def keyed(self, genome):
        """Return ``(key, normalised genome, design, found, structure, off)`` of a genome."""
        structure = self.space.structure(genome)
        off = superstructure.off(self.space.plant, structure)
        design, found, active = self.space.active(genome, off)
        genome = self.space.normalised(genome, active)
        return genetic.key(genome, self.space.genes, active), genome, design, found, structure, off

    def judge(self, genomes, budget):
        """Return the keys and normalised genomes of ``genomes`` and the simulations run.

        At most ``budget`` new candidates are simulated; one past it is not judged.
        """
        keys, normal, waiting = [], [], {}
        for genome in genomes:
            key, genome, design, found, structure, off = self.keyed(genome)
            keys.append(key)
            normal.append(genome)
            if key in self.outcomes or key in waiting:
                continue
            if not self._validity(design, structure, self.space.count(genome)):
                self.invalid += 1
                self.outcomes[key] = None
                continue
            if len(waiting) < budget:
                values = self.space.values(genome, found, off)
                waiting[key] = (design, values, structure, genome)
        items = [entry[:3] for entry in waiting.values()]
        shared = (self.case, self.plan, set(self.names))
        for key, outcome in zip(waiting, mapped_batches(_evaluated, shared, items)):
            self.outcomes[key] = _judged(outcome, self.names)
            self.entries[key] = waiting[key]
        self.evaluations += len(items)
        return keys, np.array(normal), len(items)

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

    def front(self):
        """Return the keys of the feasible designs judged so far that no other beats."""
        judged = [key for key in self.entries if self.outcomes[key][1] is None]
        if not judged:
            return []
        objectives, _ = self.scores(judged)
        return [judged[index] for index in evolution.non_dominated(objectives)]

    def design(self, key):
        """Return the ``Design`` of a judged key, without its plant (``with_plant`` adds it)."""
        design, values, structure, genome = self.entries[key]
        found = _design(
            self.space, self.case, design, values, structure, genome, self.outcomes[key]
        )
        found.source = (design, values, structure)
        return found


def _with_plant(design):
    """Return ``design`` with its plant built, once; a design of polish has its plant already."""
    source = getattr(design, "source", None)
    if design["plant"] is None and source is not None:
        try:
            design["plant"] = _built(*source)
        except Exception:
            design["plant"] = None
        design.source = None
    return design


def _design(space, case, design, values, structure, genome, outcome):
    """Return the ``Design`` of a candidate: its plant, its metrics and its parameters."""
    metrics, reason, violation = outcome
    parameters = dict(structure)
    if space.counted:
        parameters[DOUBLETS] = units.Quantity(space.count(genome), "-")
    off = superstructure.off(space.plant, structure)
    for index, variable in space.base(space.count(genome))[1]:
        if not any(_stays(path, off) for path in variable.paths):
            continue
        chosen = _chosen(variable, genome[index])
        if variable.options is None:
            chosen = units.Quantity(chosen, unit_of(design, case, variable.paths[0]))
        parameters[variable.name] = chosen
    return Design(
        structure=dict(structure),
        plant=None,
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


def checked_stop(stop):
    """Return ``stop`` as ``{generations, seconds}`` (each ``None`` when absent), or raise.

    ``generations`` is a whole number of at least 1, ``seconds`` a positive number; ``None`` is a
    search that spends its whole budget.
    """
    if stop is None:
        return dict.fromkeys(STOP_KEYS)
    if not isinstance(stop, dict) or not stop or any(key not in STOP_KEYS for key in stop):
        raise ValidationError(
            f"study.evolve: stop = {stop!r}; expected a dict with 'generations' (generations "
            "without a new design on the front) and/or 'seconds' (a time limit)",
            path="stop",
            code="invalid_value",
        )
    generations, seconds = stop.get("generations"), stop.get("seconds")
    if generations is not None:
        _whole("stop.generations", generations, 1)
    if seconds is not None and (
        isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or seconds <= 0
    ):
        raise ValidationError(
            f"study.evolve: stop.seconds = {seconds!r}; expected a positive number",
            path="stop.seconds",
            code="invalid_value",
        )
    return {"generations": generations, "seconds": seconds}


def _polished(archive, designs, polish, population, seed, plan):
    """Return ``(designs, simulations)`` of a ``minimize`` of each of the first ``polish``.

    Each search starts from the design and searches the ranges its plant keeps on the first
    objective, ``population`` simulations for each doublet count; its best plant is run once
    more to read every objective, and joins the front.
    """
    found, simulations = [], 0
    name, sign = archive.names[0], archive.signs[0]
    for design in designs[:polish]:
        plant = _with_plant(design)["plant"]
        if plant is None or (not variables(plant) and counts(plant) == [None]):
            continue
        objective = name if sign > 0 else f"-{name}"
        search = minimize(plant, archive.case, objective, population, seed, plan=plan)
        simulations += search["evaluations"]
        best = search["best"]["plant"]
        if best is None:
            continue
        outcome = run_trials(
            Shared(best), archive.case, plan, [{}], set(archive.names), True, structural=True
        )[0]
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


def _points(archive, designs):
    """Return ``(objectives, violations)`` of designs, objectives minimised, inf when infeasible."""
    objectives = np.array(
        [
            [
                np.inf if not item["feasible"] else sign * item["metrics"][name].value
                for name, sign in zip(archive.names, archive.signs)
            ]
            for item in designs
        ],
        dtype=float,
    )
    return objectives, np.array([item["violation"] for item in designs], dtype=float)


def _final(archive, designs):
    """Return ``(front, best)`` of the designs: the first front, the best on the first objective.

    Designs of one structure with the same metrics are one design of the front.
    """
    objectives, violations = _points(archive, designs)
    front, crowding = genetic.rank(objectives, violations)
    ordered = [index for index in genetic.order(front, crowding) if front[index] == 0]
    if len(archive.names) == 1 or violations[ordered[0]] > 0:
        ordered = ordered[:1]
    ordered.sort(key=lambda index: (tuple(objectives[index]), index))
    chosen, seen = [], set()
    for index in ordered:
        same = (tuple(designs[index]["structure"].items()), tuple(objectives[index]))
        if same not in seen:
            seen.add(same)
            chosen.append(designs[index])
    best = min(
        range(len(designs)), key=lambda index: (violations[index], objectives[index][0], index)
    )
    return chosen, designs[best]


def _structures(archive, designs):
    """Return per valid structure its simulations, how many are feasible and its best design."""
    found = []
    for structure in archive.space.valid:
        mine = [item for item in designs if item["structure"] == structure]
        best = None
        if mine:
            objectives, violations = _points(archive, mine)
            best = mine[min(range(len(mine)), key=lambda i: (violations[i], objectives[i][0], i))]
        found.append(
            {
                "structure": dict(structure),
                "evaluations": len(mine),
                "feasible": sum(item["feasible"] for item in mine),
                "best": best,
            }
        )
    return found


def _limits(plant, evaluations, population, polish):
    """Return the progress total of a search: the budget and the most ``polish`` can run."""
    if not polish:
        return evaluations
    return evaluations + polish * (trials_of(plant, population) + 1)


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
    stop=None,
):
    """Return the best structures and designs of a superstructure, by a genetic algorithm.

    The genome holds every choice the plant states: whether each optional module is on
    (``set_optional``), the group of each choice (``set_choice``), the number of doublets when
    ``size.doublets`` has a range, and the variables of ``gm.study.minimize`` (every ``range``
    and ``options`` of a leaf, tied by role); leaves of modules that are in different places of
    the structure (an optional module, a group of a choice, the fixed modules) are not tied, so
    that alternatives keep their own sizes. A gene of a module that is off is ignored: it takes the
    plant's own value, so two candidates that differ only there are one. With one objective it is
    a genetic algorithm; with two or more it is NSGA-II: the candidates are ranked in fronts of
    non-domination and, within a front, by crowding distance. A feasible candidate beats every
    infeasible one, and infeasible ones are ranked by their violation, as in ``minimize``. Parents
    are chosen by binary tournament; continuous and integer genes cross by simulated binary
    crossover and mutate by polynomial mutation, the choices cross uniformly and mutate by a
    random reset; the structure genes mutate with a probability of one over their number, the
    other genes of one over theirs. Half of the children are local steps, a compass search: half
    of those from the best candidate of the best structure, the others from the best candidates
    of the next structures (on each objective in turn) and, with two objectives or more, from
    members of the first front by crowding distance. A local step moves one value up or down by
    a share of its range (``STEP`` at first, halved per structure and value once both directions
    failed from the same candidate), or takes the next or previous option; a candidate that a
    step made is first stepped again the same way, twice as far. A child equal to a candidate
    judged before is mutated again (``RETRIES`` times at most). Each generation keeps the best of
    the parents and children.

    The first generation is the plant's own values (clipped to the ranges) in each valid
    structure, when they are no more than ``population`` (else in half of it, structures drawn at
    random), then random candidates. A candidate whose structure gives no valid plant
    (``plant.with_structure(...).check()`` has an error) is never simulated and counts in
    ``invalid``: when valid structures are known (all of them up to ``ENUMERATED``, else those
    judged so far) it takes the nearest one instead (fewest structure genes changed, a tie drawn
    at random), so the budget goes to valid structures; else it is refused. A candidate equal to
    one judged before in the genes that matter is not simulated again. The new candidates of a
    generation run in the worker processes of ``gm.runtime.settings(processes=n)``, those of one
    structure as one batch; the same seed gives the same result, whatever ``n``. Each trial is
    judged as in ``minimize``; a candidate whose plant cannot be built or whose run raises is
    infeasible with the error as its reason, and so is one that has no unit at all for a service
    of the case (a structure without cooling), which ``minimize`` does not hold against a trial
    since no value changes it. The search ends when ``evaluations`` simulations have run, after
    ``STALL`` generations in a row without a new simulation, or as ``stop`` says. The front is
    that of every design simulated.

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
        ``on_progress(done, total)`` after each finished trial, ``total`` being ``evaluations``
        and the most ``polish`` can run (``polish`` times the trials of ``minimize`` on the whole
        plant with ``population``, plus one each); ``done`` reaches it at the end. Raising
        ``gm.errors.Cancelled`` stops the search.
    stop : dict, optional
        When to end before the budget: ``{"generations": n}`` after ``n`` generations in a row with
        no new design on the feasible front, ``{"seconds": s}`` once the search has run ``s``
        seconds (the result then depends on the machine), or both. ``None`` spends the budget.

    Returns
    -------
    Evolution
        ``{front, best, history, evaluations, invalid, structures, rejected, objectives,
        budget}``: ``front`` the designs no other beats on every objective (the best one alone
        for one objective), each a ``Design`` ``{structure, plant, metrics, feasible, reason,
        violation, parameters}``; ``best`` the design best on the first objective (the least
        violating one when none is feasible); ``history`` per generation ``{generation,
        evaluations, best, front, hypervolume}``: the simulations so far, the best value of each
        objective among the feasible candidates so far (``None`` without one), the size of the
        feasible front so far and its hypervolume (objectives scaled between the best and worst
        of the final front, reference 1.1; ``None`` above two objectives); ``evaluations`` the
        number of simulations; ``invalid`` the candidates drawn with a refused structure;
        ``structures`` per valid structure ``{structure, evaluations, feasible, best}``;
        ``rejected`` per refused structure ``{structure, reasons}``; ``budget`` ``{evaluations,
        search, polish, invalid, generations, stopped}`` with ``stopped`` one of ``budget``,
        ``stalled``, ``converged``, ``seconds``.

    Raises
    ------
    ValidationError
        The issues of ``gm.check``; ``invalid_design`` when no structure is valid (with the reason
        of each) or the plant states nothing to search; ``invalid_value`` for a setting out of its
        range.
    """
    raise_issues(check(plant, case))
    names, signs = _objectives(objectives)
    limits = checked_stop(stop)
    _PLANTS.clear()
    space = _checked(plant, evaluations, seed, population, polish)
    archive = _Archive(space, case, plan, names, signs)
    total = _limits(plant, evaluations, population, polish)
    with counting(on_progress, total) as count:
        rng = np.random.default_rng(seed)
        history, stopped = _search(archive, rng, population, evaluations, limits)
        designs = [archive.design(key) for key in archive.entries]
        if not designs:
            raise ValidationError(
                "study.evolve: no candidate was simulated; every structure drawn was refused",
                path="optional",
                code="invalid_design",
            )
        ordered = _ordered(archive, designs)
        polished, extra = _polished(archive, ordered, polish, population, seed, plan)
        if count is not None:
            count.reach(total)
    return _result(archive, history, stopped, designs + polished, extra)


def _result(archive, history, stopped, designs, extra):
    """Return the ``Evolution`` of the designs: front, best, structures, history and budget."""
    front, best = _final(archive, designs)
    summaries = _structures(archive, designs)
    for design in [*front, best, *(item["best"] for item in summaries if item["best"])]:
        _with_plant(design)
    _PLANTS.clear()
    _hypervolumes(archive, history, front)
    names, signs = archive.names, archive.signs
    return Evolution(
        front=front,
        best=best,
        history=history,
        evaluations=archive.evaluations + extra,
        invalid=archive.invalid,
        structures=summaries,
        rejected=archive.space.rejected,
        objectives=[name if sign > 0 else f"-{name}" for name, sign in zip(names, signs)],
        budget={
            "evaluations": archive.evaluations + extra,
            "search": archive.evaluations,
            "polish": extra,
            "invalid": archive.invalid,
            "generations": len(history),
            "stopped": stopped,
        },
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
    _judge_structures(plant, space)
    return space


def _count(plant):
    """Return the number of structures of ``plant``, valid or not."""
    return int(np.prod([2] * len(plant._optional) + [len(g) for g in plant._choices.values()]))


def _judged_structure(plant, space, structure):
    """Judge one structure: add it to the valid or the refused ones of ``space``; return valid."""
    issues = superstructure.is_valid(plant, structure, Plant)[1]
    if issues:
        reasons = [f"{item.path}: {item.message}" for item in issues[:3]]
        space.rejected.append({"structure": structure, "reasons": reasons})
    else:
        space.valid.append(structure)
    return not issues


def _judge_structures(plant, space):
    """Set the valid structures of ``space`` and the refused ones with their reasons, or raise.

    Above ``ENUMERATED`` structures none is judged here: the search judges each when it draws it.
    """
    space.enumerated = _count(plant) <= ENUMERATED
    if not space.enumerated:
        return
    for structure in superstructure.every(plant):
        _judged_structure(plant, space, structure)
    if not space.valid:
        shown = "; ".join(
            f"{evolution.label(item['structure'])}: {item['reasons'][0]}"
            for item in space.rejected[:5]
        )
        raise ValidationError(
            f"study.evolve: no structure of the optional modules and choices gives a valid plant "
            f"({len(space.rejected)} refused): {shown}; expected at least one, see "
            "plant.with_structure(...).check()",
            path="optional",
            code="invalid_design",
        )


def _first(archive, rng, population):
    """Return the first generation: the plant's own values in the valid structures, then random."""
    space = archive.space
    chosen = space.valid if space.enumerated else _drawn_structures(archive, rng, population)
    if len(chosen) > population:
        picked = rng.choice(len(chosen), size=population // 2, replace=False)
        chosen = [chosen[index] for index in sorted(picked)]
    own = [space.start(item) for item in chosen]
    drawn = genetic.random_genomes(space.genes, population - len(own), rng)
    drawn, repaired = archive.repaired(drawn, rng)
    archive.invalid += int(repaired.sum())
    return np.vstack([*own, drawn]) if own else drawn


def _drawn_structures(archive, rng, population):
    """Return up to half of ``population`` valid structures drawn at random, for a large space.

    At most four draws per wanted structure are judged; with none valid, the first generation is
    random and the search judges what it draws.
    """
    space, wanted, found = archive.space, population // 2, []
    genomes = genetic.random_genomes(space.genes[: space.structural], 4 * wanted, rng)
    for genome in genomes:
        structure = space.structure(genome)
        if structure in found:
            continue
        if archive._validity(space.plant, structure, space.plant.size.get("doublets")):
            found.append(structure)
        if len(found) == wanted:
            break
    return found


def _rates(space):
    """Return the mutation probability of each gene: one over the number of its kind."""
    structural = max(space.structural, 1)
    rest = max(len(space.genes) - space.structural, 1)
    return np.array(
        [
            1.0 / structural if index < space.structural else 1.0 / rest
            for index in range(len(space.genes))
        ]
    )


def _leaders(archive, members, keys):
    """Return member indices of the best candidate of each structure, the best structures first.

    For each objective the structures are ordered by their best candidate on it (smallest
    violation, then the objective, then the index); the lists of the objectives are taken in
    turn, the first objective first, each member once. A candidate whose structure was refused
    is no leader.
    """
    objectives, violations = archive.scores(keys)
    width = archive.space.structural + int(archive.space.counted)
    lists = []
    for column in range(objectives.shape[1]):
        ordered = np.lexsort((np.arange(len(keys)), objectives[:, column], violations))
        seen, found = set(), []
        for index in ordered:
            structure = tuple(members[index][:width])
            if violations[index] >= INVALID or structure in seen:
                continue
            seen.add(structure)
            found.append(int(index))
        lists.append(found)
    leaders = []
    for row in range(max(len(found) for found in lists)):
        for found in lists:
            if row < len(found) and found[row] not in leaders:
                leaders.append(found[row])
    return leaders


def _spread(archive, keys, leaders):
    """Return member indices of the first front by crowding distance, each key once, no leader.

    With one objective there is none: the leaders are the search's whole local part.
    """
    if len(archive.names) == 1:
        return []
    front, crowding = genetic.rank(*archive.scores(keys))
    seen, found = {keys[index] for index in leaders}, []
    for index in genetic.order(front, crowding):
        if front[index] == 0 and keys[index] not in seen:
            seen.add(keys[index])
            found.append(int(index))
    return found


def _shares(leaders, spread, count):
    """Return ``[(member, children)]``: who gets the local children and how many.

    Half go to the first leader; of the rest, half in turn to the front members of ``spread``
    and the others in turn to the next leaders (all to one group when the other is empty).
    """
    if not leaders:
        return []
    shares = {leaders[0]: count - count // 2}
    rest, others = count // 2, leaders[1:]
    toward = rest // 2 if spread and others else (rest if spread else 0)
    for number in range(toward):
        member = spread[number % len(spread)]
        shares[member] = shares.get(member, 0) + 1
    for number in range(rest - toward):
        member = others[number % len(others)] if others else leaders[0]
        shares[member] = shares.get(member, 0) + 1
    return list(shares.items())


def _local(archive, members, keys, count, rng):
    """Return ``count`` local children around the best candidate of the best structures.

    Half go to the leader of the best structure (``_leaders``), the rest in turn to the leaders
    of the next ones. A child moves one value of a module that stays up or down by a step, a
    share of its range, or takes the next or previous option: a compass search. Each structure
    keeps a step per gene, ``STEP`` at first; once both directions of a gene were tried from the
    same leader with the same step, it halves (back to ``STEP`` below ``SMALLEST_STEP``). A
    leader that a local step made gets first that step again, twice as long (a pattern move);
    then the untried moves, in an order drawn once per leader (one ``rng.permutation``).
    """
    space, children = archive.space, []
    width = space.structural + int(space.counted)
    leaders = _leaders(archive, members, keys)
    spread = _spread(archive, keys, leaders)
    for leader, share in _shares(leaders, spread, count):
        if not share:
            continue
        genome, key = np.array(members[leader], dtype=float), keys[leader]
        structure = tuple(genome[:width])
        off = superstructure.off(space.plant, space.structure(genome))
        active = space.active(genome, off)[2][width:]
        moves = _untried(archive, structure, key, active)
        moves = [moves[index] for index in rng.permutation(len(moves))]
        last = archive.moves.get(key)
        if last is not None and last[0] in active:
            moves.insert(0, (last[0], last[1], min(last[2] * 2, 1.0), False))
        made = []
        for index, sign, step, counted in moves:
            if len(made) == share:
                break
            child = _moved(space.genes[index], genome, index, sign, step)
            if counted:
                archive.tried.add((structure, index, sign, key, step))
            found = archive.keyed(child)[0]
            if found in archive.outcomes or found == key:
                continue
            archive.moves[found] = (index, sign, step)
            made.append(child)
        children.extend(made + [genome] * (share - len(made)))
    return np.array(children).reshape(-1, len(space.genes))


def _untried(archive, structure, key, active):
    """Return the moves ``(gene, sign, step, True)`` not yet tried from leader ``key``.

    The step of a gene halves while both its directions were tried from this leader with it.
    """
    moves = []
    for index in active:
        step = archive.steps.get((structure, index), STEP)
        gene = archive.space.genes[index]
        while gene.kind != genetic.CATEGORICAL and all(
            (structure, index, sign, key, step) in archive.tried for sign in (1, -1)
        ):
            step = step / 2 if step / 2 >= SMALLEST_STEP else STEP
            archive.steps[(structure, index)] = step
            if step == STEP:
                break
        moves += [
            (index, sign, step, True)
            for sign in (1, -1)
            if (structure, index, sign, key, step) not in archive.tried
        ]
    return moves


def _moved(gene, genome, index, sign, step):
    """Return ``genome`` with gene ``index`` moved by ``step`` of its range in direction ``sign``.

    An option moves to the next or the previous one; an integer moves by one at least.
    """
    child = np.array(genome, dtype=float)
    if gene.kind == genetic.CATEGORICAL:
        child[index] = (child[index] + sign) % (gene.high + 1)
        return child
    moved = child[index] + sign * step * (gene.high - gene.low)
    if gene.kind == genetic.INTEGER:
        moved = round(moved) if round(moved) != child[index] else child[index] + sign
    child[index] = min(max(moved, gene.low), gene.high)
    return child


def _children(archive, members, keys, population, rng):
    """Return the children of a generation: tournament, crossover and mutation, new ones first.

    ``LOCAL_SHARE`` of them are local steps from the best candidates (``_local``). A child whose
    key is that of a candidate judged before, or of a child before it, is mutated again, at most
    ``RETRIES`` times; the draws are in a fixed order.
    """
    genes, rates = archive.space.genes, _rates(archive.space)
    local = int(population * LOCAL_SHARE)
    front, crowding = genetic.rank(*archive.scores(keys))
    first = genetic.tournament(front, crowding, population - local, rng)
    second = genetic.tournament(front, crowding, population - local, rng)
    children = genetic.offspring(
        members[first],
        members[second],
        genes,
        rng,
        crossover=CROSSOVER,
        eta_crossover=ETA_CROSSOVER,
        eta_mutation=ETA_MUTATION,
        mutation=rates,
    )
    if local:
        children = np.vstack([children, _local(archive, members, keys, local, rng)])
    children, repaired = archive.repaired(children, rng)
    archive.invalid += int(repaired.sum())
    return _unseen(archive, children, genes, rates, rng)


def _unseen(archive, children, genes, rates, rng):
    """Mutate again each child whose key was judged before or drawn earlier, ``RETRIES`` times."""
    seen = set(archive.outcomes)
    for _ in range(RETRIES):
        repeated = []
        for index, child in enumerate(children):
            key = archive.keyed(child)[0]
            if key in seen:
                repeated.append(index)
            else:
                seen.add(key)
        if not repeated:
            break
        again = children[repeated]
        children[repeated] = genetic.offspring(
            again,
            again,
            genes,
            rng,
            crossover=0.0,
            eta_crossover=ETA_CROSSOVER,
            eta_mutation=ETA_MUTATION,
            mutation=np.maximum(rates, 1.0 / len(genes)) * 2,
        )
        children = archive.repaired(children, rng)[0]
    return children


def _search(archive, rng, population, evaluations, limits):
    """Run the generations until the budget is spent or the search stops; return the history.

    Returns ``(history, stopped)``. The draws are, in order: the structures of the first
    generation when they are more than ``population``, its random part, then for each generation
    the two tournaments, the children and their mutations again.
    """
    started = time.monotonic()
    keys, members, _ = archive.judge(_first(archive, rng, population), evaluations)
    history, stalled, still = [_generation(archive, 0, keys)], 0, 0
    front = set(archive.front())
    while True:
        if archive.evaluations >= evaluations:
            return history, "budget"
        if stalled >= STALL:
            return history, "stalled"
        if limits["generations"] is not None and still >= limits["generations"]:
            return history, "converged"
        if limits["seconds"] is not None and time.monotonic() - started >= limits["seconds"]:
            return history, "seconds"
        children = _children(archive, members, keys, population, rng)
        child_keys, children, ran = archive.judge(children, evaluations - archive.evaluations)
        stalled = 0 if ran else stalled + 1
        pooled, pooled_keys = np.vstack([members, children]), keys + child_keys
        ranks, crowding = genetic.rank(*archive.scores(pooled_keys))
        kept = _kept(pooled_keys, ranks, crowding, population)
        members, keys = pooled[kept], [pooled_keys[index] for index in kept]
        now = set(archive.front())
        still = 0 if now != front else still + 1
        front = now
        history.append(_generation(archive, len(history), keys))


def _kept(keys, ranks, crowding, population):
    """Return the indices of the next generation: the best, each key once while there are enough."""
    ordered = list(genetic.order(ranks, crowding))
    seen, first, later = set(), [], []
    for index in ordered:
        (later if keys[index] in seen else first).append(index)
        seen.add(keys[index])
    return (first + later)[:population]


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
    """Return the history entry of a generation: simulations so far, best values, front so far."""
    feasible = [
        archive.outcomes[key]
        for key in archive.outcomes
        if archive.outcomes[key] is not None and archive.outcomes[key][1] is None
    ]
    best = {}
    for name, sign in zip(archive.names, archive.signs):
        values = [sign * outcome[0][name].value for outcome in feasible]
        best[name] = None if not values else sign * min(values)
    front = archive.front()
    return {
        "generation": number,
        "evaluations": archive.evaluations,
        "best": best,
        "front": len(front),
        "_front": front,
    }


def _hypervolumes(archive, history, front):
    """Set the hypervolume of each generation's front, scaled by the final front; drop its keys."""
    final = [item for item in front if item["feasible"]]
    if final:
        ideal, nadir = evolution.bounds(_points(archive, final)[0])
    for entry in history:
        keys = entry.pop("_front")
        if not final or not keys:
            entry["hypervolume"] = None if not final else 0.0
            continue
        points = archive.scores(keys)[0]
        entry["hypervolume"] = evolution.hypervolume(evolution.scale(points, ideal, nadir))
