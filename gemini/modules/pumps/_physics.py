"""Where an ESP's head and power curves are below zero, read once per set of curves."""

import functools

import numpy as np

from gemini.physics import constants, pumps

CURVE_STEPS = 200
"""How many steps from zero to ``maximum_flow`` the curves are read at, to say where they are
negative."""


def negative_curves(maximum_flow, stage_count, head_coefficients, power_coefficients, as_float32):
    """Return where the head or power curve is below zero, from 0 to ``maximum_flow``, as text.

    The text is kept by the curves themselves (``curves_text``), never on the pump, so a module
    call writes no state. Curves that cannot be read as numbers (unset, or in a trace) give no
    text: the ``out_of_range`` message then stays as it is.
    """
    try:
        key = (
            float(maximum_flow),
            int(stage_count),
            tuple(np.ravel(head_coefficients).tolist()),
            tuple(np.ravel(power_coefficients).tolist()),
            (np.shape(head_coefficients), np.shape(power_coefficients)),
        )
    except Exception:
        return ""
    if not all(isinstance(value, (int, float)) for value in key[2] + key[3]):
        return ""
    return curves_text(*key, bool(as_float32))


@functools.lru_cache(maxsize=256)
def curves_text(largest, stage_count, head, power, shapes, as_float32):
    """Return the text of where the curves (flattened, with their shapes) are below zero."""
    dtype = np.float32 if as_float32 else None
    pairs = zip((head, power), shapes)
    coefficients = [np.asarray(values, dtype=dtype).reshape(shape) for values, shape in pairs]
    flows = np.linspace(0.0, largest, CURVE_STEPS + 1)
    frequency = float(constants.ESP_REFERENCE_FREQUENCY)
    parts = []
    for name, curve, values in zip(("head", "power"), (pumps.head, pumps.power), coefficients):
        read = np.asarray(curve(flows, frequency, stage_count, values), dtype=float)
        ranges = below_zero(flows, read)
        if ranges:
            said = ", ".join(f"{low:.4g} to {high:.4g}" for low, high in ranges)
            parts.append(f"negative {name} at flows {said} m3/s")
    return f"; the curves give {' and '.join(parts)} (0 to {largest:.4g} m3/s)" if parts else ""


def below_zero(flows, values):
    """Return ``[(first, last), ...]``: the runs of ``flows`` where ``values`` are below zero."""
    ranges, start = [], None
    for index, (flow, value) in enumerate(zip(flows, values, strict=True)):
        if value < 0 and start is None:
            start = flow
        if start is not None and (value >= 0 or index == len(flows) - 1):
            ranges.append((float(start), float(flows[index - 1] if value >= 0 else flow)))
            start = None
    return ranges
