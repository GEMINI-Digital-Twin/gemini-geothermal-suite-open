"""The one reader and writer of the shared formats of the input files (Appendix A, section 3).

Every reader takes the value, its ``path`` and a list ``issues``, appends an ``Issue`` for each
thing wrong and returns ``None`` when it found any, so one pass over a file reports everything.
The caller raises once at the end with ``gemini.errors.base.raise_issues``. ``to_json`` writes any
object of this module in the form it was read: the unit and the numbers the user gave come back
unchanged, the SI value is derived (``Leaf.si``).
"""

import csv
import io
import json
import math
import posixpath
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import numpy as np
import pandas as pd
from pytz.exceptions import InvalidTimeError

from gemini import units
from gemini._utils.strings import close_matches, join_names
from gemini.errors.base import Issue

FORMAT = 1
"""The one format number of every file kind."""

KINDS = ("case", "economics", "plant", "study")
"""The kinds of file a header may name."""

UNCERTAINTY_KINDS = ("uniform", "triangular", "normal")
"""The distributions a leaf may declare."""

LEAF_KEYS = ("value", "unit", "range", "options", "uncertainty")
SERIES_KEYS = ("file", "column", "unit", "range", "time_zone")


@dataclass(frozen=True)
class Range:
    """``{"min", "max"}``, either side optional, in the unit of its leaf."""

    min: float | None = None
    max: float | None = None

    def to_json(self):
        """Return the object with the sides that are set."""
        return {
            key: value for key, value in (("min", self.min), ("max", self.max)) if value is not None
        }


@dataclass(frozen=True)
class Uncertainty:
    """A distribution around the nominal value of a leaf, in the unit of the leaf."""

    kind: str
    min: float | None = None
    max: float | None = None
    std: float | None = None

    def to_json(self):
        """Return the object with the fields that are set."""
        fields = (("kind", self.kind), ("min", self.min), ("max", self.max), ("std", self.std))
        return {key: value for key, value in fields if value is not None}


@dataclass(frozen=True)
class Header:
    """The first keys of every file: ``format``, ``kind``, ``name`` and the free ``about``."""

    kind: str
    name: str
    about: dict | None = None
    format: int = FORMAT

    def to_json(self):
        """Return the header keys, ``about`` last when there is one."""
        head = {"format": self.format, "kind": self.kind, "name": self.name}
        return head if self.about is None else head | {"about": self.about}


class Source:
    """Where the files a file refers to are: a folder, an in-memory ``{name: bytes}``, or both.

    ``base`` is the folder of the containing file, relative to the root; names are POSIX paths
    relative to it. One lookup serves the disk and the mapping, so a series and a section behave
    the same from either. The mapping wins over the disk.
    """

    def __init__(self, root=None, files=None, base=""):
        """Keep the root folder, the mapping and the folder of the containing file."""
        self.root = None if root is None else Path(root)
        self.files = {} if files is None else dict(files)
        self.base = base

    def name(self, relative):
        """Return the name of ``relative`` from the root, with ``..`` and ``.`` resolved."""
        return posixpath.normpath(posixpath.join(self.base, relative))

    def content(self, relative):
        """Return the bytes of the file ``relative`` to the containing file, or ``None``."""
        name = self.name(relative)
        if name in self.files:
            return self.files[name]
        if self.root is not None and (self.root / name).is_file():
            return (self.root / name).read_bytes()
        return None

    def at(self, relative):
        """Return the source of the file ``relative``: its own references start from its folder."""
        return Source(self.root, self.files, posixpath.dirname(self.name(relative)))


