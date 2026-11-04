# Task: PyTorch-style modules — declarations in `__init__`, plain `forward`, containers, runtime

## 0. Context, goals, definition of done

You are in the team repo on branch `refactor` (package `gemini/`, `examples/`, `tests/` at the
repo root). Done so far: `gemini/core/{types,physics,modules,data,engine}`, `gemini/legacy/`,
`gemini/optim/calibrate.py`, examples under `examples/<area>/<category>/00_<name>.py` with
shared new-format files in `examples/shared/doublet_heat/`, tests in
`tests/{unit,integration,e2e,fixtures}`. Read `AGENTS.md`, `.claude/docs/*`,
`gemini/core/modules/module.py`, every module under `gemini/core/modules/`,
`examples/shared/doublet_heat/plant.py`, `gemini/core/types/{bindings,quantities,flows,results}.py`,
`gemini/legacy/`, `gemini/optim/calibrate.py`, the engine step/binding code and the examples
first. If the code differs from what is described here, adapt and record it in the report.

**Goal: writing and using a module must feel like PyTorch, as far as possible.** Everything a
module has is declared in `__init__` with ready-made classes (like `nn.Parameter`), `forward`
takes plain arguments, children are built in `__init__`, the parent class `Module` finds and
lists everything automatically, and nothing is declared twice.

### Today (to remove)
```python
class ESP(Module):
    name = "esp"; category = "pumps"; description = "..."          # repeats class/docstring/folder
    inlets = {"suction": Stream}
    outlets = {"discharge": Stream, "electricity": PowerFlow}
    soft_sensors = (...); calibratable = (...)
    class Params(BaseModel): ...                                     # 15 fields
    class Inputs(BaseModel): frequency: Frequency = Field(...)
    class Outputs(BaseModel): ...
    def forward(self, inputs, streams_in):
        ...
        return ModuleResult(self.Outputs(...), {"discharge": ..., "electricity": ...})

esp = ESP(params={"no_stages": 120, ...})                           # dict, SI only
pump = self.esp({"frequency": f}, suction=s)                        # dict + kwargs
pump.streams["discharge"]; exchanged.outputs.duty
DoubletHeatPlant(doublet=None, ...)  # children injected from outside
calibrate(plant, data, "doublet.hx", fields=["ua"])
```

