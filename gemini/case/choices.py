"""The choices of a case: what a study may vary, each as a range."""

from gemini._utils.strings import join_path
from gemini.case._utils.node import Frozen, issue
from gemini.types import inputs

KEYS = ("doublets", "depth")


class Choices(Frozen):
    """What a study may vary: the number of doublets and their depth.

    Attributes
    ----------
    doublets : Range or None
        Whole numbers of doublets, at least 1.
    depth : Range or None
        Depths [m] of the doublets, 0 or more, in SI.
    """

    where = "choices"

    def __init__(self, given, doublets, depth):
        """Build from what ``read`` found; use ``Case.from_dict`` to build from data."""
        self._set(_given=given, doublets=doublets, depth=depth)

    @classmethod
    def read(cls, data, path, issues):
        """Return the choices of ``data`` or ``None`` with issues appended."""
        if not isinstance(data, dict):
            issue(issues, path, "incompatible", f"{path} = {data!r}; expected an object")
            return None
        before = len(issues)
        inputs.check_keys(data, KEYS, path, issues)
        counts = (
            _counts(data["doublets"], join_path(path, "doublets"), issues)
            if "doublets" in data
            else None
        )
        depth = _depth(data["depth"], join_path(path, "depth"), issues) if "depth" in data else None
        if len(issues) > before:
            return None
        given = {key: data[key] for key in KEYS if key in data}
        return cls(given, counts, None if depth is None else inputs.Range(*depth))

    def to_dict(self):
        """Return the choices as they were read."""
        return {key: value for key, value in self._given.items()}

    def __eq__(self, other):
        """Equal when written alike."""
        if not isinstance(other, Choices):
            return NotImplemented
        return self.to_dict() == other.to_dict()

    __hash__ = None


def _counts(data, path, issues):
    """Return the ``Range`` of whole numbers from 1, or ``None`` with issues."""
    if not isinstance(data, dict):
        issue(issues, path, "incompatible", f"{path} = {data!r}; expected {{'min': 1, 'max': 3}}")
        return None
    inputs.check_keys(data, ("min", "max"), path, issues)
    ends = [data.get(side) for side in ("min", "max")]
    for side, end in zip(("min", "max"), ends):
        whole = isinstance(end, int) and not isinstance(end, bool) and end >= 1
        if not whole:
            issue(
                issues,
                join_path(path, side),
                "out_of_bounds",
                f"{path}.{side} = {end!r}; expected a whole number of at least 1",
            )
    if all(isinstance(end, int) for end in ends) and ends[0] > ends[1]:
        issue(issues, path, "incompatible", f"{path}: min = {ends[0]} is above max = {ends[1]}")
    return inputs.Range(*ends)


def _depth(data, path, issues):
    """Return ``(min, max)`` in metres of a range of lengths, or ``None`` with issues."""
    if not isinstance(data, dict):
        issue(issues, path, "incompatible", f"{path} = {data!r}; expected min and max lengths")
        return None
    before = len(issues)
    inputs.check_keys(data, ("min", "max"), path, issues)
    leaves = [
        inputs.from_leaf(
            data.get(side),
            join_path(path, side),
            issues,
            quantity="length",
            bounds=inputs.Range(min=0.0),
        )
        for side in ("min", "max")
    ]
    if len(issues) > before:
        return None
    low, high = leaves[0].si, leaves[1].si
    if low > high:
        issue(issues, path, "incompatible", f"{path}: min = {low} is above max = {high}")
        return None
    return low, high
