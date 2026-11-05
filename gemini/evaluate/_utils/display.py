"""The unit in which a metric is shown in a table, and the conversion of a number to it."""

from gemini import units as _units
from gemini._utils.strings import close_matches, did_you_mean, join_names
from gemini.errors import ValidationError
from gemini.modules.call import UNITS
from gemini.plants.roles import TABLE
from gemini.units import display
from gemini.units.display import without_offsets

METRICS = {
    "heat_delivered": "energy",
    "cold_delivered": "energy",
    "boiler_heat": "energy",
    "electricity_bought": "energy",
    "electricity_sold": "energy",
    "gas_bought": "energy",
    "peak_heat": "power",
    "peak_cold": "power",
    "capex": "money",
    "opex": "annual_money",
    "annualised_cost": "annual_money",
    "lcts": "money_per_energy",
    "lcoh": "money_per_energy",
    "lcoc": "money_per_energy",
    "annual_energy": "annual_energy",
    "duration": "duration",
    "analysis_period": "duration",
    "payback": "duration",
    "co2": "mass",
    "co2_emitted": "mass",
    "methane_emitted": "mass",
    "permeability": "permeability",
    "temperature_gradient": "temperature_gradient",
    "price_per_mass": "money_per_mass",
    "flow": "volume_flow",
    "temperature": "temperature",
}
"""The quantity of each metric of a table; the unit comes from ``gm.units.display``.

The values of a case that a study moves (permeability, gradient, prices) are shown by the unit of
their SI unit (``by_si_unit``), through the entries named after their quantity.

Durations are shown in ``d`` (the time a requirement counts, the running time) except the names of
``YEARS``, which are long and shown in ``yr``.

``flow`` and ``temperature`` stand for the quantities of the capacities and requirements of a
report, which are shown by their SI unit (``by_si_unit``).
"""

TITLES = {
    "heat_delivered": "Heat delivered",
    "cold_delivered": "Cold delivered",
    "boiler_heat": "Heat from the boilers",
    "electricity_bought": "Electricity bought",
    "electricity_sold": "Electricity sold",
    "gas_bought": "Gas bought",
    "peak_heat": "Peak heat demand",
    "peak_cold": "Peak cold demand",
    "capex": "Investment",
    "opex": "Operating cost",
    "annualised_cost": "Annualised cost",
    "lcts": "Cost of thermal supply",
    "lcoh": "Cost of heat",
    "lcoc": "Cost of cold",
    "annual_energy": "Energy per year",
    "duration": "Duration",
    "analysis_period": "Analysis period",
    "payback": "Payback time",
    "co2": "CO2 emissions",
    "co2_emitted": "CO2 emitted",
    "methane_emitted": "Methane emitted",
    "permeability": "Permeability",
    "temperature_gradient": "Temperature gradient",
    "price_per_mass": "Price per mass",
    "flow": "Flow",
    "temperature": "Temperature",
}
"""The readable label of each metric, in the order of ``METRICS``."""

OBJECTIVES = ("annualised_cost", "lcts", "lcoh", "lcoc", "co2")
"""The metrics worth minimising that ``gm.study.minimize`` reads: costs and emissions.

A temperature, a flow, a delivered energy or a size is a result or an input, not a target; the
others a table shows (``capex``, ``opex``, ``payback``, the energies bought) are not read by a
search."""

YEARS = ("analysis_period", "payback")
"""The names of the durations of years: shown in ``yr`` by their name, not by their SI unit."""

DIFFERENCES = ("temperature_difference",)
"""The dimensions of a difference: its unit is the SI unit itself, never the offset unit."""

DISPLAY = {
    name: (quantity, "yr" if name in YEARS else display.DISPLAY_UNITS[quantity])
    for name, quantity in METRICS.items()
}
"""For each metric its quantity and the unit it is shown in; a metric not listed is shown in SI."""


def _on_difference(found):
    """Return whether the check ``found`` judges a difference, such as a temperature lift."""
    role, quantity = found.get("role"), found.get("quantity")
    read = TABLE.get(role, {}).get(quantity)
    return read is not None and read.dimension in DIFFERENCES


def adjusted(name, table, difference=False):
    """Return the table for the value called ``name``: no offset in a difference, yr for a span.

    ``name`` may be a dotted path; its last part is the name. ``difference`` is whether the value
    is a difference, whose temperature unit is the SI unit itself, never the offset unit.
    """
    kept = without_offsets(table) if difference else table
    if str(name).rpartition(".")[2] in YEARS:
        return kept | {_units.si_unit("yr"): "yr"}
    return kept


def _adjust(owner, key, table):
    """Return the table for ``owner[key]``; a check ``owner`` may judge a difference."""
    return adjusted(key, table, _on_difference(owner))


def shown(found, table):
    """Return ``found`` with every ``Quantity`` in it converted by ``table``, ``{SI unit: unit}``.

    See ``gm.units.display.shown``: a difference keeps its SI unit and the names of ``YEARS``
    are shown in ``yr``.
    """
    return display.shown(found, table, _adjust)


def display_units(metrics, units=None):
    """Return ``{metric: unit}`` for the metrics that have a display unit; others are left out.

    Parameters
    ----------
    metrics : list of str
        The metrics of a table.
    units : dict, optional
        ``{metric: unit}`` that replaces the display unit of a metric. A name that is not in
        ``metrics`` or has no display unit raises ``invalid_value``; a unit that is unknown or
        of another dimension than the metric raises ``invalid_unit``.

    Returns
    -------
    dict
        The unit of each metric of ``metrics`` that is shown in a unit.
    """
    chosen = {name: DISPLAY[name][1] for name in metrics if name in DISPLAY}
    for name, unit in (units or {}).items():
        if name not in chosen:
            raise ValidationError(
                f"units.{name}; expected one of {join_names(chosen)}"
                f"{did_you_mean(name, chosen)}",
                path=f"units.{name}",
                code="invalid_value",
                suggestions=close_matches(name, chosen),
            )
        _units.convert(1.0, _units.si_unit(chosen[name]), unit, DISPLAY[name][0])
        chosen[name] = unit
    return chosen


def checked(units):
    """Return ``units`` when it is ``"si"`` or ``"display"``, else raise ``invalid_value``."""
    if units not in UNITS:
        raise ValidationError(
            f"evaluate: units = {units!r}; expected one of {join_names(UNITS)}"
            f"{did_you_mean(str(units), UNITS)}",
            path="units",
            code="invalid_value",
            suggestions=close_matches(str(units), UNITS),
        )
    return units


def checked_or_map(units):
    """Return ``units`` when it is a map ``{metric: unit}``, else ``checked(units)``."""
    return units if isinstance(units, dict) else checked(units)


def displayed(units, name, compute):
    """Return ``compute()``, a cost value called ``name``, in SI or in the display table.

    ``units`` is ``"si"`` (the value as computed) or ``"display"`` (the value and every part in
    the units of ``gm.units.display``, a long span in ``yr``). Anything else raises
    ``invalid_value`` before ``compute`` runs.
    """
    checked(units)
    found = compute()
    return found if units == "si" else shown(found, adjusted(name, display.by_si_unit()))


def in_unit(metric, number, unit):
    """Return ``number`` in SI of the metric ``metric`` converted to ``unit``; ``None`` stays."""
    if number is None:
        return None
    quantity, default = DISPLAY[metric]
    return _units.convert(number, _units.si_unit(default), unit, quantity)
