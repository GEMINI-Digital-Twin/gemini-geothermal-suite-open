# Building plants

A leaf module computes and a plant connects: no class does both ([modules.md](modules.md)). Every
composite is a `Plant`. A plant declares its children, ports and connections and never writes
`forward` or `update`: `Plant.forward(inputs, inlets, state)` and `Plant.update(inputs, inlets,
outlets, state, dt)` are written once, for any graph. The state of a plant is the nested dict of the
states of its children, by child name; `forward` hands each child its entry, returns the plant's
combined outputs and outlets, solves the closed loops, and builds nothing: the plan is built before
the call, in `Plant._prepare`. `describe()`, `gm.simulate`, `gm.replay` and `gm.live`
work on any plant, on every backend, and a plant has no run method of its own: run it with
`results = gm.simulate(plant, case)`. How it is computed is in
[native-engine.md](native-engine.md#14-the-plant-class-and-the-plant-dict).

`Plant` is in `gemini/plants/plant.py`, with the plant classes, one file each; `gemini.modules`
never imports `gemini.plants`. Every tool of the plants (the plan, the run, ports, loops, constraints, outputs, the
reader and writer of the plant dict, the schema, the catalogue) is in
`gemini/plants/_utils/`.

Plants are defined in Python. gemini keeps no JSON file; JSON exists only as the plant file that
agents use: `gm.Plant.from_dict`, `plant.to_dict`, `gm.Plant.from_json`, `plant.to_json`,
`gm.plants.schema`.

## A plant class

```python
from gemini.modules import Direction, Level, Output, Phase, Port
from gemini.modules.exchangers import HeatExchanger
from gemini.modules.grids import HeatingGrid
from gemini.modules.piping import Valve
from gemini.modules.pumps import CirculationPump
from gemini.plants import Plant
from gemini.streams import Fluid
from gemini.streams.energy import Energy


class HeatingSubstation(Plant):
    """Indirect district-heating substation serving a building heating circuit."""

    def __init__(self):
        """Declare the children, the ports and the circuits."""
        super().__init__()

        # Modules
        self.valve = Valve()
        self.heat_exchanger = HeatExchanger()
        self.consumer = HeatingGrid()
        self.pump = CirculationPump()

        # Inlets
        self.supply_in = Port(
            Direction.IN, fluid=Fluid.WATER, phase=Phase.LIQUID, level=Level.HOT
        )
        self.power_in = Port(Direction.IN, energy=Energy.ELECTRICITY)

        # Outlets
        self.return_out = Port(
            Direction.OUT, fluid=Fluid.WATER, phase=Phase.LIQUID, level=Level.HOT
        )
        self.loss_out = Port(Direction.OUT, energy=Energy.HEAT)

        # Connections
        self.connect("supply_in", "valve.fluid_in")
        self.connect("power_in", "pump.power_in")
        self.connect("valve.fluid_out", "heat_exchanger.hot_in")
        self.connect("heat_exchanger.hot_out", "return_out")
        self.connect("heat_exchanger.cold_out", "consumer.supply_in")
        self.connect("consumer.return_out", "pump.fluid_in")
        self.connect("pump.fluid_out", "heat_exchanger.cold_in")
        self.connect("pump.loss_out", "loss_out")

        # Outputs
        self.approach = Output.difference("heat_exchanger.hot_out.T", "pump.fluid_out.T")
```

The sections are `# Modules`, `# Parameters`, `# Inlets`, `# Boundaries`, `# Outlets`,
`# Connections`, `# Constraints`, `# Outputs`, in that order, empty ones left out. The rules:

- A child assigned as an attribute is registered as `add` does. `super().__init__()` names the plant
  after its class.
- A structural argument goes to `__init__` and into `self._size`, a dict of those arguments:
  `DistrictNetwork(consumers=3, service="cooling")`, `MultiWellPlant(producers=3, injectors=2)`,
  `HeatingCoolingPlant(doublets=2)`.
- A plant class in `gemini/plants/` is registered by its class name. `purpose` says what it
  serves (`heating`, `cooling`, `both`); a building block has none.
- No subclass of `Plant` defines `forward` and no other `Module` holds children
  (`tests/unit/test_code_quality.py`).
- A plant may derive its children's values: see [a plant that sets its children's values](modules.md#a-plant-that-sets-its-childrens-values).

## The builder

```python
import gemini as gm

plant = gm.Plant("Doublet")
plant.add("InjectionWell", name="injector")
plant.add("InjectionReservoir", name="sink")
plant.add("ProductionReservoir", name="reservoir")
plant.add("ProductionWell", name="well")
plant.add("ESP", name="esp")
plant.add("ProductionWell", name="riser")
plant.connect("injector", "sink")
plant.connect("reservoir", "well")
plant.connect("well", "esp")
plant.connect("esp", "riser")
plant.connect("return_in", "injector.wellhead_in")
plant.connect("riser.wellhead_out", "supply_out")
print(plant.summary())
print(len(plant.check()))
```

`add(type, name=None, params=None)` takes a registry name or a class and one dict of parameters,
the dict `set_params` takes: a `Quantity` or its dict for a value with a dimension (a bare number for it raises `invalid_value`), dotted names for a composite
(`params={"reservoir.temperature": {"value": 87, "unit": "degC"}}`). `connect` takes a handle, `"path.port"` or a module
path. A module path picks the only free port of a fitting kind; a port without a kind fits anything.
If several pairs fit, a `ValidationError` with code `ambiguous_port` lists them. A bare word that
names no module is a plant port, as in `return_in` above. Only `connect` wires modules; there is no
call syntax.

Every inlet and outlet of every module is connected to another module or to a named plant port. A
plant port exists only when it is named; there are no automatic ports. An unconnected port is an
error with code `unconnected_port` and the port path: `plant.check()` and
`from_dict` report it, and a plant with one does not run. While you build, `add` and `connect` do
not check it.

A plant answers what its wiring is: `p.target_of("hx.cold_out")` and `p.source_of("hx.cold_in")` give
the other end of a connection, and `p.feeds("boiler.fluid_out")` the modules an outlet reaches along
its circuit, through mixers, splitters and the units on it, ending at a grid. `gm.schedule` reads the
role of a unit from it.

## The plant file

The plant file is the input of an agent's plant-building tool (`gm.plants.schema()` is its schema)
and what the backend stores; `plant.to_dict()` and `gm.Plant.from_dict(data)` are the same form in
memory. It has two forms, both with the header `{"format": 1, "kind": "plant", "name": ...}`.

**A plant of a class** stores its class, its structural size and the values that were given, never
its structure or a derived value:

```json
{"format": 1, "kind": "plant", "name": "MultiWellPlant", "type": "MultiWellPlant",
 "size": {"producers": {"value": 3}, "injectors": {"value": 2}},
 "params": {"producers": {"0": {"reservoir": {"temperature": {"value": 87, "unit": "degC"}}}}}}
```

**A plant built with `gm.Plant(name)`** has no class and stores its structure. `to_dict(structure=True)`
gives the same form of any plant: this is how an agent edits one, and how it removes a unit, by
taking the unit out of `modules` and `connections` and joining what it joined.

```json
{"format": 1, "kind": "plant", "name": "Doublet",
 "modules": {"injector": {"type": "InjectionWell"}, "sink": {"type": "InjectionReservoir"},
             "reservoir": {"type": "ProductionReservoir"}, "well": {"type": "ProductionWell"},
             "esp": {"type": "ESP"}, "riser": {"type": "ProductionWell"}},
 "connections": [{"source": "injector.bottom_out", "target": "sink.sandface_in"},
                 {"source": "reservoir.sandface_out", "target": "well.bottom_in"},
                 {"source": "well.wellhead_out", "target": "esp.fluid_in"},
                 {"source": "esp.fluid_out", "target": "riser.bottom_in"}],
 "inlets": {"return_in": "injector.wellhead_in"},
 "outlets": {"supply_out": "riser.wellhead_out"},
 "params": {}}
```

| Key | Form | Meaning |
| --- | --- | --- |
| `format`, `kind`, `name` | both | `1`, `"plant"`, the plant name; `about` is free text that no code reads |
| `type`, `size`, `params` | class | the class name, its structural arguments as leaves and the tree of values that were given |
| `modules` | structure | `{id: {type, size?, params}}`; a group is `{type: "ModuleDict", modules: {...}}` |
| `connections` | structure | `[{source, target, type?}]`, ends are `"path.port"` |
| `inlets`, `outlets` | structure | `{plant port: "path.port"}`, a list when several ends share a power or air port |
| `outputs` | structure | `{name: {"difference": [a, b]}}`, `{"ratio": [a, b]}` or `{"sum": [a, b, ...]}`; see [outputs](#outputs) |
| `constraints` | structure | `[{target, equals or at_least, by, bounds}]`; see [constraints](#constraints) |
| `fluids`, `boundary` | both | `{path: {...}}`, the fluid of a module and the stored boundary of a module |

- `type` of a module is a registry name. It may name a plant class, whose parameters are then below
  it in the `params` tree, so a plant can contain plants.
- `ModuleDict` and `ModuleList` are groups: they hold children and have no wiring of their own.
  Connections reach through a group (`filters.hot.fluid_out`) but never into a plant child:
  `doublet.supply_out` is right, `doublet.esp.fluid_out` is an error.
- An inlet has one source and an outlet feeds one inlet (`port_in_use`), except a `many` port.
  Splitting and mixing streams are `Splitter` and `Mixer`.
- A port no connection uses is named in `inlets` / `outlets`, or it is `unconnected_port`.
- The order of connections sets the order of the calls where the wiring leaves it open, which is
  what a float sum over the ports depends on. The key order of a dictionary carries no meaning for
  numbers.
- The round trip `from_dict(p.to_dict())` rebuilds the same plant with the same numbers, for every
  shipped plant, quantity dicts included: a stated value stays as written while it equals the current
  one. The backend digests sorted-key JSON.
- A `fluids` entry passes to the modules below it, unless the section names one of them: then it
  speaks for each. The fluid of a plant set in code passes to every child.

`gm.plants.schema()` is generated from the code: the two forms, the enum of registered types, the
output forms. `plant.check()` takes no argument and returns the issues of the plant and of its
file (`unconnected_port`, `unknown_name` with suggestions and the other codes of
[errors.md](errors.md), on the paths of the dict, such as `connections[1].target`); it never
raises, and `Plant.from_dict` raises the same issues in one `ValidationError`.

`plant.set_inputs` is the one public way to set an input in memory, with a quantity for a value with
a dimension (a bare number raises `invalid_value`; `_set_si_inputs` is the private SI path of
`gemini`). A plant file has no `inputs` key: the setpoint of a stored heat pump is a leaf of its
`params`, a column of the run wins over it, and `gm.schedule` reads it through `plant.input_value`.
A value assigned on a module (`plant.pump.frequency = {"value": 50, "unit": "Hz"}`) and the last
tick a run leaves on a module are not stored. `plant.to_json(path, structure=False)` and
`gm.Plant.from_json(path)` write and read the file. A plant file of an older format raises
`ValidationError` with code `old_format`.

## What the plant file holds

A plant file (`kind: plant`, `format: 1`, header `{"format", "kind", "name"}` and free `about`) holds
only the plant: `type` (a class from `gm.plants.names()`) or `modules` and `connections` (with
`inlets`, `outlets`, `outputs`, `constraints`); both given must agree. `size` sits beside `params`,
one leaf per structural argument (`"doublets": {"value": 2, "range": {"min": 1, "max": 3}}`).
`params` is one tree that mirrors the module tree (`params.d0.esp.efficiency`); every leaf is an
object `{"value", "unit", "range", "options", "history"}`: `unit` if and only if the value has a
dimension, `range` and `options` the search freedom (an option is in the closed list of the
parameter, a range within its bounds), `history` the dated values `[{valid_from, value}]`. A leaf
may have no value: a template that `size` completes. A control or a boundary of a module is a leaf
too (`params.heat_pump.temperature_setpoint`), so there is no `inputs` key. The plant-level
`dispatch` and `outages` sit under `params.control`, `backup` and `depth` at the top of `params`.
`fluids` and `boundary` stay as keys by module path. There is no `bindings` key: a file naming
columns would tie the plant to one dataset; `set_bindings` stays in memory, and a checkpoint stores
them itself. A file of `format: 2` with no `kind` raises `old_format`. It holds nothing that
describes the world or the request, which is in the `gm.Case`: not the ground (gradient, surface
temperature), the reservoir (permeability, thickness, pressure), the brine of a `Doublet`, the air,
the return and supply temperatures of the consumers, the prices, the limits or the demand. A
parameter that the case sets is declared with `Parameter(..., case="<path in the case>")`
(`Doublet.gradient`, `surface_temperature`, `permeability`, `thickness`; `Formation.geothermal_gradient`,
`surface_temperature`; `GasGrid.composition`; `Atmosphere.pressure`; the `ElectricityGrid` limits; of
`HeatingGrid` and `CoolingGrid` the return temperature, pressure and limits and the required supply
temperature, and for cold the dew point margin) or a boundary with `Boundary(..., case=...)`
(`CoolingGrid.indoor_temperature` and `indoor_relative_humidity`, `Desander.sand_concentration`): a
plant file that states one is refused with `invalid_value` naming the case path, and `to_dict`
never writes it. What the plant states instead is a **margin** over a supply temperature
(`supply_margin` of a unit on a supply line, K), the operating `frequency` of an injection pump, and
the operating limits of the equipment (`esp.minimum_intake_pressure`, `esp.maximum_gas_fraction`).
The limits are values of the plant, so `resize` repeats them on each added doublet; the split
fractions of `ParallelExchangerPlant` are controls of its splitters in the file. A bare number with a dimension is refused. `from_dict` raises every
issue at once, except a parameter or size without a value; `plant.check()` returns all of them and
never raises. `plant.ranges` and `plant.options` give the search space in file order, `plant.size`
the sizes, `set_range` and `set_options` change them with the checks of a file. Known limits:

- `fluids` remains in the plant dict, for a module whose fluid differs from its class default. A
  plant with no case (a measured or replayed plant such as `DoubletHeatPlant`) carries its own
  brine there; with a case, a `Doublet` takes its fluid from `site.fluid`.
- The constructor defaults of the class plants (`doublets=1`, `consumers=2`, `service='heating'`,
  `producers=2`, `injectors=1`, inputs.md 7.12) stay: hundreds of calls use them.

## Superstructure

A plant may state which of its modules are open to a search of structures
(`gemini/plants/_utils/superstructure.py`), next to its ranges and options:

- `plant.set_optional("peak_boiler")`: the module may be off. Off is a **bypass**: each stream
  inlet `<x>_in` is joined to its stream outlet `<x>_out` (`fluid_in` to `fluid_out`, `hot_in` to
  `hot_out`, `source_in` to `source_out`, ...), so what fed the module feeds what it fed; its power
  ports and its other ports go with it, and it costs nothing. A module class may declare
  `bypass = {inlet: outlet}` instead of the name pairs. A module with no pair and no `bypass`
  (`Doublet`, `Mixer`, `Splitter`, `Degasser`) cannot be optional: which outlet an inlet joins is
  ambiguous, and `set_optional` raises `invalid_design`. `set_optional(name, False)` removes it.
- `plant.set_choice("cooling", {"absorption": ["chiller", "chiller_cooler"], "none": []})`: exactly
  one group is on, the modules of the others are bypassed. The groups are apart, a group may be
  empty, a module of a choice is not optional, and `groups=None` removes the choice.
- `plant.structures()` lists every valid structure, `{"peak_boiler": True, "cooling": "none"}`, in a
  fixed order (optional modules on before off, groups in the order stated); `plant.with_structure(s)`
  gives the ordinary plant of one, without optional modules and choices. A structure is valid when
  that plant reads and its `check()` has no error other than a missing value. A missing or unknown
  key of `s` raises; there is no default structure.
- The plant file holds them as `"optional": [...]` and `"choices": {name: {group: [...]}}`;
  `from_dict` reports a bad declaration as an issue at its path, and `plant.check()` of a
  superstructure judges the ports in each structure and reports `invalid_design` when none is valid.

The plant of a structure keeps the values, ranges and options of the modules that stay. Alternatives
sit in series on one circuit (the chillers one after the other on the chilled water), so that the
bypass of those that are off leaves a working circuit. A connection through a chain of modules that
are off joins its two ends, a `state` connection stays one, and a loop inside the modules that are
off goes; a join that would lead a module back to itself (the air of a dry cooler that is off,
from the atmosphere back to it) goes too, so a consumer whose only unit is off is left unconnected
and that structure is invalid. A plant of a class with a module off cannot keep its class, whose structure is fixed: it
becomes a plant of modules and connections in which every value of a module is stated, and the
values of the class itself (`depth`) and its `size` go, their effect kept in the modules. With no
module off a plant keeps its class. `gm.study.evolve` sets such values before it takes the structure,
so they stay genes of its search. Doublets in parallel are never bypassed: a doublet count is the
`size.doublets` range of a class plant.

### Union of plants

`gm.plants.union(plants, *, name)` (`gemini/plants/_utils/union.py`) builds the superstructure of
several concrete plants, so that a search of structures holds each of them:

- **Modules** match by name: the same name and type are one module, and one name with two types
  raises `invalid_design` naming both. A module of every plant is fixed. Every other one must be
  optional, so it needs a bypass pair (`<x>_in`/`<x>_out` or a class `bypass`); one without
  (`Splitter`, `Mixer`, a grid) raises `invalid_design` naming each, as merging those plants needs a
  stated bypass (`set_bypass`). A plant of a class is first read as modules and connections with
  every value of its modules stated, as `with_structure` does.
- **Wiring.** A chain of a plant starts at an outlet of a fixed module (or a plant inlet), passes
  through the bypass pairs of modules that are not fixed and ends at the next other inlet. The
  chains of all plants between the same two ends are merged into one series in an order each
  plant keeps, so that the bypass of the modules that are off gives back each plant's
  connections; the other connections are taken as stated. A chain from a module back to it (the
  air of a cooler, from the atmosphere back to it) is kept side by side, the bypass dropping it.
- **Choices.** Where the plants put disjoint groups of modules between the same two fixed modules
  (`y` in one plant, `z` in another, nothing in a third), the groups are a choice
  `{"y_or_z": {"y": [...], "z": [...], "none": []}}`, each group named after its first module; a
  module present in exactly the plants of a group joins it. The other modules are optional.
- **Values.** A value stated differently keeps the first plant's value; its options are joined and
  its range widened to the lowest minimum and highest maximum (in the first plant's unit). The same
  goes for `fluids`, `boundary` and `outputs` by key; `constraints` are joined.
- **Result.** A new `gm.Plant` with the attribute `union`: `{"structures": {plant name:
  structure}, "notes": [{"path", "kept", "values"}]}`, `values` by plant name. Before returning,
  each structure is checked: `with_structure` gives the plant's modules and connections (as sets of
  `"path.port"`, the type `state` included). Plants that no such series reproduces (two orders of
  the same modules, another connection between fixed modules, a module port at two places) raise
  `invalid_design` naming the plants and the connection.

Of the six plants of `examples/hackathon_2026`, `HeatingCoolingPlant`, `HeatingFullCoolingPlant`
and `HeatingAbsorptionCoolingPlant` merge into exactly the wiring and modules of the hand-built
`examples/hackathon_superstructure` (heat pump, adsorption and compression chillers and their coolers
optional). The six together raise: `HeatingPlant` and `HeatingHeatPumpCoolingPlant` lack the drive
splitter, mixer and cooling consumer, and `HackathonPlant` names its modules otherwise, so those
splitters, mixers and grids would have to be optional without a bypass pair.

## Loops

A connection that closes a cycle is a tear stream. `Plant.forward` iterates the cycle until the tear
stream converges, the same way for every plant:

- The tear is the connection out of a module that gives a first guess (`Module._loop_start`), else
  the last in the connection list. In a substation it is `consumer.return_out`, and on the drive
  water of a chiller the outlet of the `Mixer`, whose guess is the water that joins from outside.
  The first guess has no flow, the highest pressure that enters the loop and the fluid that enters
  the module of the tear.
- A tear stream without flow carries nothing: only its flow has to converge.
- Each pass runs the modules of the loop without recording them, and moves each field of the tear
  stream by Wegstein's method (`plants/_utils/loops.py`); then every module is called once with the
  converged stream, so outputs and balances see one call each. A stateful module in a loop is
  called from the state of the step on every pass (a trial advances nothing).
- `Module._loop_limits` keeps the iterate on the side where a module is valid: a heat exchanger
  must not reverse.
- A loop needs a module that sets its flow and its pressure, such as a `CirculationPump`.
- `plant.loop_tolerance` (1e-9, SI) and `plant.loop_passes` (50) are the settings. A loop that does
  not converge raises `PhysicsError` with code `loop_not_converged` and the tear path.

A compiled plant traces its loops as a `fixed_point` node that iterates on arrays, masked per row,
with the numbers of a plain call. A plant with a constraint is a root break: it runs for real, row by
row, the same on every backend ([engine](engine.md#the-runner)).

A connection with `"type": "state"` reads the value of the previous step. It orders nothing and
closes no loop: the target takes what the source outlet gave one step before, so a cycle that has
one such connection is no loop to iterate. The plant is then stateful, and the engine scans it in
time ([engine](engine.md#the-runner)); the values are in the plant's state under `@previous`. The
first step reads the stream at rest, at the temperature the source module guesses for a loop
(`_loop_start`) and the highest pressure of the plant inlets; a source that guesses none raises
`invalid_design`.

A plant child in a cycle with other modules, with no cycle among the leaves, is opened: its children
are called directly by the parent, as `DoubletHeatPlant` does with its `doublet`, its constraints are
solved by the parent, and its own outputs are not computed.

## Constraints

```text
self.constrain(
    "riser.wellhead_out.p",
    equals="wellhead_pressure",
    by="reservoir.production_rate",
    bounds="production_rates",
)
self.constrain(
    "injector.bottom_out.p",
    at_least="sink.bottomhole_pressure",
    by="injection_pump.pressure_setpoint",
    bounds=("injection_pump.fluid_in.p", "maximum_injection_pressure"),
)
```

The engine finds the value of the control or boundary `by` at which `target` reaches its value, with
`ops.brentq`, running the modules between them without recording them; then it calls those modules
once with it. `target` and the value are paths; `bounds` is the path of a pair, or two numbers or
paths. With `at_least` a target that reaches its value at the lower bound keeps that bound: the
injection pump adds no head when the column of brine is enough. `plants/_utils/targets.py` is the
solve; `gm.analysis.nodal` keeps its own curves in `gemini/analysis/nodal.py`.

## Outputs

A plant's outputs are only combinations of paths, computed after its children, traced, the same on
every backend:

```text
self.brine_cooling = Output.difference("riser.wellhead_out.T", "injector.wellhead_in.T")
self.share = Output.ratio("boiler.fuel", "chp.fuel")
self.fuel = Output.sum("boiler.fuel", "chp.fuel")
```

A path is an output of a child, a port field (`.m_dot`, `.T`, `.p`) or a bare name for an earlier
output of the plant. The output takes the kind of its paths: a difference of temperatures is a
temperature difference, a ratio has no unit. A value of `None` or a zero divisor gives `None`.
Anything else is read by path: a child's output (`results["sub.consumer.unmet_demand"]`) or a port
field (`results["sub.heat_exchanger.hot_out.T"]`). A plant never sums what a port shows: a total is
read from the ports of its edge modules.

## Registered plants

`gm.plants.names(category=None)` lists the plant classes, `category` being what they serve;
`gm.plants.get(name)` gives a plant without values.

| Class | Serves | Size |
| --- | --- | --- |
| `Doublet`, `NodalDoublet`, `DoubletHeatPlant`, `HeatingSubstation`, `CoolingSubstation`, `ATESPlant` | building blocks | |
| `MultiWellPlant` | both | `producers`, `injectors` |
| `DistrictNetwork` | both | `consumers`, `service` |
| `HeatingPlant` | heating | `doublets` |
| `HeatingCoolingPlant`, `HeatingFullCoolingPlant`, `HeatingAbsorptionCoolingPlant`, `HeatingHeatPumpCoolingPlant` | both | `doublets` |
| `BoilerChpPlant`, `ParallelExchangerPlant`, `DistrictEnergyPlant` | cases | |

The five template plants derive from `DoubletsPlant` (`plants/_utils/doublets.py`): `size={"doublets":
n}`, 1 to 3 (`minimum_doublets`, `maximum_doublets` of the class, `invalid_design` outside), gives the
doublets `d0` to `d{n-1}` in parallel through `production_mixers` and `injection_splitters`. A
plant-level `depth` goes to every doublet, which derives its reservoir from it; a value stated on one
doublet wins, now and later. A run that starts without a geotherm raises `missing_value` naming the path. A `Doublet` with a `depth` and no geotherm waits for it instead of
raising: a plant holds the design, and the `gm.Case` the geotherm and the rest of the environment,
so `gm.simulate(plant, case)` applies them to a copy ([engine.md](engine.md#how-the-case-reaches-the-modules)).

**Schedulable or a building block.** `gm.schedule(plant, case)` plans a plant that has `Doublet` children and a
grid, and its setpoints as `inputs`:

| A plant with values plus `gm.schedule` | Status |
| --- | --- |
| `HeatingPlant`, `HeatingCoolingPlant`, `HeatingFullCoolingPlant`, `HeatingAbsorptionCoolingPlant`, `HeatingHeatPumpCoolingPlant`, and a plant dict of the same units | schedulable: a design is a plant dict, and `examples/` holds two that run with no failed step |
| `DoubletHeatPlant` | schedulable up to 165 m3/h: the measured ESP curve, which the replay goldens hold, has no head at 60 Hz for more, so the flow range constraint must stop there |
| `Doublet`, `NodalDoublet`, `HeatingSubstation`, `CoolingSubstation`, `DistrictNetwork`, `MultiWellPlant`, `ATESPlant` | building blocks: a run sets their controls and boundaries |
| `DistrictEnergyPlant`, `BoilerChpPlant`, `ParallelExchangerPlant` | cases: their examples set their inputs |

Example plants live in `tests/fixtures/plants/<Name>.json` and `examples/*/plants/`, in a source
checkout only: they are plant files of the form above (`kind: plant`, `format: 1`). The values of
nature that moved to the case are in `tests/fixtures/plant_case_values.json`, and
`example_plant(name)` of `tests/fixtures/sample_cases.py` builds the plant from its file and sets
them on the modules. The five template plants have no values of their own: a design is its plant
file. A plant with no file raises `FileNotFoundError` and a missing `tests/fixtures/` raises `inputs_missing`.

`ATESPlant` has one wiring for both seasons: the `split_fraction` of `source_valve` and `load_valve`
sends the flow to the exchanger or to the heat pump, and the one that stands still is called at zero
flow. `AquiferStorage` offers its produced stream, so its loop needs no iteration.

## Parameters by date and bindings

```python
plant.set_params("esp", {"stage_count": 14}, valid_from="2025-01-01")
plant.params_at("esp", time="2024-06-01")
plant.param_history("esp")
plant.bindable("esp")
plant.set_bindings("esp", {
    "frequency": "esp_hz",
    "fluid_in.p": {"column": "p_in", "unit": "bar"},
})
```

`set_bindings(path, bindings)` replaces the bindings of a module. A key is a declaration name: a
control, boundary, measured output or state, which are unique within a module, or `port.field` of
an inlet. A value is a column name, whose unit comes from the run input's metadata or else the
declaration's SI unit, or `{column, unit}`. A name declared twice would raise `ValidationError`
naming the clash; no shipped module has one. The plant dict holds the same flat form and reads only
that form: a section such as `controls` is an unknown name.
