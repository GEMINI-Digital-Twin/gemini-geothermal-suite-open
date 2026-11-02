"""The discount rate and the analysis period of a case."""

from gemini import units
from gemini.case._utils.access import require
from gemini.errors import ValidationError


def discounting(case):
    """Return ``(rate, years)``: the discount rate and the analysis period (in years) of ``case``.

    A value the case lacks raises ``ValidationError`` (code ``missing_assumption``); a negative rate
    or a period under one year raises ``ValidationError``.
    """
    rate = require(case, "economics.discount_rate")
    years = require(case, "economics.analysis_period") / units.Quantity(1, "yr").si
    if rate < 0:
        raise ValidationError(
            f"discount_rate = {rate}; expected a rate of 0 or more", path="economics.discount_rate"
        )
    if years < 1:
        raise ValidationError(
            f"analysis_period = {years} yr; expected 1 year or more",
            path="economics.analysis_period",
        )
    return rate, years
