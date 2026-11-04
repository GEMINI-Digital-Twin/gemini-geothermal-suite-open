"""What a plant costs and earns: investment, operating cost, levelised costs, NPV and payback."""

from gemini.engine.apply import apply_case
from gemini.evaluate._utils.cashflow import net_cash_flow, subsidy
from gemini.evaluate._utils.cost import annuity, investment, yearly_cost
from gemini.evaluate._utils.discounting import discounting
from gemini.evaluate._utils.display import displayed
from gemini.evaluate._utils.flows import Flows
from gemini.evaluate._utils.levelised import annualised, levelised
from gemini.evaluate._utils.outcome import reported, unavailable
from gemini.units.shapes import measure


def capex(plant, case, on_error="raise", *, units="si"):
    """Return the investment of a plant: the sum of the capex of its equipment, per module.

    A module that is equipment declares a kind (``gemini.case._utils.kinds.EQUIPMENT_KINDS``) and
    a ``cost_size()``: the capex factor of its kind in ``case.economics.capex`` times
    that size. A factor the case lacks for a kind the plant uses raises ``ValidationError``
    (code ``missing_assumption``) naming ``economics.capex.<kind>``; nothing is
    estimated. The design values are those of the plant with the case applied.

    Parameters
    ----------
    plant : Module
        The plant whose modules declare costs.
    case : Case
        Its economics gives the capex factors, the currency label and the price year.
    on_error : {"raise", "record"}, optional
        A value the inputs cannot give raises; ``"record"`` makes it ``None`` with a ``reason``.
    units : {"si", "display"}, optional
        ``"si"`` (the default) is the value as computed; ``"display"`` gives it and its parts in
        the units of ``gm.units.display`` (MEUR, MEUR/yr, EUR/MWh, a span of years in ``yr``).

    Returns
    -------
    Value
        A ``gm.units.Quantity`` in SI, with the parts of the result in ``parts`` (``to_plain``
        gives the JSON). ``{value, unit, modules, price_year}``: ``value`` is the investment in
        the currency of the case (``unit``), ``modules`` maps the path of each module that is
        equipment to its capex, a value with its ``kind``, and ``price_year`` is a value in ``-``
        when the case gives it. A plant with no equipment has no value.
    """
    return displayed(
        units,
        "capex",
        lambda: reported(
            on_error, "currency", lambda: investment(apply_case(plant, case), case, on_error)
        ),
    )


def opex(plant, case, results, on_error="raise", *, units="si"):
    """Return the annual operating cost of a plant run.

    The sum of the fixed opex of each kind of equipment [currency/yr], its share
    ``opex.fixed[kind]`` of the capex of that kind, the yearly bill of the grid electricity, the
    fuel, the waste and the chemicals, and the CO2 emitted per year at ``opex.co2`` when the case
    gives it. The run is scaled to a year. A price along the demand is integrated over the run:
    the power of each step times its price. A share the case lacks for a kind the plant uses
    raises ``missing_assumption`` naming ``economics.opex.fixed.<kind>``. With
    ``economics.opex.per_energy``, the energy each unit of a producing kind made is priced too.

    Parameters
    ----------
    plant : Module
        The plant whose modules declare costs; its design values are those with the case applied.
    case : Case
        Its economics gives the prices, needed only for an energy that the run buys; a missing
        needed price raises ``ValidationError`` (code ``missing_assumption``). Co-produced gas
        costs nothing.
    results : Results
        A finished run of the plant.
    on_error : {"raise", "record"}, optional
        A value the inputs cannot give raises; ``"record"`` makes it ``None`` with a ``reason``.
    units : {"si", "display"}, optional
        ``"si"`` (the default) is the value as computed; ``"display"`` gives it and its parts in
        the units of ``gm.units.display`` (MEUR, MEUR/yr, EUR/MWh, a span of years in ``yr``).

    Returns
    -------
    Value
        A ``gm.units.Quantity`` in SI, with the parts of the result in ``parts`` (``to_plain``
        gives the JSON). ``{value, unit, components, fixed_by_kind}`` with ``unit`` the currency
        per year, ``components`` ``{fixed, electricity, fuel, waste, chemical}`` and ``co2`` with a
        price for it, and ``fixed_by_kind`` the fixed opex of each kind of equipment, each a value
        in that unit; with ``economics.opex.per_energy``, ``components`` has ``per_energy`` and
        ``per_energy_by_kind`` gives it by kind. With no equipment and ``on_error="record"``,
        ``value`` is ``None`` with a ``reason``, and only the bills are given.
    """
    return displayed(
        units,
        "opex",
        lambda: reported(
            on_error,
            "currency/yr",
            lambda: yearly_cost(apply_case(plant, case), case, results, on_error),
        ),
    )


