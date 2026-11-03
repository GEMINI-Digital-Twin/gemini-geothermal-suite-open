"""The rock around the wells of a doublet."""

from gemini.modules.declarations import Parameter, Port
from gemini.modules.module import Module
from gemini.streams.energy import Energy
from gemini.streams.kinds import Direction, Flow
from gemini.units.quantities import Temperature, TemperatureGradient


class Formation(Module):
    """The rock the wells pass through: their heat loss ends here.

    A ``Doublet`` creates and wires it, so a user never connects it, and passes it the
    ``geothermal_gradient`` and the ``surface_temperature`` of the design. ``heat_in`` receives the
    heat each well loses.
    """

    def __init__(self):
        """Declare the rock and what it receives."""
        super().__init__()

        # Parameters
        self.geothermal_gradient = Parameter(
            TemperatureGradient | None,
            default=None,
            case="site.ground.gradient",
            description=(
                "Increase of undisturbed rock temperature with depth; empty takes it from the case"
            ),
        )
        self.surface_temperature = Parameter(
            Temperature | None,
            default=None,
            case="site.ground.surface_temperature",
            description="Ground temperature at the surface; empty takes it from the case",
        )

        # Inlets
        self.heat_in = Port(Direction.IN, energy=Energy.HEAT, flow=Flow.IMPOSED, many=True)

    def forward(self, inputs, inlets, state):
        """End the heat of the wells here."""

        outputs = dict()
        outlets = dict()
        return outputs, outlets
