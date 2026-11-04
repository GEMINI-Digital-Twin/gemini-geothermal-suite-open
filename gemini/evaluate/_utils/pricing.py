"""The price of equipment: the unit cost of its kind in the economics of a case times its size."""

from gemini.case._utils.kinds import BASIS_SIZES, EQUIPMENT_KINDS
from gemini.errors import ValidationError

ECONOMICS = "economics"
"""The path of the economics in a case."""

DRILLING = "drilling"
"""The kind whose unit cost is a cost per metre that depends on the length drilled."""

PER_UNIT = "money"
"""The quantity of a cost per unit: one unit per module, whatever its size."""

BASES = {
    "power": "per W",
    "energy": "per J",
    "volume": "per m3",
    "length": "per m",
    "thermal_conductance": "per W/K",
}
"""How a basis is said in an error."""


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


def basis(economics, kind):
    """Return the quantity the capex factor of ``kind`` is given in, ``None`` when it is absent."""
    leaf = None if economics.capex is None else economics.capex.leaf(kind)
    return getattr(leaf, "quantity", None)


def size_of(module, quantity):
    """Return the size of ``module`` that a cost per ``quantity`` multiplies, in SI.

    The basis of the kind (``EQUIPMENT_KINDS``), or an absent factor, takes ``cost_size()``; a cost
    per unit counts one; another basis takes ``module.cost_size_of``, and a module without a size of
    that quantity raises ``no_value``.
    """
    kind = module.equipment_kind
    if quantity is None or quantity == EQUIPMENT_KINDS[kind][0]:
        return module.cost_size()
    if quantity == PER_UNIT:
        return 1.0
    size = module.cost_size_of(BASIS_SIZES[quantity])
    if size is None:
        path = getattr(module, "path", "") or type(module).__name__
        raise ValidationError(
            f"{path} ({type(module).__name__}) has no size {BASES[BASIS_SIZES[quantity]]} to price "
            f"a cost of {kind} given {BASES[BASIS_SIZES[quantity]]}; expected a cost "
            f"{EQUIPMENT_KINDS[kind][1]}",
            path=path,
            code="no_value",
        )
    return size


def capex_of(module, economics):
    """Return the capex of an equipment module: the unit cost of its kind times its size.

    The size is ``cost_size()``, or the size of the basis the unit of the factor tells
    (``size_of``). The drilling kind has a cost per metre that depends on the length drilled
    (``economics.drilling_cost_per_metre``); every other kind has a capex factor of its name.
    """
    size = size_of(module, basis(economics, module.equipment_kind))
    if module.equipment_kind == DRILLING:
        return economics.drilling_cost_per_metre(size) * size
    return capex_factor(economics, module.equipment_kind) * size


def fixed_opex_of(module, economics):
    """Return the fixed opex of a year [currency/yr]: the share of its kind times its capex."""
    return fixed_share(economics, module.equipment_kind) * capex_of(module, economics)