@dataclass(frozen=True, eq=False)
class Series:
    """A CSV column on its time index, in the unit the file gives.

    ``time`` is a UTC ``DatetimeIndex``, ``values`` the numbers of the column in ``unit``. ``si``
    is the column in SI. ``to_csv`` writes the column in its own unit, which is what makes the
    round trip exact.
    """

    file: str
    column: str
    unit: str | None
    time: pd.DatetimeIndex
    values: np.ndarray
    quantity: str | None = None
    time_zone: str | None = None

    @property
    def si(self):
        """The column in SI."""
        if self.unit is None:
            return self.values
        return units.array_to_si(self.values, self.unit, self.quantity)

    def to_csv(self):
        """Return the CSV text of the column: ``time`` with ISO 8601 offsets, then the column."""
        out = io.StringIO()
        writer = csv.writer(out, lineterminator="\n")
        writer.writerow(["time", self.column])
        for stamp, value in zip(self.time, self.values):
            writer.writerow([stamp.isoformat(), repr(float(value))])
        return out.getvalue()

    def to_json(self):
        """Return ``{"file", "column", "unit"}``; the numbers stay in the CSV."""
        form = {"file": self.file, "column": self.column}
        form |= {} if self.unit is None else {"unit": self.unit}
        return form if self.time_zone is None else form | {"time_zone": self.time_zone}


@dataclass(frozen=True, eq=False)
class Leaf:
    """One value of a file as given, with what the file says about it.

    ``value`` is a number or a string in ``unit`` (``None`` for a dimensionless or a choice), or
    ``None`` when ``series`` is set. ``quantity`` names the dimension that drove the read. ``si``,
    ``range_si`` and ``uncertainty_si`` give the SI numbers; ``to_json`` gives the leaf as read.
    """

    value: float | str | None = None
    unit: str | None = None
    quantity: str | None = None
    range: Range | None = None
    options: tuple | None = None
    uncertainty: Uncertainty | None = None
    series: Series | None = None

    def _si(self, number):
        """Convert one number of this leaf to SI; a number without a unit stays."""
        if number is None or self.unit is None:
            return number
        return units.to_si(number, self.unit, self.quantity)

    @property
    def si(self):
        """The value in SI: the number, the string of a choice, or the array of the series."""
        if self.series is not None:
            return self.series.si
        return self._si(self.value) if isinstance(self.value, (int, float)) else self.value

    @property
    def range_si(self):
        """The range in SI, or ``None``."""
        if self.range is None:
            return None
        return Range(self._si(self.range.min), self._si(self.range.max))

    @property
    def uncertainty_si(self):
        """The uncertainty in SI, or ``None``; a ``std`` converts by scale only."""
        spread = self.uncertainty
        if spread is None:
            return None
        std = None if spread.std is None else self._si(spread.std) - self._si(0)
        return Uncertainty(spread.kind, self._si(spread.min), self._si(spread.max), std)

    def to_json(self):
        """Return the leaf in the form it was read."""
        form = self.series.to_json() if self.series is not None else {"value": self.value}
        if self.series is None and self.unit is not None:
            form["unit"] = self.unit
        for key in ("range", "uncertainty"):
            if getattr(self, key) is not None:
                form[key] = getattr(self, key).to_json()
        if self.options is not None:
            form["options"] = list(self.options)
        return form


def to_json(item):
    """Write a ``Leaf``, ``Series``, ``Range``, ``Uncertainty`` or ``Header`` in its read form."""
    return item.to_json()


def _issue(issues, path, kind, message, **details):
    """Append one ``Issue`` to ``issues``."""
    issues.append(Issue(path, kind, message, **details))


