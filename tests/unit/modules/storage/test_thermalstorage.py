"""Fully mixed storage tank: duties, exact lumped solution, balances and limits."""

import math

import numpy as np
import pytest

import gemini as gm
from gemini import ops
from gemini.evaluate import call_energy_balance, call_mass_balance
from gemini.modules import ElectricBoiler, Module, Port
from gemini.modules.storage import ThermalStorage
from gemini.streams.flows import Stream
from gemini.streams.fluid import AIR, BRINE, Fluid
from gemini.streams.kinds import Direction, Flow, Level, Phase
from gemini.streams.ports import Ports
from tests.fixtures import si
from tests.fixtures.air import air
from tests.fixtures.designs import with_values
from tests.fixtures.equivalence import assert_close
from tests.fixtures.errors import raises
from tests.fixtures.reading import reading

CP = 4217.4
"""Default fluid heat capacity [J/kg/K]."""

CAPACITY = 1000 * CP * 2.0
"""Heat capacity [J/K] of the 2 m3 test tank of default fluid (1000 kg/m3)."""

CHARGE = Stream(
    fluid=BRINE,
    m_dot=gm.units.Quantity(1.0, "kg/s"),
    T=gm.units.Quantity(353.15, "K"),
    p=gm.units.Quantity(3e5, "Pa"),
)
DISCHARGE = Stream(
    fluid=BRINE,
    m_dot=gm.units.Quantity(0.5, "kg/s"),
    T=gm.units.Quantity(313.15, "K"),
    p=gm.units.Quantity(3e5, "Pa"),
)


START = {"temperature": 293.15}
"""A tank at 20 degC: a call states the tank temperature, a state has no default."""


def _tank(service="hot", **changes):
    """Return a configured 2 m3 tank with UA = 10 W/K."""
    params = dict(
        service=service, volume=2.0, heat_loss_conductance=10.0, reference_temperature=313.15
    )
    return si.set_params(with_values(ThermalStorage()), "", params | changes)


def _inlets(charge=CHARGE, discharge=DISCHARGE, ambient=293.15):
    return {"charge_in": charge, "discharge_in": discharge, "air_in": air(ambient)}


def test_a_call_from_a_state_uses_its_temperature():
    """A tank at 20 degC: direct circuits leave at it."""
    result = _tank()(charge_in=CHARGE, discharge_in=DISCHARGE, air_in=air(293.15), state=START)
    assert result.outlets.charge_out.T == result.outlets.discharge_out.T == 293.15
    assert result.outputs.tank_temperature == 293.15
    assert reading(result).heat_loss == 0 and reading(result).heat_absorbed == 0
    assert result.outlets.charge_out.m_dot == CHARGE.m_dot
    assert result.outlets.charge_out.p == CHARGE.p


def test_hot_tank_step_matches_the_exact_solution_and_audits():
    """A hot tank step reports start-of-step duties and advances with exp(-b dt / C)."""
    tank = _tank()
    state, result = tank.step({"temperature": 343.15}, 600, _inlets())
    out = reading(result)
    assert result.outlets.charge_out.T == result.outlets.discharge_out.T == 343.15
    assert out.charge_duty == pytest.approx(1.0 * CP * 10)
    assert out.discharge_duty == pytest.approx(0.5 * CP * 30)
    assert out.heat_loss == pytest.approx(10 * 50) and out.heat_absorbed == 0
    assert out.stored_energy == pytest.approx(CAPACITY * 30)
    assert out.heat_accumulation == pytest.approx(CP * 10 - 0.5 * CP * 30 - 500)
    b = 1.0 * CP + 0.5 * CP + 10
    equilibrium = (1.0 * CP * 353.15 + 0.5 * CP * 313.15 + 10 * 293.15) / b
    expected = equilibrium + (343.15 - equilibrium) * math.exp(-b * 600 / CAPACITY)
    assert state["temperature"] == pytest.approx(expected, rel=1e-14)
    audit = call_energy_balance(tank, result)
    assert audit["relative_residual"] < 1e-12
    assert call_mass_balance(tank, result)["residual"] == 0
    state, result = tank.step(state, 600, _inlets())
    assert result.outputs.tank_temperature == pytest.approx(expected, rel=1e-14)


