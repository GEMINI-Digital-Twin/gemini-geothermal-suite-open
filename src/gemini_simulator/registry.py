"""Registry mapping component type names to gemini_model classes.

Maps component type names (as used in project JSON files) to
gemini_model classes.

Keeping this mapping in one place lets project JSON files reference
components by a short, stable type string instead of an import path, and
gives a single place to extend when new gemini_model components are added.
"""

from gemini_model.adder.adder import Adder
from gemini_model.boiler.boiler import Boiler
from gemini_model.booster_pump.booster_pump import BoosterPump
from gemini_model.chp.chp import CHP
from gemini_model.filter.filter import Filter
from gemini_model.fluid.pvt_water_stp import PVTConstantSTP
from gemini_model.heat_exchanger.heat_exchanger import HeatExchanger
from gemini_model.injector_pump.injector_pump import InjectorPump
from gemini_model.mixer.mixer import Mixer
from gemini_model.pump.esp import ESP
from gemini_model.reservoir.inflow_performance import IPR
from gemini_model.reservoir.reservoir_pressuredrop import bottomhole_skin_dp
from gemini_model.separator.separator import Separator
from gemini_model.splitter.splitter import Splitter
from gemini_model.well.pressure_drop import DPDT
from gemini_simulator.well_components import InjectorWell, ProducerWell

COMPONENT_REGISTRY = {
    "adder": Adder,
    "mixer": Mixer,
    "splitter": Splitter,
    "separator": Separator,
    "filter": Filter,
    "heat_exchanger": HeatExchanger,
    "boiler": Boiler,
    "chp": CHP,
    "injector_pump": InjectorPump,
    "booster_pump": BoosterPump,
    "well": DPDT,
    "reservoir_bottomhole_skin": bottomhole_skin_dp,
    "reservoir_ipr": IPR,
    "esp": ESP,
    "producer_well": ProducerWell,
    "injector_well": InjectorWell,
}

# Component types that need extra, non-`parameters` setup after
# instantiation (e.g. DPDT's `.PVT` attribute, which is not part of its
# `update_parameters` dict but is required before `calculate_output` runs).
_POST_INIT_HOOKS = {
    "well": lambda component: setattr(component, "PVT", PVTConstantSTP()),
}


def create_component(component_type):
    """Instantiate a gemini_model component from its registered type name.

    Parameters
    ----------
    component_type: str
        Key into :data:`COMPONENT_REGISTRY`.
    """
    try:
        component_class = COMPONENT_REGISTRY[component_type]
    except KeyError as exc:
        known = ", ".join(sorted(COMPONENT_REGISTRY))
        raise KeyError(f"Unknown component type '{component_type}'. Known types: {known}.") from exc
    component = component_class()
    hook = _POST_INIT_HOOKS.get(component_type)
    if hook is not None:
        hook(component)
    return component