### Target (exact style to implement)
```python
class ESP(Module):
    """Electrical submersible pump installed inside a production well."""

    def __init__(self):
        super().__init__()

        # Parameters
        self.no_stages = Parameter(Count)
        self.head_coeff = Parameter(list[float], shape=(6,), calibratable=True,
                                    description="Ascending ft/stage vs bbl/day coefficients")
        self.power_coeff = Parameter(list[float], shape=(6,), calibratable=True)
        self.setting_depth = Parameter(Length, default=0.0)
        self.motor_efficiency = Parameter(Efficiency, default=1.0)
        self.min_flow = Parameter(VolumeFlow, default=0.0)
        self.max_flow = Parameter(VolumeFlow, default=1.0)
        self.bep_flow = Parameter(VolumeFlow, default=0.04)
        self.drift_threshold = Parameter(Fraction, default=0.10)

        # Inlets
        self.suction = Inlet(Stream)

        # Controls
        self.frequency = Control(Frequency)

        # Outputs
        self.head = Output(PressureDifference, soft_sensor=True)
        self.power = Output(Power, soft_sensor=True)
        self.efficiency = Output(Dimensionless, soft_sensor=True)
        self.discharge_pressure = Output(Pressure, soft_sensor=True)
        self.flow = Output(VolumeFlow)
        self.in_operating_window = Output(bool)
        self.bep_ratio = Output(Ratio)

        # Outlets
        self.discharge = Outlet(Stream)
        self.electricity = Outlet(PowerFlow)

    def forward(self, suction, frequency):
        self.flow = suction.volumetric_flow()
        self.head = pumps.head(self.flow, frequency, self.no_stages, self.head_coeff)
        self.power = pumps.power(self.flow, frequency, self.no_stages, self.power_coeff)
        self.efficiency = ...
        discharge = suction.with_(p=suction.p + self.head)
        self.discharge_pressure = discharge.p
        self.in_operating_window = ...
        self.bep_ratio = ...
        return dict(discharge=discharge, electricity=PowerFlow(P=self.power / self.motor_efficiency))

# a module with a single outlet returns the flow itself, like a layer returning one tensor:
#     def forward(self, inlet): ...; self.pressure_drop = dp; return inlet.with_(p=inlet.p - dp)

esp = gm.modules.ESP(no_stages=120, head_coeff=[...], power_coeff=[...], setting_depth="1200 m")
out = esp(suction=gm.Stream(flow="150 m3/h", T="80 C", p="20 bar"), frequency="50 Hz")
out.outputs.head; out.outlets.discharge; out.outlets.electricity
esp.inlets(); esp.controls(); esp.boundaries(); esp.inputs()
esp.parameters(); esp.named_parameters(); esp.outputs(); esp.outlets()

class DoubletHeatPlant(Module):
    """Doublet, degasser, filters, heat exchanger and injection pump in diagram order."""

    def __init__(self):
        super().__init__()

        # Modules
        self.doublet = Doublet()
        self.degasser = Degasser()
        self.filters = ModuleDict({"hot": Filter(), "cold": Filter()})
        self.heat_exchanger = HeatExchanger()
        self.injection_pump = InjectionPump()

        # Inlets
        self.secondary = Inlet(Stream)

        # Controls
        self.m_dot = Control(MassFlow)
        self.esp_frequency = Control(Frequency)
        self.injection_pressure = Control(Pressure)
        self.injection_frequency = Control(Frequency, default=60.0)

        # Outputs
        self.thermal_power = Output(Power)
        self.electricity_use = Output(Power)
        self.cop = Output(Ratio, optional=True)

        # Outlets
        self.secondary_out = Outlet(Stream)
        self.gas = Outlet(Stream)
        self.electricity = Outlet(PowerFlow)
        self.heat_loss = Outlet(HeatFlow)

    def forward(self, secondary, m_dot, esp_frequency, injection_pressure, injection_frequency):
        ...
```

### Rules (put them in `.claude/docs/modules.md` and `conventions.md`)
1. **Everything is declared in `__init__`** with six ready-made classes from `core/types`:
   `Parameter`, `Inlet`, `Control`, `Boundary`, `Output`, `Outlet`. Composites also assign
   child modules. Assigning any of these registers it (`Module.__setattr__`, like PyTorch).
2. **Section comments, fixed order, plain text, no dashes**: `# Modules` (composites only),
   `# Parameters`, `# Inlets`, `# Controls`, `# Boundaries`, `# Outputs`, `# Outlets`. Omit
   empty sections. One blank line between sections.
3. **Inputs have two kinds**: `Control` = a command someone sets (frequency, setpoint, on/off,
   valve position, production rate); the optimiser and the agent may change it. `Boundary` = a
   condition from outside the system that we cannot set (network return temperature, heat
   demand, air temperature, electricity price). `inputs()` = controls + boundaries.
4. **`forward(self, <names>)`**: its parameters are exactly the declared inlets, controls and
   boundaries (any order, no annotations needed). Checked when the instance is first called
   and by a unit test over every module; mismatch → clear `TypeError` naming the module and the
   missing/extra names.
5. **Outputs are assigned, outlets are returned** (like PyTorch buffers such as BatchNorm's
   `running_mean`, updated inside `forward`, while `forward` returns only the data that flows
   on). Inside `forward`, `self.head = value` records the value of the declared `Output` for
   this call (validated immediately: type, unit bounds). `forward` returns the outlets: a `dict`
   of outlet name → flow, or the flow itself when the module has exactly one outlet. The result
   has two parts: `out.outputs` and `out.outlets` (attribute access on both). A required output
   left unassigned → clear error naming it.
