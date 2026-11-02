"""The case: the outside conditions over one period and the rules of third parties."""

import posixpath
from pathlib import Path

import pandas as pd

from gemini import units
from gemini._utils.strings import join_path
from gemini.case._utils import schema
from gemini.case._utils.node import (
    Context,
    Frozen,
    dumps,
    files_of,
    issue,
    load,
    plain,
    refuse_replaced,
    write,
)
from gemini.case.demand import Demand
from gemini.case.economics import Economics
from gemini.case.requirement import Requirement
from gemini.case.site import Site
from gemini.case.time import Time
from gemini.case.utilities import Utilities
from gemini.errors import ValidationError
from gemini.errors.base import Issue, raise_issues
from gemini.units import inputs

HEADER = ("format", "kind", "name")
SECTIONS = {"site": Site, "demand": Demand, "utilities": Utilities}
KEYS = (*HEADER, "time", "initial_state", *SECTIONS, "economics", "requirements")
OLD = {
    "environment": '"site" (and "fluid.gas" is "site.fluid.dissolved_gas")',
    "constraints": '"requirements", each {"name", "on", "quantity", "over"?, "min"?, "max"?}',
    "assumptions": '"economics" (a file or an object) and "utilities.electricity.co2_intensity"',
    "choices": 'a "range" on the plant leaves "size.doublets" and "params.depth"',
}


def _unwritable(data, path):
    """Return the ``incompatible`` issues of the values of ``data`` that no file can hold."""
    if isinstance(data, dict):
        return [
            found
            for key, value in data.items()
            for found in _unwritable(value, path if key == "value" else join_path(path, key))
        ]
    if isinstance(data, list):
        return [
            found
            for number, value in enumerate(data)
            for found in _unwritable(value, f"{path}[{number}]")
        ]
    if data is None or isinstance(data, (str, int, float, bool)):
        return []
    message = f"{path} = {data!r}; expected a number, a text or a Boolean"
    return [Issue(path, "incompatible", message)]


