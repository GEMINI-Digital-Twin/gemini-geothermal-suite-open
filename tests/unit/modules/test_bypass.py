"""The bypass of every shipped module: what a structure that turns it off joins, or that it cannot.

The table is the audit of ``.claude/docs/equipment.md`` (Bypass): a dict is the bypass, ``{}`` a
module removed with its connections, ``None`` a module that cannot be off.
"""

import pytest

import gemini as gm
from gemini._utils import registry
from gemini.errors import ValidationError
from gemini.plants._utils import superstructure
from gemini.plants._utils.serialization import tree_params
from gemini.plants.plant import Plant
from tests.fixtures.errors import raises

FLUID = {"fluid_in": "fluid_out"}
CHILLER = {
    "generator_in": "generator_out",
    "chilled_in": "chilled_out",
    "cooling_in": "cooling_out",
}
BYPASS = {
    "BoreholeField": FLUID,
    "DownholeHeatExchanger": FLUID,
    "InjectionReservoir": None,
    "ProductionReservoir": None,
    "ThermalDecline": FLUID,
    "InjectionWell": None,
    "ProductionWell": None,
    "CentrifugalPump": FLUID,
    "CirculationPump": FLUID,
    "ESP": FLUID,
    "GasCompressor": FLUID,
    "InjectionPump": FLUID,
    "LineShaftPump": FLUID,
    "Blowdown": FLUID,
    "Degasser": {"fluid_in": "liquid_out"},
    "Desander": FLUID,
    "Filter": FLUID,
    "Flare": {},
    "InhibitorDosing": FLUID,
    "Cooler": FLUID | {"air_in": "air_out"},
    "HeatExchanger": {"hot_in": "hot_out", "cold_in": "cold_out"},
    "Boiler": FLUID,
    "CHP": FLUID,
    "ElectricBoiler": FLUID,
    "HeatPump": {"source_in": "source_out", "sink_in": "sink_out"},
    "AbsorptionUnit": CHILLER,
    "AdsorptionChiller": CHILLER,
    "FlashTurbine": FLUID,
    "ORC": FLUID,
    "Separator": {"fluid_in": "liquid_out"},
    "AquiferStorage": None,
    "IceStorage": FLUID,
    "ThermalStorage": {"charge_in": "charge_out", "discharge_in": "discharge_out"},
    "GasMakeup": {"gas_in": "excess_out"},
    "Mixer": None,
    "Pipe": FLUID,
    "PressurizationTank": FLUID,
    "Splitter": None,
    "Valve": FLUID,
    "ChemicalGrid": {},
    "CoolingGrid": {},
    "ElectricityGrid": {},
    "GasGrid": {},
    "HeatingGrid": {},
    "WasteGrid": {},
    "Atmosphere": {"air_in": "air_out"},
    "Formation": None,
    "PIDController": None,
}


def leaves():
    """Return the names of the registered module classes that are not plants."""
    return [
        name
        for name in registry.names()
        if name not in registry.names("plants") and not issubclass(registry.get(name), Plant)
    ]


def test_every_shipped_module_is_in_the_audit():
    """A new module class states whether it may be off, and how."""
    assert sorted(leaves()) == sorted(BYPASS)


@pytest.mark.parametrize("name", sorted(BYPASS))
def test_the_bypass_of_a_module_is_the_audited_one(name):
    """The bypass a structure uses, or ``invalid_design`` that says how to declare one."""
    module = registry.get(name)()
    expected = BYPASS[name]
    if expected is None:
        with raises(ValidationError, "invalid_design", match="set_bypass"):
            superstructure.pairs(module, name)
    else:
        assert superstructure.pairs(module, name) == expected


def test_a_declared_bypass_is_a_class_attribute_only():
    """``bypass`` is no parameter, so it is not in a module's values or its file."""
    plant = gm.Plant()
    plant.add("GasGrid", "gas")
    assert "bypass" not in tree_params(plant.gas) and "bypass" not in str(plant.to_dict())
