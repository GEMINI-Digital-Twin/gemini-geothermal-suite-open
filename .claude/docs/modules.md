# Writing modules

A leaf module computes and a plant connects; no class does both. A module is two pure methods:

```text
forward(self, inputs, inlets, state) -> (outputs, outlets)
update(self, inputs, inlets, outlets, state, dt) -> next state      only if it has states
```

`forward` computes one step and returns its outputs and outlets; `update` returns the state at the
end of the step. Neither writes anything to `self`, which holds the parameters, set before a run
and fixed during it. Everything that changes in time arrives as an argument: `inputs` holds the
controls and boundaries by name, `inlets` is a read-only `Ports` mapping and `state` the state
the step starts from (`{}` for a module without states). Every composite is a `Plant`
([plants.md](plants.md)): it declares children, ports and connections in `__init__` and never
writes `forward` or `update`; the plant implements both once, for any graph.

Write a module with `Module` and the declarations (`Parameter`, `Port`, `Output`,
`Control`, `Boundary`, `State`) from `gemini.modules` (`gm.modules.Module`), and the quantity types
and streams from `gemini.streams`. The base class has no string catalogue, sequential
container, fidelity flag or cost method. The shipped equipment, with each model's ports, parameters, equations and energy-audit status, is
listed in [equipment.md](equipment.md); its classes are good references for new modules.

**Physics lives in `gemini/physics/`, or in a `_physics.py` only when it needs streams.** Modules
declare and wire; they never define physics. `gemini/physics/` keeps every correlation that holds
for any equipment, whatever the number of categories that use it, and what `analysis`, `study` or
`evaluate` read; it knows no `Stream` or `Fluid`. A `_physics.py` stays beside a category only for
code that needs a `Stream` or `Fluid` (today `wells/_physics.py`, the pipe path march and the
corrosion profile) or a module's own declarations (`heating/_burner.py`, `cooling/_sorption.py`
under a name that says what they are); it imports only `gemini.physics`, `gemini.ops`,
`gemini.streams` and `gemini.errors`, never another category's file. A function that takes plain
values moves into `gemini/physics/`, the right topic file. Its functions keep `@ops.physics` and
stay traceable on every backend. Reuse existing physics functions wherever possible and combine them; add
a new physics function only when nothing existing can do the job, and generalise an existing one
rather than writing a second copy. Never write a formula inside a module, and never write the same
formula twice.
Fitting and calibration belong in `gm.analysis` or `gm.study`, not in modules. A plant class
belongs in `gemini/plants/`; `gemini.modules` never imports `gemini.plants`.

**Where a file goes under `gemini/modules/`.** There are four homes:

- A file that defines a core class users subclass or build goes directly in `gemini/modules/`:
  `module.py` (`Module`), `declarations.py` (`Parameter`, `Port`, `Output`, `Control`,
  `Boundary`, `State`), `container.py` (`ModuleList`, `ModuleDict`) and `check.py`
  (`gm.modules.check`). `Plant` is `gemini/plants/plant.py`. The class `Module` is split by job:
  `callrecord.py` (the record of a call in progress and the context that holds it), `callargs.py`
  (reading the arguments of a call and the ports it returns), `states.py` (the state tree, `update`
  and `step`), `tree.py` (children, paths and the listings of declarations), `values.py`
  (setting, checking and saving design values), `display.py` (the display of values and `help`)
  and `classpath.py` (the path a checkpoint stores for a class). `results.py` is the result of a call, `call.py` `gm.call`.
- Machinery goes in an `_utils/` folder, even if some of its functions are exported publicly:
  `gemini/modules/_utils/` (`balance`, `description`, `design`, `equipment`, `trace`),
  `gemini/plants/_utils/` for the plant tools (the plant dict `serialization` among them) and `gemini/_utils/registry.py` for the registry.
- Code shared by the modules of one category that needs a `Stream` or a module's declarations goes
  in that category folder as a private file under a name that says what it is: `heating/_burner.py`,
  `cooling/_sorption.py`, `wells/_physics.py`.
- `gemini/plants/` holds only plant classes.

## Construction and metadata