def test_exact_solution_composes_and_reaches_equilibrium():
    """Two half steps equal one full step, and a very long step reaches the equilibrium."""
    tank = _tank()
    half, _ = tank.step({"temperature": 300.0}, 900, _inlets())
    half, _ = tank.step(half, 900, _inlets())
    full, _ = tank.step({"temperature": 300.0}, 1800, _inlets())
    assert half["temperature"] == pytest.approx(full["temperature"], rel=1e-13)
    final, _ = tank.step({"temperature": 300.0}, 1e8, _inlets())
    b = 1.5 * CP + 10
    equilibrium = (1.0 * CP * 353.15 + 0.5 * CP * 313.15 + 10 * 293.15) / b
    assert final["temperature"] == pytest.approx(equilibrium, rel=1e-14)


def test_heat_exchanger_effectiveness_sets_the_circuit_outlets():
    """An indirect circuit leaves at T_in - e (T_in - T) and transfers e m cp (T_in - T)."""
    tank = _tank(charge_effectiveness=0.6, discharge_effectiveness=0.8)
    result = tank(charge_in=CHARGE, discharge_in=DISCHARGE, air_in=air(293.15), state=START)
    assert result.outlets.charge_out.T == pytest.approx(353.15 - 0.6 * 60)
    assert result.outlets.discharge_out.T == pytest.approx(313.15 - 0.8 * 20)
    assert reading(result).charge_duty == pytest.approx(0.6 * CP * 60)
    audit = call_energy_balance(tank, result)
    assert audit["relative_residual"] < 1e-12


def test_chilled_tank_in_a_warm_room_absorbs_heat():
    """A chilled tank reports stored cold, positive service duties and heat_absorbed."""
    tank = _tank("chilled", reference_temperature=285.15)
    charge = Stream(
        fluid=BRINE,
        m_dot=gm.units.Quantity(2.0, "kg/s"),
        T=gm.units.Quantity(277.15, "K"),
        p=gm.units.Quantity(3e5, "Pa"),
    )
    discharge = Stream(
        fluid=BRINE,
        m_dot=gm.units.Quantity(1.0, "kg/s"),
        T=gm.units.Quantity(285.15, "K"),
        p=gm.units.Quantity(3e5, "Pa"),
    )
    state, result = tank.step({"temperature": 279.15}, 300, _inlets(charge, discharge, 298.15))
    out = reading(result)
    assert out.stored_energy == pytest.approx(CAPACITY * 6)
    assert out.charge_duty == pytest.approx(2.0 * CP * 2)
    assert out.discharge_duty == pytest.approx(1.0 * CP * 6)
    assert out.heat_loss == 0 and out.heat_absorbed == pytest.approx(10 * 19)
    assert out.heat_accumulation == pytest.approx(-2.0 * CP * 2 + 1.0 * CP * 6 + 190)
    audit = call_energy_balance(tank, result)
    assert audit["relative_residual"] < 1e-12
    assert state["temperature"] > 279.15


def test_stopped_circuits_leave_only_ambient_cooling():
    """Zero flows keep inlet temperatures and the tank cools by Newton's law exactly."""
    tank = _tank()
    stopped = _inlets(CHARGE._with_si(m_dot=0), DISCHARGE._with_si(m_dot=0))
    state, result = tank.step({"temperature": 353.15}, 3600, stopped)
    assert result.outlets.charge_out.T == CHARGE.T
    assert reading(result).charge_duty == 0 and reading(result).discharge_duty == 0
    expected = 293.15 + 60 * math.exp(-10 * 3600 / CAPACITY)
    assert state["temperature"] == pytest.approx(expected, rel=1e-14)
    insulated = _tank(heat_loss_conductance=0)
    assert insulated.step({"temperature": 353.15}, 3600, stopped)[0] == {"temperature": 353.15}


def test_invalid_inputs_raise():
    """Reverse flow is outside the model; missing air is a wrong call."""
    tank = _tank()
    with pytest.raises(gm.errors.PhysicsError, match="thermal_storage: circuit m_dot = -1"):
        tank(
            charge_in=CHARGE._with_si(m_dot=-1),
            discharge_in=DISCHARGE,
            air_in=air(290),
            state=START,
        )
    with raises(gm.errors.ValidationError, "invalid_call"):
        tank(charge_in=CHARGE, discharge_in=DISCHARGE, state=START)
    with raises(gm.errors.ValidationError, "missing_value"):
        tank(charge_in=CHARGE, discharge_in=DISCHARGE, air_in=air(290))
    with pytest.raises(gm.errors.ValidationError):
        tank.set_params("", {"charge_effectiveness": 1.2})


