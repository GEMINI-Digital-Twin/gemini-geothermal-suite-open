"""A small traceable leaf module shared by the graph tests."""

import numpy as np
import pytest

from gemini import ops
from gemini.errors import PhysicsError
from gemini.modules import Module, Port
from gemini.modules.callrecord import outputs_enabled
from gemini.modules.declarations import Boundary, Control, Output, Parameter, State
from gemini.ops import Constant
from gemini.streams.flows import Stream
from gemini.streams.fluid import BRINE, WATER, Fluid
from gemini.streams.kinds import Direction, Flow, Level, Phase
from gemini.units import Quantity
from gemini.units.quantities import Electricity, Pressure, Ratio, Temperature

REFERENCE = Constant("REFERENCE", 2.0, "Pa", "pressure rise per unit gain and scale")


class Gain(Module):
    """Raise the inlet pressure by ``gain * scale * REFERENCE``; refuse a negative gain."""

    def __init__(self):
        """Declare one numeric and one text parameter, a control and two outputs."""
        super().__init__()
        self.fluid = BRINE

        # Parameters
        self.scale = Parameter(float)
        self.label = Parameter(str, default="x")

        # Inlets
        self.fluid_in = Port(
            Direction.IN, fluid=Fluid.ANY, phase=Phase.ANY, level=Level.ANY, flow=Flow.IMPOSED
        )

        # Controls
        self.gain = Control(float)

        # Outputs
        self.rise = Output(float)
        self.boost = Output(float)

        # Outlets
        self.fluid_out = Port(
            Direction.OUT, fluid=Fluid.ANY, phase=Phase.ANY, level=Level.ANY, flow=Flow.IMPOSED
        )

    def forward(self, inputs, inlets, state):
        """Raise the pressure."""
        gain = inputs["gain"]

        # Outlets
        inlet = inlets.fluid_in
        ops.check(
            gain >= 0,
            PhysicsError,
            "{path}: gain = {gain}",
            path=self.path,
            gain=gain,
        )
        outlet = inlet._with_si(p=inlet.p + gain * self.scale * REFERENCE)

        # Outputs
        rise = outlet.p - inlet.p
        outputs = dict(rise=rise, boost=ops.where(rise > 0, ops.truediv(rise, gain), 0.0))

        outlets = dict(fluid_out=outlet)
        return outputs, outlets


@pytest.fixture
def gain():
    """Return a configured ``Gain`` module."""
    return Gain().set_params("", {"scale": 3.0})


@pytest.fixture
def inlet():
    """Return a three-row inlet state."""
    return Stream(
        m_dot=Quantity(np.array([1.0, 1.0, 1.0]), "kg/s"),
        T=Quantity(np.array([300.0, 310.0, 320.0]), "K"),
        p=Quantity(np.array([1e5, 2e5, 3e5]), "Pa"),
        fluid=BRINE,
    )


class Stepper(Module):
    """Raise the inlet pressure ``steps`` times by one pascal; ``steps`` is structural."""

    def __init__(self):
        """Declare a structural count, a numeric increment, an inlet and an outlet."""
        super().__init__()
        self.fluid = BRINE

        # Parameters
        self.steps = Parameter(int, default=2, structural=True)
        self.increment = Parameter(float, default=1.0)

        # Inlets
        self.fluid_in = Port(
            Direction.IN, fluid=Fluid.ANY, phase=Phase.ANY, level=Level.ANY, flow=Flow.IMPOSED
        )

        # Outlets
        self.fluid_out = Port(
            Direction.OUT, fluid=Fluid.ANY, phase=Phase.ANY, level=Level.ANY, flow=Flow.IMPOSED
        )

    def forward(self, inputs, inlets, state):
        """Add the increment once per step."""

        # Outlets
        pressure = inlets.fluid_in.p
        for _ in range(self.steps):
            pressure = pressure + self.increment
        return {}, dict(fluid_out=inlets.fluid_in._with_si(p=pressure))


@pytest.fixture
def stepper():
    """Return a configured ``Stepper`` module."""
    return Stepper()


class Source(Module):
    """Emit a stream of fixed state whose mass flow is the ``rate`` control; it has no inlet."""

    def __init__(self):
        """Declare a control, an output and an outlet."""
        super().__init__()
        self.fluid = BRINE

        # Controls
        self.rate = Control(float)

        # Outputs
        self.double = Output(float)

        # Outlets
        self.fluid_out = Port(
            Direction.OUT, fluid=Fluid.ANY, phase=Phase.ANY, level=Level.ANY, flow=Flow.IMPOSED
        )

    def forward(self, inputs, inlets, state):
        """Emit the stream."""

        # Outlets
        outlet = Stream(
            m_dot=Quantity(inputs["rate"], "kg/s"),
            T=Quantity(300.0, "K"),
            p=Quantity(1e5, "Pa"),
            fluid=self.fluid,
        )
        outputs = dict(double=2 * outlet.m_dot)
        outlets = dict(fluid_out=outlet)
        return outputs, outlets


