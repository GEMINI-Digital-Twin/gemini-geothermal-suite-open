"""The unit a quantity is shown in, and the conversion of a result to it.

``DISPLAY_UNITS`` is the one table of quantity -> display unit: energy in MWh, power in MW,
temperature in degC. It names no metric and no equipment: a folder that knows its own metrics
(``gm.evaluate``) maps them to a quantity of this table. ``shown`` converts every ``Quantity``
of a result to the unit its SI unit has in a table.
"""

from collections.abc import Mapping

from gemini.units import conversions
from gemini.units.conversions import Quantity
from gemini.units.shapes import Value

DISPLAY_UNITS = {
    "energy": "MWh",
    "power": "MW",
    "money": "MEUR",
    "annual_money": "MEUR/yr",
    "money_per_energy": "EUR/MWh",
    "annual_energy": "MWh/yr",
    "duration": "d",
    "mass": "kt",
    "permeability": "mD",
    "temperature_gradient": "K/km",
    "money_per_mass": "EUR/t",
    "volume_flow": "m3/h",
    "temperature": "degC",
}
"""For each quantity the unit it is shown in; a quantity not listed is shown in SI."""


def by_si_unit(table=None):
    """Return ``{SI unit: display unit}`` derived from ``table`` (``DISPLAY_UNITS``)."""
    source = DISPLAY_UNITS if table is None else table
    return {conversions.si_unit(unit): unit for unit in source.values()}


def shown(found, table, adjust=None):
    """Return ``found`` with every ``Quantity`` in it converted by ``table``, ``{SI unit: unit}``.

    Mappings and lists are walked, and so are the parts of a ``Value``; a quantity whose SI unit
    is not in the table, and anything that is not a quantity, stays as it is. ``adjust(owner, key,
    table)``, when given, returns the table to use for ``owner[key]`` of a mapping: the caller
    that knows which names are differences or long spans changes the table there.
    """
    if isinstance(found, Quantity):
        target = table.get(conversions.si_unit(str(found.unit)))
        converted = found if target is None else found.to(target)
        if isinstance(found, Value):
            return Value(
                converted.value, converted.unit, found.reason, shown(found.parts, table, adjust)
            )
        return converted
    if isinstance(found, Mapping):
        return {
            key: shown(item, table if adjust is None else adjust(found, key, table), adjust)
            for key, item in found.items()
        }
    if isinstance(found, (list, tuple)):
        return [shown(item, table, adjust) for item in found]
    return found
