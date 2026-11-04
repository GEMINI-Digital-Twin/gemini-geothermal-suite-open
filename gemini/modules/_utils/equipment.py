"""Equipment: a module that declares its kind and the size its cost scales with."""

from gemini.errors import ValidationError


class Equipment:
    """A module that is equipment: it has a kind and a size to price.

    A subclass sets ``equipment_kind`` to one of ``gemini.case._utils.kinds.EQUIPMENT_KINDS`` and
    defines ``cost_size()``, the rating its cost scales with (a power, a length, a volume, or 1 for
    a fixed item), in SI. A kind with another cost basis (``gemini.case._utils.kinds.CAPEX_BASES``)
    also gives that size from ``cost_size_of(quantity)``. The price of it, the unit cost of the kind
    in the economics of a case times the size, is set by ``gemini.evaluate``; a module never reads a
    case.
    """

    equipment_kind = None

    def cost_size(self):
        """Return the size that the cost of this module scales with, in SI."""
        raise NotImplementedError(f"{type(self).__name__} defines no cost_size()")

    def cost_size_of(self, quantity):
        """Return the size of this module in ``quantity`` (``"power"``, ``"energy"``) in SI.

        It is the size a cost given per that quantity multiplies; ``None`` when the module has no
        size of that quantity. A subclass that has one and lacks its design value raises
        ``missing_value`` naming it (``missing_size``).
        """
        return None

    def product(self):
        """Return the port fields whose difference is the power [W] this unit produces.

        ``(first, second)`` gives ``first - second`` (an outlet less an inlet enthalpy flow), and
        ``(field, None)`` the field alone (a power port); ``None`` for a unit that produces no
        energy. A variable opex per energy produced multiplies its energy.
        """
        return None

    def missing_size(self, name):
        """Return the ``missing_value`` error of the design value ``name`` that sizes a cost."""
        path = f"{self.path}.{name}" if getattr(self, "path", "") else name
        return ValidationError(
            f"{path} is missing; expected the design value the cost is given per",
            path=path,
            code="missing_value",
        )
