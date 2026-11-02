"""The margin of a unit on a supply line."""

from gemini.modules.cooling import AbsorptionUnit, AdsorptionChiller
from gemini.modules.heating import Boiler, ElectricBoiler, HeatPump
from gemini.units import Quantity


def test_a_unit_that_can_sit_on_a_supply_line_declares_a_margin_with_no_default():
    """Heating and cooling units declare ``supply_margin`` in K, empty until the plant states it."""
    for cls in (HeatPump, Boiler, ElectricBoiler, AbsorptionUnit, AdsorptionChiller):
        unit = cls()
        assert unit.supply_margin is None
        unit.set_params("", {"supply_margin": Quantity(2, "K")})
        assert unit.supply_margin == 2.0
