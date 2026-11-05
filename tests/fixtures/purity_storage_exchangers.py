"""Purity cases of the storage, exchanger and environment classes: see ``tests.fixtures.purity``."""

from gemini.streams.flows import Stream
from gemini.streams.fluid import AIR, BRINE, GLYCOL_30, Fluid
from gemini.streams.ports import Ports
from gemini.units import Quantity

AMBIENT = Stream._si(m_dot=0.0, T=290.0, p=101325.0, fluid=AIR)
WATER_IN = Stream(
    fluid=BRINE, m_dot=Quantity(2.0, "kg/s"), T=Quantity(340.0, "K"), p=Quantity(3e5, "Pa")
)
WATER_COLD = WATER_IN._with_si(T=300.0)
AQUIFER_STATE = {
    "warm_volume": 1e4,
    "warm_temperature_change": 4.0,
    "cold_volume": 2e4,
    "cold_temperature_change": -3.0,
    "charged_heat": 1e9,
    "recovered_heat": 1e8,
}


def formation_case():
    """Return a formation and a call with the heat of two wells."""
    from gemini.modules.environment import Formation

    def run(module):
        module(heat_in=[1e3, 2e3])
        module.forward({}, Ports({"heat_in": [1e3, 2e3]}), {})

    return Formation(), run


def atmosphere_case():
    """Return the air with a wet bulb, and a call with a flue gas released into it."""
    from gemini.modules.environment import Atmosphere
    from tests.fixtures import si

    air = Atmosphere().set_params("", {"pressure": Quantity(101325, "Pa")})
    si.assign(air, "temperature", 288.15)
    si.assign(air, "wet_bulb_temperature", 280.0)
    flue = Stream(
        m_dot=Quantity(0.2, "kg/s"),
        T=Quantity(330.0, "K"),
        p=Quantity(1e5, "Pa"),
        fluid=Fluid(kind="gas", gas_composition={"CO2": 1}),
    )
    inputs = {"temperature": 288.15, "wet_bulb_temperature": 280.0}

    def run(module):
        module(gas_in=[flue])
        module.forward(inputs, Ports({"gas_in": [flue]}), {})
        module._offered()
        module._offer(inputs, Ports({}), {})

    return air, run


def cooler_case(loop):
    """Return a wet cooler, on a closed loop or not, and a call that cools a stream."""
    from gemini.modules.exchangers import Cooler
    from tests.fixtures import si

    design = dict(cooler_type="wet", capacity=2e6, approach=5, specific_fan_power=0.02)
    if loop:
        design["loop_pressure"] = 3e5
    cooler = si.set_params(Cooler(), "", design)
    cooler.temperature_setpoint = Quantity(300.0, "K")
    cooler.flow = Quantity(2.0, "kg/s")
    inputs = {"temperature_setpoint": 300.0, "flow": 2.0}
    ports = Ports({"fluid_in": WATER_IN, "air_in": AMBIENT})

    def run(module):
        module(fluid_in=WATER_IN, air_in=AMBIENT)
        module.forward(inputs, ports, {})
        if loop:
            module._offer(inputs, ports, {})

    return cooler, run


def exchanger_case():
    """Return a heat exchanger and a call with a hot and a cold stream."""
    from gemini.modules.exchangers import HeatExchanger
    from tests.fixtures import si

    exchanger = si.set_params(
        HeatExchanger(),
        "",
        dict(
            thermal_conductance=5e4,
            arrangement="counterflow",
            hot_nominal_pressure_drop=5e4,
            cold_nominal_pressure_drop=5e4,
            hot_nominal_mass_flow=2.0,
            cold_nominal_mass_flow=2.0,
        ),
    )
    ports = Ports({"hot_in": WATER_IN, "cold_in": WATER_COLD})

    def run(module):
        module(hot_in=WATER_IN, cold_in=WATER_COLD)
        module.forward({}, ports, {})

    return exchanger, run


def thermal_storage_case():
    """Return a hot tank and a call, a forward, an update and a step from a tank state."""
    from gemini.modules.storage import ThermalStorage
    from tests.fixtures import si
    from tests.fixtures.designs import with_values

    tank = si.set_params(
        with_values(ThermalStorage()),
        "",
        dict(
            service="hot",
            volume=2.0,
            heat_loss_conductance=10.0,
            reference_temperature=313.15,
            charge_effectiveness=0.8,
            discharge_effectiveness=0.9,
        ),
    )
    state = {"temperature": 320.0}
    ports = Ports({"charge_in": WATER_IN, "discharge_in": WATER_COLD, "air_in": AMBIENT})

    def run(module):
        module(charge_in=WATER_IN, discharge_in=WATER_COLD, air_in=AMBIENT, state=state)
        module.forward({}, ports, state)
        module.update({}, ports, {}, state, 600)
        module.step(state, 600, ports)

    return tank, run


def ice_storage_case():
    """Return an ice store and a call, a forward, an update and a step from a state."""
    from gemini.modules.storage import IceStorage
    from tests.fixtures import si

    store = si.set_params(IceStorage(), "", dict(water_mass=1000.0, thermal_conductance=2000.0))
    glycol = Stream(
        fluid=GLYCOL_30, m_dot=Quantity(2.0, "kg/s"), T=Quantity(268.15, "K"), p=Quantity(3e5, "Pa")
    )
    state = {"ice_fraction": 0.4, "temperature": 273.15}
    ports = Ports({"fluid_in": glycol})

    def run(module):
        module(fluid_in=glycol, state=state)
        module.forward({}, ports, state)
        module.update({}, ports, {}, state, 3600)
        module.step(state, 3600, ports)

    return store, run


def aquifer_storage_case():
    """Return a well pair that charges and a call, a forward, an update, an offer and a step."""
    from gemini.modules.storage import AquiferStorage
    from tests.fixtures import si
    from tests.fixtures.designs import with_values

    pair = si.set_params(
        with_values(AquiferStorage()),
        "",
        dict(
            aquifer_temperature=284.15,
            aquifer_thickness=30.0,
            porosity=0.3,
            rock_volumetric_heat_capacity=2.0e6,
            ground_conductivity=2.5,
            storage_period=182.625 * 86400.0,
            groundwater_pressure=3e5,
        ),
    )
    si.assign(pair, "mode", "charge")
    si.assign(pair, "groundwater_flow", 30.0)
    injection = WATER_IN._with_si(T=291.15, m_dot=30.0)
    ports = Ports({"injection_in": injection})
    inputs = {"mode": "charge", "groundwater_flow": 30.0}

    def run(module):
        module(injection_in=injection, state=AQUIFER_STATE)
        module.forward(inputs, ports, AQUIFER_STATE)
        module.update(inputs, ports, {}, AQUIFER_STATE, 3600)
        module._offer(inputs, ports, AQUIFER_STATE)
        module.step(AQUIFER_STATE, 3600, ports)

    return pair, run


CASES = {
    "Formation": formation_case,
    "Atmosphere": atmosphere_case,
    "Cooler": lambda: cooler_case(True),
    "HeatExchanger": exchanger_case,
    "ThermalStorage": thermal_storage_case,
    "IceStorage": ice_storage_case,
    "AquiferStorage": aquifer_storage_case,
}
"""``{class name: function giving (module, run)}`` of storage, exchangers and environment."""