def annualised_cost(plant, case, results, on_error="raise", *, units="si"):
    """Return the annualised system cost [currency/year]: ``capex / A + opex``.

    ``A`` is the annuity factor of ``lcoh``, the sum over the years of the analysis period of
    ``1 / (1 + discount_rate) ** t``; ``capex`` and ``opex`` are those of this package, with the
    yearly cost as scaled from the run, constant over the analysis period.

    Parameters
    ----------
    plant : Module
        The plant of the run.
    case : Case
        Its economics gives the prices, the discount rate and the analysis period.
    results : Results
        The finished run of the plant.
    on_error : {"raise", "record"}, optional
        A value the inputs cannot give raises; ``"record"`` makes it ``None`` with a ``reason``.
    units : {"si", "display"}, optional
        ``"si"`` (the default) is the value as computed; ``"display"`` gives it and its parts in
        the units of ``gm.units.display`` (MEUR, MEUR/yr, EUR/MWh, a span of years in ``yr``).

    Returns
    -------
    Value
        A ``gm.units.Quantity`` in SI, with the parts of the result in ``parts`` (``to_plain``
        gives the JSON). ``{value, unit, capex, opex, annuity_factor, discount_rate,
        analysis_period}``, the last
        five each a value. A plant without equipment with a cost has no value.
    """
    return displayed(
        units,
        "annualised_cost",
        lambda: reported(
            on_error,
            "currency/yr",
            lambda: annualised(apply_case(plant, case), case, results, on_error),
        ),
    )


def lcoh(plant, case, results, on_error="raise", *, units="si"):
    """Return the levelised cost of heat [currency/J]: the discounted cost over the discounted heat.

    ``(capex + opex * A) / (heat * A)`` with ``A`` the annuity factor, the sum over the analysis
    period's years of ``1 / (1 + discount_rate) ** t``. ``capex`` and ``opex`` are the ``capex`` and
    ``opex`` of this package, ``opex`` and ``heat`` are per year as scaled from the run,
    constant over the analysis period, with no degradation, replacement or residual value. The whole
    plant cost is charged to the heat; for a plant that also delivers cold,
    ``economics.accounting.allocation.heat_cost_share`` of it, and without that share it gives no
    value.

    Parameters
    ----------
    plant : Module
        The plant of the run.
    case : Case
        Its economics gives the prices, the discount rate and the analysis period; one it lacks
        raises ``ValidationError`` (code ``missing_assumption``).
    results : Results
        The finished run of the plant.
    on_error : {"raise", "record"}, optional
        A value the inputs cannot give raises; ``"record"`` makes it ``None`` with a ``reason``.
    units : {"si", "display"}, optional
        ``"si"`` (the default) is the value as computed; ``"display"`` gives it and its parts in
        the units of ``gm.units.display`` (MEUR, MEUR/yr, EUR/MWh, a span of years in ``yr``).

    Returns
    -------
    Value
        A ``gm.units.Quantity`` in SI, with the parts of the result in ``parts`` (``to_plain``
        gives the JSON). ``{value, unit, capex, opex, energy, discount_rate,
        analysis_period}``, the last five each
        a value; ``value`` in currency/J (``.to("EUR/MWh")`` converts). A plant that
        declares no cost, delivers no heat, or also delivers cold without a ``heat_cost_share`` has
        no value.
    """
    return displayed(units, "lcoh", lambda: levelised(plant, case, results, "heat", on_error))


