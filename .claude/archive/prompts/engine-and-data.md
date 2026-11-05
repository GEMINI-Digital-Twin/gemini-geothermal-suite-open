# Task: Engine (simulate / replay / live), in-memory data, checkpoints, simple public API, examples and tests layout

## 0. Context, goals, definition of done

You are in `<ROOT>` = the `gemini/` folder of the team repo. This task runs **after** the
"types and plants" task. Expected state: `gemini/core/{types,physics,modules,config,data,engine,
modes}` with a PyTorch-style `Module`, hand-written plants in `core/modules/plants/`, quantity
types, energy ports, a GEMINI loader producing a `PlantConfig` (dated params + sensor bindings),
data drivers in `core/data/`, run modes in `core/modes/` (twin, history, live, scenario), and an
end-to-end test on `datasets/geothermal_example`. Read `AGENTS.md`, `.claude/docs/*`, all of
`core/`, `tests/`, `examples/` first. If the code differs from this description, adapt and record
it in the report.

**The top priority of this task is user experience**: using the package must be very easy;
complexity lives inside the package and the code stays clean and tidy. The acceptance test for
that is section 1: this exact user script must run.

PyTorch analogy that drives the design:

```
PyTorch                          gemini
torch.nn.Module (model)     ->   plant Module (carries its own config: bindings, dated params)
TensorDataset (in memory)   ->   core/data/dataset.py   (from_frame / from_dict / from_numpy / from_profiles)
Sampler + DataLoader        ->   core/data/loader.py    (aligns dataset rows to clock ticks)
inference loop + callbacks  ->   core/engine/           (Engine.simulate / replay / live)
time axis of the loop       ->   core/engine/clock.py   (the clock lives in the engine)
Lightning checkpoint        ->   Engine.save_checkpoint / load_checkpoint / resume
training loop + optimizer   ->   gemini/optim/calibrate.py (fits params by calling Engine.replay)
user's own model + data     ->   examples/ (never inside the package)
```

Goals:
1. **Delete `core/modes/`**; its logic moves into the engine (running) and `optim` (calibration).
2. One `Engine` with three methods, `simulate`, `replay`, `live`, each taking the **plant
   Module** as first argument. Files split by responsibility, never by mode.
3. **Data is in-memory only.** Delete all data drivers (InfluxDB, AVEVA, GEMINI CSV driver and
   their reader/driver abstracts). A `Dataset` is built from pandas, numpy, lists, dicts or our
   own types (`Profile`). Reading files or databases is the user's job (e.g. `pd.read_csv`).
   A `Loader` (sampler) in `core/data` aligns a dataset to the engine's `Clock` (in
   `core/engine`). Normal users never touch the loader.
4. **The plant carries its configuration** (sensor bindings, dated params, column units), so no
   method takes a separate config argument. `plant.save()` / `load()` round-trip all of it.
   **Delete `core/config/` entirely** (section 3).
5. **`gemini/legacy/` is the bridge between the old GEMINI files and the new structure, in
   both directions.** It reads old files (`diagram.json`, `.param`, old CSV) into a new plant,
   bindings and `Dataset`, and writes old-format files back from a new plant and new results.
   **All conversion lives in `gemini/legacy/` and nowhere else**: no GEMINI names, tags, tables
   or mapping in `core/`, in plant classes or in examples (other than the bridge example's
   input). Running always uses the new engine and modules. No adapter for the old
   `StaticModel` API and nothing from the old framework.
6. **Engine-wide checkpoints at any time** in all three modes: save, load, resume; plus an
   automatic checkpoint callback. Checkpoints are self-contained (they do not depend on a file
   or database the dataset came from).
7. A small, curated public API: `import gemini as gm`.
8. Calibration (training analogue) in `gemini/optim/calibrate.py`, using only the public engine
   API.
9. **No examples inside the package.** Example-specific plants and data move to `examples/`.
   Generic building blocks (e.g. `Doublet`) stay in the package.
10. New layouts for `examples/` (category / example / files) and `tests/` (unit / integration /
   e2e / fixtures), and the meaningless name `geothermal_example` replaced everywhere
   (section 10).
11. Everything still works end to end, and fast enough.

Definition of done:
- The user script in section 1 runs unchanged as `tests/e2e/test_quickstart.py`.
- black / isort / flake8 clean; `pytest tests` green; golden numbers unchanged; all previous
  e2e checks (reconciliation, mass/energy balance, electricity, wiring, alarm rate) pass through
  the new API.