6. **No initial values in `__init__`.** `__init__(self)` takes no arguments except
   **structural** ones (things that change the module tree, e.g. number of segments or of
   filters in a `ModuleList`, like `nn.Linear(in, out)`). Values come from keyword arguments
   (`ESP(no_stages=120)`, applied by `Module` after the subclass `__init__` finishes),
   `load_state_dict`, `module.no_stages = 120`, or the legacy bridge. Defaults live in the
   declaration (`default=`).
7. **Never declare what `Module` derives** (`name`, `description`, `category`, port lists,
   input models, soft-sensor and calibratable lists).

Definition of done:
- The acceptance script in section 10 runs unchanged as `tests/e2e/test_module_api.py` and as
  `examples/core/basics/01_module_api.py`.
- Every module (package, `Doublet`, `DoubletHeatPlant`, test helpers) follows the target style.
  No `Params`/`Inputs`/`Outputs` classes, no `inlets =`/`outlets =`/`name =`/`category =`/
  `description =`/`soft_sensors =`/`calibratable =` class attributes, no
  `forward(self, inputs, streams_in)`, no `ModuleResult(...)` built by modules, no
  `.streams[...]` or `.outputs.` misuse in modules, plants, examples or docs.
- Golden numbers unchanged; all e2e checks (reconciliation, balances, electricity, alarm rate,
  legacy bridge round trip, checkpoint/resume, live idempotency, replay < 60 s) pass; results
  identical to the baseline of phase 0.
- black / isort / flake8 clean; `pytest -m "not e2e"` and full `pytest` green.
- Docs updated (`.claude/docs/modules.md`, `types.md`, `api.md`, `conventions.md`, new
  `runtime.md`, `AGENTS.md`, README).

Ground rules (unchanged): new branch `refactor/module-api` from `refactor`, commit per phase,
**no push, no PR**, follow `.claude/docs/*`, SI inside, no silent numeric changes
(`NOTE(refactor)` + report), `git mv` for moves, smallest clear implementation, **no
compatibility shims** for removed styles.

---

## 1. Phase 0: baseline

Run the full test suite and the replay timing; save what you will compare against (golden
values, e2e metrics, the shared plant's `state_dict()` and full replay results, simulate results
of the quickstart profile) under `tests/fixtures/module_api_baseline/`. A test compares the final
code against it (values identical; key names may change only as listed in the report's rename
table, which the test applies).

## 2. Phase 1: declaration classes (`gemini/core/types/declarations.py`)

```python
class Parameter:      # like nn.Parameter: design data, fixed during a run
    def __init__(self, kind, *, default=UNSET, shape=None, calibratable=False,
                 description=None, **bounds): ...
class Inlet:          # incoming flow port
    def __init__(self, kind=Stream, *, description=None): ...
class Control:        # command, changes over time, optimisable
    def __init__(self, kind, *, default=UNSET, description=None, **bounds): ...
class Boundary:       # outside condition, changes over time, not optimisable
    def __init__(self, kind, *, default=UNSET, description=None, **bounds): ...
class Output:         # computed number
    def __init__(self, kind, *, soft_sensor=False, optional=False, description=None): ...
class Outlet:         # outgoing flow port (Stream, PowerFlow, HeatFlow, FuelFlow)
    def __init__(self, kind=Stream, *, description=None): ...
```
- `kind` is a quantity annotation from `core/types/quantities.py` (`Length`, `Frequency`, ...),
  a Python type (`bool`, `int`, `str`, `list[float]`, `Literal[...]`), or a flow type for
  inlets/outlets. Unit, quantity name and default bounds come from the quantity annotation;
  `**bounds` (`gt`, `ge`, `lt`, `le`) tighten them.
- Validation uses Pydantic `TypeAdapter` built once per declaration (keep Pydantic's checks;
  do not hand-write validators). `shape=(6,)` checks list length.
