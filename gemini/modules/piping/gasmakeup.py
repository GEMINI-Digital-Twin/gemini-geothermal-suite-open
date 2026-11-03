"""Gas makeup: the co-produced gas first, the grid for the shortfall, the surplus to a flare."""

from gemini import ops
from gemini.modules._utils.equipment import Equipment
from gemini.modules.declarations import Port
from gemini.modules.module import Module
from gemini.streams.fluid import Fluid
from gemini.streams.kinds import Direction, Flow, Level, Phase


class GasMakeup(Equipment, Module):
    """A mixer of co-produced gas and grid gas in front of a burner.

    ``fuel_out`` offers the burner the gas of ``gas_in``, marked with the composition of the grid on
    ``grid_in``. The burner burns the co-produced gas first and returns what it burned, so the
    makeup draws the shortfall from the grid through ``grid_in`` and sends the surplus to
    ``excess_out``, usually a ``Flare``.
    """

    equipment_kind = "gas_makeup"

    offer_inlets = ("gas_in", "grid_in")

    def __init__(self):
        """Declare the ports."""
        super().__init__()

        # Inlets
        self.gas_in = Port(
            Direction.IN,
            phase=Phase.GAS,
            fluid=Fluid.NATURAL_GAS,
            level=Level.AMBIENT,
            flow=Flow.IMPOSED,
        )
        self.grid_in = Port(
            Direction.IN,
            phase=Phase.GAS,
            fluid=Fluid.NATURAL_GAS,
            level=Level.AMBIENT,
            flow=Flow.DRAWN,
        )

        # Outlets
        self.fuel_out = Port(
            Direction.OUT,
            phase=Phase.GAS,
            fluid=Fluid.NATURAL_GAS,
            level=Level.AMBIENT,
            flow=Flow.DRAWN,
            offered=True,
        )
        self.excess_out = Port(
            Direction.OUT,
            phase=Phase.GAS,
            fluid=Fluid.NATURAL_GAS,
            level=Level.AMBIENT,
            flow=Flow.IMPOSED,
        )

    def _offer(self, inputs, inlets, state):
        """Offer the co-produced gas with the mark that the grid covers the rest."""
        gas_in = inlets.gas_in
        fluid = gas_in.fluid.with_grid(inlets.grid_in.fluid.gas_composition)
        return {"fuel_out": gas_in._with_si(fluid=fluid)}

    def forward(self, inputs, inlets, state):
        """Draw the shortfall from the grid and pass the surplus on."""

        # Outlets
        gas_in, burned = inlets.gas_in, inlets.fuel_out.m_dot
        excess_out = gas_in._with_si(m_dot=ops.maximum(gas_in.m_dot - burned, 0.0))
        shortfall = ops.maximum(burned - gas_in.m_dot, 0.0)
        grid_in = inlets.grid_in._with_si(m_dot=shortfall, T=gas_in.T, p=gas_in.p)

        outputs = {}
        outlets = dict(excess_out=excess_out, grid_in=grid_in)
        return outputs, outlets

    def cost_size(self):
        """Return the size that the cost of the grid connection scales with: 1, a fixed item."""
        return 1
