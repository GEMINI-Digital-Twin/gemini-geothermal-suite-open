"""Purity cases of the pumps, power and piping classes: a module ready to run and what runs it."""

from gemini.streams.flows import Stream
from gemini.streams.fluid import BRINE, STEAM, WATER, Fluid
from gemini.streams.ports import Ports
from gemini.units import Quantity


def stream(fluid=BRINE, m_dot=10.0, T=330.0, p=5e5):
    """Return a stream of SI numbers."""
    return Stream(
        fluid=fluid, m_dot=Quantity(m_dot, "kg/s"), T=Quantity(T, "K"), p=Quantity(p, "Pa")
    )


def ready(module, inlets, inputs=None):
    """Return the module and a ``run`` that calls it and its ``forward`` on ``inlets``."""
    inputs = inputs or {}

    def run(called):
        called(**inlets, **inputs)
        called.forward(inputs, Ports(inlets), {})

    return module, run


def design(cls, values):
    """Return an instance of ``cls`` with the design ``values`` (SI numbers) set."""
    from tests.fixtures import si
    from tests.fixtures.designs import with_values

    return si.set_params(with_values(cls()), "", values)


def centrifugal_pump_case():
    """Return a centrifugal pump at its rated frequency."""
    from gemini.modules.pumps import CentrifugalPump

    pump = design(
        CentrifugalPump,
        dict(
            head_coefficients=[6e5, 0, -4e7],
            rated_frequency=50,
            best_efficiency=0.8,
            best_efficiency_flow=0.05,
            motor_efficiency=0.95,
        ),
    )
    return ready(pump, dict(fluid_in=stream(m_dot=50.0)), dict(frequency=50.0))


def circulation_pump_case():
    """Return a circulation pump of 4 kg/s on a circuit held at 3 bar."""
    from gemini.modules.pumps import CirculationPump

    pump = design(CirculationPump, dict(flow=4.0, pressure_rise=5e4, loop_pressure=3e5))
    return ready(pump, dict(fluid_in=stream(m_dot=1.0, p=1e5)))


def gas_compressor_case():
    """Return a two-stage air-like compressor."""
    from gemini.modules.pumps import GasCompressor

    compressor = design(
        GasCompressor,
        dict(
            isentropic_efficiency=0.8,
            heat_capacity_ratio=1.4,
            gas_specific_heat=1005,
            motor_efficiency=0.95,
            stage_count=2,
        ),
    )
    inlets = dict(fluid_in=stream(m_dot=0.2, T=300.0, p=1e5))
    return ready(compressor, inlets, dict(pressure_setpoint=8e5))


def injection_pump_case():
    """Return an injection pump that follows a pressure setpoint."""
    from gemini.modules.pumps import InjectionPump

    pump = design(InjectionPump, dict(pump_type="unspecified", efficiency=0.65))
    inputs = dict(pressure_setpoint=2e6, frequency=60.0)
    return ready(pump, dict(fluid_in=stream(m_dot=1.0, T=300.0, p=1e6)), inputs)


def line_shaft_pump_case():
    """Return a 12-stage line-shaft pump."""
    from gemini.modules.pumps import LineShaftPump

    curves = dict(
        stage_count=12,
        head_coefficients=[83.08389282, -0.000460444, -1.19e-07, 1.69e-11, -6.36e-16, 6.69e-21],
        power_coefficients=[10.02089977, -0.000160233, 6.52e-08, -2.13e-12, 1.71e-17, 1.38e-23],
    )
    pump = design(
        LineShaftPump, dict(curves, setting_depth=300, shaft_friction_loss=5, motor_efficiency=0.9)
    )
    return ready(pump, dict(fluid_in=stream(m_dot=40.0, T=340.0, p=1e6)), dict(frequency=55.0))


