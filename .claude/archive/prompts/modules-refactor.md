# Task: PyTorch-style `Module` design, remove units, make everything run end to end

## 0. Context and definition of done

You are in `<ROOT>` = the `gemini/` folder of the team repo (the restructured GEMINI package).
A previous refactor produced `gemini/core/{base,physics,plant,data,engine,modes}`,
`gemini/components/<category>/<name>.py`, `tests/` (incl. `tests/golden`), `examples/`,
`AGENTS.md`, `CLAUDE.md` and `.claude/docs/*`. Read all of these first, plus
`REFACTOR_REPORT.txt` and `REFACTOR_PATHS.txt`, `datasets/geothermal_example/*`
(every `.param` including its `tagnames` block, `diagram.json`, `plant.conf`, the CSV header).

Goal of this task:
1. Replace the `Component` base class by a **PyTorch-style `Module`**: modules can contain child
   modules, have a `forward`, expose parameters recursively, save/load their state, support hooks.
2. Rename `gemini/components/` → **`gemini/core/modules/`**; the base class lives in
   `gemini/core/modules/module.py` (like `torch/nn/modules/module.py`).
3. **Remove the GEMINI "unit" concept entirely** (`Unit`, `UnitModule`, `core/plant/units/**`,
   `core/engine/twin_modules/**`, `loop.py`, `mainmodule.py`). What units did moves to modules,
   plant config and generic run modes.
4. A plant is itself a `Module` **that we define in code**, exactly like a PyTorch model: a class
   that creates its child modules in `__init__` and wires them explicitly in `forward`. There is
   no automatic graph builder; `diagram.json` is only used to check that the hand-written wiring
   matches GEMINI's diagram.
5. **Everything works end to end** on `datasets/geothermal_example`.

**Definition of done (all must be true, verify before the report):**
- `poetry run black --check gemini tests`, `isort --check-only`, `flake8 gemini tests` clean.
- `poetry run pytest tests` fully green, including all golden tests (numbers unchanged).
- The example plant loads from `datasets/geothermal_example` with **no warnings about unknown
  parameters or tags**, and `GeothermalExamplePlant.forward` runs the whole doublet chain.
- A history run over the full CSV (17 280 rows) finishes, produces soft sensors and health for
  every module, and the reconciliation checks in section 8 pass.
- Every example in `examples/` runs.
- `AGENTS.md` and `.claude/docs/*` describe the new design (no mention of units/components left).

Ground rules (same as before, still in force): branch `refactor/modules`, commit after every
phase, **no push, no PR**; follow `.claude/docs/*`; SI units inside; never change numbers
silently (`# NOTE(refactor): ...` + report); `git mv` for moves; smallest clear implementation.
Do not keep backwards-compatibility shims for removed names: update every caller.

---

## 1. Phase 1: cleanup

- Make sure `__pycache__/`, `*.pyc`, `docs/_build/`, `.pytest_cache/` are in `.gitignore` and not
  tracked (`git rm -r --cached` where needed).
- Move the still-useful content of `REFACTOR_REPORT.txt` (NOTEs, decisions) into
  `.claude/docs/refactor-notes.md`, then delete `REFACTOR_REPORT.txt` and `REFACTOR_PATHS.txt`.
- Confirm `.claude/docs/` exists; if not, recreate it from the previous prompt's content.
- Tests green. Commit.

## 2. Target layout