- `UNSET` → the parameter is **uninitialized** (like `torch.nn.UninitializedParameter`).
- Each declaration knows its name once assigned (`__set_name__`-like hook from
  `Module.__setattr__`) for error messages (`"doublet.esp.no_stages: ..."`).
- Keep `DatedParams` semantics: a `Parameter` stores its value history
  (`[(valid_from, value), ...]`); the module-level API (`params_at(t)`, `apply_params_at(t)`,
  `param_history`) keeps working on top of it. Decide the cleanest storage and report it.
- `description` defaults to `None`; `help()` shows unit and bounds anyway.

## 3. Phase 2: `Module` (in `gemini/core/modules/module.py`)

### Registration and access (like `nn.Module.__setattr__` / `__getattr__`)
- `__setattr__` registers `Parameter`, `Inlet`, `Control`, `Boundary`, `Output`, `Outlet` and
  child `Module`s in ordered internal dicts (`_parameters`, `_inlets`, `_controls`,
  `_boundaries`, `_outputs`, `_outlets`, `_children`). Re-declaring a name with another kind →
  error.
- Reading `self.no_stages` returns the parameter's **current value** (plain `float`/`int`/
  `list`/...), so physics code is unchanged and numbers stay identical. Uninitialized → error
  naming the path. Writing `module.no_stages = 120` (when `no_stages` is already a declared
  Parameter) validates and sets the value (unit strings allowed, section 6).
- `module.get_parameter("no_stages")` / `plant.get_parameter("doublet.esp.no_stages")` return the
  `Parameter` object (metadata, value, history), like `nn.Module.get_parameter`.
- Reading an inlet/control/boundary/output/outlet attribute outside `forward` returns its
  declaration object (for introspection); inside `forward` the values arrive as arguments.

### Listing (recursive on composites, keys are paths like `"doublet.esp.frequency"`)
```python
module.parameters(recurse=True)      -> Iterator[Parameter]
module.named_parameters(recurse=True)-> Iterator[tuple[str, Parameter]]
module.calibratable_parameters()     -> list[Parameter]
module.inlets()  / controls() / boundaries() / inputs() / outputs() / outlets()
                                      -> dict[str, declaration]  (own only; recurse=True for all)
module.soft_sensors()                -> dict[str, Output]
module.missing_parameters()          -> list[str]   (paths of uninitialized parameters)
module.is_initialized                -> bool
```
Plus the existing ones (`named_modules`, `children`, `get_submodule`, `apply`, `state_dict`,
`load_state_dict`, hooks, `to_dict`/`from_dict`/`save`/`load`, `extra_repr`).

### Derived metadata (in `Module.__init_subclass__`, no separate file)
- `name`: snake_case of the class name (`HeatExchanger` → `heat_exchanger`, `ESP` → `esp`,
  `DoubletHeatPlant` → `doublet_heat_plant`); collision between registered classes → error.
- `description`: first paragraph of the class docstring; missing docstring → `TypeError`.
- `category`: subpackage under `gemini.core.modules` (`pumps`, `heat`, ...); outside the package
  → `"user"`.
- Registration in a module registry at class creation; `catalogue.get/create/list_modules`
  read from it (remove the `pkgutil` walk; `gemini/core/modules/__init__.py` imports the
  subpackages). Update `engine/registry.py` and `legacy`.
- Keep `stateful`, `fidelity`, `repr_fields` as optional class attributes (real choices).

### Construction with keyword values
- `Module.__init_subclass__` wraps the subclass `__init__` so that `Cls(*structural, **values)`
  runs the subclass `__init__(*structural)` first, then applies `**values` to the declared
  parameters (unknown name → error listing valid names; unit strings allowed). Composites may
  receive values for children by path: `DoubletHeatPlant(**{"doublet.esp.no_stages": 120})`.
- `Cls.__signature__` is built from the declarations so `inspect.signature`, `help()` and
  Jupyter show the parameters.
