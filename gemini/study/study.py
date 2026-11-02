"""``gm.Study``: the arguments of the study functions as a file, and the run that calls them."""

import json
import posixpath
from pathlib import Path

from gemini._utils.files import to_json
from gemini.case import Case
from gemini.engine.check import check
from gemini.errors import GeminiError, ValidationError
from gemini.errors.base import Issue, raise_issues
from gemini.evaluate import compare
from gemini.plants import Plant
from gemini.study._utils.execute import executed, trials
from gemini.study._utils.progress import counting
from gemini.study._utils.trial import checked_metric
from gemini.study.result import Run, StudyResult
from gemini.units import inputs

HEADER = ("format", "kind", "name")
METHODS = ("run", "minimize", "sample", "sensitivity")
"""The methods of a study, a closed list."""
PREPARE = ("size",)
"""The actions that can run before the method."""
KEYS = (*HEADER, "cases", "plants", "prepare", "method", "objective", "metrics")
KEYS += ("evaluations", "samples", "seed")
REQUIRED = {
    "run": (),
    "minimize": ("objective", "evaluations", "seed"),
    "sample": ("metrics", "samples", "seed"),
    "sensitivity": ("metrics",),
}
"""The keys each method needs, which have no default."""
OWN = {"evaluations": ("minimize",), "samples": ("sample",), "seed": ("minimize", "sample")}
"""The keys that only some methods read; another method refuses them rather than ignore them."""


def _issue(issues, path, kind, message, **details):
    """Append one ``Issue``."""
    issues.append(Issue(path, kind, message, **details))


def _paths(data, key, issues):
    """Return the tuple of paths of a required list of text, or ``None`` with issues."""
    found = data.get(key)
    if found is None:
        _issue(issues, key, "missing", f"{key} is missing; expected a list of file paths")
        return None
    if not isinstance(found, list) or not found or not all(isinstance(i, str) for i in found):
        _issue(issues, key, "incompatible", f"{key} = {found!r}; expected a list of file paths")
        return None
    return tuple(found)


def _whole(data, key, issues):
    """Return the integer at ``key`` (at least 1 but for ``seed``) or ``None`` with an issue."""
    found = data.get(key)
    low = None if key == "seed" else 1
    if isinstance(found, bool) or not isinstance(found, int) or (low and found < low):
        want = "a whole number" if low is None else "a whole number of at least 1"
        _issue(issues, key, "incompatible", f"{key} = {found!r}; expected {want}")
        return None
    return found


def _metrics(data, issues):
    """Return the tuple of metric names of ``data["metrics"]``, with issues for unknown names."""
    found = data["metrics"]
    if not isinstance(found, list) or not all(isinstance(i, str) for i in found):
        _issue(issues, "metrics", "incompatible", f"metrics = {found!r}; expected a list of names")
        return None
    return tuple(_known(name, f"metrics[{n}]", issues) for n, name in enumerate(found))


def _known(name, path, issues):
    """Return ``name``, with an issue when it is no metric of ``gm.evaluate``."""
    try:
        checked_metric(name.removeprefix("-"))
    except ValidationError as error:
        _issue(issues, path, "not_allowed", str(error), suggestions=tuple(error.suggestions))
    return name


