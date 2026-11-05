"""Investment and yearly cost of a plant run, before the case and the error policy of a caller."""

import numpy as np

from gemini._utils.strings import join_path
from gemini.case._utils.access import require
from gemini.case._utils.kinds import PRODUCTS, is_priced
from gemini.evaluate._utils import pricing
from gemini.evaluate._utils.co2_steps import priced_steps
from gemini.evaluate._utils.flows import Flows
from gemini.evaluate._utils.level import level
from gemini.evaluate._utils.outcome import unavailable
from gemini.evaluate._utils.series import energy
from gemini.units import SECONDS_PER_YEAR
from gemini.units.shapes import measure

NO_COST = (
    "no module of the plant is equipment with a cost: a module declares it with an "
    "equipment_kind and a cost_size()"
)
"""The reason when a plant has no equipment with a cost."""

BILLED = ("electricity", "fuel", "waste", "chemical")
"""The flows that are bought or discarded, each with a bill of its name."""

ECONOMICS = pricing.ECONOMICS
"""The path of the economics in a case."""


def annuity(rate, years):
    """Return the sum of ``1 / (1 + rate) ** t`` for the years ``t = 1 .. years``.

    The closed form ``(1 - (1 + rate) ** -years) / rate`` is used, so a part of a year gives its
    continuous value and not a sum of whole years.
    """
    if rate == 0:
        return float(years)
    return (1 - (1 + rate) ** -years) / rate


def period_cost(investment, yearly, factor):
    """Return the discounted cost of an analysis period: ``capex + opex * A``.

    Over ``A`` it is the annualised cost ``capex / A + opex``; ``lcoh`` and ``lcoc`` divide it by
    ``energy * A`` in one step, so their numbers stay those of that order of operations.
    """
    return investment + yearly * factor


def equipment(plant):
    """Return ``{path: module}`` of the modules of ``plant`` that are equipment with a kind."""
    return {
        path: module
        for path, module in plant.named_modules()
        if getattr(module, "equipment_kind", None) is not None
    }


def priced(plant, economics):
    """Return ``{path: module}`` of the equipment of ``plant`` that ``economics`` prices.

    A kind of ``PRICED_WHEN_GIVEN`` (an ice store) without its capex factor is left out.
    """
    return {
        path: module
        for path, module in equipment(plant).items()
        if is_priced(module.equipment_kind, economics)
    }


def investment(plant, case, on_error):
    """Return the investment as ``capex`` does, for a plant that already has its design values."""
    economics = require(case, ECONOMICS)
    units = priced(plant, economics)
    if not units:
        return unavailable("currency", NO_COST, on_error)
    items = {
        path: measure(pricing.capex_of(module, economics), "currency", kind=module.equipment_kind)
        for path, module in units.items()
    }
    parts = {"modules": items}
    if economics.price_year is not None:
        parts["price_year"] = measure(economics.price_year, "-")
    return measure(sum(item.value for item in items.values()), "currency", **parts)


def fixed_opex(plant, case):
    """Return the fixed opex of a year [currency/yr] of each kind of equipment of ``plant``."""
    economics = require(case, ECONOMICS)
    amounts = {}
    for module in priced(plant, economics).values():
        kind = module.equipment_kind
        amounts[kind] = amounts.get(kind, 0.0) + pricing.fixed_opex_of(module, economics)
    return amounts


def _bills(flows, case, results, plant):
    """Return the yearly bills of what the plant buys and discards, and of its CO2 when priced."""
    bills = {name: flows.cost(name, case) for name in BILLED}
    carbon = require(case, ECONOMICS).carbon
    if carbon is not None and carbon.price is not None:
        steps = priced_steps(plant, case, results)
        price = level(case, f"{ECONOMICS}.carbon.price", len(steps))
        bills["co2"] = float(np.sum(steps * price)) * SECONDS_PER_YEAR / results.durations.sum()
    return bills


def _produced(path, module, frame, seconds):
    """Return the energy [J] that the module at ``path`` produced over the run; NaN ticks add none.

    A column the run lacks adds nothing.
    """
    first, second = module.product()
    power = frame.get(join_path(path, first))
    if power is None:
        return 0.0
    if second is not None:
        inlet = frame.get(join_path(path, second))
        power = power if inlet is None else power - inlet
    return energy(power, seconds)


def per_energy_opex(plant, case, results):
    """Return the variable opex of a year [currency/yr] of each producing kind, or ``None``.

    ``economics.opex.per_energy`` prices the energy each unit of a kind produces
    (``Equipment.product``), scaled from the run to a year. Without that map there is none; with
    it, a producing kind the plant uses and the map lacks raises ``missing_assumption``.
    """
    economics = require(case, ECONOMICS)
    prices = None if economics.opex is None else economics.opex.per_energy
    if prices is None:
        return None
    frame, seconds = results.to_frame(), results.durations
    scale = SECONDS_PER_YEAR / seconds.sum()
    amounts = {}
    for path, module in priced(plant, economics).items():
        kind = module.equipment_kind
        if kind not in PRODUCTS:
            continue
        price = require(prices, kind, f"{ECONOMICS}.opex.per_energy")
        produced = _produced(path, module, frame, seconds) * scale
        amounts[kind] = amounts.get(kind, 0.0) + price * produced
    return amounts


def _components(amounts, unit):
    """Return each amount of a cost as a value."""
    return {name: measure(amount, unit) for name, amount in amounts.items()}


def yearly_cost(plant, case, results, on_error):
    """Return the annual operating cost as ``opex`` does, for a plant with its design values."""
    flows = Flows(plant, results)
    bills = _bills(flows, case, results, plant)
    unit = "currency/yr"
    if not priced(plant, require(case, ECONOMICS)):
        return unavailable(unit, NO_COST, on_error, components=_components(bills, unit))
    by_kind = fixed_opex(plant, case)
    components = {"fixed": sum(by_kind.values()), **bills}
    parts = {"fixed_by_kind": _components(by_kind, unit)}
    variable = per_energy_opex(plant, case, results)
    if variable is not None:
        components["per_energy"] = sum(variable.values())
        parts["per_energy_by_kind"] = _components(variable, unit)
    return measure(
        sum(components.values()),
        unit,
        components=_components(components, unit),
        **parts,
    )