- `core/modes/`, `core/config/` and all data drivers gone; nothing imports them; no public
  function takes a config argument; `GEMINI_NODES` and any GEMINI-to-module mapping are gone
  from `gemini/`; `influxdb`/AVEVA client packages removed from dependencies.
- `gemini/` contains no example plant, example data or example script;
  `grep -ri geothermal_example` finds nothing in the repo (outside git history).
- `engine.replay` over the full example data (17 280 rows) < 60 s on a laptop (report time).
- Checkpoint tests: interrupt a replay and a simulate mid-run, save, load in a fresh `Engine`,
  `resume()` with no arguments; final results identical to an uninterrupted run. `live` called
  repeatedly processes each tick exactly once.
- Docs updated (`.claude/docs/engine.md`, `data.md`, `api.md`, `testing.md`, `AGENTS.md`,
  README).

Ground rules (unchanged): branch `refactor/engine`, commit per phase, **no push, no PR**,
follow `.claude/docs/*`, SI inside, no silent numeric changes (`NOTE(refactor)` + report),
`git mv` for moves, smallest clear implementation, no compatibility shims for removed names.
The engine never loops forever or sleeps: periodic `live` calls are scheduled outside the
package (e.g. Celery in the backend), and that caller fetches the new data itself.

---

## 1. Acceptance script (must run as written)

Run from the repo root. `SHARED` is the shared example folder defined in section 10.

```python
import pandas as pd

import gemini as gm
from examples.shared.doublet_heat.plant import DoubletHeatPlant

SHARED = "examples/shared/doublet_heat"

# load a plant from our own (new) file format
plant = DoubletHeatPlant.load(f"{SHARED}/plant.json")
print(plant)                                   # module tree with types and key params

# data: the user reads the file (new format); the package only takes in-memory data
df = pd.read_csv(f"{SHARED}/doublet_2024_15min.csv", parse_dates=["time"])
data = gm.Dataset.from_frame(df, time_column="time")

# replay: clock inferred from the data, units from the plant's bindings
engine = gm.Engine()
res = engine.replay(plant, data)
print(res.summary())                           # energy, peaks, alarms per module
esp_power = res["doublet.esp"].power           # pandas Series (use the real ESP path)

# checkpoint any time, resume later (no dataset needed: the checkpoint is self-contained)
engine.save_checkpoint("runs/replay.ckpt")
engine2 = gm.Engine.load_checkpoint("runs/replay.ckpt")
res2 = engine2.resume()                        # nothing left to do -> same results

# calibrate (training analogue)
fit = gm.optim.calibrate(plant, data, "doublet.hx", fields=["ua"])
print(fit)
plant.save("runs/my_plant.json")
assert DoubletHeatPlant.load("runs/my_plant.json").state_dict() == plant.state_dict()

# simulate: assumed inputs over a clock
clock = gm.Clock.days(2027, 1, 1, days=1)
profiles = {
    "production_rate": gm.Profile.constant(150, unit="m3/h", clock=clock),
    "esp_frequency": gm.Profile.constant(55, unit="Hz", clock=clock),
}
sim = engine.simulate(plant, gm.Dataset.from_profiles(profiles), clock=clock)
print(sim.summary())

# live: called periodically by an external scheduler that fetches the new rows itself
day1 = df[df["time"] < "2024-06-08"]
day2 = df[(df["time"] >= "2024-06-08") & (df["time"] < "2024-06-09")]
out1 = engine.live(plant, gm.Dataset.from_frame(day1, time_column="time"),
                   checkpoint="runs/live.ckpt", now="2024-06-08T00:00:00Z")
out2 = engine.live(plant, gm.Dataset.from_frame(day2, time_column="time"),
                   checkpoint="runs/live.ckpt", now="2024-06-09T00:00:00Z")
```
Adjust module paths (`"doublet.esp"`, `"doublet.hx"`), the time column name and profile names
to the real plant and data, but keep the shape of every call. If any call cannot work as
written, change the package, not the script; only if truly impossible, change the script
minimally and explain why in the report.

---

## 2. Target layout

