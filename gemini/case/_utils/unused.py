"""The ``range`` of a case or economics leaf: read, used by nothing, deprecated."""

import warnings

from gemini._utils.strings import join_path
from gemini.errors import GeminiWarning
from gemini.errors.base import Issue

MESSAGE = (
    "{path}: a search range belongs on the plant leaf; to move a case value use uncertainty; "
    "this will be refused in a later version"
)


def ranges(data, path=""):
    """Return the ``deprecated`` issues of every leaf of ``data`` that carries a ``range``.

    A leaf is an object with a ``value`` or a ``file`` beside the ``range``, a series leaf
    included; the plant's ranges, requirement bounds and uncertainty bounds are no such leaf.
    """
    found = []
    if isinstance(data, dict):
        if "range" in data and ("value" in data or "file" in data):
            where = join_path(path, "range")
            found.append(Issue(where, "deprecated", MESSAGE.format(path=where)))
        for key, item in data.items():
            found += ranges(item, join_path(path, str(key)))
    elif isinstance(data, list):
        for number, item in enumerate(data):
            found += ranges(item, f"{path}[{number}]")
    return found


def warn(issues, stacklevel):
    """Emit one ``GeminiWarning`` for each issue; ``stacklevel`` counts from the reader's caller."""
    for item in issues:
        warnings.warn(item.message, GeminiWarning, stacklevel=stacklevel + 1)
