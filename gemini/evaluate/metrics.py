"""The metrics a table of ``gm.evaluate`` shows, with their quantity and display unit."""

from gemini.evaluate._utils.display import DISPLAY

__all__ = ["metrics"]


def metrics():
    """Return the metrics a table of results shows, each with its quantity and display unit.

    Returns
    -------
    list of dict
        ``{name, quantity, unit}`` for each metric, in a fixed order: ``quantity`` is the key of
        ``gm.units.display.DISPLAY_UNITS`` the metric is shown by (``energy``, ``power``,
        ``money``, ...) and ``unit`` the unit it is shown in (``MWh``, ``MW``, ``MEUR``, ``yr`` for
        the long durations of years). Plain JSON, a new list on each call.
    """
    return [
        {"name": name, "quantity": kind, "unit": unit} for name, (kind, unit) in DISPLAY.items()
    ]
