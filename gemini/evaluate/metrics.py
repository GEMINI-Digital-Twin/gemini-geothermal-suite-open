"""The metrics a table of ``gm.evaluate`` shows, with their quantity and display unit."""

from gemini.evaluate._utils.display import DISPLAY, OBJECTIVES, TITLES

__all__ = ["metrics"]


def metrics():
    """Return the metrics a table of results shows, each with its quantity and display unit.

    Returns
    -------
    list of dict
        ``{name, quantity, unit, title, objective}`` for each metric, in a fixed order:
        ``quantity`` is the key of ``gm.units.display.DISPLAY_UNITS`` the metric is shown by
        (``energy``, ``power``, ``money``, ...) and ``unit`` the unit it is shown in (``MWh``,
        ``MW``, ``MEUR``, ``yr`` for the long durations of years); ``title`` is a readable label;
        ``objective`` is whether the metric is a target for ``gm.study.minimize`` (a cost or an
        emission; a temperature, a flow or a delivered energy is not). Plain JSON, a new list on
        each call.
    """
    return [
        {
            "name": name,
            "quantity": kind,
            "unit": unit,
            "title": TITLES[name],
            "objective": name in OBJECTIVES,
        }
        for name, (kind, unit) in DISPLAY.items()
    ]
