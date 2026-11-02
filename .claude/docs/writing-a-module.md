# Writing a module

A module is two pure functions of the step it computes. This page writes two of them from nothing,
a pump with no memory (stateless: `forward` only) and a controller with a memory (stateful:
`forward` and `update`), and runs each alone and inside a plant. The reference for every rule is
[modules.md](modules.md); the plant side is [plants.md](plants.md) and the run is
[engine.md](engine.md).

## The contract

```text
forward(self, inputs, inlets, state) -> (outputs, outlets)
update(self, inputs, inlets, outlets, state, dt) -> next state          only a module with states
```

| Argument | What it holds |
| --- | --- |
| `self` | the parameters: set before a run and fixed during it; nothing else |
| `inputs` | the controls and boundaries of this step, by name, in SI (`inputs["frequency"]`) |
| `inlets` | the inlet streams of this step, an immutable `Ports` mapping (`inlets.fluid_in`) |
| `state` | the states at the start of the step, by name (`{}` for a module without states) |
| `outlets` (`update`) | what `forward` returned for the outlets, so `update` does not recompute them |
| `dt` (`update`) | the length of the step in seconds |

The rules, each checked by a test (`tests/unit/test_purity.py` runs a guard on every registered
class, [conventions](conventions.md#module-rules)):

- `forward` and `update` write nothing to `self` and read no control, boundary, state or output from
  it: the error names the module and the value. A value that changes in time arrives as an argument.
- `forward` returns exactly the declared outputs and outlets (and the inlets the module draws): a
  missing or an extra key is a `DefinitionError` naming the module and the key. `update` returns a
  key for each declared state and no more.
- Nothing is `None` inside a step. "No previous step yet" is a value (`previous_step = 0`), an
  output that is empty when the machine is off is NaN, and a feature that is off for the whole run
  is a parameter that is `None`, decided before the run and never by a value that changes per step.
  This is what lets the compiler trace the module.
- Branch on values with `ops.where`, `ops.minimum`, `ops.maximum`, not with `if` on a quantity that
  changes per step; a branch on a parameter is fine because a parameter is fixed.
- A state has no default: the case states where a run starts (`initial_state`).
- A formula is a function of `gemini/physics/`; the module declares and wires
  ([where physics goes](modules.md#writing-modules)). The controller below writes its few lines
  inline to stay on one page; a module of the package calls `gemini.physics`.
- A module never builds a plant. A composite is a `Plant`, which declares children and
  connections and writes neither `forward` nor `update`.

## A stateless module: a pump

A pump has no memory: the stream it gives in a step follows from the stream it takes and its
frequency in that step. `forward` is all there is. The head and power come from the polynomial
curves of the ESP in `gemini.physics.pumps`.

```python
import pandas as pd

import gemini as gm
from gemini import ops
from gemini.modules import Boundary, Control, Inlet, Module, Outlet, Output, Parameter, State
from gemini.physics import pumps
from gemini.plants import Plant
from gemini.streams import Stream
from gemini.units.quantities import (
    Count,
    Dimensionless,
    Duration,
    Frequency,
    Power,
    PressureDifference,
)


class Submersible(Module):
    """A pump that raises the pressure of the stream it takes by a head curve."""

    def __init__(self):
        super().__init__()

        # Parameters
        self.stage_count = Parameter(Count, description="Number of stages")
        self.head_coefficients = Parameter(list[float], shape=(6,), description="Head curve")
        self.power_coefficients = Parameter(list[float], shape=(6,), description="Power curve")

        # Inlets
        self.fluid_in = Inlet(Stream)

        # Controls
        self.frequency = Control(Frequency, description="Frequency of the motor")

        # Outputs
        self.head = Output(PressureDifference, description="Pressure rise")
        self.power = Output(Power, description="Power on the shaft")

        # Outlets
        self.fluid_out = Outlet(Stream)

    def forward(self, inputs, inlets, state):
        """Raise the suction pressure by the head of the curve at this flow and frequency."""
        frequency = inputs["frequency"]

        # Outlets
        suction = inlets.fluid_in
        flow = suction.volumetric_flow()
        head = pumps.head(flow, frequency, self.stage_count, self.head_coefficients)
        discharge = suction._with_si(p=suction.p + head)

        # Outputs
        power = pumps.power(flow, frequency, self.stage_count, self.power_coefficients)
        outputs = dict(head=head, power=power)

        outlets = dict(fluid_out=discharge)
        return outputs, outlets
```

The parameters are the values of the design; `set_params` takes a `Quantity` for a value with a
dimension (a bare number for it raises `invalid_value`). **Alone**, a call gives a `ModuleResult`:
the controls are keywords of the call, the state is empty and nothing is kept on the pump.

```python
DESIGN = dict(
    stage_count=100,
    head_coefficients=[400.0, -0.01, 0.0, 0.0, 0.0, 0.0],
    power_coefficients=[1.0, 0.0, 0.0, 0.0, 0.0, 0.0],
)
suction = gm.Stream(
    flow={"value": 150, "unit": "m3/h"},
    T={"value": 80, "unit": "C"},
    p={"value": 20, "unit": "bar"},
    fluid=gm.BRINE,
)

pump = Submersible().set_params("", DESIGN)
alone = pump(fluid_in=suction, frequency={"value": 50, "unit": "Hz"})
assert alone.outlets.fluid_out.p == suction.p + alone.outputs.head
assert alone.inputs["frequency"] == 50
```

**Inside a plant**, a plant class declares the pump as a child, its own ports and the connections,
and nothing else. Its `forward` is the plant's, written once: it hands each child its inlets, its
inputs and its state, and returns the plant's outlets. A control of a child is set on the plant with
`set_inputs`, by its dotted path, or comes from a column of the run named after that path.

```python
class Lift(Plant):
    """A pump between a suction port and a discharge port."""

    def __init__(self):
        super().__init__()

        # Modules
        self.pump = Submersible()

        # Inlets
        self.suction_in = Inlet(Stream)

        # Outlets
        self.discharge_out = Outlet(Stream)

        # Connections
        self.connect("suction_in", "pump.fluid_in")
        self.connect("pump.fluid_out", "discharge_out")


lift = Lift().set_params("pump", DESIGN)
lift.set_inputs({"pump.frequency": {"value": 50, "unit": "Hz"}})
inside = lift(suction_in=suction)
assert inside.outlets.discharge_out.p == alone.outlets.fluid_out.p
assert inside.children["pump"].outputs.head == alone.outputs.head
```

A run is the same call over time. The plan holds one row per step, with a column for each plant
inlet field (`suction_in.m_dot`, `.T`, `.p`) and each control that changes (`pump.frequency`); the
case holds the period. The pump is stateless, so the engine evaluates all the rows at once as
arrays, eager or compiled, with the same numbers.

```python
TIMES = pd.date_range("2024-01-01", periods=4, freq="1h", tz="UTC")
HOURLY = {
    "format": 1,
    "kind": "case",
    "name": "hourly",
    "time": {"start": "2024-01-01", "end": "2024-01-01T03:00:00", "step": {"value": 1, "unit": "h"}},
}
plan = pd.DataFrame(
    {
        "suction_in.m_dot": suction.m_dot,
        "suction_in.T": suction.T,
        "suction_in.p": suction.p,
        "pump.frequency": [45.0, 50.0, 55.0, 60.0],
    },
    index=TIMES,
)
lift.fluid = gm.BRINE
results = gm.simulate(lift, gm.Case.from_dict(HOURLY), plan=gm.Dataset.from_frame(plan))
assert results.errors() == []
assert results.to_frame()["pump.head"].is_monotonic_increasing
```

## A stateful module: a controller

A controller remembers: the command of a step depends on the sum of the errors before it. Its
memory is declared as `State`s, and a second method, `update`, returns them at the end of the step.
`forward` reads the states at the start of the step, so the command of a step uses start-of-step
values only (the integral is one step behind, as in the shipped `PIDController`). The derivative
needs the previous error and the length of the previous step; before the first step there is none,
and that is the value `previous_step = 0`, never `None`.

```python
class Regulator(Module):
    """Proportional, integral and derivative control with limits on the command."""

    def __init__(self):
        super().__init__()

        # Parameters
        self.gain = Parameter(Dimensionless, gt=0, description="Proportional gain")
        self.integral_time = Parameter(Duration, gt=0, description="Integral time")
        self.derivative_time = Parameter(Duration, ge=0, description="Derivative time")
        self.minimum = Parameter(Dimensionless, description="Lowest command")
        self.maximum = Parameter(Dimensionless, description="Highest command")

        # Controls
        self.setpoint = Control(Dimensionless, description="Target of the measurement")

        # Boundaries
        self.measurement = Boundary(Dimensionless, description="Measured value")

        # States
        self.integral = State(Dimensionless, description="Integral term at the start of the step")
        self.previous_error = State(Dimensionless, description="Error of the previous step")
        self.previous_step = State(Duration, ge=0, description="Previous step; 0 when none yet")

        # Outputs
        self.error = Output(Dimensionless, description="Setpoint minus measurement")
        self.command = Output(Dimensionless, description="Command within its limits")

    def forward(self, inputs, inlets, state):
        """Return the command from the states at the start of the step."""
        error = inputs["setpoint"] - inputs["measurement"]
        started = state["previous_step"] > 0
        step = ops.where(started, state["previous_step"], 1.0)
        slope = ops.where(started, (error - state["previous_error"]) / step, 0.0)
        raw = self.gain * (error + self.derivative_time * slope) + state["integral"]
        command = ops.minimum(self.maximum, ops.maximum(self.minimum, raw))

        outputs = dict(error=error, command=command)

        outlets = dict()
        return outputs, outlets

    def update(self, inputs, inlets, outlets, state, dt):
        """Return the states at the end of the step; the old ones are not touched."""
        error = inputs["setpoint"] - inputs["measurement"]
        return {
            "integral": state["integral"] + self.gain * dt / self.integral_time * error,
            "previous_error": error,
            "previous_step": dt,
        }
```

**Alone**, a call needs the state it starts from: `state=` takes the states by name, and a stateful
module called without one raises `missing_value` naming it. `step(state, dt, inlets)` calls the
module and then `update`, and returns the next state with the result. The controls and boundaries
are set on the module first (or passed as keywords of a call).

```python
TUNING = dict(
    gain=2.0,
    integral_time={"value": 100, "unit": "s"},
    derivative_time={"value": 10, "unit": "s"},
    minimum=0.0,
    maximum=10.0,
)
FRESH = {"integral": 0.0, "previous_error": 0.0, "previous_step": 0.0}

controller = Regulator().set_params("", TUNING)
controller.setpoint, controller.measurement = 5.0, 3.0
first = controller(state=FRESH)
assert first.outputs.command == 4.0 and first.state == FRESH

state, result = controller.step(FRESH, 60, {})
assert state == {"integral": 2.4, "previous_error": 2.0, "previous_step": 60.0}
assert result.outputs.command == 4.0

controller.measurement = 4.0
second = controller(state=state)
assert second.outputs.command == 2.0 * (1.0 + 10.0 * (1.0 - 2.0) / 60.0) + 2.4
```

The next state is a new dict: `FRESH` is unchanged and a second call from it gives the same answer.
That is what makes a trial independent of another and lets the study run many trials on one plant.

**Inside a plant**, the plant's state is the nested dict of its children's states, by child name,
and `Plant.update` is written once: it calls each child's `update` with its own entry. The state
comes from the case, which states every state of every stateful module (`gm.check` lists what is
missing). A run **scans** in time: `state[t + 1] = update(..., state[t], dt)` with `forward` in each
step, one call over the whole plan, eager or compiled (a `scan` node of the graph), the same numbers
to 1e-9.

```python
class Loop(Plant):
    """A controller whose measurement comes from the run."""

    def __init__(self):
        super().__init__()

        # Modules
        self.controller = Regulator()


loop = Loop().set_params("controller", TUNING)
loop.set_inputs({"controller.setpoint": 5.0, "controller.measurement": 3.0})
by_hand = loop.step({"controller": FRESH}, 3600, {})[0]
assert by_hand["controller"]["previous_step"] == 3600.0

START = {"value": 0, "unit": "-"}
ZERO = {"value": 0, "unit": "s"}
case = gm.Case.from_dict(
    HOURLY
    | {
        "initial_state": {
            "controller": {"integral": START, "previous_error": START, "previous_step": ZERO}
        }
    }
)
plan = pd.DataFrame(
    {
        "controller.setpoint": 5.0,
        "controller.measurement": [3.0, 3.5, 4.0, 4.5],
    },
    index=TIMES,
)
results = gm.simulate(loop, case, plan=gm.Dataset.from_frame(plan))
assert results.errors() == []
assert list(results.to_frame()["controller.error"]) == [2.0, 1.5, 1.0, 0.5]
final = results.end_state["module_states"][""]["controller"]
assert final["integral"] == 2.0 * 3600 / 100 * (2.0 + 1.5 + 1.0 + 0.5)
```

`results.end_state` holds the state at the end of the run, which a checkpoint and a resumed run
continue from; the first row of `results` started from `case.initial_state`. A step that fails
(a physical failure such as a stream the limits refuse) is a failed row: its values are NaN and the
state is the one before it ([engine.md](engine.md#errors)).

## Checklist for a new module

1. Declarations in `__init__` in the order of the sections: `# Parameters`, `# Inlets`,
   `# Controls`, `# Boundaries`, `# States`, `# Outputs`, `# Outlets`, each with its quantity and a
   description, and no default for anything a user decides.
2. `forward(self, inputs, inlets, state)` ends with `outlets = dict(...)` and
   `return outputs, outlets`; a stateful module adds `update(self, inputs, inlets, outlets, state, dt)`.
3. Controls and boundaries from `inputs`, states from `state`, parameters from `self`, nothing
   assigned; no `None` in a step; `ops` where a value decides.
4. Physics in `gemini/physics/`; reuse a function before writing one.
5. A test beside the class, and an entry in `tests/fixtures/purity.py` so the guard runs it
   ([testing.md](testing.md)). A shipped class also needs its page in [equipment.md](equipment.md)
   and its registration ([modules.md](modules.md#registry-categories-and-streams)).
