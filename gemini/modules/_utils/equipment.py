"""Equipment: a module that declares its kind and the size its cost scales with."""


class Equipment:
    """A module that is equipment: it has a kind and a size to price.

    A subclass sets ``equipment_kind`` to one of ``gemini.case._utils.kinds.EQUIPMENT_KINDS`` and
    defines ``cost_size()``, the rating its cost scales with (a power, a length, a volume, or 1 for
    a fixed item), in SI. The price of it, the unit cost of the kind in the economics of a case
    times the size, is set by ``gemini.evaluate``; a module never reads a case.
    """

    equipment_kind = None

    def cost_size(self):
        """Return the size that the cost of this module scales with, in SI."""
        raise NotImplementedError(f"{type(self).__name__} defines no cost_size()")