@pytest.fixture
def source():
    """Return a ``Source`` module."""
    return Source()


class Meter(Module):
    """Pass the stream on and draw ``draw * scale`` watts; a leaf with an output."""

    def __init__(self):
        """Declare a parameter, a control, an inlet, an output and an outlet."""
        super().__init__()
        self.fluid = BRINE

        # Parameters
        self.scale = Parameter(float, default=2.0)

        # Inlets
        self.fluid_in = Port(
            Direction.IN, fluid=Fluid.ANY, phase=Phase.ANY, level=Level.ANY, flow=Flow.IMPOSED
        )

        # Controls
        self.draw = Control(float, ge=0)

        # Outputs
        self.electricity = Output(Electricity)

        # Outlets
        self.fluid_out = Port(
            Direction.OUT, fluid=Fluid.ANY, phase=Phase.ANY, level=Level.ANY, flow=Flow.IMPOSED
        )

    def forward(self, inputs, inlets, state):
        """Pass the stream."""
        outputs = dict(electricity=inputs["draw"] * self.scale)
        outlets = dict(fluid_out=inlets.fluid_in)
        return outputs, outlets


class Line(Module):
    """A meter, then a gain, then a second meter: a composite with every output formula."""

    def __init__(self):
        """Declare the children, the output formulas and the ports."""
        super().__init__()
        self.fluid = BRINE

        # Modules
        self.first = Meter()
        self.gain = Gain().set_params("", {"scale": 3.0})
        self.second = Meter()

        # Inlets
        self.fluid_in = Port(
            Direction.IN, fluid=Fluid.ANY, phase=Phase.ANY, level=Level.ANY, flow=Flow.IMPOSED
        )

        # Controls
        self.boost = Control(float, default=1.0)

        # Outputs
        self.rise = Output(float)
        self.pressure = Output(float)
        self.electricity = Output(float)
        self.efficiency = Output(float | None)

        # Outlets
        self.fluid_out = Port(
            Direction.OUT, fluid=Fluid.ANY, phase=Phase.ANY, level=Level.ANY, flow=Flow.IMPOSED
        )

    def forward(self, inputs, inlets, state):
        """Connect the children in series; the second meter draws the line's own control."""

        # Modules
        metered = self.first(fluid_in=inlets.fluid_in, draw=1.0)
        raised = self.gain(fluid_in=metered.outlets.fluid_out, gain=inputs["boost"])
        metered_again = self.second(fluid_in=raised.outlets.fluid_out)

        # Outputs
        outputs = dict()
        if outputs_enabled():
            rise = raised.outputs.rise
            electricity = metered_again.outputs.electricity
            outputs = dict(
                rise=rise,
                pressure=raised.outlets.fluid_out.p,
                electricity=electricity,
                efficiency=ops.where(ops.eq(electricity, 0), None, ops.truediv(rise, electricity)),
            )

        # Outlets
        outlets = dict(fluid_out=metered_again.outlets.fluid_out)
        return outputs, outlets


@pytest.fixture
def line():
    """Return a ``Line`` composite with its second meter drawing 2 W."""
    line = Line()
    line.second.draw = 2.0
    return line


class Tank(Module):
    """Pass the stream on and carry a level that rises by the inlet mass flow each step."""

    def __init__(self):
        """Declare a state, an inlet, an output and an outlet."""
        super().__init__()
        self.fluid = BRINE

        # States
        self.level = State(float)

        # Inlets
        self.fluid_in = Port(
            Direction.IN, fluid=Fluid.ANY, phase=Phase.ANY, level=Level.ANY, flow=Flow.IMPOSED
        )

        # Outputs
        self.content = Output(float)

        # Outlets
        self.fluid_out = Port(
            Direction.OUT, fluid=Fluid.ANY, phase=Phase.ANY, level=Level.ANY, flow=Flow.IMPOSED
        )

    def forward(self, inputs, inlets, state):
        """Pass the stream."""
        outputs = dict(content=state["level"] + inlets.fluid_in.m_dot)
        outlets = dict(fluid_out=inlets.fluid_in)
        return outputs, outlets

    def update(self, inputs, inlets, outlets, state, dt):
        """Raise the level by the inlet mass flow."""
        return dict(level=state["level"] + inlets.fluid_in.m_dot)


