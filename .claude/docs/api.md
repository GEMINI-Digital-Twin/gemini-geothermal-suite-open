# Public API

Use `import gemini as gm`. This page lists **every public name** at `gm.__version__ = "0.5.1"`, and
is the page the other repositories build against. Names not listed here (a helper method such as
`Results.commit`, anything in `gemini._utils`, any import of an internal path such as
`gemini.engine.results`) are internal and may change. `tests/unit/test_public_api.py` pins the
names, their parameter names and the schema files, and `tests/integration/test_return_shapes.py`
walks the returns of this page against their schemas. Every name here is real: a feature is added to
this page when it is built (the planned ones removed are in [refactor-notes.md](refactor-notes.md#planned-features-removed-from-the-api)).

Conventions on every entry:

- Results are deterministic: the same input gives the same numbers on every backend.
- A value with a unit is a `gm.units.Quantity` or its dict `{"value": 150, "unit": "m3/h"}`; text such as `"150 m3/h"` is never accepted, and a bare number for a value with a dimension raises `ValidationError` `invalid_value` at every public door (see [Units](#units)). Outputs are in SI by default.
- A plant and an engine are not shared across threads: each worker loads its own.
- Readers are `from_<format>` and writers `to_<format>`: `from_csv`, `from_json`, `from_dict`,
  `from_values`, `from_bytes`, `from_npz`, `to_json`, `to_dict`, `to_bytes`, `to_npz`. No `read_*`,
  `write_*`, `load_*`, `save_*`, `parse_*` or `dump_*` name is public.
- The documents exchanged between repositories have a JSON Schema and a sample in `docs/schemas/`:
  `value`, `problem`, `check`, `module_description`, `plant`, `case`, `economics`, `study`, `results_summary`, `profile`
  (`<name>.schema.json`, `<name>.sample.json`). Regenerate with `python scripts/write_schemas.py`.
  The schema `problem` is the shape of one error or failed row; it is not an input, and the input of
  a run is a `gm.Case` (`gm.Case.schema()`). The shape keeps the name `problem`.

## Return shapes

Every public return that carries data uses only three shapes, defined once in `gemini/units/shapes.py`
and built by one helper each, so no module assembles them by hand. The JSON form of a return is
plain: no NumPy types, NaN and infinity are `null` (`gemini._utils.jsonable.to_plain`), and
`json.dumps(to_plain(result), allow_nan=False)` works. `gm.call`, `Results` and `gm.analysis` return
that plain JSON. A result of `gm.evaluate` and `gm.study` is a `gm.units.Quantity` in SI (a
`Value`, below), and `to_plain` turns it into the dict `{value, unit}`.

1. **Value** `{value, unit}`. `value` is a number, an array or `null`; when it is `null`, a `reason`
   key says why. The key is `value` for arrays too. A time series is a value with a `time` key
   beside it: `{time, value, unit}`. Statistics are `{min, max, mean}`, each a value. An output that
   is a flag or a text keeps its boolean or string. An economics value adds the parts of its result
   as more keys, each a value or a text. In Python a result of `gm.evaluate` or `gm.study` is a
   `Value`, a `Quantity` with a `reason` and the `parts` of the result: `lcts(...).value`,
   `.unit`, `.to("EUR/MWh")`, `.parts["heat"]`. Money is in the unit `currency` (`currency/J`,
   `currency/yr`), whatever `economics.currency` of the case labels, and a year is `yr`.
2. **Problem** `{path, code, message, suggestions}`, for every error, validation result and failed
   run row. A run row adds `time`. There is no `class` key: `code` is the stable key for machines.
3. **Check** `{name, passed, value, limit}`, where `value` and `limit` are values. A failed check is
   an answer, not an error. `passed` is `null`, with the reason in `value`, when there is nothing to
   judge.

A number always travels with its unit in the same dict: there is no separate `units` map. Counts of
skips by reason (`skip_counts`, `reasons`) and the state trees of `end_state` are the input of a next
call or plain tallies, not values. Public returns are plain dicts: a DataFrame comes only from a
method named `to_frame`, the one exception being run input (`gm.case.from_csv`, `from_values` and
`gm.schedule`), because the run-input format is a DataFrame. Text comes only from `help()` and
`summary()` of a plant, meant for people.

## Output units

Outputs stay SI by default. Every call marked *units* below takes an optional `units` argument, a map
from quantity to unit: `results.get("hx", "duty", units={"power": "MW"})`. Conversion uses `gm.units`
only, on the way out; nothing inside the run changes, and the returned `unit` keys say the unit
actually used (`frame.attrs["units"]` on a table). A key reaches the quantities of its family, the
first quantity defined with the same SI unit leading it: `power` reaches `duty`, `electricity` and
`heat_loss`, `pressure` a pressure difference, `temperature` a temperature difference. A key of the
quantity itself wins. A difference converts by scale only. An unknown quantity, or a unit that does
not fit it, raises `ValidationError` with suggestions.

### Display units

Every return that shows a number to a person converts through one table, `DISPLAY_UNITS` of
`gemini/units/display.py` (quantity to unit: MW, MWh, degC, m3/h, kt, MEUR, ...), and the metric
names of `gemini/evaluate/_utils/display.py` on top of it. It serves `report.to_dict()`,
`Best.to_dict()`, `Sample.to_dict()`, the history of a search, the notes of `gm.study.size` and
`gm.call(..., units="display")`. The rules, the same everywhere:

- A quantity the table does not list (a pressure in Pa, say) stays in SI.
- A difference keeps its SI unit: a temperature lift or an approach is in K, not degC. A study result
  that holds one lists its names under `differences`, so `from_dict(to_dict())` reads it back
  unchanged; the names whose last part is `analysis_period` or `payback` are durations in yr.
- A value already in its display unit is not converted again, so a second `to_dict` is exact.
- Converted back to SI, a display result equals the SI result (the table only scales).

## Freeze rule

`gm.__version__` is the one version of the package, read from `version` in `pyproject.toml`.
From 0.5.0 the API is backward compatible and additions are allowed if they break nothing: no name,
parameter (name, kind, default, order), output field, code, schema key or behaviour that exists in
0.5.0 changes, and the module-author contract (`forward`, `update`, `State`) stays; what the
competition runs stays exactly the same ([conventions.md](conventions.md#public-api-freeze)). An
addition or a fix raises the patch number (`0.5.2`). Every change has a line in the change log
below, in the same commit. `tests/fixtures/public_api_0_5_0.json` is the frozen 0.5.0 surface,
written once and never regenerated; `tests/fixtures/public_api.json` is the working snapshot with
its hash per version in the test.

**Names kept on purpose.** `gm.evaluate.call_energy_balance`, `call_mass_balance`, `collect_flows`
and `call_emissions` keep their `call_` prefix: they audit one `gm.call` result (a module or a
plant, no case), unlike `energy_balance(plant, case, results)`, which judges a run. The `gm.ops`
names are the math API that module authors write physics with; they are not internal and do not
change.

**Module catalogue.** Adding, removing, moving or renaming modules is never a version matter. The
snapshot covers the package API (functions, types, return shapes), not the list of modules.

## Package

`gemini/__init__.py` exports exactly the names below, as `gm.__all__`; `gm.__version__` is an
attribute and not in `__all__`. Every folder exports its public names flat, `gm.<folder>.<Name>`,
from its own `__init__`; the files inside a folder are private.

| Name | Returns | Status |
| --- | --- | --- |
| `gm.__version__` | text, the version in `pyproject.toml` | real |
| `gm.Module`, `gm.Parameter`, `gm.Inlet`, `gm.Outlet`, `gm.Output` | see [modules.md](modules.md) | real |
| `gm.Plant` | see [plants.md](plants.md) | real |
| `gm.Stream`, `gm.Fluid`, `gm.BRINE`, `gm.WATER` | see [types.md](types.md); `Stream(m_dot=, T=, p=, fluid=)` and `Fluid(...)` take quantities for what has a dimension | real |
| `gm.Case`, `gm.Study` | see [Case](#case) and [Evaluate and study](#evaluate-and-study) | real |
| `gm.schedule`, `gm.check`, `gm.simulate`, `gm.replay`, `gm.live`, `gm.resume`, `gm.call` | see [Running](#running) | real |
| `gm.Results`, `gm.Dataset`, `gm.Engine` | see [engine.md](engine.md) | real |
| `gm.modules`, `gm.plants`, `gm.case`, `gm.physics`, `gm.ops`, `gm.runtime`, `gm.units`, `gm.errors`, `gm.streams`, `gm.study`, `gm.evaluate`, `gm.analysis`, `gm.compiler` | the folders, below | real |

Not at the top: `gm.Clock` is `gemini.engine.Clock`; `Control`, `Boundary` and `State` are
`gm.modules.Control`, `Boundary` and `State`; `gm.Quantity` is `gm.units.Quantity`; `Ports`,
`Profile` is `gemini.case.profile.Profile` and the stream names (`kinds.names()`) are in `gemini.streams.kinds`. There is no `core`,
`base`, `registry`, `testing`, `backends`, `checks`, `economics`, `profiles`, `utils` or `graph`
folder at the top.

## Modules and streams

| Name | Returns | Status |
| --- | --- | --- |
| `gm.modules.names(category=None)` | sorted registry names; plant classes have category `plants` | real |
| `gm.modules.get(name)` | the class. Unknown: `ValidationError` with `suggestions` | real |
| `gm.modules.categories()` | `subsurface`, `wells`, `pumps`, `treatment`, `exchangers`, `heating`, `cooling`, `power`, `storage`, `piping`, `grids`, `environment`, `control`, `plants`, in display order; each is the folder that holds the module | real |
| `gm.modules.<Equipment>`, `Module`, `ModuleList`, `ModuleDict`, `trace_wiring` | classes, see [equipment.md](equipment.md) | real |
| `gm.modules.Parameter`, `Control`, `Boundary`, `State`, `Inlet`, `Outlet`, `Output`, `no_outputs()` | the declarations of a module class, see [modules.md](modules.md) | real |
| `gm.modules.check(cls, example=None)` | for developers of a new module class only: a report, never raises; `example` goes through `gm.call`, so a value with a dimension is a quantity | real |
| `gm.modules.Boiler`, `ElectricBoiler`, `CHP`, `Flare`, `GasGrid`, `GasMakeup` | the gas chain: `boiler.fuel_in`, `boiler.gas_out`, see [equipment.md](equipment.md) | real |

A class that states a `category` registers itself when it is defined (`Module.__init_subclass__`);
`abstract = True` in its body leaves it out. A second class of a registered name raises
`ValidationError` (code `duplicate_name`). There is no `register` and no `load_file`.

On an instance of `Module`; a class answers through a new instance, `gm.modules.ESP().describe()`:

| Name | Returns | Status |
| --- | --- | --- |
| `describe()` | see below; schema `module_description` | real |
| `parameter_schema()` | JSON Schema draft 2020-12; each property has `unit`, `quantity`; dotted child names | real |
| `validate_params(params, on_error="raise")` | `[]`, or raises every problem; with `"record"` the list of problems; a bare dimensioned number is one problem `invalid_value` | real |
| `help()` | text, on the class too | real |
| `check()` | list of `Issue`, one `missing` issue per unset parameter (`path`, `quantity`, `accepted` units, the meaning in `message`); `[]` when the tree can run; never raises. A plant also reports the issues of its file: units, ranges inside bounds, options allowed, connections valid | real |
| `get(path)` | the declaration at a dotted path, whatever its kind | real |
| `get_submodule(path)`, `named_modules()`, `modules()`, `children()`, `named_children()` | a module, or the tree | real |
| `state_dict()`, `set_state_dict(state, strict=True)` | the state tree of a stateful module, and its restore | real |
| `step(state, dt, inlets)`, `initial_state()` | `step` advances the states over `dt` and returns `(next_state, result)`; a module author writes `forward` and `update`, not `step`. A module has no default state: `initial_state()` of a module that declares states raises `missing_value` (the case states them) | real |

```text
{name, type, category, summary, doc,
 parameters, controls, boundaries, measured, state:
   {name: {type, unit, quantity, default, minimum, maximum, enum, description, section}},
 inlets, outlets: {port: {kind, fields: {m_dot: {unit}, T: {unit}, p: {unit}}}},
 outputs: {name: {unit, quantity, soft_sensor}},
 children: {name: type},
 connections: [{source, target, kind, type}],
 values: {parameters, controls, boundaries}}
```

`kind` is `null` for a port that takes any stream; an output's `quantity` is the quantity or `null`;
`measured` is every output of the module, which is what a `measured` binding may name. `minimum`
and `maximum` are the closest limit, strict or not. `values` are keyed by dotted path.

## The module contract

What a module author writes, and what the engine calls ([writing a module](writing-a-module.md),
[modules.md](modules.md), [engine.md](engine.md#time-as-a-scan)). The signatures are part of the
frozen 0.5.0 surface.

| Name | Signature | Contract |
| --- | --- | --- |
| `Module.forward` | `(self, inputs, inlets, state)` | pure: reads parameters on `self`, the controls and boundaries in `inputs`, the streams in `inlets` (a `Ports` mapping) and the states in `state` (`{}` without states); writes nothing; returns `(outputs, outlets)` with exactly the declared keys, else a `DefinitionError` naming the module and the key |
| `Module.update` | `(self, inputs, inlets, outlets, state, dt)` | only a module with states: pure, returns the next state, a key for each declared state and no more; `dt` in seconds |
| `Plant.forward`, `Plant.update` | the same | written once for any graph; a plant class defines neither; the state of a plant is the nested dict of the states of its children, by child name, plus `@previous` for state connections |
| `Module.step` | `(state, dt, inlets)` | `(next_state, result)`: `forward`, then `update` of every stateful module the call reached |
| `module(..., state=tree)` | keyword | calls from a state; a stateful module without one raises `missing_value` naming it |
| `State` | `(type, *, default=UNSET, description=None, **bounds)` | declared like a parameter, no default in a shipped module: the case states it (`initial_state`) |
| pre-hook | `(module, inputs, inlets, state)` | `None` observes, a mapping replaces the controls and boundaries of this call |
| forward hook | `(module, inputs, inlets, state, outputs, outlets)` | `None` observes, a mapping replaces outputs of this call |
| `gm.call` | `state=None, dt=None` | a module with state takes both; the result has `state` |

A per-step value is never `None` (an empty output is NaN, shown as `None`), and a module reads no
control, boundary, state or output from `self` and assigns none inside a call.

## Plants

A leaf computes and a plant connects: see [plants.md](plants.md). Plants are Python classes; the
plant dict is the JSON form agents use, and `gm.plants.schema()` is its schema. The plant classes
are in `gm.plants`, not in `gm.modules`; `gm.modules` never imports `gm.plants`.

| Name | Returns | Status |
| --- | --- | --- |
| `gm.Plant(name)` | an empty plant; subclass it for a plant class | real |
| `gm.Plant.from_dict(data)` | a plant of a class or without one, from a plant file (`kind: plant`, `format: 1`); one `ValidationError` carries every issue in `issues`, except a parameter or size without a value, which `size` completes | real |
| `gm.Plant.from_json(path)`, `p.to_json(path, structure=False)` | reads or writes the plant file as JSON; `structure=True` writes the full form, the class and its modules and connections | real |
| `p.size` | the structural size as a plain mapping, `{"doublets": 2}` | real |
| `p.ranges`, `p.options` | the search space the file states: `{path: Range}` in SI and `{path: tuple}`, in file order, `size.doublets` first | real |
| `p.set_range(path, min=None, max=None)`, `p.set_options(path, options)` | the plant; checked as a file's range and options are | real |
| `p.add(type, name=None, params=None)` | the added module; `type` is a registry name or a class, `params` the dict `set_params` takes (quantities for what has a dimension) | real |
| `p.connect(source, target, type=None)` | nothing; `ValidationError` with candidates, see [plants.md](plants.md) | real |
| `p.constrain(target, by, bounds, equals=None, at_least=None)` | nothing; the engine solves `by` so that `target` reaches its value, see [plants.md](plants.md#constraints) | real |
| `p.loop_tolerance`, `p.loop_passes` | the settings of a loop, 1e-9 and 50, see [plants.md](plants.md#loops) | real |
| `p.summary()` | text table | real |
| `p.set_inputs(values)` | the plant; sets an input of a control or a boundary by path, the one public way; a bare number for a declared input with a dimension is refused: `{"heat_pump.temperature_setpoint": {"value": 100, "unit": "degC"}, "heating_return.T": {"value": 60, "unit": "degC"}}`. A plant file has no `inputs` key (it is refused, `old_format`): a control is a leaf of `params` and an input of the case is in the case, see [plants.md](plants.md#the-plant-dict) | real |
| `p.input_value(path)` | the input in SI, or `None` when it has no value | real |
| `p.target_of(source)`, `p.source_of(target)` | the `"path.port"` an outlet feeds, or that feeds an inlet; `None` for a plant port | real |
| `p.feeds(source)` | the paths of the modules an outlet reaches through its circuit, nearest first; it ends at a grid or a plant port | real |
| `p.to_dict(structure=False)` | the plant file (`format: 1`, `kind: plant`); `structure=True` gives the modules and connections of a plant of a class as well | real |
| `Output.difference(a, b)`, `Output.ratio(a, b)`, `Output.sum(a, b, ...)` | the outputs of a plant, combinations of paths, see [plants.md](plants.md#outputs) | real |
| `gm.plants.schema()` | JSON Schema of the plant file (`kind: plant`, `format: 1`: `type`, `size`, `params` as a tree of leaf objects, `modules`, `connections`), generated from the code | real |
| `gm.plants.names(category=None)` | plant names; `category` is `heating`, `cooling` or `both`, what a plant serves | real |
| `gm.plants.get(name)` | a new plant without values | real |
| `gm.plants.capabilities()` | `{plant class: {roles, schedulable, ranges}}`, built from the code; `ranges` lists every leaf of the plant file that may state a `range` for a study: `size.doublets` when the class has it, then `params.<path>` of each numeric parameter, control and boundary (`params.depth`, `params.d0.nominal_flow`) | real |
| `gm.plants.<Plant class>` | the plant classes, see [plants.md](plants.md#registered-plants). The five template plants take `doublets=n`, `size={"doublets": n}` in a plant dict, and a plant-level `depth` | real |

A `Doublet` with a `depth` and no geotherm waits for it, and a run that starts without it raises code
`missing_value` with the path: a plant holds the design, and the geotherm comes from the case
(`site.ground`).

On any plant, `path` being a dotted module path (`""` is the root):

| Name | Returns | Status |
| --- | --- | --- |
| `set_params(path, params, valid_from=None)` | dated entry, validated; a complete snapshot; a value with a dimension is a `Quantity` or `{"value", "unit"}`, a bare number for it raises `invalid_value` (zero too) | real |
| `params_at(path, time=None)` | `{name: value}` in force at `time`, latest without one | real |
| `param_history(path)` | `[{valid_from, params}]` | real |
| `bindable(path)` | `{controls: [name], boundaries: [name], inlets: {port: [field]}, measured: [name], state: [name]}` | real |
| `set_bindings(path, bindings)` | replaces them; flat `{name: column}` or `{name: {column, unit}}`, `name` a declaration or `port.field`; units checked | real |

## Units

| Name | Returns | Status |
| --- | --- | --- |
| `gm.units.names(quantity=None)` | unit names, of one quantity if given | real |
| `gm.units.convert(value, from_unit, to_unit, quantity=None)` | number | real |
| `gm.units.fits(unit, quantity)` | bool; an unknown unit is false, an unknown quantity raises | real |
| `gm.units.Unit` | the `str` enum of every unit of the table, generated from it: `Unit.M3_PER_H == "m3/h"` | real |
| `gm.units.Quantity(value, unit)` | the one shape of a value with a dimension; `.si`, `.to(unit, quantity=None)`, `to_dict()`, `Quantity.from_dict(d)`; equality compares SI values | real |

Every public input with a dimension takes a `Quantity` or its dict `{"value": 150, "unit":
"m3/h"}`. A text such as `"150 m3/h"` is `ValidationError` `invalid_value` everywhere, and a unit
of another dimension is `invalid_unit` that lists the units of the field. A dimensionless value (an
efficiency, a fraction, a rate, a count) stays a number. Nothing in the package parses unit text.
`gm.units.parse` and `split_quantity` are gone.

A bare number with a dimension is refused at every public door: `set_params` (also `Plant.add` and
`validate_params`), `Plant.set_inputs`, `gm.Stream(...)`, `gm.Fluid(...)` for density, viscosity,
specific heat and thermal conductivity, the `parameters`, `controls` and inlet fields of `gm.call`,
`gm.modules.check`, `Atmosphere.ambient_air`, a plant file (`params`, `fluids`), a `gm.Case` and the variables, limits and distributions of `gm.study`. The error is
`ValidationError` `invalid_value`, with the path, the quantity and the accepted units, and zero is
refused too: `set_params("", {"length": 1500.0})` fails and `{"length": Quantity(1.5, "km")}` is
stored as 1500 m. `gemini` itself passes SI through the private `_set_si_params`, `_set_si_inputs`,
`Stream._si` and `Fluid._si`, which are not public. Attribute assignment on a module outside a call
(`esp.frequency = 50`) and `Stream.with_(T=300.0)` are refused the same way; `gemini` uses
`Module._assign_si` and `Stream._with_si`.

A `Doublet` has `volume_imbalance`, a `HeatingGrid` and a `CoolingGrid` have `surplus`: see
[equipment.md](equipment.md).

## Runtime and ops

| Name | Returns | Status |
| --- | --- | --- |
| `gm.runtime.settings(backend=..., precision=..., display_units=..., processes=...)` | a context manager and decorator: the settings apply inside it and are restored after; `backend=None` restores the automatic choice; `processes` (a whole number, default 1) is the number of worker processes of the trials of `gm.study.sample`, `sensitivity` and `minimize`, with the numbers and the order of a serial run (a script needs the `if __name__ == "__main__":` guard); an unknown name or value raises `ValidationError` | real |
| `gm.runtime.state()` | a copy of the current settings, plain data | real |
| `gm.ops.register_backend(backend)` | adds a `Backend` object to the registry under its `name`; `gm.runtime.settings(backend=name)` then selects it | real |
| `gm.ops.<op>` | the math API of the ops, see [physics.md](physics.md) | real |
| `gm.compiler.compile(plant)` | the executor of a plant, which traces it into a computation graph; importing `gm.compiler` registers it as the executor of `Engine(..., compile=True)`, see [native-engine.md](native-engine.md) | real |

The setters and getters of the settings (`set_precision`, `set_display_units`,
`get_precision`, ...) are not public: change a setting with `gm.runtime.settings`.

## Case

`gm.Case` is the strict, typed entry boundary of every run: the outside conditions over one period
and the rules of third parties. Sections `time`, `initial_state`, `site`, `demand`, `utilities`,
`economics` and `requirements` in a `case.json` with its CSV files and `economics.json`
next to it ([data.md](data.md#the-case) holds the file section by section, [inputs.md](inputs.md)
the rule of each field). Objects are immutable, values are stored in SI as plain numbers or arrays
and written back as given. No field has a default but absent (`None`). An absent value that a call
needs raises `missing_value` naming its path, `missing_assumption` below `economics`.

| Name | Meaning | Status |
| --- | --- | --- |
| `gm.Case.from_json(path)`, `case.to_json(path)` | reads a `case.json`, its CSV files and its economics file, or writes them | real |
| `gm.Case.from_dict(data, files=None, folder=None)`, `case.to_dict()`, `case.files()`, `gm.Case.schema()` | plain data; the CSV and JSON files the case names come from `files`, a mapping `{name: bytes}` with names relative to the case (no folder is needed in memory), else from `folder`, for a caller that edits a dict read from a `case.json` and has its files on disk; the CSV and JSON files of a case; JSON Schema | real |
| `case.check()`, `economics.check()` | the issues of an object; never raises. `from_json` and `from_dict` raise a `ValidationError` carrying the same issues | real |
| `case.with_value(path, number)`, `case.field(path)`, `case.leaf(path)`, `case.uncertainty` | a copy with an SI value, the quantity and bounds of a value, the leaf as read, the index of uncertainties | real |
| `gm.case.Time` (`start`, `end`, `step`) | `end` is excluded; `.index` is the UTC `DatetimeIndex` of the steps | real |
| `gm.case.Site` with `Ground`, `Reservoir`, `Fluid`, `Air` | `temperature_at(depth)`, `pressure_at(depth)` | real |
| `gm.case.Demand` with `Service`, `CoolingService` | `.frame` in W on the index of `time`; the services hold `power` and the conditions of the consumer | real |
| `gm.case.Utilities` with `Electricity`, `Gas` | `co2_intensity`, `import_limit`, `export_limit`, `composition`, `heating_value` | real |
| `gm.case.Economics.from_json(path, time=None)`, `from_dict(data, files=None, time=None)`, `to_json`, `check`, `schema`, `drilling_cost_per_metre(length)` | all money; usable alone, held as `case.economics`; `time` (the `Time` of a case) only for a price given as a series; its sections are `gm.case.Capex`, `Opex`, `Energy`, `Carbon`, `Revenue`, `Subsidy`, `Accounting`, `Gwp` and `DepthTable` | real |
| `gm.case.Requirement` (`name`, `on`, `quantity`, `over`, `when`, `min`, `max`) | a rule on a quantity of a role; bounds in SI | real |
| `gm.case.Range`, `gm.case.Uncertainty` | the shared objects of `gemini.units.inputs` | real |
| `gm.plants.roles()` | `{role: {quantity: {"dimension", "over"}}}`, the closed table a `Requirement` names. `doublet` has `production_flow`, `brine_cooling`, `pump_efficiency`, `reinjection_ratio`, `count`, `intake_pressure`, ...; `heating_supply` and `cooling_supply` have `unmet` and `unmet_share`; the role `plant` has `electricity_bought`, `gas_bought`, `heat_surplus`, `co2` and `gas_burned` (the co-produced gas burned in the plant, kg/s) | real |

The plant dict holds only the plant ([plants.md](plants.md#what-the-plant-dict-holds)). A run sets
the values of the case on a copy of the plant by module class ([engine.md](engine.md#how-the-case-reaches-the-modules)).

## Running

Run input is one format: a pandas DataFrame or a `gm.Dataset` with a timezone-aware UTC index, columns
named by binding `column`, units from the binding. A missing bound column raises `ValidationError`
(code `missing_column`) listing them all. A NaN row is a row code and the run continues.

```python
import gemini as gm

case = gm.Case.from_json("examples/shallow_district/case.json")
plant = gm.Plant.from_json("examples/shallow_district/plants/HeatingHeatPumpCoolingPlant.json")
results = gm.simulate(plant, case)
print(results.summary(units={"power": "MW", "temperature": "degC"}))
```

Use the functions for a run that is one call (agents, backend workers, examples, scripts) and
`gm.Engine` for what must live across calls: a run held in memory, a callback that reads the engine,
a manual checkpoint. Each function builds an `Engine`, calls the matching method and returns its
`Results`, so the numbers are the same on every backend; see
[engine.md](engine.md#functions-or-engine).

| Name | Returns | Status |
| --- | --- | --- |
| `gm.schedule(plant, case)` | run input, a UTC DataFrame: the demand and one column per scheduled control, named after its dotted path; `attrs["units"]` states the unit of each driven column, `attrs["outages"]` is `{doublet path: [ISO time of each outage step]}` and `attrs["check_only"]` lists the constraints the schedule does not enforce; sources load from the cheapest to the dearest; see [engine.md](engine.md#schedule) | real |
| `gm.simulate(plant, case=None, plan=None, clock=None, checkpoint=None, checkpoint_every=None, backend="numpy", callbacks=None, on_error="raise", compile=True)` | `Results`; `gm.check(plant, case)` runs first and raises its issues; `case=None` only with a `plan` (a building block has no demand; no check runs); without a `plan` it schedules; `compile=False` forces the eager run. `compile` and `backend` cannot change a result | real |
| `gm.replay(plant, data, start=None, end=None, state=None, clock=None, only=None, checkpoint=None, checkpoint_every=None, backend="numpy", callbacks=None, on_error="raise")` | `Results`; `results.end_state` is the `state=` of the next call | real |
| `gm.live(plant, source, checkpoint, step=None, now=None, sink=None, backend="numpy", callbacks=None, on_error="raise")` | `Results` of the new rows; `checkpoint` is a required path | real |
| `gm.resume(checkpoint, callbacks=None)` | `Results` of an interrupted `simulate` or `replay`; `RunError` (code `checkpoint`) on a live checkpoint | real |
| `gm.Engine(plant, backend="numpy", callbacks=None, on_error="raise", compile=True)` | one runner, for complex tasks | real |
| `engine.simulate(profile, clock=None)` | `Results` | real |
| `engine.replay(data, start=None, end=None, state=None, clock=None, only=None)` | `Results`; `results.end_state` is the `state=` of the next call | real |
| `engine.live(source, checkpoint=None, step=None, now=None, sink=None)` | `Results` of the new rows | real |
| `engine.to_checkpoint(path)`, `gm.Engine.from_checkpoint(path, callbacks=None)`, `engine.resume()` | see [engine.md](engine.md) | real |
| `AutoCheckpoint(path, every=100)` | a callback that saves every N steps or every duration | real |
| Callback `on_progress(engine, done, total)` | a callback may raise `gm.errors.Cancelled`; committed ticks stay in `engine.results` | real |
| `gm.call(module, parameters, inlets, controls, units, on_error="raise", state=None, dt=None)` | `{outlets: {port: {field: value}}, outputs: {name: value}, state: {...}, errors: [problem]}`; a run at one point. `units` has no default: `"si"` gives every value as the plain JSON `{value, unit}` in SI, `"display"` gives every value as a `gm.units.Quantity` (a `Value` for a value that is `None`, with its `reason`) in the display unit of `gm.units.display.DISPLAY_UNITS`, the table of the report (MW, MWh, degC, m3/h, ...); a quantity the table does not list, and a difference such as a temperature lift, stays in SI. Converted back to SI the two results are equal. Any other text is `invalid_value` (path `units`); the map `{quantity: unit}` of the other public returns is not taken. A module with state, or a plant with one below it, needs `state` (the state at the start, `{state name: quantity}`, for a plant `{child name: {state name: quantity}}`) and `dt` (the step, a quantity of time): without either the call raises `missing_value` naming it, a bare number for a state is `invalid_value`, and `state` or `dt` on a module without state is `invalid_call`. The result's `state` is the state at the end of the step in the same nesting, as values in the choice of `units`, ready to be the `state` of the next call; it is `{}` for a module without state (only the stateful modules that were called are in it). `parameters`, `controls` and the inlet fields are quantities for what has a dimension (a bare number raises `invalid_value`, listed in `errors` with `on_error="record"`). An inlet takes `m_dot` for a mass flow or `flow` for a volume flow (`{"value": 150, "unit": "m3/h"}`, by the density of the inlet's `fluid`), with `T`, `p` and an optional `fluid`; a volume unit on `m_dot` raises code `invalid_call` with the suggestion `flow`. A module works on the fluid of its inlet streams (a tank, an injection aquifer, a pipe), so `gm.call` needs no fluid argument; a module reads `module.fluid` only where it has no inlet stream to take it from (a source such as `ProductionReservoir`, the offer of `ChemicalGrid` and `AquiferStorage`), and `gm.call` of those raises `missing_value` naming `<module>.fluid` | real |

`rules`, `order`, `cooling_order` and the list and fraction forms of `operating_time` of the old
`gm.schedule` are gone: limits are the `requirements` of the case, and the merit order and the outage
steps are the plant's `control.dispatch` and `control.outages`.

| `Results` | Returns | Status |
| --- | --- | --- |
| `names()` | `{path: [field]}` | real |
| `get(path, field, start=None, end=None, units=None)` | the time series `{time, value, unit}`; *units* | real |
| `summary(path=None, start=None, end=None, units=None)` | `{path: {field: {min, max, mean}}}`, each a value; *units*; schema `results_summary` | real |
| `errors()` | `[{path, code, message, suggestions, time}]`, `code` from `gm.errors.ROW_CODES` | real |
| `to_frame(units=None, table="series")` | DataFrame. `"series"`: columns `path.field`, the calculated-tag names, *units*, with `attrs["units"]`. `"energy"`: the table of `energy_report`, one row per module and energy output | real |
| `to_dict(units=None)` | `{time, duration, series: {path: {field: value}}, errors, skip_counts, end_state}`, `duration` a value; *units* | real |
| `to_npz(path)`, `gm.Results.from_npz(path)` | `.npz` | real |
| `to_bytes()`, `gm.Results.from_bytes(data)` | `.npz` bytes | real |
| `end_state` | `{position, module_states}` | real |
| `energy_report(units=None)` | `{path: {output: {energy, peak, hours, operating_hours, alarms, alarm_rate, skipped, errors, peaks, reasons}}}`, every number a value; *units*. A path without an energy output has the entry `""` | real |
| `results[path].field`, `skip_counts` | a pandas Series, `{path: {reason: count}}` | real |

## Demand frames

Readers are `from_<format>` and writers `to_<format>` everywhere. A reader that returns a gemini
class is a classmethod of it (`gm.Case.from_json`); only a reader that returns no gemini class,
a demand frame, is a plain function of its folder (`gm.case`; there is no `gm.data`).

| Name | Returns | Status |
| --- | --- | --- |
| `gm.case.from_csv(path, columns, unit)` | run input read from a CSV file whose first column is `time`: a UTC DataFrame at any constant step, `heating_demand` and `cooling_demand` in W, `units` and `quantities` in `attrs`; `columns` is `{file column: quantity}`. Problems: `unknown_name`, `invalid_unit`, `missing_column` (`time` included), `missing_value`, `out_of_bounds`, and `RunError` code `invalid_data` for an index that is not monotonic or has gaps, repeats or a changing step | real |
| `gm.case.from_values(values, unit, start, step, quantity)` | the same frame with one column; `quantity` is `heating_demand` or `cooling_demand`, `step` a duration or seconds | real |
| `gm.case.profile_schema()` | JSON Schema of that frame as a document | real |

gemini ships no profile: a demand is the caller's.

## Analysis

Details and inputs are in the docstrings and [economics.md](economics.md). Every number of these
returns is a value; every entry here takes *units*, except where a coefficient has no quantity.

| Name | Returns | Status |
| --- | --- | --- |
| `gm.study.calibrate` with `plant, dataset, params, start=None, end=None, backend="numpy", apply=True` | a `gm.study.CalibrationResult`; fits only through replay. With `apply=True` a successful fit replaces the current parameter as an explicit override and adds no dated snapshot. Pass parameter objects declared `calibratable=True`, such as `plant.get("heat_exchanger.thermal_conductance")` | real |
| `gm.analysis.nodal(plant, well, conditions, on_error="raise", units=None)` | `{well, cases: [{conditions, ipr: {rate, pressure}, vlp: {rate, pressure}, operating_point: {rate, wellhead_pressure, sandface_pressure}, error}]}`; with `"record"` a failed case has its problem in `error`; an injection well or its aquifer has the same shape | real |
| `gm.analysis.pump_curve(plant, pump, measured=None, units=None)` | `{pump, frequency, curve: {flow, head}, measured: [{flow, frequency, head, theoretical_head}], correction: {slope, offset}}`, or `correction` a null value with its reason | real |
| `gm.analysis.corrosion_forecast(model, until, units=None)` | `{correlation, rate, thickness, minimum_thickness, years_left}`; `thickness` a time series, `rate` stays in mm/year | real |
| `gm.analysis.fit_head_coefficients(flows, frequencies, heads, stage_count, units=None)` | a value of six ESP head coefficients, on their own basis | real |
| `gm.analysis.fit_head_correction(measured, theoretical, units=None)` | `{slope, offset}` of the head correction | real |
| `gm.analysis.estimate_reservoir_pressure(flows, bottomhole_pressures, units=None)` | `{pressure, r_squared}` | real |
| `gm.analysis.estimate_conductance(hot_in_T, hot_out_T, cold_in_T, cold_out_T, m_dot_hot, m_dot_cold, *, cp_hot, cp_cold, arrangement, units=None)` | a value of the apparent UA of an exchanger | real |

## Evaluate and study

Every `gm.evaluate` function takes `(plant, case, results, ...)`; only `capex` has no results.
The cost functions return a value with the parts of the result as more keys. A value the inputs
cannot give raises `ValidationError` (code `no_value`, or `missing_assumption` for an assumption
nobody gave); with `on_error="record"` it is a `Value` whose `value` is `None` and whose `reason`
says why. Prices, rates and cost factors are those of `case.economics`; gemini holds none.
Equipment declares its `equipment_kind` and the `cost_size()` its cost scales with; `gm.evaluate` multiplies
it by the cost factor of its kind, see [economics.md](economics.md#costs). A violated requirement is a check, never an
error.

| Name | Status |
| --- | --- |
| `gm.evaluate.totals(plant, case, results)` | real: `{name: value}` of what crossed the plant's edge over the run, each read from the ports of the edge modules, heat and cold as delivered, useful (at most the demand) and surplus; `None` with a reason when no edge module shows it. It also gives the KPIs `heating_coverage`, `cooling_coverage`, `cop`, `peak_heat`, `peak_cold` |
| `gm.evaluate.requirements(plant, case, results)` | real: a list of checks `{name, role, unit_path, quantity, passed, value, limit, worst_step}`, one per unit of the role of each requirement of the case (`name` that of the requirement), plus the supply temperatures of the services; `value` the worst of the run; `passed` is `null` with a reason `no_value` when there is nothing to judge (a role with no unit in the plant gives one such check); a role or quantity not in `gm.plants.roles()` raises `unknown_name` |
| `gm.evaluate.plant_balance(plant, case, results)` | real, a list of checks: mass and energy of every module within 1e-9 and of the root within 1e-6. The root's in and out are the ports of the grids and environment modules, the aquifers and the plant ports of a building block run alone; a replay does not close at the root |
| `gm.evaluate.energy_balance(plant, case, results)`, `mass_balance(plant, case, results)`, `bounds(plant, case, results)` | real, each a check; they are ledger checks, see [economics.md](economics.md) |
| `gm.evaluate.call_energy_balance(module, result)`, `call_mass_balance(module, result)`, `collect_flows(result_tree)`, `call_emissions(result_tree, fuel_factor, electricity_factor)` | real: the audits of one `gm.call` (a module or a plant, no case), the former `gm.modules.energy_balance`, `mass_balance`, `collect_flows` and `emissions`; they sit here because they judge, and a module never imports `evaluate` |
| `gm.evaluate.verdict(plant, case, results)` | real: the one answer to feasibility, a `Verdict` (a `dict`, `to_dict()` for plain JSON) `{feasible, reasons}`. A reason is `{kind, name, message}` plus `path`, `value`, `limit`, `worst_step` when it has them (a `requirement` reason also has `role` and `quantity`). Kinds: `requirement` (a failed requirement or service supply temperature of the case, none checkable, a service not delivered; `name` that of the requirement, or `cold_delivered`-style), `failed_step` (failed or skipped rows), `numerical` (a mass, energy or plant balance beyond its constant, a loop that did not converge) and `bound` (an output outside the limits its module declares, or past an operating limit of `Module.operating_limits`, in the steps in which the module ran). The case is applied to the plant once; `report` and `compare` use it, nothing else decides feasibility |
| `gm.evaluate.capex(plant, case, on_error="raise")` | real: the sum, each module in `parts["modules"]` |
| `gm.evaluate.opex(plant, case, results, on_error="raise")` | real: the fixed opex of each kind in `parts["fixed_by_kind"]` and the bills of energy; no variable opex |
| `gm.evaluate.lcoh(plant, case, results, on_error="raise")` | real: the discount rate and the analysis period are `economics.discount_rate` and `economics.analysis_period` of the case; there is no argument for either |
| `gm.evaluate.lcoc(plant, case, results, on_error="raise")` | real |
| `gm.evaluate.lcts(plant, case, results, on_error="raise")` | real |
| `gm.evaluate.annualised_cost(plant, case, results, on_error="raise")` | real |
| `gm.evaluate.co2(plant, case, results, on_error="raise")` | real: stepwise; a factor is needed only when its source is non-zero |
| `gm.evaluate.npv(plant, case, results, on_error="raise")` | real |
| `gm.evaluate.payback(plant, case, results, on_error="raise")` | real |
| `gm.evaluate.capacities(plant, case, results)` | real: `{path: {kind, capacity, peak, share}}`, each a `Value` but `kind`, for the equipment that has a rating |
| `gm.evaluate.daily_coverage(plant, case, results)` | real: `{service: [day, ...]}` for `heating` and `cooling` (a service the plant has no consumer for is left out), the days in time order, each `{date, source, demand, geothermal, backup, short, failed_steps}`; `date` is a UTC day `YYYY-MM-DD` (the time of a case is UTC); the energies are `Quantity` values in the display unit of energy (MWh, `gm.units.display`) and `failed_steps` a count (`-`); `to_plain` gives the JSON; `demand = geothermal + backup + short`; `backup` is what the units of the roles `boiler` and `chp` (`gm.plants.roles()`) gave their water, never a class list, `geothermal` the rest of the useful heat, `short` the unmet demand (no role is a backup of cooling, so its `backup` is 0); `failed_steps` counts the ticks of the day that failed, were skipped or show no demand: they add no energy, as in `totals`, but the day is `short`; `source` (`geothermal`, `backup` or `short`, the colour of the day) is `short` with a failed step or an unmet demand above a millionth of the demand, else `backup` with a backup above that. The sums over the days are `heat_useful` (`cold_useful`) of `totals`, and `heating_coverage` (`cooling_coverage`) is their ratio to the sum of `demand` |
| `gm.study.kinds()` | real: `[{kind, use, title, description, settings}]` for `run`, `minimize`, `sample`, `sensitivity` (`use` `"method"`) and `size` (`use` `"prepare"`); plain words; `settings` the JSON Schema of the keys the kind reads beyond `cases` and `plants` (`objective`, `evaluations`, `seed` for `minimize`; `metrics`, `samples`, `seed` for `sample`; `metrics` for `sensitivity`), with `required`, titles and the choices of metrics | real |
| `gm.case.missing(case)` | real: `Issue`s of kind `missing` for what a `Case` or a partial case dict lacks: header, `time` keys, the required leaves of the sections given, the header of an inline economics, the keys of each requirement; `quantity` and `accepted` units where the value has a dimension; never raises. It takes no plant: what a plant needs from the case is `gm.check(plant, case)` | real |
| `units="display"` | real: on `Results.get/summary/to_frame/to_dict/energy_report`, `Comparison.to_dict` and (keyword-only) the cost functions, the one table `gm.units.display`; a map by quantity still works; `"si"` and the default are unchanged | real |
| `gm.evaluate.metrics()` | real: the metrics a table of results shows, `[{name, quantity, unit, title, objective}]` in a fixed order (`title` a readable label, `objective` whether `gm.study.minimize` may target it: costs and CO2), `quantity` the key of `gm.units.display.DISPLAY_UNITS` and `unit` the display unit (`yr` for the durations of years); plain JSON, a new list on each call. The names are the keys of the private table the backend read before |
| `gm.evaluate.report(plant, case, results)` | real: a `Report`, see [the contract](#the-geomind-contract) |
| `gm.evaluate.compare(reports, by)` | real: a `Comparison`, see [the contract](#the-geomind-contract) |
| `gm.evaluate.failures(results)` | real: a `Failures`, the failed and skipped rows of a run grouped by module path and row code, most frequent first: `groups` of `{path, code, kind, count, first, last, message}`, `total`, `to_dict()` (`{total, groups}`, JSON) and `to_frame()` |
| `gm.study.size(plant, case)` | real: a new plant with first sizes under the policy `backup` that the plant states in `params.backup` (`"none"`: the boiler covers what the doublets cannot reach; `"peak"`: the whole heating peak with the doublets off; no default, `missing_value` naming `params.backup` without it); runs `gm.check`, tolerating the parameters without a value; a rated unit has the capacity of the largest duty the case lets it run, so `share <= 1`; the notes are `plant.sizing` `{sized, unchanged, broken, simulation}` and `size` never hides an infeasible start |
| `gm.study.minimize(plant, case, objective, evaluations, seed, *, plan=None, on_progress=None)` | real: `{best, feasible, history, evaluations}`, `best` a `Best` (a `Value`) whose `parts["parameters"]` are `{name: Quantity}` (an option is its string) and whose `["plant"]` is the best `Plant` (its `to_json` is a plant file that runs); `Best.to_dict()` is plain JSON and `Best.from_dict` reads it back; the variables are the `range` and `options` leaves of the plant and its `size.doublets` range, tied by parameter name, role and range (see economics.md); `evaluations` and `seed` have no default; `gm.check` runs first; a trial is judged by the reasons of its `gm.evaluate.verdict` that carry a `violation`; `on_progress=None`: `on_progress(done, total)` runs in the calling process after each finished trial (also with `processes=n`), `total` the known trial count, and `done` reaches it at the end; raising `gm.errors.Cancelled` from it stops the study, later trials do not start, the workers are stopped and the exception propagates; no effect on the trials or the numbers when not given |
| `gm.study.sample(plant, case, metrics, samples, seed, *, plan=None, on_progress=None)` | real: `Sample`, a dict `{samples, summary}`, `summary` per metric `{mean, p5, p50, p95, failed}`, each a `Value`, `failed` the draws left out because their run had failed steps (their metrics are `None` with the count and the top failure); each item of `samples` also has `feasible`, a bool from `gm.evaluate.verdict` of its run (`False` for a run with failed steps; absent from a result stored before it), which changes no metric and no summary key or count; draws only the `uncertainty` the case declares (`missing_value` if none), never a plant parameter; `seed` has no default; `to_dict()` / `Sample.from_dict` are JSON; `on_progress=None`: `on_progress(done, total)` runs in the calling process after each finished trial (also with `processes=n`), `total` the known trial count, and `done` reaches it at the end; raising `gm.errors.Cancelled` from it stops the study, later trials do not start, the workers are stopped and the exception propagates; no effect on the trials or the numbers when not given |
| `gm.Study.from_json(path)`, `Study.from_dict(data, files=None, folder=None)`, `run(plants=None)`, `check()`, `to_json` | real: `study.json` (`kind: study`) as the arguments of the study functions; `run` returns a `StudyResult` (`runs`, `comparison`, `best`, `to_json(folder)` writing the run records) |
| `gm.check(plant, case)` | real: the list of `Issue` that need both (a capex and a fixed opex for each kind, a requirement on a role the plant lacks other than the supplies, an initial state for each stateful module, energy prices of a `least_cost` dispatch, parameters without a value); it never raises; `simulate` and every study function run it first |
| `gm.study.sensitivity(plant, case, metrics, *, plan=None, on_progress=None)` | real: a `Tornado`, a list sorted by effect with `to_frame()`, `to_dict()` and `Tornado.from_dict`; a bound whose run had failed steps is `None` with a reason, and so is the effect; each row also has `feasible_low` and `feasible_high`, bools from `gm.evaluate.verdict` of the run at each end (`False` for a failed run; absent from a result stored before them), which change no number and no row order, and `to_frame()` does not show them; each value the case declares an `uncertainty` for, at its `min` and `max` (`value ± std` for a `normal` without bounds); `on_progress=None`: `on_progress(done, total)` runs in the calling process after each finished trial (also with `processes=n`), `total` the known trial count, and `done` reaches it at the end; raising `gm.errors.Cancelled` from it stops the study, later trials do not start, the workers are stopped and the exception propagates; no effect on the trials or the numbers when not given |

`case` of `gm.study.minimize` and `sample` plans the demand for each trial with `gm.schedule` on the
design of that trial, so a variable that changes the design changes the plan. A `plan` (run input, a
frame) stays fixed over the trials and lets `case` be `None` for a building block with no demand
and metrics that need no assumptions; with neither the call raises `ValidationError` code
`missing_value`. A case without prices gives an economic metric a reason, not a value.

Known limits of `gm.study`:

- `size.doublets` is searched only for a plant that states a `range` for it (a plant class that
  takes the structural size `doublets`, `"size.doublets" in gm.plants.capabilities()[class]["ranges"]`). Without it
  the count is not searched, and `size` keeps the doublets the plant has and lists that in
  `plant.sizing["unchanged"]`; `invalid_design` is raised when the plant states nothing to search.
- A search that varies the doublet count, the flow or the depth leaves the rating of the
  injection pump at the value `size` gave it. Measured on the hackathon case, doubling its power
  moves LCTS by 0.13 EUR/MWh and quadrupling it by 0.38, under 0.5 EUR/MWh.
- `evaluations` counts the simulations **for each doublet count**; a trial costs about two
  simulations of the plant (0.15 s on the hackathon year); `gm.runtime.settings(processes=n)` runs the
  doublet counts of `minimize` in parallel.

Known limits of the cost model: a module without an equipment kind (`IceStorage`,
`ESP`, `LineShaftPump`, `AquiferStorage`, `ORC`, `Separator`, `GasCompressor`, ...) adds no capex,
see [equipment.md](equipment.md#cost-kinds-and-the-equipment-mixin).

## The geomind contract

geomind follows the list below. It is every call that `examples/hackathon.py` makes, in the order
of the flow, with its signature and its return shape. `python examples/hackathon.py` runs it (see
[examples/README.md](../../examples/README.md)); `tests/e2e/test_examples.py` runs it in CI.

| Step | Call | Returns |
| --- | --- | --- |
| Read the case | `gm.Case.from_json(path)` | `gm.Case`. `ValidationError` with `path` and `code` for a wrong file |
| Read a candidate | `gm.Plant.from_json(path)` | `gm.Plant`. `plant.to_dict()` is the plant dict |
| Fill a plant | `gm.plants.<Class>(...)`, then `plant.check()` and `plant.set_params("", values)`, a value with a dimension a `Quantity` | a list of `missing` issues, one per value still unset (the reservoir and the wells that the case gives are in it until a run); a run with a value missing raises `missing_value` naming all of them |
| Check a plant | `plant.check()` | `[]`, or the issues; it never raises. `gm.Plant.from_dict` raises one `ValidationError` with the same issues |
| Make a value | `gm.units.Quantity(value, unit)`, with `unit` a text of the `Unit` table | `Quantity`: `.value`, `.unit`, `.si`, `.to(unit)`, `to_dict()` |
| Size | `gm.study.size(plant, case)`, the policy being the plant's `params.backup` | a new `gm.Plant`; `plant.sizing` is `{"sized": [{path, value, reason}], "unchanged": [{path, reason}], "broken": [{unit_path, role, quantity, value, limit, worst_step}], "simulation": str}` |
| Search | `gm.study.minimize(plant, case, objective, evaluations, seed, *, plan=None)`, called as `minimize(sized, case, "lcts", 20, 0)`; the plant states its `range` and `options` | `{"best": Value, "feasible": bool, "history": [...], "evaluations": int}`; `result["best"]["plant"]` is the best `gm.Plant`, `best.parts["parameters"]` is `{name: Quantity}`. `feasible` says whether `best` has no reason in its verdict that a design can change; with no feasible trial `best` is the least violating one that ran |
| Simulate | `gm.simulate(plant, case, plan=None, ...)` | `gm.Results`, planned by `gm.schedule(plant, case)` |
| Report | `gm.evaluate.report(plant, case, results)` | `Report`, a `dict`, below |
| Read a value | `report[key].to(unit)`, with `unit` a text of the table (`"GWh"`, `"MEUR"`, `"MEUR/yr"`, `"EUR/MWh"`, `"kt"`) | `Value`: `.value` a number or `None`, `.unit`, `.reason` (why `value` is `None`), `.parts`, `.si` |
| Compare | `gm.evaluate.compare(reports, by=["lcts", "co2"])` | `Comparison`, below |
| Uncertainty | `gm.study.sample(plant, case, ["lcts", "co2"], samples, seed)`: the case declares `uncertainty` next to its numbers | `Sample` `{samples, summary}`, `summary[metric]` `{mean, p5, p50, p95, failed}`, each draw with a `feasible` flag; a case with none raises `missing_value` |
| Why steps failed | `gm.evaluate.failures(results)` | `Failures`: `groups` of `{path, code, kind, count, first, last, message}`, most frequent first; `to_dict()`, `to_frame()`; `report["failures"]` holds it |
| Table | `comparison.to_frame()` | a DataFrame, one row per report, columns `<metric> [<unit>]` in display units (MWh, MW, MEUR, MEUR/yr, EUR/MWh, kt; `to_frame(units={"lcts": "EUR/MWh"})` chooses another), `rank_<metric>`, `pareto` and `feasible` |
| Sensitivity | `gm.study.sensitivity(plant, case, ["lcts"])`: the case declares `uncertainty` next to its numbers | a list of `{parameter, metric, low, high, at_low, at_high, effect, feasible_low, feasible_high}`; `.to_frame(units=None)` a DataFrame of columns `parameter, metric, low, high, at_low, at_high, effect, unit`, the metric in its display unit or the one in `units` |
| Save | `report.to_dict(units=None)`, `comparison.to_dict()`, `Comparison.from_dict(data)`, and `to_dict()` / `from_dict` of `Best`, `Sample`, `Tornado`; `failures.to_dict()` | plain JSON (`json.dumps` works); the report in display units (MWh, MW, MEUR, EUR/MWh, kt, m3/h, degC) or `{metric: unit}`; `str(report)` is that JSON; values inside stay SI. `Best.to_dict()` and `Sample.to_dict()` (and the history of a search in `Study` results) are in the same display units, from the one table `gm.units.display` with `evaluate/_utils/display.py` (a long span in yr, a difference of temperature in K, listed in the `differences` key of the result when there are any); `from_dict` reads them back to the same values (equal after conversion, not bit for bit). The `value` of a note of `plant.sizing` is a `Quantity` in display units (capacity in MW, flow in m3/h) and its `reason` text uses them |

`Report` is a `dict` subclass with these keys, each a `Value` in SI unless said: `heat_delivered`,
`cold_delivered`, `boiler_heat`, `electricity_bought`, `gas_bought` (J over the run),
`capacities` (`{path: {kind, capacity, peak, share}}`), `capex`, `opex`, `lcts`, `lcoh`, `lcoc`,
`co2`, `services` (the list of services the plant is asked to deliver, `"heating"` and `"cooling"`), `verdict` (the `Verdict` of `gm.evaluate.verdict`), `requirements` (a list of `{name, role, unit_path, quantity, passed, value, limit,
worst_step}`; `value` and `limit` are `Value`s), `passed` (`False` if any requirement failed,
`True` if none failed and one passed, else `None`) and `failed_steps` (an `int`). Its costs are
read with `on_error="record"`: a cost the case or the plant cannot give has `value` `None` and a
`reason`, and a plant that does not show a quantity (a cold delivered with no cooling grid) says so
in `reason`. `report.to_dict(units=None)` gives plain JSON with `{value, unit}` for every `Value`, in display units, its parts too: the annualised cost in MEUR/yr (`opex` components and `lcts` parts through the one display table), an energy per year in MWh/yr, a mass in kt, a duration in days, except `analysis_period`, `payback` and `lifetime_years` in yr, and a temperature difference (a requirement on `lift`, `approach`, `brine_cooling`) in K. A `units` map reaches the parts of the same SI unit, so `co2="t"` shows its kg parts in t; the values inside stay SI.

`Comparison` is a `list`, one entry per report in the order given: `{index, values, ranks,
pareto, feasible}` and, for an infeasible report, `reasons`. `values` are the metrics as `gm.units.Quantity` in SI
(a plain number stays a float, `None` for no value; only `to_frame` converts to display units), `ranks` start at 1
(equal values share a rank, the feasible come before the infeasible), `pareto` is `True` when no
other feasible report is at least as good in every metric and better in one. A report is
feasible when the `verdict` of its report has no reason (`gm.evaluate.verdict`); `reasons` are
those of the verdict. A dict without a `verdict`, such as a table of figures, is feasible. `by` is a name, a list of names or `{metric: "min" | "max"}`; a report without a value
of a metric ranks last for it and is never on the front.

What the calls do not do, honestly: `fluids` remains in a plant dict for a plant with no case; consumer
return pressure stays a design parameter of the plant; a search varying the doublets, flow or depth
leaves the injection pump at the rating of `size`.

## Errors

Every public call raises on failure by default. A call that can report instead takes
`on_error="raise" | "record"`: `validate` functions return the problems, `gm.call` returns them
under `errors`, a run records them in `results.errors()` and continues, a cost value is
`{value: null, reason}`. `gm.evaluate.*` checks return a check; a violated limit never raises.

`gm.errors` holds seven error classes and `GeminiWarning`, listed with their use in [errors.md](errors.md):
`GeminiError` with `ValidationError`, `DefinitionError`, `PhysicsError`, `RunError`, `Cancelled` and
`NotImplementedYet`. `to_dict()` is the problem
`{path, code, message, suggestions}` (schema `problem`; the return shape of an error, not an
input), `error.problems` lists every problem of an error, `CODES` is the fixed `code` list
and `ROW_CODES` the row codes with their meaning.

## Names and signatures

Every public name with its signature, one row each: the names of `gm.__all__`, of the `__all__` of
each folder, and the methods that `tests/fixtures/capture_public_api.py` pins. `tests/unit/test_api_contract.py`
fails when a public name is missing from this table, when a row names something that does not exist,
and when a signature differs from the code (parameter names, kinds and defaults; a default with no
written form is `...`). The module classes of the catalogue (`gm.modules.names()`) and the plant
classes are one row each, expanded by category: see [equipment.md](equipment.md) and
[plants.md](plants.md#registered-plants). What each name returns is in the sections above.

### Top level

| Name | Signature | Kind |
| --- | --- | --- |
| `gm.BRINE` |  | value |
| `gm.Case` | `(**found)` | class |
| `gm.Dataset` | `(frame, units=None)` | class |
| `gm.Engine` | `(plant, backend='numpy', callbacks=None, on_error='raise', compile=True)` | class |
| `gm.Fluid` | `(*, kind='brine', salinity=0.0, co2_mass_fraction=0.0, gas_mass_fraction=0.0, gas_liquid_ratio=None, gas_composition=None, grid_composition=None, glycol_fraction=0.0, property_model='constant_stp', density=None, viscosity=None, specific_heat=None, thermal_conductivity=None)` | class |
| `gm.Inlet` | `(type=..., *, kind=None, many=False, drawn=None, description=None)` | class |
| `gm.Module` | `()` | class |
| `gm.Outlet` | `(type=..., *, kind=None, many=False, drawn=False, offered=False, description=None)` | class |
| `gm.Output` | `(type, *, soft_sensor=False, description=None)` | class |
| `gm.Parameter` | `(type, *, default=UNSET, shape=None, calibratable=False, structural=False, case=None, description=None, **bounds)` | class |
| `gm.Plant` | `(name=None)` | class |
| `gm.Results` | `(declared=None)` | class |
| `gm.Stream` | `(**data)` | class |
| `gm.Study` | `(found, name, files=None, folder=None, about=None)` | class |
| `gm.WATER` |  | value |
| `gm.call` | `(module, parameters, inlets, controls, units, on_error='raise', state=None, dt=None)` | function |
| `gm.check` | `(plant, case)` | function |
| `gm.live` | `(plant, source, checkpoint, step=None, now=None, sink=None, backend='numpy', callbacks=None, on_error='raise')` | function |
| `gm.replay` | `(plant, data, start=None, end=None, state=None, clock=None, only=None, checkpoint=None, checkpoint_every=None, backend='numpy', callbacks=None, on_error='raise')` | function |
| `gm.resume` | `(checkpoint, callbacks=None)` | function |
| `gm.schedule` | `(plant, case)` | function |
| `gm.simulate` | `(plant, case=None, plan=None, clock=None, checkpoint=None, checkpoint_every=None, backend='numpy', callbacks=None, on_error='raise', compile=True)` | function |
| `gm.analysis` |  | module |
| `gm.case` |  | module |
| `gm.compiler` |  | module |
| `gm.errors` |  | module |
| `gm.evaluate` |  | module |
| `gm.modules` |  | module |
| `gm.ops` |  | module |
| `gm.physics` |  | module |
| `gm.plants` |  | module |
| `gm.runtime` |  | module |
| `gm.streams` |  | module |
| `gm.study` |  | module |
| `gm.units` |  | module |

### Methods of the main classes

| Name | Signature | Kind |
| --- | --- | --- |
| `gm.Case.to_dict` | `()` | method |
| `gm.Case.from_dict` | `(data, files=None, folder=None)` | method |
| `gm.Case.schema` | `()` | method |
| `gm.Case.to_json` | `(path)` | method |
| `gm.Case.from_json` | `(path)` | method |
| `gm.Case.check` | `()` | method |
| `gm.Case.files` | `()` | method |
| `gm.Case.field` | `(path)` | method |
| `gm.Case.leaf` | `(path)` | method |
| `gm.Case.with_value` | `(path, number)` | method |
| `gm.Study.from_dict` | `(data, files=None, folder=None)` | method |
| `gm.Study.from_json` | `(path)` | method |
| `gm.Study.to_dict` | `()` | method |
| `gm.Study.to_json` | `(path)` | method |
| `gm.Study.check` | `()` | method |
| `gm.Study.run` | `(plants=None, *, on_progress=None)` | method |
| `gm.Plant.add` | `(type, name=None, params=None)` | method |
| `gm.Plant.connect` | `(source, target, type=None)` | method |
| `gm.Plant.constrain` | `(target, by, bounds, equals=None, at_least=None)` | method |
| `gm.Plant.set_inputs` | `(values)` | method |
| `gm.Plant.input_value` | `(path)` | method |
| `gm.Plant.target_of` | `(source)` | method |
| `gm.Plant.source_of` | `(target)` | method |
| `gm.Plant.feeds` | `(source)` | method |
| `gm.Plant.check` | `()` | method |
| `gm.Plant.set_range` | `(path, min=None, max=None)` | method |
| `gm.Plant.set_options` | `(path, options)` | method |
| `gm.Plant.summary` | `()` | method |
| `gm.Plant.to_dict` | `(structure=False)` | method |
| `gm.Plant.from_dict` | `(data)` | method |
| `gm.Plant.to_json` | `(path, structure=False)` | method |
| `gm.Plant.from_json` | `(path)` | method |
| `gm.Module.describe` | `()` | method |
| `gm.Module.parameter_schema` | `()` | method |
| `gm.Module.validate_params` | `(params, on_error='raise')` | method |
| `gm.Module.help` | `()` | method |
| `gm.Module.set_params` | `(path, params, valid_from=None)` | method |
| `gm.Module.params_at` | `(path, time=None)` | method |
| `gm.Module.param_history` | `(path)` | method |
| `gm.Module.bindable` | `(path)` | method |
| `gm.Module.set_bindings` | `(path, bindings)` | method |
| `gm.Module.get` | `(path)` | method |
| `gm.Module.get_submodule` | `(path)` | method |
| `gm.Module.named_modules` | `(prefix='')` | method |
| `gm.Engine.simulate` | `(profile, clock=None)` | method |
| `gm.Engine.replay` | `(data, start=None, end=None, state=None, clock=None, only=None)` | method |
| `gm.Engine.live` | `(source, checkpoint=None, step=None, now=None, sink=None)` | method |
| `gm.Engine.to_checkpoint` | `(path)` | method |
| `gm.Engine.from_checkpoint` | `(path, callbacks=None)` | method |
| `gm.Engine.resume` | `()` | method |
| `gm.Results.names` | `()` | method |
| `gm.Results.get` | `(path, field, start=None, end=None, units=None)` | method |
| `gm.Results.summary` | `(path=None, start=None, end=None, units=None)` | method |
| `gm.Results.errors` | `()` | method |
| `gm.Results.to_frame` | `(units=None, table='series')` | method |
| `gm.Results.to_dict` | `(units=None)` | method |
| `gm.Results.to_npz` | `(path)` | method |
| `gm.Results.from_npz` | `(path)` | method |
| `gm.Results.to_bytes` | `()` | method |
| `gm.Results.from_bytes` | `(data)` | method |
| `gm.Results.energy_report` | `(units=None)` | method |

### gm.modules

| Name | Signature | Kind |
| --- | --- | --- |
| `gm.modules.Module` | `()` | class |
| `gm.modules.ModuleList` | `(modules=())` | class |
| `gm.modules.ModuleDict` | `(modules=())` | class |
| `gm.modules.trace_wiring` | `(plant, inputs)` | function |
| `gm.modules.names` | `(category=None)` | function |
| `gm.modules.get` | `(name)` | function |
| `gm.modules.categories` | `()` | function |
| `gm.modules.check` | `(example=None)` | function |
| `gm.modules.no_outputs` | `()` | function |
| `gm.modules.Parameter` | `(type, *, default=UNSET, shape=None, calibratable=False, structural=False, case=None, description=None, **bounds)` | class |
| `gm.modules.Inlet` | `(type=..., *, kind=None, many=False, drawn=None, description=None)` | class |
| `gm.modules.Control` | `(type, *, default=UNSET, description=None, **bounds)` | class |
| `gm.modules.Boundary` | `(type, *, case=None, **kwargs)` | class |
| `gm.modules.State` | `(type, *, default=UNSET, description=None, **bounds)` | class |
| `gm.modules.Output` | `(type, *, soft_sensor=False, description=None)` | class |
| `gm.modules.Outlet` | `(type=..., *, kind=None, many=False, drawn=False, offered=False, description=None)` | class |
| `gm.modules.<Equipment>` | | catalogue |

### gm.plants

| Name | Signature | Kind |
| --- | --- | --- |
| `gm.plants.Plant` | `(name=None)` | class |
| `gm.plants.capabilities` | `()` | function |
| `gm.plants.schema` | `()` | function |
| `gm.plants.names` | `(category=None)` | function |
| `gm.plants.roles` | `()` | function |
| `gm.plants.get` | `(name)` | function |
| `gm.plants.<Plant class>` | | catalogue |

### gm.case

| Name | Signature | Kind |
| --- | --- | --- |
| `gm.case.Case` | `(**found)` | class |
| `gm.case.Time` | `(given, start, end, step)` | class |
| `gm.case.Site` | `(leaves=None, values=None, children=None, about=None)` | class |
| `gm.case.Ground` | `(leaves=None, values=None, children=None, about=None)` | class |
| `gm.case.Reservoir` | `(leaves=None, values=None, children=None, about=None)` | class |
| `gm.case.Fluid` | `(leaves=None, values=None, children=None, about=None)` | class |
| `gm.case.Air` | `(leaves=None, values=None, children=None, about=None)` | class |
| `gm.case.Demand` | `(leaves=None, values=None, children=None, about=None)` | class |
| `gm.case.Service` | `(leaves=None, values=None, children=None, about=None)` | class |
| `gm.case.CoolingService` | `(leaves=None, values=None, children=None, about=None)` | class |
| `gm.case.Utilities` | `(leaves=None, values=None, children=None, about=None)` | class |
| `gm.case.Electricity` | `(leaves=None, values=None, children=None, about=None)` | class |
| `gm.case.Gas` | `(leaves=None, values=None, children=None, about=None)` | class |
| `gm.case.Economics` | `(leaves=None, values=None, children=None, about=None)` | class |
| `gm.case.Capex` | `(leaves=None, values=None, children=None, about=None)` | class |
| `gm.case.DepthTable` | `(given, depth, cost)` | class |
| `gm.case.Opex` | `(leaves=None, values=None, children=None, about=None)` | class |
| `gm.case.Energy` | `(leaves=None, values=None, children=None, about=None)` | class |
| `gm.case.Carbon` | `(leaves=None, values=None, children=None, about=None)` | class |
| `gm.case.Revenue` | `(leaves=None, values=None, children=None, about=None)` | class |
| `gm.case.Subsidy` | `(leaves=None, values=None, children=None, about=None)` | class |
| `gm.case.Accounting` | `(leaves=None, values=None, children=None, about=None)` | class |
| `gm.case.Gwp` | `(leaves=None, values=None, children=None, about=None)` | class |
| `gm.case.Requirement` | `(given, **values)` | class |
| `gm.case.Range` | `(min=None, max=None)` | class |
| `gm.case.Uncertainty` | `(kind, min=None, max=None, std=None)` | class |
| `gm.case.from_csv` | `(path, columns, unit)` | function |
| `gm.case.missing` | `(case)` | function |
| `gm.case.from_values` | `(values, unit, start, step, quantity)` | function |
| `gm.case.profile_schema` | `()` | function |

### gm.units

| Name | Signature | Kind |
| --- | --- | --- |
| `gm.units.Quantity` | `(value, unit)` | class |
| `gm.units.Unit` | `(*values)` | class |
| `gm.units.names` | `(quantity=None)` | function |
| `gm.units.convert` | `(value, from_unit, to_unit, quantity=None)` | function |
| `gm.units.fits` | `(unit, quantity)` | function |

### gm.streams

| Name | Signature | Kind |
| --- | --- | --- |
| `gm.streams.Stream` | `(**data)` | class |
| `gm.streams.Fluid` | `(*, kind='brine', salinity=0.0, co2_mass_fraction=0.0, gas_mass_fraction=0.0, gas_liquid_ratio=None, gas_composition=None, grid_composition=None, glycol_fraction=0.0, property_model='constant_stp', density=None, viscosity=None, specific_heat=None, thermal_conductivity=None)` | class |
| `gm.streams.Ports` | `(values=None, *, path='module')` | class |
| `gm.streams.BRINE` |  | value |
| `gm.streams.WATER` |  | value |
| `gm.streams.GLYCOL_30` |  | value |
| `gm.streams.STEAM` |  | value |

### gm.runtime

| Name | Signature | Kind |
| --- | --- | --- |
| `gm.runtime.settings` | `(backend=..., **changes)` | function |
| `gm.runtime.state` | `()` | function |

### gm.analysis

| Name | Signature | Kind |
| --- | --- | --- |
| `gm.analysis.nodal` | `(plant, well, conditions, on_error='raise', units=None)` | function |
| `gm.analysis.pump_curve` | `(plant, pump, measured=None, units=None)` | function |
| `gm.analysis.corrosion_forecast` | `(model, until, units=None)` | function |
| `gm.analysis.fit_head_coefficients` | `(flows, frequencies, heads, stage_count, units=None)` | function |
| `gm.analysis.fit_head_correction` | `(measured, theoretical, units=None)` | function |
| `gm.analysis.estimate_reservoir_pressure` | `(flows, bottomhole_pressures, units=None)` | function |
| `gm.analysis.estimate_conductance` | `(hot_in_T, hot_out_T, cold_in_T, cold_out_T, m_dot_hot, m_dot_cold, *, cp_hot, cp_cold, arrangement, units=None)` | function |

### gm.evaluate

| Name | Signature | Kind |
| --- | --- | --- |
| `gm.evaluate.totals` | `(plant, case, results)` | function |
| `gm.evaluate.capacities` | `(plant, case, results)` | function |
| `gm.evaluate.daily_coverage` | `(plant, case, results)` | function |
| `gm.evaluate.metrics` | `()` | function |
| `gm.evaluate.report` | `(plant, case, results)` | function |
| `gm.evaluate.compare` | `(reports, by)` | function |
| `gm.evaluate.failures` | `(results)` | function |
| `gm.evaluate.energy_balance` | `(plant, case, results)` | function |
| `gm.evaluate.mass_balance` | `(plant, case, results)` | function |
| `gm.evaluate.plant_balance` | `(plant, case, results)` | function |
| `gm.evaluate.collect_flows` | `(result_tree)` | function |
| `gm.evaluate.call_emissions` | `(result_tree, fuel_factor, electricity_factor)` | function |
| `gm.evaluate.call_energy_balance` | `(module, result)` | function |
| `gm.evaluate.call_mass_balance` | `(module, result)` | function |
| `gm.evaluate.bounds` | `(plant, case, results)` | function |
| `gm.evaluate.requirements` | `(plant, case, results)` | function |
| `gm.evaluate.verdict` | `(plant, case, results)` | function |
| `gm.evaluate.capex` | `(plant, case, on_error='raise', *, units='si')` | function |
| `gm.evaluate.opex` | `(plant, case, results, on_error='raise', *, units='si')` | function |
| `gm.evaluate.lcoh` | `(plant, case, results, on_error='raise', *, units='si')` | function |
| `gm.evaluate.lcoc` | `(plant, case, results, on_error='raise', *, units='si')` | function |
| `gm.evaluate.lcts` | `(plant, case, results, on_error='raise', *, units='si')` | function |
| `gm.evaluate.annualised_cost` | `(plant, case, results, on_error='raise', *, units='si')` | function |
| `gm.evaluate.co2` | `(plant, case, results, on_error='raise')` | function |
| `gm.evaluate.npv` | `(plant, case, results, on_error='raise', *, units='si')` | function |
| `gm.evaluate.payback` | `(plant, case, results, on_error='raise', *, units='si')` | function |

### gm.study

| Name | Signature | Kind |
| --- | --- | --- |
| `gm.study.minimize` | `(plant, case, objective, evaluations, seed, *, plan=None, on_progress=None)` | function |
| `gm.study.sample` | `(plant, case, metrics, samples, seed, *, plan=None, on_progress=None)` | function |
| `gm.study.Sample` |  | class |
| `gm.study.size` | `(plant, case)` | function |
| `gm.study.sensitivity` | `(plant, case, metrics, *, plan=None, on_progress=None)` | function |
| `gm.study.Tornado` | `(iterable=(), /)` | class |
| `gm.study.Study` | `(found, name, files=None, folder=None, about=None)` | class |
| `gm.study.StudyResult` | `(study, runs, comparison, best, cases)` | class |
| `gm.study.Run` | `(plant_name, case_name, verdict, metrics, plant, source, report, results, found=None, note=None)` | class |
| `gm.study.kinds` | `()` | function |
| `gm.study.calibrate` | `(plant, dataset, params, start=None, end=None, backend='numpy', apply=True)` | function |
| `gm.study.CalibrationResult` | `(fitted, rms_before, rms_after, observations, success, message, applied, initial, rms_by_output_before, rms_by_output_after, evaluations)` | class |

### gm.errors

| Name | Signature | Kind |
| --- | --- | --- |
| `gm.errors.CODES` |  | value |
| `gm.errors.ROW_CODES` |  | value |
| `gm.errors.GeminiError` | `(*args, path=None, code=None, suggestions=(), problems=())` | class |
| `gm.errors.GeminiWarning` |  | class |
| `gm.errors.ValidationError` | `(*args, path=None, code=None, suggestions=(), problems=())` | class |
| `gm.errors.DefinitionError` | `(*args, path=None, code=None, suggestions=(), problems=())` | class |
| `gm.errors.PhysicsError` | `(*args, path=None, code=None, suggestions=(), problems=())` | class |
| `gm.errors.RunError` | `(*args, path=None, code=None, suggestions=(), problems=())` | class |
| `gm.errors.Cancelled` | `(*args, path=None, code=None, suggestions=(), problems=())` | class |
| `gm.errors.NotImplementedYet` | `(*args, path=None, code=None, suggestions=(), problems=())` | class |

### gm.compiler

| Name | Signature | Kind |
| --- | --- | --- |
| `gm.compiler.compile` | `(plant)` | function |

### gm.ops

| Name | Signature | Kind |
| --- | --- | --- |
| `gm.ops.Constant` | `(name, value, unit, description)` | class |
| `gm.ops.Failed` | `(error)` | class |
| `gm.ops.Operators` | `()` | class |
| `gm.ops.Symbolic` | `()` | class |
| `gm.ops.abs` | `(value)` | function |
| `gm.ops.acos` | `(value)` | function |
| `gm.ops.add` | `(left, right)` | function |
| `gm.ops.any_nan` | `(*values)` | function |
| `gm.ops.asin` | `(value)` | function |
| `gm.ops.atan` | `(value)` | function |
| `gm.ops.atan2` | `(left, right)` | function |
| `gm.ops.brentq` | `(function, low, high, args=(), xtol=2e-12, rtol=8.881784197001252e-16, maxiter=100)` | function |
| `gm.ops.ceil` | `(value)` | function |
| `gm.ops.check` | `(condition, error, message, code=None, **values)` | function |
| `gm.ops.check_numbers` | `(function, **values)` | function |
| `gm.ops.clip` | `(first, second, third)` | function |
| `gm.ops.control` |  | module |
| `gm.ops.cos` | `(value)` | function |
| `gm.ops.cosh` | `(value)` | function |
| `gm.ops.cumsum` | `(values)` | function |
| `gm.ops.dispatch` | `(name, *operands, attributes=None)` | function |
| `gm.ops.eq` | `(left, right)` | function |
| `gm.ops.exp` | `(value)` | function |
| `gm.ops.expm1` | `(value)` | function |
| `gm.ops.floor` | `(value)` | function |
| `gm.ops.floordiv` | `(left, right)` | function |
| `gm.ops.ge` | `(left, right)` | function |
| `gm.ops.getitem` | `(value, index)` | function |
| `gm.ops.gt` | `(left, right)` | function |
| `gm.ops.interp` | `(x, xp, fp)` | function |
| `gm.ops.isfinite` | `(value)` | function |
| `gm.ops.isinf` | `(value)` | function |
| `gm.ops.isnan` | `(value)` | function |
| `gm.ops.le` | `(left, right)` | function |
| `gm.ops.log` | `(value)` | function |
| `gm.ops.log10` | `(value)` | function |
| `gm.ops.logical_and` | `(left, right)` | function |
| `gm.ops.logical_not` | `(value)` | function |
| `gm.ops.logical_or` | `(left, right)` | function |
| `gm.ops.lt` | `(left, right)` | function |
| `gm.ops.maximum` | `(left, right)` | function |
| `gm.ops.mean` | `(values)` | function |
| `gm.ops.minimum` | `(left, right)` | function |
| `gm.ops.mod` | `(left, right)` | function |
| `gm.ops.mul` | `(left, right)` | function |
| `gm.ops.ne` | `(left, right)` | function |
| `gm.ops.neg` | `(value)` | function |
| `gm.ops.newton` | `(function, start, derivative, args=(), tolerance=1e-06, max_iterations=100)` | function |
| `gm.ops.physics` | `(function)` | function |
| `gm.ops.require` | `(value)` | function |
| `gm.ops.pow` | `(left, right)` | function |
| `gm.ops.register_backend` | `(backend)` | function |
| `gm.ops.round` | `(left, right)` | function |
| `gm.ops.scope` |  | module |
| `gm.ops.sign` | `(value)` | function |
| `gm.ops.sin` | `(value)` | function |
| `gm.ops.sinh` | `(value)` | function |
| `gm.ops.sqrt` | `(value)` | function |
| `gm.ops.sub` | `(left, right)` | function |
| `gm.ops.sum` | `(values)` | function |
| `gm.ops.tan` | `(value)` | function |
| `gm.ops.tanh` | `(value)` | function |
| `gm.ops.truediv` | `(left, right)` | function |
| `gm.ops.where` | `(first, second, third)` | function |

### gm.physics

| Name | Signature | Kind |
| --- | --- | --- |
| `gm.physics.chemistry` |  | module |
| `gm.physics.combustion` |  | module |
| `gm.physics.constants` |  | module |
| `gm.physics.corrosion` |  | module |
| `gm.physics.cycles` |  | module |
| `gm.physics.diagnostics` |  | module |
| `gm.physics.energy` |  | module |
| `gm.physics.erosion` |  | module |
| `gm.physics.fluid` |  | module |
| `gm.physics.gas` |  | module |
| `gm.physics.geometry` |  | module |
| `gm.physics.ground` |  | module |
| `gm.physics.heat_transfer` |  | module |
| `gm.physics.hydraulics` |  | module |
| `gm.physics.psychrometrics` |  | module |
| `gm.physics.pumps` |  | module |
| `gm.physics.refrigeration` |  | module |
| `gm.physics.separation` |  | module |
| `gm.physics.steam` |  | module |

## Change log

The lines of the unreleased changes are in the order the work was done; the first two below sum
them up (the correctness work, then the study release), and a later line wins over an earlier one
where they differ (several older lines name `gm.Problem`, `gm.kpi` or `gm.optim`, which are gone).

| Version | Date | Change |
| --- | --- | --- |
| 0.5.5 | 2026-11-02 | **First published package, no API change** (the frozen file unchanged). `pydantic>=2.10.0` is required, `doc` of `describe` has no indentation on every Python, and each new version on `dev` goes to a GitHub Release and `ghcr.io`. |
| 0.5.4 | 2026-11-02 | **Fixes and additions, two on purpose** (every number is the same to 1e-9; no example verdict changes; the frozen `public_api_0_5_0.json` is unchanged). Two fixes change behaviour for inputs 0.5.0 accepted: `gm.evaluate.verdict` makes a requirement that could not be judged (`passed` None) beside a passed one a reason of kind `requirement`, so the run is infeasible (it was feasible; no `violation`, so a search ranks as before; not a reason: a `when="running"` requirement on a unit that never ran, and the supply of a service already reported as not delivered; `report`, `compare` and `Study` read this verdict); `nominal_flow` of `Doublet` and `InjectionPump` at zero or below raises `out_of_bounds` (`gt=0`; empty stays allowed). Added: `gm.study.sample` items have `feasible`; `gm.study.sensitivity` rows have `feasible_low` and `feasible_high`; both are in `to_dict` and read by `from_dict` (which also reads a 0.5.3 result without them); `summary`, `Tornado.to_frame` and the row order are unchanged; each trial runs one more verdict. |
| 0.5.3 | 2026-11-02 | **Additions for the app, no break** (same release, the frozen file unchanged). `Case.schema()` and `Economics.schema()` give `kind` as `{"type": "string", "const": ...}` (a generated header is read) and gain `x-` keys: `x-quantity`, `x-units`, `x-limits` (SI bounds with the SI unit) and `x-fraction` on a leaf, `x-quantities` on the file; `gm.evaluate.metrics()` entries gain `title` and `objective`; `gm.study.kinds()`; `units="display"` (and `"si"`) on `Results.get`, `summary`, `to_frame`, `to_dict`, `energy_report`, on `Comparison.to_dict` and, keyword only, on `capex`, `opex`, `annualised_cost`, `lcoh`, `lcoc`, `lcts`, `npv`, `payback` (value and parts in display units); `gm.case.missing(case)`; `gm.plants.capabilities()[class]["ranges"]` lists every numeric leaf of `params`. **Addition, no break** (the frozen `public_api_0_5_0.json` is unchanged and `test_api_compatibility` is green; the working snapshot gains the code `deprecated`). A `range` on a case or economics leaf (or series leaf) is deprecated: `case.check()`, `economics.check()`, `gm.check` and `Study.check` report it as an `Issue` of kind `deprecated` (a warning, last in the list, `Issue.is_warning`), and reading the case emits `gm.errors.GeminiWarning`. Reading, `simulate`, `size` and the studies are unchanged (`raise_issues` skips warnings) and every number is the same; the issue keys are unchanged. A caller that treats a non-empty `gm.check` list as not ready should skip `issue.is_warning`. |
| 0.5.2 | 2026-11-02 | **Additions for the frontend, no break** (`public_api_0_5_0.json` is unchanged and `test_api_compatibility` is green). `on_progress=None`, keyword only, on `gm.study.minimize`, `sample`, `sensitivity` and `gm.Study.run`: `on_progress(done, total)` after each finished trial in the calling process, also with `processes=n`; raising `gm.errors.Cancelled` from it stops the study (later trials do not start, the workers are stopped); not given, the call is that of 0.5.1 and the numbers are equal. `gm.evaluate.daily_coverage(plant, case, results)`: per day and service, demand, geothermal, backup and short energy in display units. `gm.evaluate.metrics()`: the metric names with their quantity and display unit. |
| 0.5.1 | 2026-11-02 | **Additions and fixes, no break** (the frozen `public_api_0_5_0.json` is unchanged and `test_api_compatibility` is green; the working snapshot only changed its version). Time is a scan: a stateful plant carries its state from step to step in one call over the whole run, eager and compiled, with the same numbers to 1e-9. State connections (`connect(source, target, type="state")`, a connection of type `state` in the plant file, no new key) are built; the plant keeps the previous values in its state. `minimize`, `sample` and `sensitivity` run their trials on one shared plant as one array pass; the sequence of trials and every result are those of 0.5.0. A module takes the fluid of its inlet stream (`ThermalStorage`, `InjectionReservoir`), so `gm.call` works on them with `state` and `dt`; the modules that still need `module.fluid` (a source, the offers of `ChemicalGrid` and `AquiferStorage`) raise `missing_value` naming it. `gm.check` never raises. New page [writing-a-module.md](writing-a-module.md). |
| 0.4.0 | 2026-11-02 | **Folders by job** (rules and tree in [structure.md](structure.md)). Moves only, numbers equal to 1e-9; no old path is kept. Public names, old -> new: `gm.data.from_csv`, `from_values`, `profile_schema` -> `gm.case.from_csv`, `from_values`, `profile_schema` (`gm.data` is gone); `gm.analysis.calibrate`, `CalibrationResult` -> `gm.study.calibrate`, `CalibrationResult`; `gm.case.roles()` -> `gm.plants.roles()`; `gm.modules.collect_flows`, `emissions`, `energy_balance`, `mass_balance` -> `gm.evaluate.collect_flows`, `call_emissions`, `call_energy_balance`, `call_mass_balance`; `gm.physics.dispatch`, `gm.physics.doublet`, `gm.physics.costs` removed (the dispatch policy is `engine/schedule/`, the doublet design `plants/_utils/`, the price `evaluate/_utils/pricing.py`); `circuit_flow`, `temperature_after` -> `gm.physics.energy`; `hydraulics.pipe_path_profile`, `corrosion_profile` -> `modules/wells/_physics.py` (they take a `Stream`), `hydraulics.erosion_check` -> `gm.physics.erosion.pipe_path_erosion_check(path, mass_flow, density)`; the PID relations are `gm.physics.control` (new module); `gm.streams` joins `gm.__all__` (`Stream`, `Fluid`, `Ports`, `BRINE`, `WATER`, `GLYCOL_30`, `STEAM`); `gm.run` and `gm.types` are gone (nothing public lived there). `gm.evaluate.<name>`, `gm.analysis.nodal`, `pump_curve` and the rest are unchanged. Examples move from `inputs/examples/<name>/` to `examples/<name>/`, test data from `inputs/` to `tests/fixtures/`. |
| 0.5.0, before the freeze | | **Readable units in `gm.call` and the study results; burned gas; state door.** `gm.call(module, parameters, inlets, controls, units, on_error="raise", state=None, dt=None)`: `units` is required, `"si"` or `"display"`, and replaces the map `{quantity: unit}`; the result has a key `state`; a module with state takes `state` and `dt`. `Best.to_dict()`, `Sample.to_dict()`, the history of a search and the notes of `gm.study.size` are in display units. New plant quantity `gas_burned` (kg/s) of the role `plant`. `runtime.settings(default_fluid=)` is removed (the fluid is `site.fluid` or a plant `fluids` entry; a module or `gm.Stream` without one raises `missing_value`). Module contract: `forward(self, inputs, inlets, state)` is pure and a stateful module has a pure `update(self, inputs, inlets, outlets, state, dt)`; a stateful plant scans its steps in time. Hooks are `(module, inputs, inlets, state)` and `(module, inputs, inlets, state, outputs, outlets)`, and a returned mapping replaces the controls (pre-hook) or outputs (forward hook) of the call. `gm.physics.control` is new. A physical failure of a simulated step (`invalid_inlet`, `out_of_bounds`, `out_of_range`, `no_convergence`) is a failed row whatever `on_error` says; a trial of a search that fails a step is infeasible instead of raising. |
| 0.5.0, before the freeze | | **Physics of pumps and power in `gm.physics`.** `modules/pumps/_physics.py` and `modules/power/_physics.py` are gone: `head`, `pump_efficiency`, `esp_efficiency`, `line_shaft_friction_power` are in `gm.physics.pumps`; the intercooled compression (`isentropic_outlet_temperature`, `stage_outlet_temperature`, `stage_pressure_ratio`, `overall_pressure_ratio`, `specific_compression_work`, `shaft_power`, `heat_rejected`) is in `gm.physics.gas`; the IAPWS-IF97 steam, flash and turbine functions are the new `gm.physics.steam`; `lorenz_efficiency`, `cycle_design`, `plant_balance` are the new `gm.physics.cycles`. |
| 0.5.0 | 2026-11-02 | **Backward compatible from here.** Last breaking change, old -> new: `gm.evaluate.run_all` -> `gm.evaluate.verdict` (`{feasible, reasons}` replaces `{passed, checks}`); `gm.physics.control` -> private `modules/control/_physics.py`. `gm.evaluate.call_*` and `gm.ops` stay (reasons in the freeze rule). New tests: `test_api_compatibility.py` with the frozen `public_api_0_5_0.json`, `test_competition_surface.py`. |
| 0.3.0 | 2026-11-02 | **Inputs by owner.** `gm.Case` has the sections `time`, `initial_state`, `site`, `demand`, `utilities`, `economics` and `requirements`; `economics.json` holds all money; the plant file is `kind: plant`, `format: 1` with the design space (`range`, `options`) and the controls as leaves; `gm.Study` and `study.json` record a run. `gm.case.Choices`, `Constraint`, `Assumptions` and `Finance` are removed, `gm.evaluate.constraints` is `requirements`, `gm.plants.validate` and `missing_parameters` are `check()`. |
| 0.3.0 | 2026-11-02 | **Signatures `(plant, case, ...)`.** `gm.check(plant, case)` is new and runs first in `simulate` and every study function. Removed arguments, no alias: `discount_rate` and `lifetime` of the costs (the economics file owns them), `constraints` and `variables` of `minimize` (the case and the plant own them; `evaluations` and `seed` have no default), `backup` of `size`, `time_column` of `gm.case.from_csv`; `sample(..., count)` is `samples`. `Case.from_dict(data, files=None, folder=None)`, `Economics.from_dict(data, files=None, time=None)`. Every signature, old and new, is in the table below the change log. |
| 0.3.0 | 2026-11-02 | **Return shapes.** `capabilities()[class]["ranges"]` replaces `"choices"`; the cost parts `lifetime_years` are `analysis_period`; the result of `minimize` has no `fixed`; `report` has `requirements` and `verdict`; `docs/schemas/plant.*` replace `plant_dict.*` and `study.*` is new; a checkpoint of 0.2.0 is refused (`old_format`). The public-API snapshot gains `gm.check`, `gm.schedule` and the methods of `Study`, and this page the table "Names and signatures", which a test compares with the code. |
| 0.2.0, unreleased changes | | **Correctness.** One unit format at every public door: a bare number with a dimension raises `invalid_value` in `set_params`, `Plant.add`, `validate_params`, `Plant.set_inputs`, `Stream(...)`, `Fluid(...)`, `gm.call`, `gm.modules.check` and `Atmosphere.ambient_air`; `gemini` uses the private `_set_si_params`, `_set_si_inputs`, `Stream._si` and `Fluid._si`, and a plant class that derives overrides `_set_si_params`. The stored `fluids` and `param_history` of a plant dict are `{"value", "unit"}`. No module hides a default: a declaration has none unless it is a sourced constant or the zero of an accumulator (`DECLARED_DEFAULTS` in `tests/unit/test_code_quality.py`), `None` switches a feature off, and a `State` without a default takes the parameter `initial_<state>`; `ESP` and `InjectionPump` lost theirs, `Doublet` has the parameter `roughness`. `ESP` has the outputs `intake_pressure` and `gas_volume_fraction`; roles gain `doublet.intake_pressure` and `intake_gas_fraction`, `heat_output` (`heat_pump`, `boiler`, `chp`), `cold_output` (`chiller`) and the role `plant` (`electricity_bought`, `gas_bought`, `heat_surplus`, `co2`). `report.to_dict` converts the parts too. `gm.plants.validate` takes a `Plant`. |
| 0.2.0, unreleased changes | | The study release. New: `gm.study.size(plant, case, backup)` (the policy has no default; rated units carry their duty; the notes list what the start breaks); `plant.missing_parameters()` and one error that lists every missing path with its meaning; the `uncertainty` of the case and `gm.case.Uncertainty`, `Sample`, `Tornado`; `gm.evaluate.failures(results)`, also in the report; `to_dict()` / `from_dict` of `Best`, `Sample`, `Tornado`, `Comparison`, `Report`; `report.to_dict(units=None)` in display units; `gm.runtime.settings(processes=n)` for parallel trials, one compiled graph for all trials of a study. `Comparison` values are `Quantity`. An `ESP` row outside its curve or over its speed-scaled `maximum_flow` fails with `out_of_range`; a run with failed steps is no valid design: a trial of a study is infeasible and its metrics are `None` with a reason, and `summary[metric]["failed"]` of `sample` counts the draws left out; an `InjectionPump` with a setpoint below its suction does not pump (`is_pumping`). Removed, with no alias: `gm.plants.example`, `gm.case.synthesize`, `gm.analysis.injectivity`, `calibrate_pump`, `calibrate_corrosion`, `erosion` (stubs that only raised `NotImplementedYet`; a name returns when it is built, the list is in [refactor-notes.md](refactor-notes.md#planned-features-removed-from-the-api)). Callers move with the table below. |
| 0.2.0, unreleased changes | | **The case.** `gm.Case` and the folder `gm.case` replace `gm.Problem`, `gm.Constraint` and `gm.Assumptions`; `gm.__all__` has `Case` and `case` and no `Problem`, `Constraint` or `Assumptions`; `gm.optim` is `gm.study`. Every call takes `(plant, case)`, plus `results` when it reads a run: `gm.schedule(plant, case)`, `gm.simulate(plant, case=None, plan=None, ...)`, `gm.evaluate.*`, `gm.study.*`. The input file is `case.json` with CSV profiles, not `problem.json`. A plant dict holds only the plant: the ground, reservoir, brine, air, return and supply temperatures are the case's, set on a copy of the plant by module class, and a plant dict that states one is refused. Nothing a user must decide has a default: an absent value raises `missing_value` (`missing_assumption` below `assumptions`). One unit format: a `Quantity` or `{"value", "unit"}`, no unit text anywhere, `gm.units.parse` is gone. Costs on every equipment kind, `capacities`, `report`, `compare`, `gm.study.size`, `sensitivity` and `gm.plants.capabilities` are built. Known limits: bare SI numbers remain accepted in `set_params`, `gm.call`, `gm.Stream` and `gm.Fluid`; `fluids` remains in the plant dict for a plant with no case; the consumer return pressure stays a plant parameter. |
| 0.2.0, unreleased changes | | `gm.Problem`, `gm.Constraint`, `gm.Assumptions` and `Problem.apply_site` are removed. `gm.schedule(plant, case)` and `gm.simulate(plant, case=None, plan=None, ...)` take a `gm.Case`: a run sets the values of the case on a copy of the plant by class (ground on `Formation`, reservoir and brine on each `Doublet` at its depth, air on `Atmosphere`, the return and the required supply temperature on `HeatingGrid` and `CoolingGrid`), and the schedule finds its limits by role and quantity (`doublet`, `production_flow`, `brine_cooling`). A value the plant needs and the case lacks raises `missing_value` (`missing_assumption` for a price) naming its path in the case. |
| 0.2.0, unreleased changes | | A parameter that the case holds (`Doublet.gradient`, `surface_temperature`, `permeability`, `thickness`, `Formation.geothermal_gradient`, `surface_temperature`, `HeatingGrid` and `CoolingGrid` `return_temperature` and `minimum_supply_temperature` or `maximum_supply_temperature`) is refused in a plant dict (`invalid_value`, naming the case path) and never written by `to_dict`. A value with a unit in a plant dict, `params` or `inputs`, is a `{"value", "unit"}`, and `to_dict` writes it so. `HeatingGrid`, `CoolingGrid` and `Cooler` carry water. An engine checkpoint of a plant stores its plant dict and its `state_dict`. |
| 0.2.0, unreleased changes | | New `gm.Case` and the folder `gm.case` (`Case`, `Time`, `Environment`, `Ground`, `Reservoir`, `Fluid`, `Air`, `Demand`, `Service`, `Choices`, `Range`, `Constraint`, `Assumptions`, `Finance`, `Capex`, `Opex`, `Revenue`, `Allocation`, `Emissions`, `CO2`, `CH4`, `roles()`): a strict, frozen, SI-stored entry boundary with `to_dict`, `from_dict`, `schema`, `from_json`, `to_json`. New `gm.physics.ground.reservoir_temperature` and `reservoir_pressure`; `gm.units` gains `EUR/m3`, the type `MoneyPerVolume`. The folder `gm.optim` is renamed `gm.study`. `gm.Problem`, `gm.Constraint` and `gm.Assumptions` stay until the schedule, the run and `gm.evaluate` are ported to `gm.Case`. |
| 0.2.0, unreleased changes | | Costs on every equipment kind. A module that is equipment declares `equipment_kind` (one of `gm.case.Capex`'s 19 kinds) and `capex(finance)` and `fixed_opex(finance)` in the currency of the case; grids, environment, control, mixers, splitters and valves have none. `Doublet` is the `production_pump` and the wells are `drilling`; a `HeatPump` in cooling mode is a `compression_chiller`. A factor or a fixed share the case lacks is `missing_assumption` naming `assumptions.finance.capex.<kind>` or `assumptions.finance.opex.fixed.<kind>`. `gm.evaluate.*` take `(plant, case, results, ...)`; `capex` gives the sum and each module in `parts["modules"]`, `opex` the fixed opex by kind in `parts["fixed_by_kind"]` (no variable opex any more), `co2` and the CO2 price follow the profiles of the case step by step. `constraints` checks the constraints by role and the supply temperatures of the services, each item `{name, role, unit_path, quantity, passed, value, limit, worst_step}` (the item had `path`). Built: `capacities`, `report` (a `dict` with `to_dict()`), `compare(reports, by)` (a list with `to_frame()`, ranks and `pareto`). `gm.types.Cost` is gone. `gm.case.legacy.results_to_frame` is `gm.case.legacy.to_frame`. |
| 0.2.0, unreleased changes | | `gm.study` takes the case: `minimize(plant, case, objective, variables=None, ...)` searches `case.choices` (`size.doublets` discrete, `depth`) by default, and a variable or a distribution may be a number of the case named `case.<path>`; `size`, `sensitivity` and `gm.plants.capabilities` are built. |
| 0.2.0, unreleased changes | | Examples: five flat scripts in `examples/` (`quickstart.py`, `hackathon.py`, `costs.py`, `uncertainty.py`, `plant.py`); `examples/basics`, `recipes` and `cases` are removed. The hackathon and shallow district samples hold a `case.json`; the hackathon candidates are in `plants/`. |
| 0.2.0, unreleased changes | | The COP estimate of the cost dispatch reads the module's `carnot_fraction`, or `lorenz_fraction` for a Lorenz machine, which it had read as the Carnot default. The default 0.5 cites H. U. Frutschi, ABB Review 5/1996, pp. 33-34; the sample plants state it. |
| 0.2.0, unreleased changes | | `plan.attrs["check_only"]` lists a constraint the schedule enforces in part with only the bounds left: a duration of `min` and `max`, of `equals` and another bound, or a brine cooling with a `min`. |
| 0.2.0, unreleased changes | | A `Doublet` with a `depth` and no `gradient` or `surface_temperature` when a run or a schedule starts raises `ValidationError` code `missing_value` with the path of each value, whatever `on_error` says; `missing_parameters` lists them. |
| 0.2.0, unreleased changes | | Private paths only: `gm.call` is `gemini/modules/call.py`, so no run folder imports above the run, in a function or not. No change to a name of this page. |
| 0.2.0, unreleased changes | | One folder per concern, flat public names. Top level: `gemini/modules`, `plants`, `physics`, `ops`, `runtime`, `engine`, `run`, `types`, `units`, `errors`, `data`, `study`, `evaluate`, `analysis`, `compiler`, `_utils`; `gm.__all__` is pinned. The folders `core`, `base`, `registry`, `testing`, `backends`, `checks`, `economics`, `profiles`, `utils` and `graph` at the top are gone. Run folders import none of `compiler`, `data`, `study`, `evaluate`, `analysis`; importing `gm.compiler` registers its executor, and a run works without it. |
| 0.2.0, unreleased changes | | One `gm.Problem` for every call: `gm.Problem`, `gm.Constraint`, `gm.Assumptions`, with `to_dict`, `from_dict`, `schema`; `Problem.from_json`, `to_json`, `apply_site`. `gm.schedule(plant, problem)`; `gm.simulate(plant, problem=None, plan=None, ..., compile=True)`; every `gm.evaluate` function takes `(plant, problem, results, ...)`, `gm.study.minimize` and `sample` `(plant, problem, ..., *, plan=None)`. A schedule loads sources by marginal cost and reads its limits from constraints; `attrs["check_only"]` lists the constraints it does not enforce. `Assumptions.prices` and `co2_price` replace the six flat price fields. A `Doublet` with a `depth` and no geotherm waits for the site. |
| 0.2.0, unreleased changes | | `gm.evaluate.constraints` replaces `Limits`, `limits` and `operating_time`; `gm.evaluate.totals` also gives `heating_coverage`, `cooling_coverage`, `cop`, `peak_heat` and `peak_cold`, the former `gm.kpi.compute`. `gm.checks.*`, `gm.economics.*` and `gm.kpi.*` are `gm.evaluate.*`, `gm.profiles.*` is `gm.case.*`, `calibrate` and `CalibrationResult` are in `gm.analysis`. |
| 0.2.0, unreleased changes | | Naming: readers `from_<format>`, writers `to_<format>`. `Plant.save`, `load` are `to_json`, `from_json`; `gm.plants.from_dict` is `gm.Plant.from_dict`; `gm.plants.convert_legacy` is `gm.Plant.from_legacy`, which returns a plant; `Results.save`, `load` are `to_npz`, `from_npz`; `Engine.save_checkpoint`, `load_checkpoint` are `to_checkpoint`, `from_checkpoint`; `Module.load_state_dict` is `set_state_dict`. `gm.evaluate(...)` is `gm.call(...)`; `gm.testing.check_module` is `gm.modules.check`. `gm.runtime` has `settings` and `state` only. |
| 0.2.0, unreleased changes | | A module class that states a `category` registers itself; `gm.modules.register` and `load_file` are gone, `abstract = True` leaves a class out. New codes `duplicate_name` and `conflicting_value`. Plant classes are in `gm.plants`, not `gm.modules`. |
| 0.2.0, unreleased changes | | New names whose work lands later: `gm.plants.capabilities`, `gm.case.synthesize`, `gm.evaluate.capacities`, `report`, `compare`, `gm.study.size`, `sensitivity`. New: `gm.compiler.compile`, `gm.ops.register_backend`. |
| 0.2.0, unreleased changes | | `InjectionPump.efficiency` has no default: without a value or head and power curves it raises `missing_value`. |
| 0.2.0, unreleased changes | | gemini knows no sample problem. Removed: `gm.challenge_rules`, `HackathonPlant`, `gm.profiles.demand`, `gm.profiles.get`, `gm.profiles.names`, `gm.checks.operating_days`, `rules["operating_days"]`, `attrs["outage_days"]`, and `inputs/hackathon/`, now `examples/hackathon_2026/`. New: `gm.profiles.from_csv`, `gm.profiles.from_values`, `gm.checks.operating_time`, `rules["operating_time"]`, `attrs["outages"]`, `rules` on `gm.study.minimize` and `sample`, where `profile=None` now raises. `gm.schedule` has no default for `doublet_flow` or `max_brine_cooling`, and works on any constant step. `gm.plants.example` of the five template plants raises `NotImplementedYet`. `Doublet.gradient` and `surface_temperature` have no default: a `depth` without them raises `missing_value`. `gm.checks.run_all` takes `duration`. `normal_density` takes its reference conditions. `profile_schema` describes columns, time and values only. |
| 0.2.0, unreleased changes | | `gm.study.minimize` respects the case: a trial is feasible when no step fails and every constraint of the case passes; the result gains `feasible` and `fixed`, a `history` item has `reason` (the first failed check) and `parts["violation"]`, and the search ranks every feasible trial before every infeasible one. A variable `<role>.<parameter>` (a role of `gm.plants.roles()`, for example `heat_pump.capacity`, `doublet.nominal_flow`) reaches every unit of the role after the doublet count; `depth` on a plant with no depth of its own is every doublet's; a role the plant lacks and `size.doublets` on a plant without it go to `fixed`, and `invalid_design` is raised only when nothing is left to search. `gm.study.size` gives a heat pump the part of the heating peak the reservoir cannot reach, not the peak, and rates the `InjectionPump`. `InjectionPump` has `nominal_flow` and `nominal_head` and is priced as `injection_pump`. `gm.evaluate.compare` entries gain `feasible` and `reasons`, feasible reports rank first and the front holds only feasible ones; `report` gains `services`. `to_frame(units=None)` of `Comparison` and of the sensitivity shows display units (MWh, MW, MEUR, EUR/MWh, kt), columns `<metric> [<unit>]`. Prices of `examples/hackathon_2026/case.json` cited: electricity, gas and CO2. |
| 0.2.0, unreleased changes | | `make sandbox-image` builds `gemini-sandbox:<version>`, the image of geomind's module sandbox, from `docker/sandbox.Dockerfile`. |
| 0.2.0, unreleased changes | | `gm.analysis.nodal` solves injection wells: the wellhead pressure of a rate, or the rate of a wellhead pressure. |
| 0.2.0, unreleased changes | | `gm.challenge_rules()` and `gm.profiles.demand()`. `profile=None` in `gm.study.minimize` and `sample` is the demand year under the challenge rules, and a demand frame is planned for each trial. Reading a finished run no longer builds the JSON of every column. |
| 0.2.0, unreleased changes | | `gm.plants.example` of the five template plants holds the challenge values on two doublets, with `inputs`, and runs the demand year (`examples/cases/challenge_year.py`); a value file may state `size`. A plan states the unit of its columns in `attrs["units"]`, and a run reads them: a binding in another unit no longer misreads a plan. On a root plant, which has no ports, a failing row is now an error: it passed unnoticed on a traced plant. A stopped drive circuit of `AdsorptionChiller` has no driving-temperature limit. |
| 0.2.0, unreleased changes | | `Doublet.volume_imbalance` and `InjectionReservoir.liquid_flow`. `gm.checks.Limits` takes a parameter. `gm.checks.limits` on a run whose every row failed gives `passed: null` with a reason `no_value` instead of a `KeyError`. |
| 0.2.0, unreleased changes | | `HeatingGrid.surplus` and `CoolingGrid.surplus`, what the water gives above the demand. `gm.kpi.totals` adds `heat_useful`, `heat_surplus`, `cold_useful`, `cold_surplus`; `gm.kpi.compute`, `gm.economics.lcoh`, `lcoc` and `lcts` read the useful energy. `HackathonPlant`, `HeatingCoolingPlant`, `HeatingFullCoolingPlant` and `HeatingAbsorptionCoolingPlant` return the drive water of their chillers through a bypass past the users (`loads` and `heat_return`, `drive_splitter` and `drive_mixer`), a loop the engine closes, and `gm.schedule` sets its split: the heating supply stays at its setpoint. |
| 0.2.0, unreleased changes | | `gm.schedule` finds roles from the wiring: a unit that feeds the `CoolingGrid` is a cooling unit, a `HeatPump` included. `rules["cooling_order"]`, heat-driven first by default, dispatches absorption, adsorption and compression chillers, each up to its capacity. `Plant.feeds`. |
| 0.2.0, unreleased changes | | Template plants take `size={"doublets": n}`, 1 to 3: `doublet` is now `d0`, with `d1`, `d2`, `production_mixers` and `injection_splitters`, and a plant-level `depth`. `Doublet.gradient` and `surface_temperature` default to the challenge values. |
| 0.2.0, unreleased changes | | `Plant.set_inputs`, `Plant.input_value`, `Plant.target_of`, `Plant.source_of`. The plant dict has one key `inputs`, `{path: value}`, in both forms; `gm.plants.from_dict`, `gm.schedule` and a run use it. `boundary[""]["inputs"]` and `boundary[""]["root_inputs"]` are gone: a plant inlet field is the path `port.field`. |
| 0.2.0, unreleased changes | | Leaves compute, plants connect. `_compute_outputs` is gone: a leaf computes once in `forward`. Every composite is a `Plant`, which never writes `forward`, with `HeatingSubstation`, `CoolingSubstation`, `NodalDoublet`, `DistrictEnergyPlant`, `BoilerChpPlant`, `ParallelExchangerPlant` and `ATESPlant` among them. The engine closes loops (`loop_not_converged`) and solves `Plant.constrain`. `CirculationPump` carries the flow of a building circuit, and its electricity is counted. Plant outputs are `Output.difference`, `Output.ratio` and `Output.sum` of paths; `Results` reads a path. |
| 0.2.0, unreleased changes | | No JSON file in `gemini/`: `gemini/assets/` is gone. A plant of a class stores `{type, size?, params}`, `to_dict(structure=True)` its structure. Templates are the plant classes `HeatingPlant`, `HeatingCoolingPlant`, `HeatingFullCoolingPlant`, `HeatingAbsorptionCoolingPlant` and `HeatingHeatPumpCoolingPlant`, and `DistrictNetwork` and `MultiWellPlant` take their size. Removed names are listed below. Code `loop_without_state` and `migration_failed` are gone, `loop_not_converged` is new. |
| 0.2.0, unreleased changes | | `gm.study.minimize` and `gm.study.sample` are built, on the metrics of `gm.kpi` and `gm.economics`; each takes `assumptions`. |
| 0.2.0, unreleased changes | | `gm.evaluate`: a volume unit on `m_dot` names `flow` in its message, `path` and `suggestions`; the code stays `invalid_call`. |
| 0.2.0, unreleased changes | | `gm.economics.annualised_cost` and `gm.economics.lcts`, the levelised cost of heat and cold together. |
| 0.2.0, unreleased changes | | `rules["operating_days"]` of `gm.schedule` is built: a count or a list of outage dates, `attrs["outage_days"]`, the column `<heat pump>.is_running`. New `gm.checks.operating_days`, since replaced; `gm.checks.run_all` takes `days`. |
| 0.2.0, unreleased changes | | File layout of `gemini/modules/`: `plant.py` and `container.py` beside `module.py`, the plant tools in `plants/_utils/`, `heating/_burner.py`, `cooling/_sorption.py`. Private paths only: no change to a name of this page. |
| 0.2.0, unreleased changes | | Data layout: `gemini/assets/` (installed: plant structures, templates) and `inputs/` (repository only: hackathon inputs, example values, measured data, legacy project); `datasets/` is gone. New code `inputs_missing`: `gm.profiles.get` and `gm.plants.example` raise it outside a source checkout. Templates `DistrictNetwork` and `MultiWellPlant` are now `district_network` and `multi_well`. `gm.plants.example("Doublet")` is the registered class, with the outputs of its structure file. No change to a name of this page. |
| 0.2.0, unreleased changes | | Plants `NodalDoublet`, `ParallelExchangerPlant`, `BoilerChpPlant`, `DistrictEnergyPlant`, `HackathonPlant`: catalogue only, no change to a name of this page. |
| 0.2.0, unreleased changes | | `gm.kpi.totals(plant, results)`: heat and cold delivered, electricity bought and sold, gas bought, emissions, waste, chemicals and losses, read from the ports of the edge modules. The hackathon example has all seven edge modules, a desander and inhibitor dosing. |
| 0.2.0, unreleased changes | | `gm.checks.plant_balance(plant, run)`: a `Check` of mass and of energy per module and for the plant, whose in and out are the ports of the grids and environment modules. `Flare` has `fuel` and `loss_out`. |
| 0.2.0, unreleased changes | | Port quantities are in `Results`: `<port>.mass_flow`, `.volume_flow`, `.temperature`, `.pressure`, `.enthalpy_flow`, `.gas_flow`, `.co2_flow`, `.chemical_flow`, and a `Power` port under its name. Outputs a port shows are gone (`useful_duty`, `condenser_duty`, `electricity`, `electricity_generated`, `heat_loss`, `heat_supplied`, ...), and so are automatic sums, the `sum` key of a plant's `outputs` and the quantities `ElectricityGenerated`, `HeatLoss`, `HeatSupplied` and `HeatAbsorbed`. `gm.kpi` and `gm.economics` read the edge modules; `waste_disposal_price`, `chemical_price`. |
| 0.2.0, unreleased changes | | Port names follow `<role>_in` and `<role>_out` (`gm.plants.migrate` converts stored specs). `Inlet(Stream, kind=...)` replaces `stream=`, the first argument of a declaration is `type`, `p.add(type, ...)`, `p.connect(source, target, type=None)`, a connection's `type: "state"`; `describe()` gives ports `{kind, fields}`, outputs `{unit, quantity, soft_sensor}`, connections `{source, target, kind, type}`. |
| 0.2.0, unreleased changes | | Losses are ports: wells, pipes, storage, boilers, `CHP`, `ORC`, `FlashTurbine`, `CentrifugalPump`, `GasCompressor`, `BoreholeField` and `DownholeHeatExchanger` have `loss_out`, signed, to `Atmosphere.heat_in` or `Formation.heat_in`; `DistrictNetwork` and `ATESPlant` expose one `loss_out`. |
| 0.2.0, unreleased changes | | Category `environment`: `Atmosphere` holds the ambient conditions and computes `co2_emission` and `methane_emission`; `Formation` is created by `Doublet`. `Vent` is gone: its inlet connects to `Atmosphere.gas_in`. `Boiler`, `CHP` and `Flare` have `flue_out`; `Pipe`, `Cooler`, `ThermalStorage` and `ORC` have `air_in` instead of `ambient_temperature`; `Cooler` has `air_out` and may close a water loop (`loop_pressure`, `flow`). |
| 0.2.0, unreleased changes | | Category `grids`: `ElectricityGrid` (from `GridConnection`, without prices), `GasGrid`, `HeatingGrid` (from `HeatConsumer`), `CoolingGrid` (from `CoolingConsumer`), `WasteGrid`, `ChemicalGrid`; category `demand` removed. `GasMakeup` has `gas_in`, `grid_in`, `fuel_out`, `excess_out`; a burner's `fuel_in` shows what it burned and `gas_out` is gone. `gm.schedule` writes `<grid>.flow`. `validate` reports `root_plant_port`. |
| 0.2.0, unreleased changes | | Ports carry a `Power`: `Inlet(Power, kind="electricity")`, `Outlet(Power, kind="heat")`; `many=True`, `drawn=True`, `offered=True`; consumers get `power_in`, generators `power_out`; a plant port may list several ends. `gm.streams.names()` adds `heat`, `air`, `waste`, `chemical`. |
| 0.2.0, unreleased changes | | Layout: helpers in `gemini/modules/_utils/`, physics of one category in its `_physics.py`. Public names unchanged. |
| 0.2.0, unreleased changes | | One unit format. New `gm.units.Unit`, a `str` enum generated from the unit table, and `gm.units.Quantity(value, unit)` is the one shape of a value with a dimension: `.si`, `.to(unit)`, `to_dict`, `from_dict`, equality on SI. Removed: `gm.units.parse`, `split_quantity`, and every reading of unit text: `"150 m3/h"` is `ValidationError` `invalid_value` in `set_params`, the plant dict, `gm.call`, `gm.Stream`, `gm.Fluid`, `gm.Problem`, `gm.Constraint` and `gm.Assumptions`, which take a `Quantity` or `{"value", "unit"}`. A unit of another dimension is `invalid_unit` and lists the units of the field; the schema of a parameter with a unit offers `{"value": number, "unit": enum}`. New units `yr`, `%/yr`, `g/kWh`, `kg/J`, `J/yr`, `1/yr`, `EUR`, `EUR/MWh`, `EUR/kWh`, `EUR/kg`, `EUR/t`, `EUR/W`, `EUR/m`, `EUR/(W/K)` (the currency is a label: nothing converts between currencies), and quantities `MoneyPerMass`, `MoneyPerPower`, `MoneyPerLength`, `MoneyPerConductance`, `MassPerEnergy`, `AnnualEnergy`, `AnnualRate`. `currency/year` is `currency/yr`. |
| 0.2.0, unreleased changes | | `Assumptions`: `co2_price`, `electricity_emission_factor` and every cost factor are a `Quantity` (the price profile `{"unit", "values"}` is a `Quantity` with an array), and a bare number raises. `Constraint` bounds, `Problem.site` values and the `gm.study` variables, limits and distributions are `Quantity` for a field with a unit. `Assumptions.emission_factor()` gives the factor in SI. |
| 0.2.0, unreleased changes | | `Results.units` is `{"<path>.<field>": unit}` for every column of `to_frame`; the former `{path: {field: unit}}` is `Results.declared` (and the constructor argument). New units `MWh`, `GWh`, `TWh`, `MJ`, `GJ`, `GW`, `kt`, `Mt`, `kg/yr`, `t/yr`, `kt/yr`, `Mt/yr`, `kWh/yr`, `MWh/yr`, `GWh/yr`, `kEUR`, `MEUR`, `EUR/J`, `EUR/yr`, `kEUR/yr`, `MEUR/yr`. |
| 0.2.0, unreleased changes | | Outputs: each value of `gm.evaluate`, each check `value` and `limit`, and the results of `gm.study.minimize` and `sample` are a `Value`, a `Quantity` in SI with `reason` and `parts`; `to_plain` gives the JSON of before, with `currency` for money and `yr` for years. `Value` and `measure` are in `gemini/units/shapes.py`. `gm.study.minimize` returns `Value` objects, not JSON. |
| 0.2.0, unreleased changes | | Behaviour users see, no name changed: `gm.analysis.estimate_conductance` requires `cp_hot`, `cp_cold` and `arrangement`; `years_left` returns years (`yr`); on the Python backend `ops.maximum` and `ops.minimum` return NaN for a NaN operand and `ops.floor` and `ops.ceil` return floats, as on NumPy; `ops.brentq` raises the `PhysicsError` of a failed check instead of swallowing it; `gm.call` reports an error raised inside `forward` as itself, not as `invalid_value`; `report()["boiler_heat"]` is a value with no number and a reason where the run has no series of a boiler; the plant dict schema offers a number or a quantity for an input, no unit string. |
| 0.2.0 | 2026-10-31 | Demand profiles: `gm.profiles.get` reads the two organiser files of 2027; `profile_schema` describes what `get` returns. |
| 0.2.0 | 2026-10-31 | No dangling ports: an unconnected port is `unconnected_port`; plant ports exist only when named, the automatic `<path>_<port>` ports are gone. |
| 0.2.0 | 2026-10-31 | A module may set its children's values: every parameter route reaches an overridden `set_params`; `to_dict` stores no derived value. |
| 0.2.0 | 2026-10-31 | `Fluid`: `density` and `viscosity` replace `liquid_density` and `liquid_viscosity`; `gas_liquid_ratio`, `gas_composition`, `kind="gas"`; reservoirs lose both parameters. |
| 0.2.0 | 2026-10-31 | Gas chain: `Boiler` and `CHP` get `fuel_in` and `gas_out`; `ElectricBoiler` replaces `fuel_type="electric"`; `GasGrid`, `GasMakeup`, `Flare`; `gm.economics.co2` sums the emission outputs; `gas_price` and `methane_gwp` replace `fuel_price` and `fuel_emission_factor`; code `missing_assumption`. |
| 0.2.0 | 2026-10-31 | `gm.plants.Doublet`: a doublet designed from its depth; `gm.modules.get("Doublet")` gives that class. |
| 0.2.0 | 2026-10-31 | Two-phase well check: the gas superficial velocity follows the gas mass flow, at the gas density of the section. |
| 0.2.0 | 2026-10-31 | `gm.schedule`; a root inlet field binds to a column named `port.field`. |
| 0.2.0 | 2026-10-31 | `gm.checks.Limits` and `gm.checks.limits`; `Doublet.flow`, `Doublet.brine_cooling`, `HeatConsumer.supply_in_T`, `ProductionReservoir.liquid_flow`, `InjectionWell.wellhead_temperature`, `Output.difference`. |
| 0.2.0 | 2026-10-31 | Costs: `capex(assumptions)` on equipment, cost factors in `Assumptions`, `heat_cost_share`. |
| 0.2.0 | 2026-10-31 | Hackathon example `examples/cases/hackathon.py`. |
| 0.2.0 | 2026-10-31 | Version 0.2.0: a checkpoint written before 0.2.0 raises `old_format`; `gm.plants.migrate` converts its plant file. |
| 0.1.0 | 2026-10-30 | First consistent API. |

Names changed in 0.3.0, old and new (the old column is the code before the inputs task):

**Signatures**


| Old (0.2.0) | New (0.3.0) |
| --- | --- |
| `gm.evaluate.lcoh`, `lcoc`, `lcts`, `annualised_cost`, `npv` `(plant, case, results, discount_rate=None, lifetime=None, on_error="raise")` | `(plant, case, results, on_error="raise")`: `economics.discount_rate` and `economics.analysis_period` of the case are the only source |
| `gm.study.minimize(plant, case, objective, variables=None, constraints=None, evaluations=100, *, plan=None)` | `gm.study.minimize(plant, case, objective, evaluations, seed, *, plan=None)`: `variables` is the `range` and `options` leaves of the plant, `constraints` is the `requirements` of the case (nothing real needed the argument), `evaluations` and `seed` have no default; the result has no `fixed` |
| `gm.study.sample(plant, case, metrics, count, seed, *, plan=None)` | `gm.study.sample(plant, case, metrics, samples, seed, *, plan=None)` |
| `gm.study.size(plant, case, backup=None)` | `gm.study.size(plant, case)`: the policy is `params.backup` of the plant |
| `gm.case.from_csv(path, columns, unit, time_column=None)` | `gm.case.from_csv(path, columns, unit)`: the first column is named `time` |
| `gm.Case.from_dict(data, folder=None)` | `gm.Case.from_dict(data, files=None, folder=None)`: series and economics from `files` (`{name: bytes}`), else from `folder` |
| (none) | `gm.case.Economics.from_dict(data, files=None, time=None)`, `from_json(path, time=None)`, `to_json`, `check`, `schema`, `drilling_cost_per_metre(length)`: the file `economics.json`, held as `case.economics` |
| `gm.Case(*, time, environment=None, demand=None, choices=None, constraints=None, assumptions=None, uncertainty=None)` | `gm.Case(**found)`, built by `from_dict` or `from_json`; no pydantic methods (`model_dump`, `model_copy`, `copy`, `json`, ...): `to_dict`, `with_value` |
| `gm.Plant.to_json(path)` | `gm.Plant.to_json(path, structure=False)` |
| `gm.case.Range(min=None, max=None, *, unit=None)`; `gm.case.Uncertainty(*, kind, min, max, std)`; `gm.case.Time(*, start, end, step)` | `Range(min=None, max=None)` (the bounds are in the unit of the leaf); `Uncertainty(kind, min=None, max=None, std=None)`; `Time.from_dict({...})` |
| `gm.modules.Boundary(type, *, default=UNSET, description=None, **bounds)` | `gm.modules.Boundary(type, *, case=None, **kwargs)`: a boundary that the case owns names its path |
| `gm.case.Constraint(*, on, quantity, over='each', when='always', min=None, max=None, equals=None)` | `gm.case.Requirement` `(name, on, quantity, over?, when?, min, max)`, built by `Requirement.from_dict`; `equals` is `min` = `max`; `over` is absent for a window quantity |
| `gm.case.Environment(ground, reservoir, fluid, air)`; `Fluid(gas=)`; `Air(temperature)` | `gm.case.Site(ground, reservoir, fluid, air)`; `Fluid.dissolved_gas`; `Air(temperature, relative_humidity, pressure)` |
| `gm.case.Demand(file, time_column, heating, cooling)`; `Service(column, unit, supply_temperature, return_temperature)` | `gm.case.Demand(heating, cooling)`; `Service`, `CoolingService`: `power` (a series), the supply and return conditions of the consumer |
| `gm.case.Assumptions(finance, emissions)`, `Finance`, `Allocation`, `Emissions`, `CO2`, `CH4`, `Capex`, `Opex(fixed, electricity, gas, chemical, waste_disposal, co2)`, `Revenue(heat, cold)` | `gm.case.Economics` with `Capex`, `Opex(fixed, variable)`, `Energy`, `Carbon`, `Revenue(heat, cold, subsidy)`, `Subsidy`, `Accounting`, `Gwp`, `DepthTable`; `gm.case.Utilities` with `Electricity`, `Gas` |
| `gm.case.Choices(doublets, depth)` | removed: a `range` on `size.doublets` and `params.depth` of the plant file (`plant.set_range`) |
| `gm.evaluate.constraints` | `gm.evaluate.requirements` (the same arguments); new `gm.evaluate.verdict` |
| `gm.plants.validate(data, on_error="raise")`; `Module.missing_parameters()`, `Plant.missing_parameters()` | `plant.check()` (a list of issues, never raises); `Plant.from_dict` raises the same issues |
| (none) | new: `gm.Study`, `gm.check(plant, case)`, `gm.study.Study`, `StudyResult`, `Run`; `Case.check`, `files`, `field`, `leaf`, `with_value`; `Plant.check`, `set_range`, `set_options`, `ranges`, `options`, `size`; `Study.from_dict(data, files=None, folder=None)`, `from_json`, `run(plants=None)`, `check`, `to_dict`, `to_json`, `schema` |

**Return shapes and files**


| Old (0.2.0) | New (0.3.0) |
| --- | --- |
| `gm.plants.capabilities()[class]["choices"]` (`["doublets", "depth"]`) | `["ranges"]` (`["size.doublets", "params.depth"]`): the leaves of the plant file that may state a `range` |
| cost parts `lifetime_years` of `lcoh`, `lcoc`, `annualised_cost`, `npv` | `analysis_period` (in yr) |
| `report["constraints"]` | `report["requirements"]` and `report["verdict"]`; `compare` reads the verdict |
| result of `minimize` `{best, feasible, fixed, history, evaluations}` | `{best, feasible, history, evaluations}` |
| `docs/schemas/plant_dict.*` | `docs/schemas/plant.*`; new `study.*`; `case.*` and `economics.*` regenerated |
| plant dict `format: 2` without `kind`; keys `inputs`, `bindings`, flat dotted `params` | plant file `format: 1`, `kind: plant`; `params` a tree of leaf objects; a control is a leaf; `bindings` stay in memory; the key `inputs` is refused |
| `case.json` keys `environment`, `constraints`, `assumptions`, `choices`, `demand.file`, `time_column` | `site`, `requirements`, `economics` (a file), `utilities`, ranges in the plant, a series leaf with a `time` column: the old keys are refused with `old_format` |
| checkpoints written by 0.2.0 | refused with `old_format` (they hold a plant of `format: 2`) |

The rows below are the history of 0.2.0, whose replacements are themselves replaced by the rows above where they differ (`case.environment` is `case.site`, `gm.case.Constraint` is `gm.case.Requirement`, `gm.case.Assumptions` is `case.economics`).

Names removed or renamed in the unreleased changes of 0.2.0:

| Name | Replaced by |
| --- | --- |
| `gm.Problem`, `Problem.from_json`, `to_json`, `from_dict`, `to_dict`, `schema`, `apply_site`; `problem.json` | `gm.Case` and the same methods (`apply_site` is internal: a run sets the case on a copy by module class); `case.json` |
| `gm.Constraint(path, min, max, over, when)` | `gm.case.Requirement` (`name`, `on`, `quantity`, `over`, `when`, `min`, `max`): a role and a quantity of it, from `gm.plants.roles()`, not a module path |
| `gm.Assumptions(...)`: `prices`, `co2_price`, `electricity_emission_factor`, `methane_gwp`, `discount_rate`, `lifetime_years`, `heat_cost_share`, `currency`, the cost factors `drilling_cost`, `heat_pump_cost`, `boiler_cost`, ... | `gm.case.Assumptions(finance, emissions)`: `finance.opex.*`, `opex.co2`, `emissions.CO2.electricity`, `emissions.CH4.gwp`, `finance.discount_rate`, `lifetime`, `allocation.heat_cost_share`, `finance.currency`, `finance.capex.<kind>`, `finance.opex.fixed.<kind>`; no sourced defaults: the values are stated in the case |` | `case.economics` (`economics.json`): `discount_rate`, `analysis_period`, `capex.<kind>`, `opex.fixed.<kind>`, `opex.variable`, `energy.electricity`, `energy.gas`, `carbon.price`, `revenue`, `accounting.allocation.heat_cost_share`, `accounting.gwp.CH4`, `currency`; the CO2 intensity of electricity is `case.utilities.electricity.co2_intensity`; no sourced defaults: the values are stated in the case |
| `Problem.site`, `site` values by parameter path | `case.site` (ground, reservoir, fluid, air) |
| `gm.optim` | `gm.study`: `minimize`, `sample`, `size`, `sensitivity` |
| `gm.units.parse`, `gm.units.split_quantity`, every unit text such as `"150 m3/h"` | `gm.units.Quantity(150, "m3/h")` or `{"value": 150, "unit": "m3/h"}` |
| `gm.types.Cost`, `total_cost`, `scaled_cost`; `capex(assumptions)` returning a `Cost` | `capex(finance)` and `fixed_opex(finance)` of the mixin `Equipment` returning an amount; `gemini.physics.costs.scaled`; `gm.evaluate.capex` |
| `gm.case.legacy.results_to_frame(results, project)` | removed with `gm.case.legacy`, see [legacy.md](legacy.md) |
| `Results.units` as `{path: {field: unit}}` | `Results.declared`; `Results.units` is `{"<path>.<field>": unit}` for every column of `to_frame` |
| Plant dict keys and parameters the case holds: `Doublet.gradient`, `surface_temperature`, `permeability`, `thickness`; `Formation.geothermal_gradient`, `surface_temperature`; `HeatingGrid` and `CoolingGrid` `return_temperature` and the required supply temperature | `case.site.ground`, `reservoir`, `demand.<service>`: refused in a plant dict with `invalid_value` naming the case path |
| `Module.set_params("", {"length": 1500.0})`, `Plant.add(..., params={"length": 5.0})`, `Plant.set_inputs({"x.temperature_setpoint": 373.15})`, `Module.validate_params({"length": 5.0})` with a bare number for a value with a dimension | the same with a `Quantity` or `{"value", "unit"}`: `{"length": Quantity(1.5, "km")}`; a bare number raises `invalid_value`, a dimensionless value stays a number |
| `Stream(m_dot=10, T=300, p=1e5)`, `Stream(flow=2, ...)` (kg/s, K, Pa) | `Stream(m_dot=Quantity(10, "kg/s"), T=Quantity(300, "K"), p=Quantity(1, "bar"), fluid=BRINE)`; `flow` is a mass or a volume quantity |
| `Fluid(density=1068.0)` | `Fluid(density=Quantity(1068, "kg/m3"))`; a fraction or a ratio stays a number |
| `gm.call("M", {"length": 5}, {"p": {"m_dot": 12.0}}, {"frequency": 50.0})` | the same with quantities for `length`, `m_dot` and `frequency` |
| A class plant that overrides `set_params` to derive | override `_set_si_params(path, params, valid_from=None)`, which gets SI values |
| `Atmosphere.ambient_air(283.15)` | `ambient_air(Quantity(283.15, "K"))` |
| Defaults of `ESP` (`setting_depth`, `motor_efficiency`, `minimum_flow`, `maximum_flow`, `best_efficiency_flow`, `drift_threshold`, `pump_type`), of `InjectionPump.pump_type`, and of the other modules listed in `DECLARED_DEFAULTS` | the plant states them in its dict; `missing_parameters()` lists them; `None` where a feature is off |
| `gemini.physics.pumps.DEFAULT_BEP_FLOW`, `DEFAULT_INJECTION_PUMP_FREQUENCY`, `COMMERCIAL_STEEL_ROUGHNESS`, `DEFAULT_LORENZ_FRACTION`, `DEFAULT_MINIMUM_LIFT`, `DEFAULT_DRIFT_THRESHOLD`, `DEFAULT_DECLINE_THRESHOLD`, `DEFAULT_FOULING_THRESHOLD`, `DEFAULT_VALVE_RANGEABILITY`, `DEFAULT_WELL_U_VALUE`, `DEFAULT_CIRCULATION_PUMP_EFFICIENCY`, `HALF_YEAR`, `DOUBLET_WELL_SPACING`, `FILTER_NOMINAL_MASS_FLOW` | removed; `Doublet.roughness` is a parameter, `InjectionPump.frequency` defaults to the catalogue frequency `ESP_REFERENCE_FREQUENCY` |
| `report.to_dict()` parts in SI (`annualised_cost` in EUR/yr, `kg` parts of `co2`) | the parts in display units too: MEUR/yr, MWh/yr, kt, days |
| `gm.evaluate.requirements` item key `path` | `unit_path`, with `role` and `quantity` |
| `gm.evaluate.compare(plant, problem, results, other)` (a stub) | `gm.evaluate.compare(reports, by)` |
| `gm.plants.example(name)` | a stored plant dict, `gm.Plant.from_json(path)` (`examples/*/plants/*.json`, `tests/fixtures/doublet_heat/plant.json`), or the class `gm.plants.<Class>(...)` and `plant.missing_parameters()` to see what to `set_params` |
| `gm.study.size(plant, case)` | `gm.study.size(plant, case, backup="peak" or "none")`; the policy has no default |
| `gm.study.sample(plant, case, distributions, metrics, count, seed=0)` | `gm.study.sample(plant, case, metrics, count, seed)`: the distributions are the `uncertainty` of the case, a plant parameter is never drawn, `seed` has no default |
| `gm.study.sensitivity(plant, case, parameters, metrics)` | `gm.study.sensitivity(plant, case, metrics)`: every value the case declares an `uncertainty` for, at its `min` and `max` |
| A `Comparison` value as a `float` in display units | `gm.units.Quantity` in SI: `entry["values"]["lcts"].to("EUR/MWh").value`; `to_frame()` keeps the display units |
| `report.to_dict()` in SI | `report.to_dict(units=None)` in display units (MWh, MW, MEUR, EUR/MWh, kt, m3/h, degC), or `{metric: unit}`; the values inside the report stay SI |
| The plant dict key `pipe_path` of a well, the structural `esp_depth` | the lists `section_length`, `section_inclination`, `section_diameter`, `section_roughness`; `esp_depth` is an ordinary number |
| `example_plant(name)` read by a README or doc snippet | `gm.Plant.from_json(path)`; the test fixture stays in `tests/` |
| `gm.case.synthesize`, `gm.analysis.injectivity`, `calibrate_pump`, `calibrate_corrosion`, `erosion` | none: stubs removed, see refactor-notes |
| `examples/basics/`, `examples/recipes/`, `examples/cases/` | five flat scripts in `examples/` |
| `Module._compute_outputs` | `forward` assigns the outputs |
| `Output.of`, `Outlet.field` | a path: `results["sub.consumer.unmet_demand"]`, `results["sub.pipe.fluid_out.T"]`, `result.children[...]` |
| `Doublet.flow`, `.production_temperature`, `.injection_temperature`; the outputs of `ATESPlant`, `HeatingSubstation`, `CoolingSubstation`, `DoubletHeatPlant`, `BoilerChpPlant`, `ParallelExchangerPlant`, `DistrictEnergyPlant`, `MultiWellPlant`, `DistrictNetwork` | the same path below the plant: `d0.reservoir.liquid_flow`, `sub.consumer.unmet_demand` |
| `HeatingSubstation.building_flow`, `.building_pressure`, same on `CoolingSubstation` | `pump.flow`, `pump.loop_pressure`, with `pump.pressure_rise` |
| `ATESPlant.groundwater_pressure`, `.groundwater_flow` | `storage.groundwater_pressure`, `storage.groundwater_flow`, with `source_valve` and `load_valve` |
| `NodalDoublet.produce`, `.inject` | `Plant.constrain` in the class |
| `to_spec`, `from_spec`, `spec_schema` | `to_dict`, `from_dict`, `schema` |
| `gm.plants.templates`, `from_template` | `gm.plants.names(category=...)`, `gm.plants.get(name)`; a size is a constructor argument |
| `gm.plants.migrate`, `scripts/migrate_plants.py` | none: nothing that remains needs it |
| `Module.to_dict`, `from_dict`, `save`, `load` | on `Plant` only; a single module is stored by wrapping it in a plant |
| `update_params`, `apply_params_at`, `clear_param_overrides` | `set_params` with `valid_from`; attribute assignment for an override |
| `get_parameter`, `get_control`, `get_boundary` | `get(path)` |
| `get_module` | `get_submodule` |
| `boundary[""]["inputs"]`, `boundary[""]["root_inputs"]` | the key `inputs` of the plant dict; `{"return_in": {"T": 293.15}}` is `{"return_in.T": 293.15}` |
| `offer`, `has_input_value`, `add_module`, `extra_repr` | private; assign a control or boundary on its module, `plant.get(path).owner` |
| `offered_outlets`, `start_states`, `trial_outlets`, `calibratable_parameters` | gone |
| `describe`, `parameter_schema`, `validate_params` on a class | on an instance, `gm.modules.ESP().describe()` |
| `docs/schemas/plant_spec.*` | `docs/schemas/plant_dict.*` |
| `gm.challenge_rules` | a `rules` dict of the caller |
| `HackathonPlant` | a plant dict, as `plant_with_treatment.json` of `examples/hackathon_2026/` |
| `gm.profiles.demand`, `gm.profiles.get`, `gm.profiles.names` | `gm.profiles.from_csv`, `gm.profiles.from_values` |
| `gm.checks.operating_days`, `rules["operating_days"]`, `days` of `run_all` | `gm.checks.operating_time`, `rules["operating_time"]`, `duration` |
| `attrs["outage_days"]` of a plan | `attrs["outages"]` |
| `profile=None` of `gm.study.minimize`, `sample` | the caller's demand and `rules` |
| `gm.plants.from_dict(data)` | `gm.Plant.from_dict(data)` |
| `Plant.save(path)`, `gm.Plant.load(path)` | `Plant.to_json(path)`, `gm.Plant.from_json(path)` |
| `Results.save(path)`, `gm.Results.load(path)` | `Results.to_npz(path)`, `gm.Results.from_npz(path)` |
| `gm.plants.convert_legacy(folder)`, `gm.Plant.from_legacy(folder)` | removed; the reader of the old project folder is `scripts/legacy/` and builds no plant, see [legacy.md](legacy.md) |
| `p.validate(on_error="raise")`, `gm.plants.validate(p)` | `p.check()` |
| `Engine.save_checkpoint`, `Engine.load_checkpoint` | `Engine.to_checkpoint`, `Engine.from_checkpoint` |
| `Module.load_state_dict` | `Module.set_state_dict` |
| `gm.runtime.load_state`; `set_precision`, `set_display_units` and the getters | internal `set_state`; `gm.runtime.settings(...)` and `gm.runtime.state()` |
| `gm.evaluate(module, ...)` | `gm.call(module, ...)` |
| `gm.testing.check_module` | `gm.modules.check` |
| `gm.checks.*`, `gm.economics.*`, `gm.kpi.*` | `gm.evaluate.*`; `gm.kpi.compute` is in `gm.evaluate.totals` |
| `gm.checks.Limits`, `gm.checks.limits`, `gm.checks.operating_time` | `gm.case.Requirement` and `gm.evaluate.requirements` |
| `gm.economics.Assumptions` | `case.economics` |
| `electricity_price`, `gas_price`, `waste_disposal_price`, `chemical_price`, `heat_price`, `cold_price` of `Assumptions` | `economics.energy` and `economics.revenue` of the case |
| `rules` of `gm.schedule`, `gm.study.minimize`, `sample`; `order`, `cooling_order`, `operating_time` as a list or a fraction | the `requirements` of the case; `gm.schedule(plant, case)` |
| `gm.schedule(plant, demand, rules)`, `gm.simulate(plant, profile)` | `gm.schedule(plant, case)`, `gm.simulate(plant, case)` |
| `gm.profiles.*` | `gm.case.*` |
| `gm.study.calibrate`, `gm.study.CalibrationResult` | `gm.study.calibrate`, `gm.study.CalibrationResult` |
| `gm.modules.register`, `gm.modules.load_file` | none: a class that states a `category` registers itself in `Module.__init_subclass__`; `abstract = True` leaves it out; a second class of a name raises `duplicate_name` |
| `gm.modules.<Plant class>` | `gm.plants.<Plant class>` |
| `gm.backends.settings(backend)` | `gm.runtime.settings(backend=...)` |
| `gemini.types.Parameter`, `Control`, `Boundary`, `State`, `Inlet`, `Outlet`, `Output` | `gm.modules.*` |
| `gm.Clock` | `gemini.engine.Clock` |
| `gm.Ports`, `gm.Profile`, `gm.streams` | `gemini.types.Ports`, `Profile`, `streams` |
| `gm.Quantity` | `gm.units.Quantity` |
| `gm.no_outputs` | `gm.modules.no_outputs` |

Before 0.1.0 the API counted integer versions 1 to 5: the first frozen list, `category` as the
folder of a module, `gm.legacy` moved behind `gm.plants.convert_legacy`, the fits moved to
`gm.analysis` with one name per concept ([glossary.md](glossary.md)), and the run functions over
`gm.Engine`. Checkpoints and results files written before 0.1.0 do not load: they raise
`ValidationError` with code `old_format`.
