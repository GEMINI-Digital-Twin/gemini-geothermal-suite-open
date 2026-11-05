"""The levelised cost of a product and the annualised cost of a plant."""

from gemini.engine.apply import apply_case
from gemini.evaluate._utils.cost import annuity, investment, period_cost, yearly_cost
from gemini.evaluate._utils.discounting import discounting
from gemini.evaluate._utils.flows import Flows
from gemini.evaluate._utils.outcome import reported, unavailable
from gemini.units.shapes import measure


def levelised(plant, case, results, product, on_error):
    """Return the levelised cost of ``product`` ("heat" or "cold") over the analysis period."""
    return reported(
        on_error,
        "currency/J",
        lambda: _cost_of(apply_case(plant, case), case, results, product, on_error),
    )


def _share(case, product):
    """Return the share of the cost charged to ``product``, or ``None`` when the case lacks it."""
    accounting = case.economics.accounting
    allocation = None if accounting is None else accounting.allocation
    share = None if allocation is None else allocation.heat_cost_share
    if share is None:
        return None
    return share if product == "heat" else 1 - share


def _cost_of(plant, case, results, product, on_error):
    """Compute the levelised cost; ``on_error`` applies to a value the plant cannot give."""
    rate, years = discounting(case)
    cost = investment(plant, case, on_error)
    unit = "currency/J"
    if cost.value is None:
        return unavailable(unit, cost.reason, on_error)
    flows = Flows(plant, results)
    other = "cold" if product == "heat" else "heat"
    delivered = flows.energy(product)
    if delivered <= 0:
        return unavailable(unit, f"the run delivers no {product}", on_error)
    share = 1.0
    if flows.energy(other) > 0:
        share = _share(case, product)
        if share is None:
            reason = "the plant delivers heat and cold; the split of its cost is not defined"
            return unavailable(unit, reason, on_error)
    yearly = yearly_cost(plant, case, results, "raise").value
    factor = annuity(rate, years)
    return measure(
        share * period_cost(cost.value, yearly, factor) / (delivered * factor),
        unit,
        capex=measure(cost.value, cost.unit),
        opex=measure(yearly, "currency/yr"),
        energy=measure(delivered, "J/yr"),
        discount_rate=measure(rate, "-"),
        analysis_period=measure(years, "yr"),
    )


def annualised(plant, case, results, on_error):
    """Return the annualised cost of a plant that already has its design values."""
    rate, years = discounting(case)
    cost = investment(plant, case, on_error)
    unit = "currency/yr"
    if cost.value is None:
        return unavailable(unit, cost.reason, on_error)
    yearly = yearly_cost(plant, case, results, "raise").value
    factor = annuity(rate, years)
    return measure(
        period_cost(cost.value, yearly, factor) / factor,
        unit,
        capex=measure(cost.value, cost.unit),
        opex=measure(yearly, unit),
        annuity_factor=measure(factor, "yr"),
        discount_rate=measure(rate, "-"),
        analysis_period=measure(years, "yr"),
    )