```
gemini/
├── __init__.py
├── core/
│   ├── base/
│   │   ├── stream.py           # Stream (unchanged)
│   │   └── health.py           # Health (moved out of component.py)
│   ├── physics/                # unchanged
│   ├── modules/
│   │   ├── __init__.py         # exports Module, Sequential and all equipment classes
│   │   ├── module.py           # Module, ModuleResult, ParamRef, Sequential, hook handles
│   │   ├── subsurface/  reservoir.py  productionwell.py  injectionwell.py
│   │   ├── pumps/       esp.py  injectionpump.py  boosterpump.py
│   │   ├── treatment/   degasser.py  filter.py  blowdown.py
│   │   ├── heat/        heatexchanger.py  boiler.py
│   │   └── plants/          geothermal_example.py   # hand-written plant Modules
│   ├── config/
│   │   ├── schema.py           # PlantConfig and friends (Pydantic)
│   │   ├── gemini_loader.py    # GEMINI project folder -> PlantConfig (was plant/loader + param_mapping)
│   │   └── build.py            # PlantConfig -> plant Module params/bindings (+ to/from JSON)
│   ├── data/                   # unchanged drivers; add a simple CSV time-series reader if missing
│   ├── engine/
│   │   ├── registry.py         # type name -> Module class
│   │   ├── results.py          # per-module, per-timestep result table
│   │   └── events.py           # JSON-lines event log via hooks
│   └── modes/
│       ├── twin.py             # shared per-timestep twin evaluation
│       ├── history.py          # replay + calibration over a past period
│       ├── live.py             # latest window from a data driver -> twin
│       └── scenario.py         # chained plant forward over assumed inputs
├── design/__init__.py
├── optim/__init__.py
└── agentic/__init__.py
```
Delete: `core/base/component.py`, `core/base/unit.py`, `core/base/unit_module.py`,
`core/plant/` (after moving loader/param_mapping logic into `core/config/`),
`core/engine/{loop,mainmodule,runner}.py`, `core/engine/twin_modules/`, `gemini/components/`.
Tests mirror the new layout (`tests/core/modules/<category>/test_<name>.py`, ...).

## 3. Phase 2: `Module` base class (`core/modules/module.py`)

Keep everything the old `Component` had (class-level `name`, `category`, `description`,
nested Pydantic `Params` / `Inputs` / `Outputs`, `inlets`, `outlets`, `soft_sensors`,
`calibratable`, `stateful`, `health`, `capex`, `schema`, all validation and the
`__init_subclass__` checks), rename `compute` → `forward`, and add the PyTorch features:

```python
class ModuleResult(NamedTuple):
    outputs: BaseModel
    streams: dict[str, Stream]


class Module(ABC):
    def __init__(self, params: dict | BaseModel | None = None, *, fluid: str = "brine"): ...

    # --- children (like torch) ---------------------------------------------------------
    def __setattr__(self, name, value): ...        # a Module value is registered as child
    def add_module(self, name: str, module: "Module") -> None: ...
    def children(self) -> Iterator["Module"]: ...
    def named_children(self) -> Iterator[tuple[str, "Module"]]: ...
    def modules(self) -> Iterator["Module"]: ...                    # self + all descendants
    def named_modules(self, prefix: str = "") -> Iterator[tuple[str, "Module"]]:  # "doublet.esp"
    def get_submodule(self, path: str) -> "Module": ...
    def apply(self, fn: Callable[["Module"], None]) -> "Module": ...

    # --- forward ------------------------------------------------------------------------
    @abstractmethod
    def forward(self, inputs: BaseModel, streams_in: dict[str, Stream]) -> ModuleResult: ...
    def __call__(self, inputs: BaseModel | dict | None = None,
                 streams_in: dict[str, Stream] | None = None, **streams: Stream) -> ModuleResult:
        # 1. validate inputs with Inputs (None -> Inputs()), merge streams_in + **streams
        # 2. check inlet keys == inlets (clear error with module path)
        # 3. run forward-pre hooks, forward, forward hooks
        # 4. check result: Outputs instance, stream keys == outlets

    # --- parameters ---------------------------------------------------------------------
    def named_params(self, recurse: bool = True) -> Iterator[tuple[str, Any]]:  # "esp.no_stages"
    def calibratable_params(self, recurse: bool = True) -> list["ParamRef"]: ...
    def get_param(self, path: str) -> Any: ...
    def set_param(self, path: str, value: Any) -> None: ...  # re-validates the owning Params

    # --- state --------------------------------------------------------------------------
    def state_dict(self) -> dict: ...            # {"<path>": {"type": name, "params": {...}}}, JSON-safe
    def load_state_dict(self, state: dict, strict: bool = True) -> None: ...
    def initial_state(self) -> Any: ...          # composites: {child_path: state} for stateful children
    def step(self, state, inputs, streams_in, dt) -> tuple[Any, ModuleResult]: ...

    # --- hooks --------------------------------------------------------------------------
    def register_forward_pre_hook(self, fn) -> "HookHandle": ...   # fn(module, inputs, streams_in)
    def register_forward_hook(self, fn) -> "HookHandle": ...       # fn(module, inputs, streams_in, result)

    # --- twin -----------------------------------------------------------------------------
    def health(self, predicted: BaseModel, measured: dict[str, float]) -> Health | None: ...
    def health_report(self, results: dict[str, ModuleResult],
                      measured: dict[str, dict[str, float]]) -> dict[str, Health]: ...  # recursive

    @classmethod
    def schema(cls) -> dict: ...
```

