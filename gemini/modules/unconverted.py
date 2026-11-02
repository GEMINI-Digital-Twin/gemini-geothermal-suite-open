"""TEMPORARY: the old module contract, kept only until every module class is converted.

The old contract is ``forward(self, inlets)``: outputs assigned on ``self``, controls, boundaries
and states read from ``self``, states advanced by ``_advance_states(inlets, outlets, dt)`` and
started from their defaults. A class is unconverted when its ``forward`` has that signature. Each
class converted to ``forward(self, inputs, inlets, state)`` leaves ``OLD_STYLE_MUST_BECOME_EMPTY``,
and a test refuses a name in it that is converted and a class that is old but not in it. The last
conversion deletes this file, every call into it and the test.
"""

import inspect
from collections.abc import Mapping

from gemini._utils.mappings import get_nested
from gemini._utils.strings import join_names
from gemini.errors import ValidationError
from gemini.modules.declarations import UNSET

OLD_STYLE_MUST_BECOME_EMPTY = frozenset(
    {
        "AbsorptionUnit",
        "AdsorptionChiller",
        "AquiferStorage",
        "Atmosphere",
        "Blowdown",
        "Boiler",
        "BoreholeField",
        "CHP",
        "CentrifugalPump",
        "ChemicalGrid",
        "CirculationPump",
        "Cooler",
        "CoolingGrid",
        "Degasser",
        "Desander",
        "DownholeHeatExchanger",
        "ElectricBoiler",
        "ElectricityGrid",
        "Filter",
        "Flare",
        "FlashTurbine",
        "Formation",
        "GasCompressor",
        "GasGrid",
        "GasMakeup",
        "HeatExchanger",
        "HeatPump",
        "HeatingGrid",
        "IceStorage",
        "InhibitorDosing",
        "InjectionPump",
        "InjectionReservoir",
        "InjectionWell",
        "LineShaftPump",
        "Mixer",
        "ORC",
        "Pipe",
        "PressurizationTank",
        "ProductionReservoir",
        "ProductionWell",
        "Separator",
        "Splitter",
        "ThermalDecline",
        "ThermalStorage",
        "Valve",
        "WasteGrid",
    }
)
"""The names of the module classes whose ``forward`` still has the old signature."""

UNCONVERTED_SIGNATURE = ("self", "inlets")


def detect(cls):
    """Return whether ``cls`` still has the old ``forward(self, inlets)``."""
    return tuple(inspect.signature(cls.forward).parameters) == UNCONVERTED_SIGNATURE


def initial_states(module):
    """Return the validated initial value of every state of an unconverted module."""
    return {name: _initial_state(module, name, state) for name, state in module._states.items()}


def _initial_state(module, name, state):
    """Return the default of one state, else the value of its parameter ``initial_<name>``."""
    if state.default is not UNSET:
        return state.default_value()
    return state.validate(module._parameter_value(f"initial_{name}"))


def advance(module, inlets, outlets, dt):
    """Return the end-of-step states of an unconverted module from its ``_advance_states``."""
    values = module._advance_states(inlets, outlets, dt)
    if not isinstance(values, Mapping) or values.keys() != module._states.keys():
        raise ValidationError(
            f"{module.path}: _advance_states returned {sorted(values or ())}; expected "
            f"{join_names(module._states)}",
            code="invalid_design",
        )
    return values


def inherited_state(module, parent):
    """Return the state a child gets from an unconverted composite that did not pass it, or None.

    The composite's ``forward(self, inlets)`` cannot pass a state, so the child reads its entry of
    the state tree of the enclosing call, at its path below that composite.
    """
    if parent is None or not parent.module._unconverted or not parent.state:
        return None
    return get_nested(parent.state, tuple(module._relative_path(parent.module).split(".")))