def lcoc(plant, case, results, on_error="raise", *, units="si"):
    """Return the levelised cost of cold [currency/J]; the cooling twin of ``lcoh``.

    The same formula with the cold delivered (what the water gains across the ``CoolingGrid``
    leaves) in place of the heat, and for a plant that also delivers heat the share of the cost
    ``allocation.heat_cost_share`` leaves. The parameters and the return shape are those of
    ``lcoh``.
    """
    return displayed(units, "lcoc", lambda: levelised(plant, case, results, "cold", on_error))


def lcts(plant, case, results, on_error="raise", *, units="si"):
    """Return the levelised cost of thermal supply [currency/J].

    ``annualised_cost / (heat + cold)``, the heat and the cold delivered per year as scaled from
    the run. One cost over both products, so it needs no ``heat_cost_share``. The parameters are
    those of ``annualised_cost``.

    Returns
    -------
    Value
        A ``gm.units.Quantity`` in SI, with the parts of the result in ``parts`` (``to_plain``
        gives the JSON). ``{value, unit, annualised_cost, heat, cold}``, the last three each
        a value, ``heat`` and
        ``cold`` in J/year; ``value`` in currency/J (``.to("EUR/MWh")`` converts). A plant
        without equipment with a cost, or a run that delivers neither heat nor cold, has no value.
    """
    return displayed(
        units,
        "lcts",
        lambda: reported(on_error, "currency/J", lambda: _lcts(plant, case, results, on_error)),
    )


def _lcts(plant, case, results, on_error):
    """Return the cost per joule of heat and cold; ``on_error`` applies to a missing value."""
    unit = "currency/J"
    sited = apply_case(plant, case)
    flows = Flows(sited, results)
    heat, cold = flows.energy("heat"), flows.energy("cold")
    if heat + cold <= 0:
        return unavailable(unit, "the run delivers neither heat nor cold", on_error)
    cost = annualised(sited, case, results, on_error)
    if cost.value is None:
        return unavailable(unit, cost.reason, on_error)
    return measure(
        cost.value / (heat + cold),
        unit,
        annualised_cost=measure(cost.value, cost.unit),
        heat=measure(heat, "J/yr"),
        cold=measure(cold, "J/yr"),
    )


def npv(plant, case, results, on_error="raise", *, units="si"):
    """Return the net present value [currency]: ``-capex + (revenue - opex) * A``.

    ``A`` is the annuity factor, the sum over the years of the analysis period of
    ``1 / (1 + rate) ** t``.
    The yearly revenue is the heat and cold delivered per year at the prices of ``heat`` and
    ``cold``, integrated over the run when a price follows the demand; the yearly cost is
    ``opex``. Both are constant over the analysis period, with no degradation, tax, replacement or
    residual value. A subsidy of the case (``economics.revenue.subsidy``) adds its amount per
    year for its duration, within the analysis period, discounted like the rest; a subsidy per
    energy pays its amount on the useful heat of a year, up to its ``cap``.

    Parameters
    ----------
    plant : Module
        The plant of the run.
    case : Case
        Its economics gives the prices, the discount rate and the analysis period. Anything
        needed and given nowhere raises ``ValidationError`` (code ``missing_assumption``).
    results : Results
        The finished run of the plant.
    on_error : {"raise", "record"}, optional
        A value the inputs cannot give raises; ``"record"`` makes it ``None`` with a ``reason``.
    units : {"si", "display"}, optional
        ``"si"`` (the default) is the value as computed; ``"display"`` gives it and its parts in
        the units of ``gm.units.display`` (MEUR, MEUR/yr, EUR/MWh, a span of years in ``yr``).

    Returns
    -------
    Value
        A ``gm.units.Quantity`` in SI, with the parts of the result in ``parts`` (``to_plain``
        gives the JSON). ``{value, unit, capex, net_cash_flow, discount_rate,
        analysis_period}``, the last four each
        a value, with ``value`` and ``capex`` in the currency (``unit``) and ``net_cash_flow`` in
        currency per year. A plant without equipment with a cost has no value.
    """
    return displayed(
        units,
        "npv",
        lambda: reported(on_error, "currency", lambda: _npv(plant, case, results, on_error)),
    )


