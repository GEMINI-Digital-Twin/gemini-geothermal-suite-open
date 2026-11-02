"""The price of equipment: the unit cost of its kind in the economics of a case times its size."""

from gemini.errors import ValidationError

ECONOMICS = "economics"
"""The path of the economics in a case."""

DRILLING = "drilling"
"""The kind whose unit cost is a cost per metre that depends on the length drilled."""


def _missing(path):
    """Return the error of a cost value that the case does not give."""
    return ValidationError(
        f"{path} is missing; expected a value in the case (it has no default)",
        path=path,
        code="missing_assumption",
    )


def capex_factor(economics, kind):
    """Return the capex factor of ``kind`` in SI, or raise ``missing_assumption`` naming it."""
    factor = getattr(economics.capex, kind, None) if economics.capex is not None else None
    if factor is None:
        raise _missing(f"{ECONOMICS}.capex.{kind}")
    return factor


def fixed_share(economics, kind):
    """Return the yearly fixed opex of ``kind`` as a share of its capex [1/yr], or raise."""
    share = (economics.opex.fixed if economics.opex is not None else None) or {}
    if share.get(kind) is None:
        raise _missing(f"{ECONOMICS}.opex.fixed.{kind}")
    return share[kind]


def capex_of(module, economics):
    """Return the capex of an equipment module: the unit cost of its kind times ``cost_size()``.

    The drilling kind has a cost per metre that depends on the length drilled
    (``economics.drilling_cost_per_metre``); every other kind has a capex factor of its name.
    """
    size = module.cost_size()
    if module.equipment_kind == DRILLING:
        return economics.drilling_cost_per_metre(size) * size
    return capex_factor(economics, module.equipment_kind) * size


def fixed_opex_of(module, economics):
    """Return the fixed opex of a year [currency/yr]: the share of its kind times its capex."""
    return fixed_share(economics, module.equipment_kind) * capex_of(module, economics)