```
<repo>/
├── gemini/                         # the package only, no examples
│   ├── __init__.py                 # curated public API (section 8)
│   ├── core/
│   │   ├── data/
│   │   │   ├── dataset.py          # Dataset (in-memory)
│   │   │   └── loader.py           # Loader (sampler): aligns a Dataset to a Clock
│   │   ├── engine/
│   │   │   ├── engine.py           # Engine: simulate, replay, live, save/load_checkpoint, resume
│   │   │   ├── clock.py            # Clock: FixedClock, DataClock, LiveClock (+ constructors)
│   │   │   ├── step.py             # chained_step, twin_step (from modes/)
│   │   │   ├── results.py          # Results (+ summary, path access)
│   │   │   ├── callbacks.py        # Callback, EventLog, Progress, AlarmCollector, AutoCheckpoint
│   │   │   ├── checkpoint.py       # Checkpoint format, save/load (atomic)
│   │   │   └── registry.py
│   │   ├── modules/plants/         # generic plants only (Doublet); no example plants
│   │   └── (types, physics, other modules unchanged except section 3)
│   ├── legacy/                     # bridge old GEMINI files <-> new structure (section 3)
│   │   ├── __init__.py             # public functions only
│   │   ├── files.py                # raw read/write of old files -> typed GeminiProject
│   │   ├── tables.py               # GEMINI node types/properties/ports/tags <-> our modules/fields/units
│   │   └── convert.py              # GeminiProject <-> plant, old CSV <-> Dataset, Results -> old CSV
│   └── optim/
│       ├── __init__.py
│       └── calibrate.py
├── examples/                       # section 10
└── tests/                          # section 11
```
`core/data/drivers/` is deleted. The root `datasets/` folder is deleted (its content moves to
`examples/shared/`, section 10).

## 3. Phase 1: the plant carries its configuration

- Add to `Module` (root-level use; children may have their own):
  - `plant.bindings: dict[str, ModuleBindings]` keyed by module path (`""` = root);
  - dated params: each module keeps `param_history: list[DatedParams]` (default: one entry with
    `valid_from=None` = its current params); `module.params_at(t)` and
    `plant.apply_params_at(t)` (recursive);
  - `plant.column_units() -> dict[str, ColumnInfo]` derived from bindings.
- **Delete `core/config/`.** Where its parts go:
  - `ModuleBindings`, `DatedParams`, `ColumnInfo` → `core/types/` (plain types like the others).
  - Our own plant file format → methods on `Module` next to `state_dict`, like PyTorch
    (`gemini/core/modules/module.py`, or a sibling `serialization.py` if module.py gets long):
    - `plant.to_dict()` / `PlantClass.from_dict(d)`: plant type, module params incl. histories,
      bindings. JSON-serialisable.
    - `plant.save(path)` writes `to_dict()` as JSON; `PlantClass.load(path)` reads it back.
      Check that the stored plant type matches the class; clear error if not.
    - These are classmethods on the plant class, so a plant defined outside the package (in an
      example) works the same as one inside it, like `model = MyNet()` + `load_state_dict`.
  - Everything GEMINI-specific (loader, `GEMINI_NODES`, node/param/tag mapping, wiring check)
    → `gemini/legacy/` (below). Plant classes contain no GEMINI code.
  - Remove any name-based global plant registry that existed only so the loader could find
    example plants. Delete `PlantConfig`; no name in the package says "config".
