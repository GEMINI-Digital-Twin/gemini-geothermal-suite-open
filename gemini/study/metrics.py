"""The metrics a study reads, with the unit it records them in and what each one means."""

from gemini.evaluate._utils.display import OBJECTIVES
from gemini.study._utils.trial import METRICS

__all__ = ["metrics"]

_WORDS = {
    "heating_coverage": (
        "Heating coverage",
        "-",
        "higher",
        "The heat delivered over the heat demanded in the period, between 0 and 1.",
    ),
    "cooling_coverage": (
        "Cooling coverage",
        "-",
        "higher",
        "The cold delivered over the cold demanded in the period, between 0 and 1.",
    ),
    "cop": (
        "Coefficient of performance",
        "-",
        "higher",
        "The heat delivered over the electricity consumed in the period.",
    ),
    "peak_heat": (
        "Peak heat demand",
        "W",
        None,
        "The largest heating power delivered in one step of the period.",
    ),
    "peak_cold": (
        "Peak cold demand",
        "W",
        None,
        "The largest cooling power delivered in one step of the period.",
    ),
    "lcoh": (
        "Cost of heat",
        "currency/J",
        "lower",
        "The levelised cost of heat: the discounted cost over the discounted heat delivered.",
    ),
    "lcoc": (
        "Cost of cold",
        "currency/J",
        "lower",
        "The levelised cost of cold: the discounted cost over the discounted cold delivered.",
    ),
    "lcts": (
        "Cost of thermal supply",
        "currency/J",
        "lower",
        "The levelised cost of thermal supply: the annualised cost over the heat and the cold "
        "delivered in a year.",
    ),
    "annualised_cost": (
        "Annualised cost",
        "currency/yr",
        "lower",
        "The yearly cost of the system: the investment spread over the analysis period at the "
        "discount rate, plus the operating cost.",
    ),
    "co2": (
        "CO2 emissions",
        "kg",
        "lower",
        "The CO2-equivalent emitted over the period: direct, from methane and from the electricity "
        "bought.",
    ),
}
"""The ``(title, unit, better, description)`` of each name of ``METRICS``."""


def metrics():
    """Return the metrics a study reads, each with its unit and what it means.

    These are the names ``objective``, ``objectives`` and ``metrics`` of a study accept (a
    ``-`` before a name maximises it), the same list the settings of ``gm.study.kinds()`` offer.

    Returns
    -------
    list of dict
        ``{name, title, unit, description, better, objective}`` for each metric, in a fixed order.
        ``unit`` is the SI unit the study records the value in (``currency`` is the
        ``economics.currency`` of the case; ``-`` is dimensionless); ``better`` is ``"lower"`` or
        ``"higher"`` when one direction is better, ``None`` for a size such as a peak power;
        ``objective`` is whether the metric is one worth minimising (a cost or an emission, the
        ``objective`` choices of ``gm.study.kinds()``). Plain JSON, a new list on each call.
    """
    return [
        {
            "name": name,
            "title": _WORDS[name][0],
            "unit": _WORDS[name][1],
            "description": _WORDS[name][3],
            "better": _WORDS[name][2],
            "objective": name in OBJECTIVES,
        }
        for name in METRICS
    ]
