"""A small valid module in a file of its own, as a user would write and load one."""

from gemini.modules import Port
from gemini.modules.declarations import Output, Parameter
from gemini.modules.module import Module
from gemini.streams.fluid import Fluid
from gemini.streams.kinds import Direction, Flow, Level, Phase
from gemini.units.quantities import Pressure, PressureDifference


class Booster(Module):
    """Raise the stream pressure by a fixed gain."""

    category = "pumps"
    abstract = True

    def __init__(self):
        """Declare the gain, the suction and discharge ports and the head."""
        super().__init__()

        # Parameters
        self.gain = Parameter(PressureDifference, default=1e5)

        # Inlets
        self.fluid_in = Port(
            Direction.IN, fluid=Fluid.ANY, phase=Phase.ANY, level=Level.ANY, flow=Flow.IMPOSED
        )

        # Outputs
        self.head = Output(Pressure)

        # Outlets
        self.fluid_out = Port(
            Direction.OUT, fluid=Fluid.ANY, phase=Phase.ANY, level=Level.ANY, flow=Flow.IMPOSED
        )

    def forward(self, inputs, inlets, state):
        """Return the suction stream at a pressure raised by the gain."""

        # Outlets
        discharge = inlets.fluid_in._with_si(p=inlets.fluid_in.p + self.gain)

        # Outputs
        outputs = dict(head=self.gain)

        outlets = dict(fluid_out=discharge)
        return outputs, outlets


EXAMPLE = {
    "inlets": {
        "fluid_in": {
            "fluid": {"kind": "brine"},
            "m_dot": {"value": 10, "unit": "kg/s"},
            "T": {"value": 50, "unit": "degC"},
            "p": {"value": 2, "unit": "bar"},
        }
    }
}
"""Values for one call of ``Booster``, the arguments of ``gm.evaluate``."""