- **`gemini/legacy/`: the bridge.** All conversion between old and new lives here.
  - `files.py`: raw, faithful read/write of the old files, no interpretation:
    ```python
    class GeminiNode(BaseModel): id: str; type: str; name: str; ports: list[str]
    class GeminiLink(BaseModel): source: str; source_port: str; target: str; target_port: str
    class GeminiParam(BaseModel): values: list[Any]; timestamps: list[datetime | None]; unit: str | None
    class GeminiTags(BaseModel): measured: dict[str, str]; filtered: dict[str, str]; calculated: dict[str, str]
    class GeminiProject(BaseModel):
        nodes: dict[str, GeminiNode]
        links: list[GeminiLink]
        params: dict[str, dict[str, GeminiParam]]   # node id -> property -> dated values
        tags: dict[str, GeminiTags]                  # node id -> sensor tags
    ```
    `read_project(folder) -> GeminiProject` and `write_project(project, folder)`;
    `write_project(read_project(f))` reproduces the original files (byte-identical where the
    format allows, otherwise identical after JSON/whitespace normalisation; say which in the
    report). Old CSV: `read_csv(path) -> pd.DataFrame` / `write_csv(df, path)` (`;`, old
    timestamp format). Clear errors naming file and field.
  - `tables.py`: the general mapping, written once: GEMINI node type → our module class; GEMINI
    property names → our param fields (+ unit conversion); GEMINI port names → our ports; tag
    kinds → bindings (measured/filtered → measurement bindings, calculated → soft-sensor
    outputs). Plain dicts/dataclasses, one place, documented.
  - `convert.py` + public functions in `legacy/__init__.py`:
    ```python
    def to_plant(project, plant: Module, nodes: dict[str, str] | None = None) -> Module: ...
        # fills params, dated histories and bindings of an existing plant instance;
        # nodes: GEMINI node id -> module path; None -> match by node type when unique in the
        # plant, ambiguous -> one error listing the candidates
    def to_dataset(project, df_old) -> Dataset: ...
        # renames tag columns to the plant's new column names, converts to SI
    def from_plant(plant, template: GeminiProject, nodes=None) -> GeminiProject: ...
        # current params/histories back into GEMINI properties and units
    def results_to_frame(results, project, nodes=None) -> pd.DataFrame: ...
        # new results -> old tag column names and units (for write_csv)
    def check_wiring(plant, project, nodes=None) -> list[str]: ...   # [] = matches diagram.json
    ```
  - Round trips are exact (tests): old → new → old params; old CSV → Dataset → old CSV values.
  - Unit tests on small synthetic old files in `tests/unit/legacy/` (mirror rule). These are the
    only tests that touch the old formats, plus the bridge e2e (section 11).
- `print(plant)` (`__repr__`): an indented tree like PyTorch:
  ```
  DoubletHeatPlant(
    (doublet): Doublet(
      (reservoir): ProductionReservoir(pressure=…bar, temperature=…°C, PI=…)
      (esp): ESP(no_stages=…, setting_depth=… m)
      ...
  ```
  Show 2–4 key params per module in human units (implement `extra_repr()` per module, like
  PyTorch; conversion for display via `units`).
- Remove the `config` argument from every engine/optim function; update callers and tests.

## 4. Phase 2: `Dataset` (`core/data/dataset.py`), in-memory only

First delete `core/data/drivers/` (InfluxDB, AVEVA, GEMINI CSV driver, reader/driver
abstracts), their tests, and their dependencies in `pyproject.toml`. Record the deleted paths in
the report.

```python
class ColumnInfo(BaseModel):
    unit: str                    # raw unit understood by units.to_si
    quantity: str | None = None

class Dataset:
    """Time-indexed table of raw values held in memory; units are metadata."""
    columns: dict[str, ColumnInfo]
    start: datetime; end: datetime                      # properties
    native_step: timedelta | None                       # median spacing
    def read(self, start, end, columns=None) -> pd.DataFrame: ...   # inclusive, UTC index
    def window(self, start, end) -> "Dataset": ...
    def after(self, t) -> "Dataset": ...                # rows strictly after t
    def __len__(self) -> int: ...
    def fingerprint(self) -> str: ...                   # stable hash of index + values + units
    def to_frame(self) -> pd.DataFrame: ...

    @staticmethod
    def from_frame(df, time_column=None, units=None, tz="UTC") -> "Dataset": ...
        # time_column=None → use the DatetimeIndex
    @staticmethod
    def from_dict(data: dict[str, list | np.ndarray], time, units=None, tz="UTC") -> "Dataset": ...
    @staticmethod
    def from_records(rows: list[dict], time_column, units=None, tz="UTC") -> "Dataset": ...
    @staticmethod
    def from_numpy(time: np.ndarray, values: np.ndarray, columns: list[str],
                   units=None, tz="UTC") -> "Dataset": ...
    @staticmethod
    def from_profiles(profiles: dict[str, Profile]) -> "Dataset": ...
```
- One concrete class backed by a pandas DataFrame with a sorted, unique, tz-aware UTC index;
  every constructor normalises into it (duplicate timestamps → clear error).
- No file or network I/O anywhere in `core/data` (a test asserts `core/data` does not import
  `open`-based readers, `requests`, or database clients).
- String columns (status flags) are kept.
- If `units` is not given, units come from the plant's bindings at run time (the engine passes
  `plant.column_units()`); a bound column missing from the dataset → one error listing all
  missing columns.
- Tests per constructor (same data through every constructor → identical `fingerprint()`),
  inclusive bounds, tz handling, `native_step` = 15 min for the example data.

## 5. Phase 3: `Loader` in data, `Clock` in engine

