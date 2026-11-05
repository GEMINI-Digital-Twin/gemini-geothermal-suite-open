"""Nodal doublet with three parallel heat exchangers on one secondary network."""

from gemini.modules.container import ModuleList
from gemini.modules.declarations import Port
from gemini.modules.exchangers import HeatExchanger
from gemini.modules.grids import ElectricityGrid
from gemini.modules.piping import Mixer, Splitter
from gemini.modules.treatment import Degasser, Filter
from gemini.plants._utils.cascades import mix_chain
from gemini.plants.nodaldoublet import NodalDoublet
from gemini.plants.plant import Plant
from gemini.streams.fluid import Fluid
from gemini.streams.kinds import Direction, Flow, Level, Phase

EXCHANGERS = 3
"""The heat exchangers in parallel; the share of the flow each takes is the ``split_fraction`` of
the splitters of the plant file."""
TEES = EXCHANGERS - 1
"""The splitters or mixers of one cascade."""


class ParallelExchangerPlant(Plant):
    """Nodal doublet whose brine heats one secondary network through three parallel exchangers.

    The port of the upstream GEMINI simulator's ``parallel_hex_plant`` example. The producer is
    solved for its rate at the ``doublet.wellhead_pressure`` boundary; the brine passes a degasser
    and a filter, is divided over the exchangers, remixed, filtered again and injected, with the
    injection pump set to the wellhead pressure the injector needs. The secondary water is divided
    in the same way and remixed after the exchangers. The shares are the designer's: the
    ``split_fraction`` of the two splitter cascades, stated in the plant file (a splitter sends
    that share of its feed to its second branch, the last exchanger takes the rest).
    ``tests/fixtures/plants/ParallelExchangerPlant.json`` carries the shares and the well,
    reservoir, ESP and exchanger data of the upstream example.

    Not schedulable: its doublet is a ``NodalDoublet``, and a run sets its splits and setpoints.
    """

    def __init__(self):
        """Build the plant; the tees are cascades of two-way splitters and mixers."""
        super().__init__()

        # Modules
        self.doublet = NodalDoublet()
        self.degasser = Degasser()
        self.inlet_filter = Filter()
        self.primary_splitters = ModuleList(Splitter() for _ in range(TEES))
        self.secondary_splitters = ModuleList(Splitter() for _ in range(TEES))
        self.heat_exchangers = ModuleList(HeatExchanger() for _ in range(EXCHANGERS))
        self.primary_mixers = ModuleList(Mixer() for _ in range(TEES))
        self.secondary_mixers = ModuleList(Mixer() for _ in range(TEES))
        self.outlet_filter = Filter()
        self.electricity_grid = ElectricityGrid()

        # Inlets
        self.return_in = Port(
            Direction.IN, fluid=Fluid.ANY, phase=Phase.LIQUID, level=Level.ANY, flow=Flow.IMPOSED
        )

        # Outlets
        self.supply_out = Port(
            Direction.OUT, fluid=Fluid.ANY, phase=Phase.LIQUID, level=Level.ANY, flow=Flow.IMPOSED
        )
        self.gas_out = Port(
            Direction.OUT,
            phase=Phase.GAS,
            fluid=Fluid.NATURAL_GAS,
            level=Level.AMBIENT,
            flow=Flow.IMPOSED,
        )

        # Connections
        self.connect("return_in", "secondary_splitters.0.fluid_in")
        self.connect("doublet.supply_out", "degasser.fluid_in")
        self.connect("degasser.liquid_out", "inlet_filter.fluid_in")
        self.connect("inlet_filter.fluid_out", "primary_splitters.0.fluid_in")
        self._divide("primary_splitters", "hot_in")
        self._divide("secondary_splitters", "cold_in")
        self._combine("primary_mixers", "hot_out")
        self._combine("secondary_mixers", "cold_out")
        self.connect(f"primary_mixers.{TEES - 1}.fluid_out", "outlet_filter.fluid_in")
        self.connect("outlet_filter.fluid_out", "doublet.return_in")
        self.connect("electricity_grid.power_out", "doublet.power_in")
        self.connect(f"secondary_mixers.{TEES - 1}.fluid_out", "supply_out")
        self.connect("degasser.gas_out", "gas_out")

    def _divide(self, cascade, port):
        """Connect a splitter cascade: each sends its share to an exchanger, the last the rest."""
        for index in range(TEES):
            self.connect(f"{cascade}.{index}.branch2_out", f"heat_exchangers.{index}.{port}")
            if index < TEES - 1:
                self.connect(f"{cascade}.{index}.branch1_out", f"{cascade}.{index + 1}.fluid_in")
        self.connect(f"{cascade}.{TEES - 1}.branch1_out", f"heat_exchangers.{TEES}.{port}")

    def _combine(self, cascade, port):
        """Connect a mixer cascade over the exchangers, the running mix entering first."""
        mix_chain(self, [f"heat_exchangers.{index}.{port}" for index in range(TEES + 1)], cascade)