Construct a module without arguments and set its values afterwards; `set_params` returns the
module, so `ESP().set_params("", {"stage_count": 12, ...})` builds a configured pump. Only structural
tree-shape arguments (for example `ModuleList(modules)`, `DistrictNetwork(consumers=3)`) go to
`__init__`. There is no
class-creation hook: `module.name` is the snake_case class name computed on access,
`Module.help()` reads the first paragraph of the class docstring and lists the declarations, and
any number of classes may share a name. `module.path` is the dotted position in the tree, or the
name for a standalone module. `module.fluid` is a validated property saved by `state_dict()`; it raises `missing_value` until the case or the plant `fluids` sets it. A module that works on a fluid takes it from its inlet stream (`self._fluid_of(stream)`: the stream's fluid, unless the module states its own, a design choice such as a plant `fluids` entry), so a call of the module alone, `gm.call` included, needs only the `fluid` of its inlets; `module.fluid` is read only where no inlet stream exists (a source, an offer). Checkpoints
store the root class as `module:qualname` through `class_path`/`import_class` in `classpath.py`, the
only import-by-string in the package.

## Registry, categories and streams

`gemini/_utils/registry.py` is the one registry of module and plant classes. A class that states a
`category` joins it under its class name when it is defined (`Module.__init_subclass__`), so every
shipped equipment class is registered when `gm.modules` is imported and a new class needs no call.
`abstract = True` in the body of a class leaves it out (`Module` and `Plant` are abstract); a
subclass does not inherit it. A second class of a registered name raises `ValidationError` (code
`duplicate_name`); defining the same class again replaces it. `gm.modules.names(category=None)`,
`get(name)` and `categories()` read the registry; an unknown name raises `ValidationError` with its
close matches in `suggestions`. A class in a file of the user is a class like any other: import the
file, and a plant dict can then name it by `type`. There is no `register` and no `load_file`.

Once a new class is written, run `gm.modules.check(cls, example=None)`. It never raises
and returns `{module, passed, checks}`, each check `{name, passed, message}` with `passed` `True`,
`False` or `None` (undecided). The checks are `is_module`, `instantiate` (the declaration rules
run in `__init__`), `category`, `forward_signature` (exactly `forward(self, inputs, inlets, state)`), `units`
(every scalar numeric parameter, control, boundary and output is declared with a quantity type
that has a unit; coefficient arrays are exempt), `describe` (plain JSON) and `call` (one
`gm.call` call). A module that needs parameters, controls or inlet streams is undecided on
`call` until `example` gives them in the shape of `gm.call`:
`{"parameters": {...}, "inlets": {...}, "controls": {...}}`.

There is one classification: a shipped module's category is the name of the folder of
`gemini/modules/` that holds its file, and a new module goes in the folder of what it does.
`CATEGORIES` of `gemini/_utils/registry.py` is the fixed list of those folders, one word each, in display order;
[equipment.md](equipment.md#overview) lists the modules of each. `Module.category` reads the folder
from the import path of the class, so a shipped class never declares it and the two cannot disagree
(`tests/unit/_utils/test_registry.py` checks the folders, the list and every class). The classes of
`gemini/plants/` read `plants`. A class from outside has no folder: it states the class attribute
`category`, one of the list, and a subclass of a shipped class states its own.

## Ports

A port is `Port(direction, *, fluid=None, energy=None, ...)`. `direction` is `Direction.IN` or
`Direction.OUT`. Exactly one of `fluid` and `energy` is given: `fluid` makes a stream port (a
`Stream`), `energy` a power port (a power in W). "Any" is the preset `Fluid.ANY` or `Energy.ANY`.
The other fields say what may be connected:

| Field | Applies to | Values | Default |
|---|---|---|---|
| `fluid` | stream port | a `Fluid` preset such as `Fluid.WATER`, `BRINE`, `GLYCOL`, `STEAM`, `AIR`, `NATURAL_GAS`, `FLUE_GAS`, `CHEMICAL`, `WASTE`, or `Fluid.ANY`; compared by `Fluid.family` | required for a stream port |
| `energy` | power port | `Energy.ELECTRICITY`, `Energy.HEAT`, `Energy.FUEL`, or `Energy.ANY` | required for a power port |
| `phase` | stream port | `Phase.LIQUID`, `GAS`, `TWO_PHASE`, `ANY` | `ANY` |
| `level` | stream port | `Level.HOT`, `WARM`, `COOL`, `CHILLED`, `AMBIENT`, `GEOTHERMAL`, `ANY` | `ANY` |
| `temperature`, `pressure` | stream port | optional `(low, high)` ranges in SI, described and not checked | `None` |
| `generic` | both | a letter such as `"T"`, see below | `None` |
| `flow` | both | `Flow.IMPOSED` (the giver decides) or `Flow.DRAWN` (the taker decides) | drawn for a single power inlet and a `many` outlet, imposed otherwise |
| `many`, `required`, `offered` | both | as described here | `False`, `True`, `False` |

```python
from gemini.modules import Direction, Flow, Level, Phase, Port
from gemini.streams import Fluid
from gemini.streams.energy import Energy

fluid_in = Port(
    Direction.IN,
    fluid=Fluid.WATER, phase=Phase.LIQUID, level=Level.HOT, flow=Flow.IMPOSED,
)
power_in = Port(Direction.IN, energy=Energy.ELECTRICITY, flow=Flow.DRAWN)
any_out = Port(Direction.OUT, fluid=Fluid.ANY)
fluid_t = Port(Direction.IN, fluid=Fluid.ANY, phase=Phase.LIQUID, generic="T")
```

A field not given is "any". Giving both `fluid` and `energy`, neither, or a phase, level,
temperature or pressure on a power port is a `DefinitionError`. A port has no `kind=` argument;
`port.kind` is still readable as a label derived from its fields, and it never changes a calculation.

**The compatibility rule.** Two ports connect when they have opposite directions and the same
kind of content (both stream or both power), and each of phase, fluid (by family), level and energy is equal on both sides or "any" on
one of them. A connection that fails it is a `stream_mismatch`.

**Generic letters.** A side of a pipe, pump, mixer, splitter or valve is `generic="T"`: what it
carries is whatever its connections carry, and the ports of one module with the same letter carry
the same thing. A heat exchanger uses `"H"` and `"C"` for its hot and cold sides, a heat pump
`"S"` for its source. The plant infers what a letter carries from the connections around it; a
letter asked to carry two different values is a `generic_conflict`.

**Checking and suggesting.** `plant.check()` returns the issues of the plant and never raises. For
ports they are `stream_mismatch` (a connection whose ends are not compatible once the generic
letters have taken their values), `generic_conflict` and `unconnected_port` (a required port with
no connection). `plant.suggest(port=None, *, free=True, loose=True, limit=None)` lists the ports a
port may connect to, best first, as `Suggestion(port, match, exact, loose, closes_loop)`. `port` is
a `"path.port"`, a bound port or a module (a module gives a dict of lists); without it the
suggestions are for every unconnected required port. `match` is `Match.EXACT` when every field is
equal and `Match.LOOSE` when some matched through "any" or a generic letter, `exact` and `loose`
list the fields of each kind, and `closes_loop` is true when the two modules are connected the
other way already. The order is exact matches, then more equal fields, then a port that closes a
loop; there is no score. `free=False` includes ports already connected, `loose=False` keeps the
exact matches only. `plant.connect(end, suggestion)` accepts a suggestion in place of a target.

```python
import gemini as gm
from gemini.modules.piping import Pipe
from gemini.modules.pumps import CirculationPump

plant = gm.Plant()
plant.add(CirculationPump, "pump")
plant.add(Pipe, "pipe")
found = plant.suggest("pump.fluid_out")
plant.connect("pump.fluid_out", found[0])
print(found[0].port.path, found[0].match, plant.check()[0].code)
```

`many=True` lets several ports connect to one port; its value is the list of what arrives, and the module sums it with an explicit
function (`energy.total_power`). A `many` port may stay empty.function (`energy.total_power`). A `many` port may stay empty.

A plant runs its modules in the order the values travel, and on some connections the value travels
against the energy, because the module that receives the energy decides how much it takes:

- **A drawn port.** A single `Power` inlet is drawn: a call needs no value for it, `forward` computes
  it and returns it under the name of the port, beside the outlets, and `result.inlets.power_in`
  shows it. A stream inlet is drawn with `Port(Direction.IN, fluid=Fluid.ANY, flow=Flow.DRAWN)`: it receives the conditions the
  source offers and `forward` returns the stream it took. A `many` outlet is drawn, as is any
  outlet with `flow=Flow.DRAWN`: the module receives what its takers drew under the name of the outlet
  (`inlets.power_out` in `forward`). The taker runs before
  the source. The drawn values are returned in the `outlets` dict of `forward`, with the outlets.
- **An offered outlet.** `Port(Direction.OUT, fluid=Fluid.ANY, offered=True)` exists before the other modules run. Its
  module defines `_offer(self, inputs, inlets, state)`, pure like `forward` and reading
  parameters, its inputs, its state and the inlets it names in `offer_inlets`; the plan gives the
  module one offer step and one call. A forward that needs the offer calls
  `self._offer(inputs, inlets, state)` itself and writes nothing. This is how an
  edge module both feeds modules and receives from them without a cycle, and how a connection back
  to such a module is no loop. A direct call that leaves a drawn outlet out gets its offer, and one
  that leaves out a `many` port an empty list.

A sub-plant exposes one port for what several children share: `plant.connect("power_in",
"esp.power_in")` twice, or `"inlets": {"power_in": ["esp.power_in", "pump.power_in"]}` in the plant dict.
Its value is the sum of what the ends carry (`energy.total_power`), so from outside a sub-plant reads
like a leaf. Several ends may share a plant port that carries a power or air, never a plain stream.

## Describing a module

`describe()`, `parameter_schema()` and `validate_params(params)` are instance methods: a module's
declarations exist only once `__init__` has run, so a class answers through a new instance,
`gm.modules.ESP().describe()`. They live in `gemini/modules/_utils/description.py`, return plain
JSON (`json.dumps(..., allow_nan=False)`) and never change the module.

`describe()` returns `{name, type, category, summary, doc, parameters, controls, boundaries,
measured, state, inlets, outlets, outputs, children, connections, values}`:

- `name` is `module.path`, `type` the class name (a plant shows its given name), `summary` the
  first paragraph of the docstring and `doc` all of it.
- `parameters`, `controls`, `boundaries`, `measured` and `state` map a name to `{type, unit,
  quantity, default, minimum, maximum, enum, description, section}`. A missing item is `null`;
  `default` is `null` for `UNSET`. `type` is the JSON type of the value: `array` for a list (the
  sections of a well path, `section_length`), given as `{"value": [400, 150], "unit": "m"}` with one
  unit for the list; `unit`, `quantity`, `minimum` and `maximum` then hold for each item. `minimum` and `maximum` are the closest limit, so a strict bound
  (`gt`, `lt`) shows as the bound itself. `enum` comes from a `Literal`. Only the module's own
  declarations are listed; children appear under `children`.
- `measured` lists every output of the module itself: replay (`engine/bindings.py`) takes a measured
  binding for any output name and compares it with that output; no narrower rule exists.
- `inlets` and `outlets` map a port to `{kind, fields: {m_dot: {unit: "kg/s"}, T: {unit: "K"},
  p: {unit: "Pa"}}}`; `kind` is `null` for a port that takes any stream.
- `outputs` maps a name to `{unit, quantity, soft_sensor}`; `quantity` is the quantity name
  (one of the nine) or `null`.
- `children` is `{name: type}` and `connections` is `[{source, target, kind, type}]`, both empty
  for a leaf. A plant exposes its wiring through `_connection_list()`.
- `values` holds the current `parameters`, `controls` and `boundaries`; unset ones are left out
  and a child's values are keyed by dotted path.

`parameter_schema()` is JSON Schema draft 2020-12: `$schema`, `title`, `type: object`,
`properties`, `required` (parameters with no default) and `additionalProperties: false`. A child's
parameters appear under their dotted path. Each property has the standard keywords (`type` or
`anyOf`, `minimum`, `maximum`, `exclusiveMinimum`, `exclusiveMaximum`, `enum`, `default`,
`description`) plus `unit` and `quantity`. A number with a unit is `anyOf` number and string,
because inputs accept `{"value": 150, "unit": "m3/h"}`; a list with a unit is `anyOf` array and
the object `{"value": [numbers], "unit"}`.

`validate_params(params, on_error="raise")` checks every entry and raises one `ValidationError` that
carries every problem; with `on_error="record"` it returns them, each
`{path, code, message, suggestions}`. `path` is the parameter name; the codes are `unknown_name` (with `suggestions`),
`invalid_unit`, `out_of_bounds` and `invalid_value`. It runs `declaration.validate` once per entry
and tells the failures apart by the exception and its cause. The message of a list with a unit
(a bare list, a single number, no unit or a wrong one) shows the value as given and asks for
`{'value': [<number>, ...], 'unit': <unit>}` with the units of its quantity; in a plant file a wrong
or missing unit of a list is one `unit` issue at `<path>.unit`, not one per item.

## Listing declarations

Every declaration listing takes `recurse` with default `True` and keys its result by dotted path
relative to the module (`"doublet.esp.frequency"` from the root): `parameters()` and
`named_parameters()` iterate, and `controls()`,
`boundaries()`, `inputs()`, `outputs()` and `soft_sensors()` return dicts. Pass `recurse=False`
for the module's own declarations under their local names. `inlets()` and `outlets()` take no
`recurse`: a child's ports are internal connections, not ports of the parent.
`children()`/`named_children()` list direct children and `modules()`/`named_modules()` walk the
tree. `get(path)` returns the declaration at a dotted path, whatever its kind, and
`get_submodule(path)` the module; both suggest a close match for a typo.

## Leaf modules

A leaf computes once, in `forward(self, inputs, inlets, state)`: it calls physics and returns two
dicts, `outputs` (a key for each declared output) and `outlets` (a key for each outlet it gives and
each inlet it draws). A missing or an extra key is a `DefinitionError` naming the module and the
key. Parameters are read on `self`; the controls and boundaries are `inputs["frequency"]`, never
`self.frequency`, which is refused inside a call.

```python
from gemini.modules import Control, Direction, Module, Output, Parameter, Port
from gemini.physics import pumps
from gemini.streams import Fluid, Stream
from gemini.units.quantities import (
    Count, Electricity, Frequency, Power, PressureDifference, VolumeFlow,
)


class Pump(Module):
    """Example fluid pump."""

    def __init__(self):
        super().__init__()

        # Parameters
        self.stage_count = Parameter(Count)
        self.head_coefficients = Parameter(list[float], shape=(6,))
        self.power_coefficients = Parameter(list[float], shape=(6,))

        # Inlets
        self.fluid_in = Port(Direction.IN, fluid=Fluid.ANY)

        # Controls
        self.frequency = Control(Frequency)

        # Outputs
        self.flow = Output(VolumeFlow)
        self.head = Output(PressureDifference)
        self.power = Output(Power)
        self.electricity = Output(Electricity)

        # Outlets
        self.fluid_out = Port(Direction.OUT, fluid=Fluid.ANY)

    def forward(self, inputs, inlets, state):
        """Raise the suction pressure."""
        frequency = inputs["frequency"]

        # Outlets
        suction = inlets.fluid_in
        flow = suction.volumetric_flow()
        curve = sum(c * flow**i for i, c in enumerate(self.head_coefficients))
        head = self.stage_count * (frequency / 60.0) ** 2 * curve
        discharge = suction._with_si(p=suction.p + head)

        # Outputs
        power = pumps.power(flow, frequency, self.stage_count, self.power_coefficients)
        outputs = dict(flow=flow, head=head, power=power, electricity=power)

        outlets = dict(fluid_out=discharge)
        return outputs, outlets
```

Do not cache call data on `self`: it belongs in a local variable of `forward`. Under
`gm.modules.no_outputs()` the outputs are still returned; nothing validates them and the result
drops them. The tests enforce the rule: `tests/fixtures/purity.py` runs `forward` and `update` and
fails when `self` or a child changed afterwards, and `tests/unit/test_purity.py` applies it to every
registered class.

## Plants

A composite is a `Plant`: its shape, connections, loops, constraints and outputs are in
[plants.md](plants.md). `module.is_leaf` is true exactly when the module has no registered
children. Composites built from a variable number of children use the containers
`ModuleList(modules)` (children named `"0"`, `"1"`, ...; inserting or removing renumbers the later
children) and `ModuleDict(mapping)` (caller-chosen keys that must not shadow module or mapping
attributes). Containers compare and hash by identity like every module.

### A plant that sets its children's values

A plant may derive its children's parameters from its own. It overrides `_set_si_params`, which
receives SI values, computes the child values with functions from `gemini/physics/` and calls
`super()._set_si_params` with them. `set_params` is the public door: it refuses a bare number with a
dimension, converts the quantities to SI and calls `_set_si_params`. Never override `set_params`:

```python
from gemini.modules import Parameter, ProductionReservoir
from gemini.physics import hydraulics
from gemini.plants import Plant
from gemini.units.quantities import Density, Length


class Column(Plant):
    """A reservoir whose pressure comes from the height of its water column."""

    def __init__(self):
        super().__init__()

        # Modules
        self.reservoir = ProductionReservoir()

        # Parameters
        self.height = Parameter(Length | None, default=None)
        self.density = Parameter(Density | None, default=None)

    def _set_si_params(self, path, params, valid_from=None):
        """Derive the reservoir pressure, unless the same call states it."""
        if path:
            return super()._set_si_params(path, params, valid_from)
        values = self._own_values(params, valid_from)
        derived = {}
        if values["height"] is not None and values["density"] is not None:
            pressure = hydraulics.hydrostatic_dp(values["density"], values["height"])
            derived["reservoir.pressure"] = pressure
        return super()._set_si_params("", self._keep_derived(derived, params) | params, valid_from)
```

`_own_values(params, valid_from)` gives the module's own values in force at that date with the ones
of this call, in SI, so a dated call derives from the design of its date. A value that has not been
given yet derives nothing: the values may arrive one call at a time. `_keep_derived(derived, params)`
does the bookkeeping: an explicit child value in the call wins, now and in later calls
(`{"depth": {"value": 3000, "unit": "m"}, "well.section_length": [2600.0], ...}` keeps the given pipe path), and it records the names
it keeps.

Every route that sets parameters reaches this method: `add(..., params=)`, `from_dict`,
`set_params(path, ...)` at any depth, a dated `set_params(..., valid_from=)`, a `param_history`
section and attribute assignment (a bare SI number, author-level). Setting the fluid of a plant passes it to every child and derives
again.

All of this is done once, in `Plant`: the formulas go into physics (`gemini/plants/_utils/doublet_design.py`) and
the plant keeps a short `_set_si_params`. `to_dict` stores the plant's own parameters and the explicit
child values, never a derived value: `from_dict(p.to_dict())` derives them again and rebuilds the
same numbers. Dated entries of a child that only hold derived values are left out in the same way.

## Values

Parameters, controls and boundaries are set by attribute assignment or in bulk:

- `set_params(path, params, valid_from=None)` validates parameters by local or dotted name, takes a
  quantity (`Quantity` or `{"value", "unit"}`) for every value with a dimension and refuses a bare
  number for it (`invalid_value`), converts to SI and stores them (`_set_si_params` is the private
  SI path of `gemini` itself), in the undated base entry or from a date on, and returns the module; `params_at(path,
  time)` returns the values active at an instant.
- `module.frequency = 50` persists one control or boundary, and `module.stage_count = 12` sets a
  parameter as an override that wins over every date.
- `check()` lists the uninitialized parameters as `missing` issues (path, quantity, accepted units,
  meaning) and
  `is_initialized` is true when there are none. A run, `size` or a read of an unset value raises
  `missing_value` listing every missing path with its description at once (`problems` holds one
  item per path). Every `Parameter`, `Control`, `Boundary` and `Output` declares a short
  `description` of its physical meaning, never a default; a quality test enforces it.
- `state_dict()` returns JSON-safe parameter values and the fluid of every module path, and
  `set_state_dict(state, strict=True)` validates all of them before applying any. With
  `strict=False` only the modules named in `state` are filled; unknown paths are always rejected.
  `to_dict()`/`from_dict()` and `save(path)`/`load(path)` of a `Plant` add dated histories,
  overrides, bindings and boundary defaults; a single module is stored by wrapping it in a plant.

```python
curve = [1, 0, 0, 0, 0, 0]
pump = Pump().set_params(
    "", {"stage_count": 10, "head_coefficients": curve, "power_coefficients": curve}
)
pump.frequency = {"value": 50, "unit": "Hz"}
```

## Calling modules and `Ports`

Keyword, mapping and positional inlet calls are equivalent. Positional streams follow inlet
declaration order; controls and boundaries remain optional call keywords that apply to this call
only. Do not combine an inlet mapping with inlet keywords.

```python
import gemini as gm

stream = gm.Stream(flow={"value": 150, "unit": "m3/h"}, T={"value": 80, "unit": "C"}, p={"value": 20, "unit": "bar"}, fluid=gm.BRINE)
a = pump(fluid_in=stream, frequency={"value": 50, "unit": "Hz"})
b = pump({"fluid_in": stream}, frequency={"value": 50, "unit": "Hz"})
c = pump(stream, frequency={"value": 50, "unit": "Hz"})
assert a.outputs.head == b.outputs.head == c.outputs.head
assert a.outputs.get("head", unit="bar") == a.outputs.head / 1e5
```

`inlets` and `result.outlets` are immutable `Ports`. They preserve
declaration order and support both `ports.fluid_in` and `ports["suction"]`. Unknown names report
the module path, valid names and a close-match suggestion. A call returns a `ModuleResult` with
`outputs` (a `Values` mapping whose `get(name, unit=...)` converts from the declared unit),
`outlets`, `inlets`, the resolved `inputs` and the `children` results of the call.

## Call order and hooks

One call performs these steps:

1. validate inlets and resolve controls and boundaries into `inputs` (call keyword, value set before
   the run, default), and the state into `state` (the keyword `state=`);
2. run forward pre-hooks;
3. run `forward`, check the keys of the outputs and outlets it returned, validate the outlets;
4. record the outputs, validated;
5. run forward hooks;
6. verify every output was returned and build `ModuleResult`.

A value set before the run, `pump.frequency = Quantity(50, "Hz")` or `set_inputs`, stays a pre-run
value on the module, a `Quantity` at the door and SI inside. A call and the engine pour it into
`inputs`; a keyword of the call, or a column of the plan, wins. `forward` never reads it from
`self`.

Pre-hooks always receive `(module, inputs, inlets, state)` and forward hooks always receive
`(module, inputs, inlets, state, outputs, outlets)`, the arguments of `forward` and its results.
A hook returns `None` or a mapping: a pre-hook's mapping replaces those controls and boundaries
for this call, a forward hook's mapping replaces those outputs:

```python
def clamp(module, inputs, inlets, state):
    return {"frequency": min(inputs["frequency"], 45)}


def lose(module, inputs, inlets, state, outputs, outlets):
    return {"power": outputs["power"] / 0.9}


pre_handle = pump.register_forward_pre_hook(clamp)
handle = pump.register_forward_hook(lose)
clamped = pump(fluid_in=stream, frequency=50)
assert clamped.inputs["frequency"] == 45
pre_handle.remove()
handle.remove()
```

Any non-fixed hook signature fails at registration with a `DefinitionError`; a name the mapping
does not declare, or a return of another kind, fails the call. Remove a hook with
`handle.remove()`; removing twice does nothing. A hook changes only the running call.

A pre-hook makes its module a graph break, and so does a forward hook that returns nothing: the
tracer calls such a hook once on traced values to classify it, then the module runs for real, row
by row, hooks included. A forward hook that returns outputs is part of the graph. `EventLog`
registers no hook: it reads the results of each tick.

## Per-call values

The values of one call (resolved controls and boundaries, the state, the outputs and the results of
child calls) live in one `CallRecord` held in a context variable while the call runs; it is the
only per-call state and the module holds none. Attribute access on a module returns parameter values
(the call record's parameter values while a call runs, which is how the compiler passes traced
ones and how a batch of trials can share one plant), the value a control or boundary was set to
before the run, and port declarations. Inside a call of a converted module a control, a
boundary, a state or an output is not read from `self`, and none is assigned: the error names the
module and the value. Child calls made from pre-hooks are recorded on the module whose call is
running. A module keeps no result after the call returns: use the returned `ModuleResult`, which
also holds the `state` the call started from.

## Traced calls

While `gemini.compiler` traces a module, its `CallRecord` carries the running `Trace` (`call.trace`) and a
child call made inside it is recorded in the graph by `Trace.child` instead of evaluated: the child's controls, boundaries
and numeric parameters become graph inputs named `<path below the root>.<name>`, supplied keyword
values win without validation, and the `ModuleResult` of traced values joins the parent's call
records, so the combinations of a plant and `ModuleResult.leaves()` work
unchanged. `Output.ratio` is `where(bottom == 0, None, top / bottom)` with the division written as
`ops.truediv`, which gives `None` on plain floats. A leaf child that
has a pre-hook, has a read-only hook, raises `TraceError` or is stateful in a call that is not
stepped becomes one **break node**: the graph is rolled back to where the child call started and the
child runs on the plain path (`module(**row)`, hooks included) once per row while the
graph is evaluated, its outputs and outlet fields being `break_output` nodes. The outlet fluids
come from one probe of `forward` on representative inlets; a row with another fluid fails. A
failed row is NaN and carries an error code that raises the child's own exception. A composite
child that cannot be recorded makes the whole root a graph
break (`graph.breaks` lists the leaf breaks with their reasons). A stateful module in a stepped
call is no break: it is the body of a `scan` node (native-engine.md, Scan).

An output of a list or tuple of traced values (the per-section profiles of the wells) is a vector
output of fixed length: `Graph.output` records each item as `<name>[<index>]`, `graph.vectors`
keeps the length, and `gemini.compiler.run.run` returns one array of shape `(rows, length)`.

A traced call is not validated, so the tracer adds the validation as graph checks. For every
traced call (children included, break nodes excepted) each control, boundary and output with
bounds (`Declaration.limits()`: `ge`/`gt`/`le`/`lt` read once from the quantity metadata and the
declared bounds, applied to each item of a list; an `X | None` kind lets NaN pass) gets an
`ops.check` raising `ValidationError`, and the root inlets carry the `Stream` limits (finite
`m_dot`, `T > 0`, `p >= 0`). These checks are attached to every graph output, so a row that
violates a bound fails even where the arithmetic never reads the bad value.

## Skipping outputs

`gm.modules.no_outputs()` is a nestable, context-local context manager and decorator. It skips validating
what `forward` returns, the combinations of a plant, forward hooks and the check of the output keys.
`forward`, pre-hooks and outlet validation still run; the result has an empty `outputs` mapping.

```python
with gm.modules.no_outputs():
    fast = pump(fluid_in=stream, frequency={"value": 50, "unit": "Hz"})

assert dict(fast.outputs) == {}
assert fast.outlets.fluid_out == a.outlets.fluid_out
```

## State and health

Stateful equipment declares its carried values as `State(kind)` in the `# States` section, with its
quantity and a description like a parameter, and **no default**: the case states where a run starts
(`case.initial_state`, see [inputs.md](inputs.md)) and `gm.check` lists a stateful module the case
does not state as a `missing` issue. `forward` takes the state at the start of the step in its
`state` argument; a stateful leaf also implements `update(self, inputs, inlets, outlets, state, dt)`,
which returns the state at the end of the step, a key for each declared state and no more. Both are
pure. A state is never assigned and never read from `self`. A value that means "none yet" is a
value, not `None`: the PID controller's `previous_step = 0` is "no previous step", so the module
traces. `module.stateful` is true when a module declares states (a plant also when a connection is of type
`state`), and `states(recurse=True)` lists
them by dotted path.

The state of a plant is the nested dict of the states of its children, by child name, for example
`{"storage": {"temperature": 330.0}}`; a stateless module has `{}`. `module(..., state=tree)` calls a
module from a state, and a stateful module called without one raises `missing_value` naming it.
`step(state, dt, inlets)` returns `(next_state, result)` for any module: it calls the module with
`state` and then runs `update` of every stateful module the call reached, on the values of that
call. `Plant.update(inputs, inlets, outlets, state, dt)` does the same from the plant's own
arguments, calling the children again. A stateful module called twice in one step raises
`ValidationError`. The engine integrates these steps; see [engine.md](engine.md). The shipped
stateful leaves (`ThermalDecline`, `AquiferStorage`, `BoreholeField`, `ThermalStorage`,
`IceStorage`, `PIDController`) and how each integrates over `dt` are described in
[equipment.md](equipment.md).

```python
from gemini.physics import heat_transfer
from gemini.modules import State
from gemini.units.quantities import Power, Temperature


class Tank(Module):
    """Mixed tank whose temperature follows the inlet."""

    def __init__(self):
        super().__init__()

        # Parameters
        self.heat_capacity = Parameter(float, gt=0)

        # Inlets
        self.fluid_in = Port(Direction.IN, fluid=Fluid.ANY)

        # States
        self.temperature = State(Temperature)

        # Outputs
        self.duty = Output(Power)

        # Outlets
        self.fluid_out = Port(Direction.OUT, fluid=Fluid.ANY)

    def forward(self, inputs, inlets, state):
        """Leave at the tank temperature of the start of the step."""

        # Outlets
        outlet = inlets.fluid_in._with_si(T=state["temperature"])

        # Outputs
        outputs = dict(duty=self._duty(inlets.fluid_in, state))

        outlets = dict(fluid_out=outlet)
        return outputs, outlets

    def update(self, inputs, inlets, outlets, state, dt):
        """Return the temperature at the end of the step."""
        heat = heat_transfer.heat_rate(self._duty(inlets.fluid_in, state), dt)
        rise = heat_transfer.temperature_change(heat, self.heat_capacity)
        return {"temperature": state["temperature"] + rise}

    def _duty(self, inlet, state):
        return heat_transfer.heat_rate(inlet.heat_capacity_rate(), inlet.T - state["temperature"])


tank = Tank().set_params("", {"heat_capacity": 4.2e5})
state, result = tank.step({"temperature": 300.0}, 60, {"fluid_in": stream})
assert result.outlets.fluid_out.T == 300 and state["temperature"] > 300
```

A module with a diagnostic model overrides `health(self, result, measured)`. It receives the
call's `ModuleResult` and the measured outputs of that tick and returns a `Health` (`assessed`,
`score`, `alarm`, `message`, `metrics`); the base method returns `None`, which the engine records
as `assessed=False`. A module that is equipment defines `cost_size()`, the size its cost scales with, and a kind; `gm.evaluate` prices it;
see [types.md](types.md#profiles-and-costs).

## Energy flow

Everything in the plant's energy and mass flow is a module; everything that crosses between modules
goes through a port.

```text
 ElectricityGrid --power_out--> power_in  ......................
 GasGrid --gas_out--> GasMakeup --fuel_out--> Boiler ---flue_out--> Atmosphere.gas_in
 ChemicalGrid --chemical_out--> InhibitorDosing    |
 Atmosphere --air_out--> air_in (Pipe, Cooler)     +---loss_out--> Atmosphere.heat_in
                                                           wells --> Formation.heat_in
 reservoir --> wells --> treatment --> exchangers --> wells --> reservoir
                             |
                             +---waste_out--> WasteGrid
 HeatingGrid.return_out --> heat pump, boiler --> HeatingGrid.supply_in
 CoolingGrid.return_out --> chiller           --> CoolingGrid.supply_in
```

- **Edge rule.** The grids (`ElectricityGrid`, `GasGrid`, `HeatingGrid`, `CoolingGrid`, `WasteGrid`,
  `ChemicalGrid`) and the environment (`Atmosphere`, `Formation`) are the plant's edge. A plant
  total is read from their ports (`gm.evaluate.totals`), never summed by a parent;
  `gm.evaluate.plant_balance` closes the root on them. The aquifers are the one other open boundary.
- **Supply rule.** A root plant has no plant port (`root_plant_port`): what it buys comes from a
  grid, and an unconnected inlet is `unconnected_port`. A registered plant is a building block and
  has plant ports. Nothing supplies itself: there is no default fuel, power or air.
- **Port rule.** A port's name is `<role>_in` or `<role>_out`; its `kind` labels what it carries. A
  value that travels back to its source goes by who decides it: a single `Power` inlet is drawn, a
  `drawn=True` inlet shows what the module took of what was offered, and an `offered=True` outlet
  exists before the modules around it run. A `many` port takes the list of what is connected.
- **Output rule.** An output holds only what is on no port ([types.md](types.md#port-quantities)).

## Structure

Constructor sections of a leaf are ordered `Modules`, `Parameters`, `Inlets`, `Controls`,
`Boundaries`, `States`, `Outputs`, `Outlets`, with empty sections omitted; those of a plant are in
[plants.md](plants.md#a-plant-class). `forward` uses `# Outlets` when outlets exist and `# Outputs`
when it returns outputs, in that order. It writes nothing to `self` and ends with
`outlets = dict(...)` followed by `return outputs, outlets`. Method order is `__init__`, `forward`,
`update` when the module has states, then private helpers. The signature is always
`forward(self, inputs, inlets, state)`, including modules with no ports; parameters have no defaults
or variadic forms.

A port carries a `Stream` or a `Power`. What crosses a port is shown by the port, see
[types.md](types.md#port-quantities). Results keep the same dotted
`<module path>.<name>` addressing scheme. Port, control and output names follow the naming rule
in [conventions.md](conventions.md#naming).