### `core/engine/clock.py`
```python
class Clock(ABC):
    def __iter__(self) -> Iterator[datetime]: ...
    def dt(self, t) -> float: ...                       # s to next tick (last: step)
    def __len__(self) -> int: ...
    def position(self, t) -> int: ...                   # index of tick t (for resume)
    def after(self, t) -> "Clock": ...                  # remaining ticks after t (for resume)
    def describe(self) -> dict: ...                     # for checkpoints

    @staticmethod
    def year(year, step="1h", tz="UTC") -> "FixedClock": ...
    @staticmethod
    def days(year, month, day, days=1, step="1h", tz="UTC") -> "FixedClock": ...
    @staticmethod
    def range(start, end, step) -> "FixedClock": ...
    @staticmethod
    def from_data(dataset, step=None) -> "DataClock": ...

class FixedClock(Clock): ...
class DataClock(Clock): ...      # dataset timestamps (step=None) or regular grid over its range
class LiveClock(Clock): ...      # (last_processed, now] aligned to step; `now` injectable
```
Accept `step` as `timedelta` or strings like `"15min"`, `"1h"`; accept datetimes or ISO strings.
`DataClock.describe()` stores the tick list compactly (start, step, count, or the explicit
timestamps when irregular) so it can be rebuilt without the dataset.

### `core/data/loader.py`
```python
class Sample(NamedTuple):
    t: datetime; dt: float; row: dict[str, float | str]; missing: tuple[str, ...]; gap: bool

class Loader:
    """Sampler: aligns a Dataset to clock ticks. No batching, shuffling or workers."""
    def __init__(self, dataset, ticks: Iterable[datetime], columns=None,
                 align: Literal["exact", "previous", "mean"] = "previous",
                 max_gap: timedelta | None = None): ...
    def __iter__(self) -> Iterator[Sample]: ...
```
The loader takes ticks (any iterable of datetimes), so `core/data` does not import the engine.
Data is already in memory: convert the needed columns to numpy once and walk them; no per-row
pandas indexing. `mean` for coarser ticks; `max_gap` default 2 × native step. Tests: 15-min data
on hourly ticks (`mean`, checked by hand), gaps, missing columns.

## 6. Phase 4: the engine

### `step.py` (moved from `core/modes/twin.py` / `scenario.py`)
- `twin_step(plant, sample, states, plan)`: apply params valid at `t`; for every bound module
  build inputs and inlet flows from the row (`to_si`), call it on its own measured boundary,
  compute soft sensors + health; skip modules with missing values (reason recorded).
  Stateful modules: state bound to a sensor (`ModuleBindings.state`) → take it from the
  measurement; else integrate from the previous state with `step(..., dt)`. Test both.
- `chained_step(plant, sample, states, plan)`: plant-level inputs from the row through root
  bindings (`""` path; profiles use the same mechanism), one `plant.step`/`plant(...)`.
- `plan` = per-run precomputed binding plan (built once, not per row).

### `results.py`
`Results`: append step results; `res[path]` → object with attribute access per output field
returning `pd.Series` (`res["doublet.esp"].power`); `res.to_frame()` (MultiIndex columns);
`res.summary()` → a small dataclass/DataFrame with energy totals per energy port (J and MWh in
the printed view), peaks, operating hours, alarm counts/rates, skipped counts with reasons;
`__repr__` prints the summary; `save(path)` / `load(path)` (parquet if available else CSV +
JSON metadata).

### `callbacks.py`
`Callback` with `on_run_start/on_step_start/on_step_end/on_error/on_run_end`;
`EventLog` (JSON lines + `log(kind, **payload)` for agent prompts/answers/token usage),
`Progress` (every N steps via `logging`), `AlarmCollector`, and
`AutoCheckpoint(path, every: int | str)` (steps or time span) which calls
`engine.save_checkpoint`.

### `checkpoint.py`: what a checkpoint contains
```python
class Checkpoint(BaseModel):
    version: int = 1
    run_kind: Literal["simulate", "replay", "live"] | None
    plant_class: str | None          # importable "module:QualName" of the plant class
    plant: dict                      # plant.to_dict(): params, histories, bindings
    module_states: dict[str, Any]    # states of stateful modules (JSON-serialisable)
    clock: dict | None               # clock.describe()
    position: datetime | None        # last completed tick
    dataset_fingerprint: str | None  # of the dataset the run started with
    remaining_data_file: str | None  # sibling file with the rows still needed to finish the run
    results_file: str | None         # sibling file with results so far
    created_at: datetime
```
- Self-contained: because datasets are in memory, the checkpoint stores the rows still needed to
  finish the run (`dataset.after(position)`, only the bound columns) in
  `<path>.data.parquet|csv`, results so far in `<path>.results.parquet|csv`, and the rest in
  `<path>` (JSON). All files written atomically (temp + rename). For `live` no data is stored
  (each call brings its own new rows).
