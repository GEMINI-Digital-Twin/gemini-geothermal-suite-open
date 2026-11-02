"""The operating limits of the modules of a plant against a finished run."""

import numpy as np

from gemini.evaluate._utils.columns import fields, parameter_values, series
from gemini.types.shapes import measure

TOLERANCE = 1e-9
"""Relative margin of an operating limit: a value on the limit passes through its rounding."""


def breaches(plant, frame):
    """Return one dict per operating limit that a run breaches.

    ``Module.operating_limits`` lists, for a class, ``(output, "min" or "max", parameter)``: the
    output may not fall below (``min``) or rise above (``max``) the value of the parameter, in the
    steps in which the module carried flow. A module whose parameter is not set has no limit, and
    a limit never changes the run. A breach is ``{path, output, sense, limit, worst, step}``: the
    module, ``limit`` and ``worst`` as values, ``step`` the time of the worst step.
    """
    found = []
    for path, module in plant.named_modules():
        for output, sense, parameter in module.operating_limits:
            item = _breach(plant, frame, path, (output, sense, parameter))
            if item is not None:
                found.append(item)
    return found


def _breach(plant, frame, path, limit):
    """Return the breach of one limit of the module at ``path``, or ``None``."""
    output, sense, parameter = limit
    set_values = parameter_values(plant, frame, path, parameter)
    if np.isnan(set_values).all():
        return None
    values, active = series(plant, frame, path, output)
    keep = np.isfinite(values) & active
    if not keep.any():
        return None
    held = float(np.nanmax(set_values) if sense == "min" else np.nanmin(set_values))
    judged = values[keep]
    position = int(judged.argmin() if sense == "min" else judged.argmax())
    worst = float(judged[position])
    outside = worst < held if sense == "min" else worst > held
    if not outside or abs(worst - held) <= TOLERANCE * abs(held):
        return None
    unit = fields(plant, path)[output][0]
    step = frame.index[int(keep.nonzero()[0][position])]
    return {
        "path": path,
        "output": output,
        "sense": sense,
        "limit": measure(held, unit),
        "worst": measure(worst, unit),
        "step": step,
    }