def _heat(plant, results):
    """Return a function that gives the useful heat of a year [J/yr] of a run when called."""
    return lambda: Flows(plant, results).energy("heat")


def _npv(plant, case, results, on_error):
    """Return the net present value; ``on_error`` applies to a plant without a cost."""
    rate, years = discounting(case)
    sited = apply_case(plant, case)
    cost, flow, unit, reason = net_cash_flow(sited, case, results, on_error)
    if cost is None:
        return unavailable(unit, reason, on_error)
    amount, paid = subsidy(case, _heat(sited, results))
    granted = amount * annuity(rate, min(paid, years)) if amount else 0.0
    return measure(
        flow * annuity(rate, years) + granted - cost,
        unit,
        capex=measure(cost, unit),
        net_cash_flow=measure(flow, "currency/yr"),
        discount_rate=measure(rate, "-"),
        analysis_period=measure(years, "yr"),
    )


def payback(plant, case, results, on_error="raise", *, units="si"):
    """Return the simple payback time [year]: ``capex / (revenue - opex)``, without discounting.

    A subsidy of the case (``economics.revenue.subsidy``) adds its amount per year to the cash flow
    for its duration only (a subsidy per energy, its amount on the useful heat of a year up to its
    ``cap``): the payback is the time at which the sum of the cash flows equals the capex.

    Parameters
    ----------
    plant : Module
        The plant of the run.
    case : Case
        Its economics gives the prices of ``heat``, ``cold`` and energy, as for ``npv``; anything
        needed and missing raises ``ValidationError`` (code ``missing_assumption``).
    results : Results
        The finished run of the plant.
    on_error : {"raise", "record"}, optional
        A value the inputs cannot give raises; ``"record"`` makes it ``None`` with a ``reason``.
    units : {"si", "display"}, optional
        ``"si"`` (the default) is the value as computed; ``"display"`` gives it and its parts in
        the units of ``gm.units.display`` (MEUR, MEUR/yr, EUR/MWh, a span of years in ``yr``).

    Returns
    -------
    Value
        A ``gm.units.Quantity`` in SI, with the parts of the result in ``parts`` (``to_plain``
        gives the JSON). ``{value, unit, capex, net_cash_flow}`` with ``unit`` ``"yr"`` and
        the last two each a value. A plant without equipment with a cost, or whose yearly revenue
        does not exceed its yearly cost (it never pays back), has no value.
    """
    return displayed(
        units,
        "payback",
        lambda: reported(on_error, "yr", lambda: _payback(plant, case, results, on_error)),
    )


def _payback(plant, case, results, on_error):
    """Return the payback time; ``on_error`` applies to a value the plant cannot give."""
    sited = apply_case(plant, case)
    cost, flow, unit, reason = net_cash_flow(sited, case, results, on_error)
    if cost is None:
        return unavailable("yr", reason, on_error)
    details = dict(capex=measure(cost, unit), net_cash_flow=measure(flow, "currency/yr"))
    amount, paid = subsidy(case, _heat(sited, results))
    if flow <= 0 and not (amount and (flow + amount) * paid >= cost):
        reason = "the yearly revenue does not exceed the yearly cost"
        return unavailable("yr", reason, on_error, **details)
    return measure(_years(cost, flow, amount, paid), "yr", **details)


def _years(cost, flow, amount, paid):
    """Return the years until the cash flow repays ``cost``, a subsidy being paid ``paid`` years."""
    if amount and (flow + amount) * paid < cost:
        return paid + (cost - (flow + amount) * paid) / flow
    return cost / (flow + amount)
