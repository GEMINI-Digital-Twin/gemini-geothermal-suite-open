"""The time of a case: the first instant, the end that is excluded, and the step."""

import pandas as pd

from gemini._utils.strings import join_path
from gemini._utils.time import to_utc
from gemini.case._utils.node import Frozen, issue, plain
from gemini.errors.base import raise_issues
from gemini.units import inputs

KEYS = ("start", "end", "step")


class Time(Frozen):
    """The period of a case: ``start``, ``end`` and ``step``.

    ``end`` is excluded, so ``2027-01-01`` to ``2028-01-01`` at one day is 365 steps. Every series
    of the case lies on ``Time.index``. ``start`` and ``end`` are UTC timestamps (text without an
    offset is UTC) and ``step`` a duration in seconds. ``to_dict`` writes them as given.

    Attributes
    ----------
    start, end : Timestamp
        First instant and end, UTC.
    step : float
        Step [s].
    """

    where = "time"

    def __init__(self, given, start, end, step):
        """Build from what ``read`` found; use ``from_dict`` to build from data."""
        self._set(_given=given, start=start, end=end, step=step)

    @classmethod
    def read(cls, data, path, issues):
        """Return the time of ``data`` or ``None`` with issues appended."""
        if not isinstance(data, dict):
            issue(issues, path, "incompatible", f"{path} = {data!r}; expected an object")
            return None
        before = len(issues)
        inputs.check_keys(data, KEYS, path, issues)
        instants = {
            name: _instant(data.get(name), join_path(path, name), issues) for name in KEYS[:2]
        }
        step = _step(data.get("step"), join_path(path, "step"), issues)
        if len(issues) > before:
            return None
        found = cls({**data}, instants["start"], instants["end"], step.si)
        found._given["step"] = step
        return found._ordered(path, issues)

    def _ordered(self, path, issues):
        """Return this time unless the end does not follow the start by whole steps."""
        seconds = (self.end - self.start).total_seconds()
        if seconds <= 0:
            issue(
                issues,
                join_path(path, "end"),
                "out_of_bounds",
                f"{path}.end = {self.end}; expected a time after start",
            )
            return None
        if seconds % self.step:
            issue(
                issues,
                join_path(path, "step"),
                "incompatible",
                f"{path}.step = {self.step} s does not divide the period of {seconds} s; "
                "expected a whole number of steps between start and end",
            )
            return None
        return self

    @classmethod
    def from_dict(cls, data):
        """Return the time of ``data``; raises ``ValidationError`` carrying every issue."""
        issues = []
        found = cls.read(plain(data), cls.where, issues)
        raise_issues(issues)
        return found

    @property
    def index(self):
        """The instants of the run: a UTC ``DatetimeIndex`` called ``time``, ``end`` excluded."""
        step = pd.Timedelta(seconds=self.step)
        return pd.date_range(self.start, self.end, freq=step, inclusive="left", name="time")

    def to_dict(self):
        """Return the time as it was read."""
        return {
            "start": self._given["start"],
            "end": self._given["end"],
            "step": self._given["step"].to_json(),
        }

    def __eq__(self, other):
        """Equal when written alike."""
        if not isinstance(other, Time):
            return NotImplemented
        return self.to_dict() == other.to_dict()

    __hash__ = None


def _instant(value, path, issues):
    """Return the UTC ``Timestamp`` of ISO 8601 text, or ``None`` with an issue."""
    if value is None:
        issue(issues, path, "missing", f"{path}: {path.rsplit('.', 1)[-1]} is missing")
        return None
    try:
        return pd.Timestamp(to_utc(value))
    except (TypeError, ValueError):
        issue(
            issues,
            path,
            "incompatible",
            f"{path} = {value!r}; expected ISO 8601 text such as '2027-01-01'",
        )
        return None


def _step(value, path, issues):
    """Return the ``Leaf`` of the step, a duration above zero, or ``None`` with an issue."""
    if value is None:
        issue(issues, path, "missing", f"{path}: step is missing")
        return None
    leaf = inputs.from_leaf(value, path, issues, quantity="duration")
    if leaf is not None and leaf.si <= 0:
        issue(
            issues, path, "out_of_bounds", f"{path}: value = {leaf.value}; expected more than zero"
        )
        return None
    return leaf
