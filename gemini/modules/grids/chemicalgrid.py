"""The plant's edge for bought chemicals."""

from gemini.modules.declarations import Port
from gemini.modules.module import Module
from gemini.physics import gas
from gemini.streams.flows import Stream
from gemini.streams.fluid import Fluid
from gemini.streams.kinds import Direction, Flow, Level, Phase


class ChemicalGrid(Module):
    """Where a chemical product enters the plant.

    ``chemical_out`` is offered without flow at normal conditions and the dosing module returns what
    it takes, so the dosed amount is read from the port. The product price is
    ``economics.opex.variable.chemical`` of the case.
    """

    bypass = {}
    """Removable: a supply that goes when what it fed goes."""

    def __init__(self):
        """Declare the outlet."""
        super().__init__()

        # Outlets
        self.chemical_out = Port(
            Direction.OUT,
            phase=Phase.LIQUID,
            fluid=Fluid.CHEMICAL,
            level=Level.AMBIENT,
            flow=Flow.DRAWN,
            offered=True,
        )

    def _offer(self, inputs, inlets, state):
        """Offer the product at normal conditions, with the module's fluid."""
        offered = Stream._si(
            m_dot=0.0, T=gas.NORMAL_TEMPERATURE, p=gas.NORMAL_PRESSURE, fluid=self.fluid
        )
        return {"chemical_out": offered}

    def forward(self, inputs, inlets, state):
        """Nothing but what the dosing draws leaves."""

        outputs = dict()
        outlets = dict()
        return outputs, outlets
