"""The annuity and the lifetime cost."""

import pytest

import gemini as gm
from gemini.evaluate._utils import cost
from gemini.units import SECONDS_PER_YEAR, Quantity
from tests.fixtures.cases import make_case
from tests.fixtures.errors import raises
from tests.fixtures.result_tables import make_results


def test_annuity_is_the_discounted_year_count():
    """Ten years at 5 % are 7.7217 discounted years; at 0 % they are ten."""
    assert cost.annuity(0.05, 10) == pytest.approx(7.721734929, rel=1e-9)
    assert cost.annuity(0.0, 10) == 10.0


def test_annuity_of_a_part_of_a_year_is_the_closed_form():
    """A period of 2.5 years is read by the closed form, not by a sum of whole years."""
    closed = (1 - 1.05**-2.5) / 0.05
    assert cost.annuity(0.05, 2.5) == pytest.approx(closed, rel=1e-12)
    assert cost.annuity(0.0, 2.5) == 2.5
    assert cost.annuity(0.05, 2) == pytest.approx(1 / 1.05 + 1 / 1.05**2, rel=1e-12)


def _engine_case(per_energy=None):
    """Return a day's case pricing a CHP and a boiler, with ``per_energy`` as its variable opex."""
    opex = {"fixed": {"chp": Quantity(1, "%/yr"), "boiler": Quantity(2, "%/yr")}}
    if per_energy is not None:
        opex["per_energy"] = per_energy
    capex = {"chp": Quantity(1, "EUR/W"), "boiler": Quantity(0.1, "EUR/W")}
    return make_case(economics={"capex": capex, "opex": opex})


def _engine_plant():
    """Return a plant of a 1 MW CHP and a 2 MW boiler, ports aside."""
    plant = gm.Plant("Units")
    plant.add("CHP", name="engine", params={"electric_capacity": Quantity(1, "MW")})
    plant.add("Boiler", name="burner", params={"capacity": Quantity(2, "MW")})
    return plant


ENGINE_RUN = {
    "engine": {"power_out": [8e5] * 24},
    "burner": {
        "fluid_out.enthalpy_flow": [3e6] * 24,
        "fluid_in.enthalpy_flow": [2.5e6] * 12 + [float("nan")] * 12,
    },
}
"""A day: the CHP makes 0.8 MW of electricity, the boiler 0.5 MW of heat for half of it."""


def test_the_variable_opex_per_energy_is_the_energy_each_unit_produces_times_its_price():
    """The CHP's electricity and the boiler's heat over a year, at their kind's price."""
    case = _engine_case({"chp": Quantity(5.4, "EUR/MWh"), "boiler": Quantity(1.1, "EUR/MWh")})
    found = cost.yearly_cost(_engine_plant(), case, make_results(ENGINE_RUN), "raise")
    chp = 5.4 / 3.6e9 * 8e5 * SECONDS_PER_YEAR
    boiler = 1.1 / 3.6e9 * 5e5 * SECONDS_PER_YEAR / 2
    assert found.parts["per_energy_by_kind"]["chp"].value == pytest.approx(chp)
    assert found.parts["per_energy_by_kind"]["boiler"].value == pytest.approx(boiler)
    assert found.parts["components"]["per_energy"].value == pytest.approx(chp + boiler)
    fixed = found.parts["components"]["fixed"].value
    assert found.value == pytest.approx(fixed + chp + boiler)


def test_without_a_variable_opex_per_energy_the_opex_is_as_before():
    """No section: no component, no part."""
    found = cost.yearly_cost(_engine_plant(), _engine_case(), make_results(ENGINE_RUN), "raise")
    assert "per_energy" not in found.parts["components"]
    assert "per_energy_by_kind" not in found.parts


def test_a_producing_kind_the_variable_opex_lacks_is_a_missing_assumption():
    """Given for the CHP, the boiler's is asked for by its path."""
    case = _engine_case({"chp": Quantity(5.4, "EUR/MWh")})
    with raises(gm.errors.ValidationError, "missing_assumption", match=r"opex\.per_energy\.boiler"):
        cost.yearly_cost(_engine_plant(), case, make_results(ENGINE_RUN), "raise")
