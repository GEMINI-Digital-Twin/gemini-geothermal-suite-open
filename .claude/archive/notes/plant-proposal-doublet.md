# Proposed shape of a plant: `Doublet`

The same plant as today's `Doublet` (its modules, connections and outputs come from the current
spec). It is written in the proposed style:
- a `Plant` subclass;
- structure in `__init__` only;
- no `forward`;
- design values passed to the children through `set_params`;
- plant outputs only for combinations.

```python
"""Geothermal doublet: producer with ESP, injector, and the formation around both wells."""

from gemini import physics
from gemini.modules import (
    ESP,
    Formation,
    InjectionReservoir,
    InjectionWell,
    Plant,
    ProductionReservoir,
    ProductionWell,
)
from gemini.types import (
    Efficiency,
    Inlet,
    Length,
    Outlet,
    Output,
    Parameter,
    Permeability,
    Power,
    Pressure,
    Stream,
    Temperature,
    TemperatureGradient,
    VolumeFlow,
)


class Doublet(Plant):
    """One production and one injection well into the same aquifer.

    Design values (depth, gradient, ...) derive the children's values in ``set_params``;
    a child value given in the same call wins over the derived one.
    """

    def __init__(self):
        """Declare the design values, the children, the ports, the wiring and the outputs."""
        super().__init__()

        # Modules
        self.reservoir = ProductionReservoir()
        self.well = ProductionWell()
        self.esp = ESP()
        self.riser = ProductionWell()
        self.injector = InjectionWell()
        self.sink = InjectionReservoir()
        self.formation = Formation()

        # Parameters
        self.depth = Parameter(Length | None, default=None)
        self.gradient = Parameter(TemperatureGradient | None, default=None)
        self.surface_temperature = Parameter(Temperature | None, default=None)
        self.permeability = Parameter(Permeability | None, default=None)
        self.thickness = Parameter(Length | None, default=None)
        self.well_diameter = Parameter(Length | None, default=None)
        self.nominal_flow = Parameter(VolumeFlow | None, default=None)
        self.pump_efficiency = Parameter(Efficiency | None, default=None)
        self.nominal_wellhead_pressure = Parameter(Pressure | None, default=None)

        # Inlets
        self.return_in = Inlet(Stream, kind="brine")
        self.power_in = Inlet(Power, kind="electricity")

        # Outlets
        self.supply_out = Outlet(Stream, kind="brine")

        # Connections
        self.connect("reservoir.sandface_out", "well.bottom_in")
        self.connect("well.wellhead_out", "esp.fluid_in")
        self.connect("esp.fluid_out", "riser.bottom_in")
        self.connect("riser.wellhead_out", "supply_out")
        self.connect("return_in", "injector.wellhead_in")
        self.connect("injector.bottom_out", "sink.sandface_in")
        self.connect("power_in", "esp.power_in")
        self.connect("well.loss_out", "formation.heat_in")
        self.connect("riser.loss_out", "formation.heat_in")
        self.connect("injector.loss_out", "formation.heat_in")

        # Outputs
        self.brine_cooling = Output.difference("riser.wellhead_out.T", "injector.wellhead_in.T")

    def set_params(self, path, params, valid_from=None):
        """Derive the children's values from the design values, then set everything."""
        if path:
            return super().set_params(path, params, valid_from)
        design = self.own_values(params)
        derived = physics.doublet.child_values(design, self.fluid)
        return super().set_params("", derived | params, valid_from)

    def capex(self, assumptions):
        """Return the cost of both wells by the metre and of the pump by its power."""
        ...
```

## What is no longer there

| Today | Proposed |
|---|---|
| `library.fill(self, "Doublet")` reads the structure from JSON | structure only in `__init__`, written once |
| outputs `flow`, `production_temperature`, `injection_temperature` (`Output.of`, aliases) | read by path: `results["doublet.riser.wellhead_out.T"]`, `results["doublet.reservoir.sandface_out.volume_flow"]` |
| `brine_cooling` refers to the aliases | `Output.difference` on the port paths directly |
| `_derived`, `_column`, `_flow_paths`, `_pump` in the plant file (≈100 lines) | one physics function, `physics.doublet.child_values` (or `subsurface/_physics.py`) |
| `_baselines`, `_stated`, `to_spec` override, `fluid` setter override | handled once in `Plant`: explicit values are remembered, the fluid passes to the children |

## How it is used

```python
p = gm.Plant("hackathon")
p.add(Doublet, "d1", params={"depth": "2500 m", "gradient": "30 K/km",
                             "surface_temperature": "12 degC", "permeability": "200 mD",
                             "thickness": "100 m", "well_diameter": "0.2 m"})
p.connect("d1.supply_out", "hx.hot_in")
p.connect("hx.hot_out", "d1.return_in")
p.connect("grid.power_out", "d1.power_in")

results = gm.simulate(p, plan)
results["d1.brine_cooling"]                    # plant output (combination)
results["d1.riser.wellhead_out.T"]             # port value
results["d1.esp.head"]                         # child's internal output
```

## Stored as a dict

```python
p.to_dict()["modules"]["d1"]
# {"type": "Doublet", "params": {"depth": 2500.0, "gradient": 0.03, ...}}
```

A class plant stores only its type and the values given to it, never its structure or the
derived values. A plant built by hand (`gm.Plant("hackathon")`) stores its modules and
connections, because it has no class.
