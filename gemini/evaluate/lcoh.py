"""Levelised cost of heat."""

from gemini.evaluate._utils.levelised import levelised


def lcoh(plant, case, results, on_error="raise"):
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
    return levelised(plant, case, results, "heat", on_error)