class Case(Frozen):
    """The outside conditions over one period and the rules of third parties: ``(plant, case)``.

    Sections, in the order of ``case.json``: ``time``, ``initial_state``, ``site``, ``demand``,
    ``utilities``, ``economics`` and ``requirements``. Everything is stored in SI as
    plain numbers or arrays on ``time.index``; ``to_dict`` and ``to_json`` write each value as it
    was read, with its unit, and a series as a reference to its CSV file. Nothing has a default: a
    value that is absent is ``None``, and a call that needs it raises ``missing_value``
    (``missing_assumption`` below ``economics``) naming its path.

    ``from_json`` reads a ``case.json`` and the CSV files and the economics file it names;
    ``from_dict`` reads a dict and the CSV files from a folder or from a mapping ``{name: bytes}``.
    Both raise a ``ValidationError`` carrying every issue. ``check`` returns the issues of an
    object and never raises.

    Attributes
    ----------
    name : str
    time : Time
    initial_state : dict or None
        ``{module path: {state name: Leaf}}``; ``Leaf.si`` is the value in SI.
    site : Site or None
    demand : Demand or None
    utilities : Utilities or None
    economics : Economics or None
    requirements : tuple of Requirement or None
    """

    where = "case"

    def __init__(self, **found):
        """Build from what ``read`` found; use ``from_dict`` to build from data."""
        self._set(**found)

    @classmethod
    def from_dict(cls, data, files=None, folder=None):
        """Return the case of ``data``.

        ``files`` is ``{name: bytes}``, the CSV and JSON files the case names, with names relative
        to the folder of the case; ``folder`` is where the files are read from when they are not in
        ``files``. Raises ``ValidationError`` carrying every issue found.
        """
        issues = []
        found = cls._read(plain(data), inputs.Source(folder, files), issues)
        raise_issues(issues)
        return found

    @classmethod
    def from_json(cls, path):
        """Return the case of a ``case.json``, its CSV and economics files read from its folder.

        Raises
        ------
        ValidationError
            ``invalid_format`` for a file that is missing or no JSON object, and every issue of
            what it holds.
        """
        return cls.from_dict(load(path), folder=Path(path).parent)

    @classmethod
    def _read(cls, data, source, issues):
        """Return the case of ``data`` or ``None`` with issues appended."""
        head = inputs.from_header(data, "case", cls.where, issues)
        if head is None:
            return None
        before = len(issues)
        refuse_replaced(OLD, data, "", issues)
        inputs.check_keys({k: v for k, v in data.items() if k not in OLD}, KEYS, "", issues)
        time = Time.read(data["time"], "time", issues) if "time" in data else None
        if "time" not in data:
            issue(issues, "time", "missing", "time is missing")
        if time is None:
            return None
        ctx = Context(issues, source, time.index, _step(time))
        found = {"name": head.name, "about": head.about, "time": time}
        found.update(_sections(data, ctx))
        found.update(_economics(data, ctx))
        found["requirements"] = (
            _requirements(data.get("requirements"), issues) if "requirements" in data else None
        )
        found["initial_state"] = (
            _state(data["initial_state"], issues) if "initial_state" in data else None
        )
        return cls(**found) if len(issues) == before else None

    @classmethod
    def schema(cls):
        """Return the JSON Schema (draft 2020-12) of ``case.json``."""
        properties = {name: schema.section(sub) for name, sub in SECTIONS.items()}
        used = {}
        for sub in (*SECTIONS.values(), Economics):
            used |= schema.quantities(sub)
        used["duration"] = units.names("duration")
        properties |= {
            "time": schema.time(),
            "initial_state": {"type": "object", "additionalProperties": {"type": "object"}},
            "economics": {"anyOf": [{"type": "string"}, Economics.schema()]},
            "requirements": {"type": "array", "items": schema.requirement()},
        }
        found = schema.closed(
            schema.header("case") | {"about": {"type": "object"}} | properties,
            ["format", "kind", "name", "time"],
        )
        return {"$schema": schema.DRAFT, "title": cls.__name__} | found | {"x-quantities": used}

    def to_dict(self):
        """Return the case as it was read, the header first."""
        data = inputs.Header("case", self.name, self.about).to_json()
        data["time"] = self.time.to_dict()
        if self.initial_state is not None:
            data["initial_state"] = {
                module: {state: leaf.to_json() for state, leaf in states.items()}
                for module, states in self.initial_state.items()
            }
        for name in SECTIONS:
            if getattr(self, name) is not None:
                data[name] = getattr(self, name).to_dict()
        if self.economics is not None:
            data["economics"] = self._reference or self.economics.to_dict()
        if self.requirements is not None:
            data["requirements"] = [item.to_dict() for item in self.requirements]
        return data

    def files(self):
        """Return ``{name: bytes}`` of every file the case writes besides ``case.json``."""
        series = [item for name in SECTIONS for item in _series(getattr(self, name))]
        found = {}
        if self.economics is not None and self._reference is None:
            series += self.economics.series()
        if self.economics is not None and self._reference is not None:
            base = posixpath.dirname(_normal(self._reference))
            found[_normal(self._reference)] = dumps(self.economics.to_dict()).encode()
            found.update(self.economics.files(base))
        return {**files_of(series), **found}

    def to_json(self, path):
        """Write ``path``, its economics file, and the CSV files of its series next to it."""
        write(path, self.to_dict(), self.files())

    def check(self):
        """Return the list of issues of this case; it never raises.

        The case is written and read again, so a value changed by ``with_value`` is judged by the
        rules that judge a file.
        """
        try:
            files = self.files()
        except TypeError:
            return _unwritable(self.economics.to_dict(), "economics")
        issues = []
        self._read(self.to_dict(), inputs.Source(None, files), issues)
        return issues

    @property
    def uncertainty(self):
        """``{path: Uncertainty}`` in SI of every value that declares one, by its dotted path."""
        found = {}
        for name in (*SECTIONS, "economics"):
            part = getattr(self, name)
            if part is not None:
                found.update(part.uncertainty(name))
        return found

    def _part(self, path):
        """Return ``(part, rest)`` for the dotted ``path`` of a value, or raise ``unknown_name``."""
        head, _, rest = path.partition(".")
        part = getattr(self, head, None) if head in (*SECTIONS, "economics") else None
        if part is None and head in (*SECTIONS, "economics") and rest:
            raise ValidationError(
                f"{path} is missing; expected a value in the case (it has no default)",
                path=path,
                code="missing_value",
            )
        if part is None or not rest:
            raise ValidationError(
                f"{path} is not a value of the case; expected a path below "
                "site, demand, utilities or economics",
                path=path,
                code="unknown_name",
            )
        return part, rest

    def field(self, path):
        """Return the ``Field`` (quantity and bounds) of the value at the dotted ``path``."""
        part, rest = self._part(path)
        return part.field(rest)

    def leaf(self, path):
        """Return the ``Leaf`` of the value at the dotted ``path``, as it was read, or ``None``."""
        part, rest = self._part(path)
        return part.leaf(rest)

    def with_value(self, path, number):
        """Return a copy with the value at ``path`` set to the SI ``number``; a series becomes it.

        Raises ``out_of_bounds`` for a number outside the bounds of the value.
        """
        part, rest = self._part(path)
        return self._copy(**{path.partition(".")[0]: part.with_value(rest, number)})

    def _copy(self, **replaced):
        """Return a copy with some sections replaced."""
        new = object.__new__(Case)
        new.__dict__.update(self.__dict__)
        new.__dict__.update(replaced)
        return new

    def __eq__(self, other):
        """Equal when written alike, with the same files."""
        if not isinstance(other, Case):
            return NotImplemented
        return self.to_dict() == other.to_dict() and self.files() == other.files()

    __hash__ = None