- `fluid=` stays an optional keyword handled by `Module` (default from `runtime`).

### Calling
- `module(*args, **kwargs)` binds to the `forward` signature; validates inlets (flow types),
  controls and boundaries (unit strings / `Quantity` accepted, converted to SI, bounds checked;
  defaults applied); checks `missing_parameters()` is empty; opens a fresh per-call output
  record; runs pre-hooks, `forward`, hooks; collects the assigned outputs and validates the
  returned outlets (dict keys == declared outlets, or a single flow for a single-outlet module;
  flow types); returns `ModuleResult`.
- **Per-call output record**: assigning to a declared `Output` inside `forward` writes into a
  record that belongs to the current call, held in a `contextvars.ContextVar` (the code already
  uses one for the evaluation tree), never into module state. So the same module can be called
  in nested calls, repeatedly in one step, or from several threads without mixing values.
  Reading `self.head` inside `forward` after assigning it returns the recorded value; reading it
  outside a call returns the `Output` declaration. Assigning to an `Output` outside `forward` →
  error.
- `ModuleResult` (in `core/types/results.py`): `outputs` and `outlets` (both attribute- and
  `[]`-accessible, iterable over names), plus the existing audit fields (inputs, inlets,
  children, balances). `repr` prints values in the runtime display units. Remove the old
  `streams` name (use `outlets`) and the old tuple-unpacking behaviour unless the engine needs
  it internally.
- Hooks: pre-hook `fn(module, inputs: dict, inlets: dict)`, hook `fn(module, inputs, inlets,
  result)`.
- Stateful modules (none today; keep the contract): `step(self, state, dt, <same names>)` →
  `(new_state, outlets)`, outputs assigned the same way.
- **How the engine calls modules** (keep it, make it explicit in `engine.md`): `simulate` calls
  the plant once per time step, so the plant's `forward` runs once per step and calls its
  children in its own order (chained, PyTorch-style). `replay` and `live` do **not** call the
  plant's `forward`: the engine calls every bound module separately (`module(**kwargs)`), each
  fed by its own sensors through `inlets()`, `controls()`, `boundaries()`, so model errors do not
  propagate between equipment. Both always go through `__call__`, never `forward` directly.
- The old call style `module(inputs_dict, streams_in, **streams)` is removed.

### `print` and `help`
- `print(plant)`: PyTorch-like tree; each line shows the module and 2–4 key parameter values
  in display units (`repr_fields` or the first initialized parameters).
- `Cls.help()` / `module.help()` (returns a string): description, category, then one block per
  section (parameters with unit, default, bounds, calibratable; inlets; controls; boundaries;
  outputs with unit and soft-sensor flag; outlets). `gm.modules.list()` → names grouped by
  category.

## 4. Phase 3: containers (`gemini/core/modules/container.py`)

Like `torch/nn/modules/container.py`: move `Sequential` out of `module.py` (`git mv` the code,
keep behaviour, adapt to the new call style) and add `ModuleList` (`append`, `extend`, `insert`,
int/slice indexing, `len`, `iter`; children `"0"`, `"1"`, ...) and `ModuleDict` (mapping API;
children named by key). Both have no `forward` and no declarations of their own; they work with
`named_modules`, parameters, `state_dict`/`load_state_dict`, `to_dict`/`from_dict`, hooks,
bindings, engine paths, legacy mapping and `print`. `module.py` keeps only `Module` and its
private helpers. Export `Sequential`, `ModuleList`, `ModuleDict` from `gm.modules`. Use
`ModuleDict` for the two filters in `DoubletHeatPlant` (`filters.hot`, `filters.cold`).

## 5. Phase 4: `gemini/core/runtime.py` (global settings only)