class Study:
    """What to run and how, as a file: the arguments of the functions of ``gm.study``.

    ``study.json`` (``kind: study``) records which ``cases`` and ``plants`` (paths, relative to the
    file), an optional ``prepare`` (``["size"]``, an action before the method, whose criterion
    ``backup`` is the plant's), the ``method`` (``run``, ``minimize``, ``sample`` or
    ``sensitivity``), the ``objective`` and ``metrics`` and the settings the method needs:
    ``evaluations`` and ``seed`` for ``minimize``, ``samples`` and ``seed`` for ``sample``. A
    setting has no default: one that the method needs and the file lacks is a ``missing`` issue,
    and one that the method does not read is refused. ``run`` calls the functions of ``gm.study``
    for every plant on every case; there is no second implementation.

    ``from_json`` and ``from_dict`` raise a ``ValidationError`` carrying every issue; ``check``
    returns them and never raises, and adds the files that cannot be read.

    Attributes
    ----------
    name, cases, plants, prepare, method, objective, metrics, evaluations, samples, seed
        As in the file; absent settings are ``None``.
    """

    def __init__(self, found, name, files=None, folder=None, about=None):
        """Build from what ``_read`` found; use ``from_dict`` to build from data."""
        self.name, self.about = name, about
        self.cases, self.plants = found["cases"], found["plants"]
        self.prepare = found["prepare"]
        self.method = found["method"]
        for key in ("objective", "metrics", "evaluations", "samples", "seed"):
            setattr(self, key, found[key])
        self.files = {} if files is None else dict(files)
        self.folder = None if folder is None else Path(folder)

    @classmethod
    def from_dict(cls, data, files=None, folder=None):
        """Return the study of ``data``; ``files`` is ``{path: bytes}`` of the files it names.

        A file that is not in ``files`` is read from ``folder`` when it is run. Raises
        ``ValidationError`` carrying every issue.
        """
        issues = []
        found = cls._read(data, issues)
        raise_issues(issues)
        return cls(found, data["name"], files, folder, data.get("about"))

    @classmethod
    def from_json(cls, path):
        """Return the study of a ``study.json``; its files are read from the folder it is in."""
        path = Path(path)
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError) as error:
            raise ValidationError(
                f"{str(path)!r} is not a readable JSON file ({error})",
                path=str(path),
                code="invalid_format",
            ) from error
        return cls.from_dict(data, folder=path.parent)

    @classmethod
    def _read(cls, data, issues):
        """Return the settings of ``data`` or ``None``, with every issue appended."""
        head = inputs.from_header(data, "study", "", issues)
        if head is None:
            return None
        before = len(issues)
        inputs.check_keys(data, KEYS, "", issues)
        found = {"cases": _paths(data, "cases", issues), "plants": _paths(data, "plants", issues)}
        found["prepare"] = cls._prepare(data, issues)
        found["method"] = cls._method(data, issues)
        found |= cls._settings(data, found["method"], issues)
        return found if len(issues) == before else None

    @staticmethod
    def _prepare(data, issues):
        """Return the tuple of actions before the method; absent is none."""
        found = data.get("prepare", [])
        if not isinstance(found, list) or any(item not in PREPARE for item in found):
            _issue(
                issues,
                "prepare",
                "not_allowed",
                f"prepare = {found!r}; expected a list of {PREPARE}",
            )
            return ()
        return tuple(found)

    @staticmethod
    def _method(data, issues):
        """Return the method, with an issue when it is missing or not in the closed list."""
        method = data.get("method")
        if method is None:
            _issue(issues, "method", "missing", f"method is missing; expected one of {METHODS}")
        elif method not in METHODS:
            _issue(
                issues, "method", "not_allowed", f"method = {method!r}; expected one of {METHODS}"
            )
            return None
        return method

    @classmethod
    def _settings(cls, data, method, issues):
        """Return the objective, metrics and settings, each ``None`` when absent."""
        found = dict.fromkeys(("objective", "metrics", "evaluations", "samples", "seed"))
        for key, only in OWN.items():
            if key in data and method is not None and method not in only:
                message = f"{key} is not read by the method {method!r}; expected it only for {only}"
                _issue(issues, key, "incompatible", message)
        for key in REQUIRED.get(method, ()):
            if key not in data:
                _issue(issues, key, "missing", f"{key} is missing; the method {method} needs it")
        if "objective" in data:
            found["objective"] = _known(data["objective"], "objective", issues)
        if "metrics" in data:
            found["metrics"] = _metrics(data, issues)
        for key in ("evaluations", "samples", "seed"):
            if key in data:
                found[key] = _whole(data, key, issues)
        return found

    def to_dict(self):
        """Return the study as a file: the header, then the keys that are set."""
        data = inputs.Header("study", self.name, self.about).to_json()
        data["cases"], data["plants"] = list(self.cases), list(self.plants)
        if self.prepare:
            data["prepare"] = list(self.prepare)
        data["method"] = self.method
        for key in ("objective", "metrics", "evaluations", "samples", "seed"):
            if getattr(self, key) is not None:
                value = getattr(self, key)
                data[key] = list(value) if key == "metrics" else value
        return data

    def to_json(self, path):
        """Write the study file."""
        to_json(path, self.to_dict())

    @classmethod
    def schema(cls):
        """Return the JSON Schema (draft 2020-12) of ``study.json``, from the lists of the class."""
        names = {"type": "array", "items": {"type": "string"}, "minItems": 1}
        whole = {"type": "integer", "minimum": 1}
        properties = {
            "format": {"const": inputs.FORMAT},
            "kind": {"const": "study"},
            "name": {"type": "string"},
            "about": {},
            "cases": names,
            "plants": names,
            "prepare": {"type": "array", "items": {"enum": list(PREPARE)}},
            "method": {"enum": list(METHODS)},
            "objective": {"type": "string"},
            "metrics": names,
            "evaluations": whole,
            "samples": whole,
            "seed": {"type": "integer"},
        }
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": cls.__name__,
            "type": "object",
            "additionalProperties": False,
            "required": [*HEADER, "cases", "plants", "method"],
            "properties": properties,
        }

    def check(self):
        """Return the list of issues of the study; it never raises.

        The study is written and read again, then every case and plant it names must read, and each
        plant must be ready for each case (``gm.check``, the parameters a size completes aside). A
        warning (``Issue.is_warning``) is passed on once and does not make a pair unready.
        """
        issues = []
        self._read(self.to_dict(), issues)
        if issues:
            return issues
        cases, plants = {}, {}
        for path in self.cases:
            self._loaded(cases, path, self._case, issues)
        for path in self.plants:
            self._loaded(plants, path, self._plant, issues)
        for plant in plants.values():
            for case in cases.values():
                issues += self._unready(plant, case)
        return self._once(issues)

    @staticmethod
    def _once(issues):
        """Return ``issues`` with a warning that several pairs repeat kept once."""
        seen, found = set(), []
        for item in issues:
            key = (item.path, item.message)
            if item.is_warning and key in seen:
                continue
            seen.add(key)
            found.append(item)
        return found

    def _unready(self, plant, case):
        """Return the issues of ``gm.check`` for one pair that the method itself would raise."""
        sized = "size" in self.prepare
        return [
            item
            for item in check(plant, case)
            if not (sized and item.kind == "missing" and item.path.startswith("params."))
        ]

    @property
    def names(self):
        """The metrics the study reads, the objective first, without the sign of a maximum."""
        found = [self.objective] if self.objective else []
        names = [name.removeprefix("-") for name in (*found, *(self.metrics or ()))]
        return list(dict.fromkeys(names))

    @staticmethod
    def _loaded(found, path, reader, issues):
        """Read the file ``path`` with ``reader`` into ``found``, or add the issues it raises."""
        try:
            found[path] = reader(path)
        except ValidationError as error:
            issues.extend(error.issues or [Issue(path, "incompatible", str(error))])
        except (GeminiError, OSError) as error:
            issues.append(Issue(path, "incompatible", f"{path}: {error}"))

    def _case(self, path):
        """Return the case of the file ``path``."""
        if path not in self.files:
            return Case.from_json(self._at(path))
        base = posixpath.dirname(path)
        prefix = f"{base}/" if base else ""
        mine = {
            name.removeprefix(prefix): content
            for name, content in self.files.items()
            if name != path and name.startswith(prefix)
        }
        return Case.from_dict(json.loads(self.files[path]), files=mine)

    def _plant(self, path):
        """Return the plant of the file ``path``."""
        if path not in self.files:
            return Plant.from_json(self._at(path))
        return Plant.from_dict(json.loads(self.files[path]))

    def _at(self, path):
        """Return the place of the file ``path`` below the folder of the study."""
        if self.folder is None:
            raise ValidationError(
                f"{path}: no folder and no file of that name; expected the study to be read from "
                "a file or given the file in files",
                path=path,
                code="invalid_value",
            )
        return self.folder / path

    def run(self, plants=None, *, on_progress=None):
        """Run the method on every plant and every case and return a ``StudyResult``.

        ``plants`` is optionally ``{name: Plant}`` in memory, instead of the plant files of the
        study, for a plant that came from an earlier run (the best design to sample). Each plant is
        prepared, run by the function of the method (``gm.study.size``, ``minimize``, ``sample``,
        ``sensitivity``), simulated and reported; ``minimize`` on a plant that states no range and
        no options runs the plant as it is, with a ``note``.

        ``on_progress(done, total)``, when given, is called in the calling process after each
        finished trial of the method (``minimize``, ``sample`` and ``sensitivity`` run trials, also
        in worker processes); ``total`` is their number over every plant and case, a pair that
        runs none counts as one, and ``done`` reaches ``total`` at the end even when a search ends
        early. Raising ``gm.errors.Cancelled`` from it stops the study: no later trial starts, the
        workers are stopped and the exception propagates. The result does not depend on it.
        """
        issues = []
        cases = {}
        for path in self.cases:
            self._loaded(cases, path, self._case, issues)
        given = dict(plants) if plants is not None else {}
        if plants is None:
            for path in self.plants:
                self._loaded(given, Path(path).stem, lambda _, path=path: self._plant(path), issues)
        raise_issues(issues)
        named = {case.name: case for case in cases.values()}
        pairs = [(name, plant, case) for case in named.values() for name, plant in given.items()]
        planned = [] if on_progress is None else [trials(self, p, c) for _, p, c in pairs]
        runs, reached = [], 0
        with counting(on_progress, sum(planned)) as count:
            for (name, plant, case), expected in zip(pairs, planned or [0] * len(pairs)):
                runs.append(self._record(name, plant, case))
                reached += expected
                if count is not None:
                    count.reach(reached)
        return self._result(runs, named)

    def _record(self, name, plant, case):
        """Return the ``Run`` of ``plant`` named ``name`` on ``case``."""
        design, found, note, results, report = executed(self, plant, case)
        return Run(
            plant_name=name,
            case_name=case.name,
            verdict=report["verdict"],
            metrics={item: report[item] for item in self.names if item in report},
            plant=design,
            source=plant,
            report=report,
            results=results,
            found=found,
            note=note,
        )

    def _result(self, runs, cases):
        """Return the ``StudyResult``: the comparison of each case and its best run."""
        comparison, best = {}, {}
        by = self._ranking()
        for name in cases:
            mine = [run for run in runs if run.case_name == name]
            if not by:
                best[name] = None
                continue
            comparison[name] = compare([run.report for run in mine], by=by)
            best[name] = self._winner(mine, comparison[name])
        return StudyResult(self, runs, comparison, best, cases)

    def _ranking(self):
        """Return ``{metric: "min" or "max"}`` for ``compare``: the objective, then the metrics."""
        found = [self.objective] if self.objective else []
        senses = {}
        for name in (*found, *(self.metrics or ())):
            senses.setdefault(name.removeprefix("-"), "max" if name.startswith("-") else "min")
        return senses

    def _winner(self, runs, ranked):
        """Return the feasible run ranked first by the objective, or ``None``."""
        if not self.objective:
            return None
        key = self.objective.removeprefix("-")
        feasible = [(entry["ranks"][key], entry["index"]) for entry in ranked if entry["feasible"]]
        return runs[min(feasible)[1]] if feasible else None