def _step(time):
    """Return the step of ``time`` as a ``Timedelta``."""
    return pd.Timedelta(seconds=time.step)


def _series(part):
    """Return the series of a section, none when it is absent."""
    return [] if part is None else part.series()


def _normal(name):
    """Return ``name`` as a POSIX path without ``.`` and ``..``."""
    return posixpath.normpath(name)


def _sections(data, ctx):
    """Return ``{name: section}`` of the sections of the physics given in ``data``."""
    return {
        name: SECTIONS[name].read(data[name], name, ctx) if name in data else None
        for name in SECTIONS
    }


def _economics(data, ctx):
    """Return ``{"economics", "_reference"}``: the economics and the file it was given as."""
    if "economics" not in data:
        return {"economics": None, "_reference": None}
    reference = data["economics"] if isinstance(data["economics"], str) else None
    return {
        "economics": Economics.read(data["economics"], "economics", ctx),
        "_reference": reference,
    }


def _requirements(data, issues):
    """Return the tuple of requirements of a list, or ``None`` with issues."""
    if not isinstance(data, list):
        issue(issues, "requirements", "incompatible", f"requirements = {data!r}; expected a list")
        return None
    before = len(issues)
    found = tuple(
        Requirement.read(item, f"requirements[{number}]", issues)
        for number, item in enumerate(data)
    )
    names = [item.name for item in found if item is not None]
    for name in dict.fromkeys(names):
        if names.count(name) > 1:
            issue(
                issues,
                "requirements",
                "incompatible",
                f"requirements: name {name!r} is used twice; expected unique names",
                code="duplicate_name",
            )
    return found if len(issues) == before else None


def _state(data, issues):
    """Return ``{module: {state: Leaf}}`` of the initial state, or ``None`` with issues."""
    if not isinstance(data, dict):
        issue(
            issues, "initial_state", "incompatible", f"initial_state = {data!r}; expected an object"
        )
        return None
    before = len(issues)
    found = {}
    for module, states in data.items():
        path = join_path("initial_state", module)
        if not isinstance(states, dict):
            issue(issues, path, "incompatible", f"{path} = {states!r}; expected {{state: value}}")
            continue
        found[module] = {
            state: _state_leaf(raw, join_path(path, state), issues) for state, raw in states.items()
        }
    return found if len(issues) == before else None


def _state_leaf(data, path, issues):
    """Return the ``Leaf`` of one state, its unit known but its dimension left to the plant."""
    if not isinstance(data, dict) or set(data) - {"value", "unit"}:
        issue(issues, path, "incompatible", f"{path} = {data!r}; expected {units.QUANTITY_FORM}")
        return None
    value, unit = data.get("value"), data.get("unit")
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        issue(
            issues, f"{path}.value", "incompatible", f"{path}.value = {value!r}; expected a number"
        )
        return None
    if unit is not None and not (isinstance(unit, str) and units.si_unit(unit)):
        issue(issues, f"{path}.unit", "unit", f"{path}.unit = {unit!r}; expected a unit of gemini")
        return None
    return inputs.Leaf(value, unit)
