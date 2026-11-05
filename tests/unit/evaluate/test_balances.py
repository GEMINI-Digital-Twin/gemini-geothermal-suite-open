"""The ledgers of a finished run and the audits of one call."""

import math

import numpy as np
import pytest

import gemini as gm
from gemini._utils.jsonable import to_plain
from gemini.evaluate.balances import (
    call_emissions,
    call_energy_balance,
    call_mass_balance,
    collect_flows,
)
from gemini.modules import Module, Pipe, Port
from gemini.modules.grids import GasGrid
from gemini.modules.heating import CHP, Boiler, ElectricBoiler
from gemini.modules.pumps import ESP, InjectionPump
from gemini.modules.results import ModuleResult, Values
from gemini.runtime import settings
from gemini.streams.energy import Energy
from gemini.streams.flows import Stream
from gemini.streams.fluid import BRINE, Fluid
from gemini.streams.kinds import Direction, Flow, Level, Phase
from gemini.streams.ports import Ports
from gemini.units import Quantity
from tests.fixtures import si
from tests.fixtures.air import air
from tests.fixtures.balance import assert_plant_closes
from tests.fixtures.costed_plants import heating_plant
from tests.fixtures.designs import with_values
from tests.fixtures.equivalence import STREAM_FIELDS, assert_close
from tests.fixtures.esp_design import ESP_MODULE
from tests.fixtures.parity import BACKENDS
from tests.fixtures.reading import reading
from tests.fixtures.result_tables import make_results

PLANT = heating_plant()


ENERGY = {"power_in": [10.0, 5.0], "fuel": [1.0, 0.5], "heat_accumulation": [-3.0, 2.0]}


def test_energy_ledger_passes_and_reports_the_smallest_power():
    """Signed storage is not judged; the smallest of the other columns is 0.5 W."""
    result = gm.evaluate.energy_balance(PLANT, None, make_results({"leaf": ENERGY}))
    assert to_plain(result) == {
        "name": "energy_balance",
        "passed": True,
        "value": {"value": 0.5, "unit": "W"},
        "limit": {"value": 1e-9, "unit": "W"},
    }


def test_a_negative_nonnegative_output_fails():
    """A fuel power of -2 W breaks the sign convention."""
    result = gm.evaluate.energy_balance(PLANT, None, make_results({"leaf": {"fuel": [1.0, -2.0]}}))
    assert result["passed"] is False and result["value"].value == -2.0


def test_noise_below_the_tolerance_and_missing_values_are_accepted():
    """-1e-12 W is zero; a NaN tick is a skipped row, not a violation."""
    noisy = make_results({"leaf": {"fuel": [-1e-12, math.nan, 4.0]}})
    assert gm.evaluate.energy_balance(PLANT, None, noisy)["passed"] is True


def test_an_infinite_power_fails():
    """A divergent value is a failure even though it is not negative."""
    result = gm.evaluate.energy_balance(
        PLANT, None, make_results({"leaf": {"fuel": [1.0, math.inf]}})
    )
    assert result["passed"] is False


def test_nothing_to_judge_is_undecided_with_a_reason():
    """No energy column, or only missing values, gives ``passed`` None."""
    other = gm.evaluate.energy_balance(PLANT, None, make_results({"leaf": {"head": [1.0]}}))
    assert other["passed"] is None
    assert other["value"].reason == "results have no energy output column"
    empty = gm.evaluate.energy_balance(PLANT, None, make_results({"leaf": {"fuel": [math.nan]}}))
    assert empty["passed"] is None and empty["value"].reason == "every value is missing"


def test_the_example_plant_run_passes_the_energy_ledger(fresh_plant, fast_dataset):
    """A six-hour replay of the doublet heat plant has non-negative powers."""
    replay = gm.replay(fresh_plant, fast_dataset.window(None, "2024-07-01T06:00:00Z"))
    assert gm.evaluate.energy_balance(fresh_plant, None, replay)["passed"] is True


