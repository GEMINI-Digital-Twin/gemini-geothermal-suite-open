"""One plant on one case through the method of a study, with the same functions a caller uses."""

from gemini.engine.simulate import simulate
from gemini.evaluate import report as reported
from gemini.study._utils.uncertain import declared
from gemini.study._utils.variables import searchable
from gemini.study.evolve import evolve
from gemini.study.minimize import minimize, trials_of
from gemini.study.sample import sample
from gemini.study.sensitivity import sensitivity
from gemini.study.size import size


def _plain(study, plant, case):
    """Return ``(design, found, note)`` of the method ``run``: the plant as it is."""
    return plant, None, None


def _searched(study, plant, case):
    """Return ``(design, found, note)`` of ``minimize``: the best design of the search.

    A plant that states no range and no options is run as it is, with a note; so is one for which
    every trial failed.
    """
    if not searchable(plant):
        return plant, None, "the plant states no range and no options: run as it is"
    found = minimize(plant, case, study.objective, study.evaluations, study.seed)
    best = found["best"]["plant"]
    if best is None:
        return plant, found, "every trial failed: run as it is"
    return best, found, None


def _evolved(study, plant, case):
    """Return ``(design, found, note)`` of ``evolve``: the best design of the genetic search."""
    found = evolve(
        plant,
        case,
        list(study.objectives),
        study.evaluations,
        study.seed,
        population=study.population,
        polish=study.polish,
    )
    return found["best"]["plant"], found, None


def _drawn(study, plant, case):
    """Return ``(design, found, note)`` of ``sample``: the spread of the metrics."""
    return plant, sample(plant, case, study.names, study.samples, study.seed), None


def _moved(study, plant, case):
    """Return ``(design, found, note)`` of ``sensitivity``: the tornado of the metrics."""
    return plant, sensitivity(plant, case, study.names), None


METHODS = {"run": _plain, "minimize": _searched, "sample": _drawn, "sensitivity": _moved}
METHODS["evolve"] = _evolved
"""The function of each method of ``study.json``."""


def executed(study, plant, case):
    """Return ``(design, found, note, results, report)`` of ``plant`` on ``case`` for ``study``.

    The plant is sized first when the study prepares it, then the method runs, then the design it
    gives (the plant itself, or the best of a search) is simulated and reported.
    """
    prepared = size(plant, case) if "size" in study.prepare else plant
    design, found, note = METHODS[study.method](study, prepared, case)
    results = simulate(design, case)
    return design, found, note, results, reported(design, case, results)


def _searches(study, plant, case):
    """Return the trials of ``minimize`` on ``plant``: none when the plant is run as it is."""
    return trials_of(plant, study.evaluations) if searchable(plant) else 0


def _draws(study, plant, case):
    """Return the trials of ``sample``: one for each draw."""
    return study.samples


def _ends(study, plant, case):
    """Return the trials of ``sensitivity``: the two ends of each uncertain value."""
    return 2 * len(declared(case, "sensitivity"))


TRIALS = {"run": lambda study, plant, case: 0, "minimize": _searches, "sample": _draws}
TRIALS["sensitivity"] = _ends
TRIALS["evolve"] = lambda study, plant, case: study.evaluations


def trials(study, plant, case):
    """Return the trials the method of ``study`` runs on ``plant`` and ``case``, one at least."""
    return max(1, TRIALS[study.method](study, plant, case))