class BoilerCharging(Module):
    """Boiler heating the charge circuit of a storage tank."""

    def __init__(self):
        """Declare the test composite."""
        super().__init__()

        # Modules
        self.boiler = ElectricBoiler().set_params(
            "", {"capacity": gm.units.Quantity(2e5, "W"), "efficiency": 0.9}
        )
        self.storage = _tank()

        # Inlets
        self.charge_in = Port(
            Direction.IN, fluid=Fluid.ANY, phase=Phase.ANY, level=Level.ANY, flow=Flow.IMPOSED
        )
        self.discharge_in = Port(
            Direction.IN, fluid=Fluid.ANY, phase=Phase.ANY, level=Level.ANY, flow=Flow.IMPOSED
        )
        self.air_in = Port(
            Direction.IN, phase=Phase.GAS, fluid=Fluid.AIR, level=Level.AMBIENT, flow=Flow.IMPOSED
        )

        # Outlets
        self.charge_out = Port(
            Direction.OUT, fluid=Fluid.ANY, phase=Phase.ANY, level=Level.ANY, flow=Flow.IMPOSED
        )
        self.discharge_out = Port(
            Direction.OUT, fluid=Fluid.ANY, phase=Phase.ANY, level=Level.ANY, flow=Flow.IMPOSED
        )

    def forward(self, inputs, inlets, state):
        """Heat the charge water, then pass both circuits through the tank."""

        # Modules
        heated = self.boiler(fluid_in=inlets.charge_in)
        stored = self.storage(
            charge_in=heated.outlets.fluid_out,
            discharge_in=inlets.discharge_in,
            air_in=inlets.air_in,
            state=state["storage"],
        )

        # Outlets
        charge_out = stored.outlets.charge_out
        discharge_out = stored.outlets.discharge_out

        outputs = dict()
        outlets = dict(charge_out=charge_out, discharge_out=discharge_out)
        return outputs, outlets


def test_composite_step_charges_the_tank():
    """A composite steps the tank through its forward; the audit residual is the accumulation."""
    plant = BoilerCharging()
    si.assign(plant.boiler, "temperature_setpoint", 363.15)
    cold = Stream(
        fluid=BRINE,
        m_dot=gm.units.Quantity(0.5, "kg/s"),
        T=gm.units.Quantity(313.15, "K"),
        p=gm.units.Quantity(3e5, "Pa"),
    )
    state, _ = plant.step({"storage": START}, 900, _inlets(cold, DISCHARGE))
    state, result = plant.step(state, 900, _inlets(cold, DISCHARGE))
    storage = reading(result.children["storage"])
    assert state["storage"]["temperature"] > storage.tank_temperature > 293.15
    assert reading(result.children["boiler"]).electricity > 0
    audit = call_energy_balance(plant, result)
    assert audit["relative_residual"] < 1e-12
    assert call_mass_balance(plant, result)["residual"] == 0


def _rows():
    return [
        dict(
            charge_in=Stream(
                fluid=BRINE,
                m_dot=gm.units.Quantity(charge, "kg/s"),
                T=gm.units.Quantity(353.15, "K"),
                p=gm.units.Quantity(3e5, "Pa"),
            ),
            discharge_in=Stream(
                fluid=BRINE,
                m_dot=gm.units.Quantity(discharge, "kg/s"),
                T=gm.units.Quantity(313.15, "K"),
                p=gm.units.Quantity(3e5, "Pa"),
            ),
            air_in=air(ambient),
        )
        for charge, discharge, ambient in [(1.0, 0.5, 293.15), (0, 0.5, 303.15), (0, 0, 273.15)]
    ]


def _stacked(rows):
    """Return the inlets of ``rows`` as streams of arrays."""
    return {
        name: Stream._si(
            **{f: np.array([getattr(row[name], f) for row in rows]) for f in ("m_dot", "T", "p")},
            fluid=rows[0][name].fluid,
        )
        for name in ("charge_in", "discharge_in")
    }


