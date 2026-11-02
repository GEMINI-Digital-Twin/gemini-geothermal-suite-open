"""The price of equipment: its unit cost in the economics of a case times its size."""

import pytest

import gemini as gm
from gemini.evaluate._utils import pricing
from gemini.modules._utils.equipment import Equipment
from gemini.units import Quantity
from tests.fixtures.cases import make_case
from tests.fixtures.errors import raises


def economics(**parts):
    """Return the economics of a case with ``parts``."""
    return make_case(economics=parts).economics


def test_the_factor_of_a_kind_is_read_in_si():
    """A degasser costs a fixed amount."""
    section = economics(capex={"degasser": Quantity(1.5, "MEUR")})
    assert pricing.capex_factor(section, "degasser") == pytest.approx(1.5e6)


def test_a_factor_the_case_lacks_is_missing_assumption_naming_the_path():
    """No capex section, or no factor of the kind."""
    for section in (economics(currency="EUR"), economics(capex={})):
        with raises(
            gm.errors.ValidationError,
            "missing_assumption",
            match=r"economics\.capex\.boiler",
        ):
            pricing.capex_factor(section, "boiler")


def test_a_share_the_case_lacks_is_missing_assumption_naming_the_path():
    """No opex section, no fixed shares, or no share of the kind."""
    sections = (
        economics(currency="EUR"),
        economics(opex={}),
        economics(opex={"fixed": {"flare": Quantity(1, "%/yr")}}),
    )
    for section in sections:
        with raises(
            gm.errors.ValidationError,
            "missing_assumption",
            match=r"economics\.opex\.fixed\.boiler",
        ):
            pricing.fixed_share(section, "boiler")


def test_equipment_costs_its_factor_times_its_size_and_a_share_of_that_a_year():
    """A kind of ``pipe`` at 300 per metre, 120 m, and 2 %/yr."""

    class Line(Equipment):
        equipment_kind = "pipe"

        def cost_size(self):
            return 120.0

    section = economics(
        capex={"pipe": Quantity(300.0, "currency/m")},
        opex={"fixed": {"pipe": Quantity(2, "%/yr")}},
    )
    assert pricing.capex_of(Line(), section) == pytest.approx(36000.0)
    assert pricing.fixed_opex_of(Line(), section) == pytest.approx(720.0)


def test_drilling_costs_the_cost_per_metre_of_its_length_times_the_length():
    """A constant drilling cost of 2000 per metre over 1500 m."""

    class Well(Equipment):
        equipment_kind = "drilling"

        def cost_size(self):
            return 1500.0

    section = economics(
        capex={"drilling": Quantity(2000.0, "currency/m")},
        opex={"fixed": {"drilling": Quantity(1, "%/yr")}},
    )
    assert pricing.capex_of(Well(), section) == 2000.0 * 1500.0
    assert pricing.fixed_opex_of(Well(), section) == pytest.approx(0.01 * 2000.0 * 1500.0)
