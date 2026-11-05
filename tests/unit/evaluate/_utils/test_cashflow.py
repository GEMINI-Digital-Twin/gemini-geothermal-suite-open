"""The yearly cash flow shared by the net present value and the payback."""

import pytest

import gemini as gm
from gemini.evaluate._utils.cashflow import net_cash_flow, subsidy
from gemini.evaluate._utils.cost import annuity as annuity_factor
from gemini.units import SECONDS_PER_YEAR, Quantity
from tests.fixtures.cases import FINANCE, costed_economics, make_case
from tests.fixtures.costed_plants import day, heating_plant
from tests.fixtures.errors import raises

CASE = make_case(
    economics=costed_economics(
        energy={"electricity": Quantity(2e-8, "currency/J")},
        revenue={"heat": Quantity(5e-8, "currency/J")},
    )
)


def test_the_net_cash_flow_is_the_revenue_less_the_yearly_cost():
    """Heat sold at 5e-8 per joule against the fixed opex and the electricity."""
    capex, flow, unit, reason = net_cash_flow(heating_plant(), CASE, day(), "raise")
    heat = 1000.0 * SECONDS_PER_YEAR
    opex = 10.0 + 2e-8 * 100.0 * SECONDS_PER_YEAR
    assert (capex, unit, reason) == (1000.0, "currency", None)
    assert flow == pytest.approx(5e-8 * heat - opex, rel=1e-12)


def test_a_plant_without_equipment_has_no_cash_flow():
    """The numbers are None and the reason says why."""
    capex, flow, _, reason = net_cash_flow(heating_plant(costed=False), CASE, day(), "record")
    assert capex is None and flow is None and "no module of the plant is equipment" in reason


HEAT = 4e13
"""Useful heat of a year [J]: about 11.1 GWh."""


def subsidised(**given):
    """Return a case whose only economics is a subsidy of ``given`` for 15 years."""
    return make_case(economics={"revenue": {"subsidy": {"duration": Quantity(15, "yr"), **given}}})


def test_a_subsidy_per_year_is_paid_as_it_is_given():
    """An amount per year needs no heat."""
    case = subsidised(amount=Quantity(1e6, "EUR/yr"))
    assert subsidy(case, lambda: pytest.fail("no heat is read")) == (1e6, pytest.approx(15))


def test_a_subsidy_per_energy_is_paid_on_the_useful_heat_up_to_its_cap():
    """EUR/MWh on the heat, capped by MWh/yr or by full-load hours times the capacity."""
    per_energy = Quantity(50, "EUR/MWh")
    found, years = subsidy(subsidised(amount=per_energy), lambda: HEAT)
    assert found == pytest.approx(50 * HEAT / 3.6e9) and years == pytest.approx(15)
    capped = subsidised(amount=per_energy, cap=Quantity(5000, "MWh/yr"))
    assert subsidy(capped, lambda: HEAT)[0] == pytest.approx(50 * 5000)
    hours = subsidised(amount=per_energy, cap=Quantity(3000, "h/yr"), capacity=Quantity(2, "MW"))
    assert subsidy(hours, lambda: HEAT)[0] == pytest.approx(50 * 6000)
    assert subsidy(hours, lambda: 1e12)[0] == pytest.approx(50 * 1e12 / 3.6e9)


def test_a_cap_in_full_load_hours_needs_the_capacity_it_is_granted_for():
    """``missing_assumption`` naming ``economics.revenue.subsidy.capacity``."""
    case = subsidised(amount=Quantity(50, "EUR/MWh"), cap=Quantity(3000, "h/yr"))
    with raises(
        gm.errors.ValidationError, "missing_assumption", match=r"revenue\.subsidy\.capacity"
    ):
        subsidy(case, lambda: HEAT)


def test_a_cap_on_a_subsidy_per_year_is_refused():
    """A cap limits the energy a subsidy per MWh is paid on; an amount per year has none."""
    with raises(gm.errors.ValidationError, "invalid_value", match=r"subsidy\.cap"):
        subsidised(amount=Quantity(1e6, "EUR/yr"), cap=Quantity(5000, "MWh/yr"))


def test_the_net_present_value_counts_a_subsidy_per_energy_on_the_heat_of_the_run():
    """NPV: the subsidy per MWh of the year's useful heat, discounted over its duration."""
    data = costed_economics(
        energy={"electricity": Quantity(2e-8, "currency/J")},
        revenue={"heat": Quantity(5e-8, "currency/J")},
        **FINANCE,
    )
    plain = make_case(economics=data)
    data["revenue"]["subsidy"] = {"amount": Quantity(1e-8, "EUR/J"), "duration": Quantity(5, "yr")}
    paid = make_case(economics=data)
    gain = gm.evaluate.npv(heating_plant(), paid, day()).value
    gain -= gm.evaluate.npv(heating_plant(), plain, day()).value
    factor = annuity_factor(plain.economics.discount_rate, 5)
    assert gain == pytest.approx(1e-8 * 1000.0 * SECONDS_PER_YEAR * factor)
