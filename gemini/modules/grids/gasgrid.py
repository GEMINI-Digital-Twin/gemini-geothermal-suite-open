"""The gas grid: the plant's edge for bought gas."""

from gemini.errors import ValidationError
from gemini.modules.declarations import Parameter, Port
from gemini.modules.module import Module
from gemini.physics import gas
from gemini.streams.flows import Stream
from gemini.streams.fluid import Fluid, grid_gas
from gemini.streams.kinds import Direction, Flow, Level, Phase
from gemini.units.quantities import Fraction


class GasGrid(Module):
    """Gas grid: bought gas of ``composition``, which the case states.

    The composition is the physical property of the gas grid, ``utilities.gas.composition`` of the
    case; a plant file does not state it, and a run without it raises ``missing_value``.

    ``gas_out`` is offered at normal conditions, without flow, and the taker returns what it burns:
    a burner on ``gas_out``, or a ``GasMakeup`` for the shortfall of the co-produced gas.
    """

    def __init__(self):
        """Declare the grid gas composition and the outlet."""
        super().__init__()

        # Parameters
        self.composition = Parameter(
            dict[str, Fraction] | None,
            default=None,
            structural=True,
            case="utilities.gas.composition",
            description=(
                "Mole fractions of the gas components by name; empty takes them from the case"
            ),
        )

        # Outlets
        self.gas_out = Port(
            Direction.OUT,
            phase=Phase.GAS,
            fluid=Fluid.NATURAL_GAS,
            level=Level.AMBIENT,
            flow=Flow.DRAWN,
            offered=True,
        )

    def _offer(self, inputs, inlets, state):
        """Offer the grid gas at normal conditions."""
        if self.composition is None:
            raise ValidationError(
                f"{self.path}: composition is missing; expected utilities.gas.composition in the "
                "case",
                path="utilities.gas.composition",
                code="missing_value",
            )
        offered = Stream._si(
            m_dot=0.0,
            T=gas.NORMAL_TEMPERATURE,
            p=gas.NORMAL_PRESSURE,
            fluid=grid_gas(self.composition),
        )
        return {"gas_out": offered}

    def forward(self, inputs, inlets, state):
        """Nothing but what the taker draws leaves the grid."""

        outputs = dict()
        outlets = dict()
        return outputs, outlets
