"""The yearly cash flow of a plant run, shared by the net present value and the payback."""

from gemini.case._utils.access import require
from gemini.evaluate._utils.cost import investment, yearly_cost
from gemini.evaluate._utils.flows import Flows
from gemini.units import SECONDS_PER_YEAR


def net_cash_flow(plant, case, results, on_error):
    """Return ``(capex, yearly net cash flow, unit, reason)``; no cost gives ``None`` numbers.

    ``plant`` already has its design values. The revenue is the heat and the cold sold at their
    prices.
    """
    cost = investment(plant, case, on_error)
    if cost.value is None:
        return None, None, cost.unit, cost.reason
    yearly = yearly_cost(plant, case, results, "raise")
    flows = Flows(plant, results)
    revenue = flows.cost("heat", case) + flows.cost("cold", case)
    return cost.value, revenue - yearly.value, cost.unit, None


SUBSIDY = "economics.revenue.subsidy"
"""The path of the subsidy in a case."""


def subsidy(case, heat):
    """Return ``(amount, years)``: the subsidy [currency/yr] and how long it is paid [yr].

    A case without a subsidy, or with only one of its two figures, gives ``(0.0, 0.0)``: a subsidy
    is optional revenue, and it earns nothing unless it states both. It is paid on top of the
    cash flow of the run, from the first year, for the years it states. A subsidy per energy is
    paid on the useful heat of a year, ``heat()`` [J/yr], up to its ``cap``: an energy per year,
    or full-load hours per year times the ``capacity``, which raises ``missing_assumption`` when
    absent.
    """
    revenue = None if case.economics is None else case.economics.revenue
    given = None if revenue is None else revenue.subsidy
    if given is None or given.amount is None or given.duration is None:
        return 0.0, 0.0
    years = given.duration / SECONDS_PER_YEAR
    if given.leaf("amount").quantity != "money_per_energy":
        return float(given.amount), years
    return float(given.amount) * min(heat(), _cap(case, given)), years


def _cap(case, given):
    """Return the most heat a year [J/yr] a subsidy per energy is paid on; infinite without cap."""
    if given.cap is None:
        return float("inf")
    if given.leaf("cap").quantity == "annual_duration":
        return given.cap * require(case, f"{SUBSIDY}.capacity")
    return given.cap