def _ports(charge, discharge, ambient):
    """Return the inlets of a tank as the settled ports the pure methods take."""
    return Ports(
        {
            "charge_in": charge._numpy(),
            "discharge_in": discharge._numpy(),
            "air_in": Stream._si(m_dot=0.0, T=ambient, p=101325.0, fluid=AIR),
        }
    )


TEMPERATURES = [343.15, 303.15, 283.15]


@pytest.mark.parametrize("service", ["hot", "chilled"])
def test_thermal_storage_forward_matches_per_row(service):
    """Duties, outlets and the audit outputs on stacked rows and temperatures equal per row."""
    tank = _tank(service, charge_effectiveness=0.8)
    rows = _rows()

    def forward(temperature, charge, discharge, ambient):
        with ops.scope.Scope():
            state = {"temperature": ops.scope.wrap(temperature)}
            outputs, outlets = tank.forward({}, _ports(charge, discharge, ambient), state)
        return outputs, outlets

    expected = [
        forward(t, row["charge_in"], row["discharge_in"], row["air_in"].T)
        for t, row in zip(TEMPERATURES, rows)
    ]
    stacked = _stacked(rows)
    ambient = np.array([row["air_in"].T for row in rows])
    outputs, outlets = forward(np.array(TEMPERATURES), *stacked.values(), ambient)
    for name in outputs:
        assert_close(outputs[name], [e[0][name] for e in expected], name)
    for name in ("charge_out", "discharge_out"):
        assert_close(outlets[name].T, [e[1][name].T for e in expected], name)
    assert_close(outlets["loss_out"], [e[1]["loss_out"] for e in expected], "loss_out")


def test_thermal_storage_update_matches_per_row():
    """The exact exponential step on stacked temperatures equals one update per row."""
    tank = _tank(heat_loss_conductance=0.0)
    rows = _rows()

    def advance(temperature, charge, discharge, ambient):
        with ops.scope.Scope():
            state = {"temperature": ops.scope.wrap(temperature)}
            inlets = _ports(charge, discharge, ambient)
            return tank.update({}, inlets, {}, state, 600)["temperature"]

    expected = [
        advance(t, row["charge_in"], row["discharge_in"], row["air_in"].T)
        for t, row in zip(TEMPERATURES, rows)
    ]
    stacked = _stacked(rows)
    ambient = np.array([row["air_in"].T for row in rows])
    actual = advance(np.array(TEMPERATURES), *stacked.values(), ambient)
    assert_close(actual, expected, "temperature")
    assert expected[2] == 283.15


def _json_stream(fluid, flow, temperature, pressure):
    return {
        "fluid": fluid._to_dict(),
        "m_dot": {"value": flow, "unit": "kg/s"},
        "T": {"value": temperature, "unit": "degC"},
        "p": {"value": pressure, "unit": "bar"},
    }


def test_gm_call_takes_the_tank_fluid_from_the_inlet_stream():
    """A tank called from JSON with ``state`` and ``dt`` and no stated fluid works on its stream."""
    result = gm.call(
        "ThermalStorage",
        parameters={
            "service": "hot",
            "volume": {"value": 2, "unit": "m3"},
            "heat_loss_conductance": {"value": 10, "unit": "W/K"},
            "reference_temperature": {"value": 40, "unit": "degC"},
            "charge_effectiveness": 1.0,
            "discharge_effectiveness": 1.0,
        },
        inlets={
            "charge_in": _json_stream(BRINE, 1.0, 80, 3),
            "discharge_in": _json_stream(BRINE, 0.5, 40, 3),
            "air_in": _json_stream(AIR, 0.0, 20, 1.01325),
        },
        controls={},
        units="si",
        state={"temperature": gm.units.Quantity(20, "degC")},
        dt=gm.units.Quantity(10, "min"),
    )
    expected = _tank().step({"temperature": 293.15}, 600, _inlets())[0]["temperature"]
    assert result["state"]["temperature"]["value"] == pytest.approx(expected, rel=1e-9)


def test_the_energy_capacity_is_the_size_of_a_cost_per_energy():
    """``cost_size_of("energy")`` is ``energy_capacity``; unset, it is missing and named."""
    tank = _tank()
    assert tank.cost_size() == 2.0 and tank.cost_size_of("power") is None
    with raises(gm.errors.ValidationError, "missing_value", match="energy_capacity"):
        tank.cost_size_of("energy")
    assert _tank(energy_capacity=3.6e9).cost_size_of("energy") == 3.6e9
