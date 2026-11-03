"""The values of the economics that the costs of a run need, listed before they are evaluated."""

from gemini.case.case import Case
from gemini.engine.apply import apply_case, remember_case
from gemini.errors import ValidationError
from gemini.errors.base import Issue
from gemini.evaluate.costs import annualised_cost, capex, lcoc, lcoh, lcts, npv, opex, payback
from gemini.evaluate.emissions import co2

PLACEHOLDER = 1.0
"""The SI number that stands in for a missing value so that the next missing one can be found.

It is never a result: the costs evaluated with it are thrown away, only the paths are kept.
"""


def _metrics(plant, results):
    """Return the cost and emission functions of a run, each as ``case -> value``."""
    return [
        lambda case: capex(plant, case),
        lambda case: opex(plant, case, results),
        lambda case: annualised_cost(plant, case, results),
        lambda case: lcoh(plant, case, results),
        lambda case: lcoc(plant, case, results),
        lambda case: lcts(plant, case, results),
        lambda case: npv(plant, case, results),
        lambda case: payback(plant, case, results),
        lambda case: co2(plant, case, results),
    ]


def _first_missing(metric, plant, case):
    """Return the problems of the missing values ``metric`` raises first, or ``[]``.

    ``plant`` carries the values of the case; ``case`` differs from that case in its economics
    only, which ``apply_case`` does not read, so the plant is marked as carrying it too.
    """
    remember_case(plant, case)
    try:
        metric(case)
    except ValidationError as error:
        return [item for item in error.problems if item["code"] == "missing_assumption"]
    return []


def _with_sections(case, path):
    """Return ``case`` with the sections above the leaf ``path`` of its economics, empty if new.

    An economics the case lacks is an empty one with its header, so that a placeholder can be set.
    """
    data = case.to_dict()
    economics = case.economics.to_dict() if case.economics is not None else {}
    economics = {"format": 1, "kind": "economics", "name": "placeholder"} | economics
    node = economics
    for part in path.split(".")[1:-1]:
        node = node.setdefault(part, {})
    return Case.from_dict(data | {"economics": economics}, files=case.files())


def _placed(case, path):
    """Return ``case`` with the placeholder at ``path``, adding the sections it needs."""
    if "." not in path:
        return _with_sections(case, f"{path}.")
    try:
        return case.with_value(path, PLACEHOLDER)
    except ValidationError:
        return _with_sections(case, path).with_value(path, PLACEHOLDER)


def _issue(problem):
    """Return the ``missing`` issue of one missing value of the economics."""
    return Issue(problem["path"], "missing", problem["message"], code="missing_assumption")


def missing(plant, case, results):
    """Return every value of the economics that the costs of a run need and the case lacks.

    ``capex``, ``opex``, ``annualised_cost``, ``lcoh``, ``lcoc``, ``lcts``, ``npv``, ``payback``
    and ``co2`` each raise the first value they miss; this function asks each of them in turn,
    stands a placeholder in for every value found missing on a copy of the case, and asks again,
    so that one call lists them all. A value that is needed only because of the value of another
    (a price of a flow that the run does not have) is listed as the run needs it.

    Parameters
    ----------
    plant : Module
        The plant of the run.
    case : Case
        The case of the run, with or without its economics.
    results : Results
        A finished run of ``plant`` on ``case``.

    Returns
    -------
    list of Issue
        One ``Issue`` of kind ``missing`` and code ``missing_assumption`` per value, path
        ``economics.<path>``, in the order the costs ask for them; the same shape as
        ``gm.case.missing``. An empty list means every cost can be evaluated.
    """
    sited = apply_case(plant, case)
    found, probe = {}, case
    for metric in _metrics(sited, results):
        probe = _asked(metric, sited, probe, found)
    return list(found.values())


def _asked(metric, plant, probe, found):
    """Ask ``metric`` until it misses nothing new; add what it missed to ``found``.

    Return the case with a placeholder in place of each value found, for the next metric.
    """
    for _ in range(len(found) + 100):
        problems = [item for item in _first_missing(metric, plant, probe) if item["path"]]
        new = [item for item in problems if item["path"] not in found]
        if not new:
            return probe
        found |= {item["path"]: _issue(item) for item in new}
        try:
            probe = _placed_all(probe, new)
        except ValidationError:
            return probe
    return probe


def _placed_all(case, problems):
    """Return ``case`` with a placeholder at the path of each of ``problems``."""
    for item in problems:
        case = _placed(case, item["path"])
    return case
