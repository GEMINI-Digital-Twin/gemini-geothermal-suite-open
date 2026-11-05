"""The plant's edge for discarded flows."""

from gemini.modules.declarations import Port
from gemini.modules.module import Module
from gemini.streams.fluid import Fluid
from gemini.streams.kinds import Direction, Flow, Level, Phase


class WasteGrid(Module):
    """Where blowdown, sand and other discarded flows leave the plant.

    ``waste_in`` takes any number of connections. What leaves is read from the port; the disposal
    cost per kg is ``economics.opex.variable.waste_disposal`` of the case.
    """

    bypass = {}
    """Removable: a sink that goes when what fed it goes."""

    def __init__(self):
        """Declare the port of the discarded flows."""
        super().__init__()

        # Inlets
        self.waste_in = Port(
            Direction.IN,
            phase=Phase.LIQUID,
            fluid=Fluid.WASTE,
            level=Level.ANY,
            flow=Flow.IMPOSED,
            many=True,
        )

    def forward(self, inputs, inlets, state):
        """End the flows here."""

        outputs = dict()
        outlets = dict()
        return outputs, outlets
