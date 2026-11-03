"""The base of every section of the case: values as read, SI attributes, one reader and writer.

A section class lists its ``fields`` (leaves, each a ``Field``) and its ``sections`` (children).
``Node.read`` goes through ``gemini.units.inputs`` for every leaf and appends an ``Issue`` for each
thing wrong, so one pass reports everything. An object keeps the leaves as given (``to_dict`` writes
them back unchanged, a series in kW stays kW) and exposes plain SI numbers or arrays on the steps of
``time`` as attributes. Objects are immutable.
"""

import csv
import dataclasses
import io
import json
import posixpath
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from gemini import units
from gemini._utils.strings import join_path
from gemini.case._utils import unused
from gemini.errors import ValidationError
from gemini.errors.base import Issue, raise_issues
from gemini.units import inputs


@dataclass(frozen=True)
class Field:
    """How one leaf of a section is read.

    ``quantity`` is the dimension of the unit (``None`` for a dimensionless value), ``series`` says
    the leaf may be a CSV column, ``bounds`` is the valid range in SI, ``required`` that the leaf
    must be present, ``text`` that its value is a free label, ``integer`` that it is a whole
    number, and ``keys`` that the field is a map ``{key: leaf}`` whose values add up to ``total``
    when that is set.
    """

    quantity: str | None = None
    series: bool = False
    bounds: inputs.Range | None = None
    required: bool = False
    text: bool = False
    integer: bool = False
    keys: tuple | None = None
    total: float | None = None


@dataclass(frozen=True)
class Context:
    """What a reader needs besides the data: the issues, the files, and the steps of ``time``."""

    issues: list
    source: inputs.Source
    index: pd.DatetimeIndex | None = None
    step: pd.Timedelta | None = None
    untimed: bool = False
    """The ``time`` of the case is wrong: a series is not aligned and adds no issue of its own."""

    def at(self, source):
        """Return the context for a file whose references start from ``source``."""
        return dataclasses.replace(self, source=source)


class LeafMap:
    """A field that is a map ``{key: leaf}``: the leaves as given, in the order they were given."""

    def __init__(self, leaves):
        """Keep ``{key: Leaf}``."""
        self.leaves = dict(leaves)

    def to_json(self):
        """Return ``{key: leaf object}``."""
        return {key: leaf.to_json() for key, leaf in self.leaves.items()}


class Frozen:
    """An object that refuses to change after it is built."""

    def __setattr__(self, name, value):
        """Refuse every assignment."""
        raise AttributeError(f"{type(self).__name__} is immutable; build another with with_value")

    def __delattr__(self, name):
        """Refuse every deletion."""
        raise AttributeError(f"{type(self).__name__} is immutable")

    def _set(self, **values):
        """Set attributes while building."""
        for name, value in values.items():
            object.__setattr__(self, name, value)


def si_unit_of(quantity):
    """Return the SI unit string of a named quantity, such as ``"m3/s"`` for ``volume_flow``."""
    return units.si_unit(units.names(quantity)[0])


def plain(data):
    """Return ``data`` with every ``Quantity`` turned into its ``{"value", "unit"}`` object."""
    if isinstance(data, units.Quantity):
        return data.to_dict()
    if isinstance(data, dict):
        return {key: plain(item) for key, item in data.items()}
    if isinstance(data, (list, tuple)):
        return [plain(item) for item in data]
    return data


def issue(issues, path, kind, message, **details):
    """Append one ``Issue``."""
    issues.append(Issue(path, kind, message, **details))


def refuse_replaced(old, data, path, issues):
    """Append an ``old_format`` issue naming the new form for each key of ``data`` in ``old``."""
    for key, form in old.items():
        if key in data:
            issue(
                issues,
                join_path(path, key),
                "unknown_key",
                f"{join_path(path, key)}: this key is of an older shape; expected {form}",
                code="old_format",
            )