Details:
- `ParamRef`: `path`, `module_path`, `field`, `value`, `bounds: tuple[float, float] | None`
  (taken from Pydantic `gt/ge/lt/le` when present).
- Composite modules (with children) may have empty `Params`/`Inputs`/`Outputs`; their `name` and
  `category` are still required (`category = "plant"` for plants).
- `Sequential(*modules)`: a composite that chains modules with exactly one inlet and one outlet
  each; its inlet = first module's inlet, outlet = last module's outlet; `Inputs` is a dict keyed
  by child index/name passed through.
- Equality/hash: modules are identity objects (do not override `__eq__`).
- Keep it small: no device/dtype/train/eval concepts.

Port every existing equipment class to `Module` (rename `compute` → `forward`, return
`ModuleResult`). Golden numbers must not change. Tests in `tests/core/modules/test_module.py`
cover: child registration and paths, `named_params` recursion, `set_param` re-validation error,
`state_dict` → JSON → `load_state_dict` round trip (strict and non-strict), hooks order and
`HookHandle.remove()`, `Sequential` chaining, error messages naming the module path.

## 4. Phase 3: make every equipment module runnable

The example plant contains filters, a degasser and an injection pump that were placeholders.
For the plant to run end to end, **no module in the example may raise `NotImplementedError`**.
Implement simple, honest physics and mark it:

- Every module gets a class attribute `fidelity: ClassVar[Literal["model", "simple",
  "passthrough"]]` and it appears in `schema()`.
- `Filter` (`simple`): outlet = inlet with `p - dp`, where `dp = dp_nominal·(m_dot/m_dot_nominal)²`
  (params with defaults from the dataset: `FilterA_PDrop ≈ 0.016 bar` at `Qp ≈ 149 m³/h`).
  Outputs `pressure_drop`. Keep the clogging `health`.
- `Degasser` (`passthrough` for liquid): `liquid` outlet = inlet with `p` set to the separator
  outlet pressure `p_out` param or `p - dp` (dataset `Sep_Pin`/`Sep_Pout`); `gas` outlet = a
  zero-flow stream. Document that gas separation is not modelled.
- `InjectionPump` (`simple`): if `no_stages` and curves are available use the ESP-style
  correlation via a shared helper in `core/physics/` (e.g. `pumps.py` with the polynomial
  head/power functions moved out of `esp.py`); otherwise `Inputs.discharge_pressure [Pa]`
  setpoint with `power = Q·Δp/efficiency` (`efficiency` param, default 0.7). Check the dataset
  (`InjectorPump_Pin/Pout/PowerDraw`) and choose the variant that reproduces it best; NOTE it.
- `BoosterPump`, `Blowdown` (`passthrough`): outlet = inlet; outputs empty except a
  `modelled: bool = False` flag.
- `HeatExchanger`, `Boiler`, `ESP`, `Reservoir`, wells stay `model`.

Tests per module: mass conservation (m_dot in = m_dot out summed over outlets), pressure/
temperature sanity, `fidelity` declared.

