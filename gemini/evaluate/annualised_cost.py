"""Annualised system cost."""

from gemini.evaluate._utils.levelised import annualised
from gemini.evaluate._utils.outcome import reported
from gemini.run._utils.apply import apply_case


def annualised_cost(plant, case, results, on_error="raise"):
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

    Returns
    -------
    Value
        A ``gm.units.Quantity`` in SI, with the parts of the result in ``parts`` (``to_plain``
        gives the JSON). ``{value, unit, capex, opex, annuity_factor, discount_rate,
        analysis_period}``, the last
        five each a value. A plant without equipment with a cost has no value.
    """
    return reported(
        on_error,
        "currency/yr",
        lambda: annualised(apply_case(plant, case), case, results, on_error),
    )