def _is_number(value):
    """Whether ``value`` is a finite number that is no boolean."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def check_keys(data, allowed, path, issues):
    """Append an ``unknown_key`` issue for each key of ``data`` not in ``allowed``; ``about`` is.

    The issue suggests the closest allowed key. Return whether every key is known.
    """
    allowed = set(allowed) | {"about"}
    unknown = [key for key in data if key not in allowed]
    for key in unknown:
        near = tuple(close_matches(key, sorted(allowed)))
        hint = f"; did you mean {near[0]!r}?" if near else ""
        _issue(
            issues,
            f"{path}.{key}" if path else str(key),
            "unknown_key",
            f"{path}: key {key!r}; expected one of {join_names(sorted(allowed))}{hint}",
            suggestions=near,
        )
    return not unknown


def from_header(data, kind, path, issues):
    """Return the ``Header`` of the file ``data`` of the given ``kind``, or ``None`` with issues.

    A file with no ``kind`` is of an older shape: ``old_format``, naming the new header. A wrong
    ``kind`` or an unknown ``format`` is refused.
    """
    form = f'{{"format": {FORMAT}, "kind": "{kind}", "name": "..."}}'
    if not isinstance(data, dict):
        _issue(issues, path, "incompatible", f"{path}: file = {data!r}; expected an object")
        return None
    before = len(issues)
    if "kind" not in data:
        _issue(
            issues,
            path,
            "incompatible",
            f"{path}: this file has an older shape; expected a header {form} first",
            code="old_format",
        )
        return None
    if data["kind"] != kind:
        _issue(
            issues,
            f"{path}.kind" if path else "kind",
            "incompatible",
            f"{path}: kind = {data['kind']!r}; expected {kind!r}",
            code="invalid_format",
        )
    if data.get("format") != FORMAT:
        _issue(
            issues,
            f"{path}.format" if path else "format",
            "incompatible",
            f"{path}: format = {data.get('format')!r}; expected {FORMAT}, header {form}",
            code="old_format",
        )
    _check_name(data.get("name"), path, issues)
    if len(issues) > before:
        return None
    return Header(kind, data["name"], data.get("about"))


def _check_name(name, path, issues):
    """Append the issue of a header ``name`` that is no text."""
    if not isinstance(name, str) or not name:
        place = f"{path}.name" if path else "name"
        _issue(issues, place, "missing", f"{path}: name = {name!r}; expected text")


def from_section(value, path, source, issues):
    """Return ``(mapping, source)`` of a section given as an object or as a path to a JSON file.

    A string is a path relative to the containing file, found on disk or in the mapping; the
    returned source starts from the folder of the file read.
    """
    if isinstance(value, dict):
        return value, source
    if not isinstance(value, str):
        _issue(
            issues, path, "incompatible", f"{path} = {value!r}; expected an object or a file path"
        )
        return None, source
    content = source.content(value)
    if content is None:
        _issue(issues, path, "missing", f"{path}: file {value!r} not found")
        return None, source
    try:
        data = json.loads(content)
    except ValueError as error:
        _issue(issues, path, "incompatible", f"{path}: file {value!r} is no JSON ({error})")
        return None, source
    if not isinstance(data, dict):
        _issue(issues, path, "incompatible", f"{path}: file {value!r}; expected an object")
        return None, source
    return data, source.at(value)


def _quantities(quantity):
    """Return the quantity names of ``quantity``: a name or a tuple of names, the first the main."""
    return quantity if isinstance(quantity, tuple) else (quantity,)


def _fitting(quantity, unit):
    """Return the first quantity of ``quantity`` that ``unit`` fits, else the first of them.

    A leaf whose field accepts several quantities (a cost per W or per W/K) takes the one its
    unit tells.
    """
    names = _quantities(quantity)
    found = (name for name in names if isinstance(unit, str) and units.fits(unit, name))
    return next(found, names[0])


def _unit_issue(issues, path, quantity, given, text):
    """Append the ``unit`` issue naming the quantity and the units it accepts."""
    names = _quantities(quantity)
    accepted = tuple(unit for name in names for unit in units.names(name))
    spelled = " or ".join(name.replace("_", " ") for name in names)
    _issue(
        issues,
        path,
        "unit",
        f"{path}: {text}; expected a unit of {spelled}: {join_names(list(accepted))}",
        quantity=names[0],
        accepted=accepted,
        suggestions=tuple(close_matches(given, accepted)) if isinstance(given, str) else (),
    )


def _from_unit(data, path, quantity, issues):
    """Return the unit of the leaf ``data``, or ``None`` with an issue; ``None`` is no unit."""
    given = data.get("unit")
    unit_path = f"{path}.unit"
    if quantity is None:
        if "unit" in data:
            _issue(
                issues,
                unit_path,
                "unit",
                f"{unit_path} = {given!r}; this value has no dimension, expected no unit",
            )
        return None
    if "unit" not in data:
        _unit_issue(issues, unit_path, quantity, "", "unit is missing")
        return None
    if not isinstance(given, str) or not any(units.fits(given, q) for q in _quantities(quantity)):
        _unit_issue(issues, unit_path, quantity, given, f"unit = {given!r}")
        return None
    return given


def _from_value(data, path, unit, quantity, choices, issues):
    """Return the number or choice of ``data["value"]``, or ``None`` with an issue."""
    value_path = f"{path}.value"
    value = data.get("value")
    if "value" not in data:
        _issue(issues, value_path, "missing", f"{value_path}: value is missing")
    elif choices is not None:
        if value in choices:
            return value
        near = tuple(close_matches(str(value), choices))
        _issue(
            issues,
            value_path,
            "not_allowed",
            f"{value_path} = {value!r}; expected one of {join_names(list(choices))}",
            accepted=tuple(choices),
            suggestions=near,
        )
    elif _is_number(value):
        return value
    if "value" in data and choices is None and not _is_number(value):
        _issue(
            issues,
            value_path,
            "incompatible",
            f"{value_path} = {value!r}; expected a number"
            + (f" in {unit}" if unit else "")
            + (f" ({quantity})" if quantity else ""),
            quantity=quantity,
        )
    return None


def _from_range(spec, path, unit, bounds, issues):
    """Return the ``Range`` of ``spec``, or ``None`` with issues."""
    before = len(issues)
    if not isinstance(spec, dict):
        _issue(issues, path, "incompatible", f"{path} = {spec!r}; expected {{'min': a, 'max': b}}")
        return None
    check_keys_only(spec, ("min", "max"), path, issues)
    sides = {}
    for side in ("min", "max"):
        if side in spec and not _is_number(spec[side]):
            _issue(
                issues,
                f"{path}.{side}",
                "incompatible",
                f"{path}.{side} = {spec[side]!r}; expected a number",
            )
        sides[side] = spec.get(side)
    low, high = sides["min"], sides["max"]
    if _is_number(low) and _is_number(high) and low > high:
        _issue(issues, path, "incompatible", f"{path}: min = {low} is above max = {high}")
    _within(sides, path, unit, bounds, issues)
    return None if len(issues) > before else Range(low, high)


def check_keys_only(spec, allowed, path, issues):
    """Like ``check_keys`` for an object without ``about``."""
    return check_keys({k: v for k, v in spec.items() if k != "about"}, allowed, path, issues)


def _within(sides, path, unit, bounds, issues):
    """Append ``out_of_bounds`` for each number of ``sides`` outside the declared SI ``bounds``."""
    if bounds is None:
        return
    for side, number in sides.items():
        if not _is_number(number):
            continue
        si = number if unit is None else units.to_si(number, unit)
        if (bounds.min is not None and si < bounds.min) or (
            bounds.max is not None and si > bounds.max
        ):
            _issue(
                issues,
                f"{path}.{side}" if side in ("min", "max") else path,
                "out_of_bounds",
                f"{path}: {side} = {number} {unit or ''}; expected within the bounds "
                f"{bounds.to_json()} (SI)",
            )


def _from_uncertainty(spec, path, value, issues):
    """Return the ``Uncertainty`` of ``spec`` around the nominal ``value``, or ``None``."""
    before = len(issues)
    if not isinstance(spec, dict):
        _issue(issues, path, "incompatible", f"{path} = {spec!r}; expected an object with a kind")
        return None
    kind = spec.get("kind")
    if kind not in UNCERTAINTY_KINDS:
        _issue(
            issues,
            f"{path}.kind",
            "not_allowed",
            f"{path}.kind = {kind!r}; expected one of {join_names(list(UNCERTAINTY_KINDS))}",
            accepted=UNCERTAINTY_KINDS,
            suggestions=tuple(close_matches(str(kind), UNCERTAINTY_KINDS)),
        )
        return None
    needed = ("std",) if kind == "normal" else ("min", "max")
    allowed = ("kind", "min", "max", "std") if kind == "normal" else ("kind", "min", "max")
    check_keys_only(spec, allowed, path, issues)
    for key in needed:
        if key not in spec:
            _issue(issues, f"{path}.{key}", "missing", f"{path}: {key} is missing for {kind}")
    for key in ("min", "max", "std"):
        if key in spec and not _is_number(spec[key]):
            _issue(
                issues,
                f"{path}.{key}",
                "incompatible",
                f"{path}.{key} = {spec[key]!r}; expected a number",
            )
    _spread_order(spec, path, value, issues)
    if len(issues) > before:
        return None
    return Uncertainty(kind, spec.get("min"), spec.get("max"), spec.get("std"))


def _spread_order(spec, path, value, issues):
    """Append issues for a ``std`` not above zero, ``min`` above ``max``, or ``value`` outside."""
    std = spec.get("std")
    if _is_number(std) and std <= 0:
        _issue(issues, f"{path}.std", "out_of_bounds", f"{path}.std = {std}; expected above zero")
    low, high = spec.get("min"), spec.get("max")
    if _is_number(low) and _is_number(high) and low > high:
        _issue(issues, path, "incompatible", f"{path}: min = {low} is above max = {high}")
    elif _is_number(value) and (
        (_is_number(low) and value < low) or (_is_number(high) and value > high)
    ):
        _issue(
            issues,
            path,
            "out_of_bounds",
            f"{path}: value = {value} lies outside min = {low}, max = {high}",
        )


def from_options(spec, path, choices, issues):
    """Return the tuple of ``options`` of a choice leaf, a subset of ``choices``, or ``None``."""
    if not isinstance(spec, list) or not spec:
        _issue(issues, path, "incompatible", f"{path} = {spec!r}; expected a non-empty list")
        return None
    bad = [item for item in spec if item not in choices]
    for item in bad:
        _issue(
            issues,
            path,
            "not_allowed",
            f"{path}: option {item!r}; expected one of {join_names(list(choices))}",
            accepted=tuple(choices),
            suggestions=tuple(close_matches(str(item), choices)),
        )
    return None if bad else tuple(spec)


def _dimension_form(data, path, quantity, choices, issues):
    """Append the issue for a leaf given as a bare value or text; return whether it is an object."""
    if isinstance(data, dict):
        return True
    if quantity is not None:
        _unit_issue(
            issues,
            path,
            quantity,
            "",
            f"{data!r} has no unit, expected an object like " f"{units.QUANTITY_FORM}",
        )
    else:
        _issue(
            issues,
            path,
            "missing",
            f"{path} = {data!r}; expected an object {{'value': ...}}",
        )
    return False


def from_leaf(data, path, issues, *, quantity=None, choices=None, bounds=None, source=None):
    """Return the ``Leaf`` of ``data`` or ``None`` with issues appended.

    ``quantity`` is the name of the dimension (``"power"``), a tuple of names when the unit tells
    which one the value is in (the ``Leaf`` keeps the one it fits), or ``None`` for a
    dimensionless value or a choice; ``choices`` the closed list of a choice; ``bounds`` a
    ``Range`` in SI the value and the ends of its range must lie in; ``source`` a ``Source`` for a
    series (``file`` replaces ``value``). A bare number, text such as ``"150 m3/h"``, a unit on a
    dimensionless value, a missing unit on a quantity and an unknown key are issues.
    """
    if not _dimension_form(data, path, quantity, choices, issues):
        return None
    if "file" in data:
        return _from_series_leaf(data, path, issues, quantity, bounds, source or Source())
    before = len(issues)
    check_keys(data, LEAF_KEYS, path, issues)
    unit = _from_unit(data, path, quantity, issues)
    value = _from_value(data, path, unit, quantity, choices, issues)
    extras = _from_extras(data, path, unit, value, choices, bounds, issues)
    if len(issues) > before:
        return None
    return Leaf(value, unit, None if quantity is None else _fitting(quantity, unit), *extras)


def _from_extras(data, path, unit, value, choices, bounds, issues):
    """Return ``(range, options, uncertainty)`` of a leaf, each ``None`` when absent or wrong."""
    spread = rng = options = None
    if "range" in data:
        rng = _from_range(data["range"], f"{path}.range", unit, bounds, issues)
        _only(choices is None, f"{path}.range", "a choice has options, not a range", issues)
    if "options" in data:
        _only(choices is not None, f"{path}.options", "only a choice has options", issues)
        if choices is not None:
            options = from_options(data["options"], f"{path}.options", choices, issues)
    if "uncertainty" in data:
        spread = _from_uncertainty(data["uncertainty"], f"{path}.uncertainty", value, issues)
        _only(choices is None, f"{path}.uncertainty", "a choice has no uncertainty", issues)
    if _is_number(value):
        _within({"value": value}, path, unit, bounds, issues)
    return rng, options, spread


def _only(allowed, path, message, issues):
    """Append an ``incompatible`` issue unless ``allowed``."""
    if not allowed:
        _issue(issues, path, "incompatible", f"{path}: {message}")


def _from_series_leaf(data, path, issues, quantity, bounds, source):
    """Return the ``Leaf`` of a series given in place of ``value``, or ``None`` with issues."""
    before = len(issues)
    check_keys(data, SERIES_KEYS, path, issues)
    unit = _from_unit(data, path, quantity, issues)
    quantity = None if quantity is None else _fitting(quantity, unit)
    series = from_series(data, path, source, issues, quantity=quantity, unit=unit)
    rng = None
    if "range" in data:
        rng = _from_range(data["range"], f"{path}.range", unit, bounds, issues)
    if len(issues) > before:
        return None
    return Leaf(None, unit, quantity, rng, None, None, series)


def from_series(spec, path, source, issues, *, quantity=None, unit=None):
    """Return the ``Series`` of ``{"file", "column", "unit"}`` or ``None`` with issues.

    The CSV is found through ``source`` (disk or mapping, one path). Its first column is named
    ``time``, holds ISO 8601 timestamps with an offset or ``Z``, strictly increasing; every other
    column named in the leaf must exist and be numeric. With ``time_zone``, an IANA name such as
    ``"Europe/Oslo"``, a timestamp without an offset (``2027-01-01`` or ``2027-01-01T00:00``) is
    a local time in that zone; one that is ambiguous or does not exist at a change of the clock is
    refused. Without it, a timestamp needs its offset: there is no default zone.
    """
    zone = _time_zone(spec, path, issues)
    if zone is False:
        return None
    file, column = spec.get("file"), spec.get("column")
    for key, found in (("file", file), ("column", column)):
        if not isinstance(found, str) or not found:
            _issue(issues, f"{path}.{key}", "missing", f"{path}.{key} = {found!r}; expected text")
    if not isinstance(file, str) or not isinstance(column, str) or not file or not column:
        return None
    content = source.content(file)
    if content is None:
        _issue(issues, f"{path}.file", "missing", f"{path}.file: file {file!r} not found")
        return None
    rows = list(csv.reader(io.StringIO(content.decode("utf-8-sig"))))
    return _series_of_rows(rows, file, column, path, unit, quantity, issues, zone)


def _time_zone(spec, path, issues):
    """Return the IANA name of ``time_zone``, ``None`` when absent, ``False`` with an issue."""
    zone = spec.get("time_zone")
    if zone is None:
        return None
    try:
        ZoneInfo(zone)
    except (ZoneInfoNotFoundError, TypeError, ValueError):
        _issue(
            issues,
            f"{path}.time_zone",
            "incompatible",
            f"{path}.time_zone = {zone!r}; expected an IANA time zone such as 'Europe/Oslo' or "
            "'UTC'",
        )
        return False
    return zone


def _series_of_rows(rows, file, column, path, unit, quantity, issues, zone=None):
    """Return the ``Series`` of the CSV ``rows``, or ``None`` with issues."""
    head = rows[0] if rows else []
    if not head or head[0] != "time":
        _issue(
            issues,
            f"{path}.file",
            "incompatible",
            f"{path}.file: {file} first column = {head[0] if head else None!r}; expected 'time'",
        )
        return None
    if column not in head:
        _issue(
            issues,
            f"{path}.column",
            "unknown_key",
            f"{path}.column = {column!r}; {file} has {join_names(head[1:])}",
            accepted=tuple(head[1:]),
            suggestions=tuple(close_matches(column, head[1:])),
        )
        return None
    place = head.index(column)
    body = [row for row in rows[1:] if row]
    before = len(issues)
    stamps = [_stamp(row[0], file, number, path, issues, zone) for number, row in enumerate(body)]
    values = [
        _cell(row, place, file, number, column, path, issues) for number, row in enumerate(body)
    ]
    if not body:
        _issue(issues, f"{path}.file", "missing", f"{path}.file: {file} has no rows")
    _order(stamps, file, path, issues)
    if len(issues) > before:
        return None
    index = pd.DatetimeIndex(pd.to_datetime(stamps, utc=True))
    return Series(file, column, unit, index, np.asarray(values, dtype=float), quantity, zone)


def _stamp(text, file, number, path, issues, zone=None):
    """Return the aware datetime of one cell of ``time``, or ``None`` with an issue.

    A time without an offset is local in ``zone``; without a zone it is refused.
    """
    try:
        stamp = datetime.fromisoformat(text.strip())
    except ValueError:
        _issue(
            issues,
            f"{path}.file",
            "incompatible",
            f"{path}.file: {file} row {number + 1} time = {text!r}; expected ISO 8601 with offset",
        )
        return None
    if stamp.tzinfo is None and zone is not None:
        return _localized(stamp, zone, text, file, number, path, issues)
    if stamp.tzinfo is None:
        _issue(
            issues,
            f"{path}.file",
            "incompatible",
            f"{path}.file: {file} row {number + 1} time = {text!r} has no offset; "
            "expected ISO 8601 with an offset or Z, or a time_zone for the file",
        )
        return None
    return stamp


def _localized(stamp, zone, text, file, number, path, issues):
    """Return the local ``stamp`` in ``zone`` as an aware datetime, or ``None`` with an issue.

    pandas raises ``ValueError`` for a time the clock skips or repeats; before 2.3 it raised the
    ``pytz`` errors.
    """
    try:
        return pd.Timestamp(stamp).tz_localize(zone, ambiguous="raise", nonexistent="raise")
    except (ValueError, OverflowError, InvalidTimeError) as error:
        _issue(
            issues,
            f"{path}.file",
            "incompatible",
            f"{path}.file: {file} row {number + 1} time = {text!r} is ambiguous or does not "
            f"exist in {zone} ({type(error).__name__}); expected a local time the clock shows once",
        )
        return None


def _cell(row, place, file, number, column, path, issues):
    """Return the float of one cell, or ``None`` with an issue."""
    text = row[place].strip() if place < len(row) else ""
    where = f"{path}.file: {file} row {number + 1} {column}"
    if not text:
        _issue(issues, f"{path}.file", "missing", f"{where} is empty; expected a number")
        return None
    try:
        value = float(text)
    except ValueError:
        value = math.nan
    if not math.isfinite(value):
        _issue(issues, f"{path}.file", "incompatible", f"{where} = {text!r}; expected a number")
        return None
    return value


def _order(stamps, file, path, issues):
    """Append an issue for the first repeated or backwards timestamp."""
    known = [stamp for stamp in stamps if stamp is not None]
    for number in range(1, len(known)):
        if known[number] <= known[number - 1]:
            word = "repeats" if known[number] == known[number - 1] else "goes back"
            _issue(
                issues,
                f"{path}.file",
                "incompatible",
                f"{path}.file: {file} time {known[number].isoformat()} {word}; "
                "expected strictly increasing",
            )
            return


def align(series, index, step, path, issues):
    """Return the SI values of ``series`` on the steps starting at ``index``, or ``None``.

    ``index`` is a UTC ``DatetimeIndex`` of step starts and ``step`` the ``Timedelta`` of a step.
    A sample holds until the next (the last for one step of the series). A series that does not
    cover ``[index[0], index[-1] + step)`` is a ``coverage`` issue naming the file, the column, the
    covered window and the requested one. A target step coarser than the series averages its
    samples; a finer one, or one with a step holding no sample, is an ``incompatible`` issue.
    """
    if series.time_zone and step >= DAY and step % DAY == pd.Timedelta(0):
        return _by_local_day(series, index, step, path, issues)
    time = series.time
    own = pd.Series(time).diff().dropna().median() if len(time) > 1 else step
    start, end = index[0], index[-1] + step
    covered_end = time[-1] + own
    if time[0] > start or covered_end < end:
        _issue(
            issues,
            path,
            "coverage",
            f"{path}: {series.file} column {series.column!r} covers {time[0].isoformat()} to "
            f"{covered_end.isoformat()}; requested {start.isoformat()} to {end.isoformat()}",
        )
        return None
    if step < own:
        _issue(
            issues,
            path,
            "incompatible",
            f"{path}: {series.file} column {series.column!r} has a step of {own}; "
            f"expected a target step of at least that, not {step}",
        )
        return None
    return _mean_over_steps(series, index, step, own, path, issues)


DAY = pd.Timedelta(days=1)
"""The step from which a series read in a local zone is matched by its calendar dates."""


def _by_local_day(series, index, step, path, issues):
    """Return the SI values of a daily (or coarser) local ``series`` by calendar date, or ``None``.

    A series of dates read in a zone with daylight saving time has days of 23 or 25 hours, so its
    samples are matched to the case's steps by their local calendar date, not by UTC instants
    (gemini request 37, QA-039): each row is one calendar day in the series' zone.
    """
    zone = series.time_zone
    days = series.time.tz_convert(zone).normalize().tz_localize(None).as_unit("ns")
    starts = index.tz_convert(zone).normalize().tz_localize(None).as_unit("ns")
    width = step // DAY
    ends = starts + pd.Timedelta(days=width)
    if days[0] > starts[0] or days[-1] + DAY < ends[-1]:
        _issue(
            issues,
            path,
            "coverage",
            f"{path}: {series.file} column {series.column!r} covers the local dates "
            f"{days[0].date()} to {(days[-1] + DAY).date()} in {zone}; requested "
            f"{starts[0].date()} to {ends[-1].date()}",
        )
        return None
    low = np.searchsorted(days.asi8, starts.asi8, side="left")
    high = np.searchsorted(days.asi8, ends.asi8, side="left")
    counts = high - low
    if (counts == 0).any():
        first = int(np.flatnonzero(counts == 0)[0])
        _issue(
            issues,
            path,
            "incompatible",
            f"{path}: {series.file} column {series.column!r} has no sample on the local date "
            f"{starts[first].date()} in {zone}",
        )
        return None
    values = series.si
    return np.add.reduceat(values[: high[-1]], low) / counts


def _mean_over_steps(series, index, step, own, path, issues):
    """Return the mean of the SI samples in each step, or ``None`` with an issue."""
    values = series.si
    time = series.time.as_unit("ns").asi8
    low = np.searchsorted(time, index.as_unit("ns").asi8, side="left")
    high = np.searchsorted(time, (index + step).as_unit("ns").asi8, side="left")
    counts = high - low
    if (counts == 0).any():
        first = int(np.flatnonzero(counts == 0)[0])
        _issue(
            issues,
            path,
            "incompatible",
            f"{path}: {series.file} column {series.column!r} has no sample in the step starting "
            f"{index[first].isoformat()}; its step is {own}",
        )
        return None
    return np.add.reduceat(values[: high[-1]], low) / counts