- `Engine.save_checkpoint(path)` works at any time: before a run (plant only), **during** a run
  (from a callback, between steps, never mid-step), and after a run.
- `Engine.load_checkpoint(path) -> Engine` imports `plant_class`, rebuilds the plant with
  `plant_class.from_dict`, restores states, clock, remaining data, position and results;
  `engine.plant` exposes the restored plant. If the class cannot be imported → clear error
  naming it.
- `engine.resume() -> Results`: continues the stored run from `position` to the end of its
  clock, appending to the stored results; takes no arguments. Nothing left → returns the stored
  results.
- `live` uses the same checkpoint: the `checkpoint=` path is loaded if it exists; the run covers
  ticks in `(position, now]`; rows at or before `position` in the given dataset are ignored (so
  repeated or overlapping calls are idempotent); ticks the given data does not cover are left
  for the next call (not recorded as processed); the checkpoint is saved at the end (and by
  `AutoCheckpoint` if added).

### `engine.py`
```python
class Engine:
    def __init__(self, callbacks: list[Callback] | None = None,
                 on_error: Literal["record", "raise"] = "record"): ...
    plant: Module | None             # plant of the current/last run
    results: Results | None

    def simulate(self, plant, dataset, clock) -> Results: ...
    def replay(self, plant, dataset, clock=None, start=None, end=None, only=None) -> Results: ...
    def live(self, plant, dataset, checkpoint, step=None, now=None,
             sink: Callable[[Results], None] | None = None) -> Results: ...
    def save_checkpoint(self, path) -> None: ...
    @classmethod
    def load_checkpoint(cls, path, callbacks=None) -> "Engine": ...
    def resume(self) -> Results: ...
```
- All public methods are thin wiring (~30 lines) around one private loop
  `_run(kind, plant, dataset, clock, step_fn)` handling the loader, callbacks, errors
  (`record`: store per step and continue; `raise`: re-raise), states, results and the current
  position (so a checkpoint can be taken at any step boundary).
- `replay` default clock = `Clock.from_data(dataset)`; `only=[paths]` restricts evaluation (used
  by calibration).
- `live` returns only the results of the ticks processed in that call; `sink` receives them.
- Accept `now`/`start`/`end` as datetimes or ISO strings.
- Performance: binding plan built once; iterate numpy arrays, no per-row pandas indexing; cache
  fluid properties for unchanged `(p, T)`. Measure and report replay time.

## 7. Phase 5: calibration (`gemini/optim/calibrate.py`)

```python
def calibrate(plant, dataset, module_path, fields=None, start=None, end=None,
              engine=None, apply=True) -> CalibrationResult: ...
```
- Objective via `engine.replay(plant, dataset, only=[module_path], ...)`; residuals between
  predicted outputs and the module's `measured` bindings, normalised per output.
- `scipy.optimize.least_squares` with `ParamRef` bounds; list params flattened.
- `apply=True` (default, as in the acceptance script) overwrites the module's current params
  with the fitted values. It does not add a dated-param entry. Document this in the docstring.
- `CalibrationResult` with a readable `__repr__`: fitted vs initial values, RMS before/after per
  output, evaluations, success.
- Works for `heatexchanger.ua` and `esp.head_coeff` (e2e: calibrate HX UA on the first 7 days,
  validate on the rest, previous thresholds).

## 8. Phase 6: public API (`gemini/__init__.py`)

Curated, small, documented exports:
```python
from gemini.core.engine.engine import Engine
from gemini.core.engine.clock import Clock
from gemini.core.data.dataset import Dataset
from gemini.core.types import Profile, Stream, Fluid, BRINE, WATER
from gemini.core import modules                        # gm.modules.ESP, gm.modules.HeatExchanger, gm.modules.Module ...
from gemini.core.modules import plants                 # gm.plants.Doublet (generic plants only)
from gemini import legacy                             # gm.legacy.read_project / to_plant / ...
from gemini import optim
__all__ = [...]
__version__ = ...
```
- `gm.modules` exposes every equipment class and `Module`, `Sequential`.
- `Profile.constant(value, unit=..., clock=...)` exists (add the `clock=` overload if missing).
  Remove any `Profile.from_csv`; build profiles from in-memory data
  (`Profile.from_series(series, unit=...)`).
