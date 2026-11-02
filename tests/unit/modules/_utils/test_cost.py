"""The capex and the fixed opex of a module from the economics of a case."""

import pytest

import gemini as gm
from gemini.modules._utils import cost
from gemini.units import Quantity
from tests.fixtures.cases import make_case
from tests.fixtures.errors import raises


def economics(**parts):
    """Return the economics of a case with ``parts``."""
    return make_case(economics=parts).economics


def test_the_factor_of_a_kind_is_read_in_si():
    """A degasser costs a fixed amount."""
    section = economics(capex={"degasser": Quantity(1.5, "MEUR")})
    assert cost.capex_factor(section, "degasser") == pytest.approx(1.5e6)


def test_a_factor_the_case_lacks_is_missing_assumption_naming_the_path():
    """No capex section, or no factor of the kind."""
    for section in (economics(currency="EUR"), economics(capex={})):
        with raises(
            gm.errors.ValidationError,
            "missing_assumption",
            match=r"economics\.capex\.boiler",
        ):
            cost.capex_factor(section, "boiler")


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
            cost.fixed_share(section, "boiler")


def test_equipment_costs_its_factor_times_its_size_and_a_share_of_that_a_year():
    """A kind of ``pipe`` at 300 per metre, 120 m, and 2 %/yr."""

    class Line(cost.Equipment):
        equipment_kind = "pipe"
        length = 120.0

        def capex(self, economics):
            return self.capex_of(economics, self.length)

    section = economics(
        capex={"pipe": Quantity(300.0, "currency/m")},
        opex={"fixed": {"pipe": Quantity(2, "%/yr")}},
    )
    assert Line().capex(section) == pytest.approx(36000.0)
    assert Line().fixed_opex(section) == pytest.approx(720.0)
    assert cost.Equipment.equipment_kind is None