## 5. Phase 4: plant configuration (`core/config/`)

### `schema.py`
```python
class DatedParams(BaseModel):
    valid_from: datetime | None = None      # None = since forever
    params: dict[str, Any]

class ModuleConfig(BaseModel):
    type: str                               # registry name, e.g. "esp"
    params: list[DatedParams]               # sorted by valid_from; latest valid one applies

class Binding(BaseModel):
    column: str                             # data column / tag, e.g. "ESP_freq"
    unit: str                               # unit of the raw data, e.g. "bar", "degC", "m3/h", "Hz", "W"

class ModuleBindings(BaseModel):
    inputs: dict[str, Binding] = {}         # "frequency" -> ESP_freq
    streams: dict[str, dict[str, Binding]] = {}   # "suction" -> {"p": ESP_Pin, "T": T_p_in, "m_dot": Qp}
    measured: dict[str, Binding] = {}       # Outputs field -> measured column, for health/calibration

class PlantConfig(BaseModel):
    name: str
    plant_type: str                         # registry name of the plant Module, e.g. "geothermal_example"
    modules: dict[str, ModuleConfig]        # key = child path in the plant, e.g. "esp", "hx"
    bindings: dict[str, ModuleBindings] = {}
    boundary: dict[str, Any] = {}           # which module/port is the plant inlet/outlet, ambient T, ...
    timestep: float = 900                   # s, from plant.conf
```
- `units.py` gets one function `to_si(value, unit) -> float` with a fixed table (`bar`, `barg`
  if present, `degC`, `K`, `m3/h`, `m3/s`, `kg/s`, `Hz`, `W`, `kW`, `MW`, `Pa`, `-`). Unknown
  unit → `ValueError`.
- Stream bindings with volumetric flow (`m3/h`) convert to `m_dot` with the fluid density at the
  bound `p`, `T`.

### `gemini_loader.py`: GEMINI project folder → `PlantConfig`
- Node names: from the diagram label + short id (e.g. `esp_1ee3`, `production_well_c774`), i.e.
  the `.param` file stem; map node type → registry name (`Reservoir` → `production_reservoir` or
  `injection_reservoir` depending on its links; `Production Well` → `productionwell`; `ESP` →
  `esp`; `Filter` → `filter`; `Heat Exchanger` → `heatexchanger`; `Injection Pump` →
  `injectionpump`; `Injection Well` → `injectionwell`; `Degasser` → `degasser`).
- Params: reuse the existing mapping functions (move them from `core/plant/param_mapping.py`).
  GEMINI `.param` values are lists over `timestamps`: produce one `DatedParams` per timestamp.
- **Port mapping**: GEMINI ports are generic (`in`, `out`, `out1`, `out2`; the heat exchanger has
  `PrimIn`, `PrimOut` on the left and `SecIn`, `SecOut` on the right). Add an explicit table
  `GEMINI_PORTS[type][gemini_port] = module_port` (e.g. heat exchanger `PrimIn → hot_in`,
  `PrimOut → hot_out`, `SecIn → cold_in`, `SecOut → cold_out`; degasser `out1 → liquid`,
  `out2 → gas`; single-port equipment `in → <its only inlet>`, `out → <its only outlet>`).
  Inspect `diagram.json` links and fix the table until every link maps; unknown → error.
