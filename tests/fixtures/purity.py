"""The purity guard: running ``forward`` or ``update`` leaves a module and its children unchanged.

``snapshot`` freezes everything in the ``__dict__`` of a module and of every child: plain values by
value, arrays by bytes, declarations (parameter values included) by their own attributes, any other
object by identity. ``unchanged`` runs a block and fails naming the module and the attribute that a
block wrote, replaced or added.
"""

import dataclasses
from collections.abc import Mapping
from contextlib import contextmanager

import numpy as np

from gemini.modules.declarations import Declaration
from gemini.modules.module import Module
from gemini.streams.fluid import BRINE
from tests.fixtures import purity_storage_exchangers
from tests.fixtures.purity_flow import FLOW_CASES
from tests.fixtures.purity_thermal import CASES as THERMAL_CASES

PLAIN = (int, float, complex, str, bool, bytes, type(None))
SKIPPED = ("_parent",)


def frozen(value, seen=()):
    """Return ``value`` as something that compares equal when nothing was written to it."""
    if id(value) in seen:
        return ("cycle", id(value))
    seen = (*seen, id(value))
    if isinstance(value, PLAIN):
        return value
    if isinstance(value, Module):
        return ("module", id(value))
    if isinstance(value, np.ndarray):
        return ("array", value.dtype.str, value.shape, value.tobytes())
    if isinstance(value, Mapping):
        return ("map", tuple((key, frozen(item, seen)) for key, item in value.items()))
    if isinstance(value, (list, tuple)):
        return (type(value).__name__, tuple(frozen(item, seen) for item in value))
    if isinstance(value, (set, frozenset)):
        return ("set", frozenset(frozen(item, seen) for item in value))
    if isinstance(value, Declaration) or (
        dataclasses.is_dataclass(value) and not isinstance(value, type)
    ):
        return (type(value).__name__, id(value), frozen(vars(value), seen))
    return ("object", type(value).__name__, id(value))


def snapshot(module):
    """Return the frozen attributes of ``module`` and of every module below it, by path."""
    return {
        path: {name: frozen(value) for name, value in vars(member).items() if name not in SKIPPED}
        for path, member in module.named_modules()
    }


def changes(before, after):
    """Return ``path.attribute`` of every attribute that differs between two snapshots."""
    found = []
    for path in before.keys() | after.keys():
        old, new = before.get(path, {}), after.get(path, {})
        found += [
            f"{path or 'root'}.{name}"
            for name in old.keys() | new.keys()
            if old.get(name) != new.get(name)
        ]
    return sorted(found)


@contextmanager
def unchanged(module):
    """Fail, naming what changed, when the block writes to ``module`` or to a child."""
    before = snapshot(module)
    yield
    written = changes(before, snapshot(module))
    assert not written, f"{type(module).__name__}: a call wrote {written}"


PID_TUNING = dict(
    proportional_gain=2.0,
    integral_time=100.0,
    derivative_time=10.0,
    minimum_output=0.0,
    maximum_output=1.0,
    direction="reverse",
)
FRESH_PID = {"integral": 0.0, "previous_error": 0.0, "previous_step": 0.0}


def esp_case():
    """Return a pump set to run, and what a run of it calls."""
    from gemini.modules.pumps import ESP
    from gemini.streams.flows import Stream
    from gemini.streams.ports import Ports
    from gemini.units import Quantity
    from tests.fixtures import si
    from tests.fixtures.esp_design import ESP_PARAMS

    pump = si.set_params(ESP(), "", ESP_PARAMS)
    pump.frequency = Quantity(50, "Hz")
    suction = Stream(
        fluid=BRINE, m_dot=Quantity(30, "kg/s"), T=Quantity(300, "K"), p=Quantity(5e6, "Pa")
    )

    def run(module):
        module(fluid_in=suction)
        module.forward({"frequency": 50.0}, Ports({"fluid_in": suction}), {})

    return pump, run


def pid_case():
    """Return a controller set to run, and what a run of it calls: forward, update and a step."""
    from gemini.modules.control import PIDController
    from tests.fixtures import si

    pid = si.set_params(PIDController(), "", PID_TUNING)
    pid.setpoint, pid.measurement = 1.0, 0.8
    inputs = {"setpoint": 1.0, "measurement": 0.8}

    def run(module):
        module(state=FRESH_PID)
        module.forward(inputs, {}, FRESH_PID)
        module.update(inputs, {}, {}, FRESH_PID, 60)
        module.step(FRESH_PID, 60, {})

    return pid, run


def stream_in(mass_flow=30.0, temperature=330.0, pressure=5e6):
    """Return a brine stream, the inlet of the cases below."""
    from gemini.streams.flows import Stream
    from gemini.units import Quantity

    return Stream(
        fluid=BRINE,
        m_dot=Quantity(mass_flow, "kg/s"),
        T=Quantity(temperature, "K"),
        p=Quantity(pressure, "Pa"),
    )


def stateless_run(module, inputs, inlets):
    """Return ``(module, run)``: a call and a direct ``forward`` of a module without states."""
    from gemini.streams.ports import Ports

    def run(module):
        module(**inlets)
        module.forward(inputs, Ports(inlets), {})

    return module, run


def stateful_run(module, inputs, inlets, state, dt=60.0):
    """Return ``(module, run)``: a call, ``forward``, ``update`` and a step of a stateful module."""
    from gemini.streams.ports import Ports

    ports = Ports(inlets)

    def run(module):
        module(**inlets, state=state)
        module.forward(inputs, ports, state)
        module.update(inputs, ports, {}, state, dt)
        module.step(state, dt, inlets)

    return module, run


