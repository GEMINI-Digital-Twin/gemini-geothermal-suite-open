"""A result of a study in the display units of ``gm.units.display``, for its JSON form."""

from gemini.evaluate._utils.display import adjusted
from gemini.units import Quantity
from gemini.units.display import by_si_unit
from gemini.units.display import shown as converted
from gemini.units.display import without_offsets


def shown(found, differences=()):
    """Return ``found`` with every quantity in the display unit of its SI unit.

    ``differences`` are the names of the values that are differences, such as a temperature lift:
    they keep K. A name whose last part is a long span (``analysis_period``) is shown in yr. It is
    the table of ``gm.evaluate``, so a report and a study show the same units.
    """

    def adjust(owner, key, table):
        return adjusted(key, table, key in differences)

    return converted(found, by_si_unit(), adjust)


def display_quantity(number, unit, difference=False):
    """Return the ``Quantity`` of ``number`` in the SI ``unit``, in its display unit.

    A ``difference`` of temperature keeps K.
    """
    table = by_si_unit()
    return converted(Quantity(number, unit), without_offsets(table) if difference else table)


def display_text(number, unit, difference=False):
    """Return ``number`` of the SI ``unit`` as text in its display unit, such as ``4.7 MW``."""
    found = display_quantity(number, unit, difference)
    return f"{found.value:.4g} {found.unit}"


def difference_names(parameters, quantity_of):
    """Return the names of ``parameters`` that are temperature differences.

    ``parameters`` is ``{name: Quantity}`` and ``quantity_of(name)`` the quantity of the value
    called ``name``. Only a value in K can be a difference of temperature.
    """
    return [
        name
        for name, found in parameters.items()
        if isinstance(found, Quantity)
        and str(found.unit) == "K"
        and (quantity_of(name) or "").endswith("_difference")
    ]