def test_mass_ledger_reads_the_columns_in_kg_per_second():
    """Only outputs whose unit is kg/s count; the other column is ignored."""
    columns = {"degasser": {"gas_mass_flow": [0.2, 0.0], "pressure_drop": [-5.0, -5.0]}}
    units = {"degasser": {"gas_mass_flow": "kg/s", "pressure_drop": "Pa"}}
    result = gm.evaluate.mass_balance(PLANT, None, make_results(columns, units=units))
    assert to_plain(result) == {
        "name": "mass_balance",
        "passed": True,
        "value": {"value": 0.0, "unit": "kg/s"},
        "limit": {"value": 1e-12, "unit": "kg/s"},
    }
    negative = make_results({"degasser": {"gas_mass_flow": [-0.1]}}, units=units)
    assert gm.evaluate.mass_balance(PLANT, None, negative)["passed"] is False


def test_mass_ledger_without_a_mass_flow_is_undecided():
    """No output in kg/s: nothing to judge."""
    result = gm.evaluate.mass_balance(PLANT, None, make_results({"leaf": {"head": [1.0]}}))
    assert result["passed"] is None
    assert result["value"].reason == "results have no output in kg/s"


def test_the_example_plant_run_passes_the_mass_ledger(fresh_plant, fast_dataset):
    """A six-hour replay of the doublet heat plant has non-negative mass flows."""
    replay = gm.replay(fresh_plant, fast_dataset.window(None, "2024-07-01T06:00:00Z"))
    assert gm.evaluate.mass_balance(fresh_plant, None, replay)["passed"] is True


HOT = Stream(
    fluid=BRINE,
    m_dot=gm.units.Quantity(2.0, "kg/s"),
    T=gm.units.Quantity(350.0, "K"),
    p=gm.units.Quantity(4e5, "Pa"),
)


class Leak(Module):
    """Lose a tenth of the stream without saying so."""

    def __init__(self):
        """Declare the ports."""
        super().__init__()

        # Inlets
        self.fluid_in = Port(
            Direction.IN, fluid=Fluid.ANY, phase=Phase.ANY, level=Level.ANY, flow=Flow.IMPOSED
        )

        # Outlets
        self.fluid_out = Port(
            Direction.OUT, fluid=Fluid.ANY, phase=Phase.ANY, level=Level.ANY, flow=Flow.IMPOSED
        )

    def forward(self, inputs, inlets, state):
        """Pass nine tenths of the flow."""
        outputs = dict()
        outlets = dict(fluid_out=inlets.fluid_in._with_si(m_dot=0.9 * inlets.fluid_in.m_dot))
        return outputs, outlets


class Line(Module):
    """One child between the two ports of the root."""

    def __init__(self, child):
        """Declare the child and the ports."""
        super().__init__()

        # Modules
        self.child = child

        # Inlets
        self.fluid_in = Port(
            Direction.IN, fluid=Fluid.ANY, phase=Phase.ANY, level=Level.ANY, flow=Flow.IMPOSED
        )

        # Outlets
        self.fluid_out = Port(
            Direction.OUT, fluid=Fluid.ANY, phase=Phase.ANY, level=Level.ANY, flow=Flow.IMPOSED
        )

    def forward(self, inputs, inlets, state):
        """Pass the stream through the child."""
        passed = self.child(fluid_in=inlets.fluid_in)
        outputs = dict()
        outlets = dict(fluid_out=passed.outlets.fluid_out)
        return outputs, outlets


def by_name(checks):
    """Return the checks by name."""
    return {check["name"]: check for check in checks}


def test_a_leak_fails_its_module_and_the_plant():
    """A tenth of the mass and of the enthalpy goes nowhere."""
    plant = Line(Leak())
    found = by_name(gm.evaluate.plant_balance(plant, None, plant(fluid_in=HOT)))
    assert list(found) == ["child mass", "child energy", "plant mass", "plant energy"]
    assert found["child mass"]["passed"] is False
    assert found["child mass"]["value"].value == pytest.approx(0.1)
    assert found["child energy"]["passed"] is False
    assert found["plant mass"]["value"].value == pytest.approx(0.1)
    assert to_plain(found["plant mass"]["limit"]) == {"value": 1e-6, "unit": "-"}


