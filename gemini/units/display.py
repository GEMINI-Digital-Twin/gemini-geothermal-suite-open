"""The unit a quantity is shown in, and the conversion of a result to it.

``DISPLAY_UNITS`` is the one table of quantity -> display unit: energy in MWh, power in MW,
temperature in degC. It names no metric and no equipment: a folder that knows its own metrics
(``gm.evaluate``) maps them to a quantity of this table. ``shown`` converts every ``Quantity``
of a result to the unit its SI unit has in a table.
"""

from collections.abc import Mapping

from gemini._utils.strings import close_matches
from gemini.errors import ValidationError
from gemini.units import conversions
from gemini.units.conversions import Quantity
from gemini.units.shapes import OutputUnits, Value, measure

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


def without_offsets(table):
    """Return ``table`` without the units that shift a number: a difference keeps its SI unit."""
    return {unit: shown_unit for unit, shown_unit in table.items() if unit != "K"}


class DisplayUnits(OutputUnits):
    """The ``units="display"`` argument of a public return: every quantity in its display unit.

    It stands where an ``OutputUnits`` map stands: a number stored in an SI unit comes out in the
    unit that SI unit has in ``DISPLAY_UNITS`` (energy in MWh, power in MW, temperature in degC),
    and in SI when the table has none. A difference (a quantity whose name ends in
    ``_difference``) keeps its SI unit, so a temperature lift stays in K. The choice is by the
    stored unit, so it needs no map and no quantity of the field.
    """

    def __init__(self):
        """Take no map: the table is the choice."""
        super().__init__()

    def target(self, quantity, unit=None):
        """Return the display unit of the stored ``unit``, or ``None`` to keep it."""
        if unit is None:
            return None
        table = by_si_unit()
        if quantity is not None and quantity.endswith("_difference"):
            table = without_offsets(table)
        target = table.get(conversions.si_unit(str(unit)))
        return None if target is None or target == str(unit) else target


class DisplayedValues(DisplayUnits):
    """The leaves of a public return as ``Quantity`` values in the units of ``DISPLAY_UNITS``.

    It stands where ``OutputUnits`` stands, with the same ``value(number, unit, quantity)``: the
    number is stored in the SI ``unit`` of ``quantity`` and comes out as a ``Value`` in the
    display unit of that SI unit, or in SI when the table has none. A difference (a quantity whose
    name ends in ``_difference``) keeps its SI unit, so a temperature lift stays in K.
    """

    def value(self, number, unit, quantity, reason=None, **details):
        """Return the ``Value`` of ``number``, stored in ``unit``, in its display unit."""
        table = by_si_unit()
        if quantity is not None and quantity.endswith("_difference"):
            table = without_offsets(table)
        return shown(measure(number, unit, reason, **details), table)


def output_units(units):
    """Return the object for the ``units`` of a view: ``None`` or a map, ``"si"``, ``"display"``.

    A map from quantity to unit is an ``OutputUnits``; ``"display"`` is a ``DisplayUnits``. Any
    other text raises ``invalid_value``.
    """
    if units == "display":
        return DisplayUnits()
    if units == "si":
        return OutputUnits()
    if isinstance(units, str):
        raise ValidationError(
            f'units = {units!r}; expected a map from quantity to unit, "si" or "display"',
            path="units",
            code="invalid_value",
            suggestions=close_matches(units, ("si", "display")),
        )
    return OutputUnits(units)


def shown(found, table, adjust=None):
    """Return ``found`` with every ``Quantity`` in it converted by ``table``, ``{SI unit: unit}``.

    Mappings and lists are walked, and so are the parts of a ``Value``; a quantity whose SI unit
    is not in the table, and anything that is not a quantity, stays as it is. ``adjust(owner, key,
    table)``, when given, returns the table to use for ``owner[key]`` of a mapping: the caller
    that knows which names are differences or long spans changes the table there.
    """
    if isinstance(found, Quantity):
        target = table.get(conversions.si_unit(str(found.unit)))
        keep = target is None or target == str(found.unit)
        converted = found if keep else found.to(target)
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