Modelled on PyTorch's global functions (`torch.set_default_dtype`, `torch.manual_seed`):
```python
gm.runtime.set_default_fluid(fluid) / get_default_fluid()
gm.runtime.set_precision("float64" | "float32") / get_precision()
gm.runtime.set_display_units("si" | "field") / get_display_units()   # field: bar, °C, m3/h, kW
gm.runtime.manual_seed(seed)
with gm.runtime.settings(precision="float32", display_units="field"): ...   # restores on exit
gm.runtime.state() -> dict / gm.runtime.load_state(d)
```
- `contextvars`-based (safe in threads/Celery).
- `precision` replaces the ESP `coefficient_precision` param (remove it). Legacy parity tests
  that need float32 wrap their call in `with gm.runtime.settings(precision="float32")`. Numbers
  must not change.
- `default_fluid` replaces the hard-coded `BRINE` default.
- `display_units` affects printing only (module tree, results, `help`), never values.
- `Engine.save_checkpoint` stores `runtime.state()`; `load_checkpoint`/`resume` run inside
  `settings(**stored)`.

## 6. Phase 5: units at the boundary and easy streams

- Wherever a user passes a number (keyword values, attribute assignment, call arguments,
  `Profile.constant`; `load_state_dict` stays SI only): float/int = SI; `"<value> <unit>"` or
  `gm.Quantity(value, unit)` → converted with `physics.units`, dimension checked against the
  declaration's quantity (`"1200 bar"` for a length → error with path, field, value, expected
  unit). No `pint`.
- `gm.Stream(flow=..., T=..., p=..., fluid=None)`: `flow` volumetric (`m3/h`, `m3/s`, `l/s`) or
  mass (`kg/s`, `t/h`) detected from the unit; plain float = kg/s. The SI field `m_dot=` still
  works (same class).
- Output conversion: `out.outputs.get("head", unit="bar")`,
  `res["doublet.esp"].get("head", unit="bar")` (Series), `gm.units.convert(value, from, to)`.

## 7. Phase 6: plants build their own children; engine, bindings, legacy

- `Doublet.__init__(self)` builds reservoir, production well, ESP, riser, injection well, sink;
  declares its controls (`m_dot`, `esp_frequency`), inlet (`return_`/`return_stream` — pick a
  valid name, report it) and outlets. `produce`/`inject` stay, in the new call style.
- `DoubletHeatPlant.__init__(self)` as in the target above; remove the `None`-default child
  arguments and the `setattr` loop. Its old `Inputs.secondary` becomes `Inlet` `secondary`.
- Loading = construct + fill: `Cls.load(path)` / `Cls.from_dict(d)` = `Cls()` +
  `load_state_dict` + histories + bindings. `gm.legacy.to_plant(project, Cls())` only fills
  values, histories and bindings; it never creates or attaches modules.
- Bindings: `ModuleBindings` keys become `controls`, `boundaries`, `inlets`, `measured`,
  `state` (was `inputs`, `streams`, ...). Migrate `plant.json` through the legacy bridge and keep
  the bridge e2e test green (generated files == committed files).
- Engine: the binding plan uses the declarations (`controls()`, `boundaries()`, `inlets()`,
  `outputs()`), calls modules with keyword arguments, stores outputs and outlets as before.
  Results identical to the baseline. Results columns/paths unchanged except renames listed in
  the report.
- Names change (`heatexchanger` → `heat_exchanger`, `doublet_heat` → `doublet_heat_plant`,
  filter paths, ...): update `legacy/tables.py`, catalogue users, docs, tests, `plant.json`.

## 8. Phase 7: calibration takes parameters

- `gm.optim.calibrate(plant, dataset, params: list[Parameter], start=None, end=None,
  engine=None, apply=True)`, e.g. `params=[plant.get_parameter("heat_exchanger.ua")]`. The
  compared outputs are the soft sensors of the modules owning the given parameters (`only=` on
  replay). Only `calibratable=True` parameters accepted (clear error otherwise). Remove
  `module_path`/`fields` and the old `ParamRef` if `Parameter` replaces it (report).
- `CalibrationResult` otherwise unchanged.

## 9. Phase 8: examples, tests, docs