def test_a_loss_that_reaches_no_edge_module_fails_the_plant_only():
    """The pipe closes through ``loss_out``; the root sees heat that reaches no edge module."""

    class Lost(Line):
        def forward(self, inputs, inlets, state):
            passed = self.child(fluid_in=inlets.fluid_in, air_in=air(283.15))
            outlets = dict(fluid_out=passed.outlets.fluid_out)
            return dict(), outlets

    pipe = with_values(Pipe()).set_params(
        "",
        {
            "length": gm.units.Quantity(500, "m"),
            "inner_diameter": gm.units.Quantity(0.1, "m"),
            "elevation_change": gm.units.Quantity(0, "m"),
            "heat_transfer_coefficient": gm.units.Quantity(5.0, "W/m2/K"),
        },
    )
    plant = Lost(pipe)
    found = by_name(gm.evaluate.plant_balance(plant, None, plant(fluid_in=HOT)))
    assert found["child energy"]["passed"] is True
    assert found["plant mass"]["passed"] is True
    assert found["plant energy"]["passed"] is False


def test_a_closed_line_passes():
    """A stream that leaves as it came closes at the module and at the root."""

    class Same(Leak):
        def forward(self, inputs, inlets, state):
            outlets = dict(fluid_out=inlets.fluid_in)
            return dict(), outlets

    plant = Line(Same())
    assert len(assert_plant_closes(plant, plant(fluid_in=HOT))) == 4


@pytest.mark.parametrize("backend", BACKENDS)
def test_a_finished_run_is_checked_under_any_backend(backend):
    """The columns of a run are arrays: a backend of scalars checks them the same."""
    plant = Line(Leak())
    run = plant(fluid_in=HOT)
    expected = gm.evaluate.plant_balance(plant, None, run)
    with settings(backend=backend):
        assert gm.evaluate.plant_balance(plant, None, run) == expected


GRID_GAS = with_values(GasGrid())._offered()["gas_out"]


class Radiator(Module):
    """Give the stream's heat to the surroundings."""

    def __init__(self):
        """Declare the ports."""
        super().__init__()

        # Inlets
        self.supply_in = Port(
            Direction.IN, fluid=Fluid.ANY, phase=Phase.ANY, level=Level.ANY, flow=Flow.IMPOSED
        )

        # Outlets
        self.return_out = Port(
            Direction.OUT, fluid=Fluid.ANY, phase=Phase.ANY, level=Level.ANY, flow=Flow.IMPOSED
        )
        self.loss_out = Port(Direction.OUT, energy=Energy.HEAT, flow=Flow.IMPOSED)

    def forward(self, inputs, inlets, state):
        """Cool the stream by 10 K."""

        # Outlets
        return_out = inlets.supply_in._with_si(T=inlets.supply_in.T - 10)

        loss_out = inlets.supply_in.m_dot * 4217.4 * 10

        outputs = dict()
        outlets = dict(return_out=return_out, loss_out=loss_out)
        return outputs, outlets


def boiler_of(fuel):
    """Return a boiler of ``fuel`` and the extra inlets a call of it takes."""
    if fuel == "electric":
        return (
            ElectricBoiler().set_params("", {"capacity": Quantity(1e6, "W"), "efficiency": 0.9}),
            {},
        )
    return Boiler().set_params("", {"capacity": Quantity(1e6, "W"), "efficiency": 0.9}), {
        "fuel_in": GRID_GAS
    }


@pytest.mark.parametrize("fuel", ["electric", "gas"])
def test_boiler_balance(fuel):
    """Electric and gas boilers conserve total modeled energy."""
    boiler, gas = boiler_of(fuel)
    result = boiler(
        fluid_in=Stream(
            fluid=BRINE, m_dot=Quantity(10, "kg/s"), T=Quantity(300, "K"), p=Quantity(1e6, "Pa")
        ),
        temperature_setpoint=320,
        **gas,
    )
    assert call_mass_balance(boiler, result)["residual"] == 0
    assert call_energy_balance(boiler, result)["relative_residual"] < 1e-12
    assert collect_flows(result)["electricity" if fuel == "electric" else "fuel"] > 0


def test_unresolved_pump_work():
    """Isothermal pump electricity remains explicit unresolved work."""
    pump = InjectionPump().set_params("", {"pump_type": "unspecified", "efficiency": 0.8})
    result = pump(
        fluid_in=Stream(
            fluid=BRINE, m_dot=Quantity(10, "kg/s"), T=Quantity(300, "K"), p=Quantity(1e6, "Pa")
        ),
        pressure_setpoint=2e6,
        frequency=60,
    )
    balance = call_energy_balance(pump, result)
    assert balance["unresolved_power"] == pytest.approx(result.outputs.power)
    assert balance["relative_thermal_residual"] < 1e-12