class Twice(Module):
    """Call one gain twice on the same inlet and add the two pressures."""

    def __init__(self):
        """Declare the child, an inlet and an outlet."""
        super().__init__()
        self.fluid = BRINE

        # Modules
        self.gain = Gain().set_params("", {"scale": 3.0})

        # Inlets
        self.fluid_in = Port(
            Direction.IN, fluid=Fluid.ANY, phase=Phase.ANY, level=Level.ANY, flow=Flow.IMPOSED
        )

        # Outlets
        self.fluid_out = Port(
            Direction.OUT, fluid=Fluid.ANY, phase=Phase.ANY, level=Level.ANY, flow=Flow.IMPOSED
        )

    def forward(self, inputs, inlets, state):
        """Call the child twice; both calls share its inputs."""

        # Modules
        first = self.gain(fluid_in=inlets.fluid_in)
        second = self.gain(fluid_in=inlets.fluid_in)

        # Outlets
        outlet = inlets.fluid_in._with_si(p=first.outlets.fluid_out.p + second.outlets.fluid_out.p)
        outlets = dict(fluid_out=outlet)
        return {}, outlets


@pytest.fixture
def twice():
    """Return a ``Twice`` composite."""
    return Twice()


@pytest.fixture
def tank():
    """Return a stateful ``Tank`` module."""
    return Tank()


class Chain(Module):
    """Meter, then the ``middle`` module, then a meter: the middle one can be a graph break."""

    def __init__(self, middle):
        """Declare the children, the output formulas, the drive control and the ports."""
        super().__init__()
        self.fluid = BRINE

        # Modules
        self.first = Meter()
        self.middle = middle
        self.last = Meter()

        # Inlets
        self.fluid_in = Port(
            Direction.IN, fluid=Fluid.ANY, phase=Phase.ANY, level=Level.ANY, flow=Flow.IMPOSED
        )

        # Controls
        self.drive = Control(float, default=1.0)

        # Outputs
        self.value = Output(float)
        self.pressure = Output(float)

        # Outlets
        self.fluid_out = Port(
            Direction.OUT, fluid=Fluid.ANY, phase=Phase.ANY, level=Level.ANY, flow=Flow.IMPOSED
        )

    def forward(self, inputs, inlets, state):
        """Connect the children in series; every control of the middle module gets ``drive``."""

        # Modules
        metered = self.first(fluid_in=inlets.fluid_in, draw=1.0)
        controls = {name: inputs["drive"] for name in self.middle._controls}
        through = self.middle(fluid_in=metered.outlets.fluid_out, **controls)
        last = self.last(fluid_in=through.outlets.fluid_out, draw=1.0)

        # Outputs
        outputs = dict(
            value=through.outputs[next(iter(self.middle._outputs))],
            pressure=last.outlets.fluid_out.p,
        )

        # Outlets
        outlets = dict(fluid_out=last.outlets.fluid_out)
        return outputs, outlets


class Stubborn(Gain):
    """A gain whose forward needs a number from the inlet: it cannot be traced."""

    def forward(self, inputs, inlets, state):
        """Raise the pressure by the gain times the inlet temperature as a plain float."""
        gain = inputs["gain"]

        # Outlets
        ops.check(
            gain >= 0,
            PhysicsError,
            "{path}: gain = {gain}",
            path=self.path,
            gain=gain,
        )
        outlet = inlets.fluid_in._with_si(p=inlets.fluid_in.p + gain * float(inlets.fluid_in.T))
        outlets = dict(fluid_out=outlet)
        outputs = dict(rise=outlet.p - inlets.fluid_in.p, boost=0.0)
        return outputs, outlets


class Opaque(Module):
    """A composite whose own forward needs a number from the inlet: it cannot be traced."""

    def __init__(self):
        """Declare one child, an inlet, an output to copy and an outlet."""
        super().__init__()
        self.fluid = BRINE

        # Modules
        self.meter = Meter()

        # Inlets
        self.fluid_in = Port(
            Direction.IN, fluid=Fluid.ANY, phase=Phase.ANY, level=Level.ANY, flow=Flow.IMPOSED
        )

        # Outputs
        self.electricity = Output(float)

        # Outlets
        self.fluid_out = Port(
            Direction.OUT, fluid=Fluid.ANY, phase=Phase.ANY, level=Level.ANY, flow=Flow.IMPOSED
        )

    def forward(self, inputs, inlets, state):
        """Refuse a traced value."""

        # Modules
        metered = self.meter(fluid_in=inlets.fluid_in, draw=float(inlets.fluid_in.T))

        # Outputs
        outputs = dict(electricity=metered.outputs.electricity)

        # Outlets
        outlets = dict(fluid_out=metered.outlets.fluid_out)
        return outputs, outlets


