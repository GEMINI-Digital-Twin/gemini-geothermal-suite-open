"""Declared states: initial values, leaf and composite steps, and their validation."""

import pandas as pd
import pytest

import gemini as gm
from gemini.modules import Module
from gemini.modules.bindings import Binding, ModuleBindings
from gemini.modules.declarations import Control, Inlet, Outlet, Output, Parameter, State
from gemini.streams.flows import Stream
from gemini.streams.fluid import BRINE
from gemini.units.quantities import Duty, Energy, Temperature
from tests.fixtures.errors import raises
from tests.fixtures.reading import reading

STREAM = Stream(
    fluid=BRINE,
    m_dot=gm.units.Quantity(1, "kg/s"),
    T=gm.units.Quantity(350, "K"),
    p=gm.units.Quantity(1e6, "Pa"),
)


class Tank(Module):
    """Mixed tank whose temperature relaxes towards the inlet temperature."""

    def __init__(self):
        """Declare the test module."""
        super().__init__()

        # Parameters
        self.heat_capacity = Parameter(float, default=4217.4 * 100, gt=0)

        # Inlets
        self.fluid_in = Inlet(Stream)

        # States
        self.temperature = State(Temperature)

        # Outputs
        self.duty = Output(Duty)

        # Outlets
        self.fluid_out = Outlet(Stream)

    def forward(self, inputs, inlets, state):
        """Leave at the tank temperature of the start of the step."""

        # Outlets
        outlet = inlets.fluid_in._with_si(T=state["temperature"])

        outputs = dict(duty=self._duty(inlets.fluid_in, state))
        outlets = dict(fluid_out=outlet)
        return outputs, outlets

    def update(self, inputs, inlets, outlets, state, dt):
        """Relax the temperature towards the inlet."""
        duty = self._duty(inlets.fluid_in, state)
        return {"temperature": state["temperature"] + duty * dt / self.heat_capacity}

    def _duty(self, inlet, state):
        """Return the heat taken from the inlet."""
        return inlet.m_dot * 4217.4 * (inlet.T - state["temperature"])


class Line(Module):
    """Two tanks in series."""

    def __init__(self):
        """Declare the test module."""
        super().__init__()

        # Modules
        self.first = Tank()
        self.second = Tank()

        # Inlets
        self.fluid_in = Inlet(Stream)

        # Outlets
        self.fluid_out = Outlet(Stream)

    def forward(self, inputs, inlets, state):
        """Pass the stream through both tanks."""

        # Modules
        first = self.first(fluid_in=inlets.fluid_in, state=state["first"])
        second = self.second(fluid_in=first.outlets.fluid_out, state=state["second"])

        # Outlets
        outlet = second.outlets.fluid_out

        outputs = dict()
        outlets = dict(fluid_out=outlet)
        return outputs, outlets


class Integrator(Module):
    """Accumulate a commanded rate over time."""

    def __init__(self):
        """Declare the test module."""
        super().__init__()

        # Controls
        self.rate = Control(float)

        # States
        self.total = State(Energy)

        # Outputs
        self.value = Output(Energy)

    def forward(self, inputs, inlets, state):
        """Move no fluid."""
        outputs = dict(value=state["total"])
        outlets = dict()
        return outputs, outlets

    def update(self, inputs, inlets, outlets, state, dt):
        """Add the commanded rate over the step."""
        return {"total": state["total"] + inputs["rate"] * dt}


COLD = {"temperature": 300}
LINE_COLD = {"first": dict(COLD), "second": dict(COLD)}


def test_a_call_evaluates_at_the_given_state():
    """A stateful module evaluates at the state the call passes."""
    tank = Tank()
    assert tank.stateful and not Line().stateful
    assert tank(fluid_in=STREAM, state=COLD).outlets.fluid_out.T == 300
    assert list(Line().states()) == ["first.temperature", "second.temperature"]
    assert "States:\n  temperature: K" in Tank.help()


def test_leaf_step_advances_its_state():
    """A leaf step starts from the given state and returns the end-of-step state."""
    tank = Tank()
    state, result = tank.step(COLD, 10, {"fluid_in": STREAM})
    assert result.outlets.fluid_out.T == 300
    assert state == {"temperature": pytest.approx(300 + 50 * 4217.4 * 10 / (4217.4 * 100))}
    state, result = tank.step(state, 10, {"fluid_in": STREAM})
    assert result.outlets.fluid_out.T == pytest.approx(305)


def test_composite_step_advances_every_descendant():
    """A composite steps its stateful children through its own forward, without a step method."""
    line = Line()
    state, _ = line.step(LINE_COLD, 10, {"fluid_in": STREAM})
    state, result = line.step(state, 10, {"fluid_in": STREAM})
    assert state["first"]["temperature"] > state["second"]["temperature"] > 300
    assert result.outlets.fluid_out.T == 300
    first, second = 350 - 305, 305 - 300
    assert reading(result).duty == pytest.approx(STREAM.m_dot * 4217.4 * (first + second))


def test_state_errors():
    """Unknown states, assignments, wrong returns and double calls fail with the module path."""
    tank = Tank()
    with raises(
        gm.errors.ValidationError, "unknown_name", match="tank: unknown state 'temperatur'"
    ):
        tank.step({"temperatur": 300}, 10, {"fluid_in": STREAM})
    with pytest.raises(gm.errors.DefinitionError, match="changes only in update"):
        tank.temperature = 310
    with pytest.raises(gm.errors.ValidationError, match="tank.temperature: invalid state"):
        tank.step({"temperature": -1}, 10, {"fluid_in": STREAM})
    line = Line()
    line.second = line.first
    with raises(gm.errors.ValidationError, "invalid_design", match="more than once in one step"):
        line.step(LINE_COLD, 10, {"fluid_in": STREAM})


def test_update_must_return_every_state():
    """An incomplete end-of-step mapping is a configuration error."""

    class Leaky(Tank):
        """Tank that forgets its state."""

        def update(self, inputs, inlets, outlets, state, dt):
            """Return no state."""
            return {}

    with pytest.raises(gm.errors.DefinitionError, match="missing key 'temperature'"):
        Leaky().step(COLD, 10, {"fluid_in": STREAM})


def test_engine_replay_integrates_declared_states():
    """The engine steps a declared-state twin and keeps its state between ticks."""
    plant = Integrator()
    plant.bindings = {"": ModuleBindings(controls={"rate": Binding(column="rate", unit="-")})}
    frame = pd.DataFrame(
        {"rate": [1.0, 1.0, 1.0]},
        index=pd.date_range("2024-01-01", periods=3, freq="1s", tz="UTC"),
    )
    engine = gm.Engine(plant, on_error="raise")
    start = {"position": None, "module_states": {"": {"total": 0.0}}}
    results = engine.replay(gm.Dataset.from_frame(frame), state=start)
    assert results[""].value.tolist() == [0, 1, 2]
    assert engine.module_states[""] == {"total": 3}
