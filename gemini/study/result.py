"""The result of ``Study.run``: every run's verdict and metrics, the comparison, the best plant."""

from dataclasses import dataclass
from pathlib import Path

from gemini._utils.files import to_json
from gemini._utils.jsonable import to_plain
from gemini._utils.version import package_version


@dataclass
class Run:
    """One plant on one case.

    ``plant`` is the design that was run (the plant, sized if the study prepares it, or the best
    plant of a search), ``source`` the plant as the study was given it, ``report`` the
    ``gm.evaluate.report`` of the run and ``verdict`` its verdict; ``metrics`` are the figures the
    study names. ``found`` is what the method gave besides: the dict of ``minimize``, the
    ``Sample`` or the ``Tornado``, ``None`` for ``run``; ``note`` says why a method did not run.
    """

    plant_name: str
    case_name: str
    verdict: dict
    metrics: dict
    plant: object
    source: object
    report: dict
    results: object
    found: object = None
    note: str | None = None

    def to_dict(self):
        """Return the run as plain JSON: names, verdict, metrics, note and what the method found."""
        found = None if self.found is None else _found(self.found)
        return {
            "plant_name": self.plant_name,
            "case_name": self.case_name,
            "verdict": self.verdict.to_dict(),
            "metrics": to_plain(self.metrics),
            "note": self.note,
            "found": found,
        }


def _found(found):
    """Return the plain form of what a method found, without the plant."""
    return found.to_dict()


class StudyResult:
    """What ``Study.run`` gives.

    Attributes
    ----------
    study : Study
    runs : list of Run
        Every plant on every case, the cases in the order of the study, then its plants.
    comparison : dict
        ``{case name: Comparison}`` of the reports of that case, ranked by the objective and the
        metrics of the study; empty when the study names neither.
    best : dict
        ``{case name: Run or None}``: the feasible run ranked first by the objective, ``None``
        when no run is feasible or the study has no objective. ``best[case].plant`` is the best
        plant.
    cases : dict
        ``{case name: Case}``.
    """

    def __init__(self, study, runs, comparison, best, cases):
        """Keep the runs and what was derived from them."""
        self.study = study
        self.runs = runs
        self.comparison = comparison
        self.best = best
        self.cases = cases

    def to_dict(self):
        """Return the result as plain JSON: the study, every run, the comparison, the best."""
        return {
            "study": self.study.to_dict(),
            "runs": [run.to_dict() for run in self.runs],
            "comparison": {name: found.to_dict() for name, found in self.comparison.items()},
            "best": {
                name: None if run is None else {"plant_name": run.plant_name}
                for name, run in self.best.items()
            },
        }

    def to_json(self, folder):
        """Write the run records of a study into ``folder``.

        ``study.json`` and ``version.json`` (the gemini version), ``result.json`` (``to_dict``),
        then for each case a folder with the case, its economics and its series, and in it for each
        plant a folder with the plant as it was given (``source.json``), the full plant form that
        ran (``plant.json``, ``to_json(structure=True)``), ``report.json``, ``verdict.json``,
        ``series.csv`` and, when the method found something, ``found.json``.
        """
        root = Path(folder)
        self.study.to_json(root / "study.json")
        to_json(root / "version.json", {"gemini": package_version()})
        to_json(root / "result.json", self.to_dict())
        for name, case in self.cases.items():
            case.to_json(root / name / "case.json")
        for run in self.runs:
            _write(root / run.case_name / run.plant_name, run)


def _write(where, run):
    """Write the record of one run in the folder ``where``."""
    run.source.to_json(where / "source.json")
    run.plant.to_json(where / "plant.json", structure=True)
    to_json(where / "report.json", run.report.to_dict())
    to_json(where / "verdict.json", run.verdict.to_dict())
    run.results.to_frame().to_csv(where / "series.csv")
    if run.found is not None:
        to_json(where / "found.json", _found(run.found))