- Error messages users will hit must name the module path, port/field, value and unit.
- `tests/unit/test_public_api.py`: `dir(gm)` contains exactly the documented names; every
  exported name has a docstring.

## 9. Phase 7: remove `core/modes/`

- Before deleting `core/modes/`, capture reference outputs of the old `history.replay` on the
  first day and of the old scenario run into `tests/fixtures/`; the new engine must reproduce
  them exactly.
- Delete `core/modes/`; move its tests into the new tests layout (section 11).

## 10. Phase 8: examples layout and naming

Rules:
- `examples/<category>/<example-name>/`: every file the example needs lives in its folder;
  the entry point is always `run.py`. A short module docstring at the top of `run.py` says what
  it shows and how to run it (`python examples/<category>/<example-name>/run.py` from the repo
  root).
- Plants and data used by more than one example live once in `examples/shared/<name>/` (no
  copies of the large CSV). This is the only exception to the rule above.
- Nothing example-specific inside `gemini/`.
- **Only `examples/legacy/` touches the old GEMINI files.** Every other example (and every test
  except the legacy ones) uses the new files only: `plant.json`, the new CSV, new outputs.

Names: the old name `geothermal_example` says nothing. Replace it everywhere (code, file and
folder names, docs, tests, comments):
- The plant (doublet with ESP, separator, filters, heat exchanger, injection pump, producing
  heat) → class `DoubletHeatPlant`, moved from `gemini/core/modules/plants/geothermal_example.py`
  to `examples/shared/doublet_heat/plant.py` (`git mv`, then rename). Its tests move
  with it into `tests/integration/` or `tests/e2e/`. `Doublet` stays in the package.
- The old GEMINI project files and the old CSV → `examples/legacy/gemini_project_bridge/
  old_project/` (`git mv`; the old files keep their content, only the folder is renamed; if
  file names contain the old name, rename and update references).
- New files in `examples/shared/doublet_heat/`, **generated by the bridge example** and
  committed:
  - `plant.json`: `plant.save()` output (params, dated histories, bindings).
  - `doublet_2024_15min.csv` (≈6 months of 15-min data from 2024): comma-separated, a `time`
    column (ISO 8601, UTC), one column per bound measurement named
    `<module path>.<field>` (e.g. `doublet.esp.frequency`), values in SI; units are declared in
    the bindings in `plant.json`.

Target:
```
examples/
├── shared/
│   └── doublet_heat/
│       ├── __init__.py
│       ├── plant.py                    # class DoubletHeatPlant(Module): structure only, no GEMINI code
│       ├── plant.json                  # new format, generated by the bridge
│       └── doublet_2024_15min.csv      # new format, generated by the bridge
├── basics/inspect_plant/run.py         # load the plant, print the tree, params, ports, energy ports
├── replay/doublet_soft_sensors/run.py  # replay; ESP efficiency, HX UA and other soft sensors; summary
├── calibrate/heat_exchanger_ua/run.py  # fit HX UA on 7 days, validate on the rest
├── simulate/esp_frequency_sweep/run.py # thermal power and electricity vs ESP frequency
├── live/daily_update/run.py            # feed one day at a time to engine.live, checkpoint, resume
└── legacy/gemini_project_bridge/
    ├── old_project/                    # original GEMINI files + old CSV (the only old files)
    └── run.py                          # old -> new plant + Dataset -> replay with the new engine
                                        # -> write plant.json + new CSV (--out, default runs/bridge/)
                                        # -> write old .param files + old-format results CSV
```
Add `examples/__init__.py` and `examples/shared/__init__.py` so
`from examples.shared.doublet_heat.plant import DoubletHeatPlant` works from the repo
root. Delete the old numbered example scripts (e.g. `00_quickstart.py`, `10_custom_plant.py`);
their useful content goes into the examples above (custom-plant content into
`basics/inspect_plant` or the `plant.py` docstring). Each example uses only `import gemini as
gm` (plus pandas/numpy and the shared plant), and writes outputs under `runs/` (gitignored).

## 11. Phase 9: tests layout