def test_esp_motor_efficiency_does_not_change_shaft_power():
    """Motor efficiency changes grid draw while shaft prediction stays fixed."""
    pump = si.set_params(
        ESP(),
        "",
        ESP_MODULE
        | {
            "stage_count": 10,
            "head_coefficients": [10, 0, 0, 0, 0, 0],
            "power_coefficients": [1, 0, 0, 0, 0, 0],
        },
    )
    inlet = Stream(
        fluid=BRINE, m_dot=Quantity(30, "kg/s"), T=Quantity(300, "K"), p=Quantity(1e6, "Pa")
    )
    first = pump(frequency=60, fluid_in=inlet)
    pump.motor_efficiency = 0.5
    second = pump(frequency=60, fluid_in=inlet)
    assert second.outputs.power == first.outputs.power
    assert reading(second).electricity == 2 * first.outputs.power


def test_heat_leaving_through_a_port_closes_the_balance():
    """Heat that leaves through a port is an energy outflow, not a residual."""
    radiator = Radiator()
    result = radiator(
        supply_in=Stream(
            fluid=BRINE, m_dot=Quantity(2, "kg/s"), T=Quantity(350, "K"), p=Quantity(1e6, "Pa")
        )
    )
    balance = call_energy_balance(radiator, result)
    assert balance["heat_loss"] == pytest.approx(2 * 4217.4 * 10)
    assert balance["relative_residual"] < 1e-12


GAS_FACTOR = 56.6 / 1e9


"""Natural-gas CO2 factor [kg/J] of the upstream GEMINI doublet example: 56.6 kg/GJ."""


GRID_FACTOR = 0.3 / 3.6e6


"""Grid-electricity CO2 factor [kg/J] of the upstream GEMINI doublet example: 0.3 kg/kWh."""


class GasHeatedInjection(Module):
    """Heat a return stream with a CHP and a boiler, then pump it into an injector."""

    def __init__(self):
        """Declare the three leaves and the plant ports."""
        super().__init__()

        # Modules
        self.chp = CHP().set_params(
            "",
            {
                "electric_capacity": Quantity(1e5, "W"),
                "electric_efficiency": 0.4,
                "thermal_efficiency": 0.45,
                "maximum_outlet_temperature": Quantity(363.15, "K"),
            },
        )
        self.boiler = Boiler().set_params("", {"capacity": Quantity(1e6, "W"), "efficiency": 0.9})
        self.pump = InjectionPump().set_params("", {"pump_type": "unspecified", "efficiency": 0.8})

        # Inlets
        self.return_in = Port(
            Direction.IN, fluid=Fluid.ANY, phase=Phase.ANY, level=Level.ANY, flow=Flow.IMPOSED
        )

        # Outlets
        self.injected = Port(
            Direction.OUT, fluid=Fluid.ANY, phase=Phase.ANY, level=Level.ANY, flow=Flow.IMPOSED
        )

    def forward(self, inputs, inlets, state):
        """Pass the stream through CHP, boiler and pump in flow order."""

        # Modules
        heated = self.chp(fluid_in=inlets.return_in, fuel_in=GRID_GAS).outlets.fluid_out
        topped = self.boiler(fluid_in=heated, fuel_in=GRID_GAS).outlets.fluid_out
        pumped = self.pump(fluid_in=topped, frequency=60)

        # Outlets
        injected = pumped.outlets.fluid_out

        outputs = dict()
        outlets = dict(injected=injected)
        return outputs, outlets