- **Bindings** from each `.param` `tagnames.measured` block: map GEMINI tag keys to module
  fields with an explicit table per type (e.g. ESP: `esp_frequency → inputs.frequency`,
  `esp_inlet_pressure → streams.suction.p`, `esp_inlet_temperature → streams.suction.T`,
  `esp_flow → streams.suction.m_dot`, `esp_head → measured.head`,
  `esp_outlet_pressure → measured.discharge_pressure`,
  `esp_power_consumption → measured.power`). Take raw units from how the old twin modules
  converted them (bar, °C, m³/h, W). Empty tag (`""`) = not bound. Do the same for every
  module type; for the heat exchanger bind `T_p_in/T_p_out/T_s_in/T_s_out/Qp/Qs/HEX_Pin/
  HEX_Pout/Thermal_PowerGen` (check which `.param` carries them; if missing in tagnames, add
  them in the loader's table and NOTE it).
- The loader must report every `.param` property and tag it did not map. Goal: zero unmapped
  for the example (or each explicitly listed as intentionally ignored with a reason).

### `build.py`
- `build_plant(config, at: datetime | None = None) -> GraphPlant` (params valid at `at`).
- `plant_to_config(plant) -> PlantConfig` and JSON save/load helpers, built on `state_dict`.
- Save the converted example as `datasets/geothermal_example/plant.json` and test that
  loading it gives the same plant as loading the GEMINI files.

## 6. Phase 5: `GraphPlant` (`core/modules/plant.py`)

`GraphPlant(Module)` with `category = "plant"`, built from module instances + links:
- Children registered with their config names (`plant.esp_1ee3`).
- `inlets`/`outlets` = unconnected ports of children, named `"<child>.<port>"` (instance-level;
  allow instance overrides of the class attributes for this class only).
- `Inputs`: a dict model `{child_name: child Inputs}`; missing children use defaults.
- `forward`: topological order over links. Cycles (e.g. the reinjection loop reservoir →
  … → injection reservoir is a cycle only if both reservoirs are the same node; secondary loops
  later) are solved by tearing: guess the tear stream, iterate until |ΔT| < 1e-3 K,
  |Δp| < 1 Pa, |Δm_dot| < 1e-6 kg/s, max 50 iterations, else raise with the residuals.
- Returns `ModuleResult` whose `outputs` holds `{child_name: child outputs}` and whose streams are
  the plant outlets; also keep the per-child `ModuleResult`s accessible (`last_results`).
- The production side starts at the production reservoir: `Inputs` for it carry `m_dot`
  (production rate). ESP sits between production well and filter: use the production well
  helpers (`intake_conditions`, `wellhead_from_discharge`) so the chain is
  reservoir → well bottom→ESP intake → ESP → ESP discharge→wellhead → … . Implement this by
  giving `ProductionWell` two internal segments if an `esp_depth` is set and the plant links
  well → ESP: the cleanest option is a small composite `ProductionWellWithESP` built
  automatically by the loader when the diagram has Production Well → ESP; choose the cleanest
  option, explain it in the report, and test it.

Tests: build from the example, run `forward` with the first CSV row's production rate and ESP
frequency, assert every link carried a stream and no NaN appears.

## 7. Phase 6: run modes (`core/modes/`) and engine

### `engine/registry.py`
Discover all concrete `Module` subclasses under `gemini.core.modules` (exclude abstract
bases, `Sequential`, `GraphPlant`); `get(name)`, `create(name, params)`, `list_modules()`.

### `engine/events.py`
`EventLog(path | None)`: `attach(plant)` registers forward hooks on every module and writes
JSON lines `{ts, module_path, inputs, outputs, duration_ms}`; also an API
`log(kind, **payload)` for the future agent (prompts, answers, token usage). In-memory when
`path is None`.

### `engine/results.py`
`Results`: append per timestep `{module_path: outputs + health}`; `to_frame()` → pandas
DataFrame with MultiIndex columns `(module_path, field)`; `save_csv/parquet`.

### `modes/twin.py` — the generic twin step (replaces all old twin modules)
`evaluate(plant, row: Mapping[str, float], at: datetime) -> dict[str, (ModuleResult, Health)]`:
for every equipment module that has bindings: apply dated params valid at `at`; build `Inputs`
and inlet `Stream`s from the bound columns (via `to_si`); call the module **on its own measured
boundary** (twin = per-module, not chained); collect soft sensors and `health(predicted,
measured)`. Unbound modules are skipped. Missing/NaN values in a row → that module is skipped
for that row with a reason (counted, not raised).

### `modes/history.py`
- `replay(plant, config, data: DataFrame, start=None, end=None) -> Results` calls
  `twin.evaluate` for each row.
- `calibrate(plant, config, data, module_path, fields: list[str] | None = None, method="least_squares")
  -> CalibrationResult`: fit the module's `calibratable` params (or the given subset) to its
  measured outputs over the window with `scipy.optimize.least_squares`, respecting `ParamRef`
  bounds; return fitted values, residual RMS before/after, and apply them with `set_param` only
  if `apply=True`. Must work at least for `heatexchanger.ua` and `esp.head_coeff` (use
  `ESP.fit_head_coefficients` as initial guess if present).
### `modes/live.py`
`run_latest(plant, config, driver, window)` reads the latest window from a data driver and calls
`twin.evaluate`; test it with the CSV driver standing in for InfluxDB.
### `modes/scenario.py`
`run(plant, inputs_per_step: Iterable[dict], dt) -> Results`: chained `plant(...)` (or `step`
for stateful plants) per timestep with assumed inputs. Test with 24 hourly steps of constant
inputs.

## 8. Phase 7: end-to-end verification (must pass)

Add `tests/e2e/test_geothermal_example.py` (mark `slow` but run it by default):
1. Load the example with `gemini_loader`; assert zero unmapped properties/tags (or only the
   documented ignore list).
2. Build the `GraphPlant`; run one `forward` from the first CSV row.
3. `history.replay` over the **full CSV**; assert it finishes, every bound module produced
   results for ≥ 99% of rows, no NaN in soft sensors.
4. Reconciliation against measurements (rows where all `*_status == "Normal"`):
   - ESP predicted power vs `ESP_PowerDraw`: median |rel. error| < 10% (report the number);
   - ESP predicted head vs `ESP_Head` (bar → Pa): median |rel. error| < 10%;
   - after `history.calibrate` of `heatexchanger.ua` on the first 7 days, HX predicted outlet
     temperatures within 0.5 K and duty within 2% of `Thermal_PowerGen` on the remaining data;
   - filter predicted Δp within 20% of `FilterA_PDrop` / `FilterB_PDrop`;
   - chained `GraphPlant.forward` with measured production rate and ESP frequency: wellhead
     pressure vs `Pwh_prod` and HX duty vs `Thermal_PowerGen` within 10% median.
   If a threshold fails, investigate (units, bindings, port mapping) before touching the
   threshold. Only if the physics genuinely cannot meet it, relax it with a `NOTE(refactor)`
   explaining why and the achieved value.
5. Health: on "Normal" rows the alarm rate per module is < 5%.

## 9. Phase 8: examples and docs

- Update `examples/` to the new API and add:
  `06_build_plant_from_gemini.py` (load, print the module tree with `named_modules`, save
  `plant.json`), `07_history_replay.py` (replay one week, print health summary and a few soft
  sensors), `08_calibrate_hx.py`, `09_scenario_day.py`. `tests/test_examples.py` runs all.
- Rewrite `.claude/docs/components.md` → `.claude/docs/modules.md` (how to write an equipment
  module, composite modules, `forward`, `fidelity`, bindings belong in config, the skeleton),
  update `conventions.md` (layout, dependency rule: `core.physics` ← `core.modules` ←
  `core.config`/`core.modes` ← `design`/`optim` ← `agentic`), `testing.md` (e2e test), and
  `AGENTS.md` (tree, links). Remove every mention of units/components/twin_modules.
- Update `README.md` with a 15-line quickstart (install, load example, replay, calibrate).

## 10. Final report (last message)

1. Final tree of `gemini/` (two levels) and `tests/`.
2. Deleted paths; renamed paths.
3. All new `NOTE(refactor)`s and still-open old ones.
4. The e2e reconciliation numbers (achieved median errors, alarm rates, calibration RMS before/
   after) in a table.
5. Unmapped/ignored GEMINI params and tags with reasons.
6. Decisions not covered by this prompt (especially ESP placement in the graph, injection pump
   variant, port mapping).
7. Lint/test summary lines.
8. Recommended next steps (heat pump, chillers, storage, demand modules; design/optim).