```
tests/
├── unit/          # mirrors gemini/ exactly: gemini/a/b/c.py → tests/unit/a/b/test_c.py
├── integration/   # several pieces together on small or synthetic data
├── e2e/           # whole user paths on the real example data
└── fixtures/      # golden numbers from the original GEMINI code + reference outputs
```
- **unit**: one test file per source file, same relative path (e.g.
  `gemini/core/modules/pumps/esp.py` → `tests/unit/core/modules/pumps/test_esp.py`). Tests one
  module/function alone: no engine run, no example data. Add a test that fails if a
  `gemini/**/*.py` file with logic has no matching unit test file (allow-list `__init__.py` and
  pure re-export files).
- **integration**: e.g. plant + engine on a few hours of synthetic data, `state_dict`
  round-trip, `save`/`load`, loader + clock alignment, callbacks order, error policies,
  checkpoint interrupt/resume for simulate and replay (a callback raises a custom interrupt
  after N steps; save in `on_error`; load in a fresh engine; `resume()`; compare with an
  uninterrupted run), `AutoCheckpoint`, live idempotency (two calls with injected `now`, a third
  with the same `now` processes nothing; overlapping data processed once), the stateful rule,
  calibration on synthetic data with known true UA.
- **All tests use the new file formats.** Only `tests/unit/legacy/` (small synthetic old
  files) and `tests/e2e/test_legacy_bridge.py` touch old GEMINI files. The bridge e2e runs the
  bridge into a temp folder and checks: generated `plant.json` and CSV equal the committed
  files in `examples/shared/doublet_heat/`; old → new → old round trip; `check_wiring` returns
  `[]`; old-format results CSV is readable by `legacy.read_csv`.
- **e2e**: through the public API only, on `examples/shared/doublet_heat`:
  `test_quickstart.py` (= section 1), full replay (reconciliation, mass/energy balance,
  electricity, alarm rate, timing < 60 s), golden match vs
  `tests/fixtures/`, calibration on real data (7 days fit / rest validate), and
  `test_examples.py` which runs every `examples/**/run.py` in a subprocess and checks it exits 0.
- **fixtures**: golden numbers JSON and reference outputs, loaded by helpers in
  `tests/conftest.py`.
- Move every existing test into this layout (`git mv` where possible); delete tests of removed
  code (drivers, modes). Mark e2e tests `@pytest.mark.e2e` (registered in `pyproject.toml`) so
  `pytest -m "not e2e"` gives a fast run.

## 12. Phase 10: docs

- `.claude/docs/api.md`: the public API, the quickstart, rules for keeping it small (new
  exports need a reason; users never need `core.*` imports for common tasks).
- `.claude/docs/data.md`: in-memory only (no drivers; the user or the backend reads files and
  databases), Dataset constructors, units as metadata, UTC, Loader (sampler), alignment, gaps.
- `.claude/docs/engine.md`: three methods and how they differ (input source, step function,
  resume), shared loop, clock, callbacks, checkpoint contents and guarantees (self-contained),
  live idempotency, stateful rule, "no infinite loop", PyTorch mapping table.
- `.claude/docs/legacy.md`: the bridge (both directions), the tables, the `nodes` map, round-trip
  guarantees, "all GEMINI conversion lives here and nowhere else".
- `.claude/docs/testing.md`: unit / integration / e2e / fixtures, mirror rule, e2e marker.
- `.claude/docs/conventions.md`: dependency rule
  `core.physics` ← `core.types` ← `core.modules` ← `core.data` ←
  `core.engine` ← `legacy` ← `optim` / `design` ← `agentic` ← `gemini/__init__` (make it true); "no
  examples inside the package"; examples layout rules.
- `AGENTS.md` tree + links; README quickstart = section 1.

## 13. Final report (last message)

1. Final tree of `gemini/` (three levels under `core/`), `examples/` and `tests/` (two levels).
2. Deleted/moved/renamed paths (drivers, modes, config, datasets, example plant, old examples),
   and where each part of `core/config/` went.
3. The acceptance script output (paste it) and any change you had to make to the script.
4. Replay timing on the full data and what you optimised.
5. Checkpoint format (example JSON, trimmed) and the resume/idempotency test results.
6. E2E table (all metrics) vs the previous task.
7. Calibration results (HX UA, ESP head_coeff).
8. Unit-test mirror check result (any source files without tests, and why).
9. New `NOTE(refactor)`s and decisions not covered here.
10. Lint/test summary lines (`pytest -m "not e2e"` and full `pytest`).