FIELD = dict(
    borehole_count=10,
    borehole_depth=150.0,
    borehole_radius=0.075,
    borehole_spacing=6.0,
    borehole_resistance=0.1,
    ground_conductivity=2.0,
    ground_volumetric_heat_capacity=2.2e6,
    undisturbed_ground_temperature=283.15,
)
DECLINE = dict(
    well_spacing=1000.0, aquifer_thickness=50.0, porosity=0.2, rock_volumetric_heat_capacity=2.5e6
)
DOWNHOLE = dict(
    borehole_depth=2500.0,
    surface_temperature=283.15,
    geothermal_gradient=0.03,
    ground_conductivity=2.5,
    ground_diffusivity=1e-6,
    borehole_radius=0.1,
    borehole_resistance=0.05,
    operating_time=3.15e7,
)
AQUIFER = dict(
    pressure=250e5,
    temperature=353.15,
    permeability=1e-12,
    aquifer_thickness=100.0,
    drainage_radius=1000.0,
    top_depth=2400.0,
    wellbore_radius=0.1,
    skin=2.0,
    decline_threshold=0.15,
)
WELL_PATH = dict(
    section_length=[600.0, 400.0],
    section_inclination=[1.5, 1.2],
    section_diameter=[0.2, 0.15],
    section_roughness=[4.5e-5, 4.5e-5],
    friction_correlation="darcy_weisbach",
    two_phase_friction_correlation="BeggsBrill",
    correction_factors=(1.0, 0.0),
    soil_temperature=288.15,
    heat_transfer_coefficient=10.0,
)


def borehole_field_case():
    """Return a borehole field set to run, and what a run of it calls."""
    from gemini.modules.subsurface import BoreholeField
    from tests.fixtures import si

    field = si.set_params(BoreholeField(), "", FIELD)
    state = {"ground_temperature_change": 0.0}
    return stateful_run(field, {}, {"fluid_in": stream_in(3.0, 273.15, 3e5)}, state)


def thermal_decline_case():
    """Return a thermal decline set to run, and what a run of it calls."""
    from gemini.modules.subsurface import ThermalDecline
    from tests.fixtures import si

    decline = si.set_params(ThermalDecline(), "", DECLINE)
    si.assign(decline, "injection_temperature", 313.15)
    inputs = {"injection_temperature": 313.15}
    state = {"injected_volume": 0.0}
    return stateful_run(decline, inputs, {"fluid_in": stream_in(50.0, 353.15, 2e7)}, state)


def downhole_heat_exchanger_case():
    """Return a downhole heat exchanger set to run, and what a run of it calls."""
    from gemini.modules.subsurface import DownholeHeatExchanger
    from tests.fixtures import si

    exchanger = si.set_params(DownholeHeatExchanger(), "", DOWNHOLE)
    return stateless_run(exchanger, {}, {"fluid_in": stream_in(5.0, 303.15, 3e5)})


def production_reservoir_case():
    """Return a production reservoir set to run, and what a run of it calls."""
    from gemini.modules.subsurface import ProductionReservoir
    from tests.fixtures import si
    from tests.fixtures.designs import with_values

    reservoir = si.set_params(
        with_values(ProductionReservoir()), "", AQUIFER | {"productivity_index": 10 / 3.6e8}
    )
    si.assign(reservoir, "production_rate", 40.0)
    return stateless_run(reservoir, {"production_rate": 40.0}, {})


def injection_reservoir_case():
    """Return an injection reservoir set to run, and what a run of it calls."""
    from gemini.modules.subsurface import InjectionReservoir
    from tests.fixtures import si
    from tests.fixtures.designs import with_values

    reservoir = si.set_params(
        with_values(InjectionReservoir()), "", AQUIFER | {"injectivity_index": 10 / 3.6e8}
    )
    return stateless_run(reservoir, {}, {"sandface_in": stream_in(-40.0, 300.0, 23e6)})


def production_well_case():
    """Return a production well set to run, and what a run of it calls."""
    from gemini.modules.wells import ProductionWell
    from tests.fixtures import si

    well = si.set_params(ProductionWell(), "", WELL_PATH | {"segment": "full"})
    return stateless_run(well, {}, {"bottom_in": stream_in(40.0, 353.15, 25e6)})


def injection_well_case():
    """Return an injection well set to run, and what a run of it calls."""
    from gemini.modules.wells import InjectionWell
    from tests.fixtures import si

    well = si.set_params(InjectionWell(), "", WELL_PATH)
    return stateless_run(well, {}, {"wellhead_in": stream_in(40.0, 300.0, 5e6)})


CASES = {
    "ESP": esp_case,
    "PIDController": pid_case,
    **FLOW_CASES,
    **THERMAL_CASES,
    "BoreholeField": borehole_field_case,
    "ThermalDecline": thermal_decline_case,
    "DownholeHeatExchanger": downhole_heat_exchanger_case,
    "ProductionReservoir": production_reservoir_case,
    "InjectionReservoir": injection_reservoir_case,
    "ProductionWell": production_well_case,
    "InjectionWell": injection_well_case,
}
"""``{class name: function giving (module, run)}`` for every converted class, by the converter.

``run`` calls ``module`` and its ``forward`` (and ``update``) directly; the module is made ready
to run, its plan built, before it is returned, because building comes before a call.
"""
CASES |= purity_storage_exchangers.CASES
