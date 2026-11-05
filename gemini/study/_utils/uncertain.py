"""The uncertain values a case declares: the only ones ``sample`` and ``sensitivity`` move."""

from gemini.errors import ValidationError
from gemini.study._utils.target import CASE_PREFIX, case_field


def tried_ends(uncertainty, value):
    """Return ``(low, high)``, the two ends a one-at-a-time sensitivity tries around ``value``.

    The bounds when there are, else ``value - std`` and ``value + std`` of a ``normal``.
    """
    low = uncertainty.min if uncertainty.min is not None else value - uncertainty.std
    high = uncertainty.max if uncertainty.max is not None else value + uncertainty.std
    return low, high


def declared(case, study):
    """Return ``[(name, uncertainty, value)]``, ``name`` as ``case.<path>`` and value in SI.

    Raises ``missing_value`` when the case declares none.
    """
    if not case.uncertainty:
        raise ValidationError(
            f"study.{study}: the case declares no uncertainty; expected an 'uncertainty' next to a "
            "number of site, demand, utilities or economics in case.json",
            path="case.uncertainty",
            code="missing_value",
        )
    found = []
    for path, uncertainty in case.uncertainty.items():
        name = f"{CASE_PREFIX}{path}"
        found.append((name, uncertainty, case_field(case, name)[1]))
    return found
