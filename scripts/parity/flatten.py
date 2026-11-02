"""Flatten the outputs of a parity case into numeric leaves and exact leaves."""

import numpy as np

from tests.fixtures.old_names import RENAMED_NAMES


def leaves(value, path=""):
    """Yield ``(path, leaf)``: a float array for numbers, else the string, ``None`` or text.

    Output names of ``main`` are mapped to the current names through ``RENAMED_NAMES``.
    """
    if isinstance(value, dict):
        for key, item in value.items():
            yield from leaves(item, f"{path}/{RENAMED_NAMES.get(key, key)}")
    elif isinstance(value, (list, tuple, np.ndarray)):
        array = np.asarray(value, dtype=object if _mixed(value) else float)
        if array.dtype == object:
            for index, item in enumerate(value):
                yield from leaves(item, f"{path}[{index}]")
        else:
            yield path, array.astype(float).ravel()
    elif isinstance(value, (bool, int, float, np.number)):
        yield path, np.array([float(value)])
    else:
        yield path, value


def _mixed(value):
    """Return whether a sequence holds anything but numbers."""
    return any(
        not isinstance(v, (bool, int, float, np.number, list, tuple, np.ndarray)) for v in value
    )


def flat(outputs):
    """Return ``{path: leaf}`` for the outputs of one case."""
    return dict(leaves(outputs))