- Update every example to the new style. Add `examples/core/basics/01_module_api.py` (= section
  10) and `examples/core/basics/02_custom_plant.py` (a small user plant outside the package with
  a `ModuleList`, run with `engine.simulate`).
- Tests (mirror rule): unit tests for every declaration class, registration and listing,
  derived metadata, keyword construction and `__signature__`, forward-signature check (one test
  that walks every registered module), output recording (incl. a threads/nested-call test) and outlet validation, units parsing,
  uninitialized parameters, containers, runtime (incl. `settings()` restore and contextvars),
  `help()`, and a **convention test** that parses every module's `__init__` source and checks
  the section comments appear in the fixed order without dashes. Integration: a user plant
  outside the package with engine, checkpoint, save/load. E2E: `test_module_api.py`, baseline
  comparison.
- Docs: `.claude/docs/modules.md` (how to write a module/plant now: the target code above and
  the 7 rules), `types.md` (declaration classes, Quantity strings, Stream constructor),
  `runtime.md`, `api.md`, `conventions.md` (rules 1–7), `AGENTS.md`, README quickstart.

## 10. Acceptance script (must run as written, from the repo root)

```python
import pandas as pd

import gemini as gm
from examples.shared.doublet_heat.plant import DoubletHeatPlant

SHARED = "examples/shared/doublet_heat"

# a module, PyTorch style
plant = DoubletHeatPlant.load(f"{SHARED}/plant.json")
values = {name: p.value for name, p in plant.doublet.esp.named_parameters()}
esp = gm.modules.ESP(**values | {"setting_depth": "1200 m"})
s = gm.Stream(flow="150 m3/h", T="80 C", p="20 bar")
out = esp(suction=s, frequency="50 Hz")
print(out.outputs.head, out.outlets.discharge.p, out.outlets.electricity.P)
print(out.outputs.get("head", unit="bar"))
print(list(esp.inlets()), list(esp.controls()), list(esp.boundaries()))
print(list(esp.outputs()), list(esp.outlets()))
print(gm.modules.ESP.help())
print(gm.modules.list())

# uninitialized modules, keyword values, attribute assignment
empty = gm.modules.ESP()
assert not empty.is_initialized and "no_stages" in empty.missing_parameters()
empty.no_stages = 120
assert empty.no_stages == 120

# self-building plants and containers
assert isinstance(plant.filters, gm.modules.ModuleDict)
fresh = DoubletHeatPlant()
assert not fresh.is_initialized
fresh.load_state_dict(plant.state_dict())
assert fresh.is_initialized
print(plant)
print(sorted(plant.controls(recurse=True)))

# runtime settings
assert gm.runtime.get_precision() == "float64"
with gm.runtime.settings(precision="float32", display_units="field"):
    print(esp(suction=s, frequency=50))
assert gm.runtime.get_precision() == "float64"

# engine and calibration with parameter objects
df = pd.read_csv(f"{SHARED}/doublet_2024_15min.csv", parse_dates=["time"])
data = gm.Dataset.from_frame(df, time_column="time")
res = gm.Engine().replay(plant, data)
print(res["doublet.esp"].get("head", unit="bar").head())
fit = gm.optim.calibrate(plant, data, params=[plant.get_parameter("heat_exchanger.ua")])
print(fit)
```
Adjust paths/attribute names only if the real plant differs; keep the shape of every call. If a
call cannot work as written, change the package; only if truly impossible, change the script
minimally and explain why in the report.

## 11. Final report (last message)

1. Tree of `gemini/core/` (two levels) and new/changed files.
2. Before/after of the ESP module and of `DoubletHeatPlant` (line counts + code).
3. What `Module` derives, and every renamed name/path/binding key (old → new).
4. Acceptance script output.
5. Baseline comparison: golden, e2e metrics, replay/simulate results, replay timing.
6. Decisions not covered here (parameter history storage, `ParamRef` fate, names you picked)
   and new `NOTE(refactor)`s.
7. Lint/test summary lines.