class Switcher(Module):
    """Pass the stream on, but with water when the inlet is warmer than 305 K."""

    def __init__(self):
        """Declare an inlet, an output and an outlet."""
        super().__init__()
        self.fluid = BRINE

        # Inlets
        self.fluid_in = Port(
            Direction.IN, fluid=Fluid.ANY, phase=Phase.ANY, level=Level.ANY, flow=Flow.IMPOSED
        )

        # Outputs
        self.seen = Output(float)

        # Outlets
        self.fluid_out = Port(
            Direction.OUT, fluid=Fluid.ANY, phase=Phase.ANY, level=Level.ANY, flow=Flow.IMPOSED
        )

    def forward(self, inputs, inlets, state):
        """Pass the stream; the fluid depends on the value of a row."""

        # Outlets
        fluid = WATER if inlets.fluid_in.T < 305.0 else BRINE
        outlets = dict(
            fluid_out=Stream(
                m_dot=Quantity(inlets.fluid_in.m_dot, "kg/s"),
                T=Quantity(inlets.fluid_in.T, "K"),
                p=Quantity(inlets.fluid_in.p, "Pa"),
                fluid=fluid,
            )
        )
        outputs = dict(seen=inlets.fluid_in.T)
        return outputs, outlets


class Vectored(Module):
    """Pass the stream on and report the inlet pressure and one pascal more as a list."""

    def __init__(self):
        """Declare an inlet, a list output and an outlet."""
        super().__init__()
        self.fluid = BRINE

        # Inlets
        self.fluid_in = Port(
            Direction.IN, fluid=Fluid.ANY, phase=Phase.ANY, level=Level.ANY, flow=Flow.IMPOSED
        )

        # Outputs
        self.profile = Output(list[float])

        # Outlets
        self.fluid_out = Port(
            Direction.OUT, fluid=Fluid.ANY, phase=Phase.ANY, level=Level.ANY, flow=Flow.IMPOSED
        )

    def forward(self, inputs, inlets, state):
        """Pass the stream."""
        outputs = dict(profile=[inlets.fluid_in.p, inlets.fluid_in.p + 1.0])
        outlets = dict(fluid_out=inlets.fluid_in)
        return outputs, outlets


class Bounded(Module):
    """Declare a bound on a control, a boundary and three outputs: a pressure, a list, a ratio."""

    def __init__(self):
        """Declare the bounded values and the passing stream."""
        super().__init__()
        self.fluid = BRINE

        # Inlets
        self.fluid_in = Port(
            Direction.IN, fluid=Fluid.ANY, phase=Phase.ANY, level=Level.ANY, flow=Flow.IMPOSED
        )

        # Controls
        self.setpoint = Control(Pressure)

        # Boundaries
        self.ambient = Boundary(Temperature)

        # Outputs
        self.margin = Output(Pressure)
        self.profile = Output(list[Pressure])
        self.share = Output(Ratio | None)

        # Outlets
        self.fluid_out = Port(
            Direction.OUT, fluid=Fluid.ANY, phase=Phase.ANY, level=Level.ANY, flow=Flow.IMPOSED
        )

    def forward(self, inputs, inlets, state):
        """Pass the stream."""
        setpoint = inputs["setpoint"]
        outputs = dict(
            margin=inlets.fluid_in.p - setpoint,
            profile=[setpoint, setpoint - 1.0],
            share=ops.where(inputs["ambient"] > 1000.0, None, setpoint / inlets.fluid_in.p),
        )
        outlets = dict(fluid_out=inlets.fluid_in)
        return outputs, outlets


@pytest.fixture
def bounded():
    """Return a ``Bounded`` module."""
    return Bounded()


class Optional(Module):
    """Report ``-1`` while its optional control has no value, else the control doubled."""

    def __init__(self):
        """Declare an optional control, an output and no streams."""
        super().__init__()
        self.fluid = BRINE

        # Controls
        self.rate = Control(float | None, default=None)

        # Outputs
        self.double = Output(float)

    def forward(self, inputs, inlets, state):
        """Expose no fluid outlets."""
        rate = inputs["rate"]
        outputs = dict(double=ops.where(ops.isnan(rate), -1.0, 2 * rate))
        outlets = dict()
        return outputs, outlets


@pytest.fixture
def optional():
    """Return an ``Optional`` module."""
    return Optional()