def csv_text(series):
    """Return the CSV text of a list of ``Series`` of one file: ``time`` and a column each."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["time", *(item.column for item in series)])
    for number, stamp in enumerate(series[0].time):
        writer.writerow([stamp.isoformat(), *(repr(float(item.values[number])) for item in series)])
    return out.getvalue()


def files_of(series, base=""):
    """Return ``{name: bytes}`` of the CSV files of ``series``, one file with all columns used."""
    grouped = {}
    for item in series:
        columns = grouped.setdefault(item.file, {})
        columns.setdefault(item.column, item)
    return {
        posixpath.normpath(posixpath.join(base, file)): csv_text(list(columns.values())).encode()
        for file, columns in grouped.items()
    }


class Node(Frozen):
    """A section of the case: leaves and child sections, all optional unless a field is required.

    Attributes named like the ``fields`` hold the value in SI (a number, text, an array on the
    steps of ``time`` for a series, a dict for a map), ``None`` when absent. Attributes named like
    the ``sections`` hold the child, ``None`` when absent. ``about`` is free metadata.
    """

    where = ""
    fields = {}
    sections = {}
    old = {}
    """``{key: new form}`` of the keys of an older shape, refused with ``old_format``."""

    def __init__(self, leaves=None, values=None, children=None, about=None):
        """Build from what ``read`` found; use ``from_dict`` to build from data."""
        self._set(_leaves=dict(leaves or {}), about=about)
        self._set(**{name: (values or {}).get(name) for name in self.fields})
        self._set(**{name: (children or {}).get(name) for name in self.sections})

    @classmethod
    def read(cls, data, path, ctx, header=()):
        """Return the section of ``data`` or ``None`` with issues appended to ``ctx.issues``."""
        data, source = inputs.from_section(data, path, ctx.source, ctx.issues)
        if data is None:
            return None
        ctx, before = ctx.at(source), len(ctx.issues)
        refuse_replaced(cls.old, data, path, ctx.issues)
        known = {key: item for key, item in data.items() if key not in cls.old}
        inputs.check_keys(known, [*header, *cls.fields, *cls.sections], path, ctx.issues)
        leaves, values = {}, {}
        for name, field in cls.fields.items():
            found = cls._field_from(name, field, data, join_path(path, name), ctx)
            if found is not None:
                leaves[name], values[name] = found
        children = {
            name: sub.read(data[name], join_path(path, name), ctx)
            for name, sub in cls.sections.items()
            if name in data
        }
        if len(ctx.issues) > before:
            return None
        found = cls(leaves, values, children, data.get("about"))
        found._verify(path, ctx)
        return found if len(ctx.issues) == before else None

    @classmethod
    def _field_from(cls, name, field, data, path, ctx):
        """Return ``(leaf, value)`` of one field, ``None`` when absent or wrong."""
        if name not in data:
            if field.required:
                issue(ctx.issues, path, "missing", f"{path}: {name} is missing")
            return None
        return field_from(field, data[name], path, ctx)

    def _verify(self, path, ctx):
        """Append the issues of a rule between fields; a section with none leaves it alone."""

    @classmethod
    def from_dict(cls, data, files=None, time=None):
        """Return the section of ``data``; ``files`` is ``{name: bytes}`` of the files it names.

        ``time`` is the ``Time`` of a case, needed only when a leaf is a series.
        Raises ``ValidationError`` carrying every issue found.
        """
        return cls._load(data, files, None, time)

    @classmethod
    def _load(cls, data, files, folder, time):
        """Return the section of ``data`` with its files from ``files`` or else from ``folder``."""
        issues = []
        ctx = Context(issues, inputs.Source(folder, files), *_steps(time))
        found = cls.read(plain(data), cls.where, ctx)
        raise_issues(issues)
        unused.warn(found._unused_ranges(), 3)
        return found

    def _unused_ranges(self):
        """Return the ``deprecated`` issues of this section: a ``range`` on a leaf."""
        return unused.ranges(self.to_dict(), self.where)

    def to_dict(self):
        """Return the section as plain data, every leaf as it was read."""
        data = {}
        for name in (*self.fields, *self.sections):
            leaf = self._leaves.get(name) if name in self.fields else getattr(self, name)
            if leaf is not None:
                data[name] = leaf.to_json() if name in self.fields else leaf.to_dict()
        return data if self.about is None else {**data, "about": self.about}

    def series(self):
        """Return the list of ``Series`` of this section and its children."""
        found = [_series_of(leaf) for leaf in self._leaves.values() if _series_of(leaf)]
        for name in self.sections:
            child = getattr(self, name)
            found.extend([] if child is None else child.series())
        return found

    def files(self, base=""):
        """Return ``{name: bytes}`` of the CSV files of the series, names from ``base``."""
        return files_of(self.series(), base)

    def uncertainty(self, prefix=""):
        """Return ``{path: Uncertainty}`` in SI of every leaf that declares one."""
        found = {}
        for name, leaf in self._leaves.items():
            for path, item in _uncertain(leaf, join_path(prefix, name)):
                found[path] = item
        for name in self.sections:
            child = getattr(self, name)
            found.update({} if child is None else child.uncertainty(join_path(prefix, name)))
        return found

    def leaf(self, path):
        """Return the ``Leaf`` at the dotted ``path`` below this section, or ``None``."""
        head, _, rest = path.partition(".")
        if head in self.sections:
            child = getattr(self, head)
            return None if child is None or not rest else child.leaf(rest)
        leaf = self._leaves.get(head)
        if rest and isinstance(leaf, LeafMap):
            return leaf.leaves.get(rest)
        return leaf if not rest else None

    @classmethod
    def field(cls, path):
        """Return the ``Field`` at ``path``, or raise ``unknown_name``."""
        head, _, rest = path.partition(".")
        if head in cls.sections:
            if not rest:
                raise _unknown(cls, path)
            return cls.sections[head].field(rest)
        if head not in cls.fields or (rest and not cls.fields[head].keys):
            raise _unknown(cls, path)
        return cls.fields[head]

    def with_value(self, path, number):
        """Return a copy with the leaf at ``path`` set to the SI ``number``, a series a constant."""
        field = self.field(path)
        head, _, rest = path.partition(".")
        if head in self.sections:
            child = getattr(self, head)
            if child is None:
                raise _absent(self, head)
            return self._copy(children={head: child.with_value(rest, number)})
        if field.keys:
            return self._with_key(head, rest, field, number)
        return self._with_leaf(head, field, self._leaf_of(field, number), number)

    def _with_key(self, head, key, field, number):
        """Return a copy with the key ``key`` of the map ``head`` set."""
        current = self._leaves.get(head)
        leaves = {} if current is None else dict(current.leaves)
        leaves[key] = self._leaf_of(field, number)
        values = dict(getattr(self, head) or {}) | {key: number}
        return self._with_leaf(head, field, LeafMap(leaves), values)

    @staticmethod
    def _leaf_of(field, number):
        """Return the leaf of a constant SI ``number``, refused when outside the bounds."""
        unit = None if field.quantity is None else si_unit_of(field.quantity)
        bounds = field.bounds
        if bounds is not None and (
            (bounds.min is not None and number < bounds.min)
            or (bounds.max is not None and number > bounds.max)
        ):
            raise ValidationError(
                f"value = {number}; expected within the bounds {bounds.to_json()} (SI)",
                code="out_of_bounds",
            )
        return inputs.Leaf(number, unit, field.quantity)

    def _with_leaf(self, name, field, leaf, value):
        """Return a copy with one leaf and its value replaced."""
        return self._copy(leaves={name: leaf}, values={name: value})

    def _copy(self, leaves=None, values=None, children=None):
        """Return a copy of this section with some leaves, values and children replaced."""
        new = object.__new__(type(self))
        new.__dict__.update(self.__dict__)
        new.__dict__["_leaves"] = {**self._leaves, **(leaves or {})}
        for name, value in {**(values or {}), **(children or {})}.items():
            new.__dict__[name] = value
        new.__dict__.pop("frame", None)
        return new

    def check(self, time=None):
        """Return the list of issues of this section; it never raises.

        The section is written and read again, so a value changed by ``with_value`` is judged
        by the same rules as one read from a file.
        """
        issues = []
        ctx = Context(issues, inputs.Source(None, self.files()), *_steps(time))
        type(self).read(self.to_dict(), self.where, ctx)
        return issues + self._unused_ranges()

    def __eq__(self, other):
        """Equal when written alike, with the same CSV files."""
        if type(other) is not type(self):
            return NotImplemented
        return self.to_dict() == other.to_dict() and self.files() == other.files()

    __hash__ = None


def _steps(time):
    """Return ``(index, step)`` of a ``Time``, or ``(None, None)``."""
    if time is None:
        return None, None
    return time.index, pd.Timedelta(seconds=time.step)


def _series_of(leaf):
    """Return the ``Series`` of a leaf, or ``None``."""
    if isinstance(leaf, LeafMap):
        return None
    return getattr(leaf, "series", None)


def _uncertain(leaf, path):
    """Yield ``(path, Uncertainty)`` of a leaf or a map of leaves."""
    if isinstance(leaf, LeafMap):
        for key, item in leaf.leaves.items():
            yield from _uncertain(item, join_path(path, key))
        return
    found = getattr(leaf, "uncertainty_si", None)
    if found is not None:
        yield path, found


def _unknown(node, path):
    """Return the ``unknown_name`` error for a path that is no value of ``node``."""
    return ValidationError(
        f"{join_path(node.where, path)} is not a value; expected one of "
        f"{', '.join((*node.fields, *node.sections))}",
        path=join_path(node.where, path),
        code="unknown_name",
    )


def _absent(node, name):
    """Return the ``missing_value`` error for a section that is absent."""
    path = join_path(node.where, name)
    return ValidationError(
        f"{path} is missing; expected a value in the case (it has no default)",
        path=path,
        code="missing_value",
    )


def field_from(field, data, path, ctx):
    """Return ``(leaf, value)`` of one field given as ``data``, or ``None`` with issues."""
    if field.keys is not None:
        return _map_from(field, data, path, ctx)
    leaf = _leaf_from(field, data, path, ctx)
    if leaf is None:
        return None
    value = _value_of(field, leaf, path, ctx)
    return None if value is None else (leaf, value)


def _leaf_from(field, data, path, ctx):
    """Return the ``Leaf`` of one field, or ``None`` with issues."""
    if isinstance(data, dict) and "file" in data and not field.series:
        issue(
            ctx.issues, path, "incompatible", f"{path}: this value has no series; expected a value"
        )
        return None
    if field.text:
        return _text_from(data, path, ctx.issues)
    return inputs.from_leaf(
        data,
        path,
        ctx.issues,
        quantity=field.quantity,
        bounds=field.bounds,
        source=ctx.source,
    )


def _text_from(data, path, issues):
    """Return the ``Leaf`` of a text label ``{"value": "EUR"}``, or ``None`` with an issue."""
    value = data.get("value") if isinstance(data, dict) else None
    if not isinstance(value, str) or not value:
        issue(issues, path, "incompatible", f"{path} = {data!r}; expected {{'value': 'text'}}")
        return None
    return inputs.from_leaf(data, path, issues, choices=(value,))


def _value_of(field, leaf, path, ctx):
    """Return the SI value of a read leaf: the number, the text, or the array on the steps."""
    if leaf.series is not None:
        return _aligned(field, leaf, path, ctx)
    value = leaf.si
    if field.integer and (isinstance(value, bool) or float(value) != int(value)):
        issue(
            ctx.issues, path, "incompatible", f"{path}: value = {value!r}; expected a whole number"
        )
        return None
    return int(value) if field.integer else value


def _aligned(field, leaf, path, ctx):
    """Return the series of ``leaf`` on the steps of ``time``, or ``None`` with issues."""
    if ctx.index is None and ctx.untimed:
        return None
    if ctx.index is None:
        issue(
            ctx.issues,
            path,
            "missing",
            f"{path}: a series needs the time of a case; read it from a case or pass time=",
        )
        return None
    values = inputs.align(leaf.series, ctx.index, ctx.step, path, ctx.issues)
    if values is None or field.bounds is None:
        return values
    low, high = field.bounds.min, field.bounds.max
    bad = np.zeros(len(values), dtype=bool)
    bad |= False if low is None else values < low
    bad |= False if high is None else values > high
    if bad.any():
        row = int(bad.argmax())
        issue(
            ctx.issues,
            path,
            "out_of_bounds",
            f"{path}: {leaf.series.file} step {row} = {values[row]} (SI); expected within the "
            f"bounds {field.bounds.to_json()}",
        )
        return None
    return values


def _map_from(field, data, path, ctx):
    """Return ``(LeafMap, {key: SI})`` of a field that is a map of leaves, or ``None``."""
    if not isinstance(data, dict):
        issue(ctx.issues, path, "incompatible", f"{path} = {data!r}; expected an object of leaves")
        return None
    before = len(ctx.issues)
    inputs.check_keys(data, field.keys, path, ctx.issues)
    item = dataclasses.replace(field, keys=None, total=None)
    found = {
        key: field_from(item, raw, join_path(path, key), ctx)
        for key, raw in data.items()
        if key in field.keys
    }
    if len(ctx.issues) > before:
        return None
    values = {key: leaf_value[1] for key, leaf_value in found.items()}
    if field.total is not None and abs(sum(values.values()) - field.total) > 1e-9:
        issue(
            ctx.issues,
            path,
            "out_of_bounds",
            f"{path}: values {values} add up to {sum(values.values())}; expected {field.total}",
        )
        return None
    return LeafMap({key: leaf_value[0] for key, leaf_value in found.items()}), values


def dumps(data):
    """Return the JSON text of ``data`` as the files of a project are written."""
    return json.dumps(data, indent=2) + "\n"


def load(path):
    """Return the JSON object of the file ``path``, or raise ``invalid_format``."""
    path = Path(path)
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as error:
        raise ValidationError(
            f"{str(path)!r} is not a readable JSON file ({error})",
            path=str(path),
            code="invalid_format",
        ) from error
    if not isinstance(data, dict):
        raise ValidationError(
            f"{str(path)!r} holds a {type(data).__name__}; expected a JSON object",
            path=str(path),
            code="invalid_format",
        )
    return data


def write(path, data, files):
    """Write the JSON ``data`` at ``path`` and the ``files`` ``{name: bytes}`` next to it."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        target = path.parent / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    path.write_text(dumps(data))
