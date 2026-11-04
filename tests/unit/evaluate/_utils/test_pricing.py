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


class Exchanger(Equipment):
    """A heat exchanger of 2000 W/K that knows its nominal duty when it is given."""

    equipment_kind = "heat_exchanger"
    path = "hx"

    def __init__(self, duty=None):
        """Keep the nominal duty [W], or ``None``."""
        self.duty = duty

    def cost_size(self):
        """Return the conductance [W/K]."""
        return 2000.0

    def cost_size_of(self, quantity):
        """Return the nominal duty for a cost per power."""
        return self.duty if quantity == "power" else None


def test_the_unit_of_a_capex_factor_chooses_the_size_it_multiplies():
    """Per W/K the conductance, per W the nominal duty of the module."""
    per_conductance = economics(capex={"heat_exchanger": Quantity(0.5, "EUR/(W/K)")})
    per_duty = economics(capex={"heat_exchanger": Quantity(0.14, "EUR/W")})
    assert pricing.capex_of(Exchanger(), per_conductance) == pytest.approx(1000.0)
    assert pricing.capex_of(Exchanger(5e6), per_duty) == pytest.approx(7e5)


def test_a_capex_per_unit_counts_one_unit_whatever_the_size():
    """A production pump priced per unit needs no nominal flow."""

    class Pump(Equipment):
        equipment_kind = "production_pump"

        def cost_size(self):
            raise AssertionError("a price per unit reads no size")

    section = economics(capex={"production_pump": Quantity(0.8, "MEUR")})
    assert pricing.capex_of(Pump(), section) == pytest.approx(8e5)


def test_a_size_a_basis_needs_and_the_module_lacks_raises_naming_it():
    """A module with no size of that quantity has no value; one whose size is unset is missing."""
    per_duty = economics(capex={"heat_exchanger": Quantity(0.14, "EUR/W")})
    with raises(gm.errors.ValidationError, "no_value", match=r"hx .*per W"):
        pricing.capex_of(Exchanger(), per_duty)

    class Tank(Equipment):
        equipment_kind = "thermal_storage"
        path = "tank"

        def cost_size(self):
            return 10.0

    per_energy = economics(capex={"thermal_storage": Quantity(3, "EUR/MWh")})
    with raises(gm.errors.ValidationError, "no_value", match=r"tank"):
        pricing.capex_of(Tank(), per_energy)