def flash_turbine_case():
    """Return a turbine on dry steam."""
    from gemini.modules.power import FlashTurbine

    turbine = design(FlashTurbine, dict(condenser_pressure=1e4, generator_efficiency=0.98))
    return ready(turbine, dict(fluid_in=stream(STEAM, 20.0, 431.98, 6e5)))


def orc_case():
    """Return an air-cooled ORC on a hot brine."""
    from gemini.modules.power import ORC
    from tests.fixtures.air import air

    plant = design(
        ORC,
        dict(
            minimum_brine_outlet_temperature=343.15,
            pinch=5,
            carnot_fraction=0.5,
            condenser_approach=15,
            parasitic_fraction=0.15,
            capacity=5e6,
        ),
    )
    return ready(plant, dict(fluid_in=stream(m_dot=100.0, T=423.15, p=10e5), air_in=air(288.15)))


def separator_case():
    """Return a separator flashing a hot liquid to 6 bar."""
    from gemini.modules.power import Separator

    inlets = dict(fluid_in=stream(m_dot=100.0, T=523.15, p=40e5))
    return ready(Separator(), inlets, dict(pressure_setpoint=6e5))


def gas_makeup_case():
    """Return a makeup whose burner takes more than the co-produced gas."""
    from gemini.modules import GasGrid, GasMakeup
    from tests.fixtures.designs import with_values

    fluid = Fluid(kind="gas", gas_composition={"CH4": 0.8, "CO2": 0.2})
    gas = stream(fluid, 0.05, 330.0, 2e5)
    grid = with_values(GasGrid())._offered()["gas_out"]
    inlets = dict(gas_in=gas, grid_in=grid, fuel_out=gas._with_si(m_dot=0.08))
    return ready(GasMakeup(), inlets)


def mixer_case():
    """Return a mixer of two branches."""
    from gemini.modules.piping import Mixer

    inlets = dict(branch1_in=stream(m_dot=6.0, T=363.15), branch2_in=stream(m_dot=2.0, p=4e5))
    return ready(Mixer(), inlets)


def pipe_case():
    """Return a pipe rising 5 m."""
    from gemini.modules.piping import Pipe
    from tests.fixtures.air import air

    pipe = design(
        Pipe,
        dict(length=1000, inner_diameter=0.1, elevation_change=5, heat_transfer_coefficient=1.0),
    )
    return ready(pipe, dict(fluid_in=stream(T=353.15), air_in=air(283.15)))


def pressurization_tank_case():
    """Return a vessel holding a circuit at 3 bar."""
    from gemini.modules.piping import PressurizationTank

    return ready(PressurizationTank(), dict(fluid_in=stream(p=1.2e5)), dict(pressure_setpoint=3e5))


def splitter_case():
    """Return a splitter sending a quarter to the second branch."""
    from gemini.modules.piping import Splitter

    return ready(Splitter(), dict(fluid_in=stream(WATER, 10.0, 353.15)), dict(split_fraction=0.25))


def valve_case():
    """Return a half-open valve."""
    from gemini.modules.piping import Valve

    valve = design(Valve, dict(flow_coefficient=100 / 3600 / 1e5**0.5))
    return ready(valve, dict(fluid_in=stream(m_dot=10.0, T=353.15, p=20e5)), dict(opening=0.5))


FLOW_CASES = {
    "CentrifugalPump": centrifugal_pump_case,
    "CirculationPump": circulation_pump_case,
    "FlashTurbine": flash_turbine_case,
    "GasCompressor": gas_compressor_case,
    "GasMakeup": gas_makeup_case,
    "InjectionPump": injection_pump_case,
    "LineShaftPump": line_shaft_pump_case,
    "Mixer": mixer_case,
    "ORC": orc_case,
    "Pipe": pipe_case,
    "PressurizationTank": pressurization_tank_case,
    "Separator": separator_case,
    "Splitter": splitter_case,
    "Valve": valve_case,
}
"""``{class name: function giving (module, run)}`` for the converted pumps, power and piping."""