@pytest.mark.parametrize("load", [0.2, 1.0])
def test_emissions_charge_fuel_and_net_grid_electricity(load):
    """Fuel is charged in full; CHP electricity offsets the 60 kW pump before the grid."""
    plant = GasHeatedInjection()
    plant._set_inputs(
        {
            "chp.load_fraction": load,
            "boiler.temperature_setpoint": 343.15,
            "pump.pressure_setpoint": 50e5,
        }
    )
    result = plant(
        return_in=Stream(
            fluid=BRINE, m_dot=Quantity(10, "kg/s"), T=Quantity(313.15, "K"), p=Quantity(2e5, "Pa")
        )
    )
    flows = collect_flows(result)
    pump_power = 10 / 1000 * 48e5 / 0.8
    assert flows["electricity"] == pytest.approx(pump_power)
    assert flows["electricity_generated"] == pytest.approx(load * 1e5)
    grid = {0.2: pump_power - 2e4, 1.0: 0.0}[load]
    expected = flows["fuel"] * GAS_FACTOR + grid * GRID_FACTOR
    assert call_emissions(result, GAS_FACTOR, GRID_FACTOR) == pytest.approx(expected, rel=1e-12)


def test_emissions_without_energy_outputs_are_zero():
    """A leaf that burns and draws nothing emits nothing."""
    result = Boiler().set_params("", {"capacity": Quantity(1e6, "W"), "efficiency": 0.9})(
        fluid_in=Stream(
            fluid=BRINE, m_dot=Quantity(10, "kg/s"), T=Quantity(350, "K"), p=Quantity(2e5, "Pa")
        ),
        fuel_in=GRID_GAS,
        temperature_setpoint=340,
    )
    assert call_emissions(result, GAS_FACTOR, GRID_FACTOR) == 0


def _stack_streams(streams):
    if not isinstance(streams[0], Stream):
        return np.array(streams)
    return Stream._si(
        **{field: np.array([getattr(s, field) for s in streams]) for field in STREAM_FIELDS},
        fluid=streams[0].fluid,
    )


def _stack_results(results):
    """Return one result whose outputs and streams are arrays over the rows of ``results``."""
    first = results[0]
    return ModuleResult(
        outputs=Values(
            {name: np.array([r.outputs[name] for r in results]) for name in first.outputs}
        ),
        inlets=Ports({n: _stack_streams([r.inlets[n] for r in results]) for n in first.inlets}),
        outlets=Ports({n: _stack_streams([r.outlets[n] for r in results]) for n in first.outlets}),
        inputs={name: np.array([r.inputs[name] for r in results]) for name in first.inputs},
    )


def _assert_balances_match(module, results, expected_keys):
    stacked = _stack_results(results)
    for audit in (call_mass_balance, call_energy_balance):
        per_row = [audit(module, result) for result in results]
        together = audit(module, stacked)
        for key in expected_keys[audit]:
            assert_close(together[key], [row[key] for row in per_row], f"{audit.__name__}.{key}")
    flows = [collect_flows(result) for result in results]
    for key, values in collect_flows(stacked).items():
        assert_close(values, [row[key] for row in flows], key)
    per_row = [call_emissions(result, 0.2, 0.4) for result in results]
    assert_close(call_emissions(stacked, 0.2, 0.4), per_row, "emissions")


BALANCE_KEYS = {
    call_mass_balance: ("in", "out", "residual", "relative_residual"),
    call_energy_balance: (
        "in",
        "out",
        "residual",
        "relative_residual",
        "thermal_residual",
        "losses",
    ),
}


@pytest.mark.parametrize("fuel", ["electric", "gas"])
def test_balances_match_on_stacked_boiler_results(fuel):
    """Audits and emissions on array-valued results equal the audits per row."""
    boiler, gas = boiler_of(fuel)
    results = [
        boiler(
            fluid_in=Stream(
                fluid=BRINE,
                m_dot=Quantity(m_dot, "kg/s"),
                T=Quantity(300, "K"),
                p=Quantity(1e6, "Pa"),
            ),
            temperature_setpoint=setpoint,
            **gas,
        )
        for m_dot, setpoint in [(10, 320), (2, 310), (0.5, 300)]
    ]
    _assert_balances_match(boiler, results, BALANCE_KEYS)


def test_balances_match_on_stacked_radiator_results():
    """Heat on a port, with a residual of either sign, audits per row."""
    radiator = Radiator()
    results = [
        radiator(
            supply_in=Stream(
                fluid=BRINE,
                m_dot=Quantity(m_dot, "kg/s"),
                T=Quantity(350, "K"),
                p=Quantity(3e5, "Pa"),
            )
        )
        for m_dot in (0.0, 1.5, 12.0)
    ]
    _assert_balances_match(radiator, results, BALANCE_KEYS)
