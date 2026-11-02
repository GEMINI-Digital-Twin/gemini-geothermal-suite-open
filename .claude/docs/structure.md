# Package structure

Every folder of `gemini/` has a reason that a reviewer can check. This page holds the rules, the
definition of each folder and the words that keep one meaning each. `tests/unit/test_package_boundaries.py`
checks the direction of imports (R4) from the real imports; `tests/unit/test_mirror.py` checks R6.

## Rules

- **R1 A folder exists only if both hold:** it is a domain a user addresses by name
  (`gm.study.minimize`, `gm.case.Case`), and it has several files with separate responsibilities.
  Otherwise it is one file (`gemini/runtime.py` still gives `gm.runtime.settings`). Reason: a folder
  is a promise of a domain; a folder with one idea in it costs a hop to read and says nothing.
- **R2 The folder name is the word the user says** (the `gm.<name>` namespace), never an
  implementation word (`utils`, `helpers`, `core`, `base`, `common`, `misc`). Reason: a name that
  says how it is built tells a reader nothing about what to look for in it. `_utils` is the one
  private exception, and R3 keeps it small.
- **R3 Private helpers live next to their only user:** `<folder>/_utils/` or a `_name.py` file; the
  top-level `gemini/_utils/` holds only helpers used by two or more folders. Reason: a helper far
  from its user is read without its context and grows users it was not made for.
- **R4 One direction of imports:** `units`, `errors`, `_utils` -> `ops` -> `physics` -> `streams`
  -> `modules` -> `plants` -> `engine` -> `evaluate` -> `study`; `case` is read by `engine`,
  `evaluate`, `study`; `analysis` sits on top; nothing imports `compiler`; `compiler` may import
  everything above it. Reason: a cycle between folders means two folders are one idea or a file is in
  the wrong place; one direction lets a reader and the compiler take any folder alone.
- **R5 A file belongs where its inputs belong:** code that reads or builds case inputs (series from
  CSV, synthetic profiles) is part of `case`; code that runs time is `engine`; code that judges
  results is `evaluate`. Reason: P1 of [inputs.md](inputs.md), one owner and one place for a thing.
- **R6 Tests and docs mirror the package:** `tests/unit/<folder>/`, one docs page per public folder.
  Reason: a reader finds the test and the page of a file without searching.
- **R7 No compatibility paths:** a move updates every import in the repo (package, tests, examples,
  scripts, docs); no re-export is left at the old place. Reason: two names for one thing is how a
  rule stops being true.

## The folders

Each folder is defined by what it takes, what it gives back, and what it may call. A file goes to the
one folder whose definition it meets; if it meets two, it is two files.

| folder | takes | gives | may call | never | reason it is separate |
| --- | --- | --- | --- | --- | --- |
| `units` | a number with a unit | SI number, or display `Quantity` (`display.py`: the table quantity -> display unit) | nothing in gemini | knows any equipment or metric | one unit format at every boundary needs one owner |
| `errors` | an issue | exception and issue types | nothing | decides anything | every folder reports problems the same way |
| `ops` | numbers or arrays | numbers or arrays | `units` | knows a physical meaning | the same math runs on scalars, arrays and the compiler's backends |
| `physics` | physical states (T, p, composition) | properties and correlations | `ops`, `units` | holds parameters or state; knows a module | a correlation is true for any equipment that uses it |
| `streams` | fluid composition and state | `Stream`, `Fluid`, ports | `physics`, `units` | knows a module | what flows between modules is one type for every module |
| `modules` | parameters, inputs, inlets, state | outputs, outlets, next state, for one step | `physics`, `ops` | loops over time; reads a case | one piece of equipment, testable alone with `gm.call` |
| `plants` | modules and connections | one module (a `Plant`) and its plan | `modules` | loops over time | a plant is a module, its plan is built once |
| `case` | files or values written before any plant exists | `Case`, economics, requirements, series, demand frames | `units`, `errors`, `physics` (the geotherm of a site), the role table of `plants` | runs or judges a plant | the outside world and its rules change without the plant (P2 of [inputs.md](inputs.md)) |
| `engine` | one plant, one case | one run: results over time | `plants`, `case` | judges, repeats runs, chooses | time is handled in one place (schedule, scan) |
| `evaluate` | plant, case, results of one run (or a retained `gm.call` tree) | numbers and judgement: costs, emissions, balances, verdict, summary, report | `case`, `engine`, `units` | runs the plant | judging must not change what was computed; it can be redone on saved results |
| `study` | plants and cases plus a method | many runs and a choice (best, samples, sensitivities, fitted parameters) | `engine`, `evaluate`, `analysis` (the nodal solves that `size` uses) | changes the physics | a question answered only by running the whole system many times |
| `analysis` | one module and a set of fixed conditions | curves or operating points (nodal, injectivity, pump curve) | `modules` via `gm.call`, `plants` to find the module of a plant | runs the engine; uses time or a case | engineering questions about one piece of equipment, answered without a plant or a year |
| `runtime` | how to run (processes, batch size, backend, precision, display units) | settings | nothing | changes a result value | it changes speed or display only, so it is not an input (P4 of [inputs.md](inputs.md)) |
| `compiler` | a plant and a case | a faster runner with results equal to eager | everything above | is imported by any of them | optional, like an ahead-of-time compiler |

The one call from `case` to `plants` is the role table (`plants/roles.py`): a requirement names a role
and a quantity of it, and the table says which exist, so there is one table, owned by the plant (P6 of
[inputs.md](inputs.md)). `plants` never imports `case`.

How the test reads the column "may call": a folder may import every folder to its left in the chain
of R4 (`plants` imports `modules`, `streams`, `physics`, `ops`, `units`, `errors`, `_utils`), and
the folders `case` and `runtime` as the table says. `runtime` is read by every folder from `streams`
up, and it calls `ops` only to select a backend.

`MAY_IMPORT` in `tests/unit/test_package_boundaries.py` is the table in code.
`KNOWN_VIOLATIONS_MUST_BECOME_EMPTY` lists the imports that break it today, each with who removes it;
the test fails when an entry is no longer true or a new violation appears. After the folder work the
only two entries are the runtime default fluid (`runtime` -> `streams`, `streams` -> `runtime`),
which the module contract removes (worker A): the fluid is a case input.

Three readings of the column "may call" that the code needs: `case` reads `physics` (a site gives
its geotherm by the rule of `physics/ground.py`) and the role table of `plants`; `analysis` takes a
plant to find its module, so it reads `plants`; `study` reads `analysis` (`size` uses the nodal
solves). `engine` and `evaluate` never read `analysis`.

### Study or analysis, the test

A function that calls the engine (a run over time on a case) is `study`; a function that calls one
module at fixed conditions, with no time and no case, is `analysis`. So `calibrate` (fit plant
parameters to measured series by running the plant) is `study`; nodal analysis (where the well curve
meets the pump curve) is `analysis`; corrosion and erosion computed from the results of a run are
`evaluate`, and their rate correlations are `physics`.

## Words that keep one meaning each

- **plan**: the plant's module order (`plants/_utils/plan.py`).
- **bindings**: which columns feed which inputs, in a run (`engine/bindings.py`, `RunBindings`) and
  as a module declares them (`modules/bindings.py`, `ModuleBindings`): one meaning, the column of a
  dataset that feeds an input. The unit metadata of a dataset column is `ColumnInfo` of
  `case/dataset.py`, not a binding.
- **graph**: the compiler's traced form (`compiler/ir.py`: the `Graph` and its nodes, with the kinds `op`
  and `fixed_point` today and `scan` for a stateful plant).

The compiler is split by the job of each part, as in a compiler textbook: capture (`trace/`: tracer,
proxy, breaks, declared limits), the intermediate form (`ir.py`), transforms (`passes/`, one file
per pass), caching (`cache.py`), execution (`interpret/`: the interpreter, one file per backend
`numpy.py` and `python.py`, `root.py` for a module called for real, `run_graph.py` which picks) and
the entry `compile.py`. `executor.py` is the graph executor the engine calls, `run.py` runs one
module over arrays.

**Three words for what an executor gives.** `ChunkResult` (`engine/chunkresult.py`) is what an
executor gives for one module over the rows of a chunk, `GraphResult` (`compiler/interpret/`) is a
`ChunkResult` that also keeps its graph, and `TwinResult` (`engine/twinresult.py`) is what one twin
gave over a chunk. The word *evaluate* stays for the public folder `gm.evaluate`.

**One record of a failed row.** `errors/rows.py` builds the record of a row that gave no result
(`failed_row`, `skipped_row`, `row_code`, the `SKIPPED` code). The engine fills it from the exception
of either executor, `Results.errors` lists it and `gm.evaluate.failures` groups it. The `Failed` and
`RowFailures` of `ops/` are the mechanism that carries a failed check through arrays, not a record.

### One name in two folders: `executor`

`engine/executor.py` is the interface the engine calls to evaluate one module over a block of
ticks; `compiler/executor.py` is the implementation that runs a graph. This is correct: the
interface lives in the core, the implementation in the compiler, which registers itself. It is the
one allowed name that appears in two folders, because it is the plug between them. Every other
name means one thing in one folder.

## The tree

```text
gemini/
  __init__.py        public top names; gm.streams is one of them
  runtime.py         settings (processes, batch size, backend, precision, display units)
  units/             Quantity, conversions, the unit rule, the return shapes, inputs.py (the shared input formats), display.py (quantity -> display unit)
  errors/            error classes, issues, rows.py (the failed-row record)
  _utils/            helpers used by two or more folders
  ops/               math API, dispatch, kernels, failed rows
  physics/           correlations and fluid properties only
  streams/           Stream, Fluid, Ports, stream kinds
  modules/           Module, declarations, containers, results, bindings, gm.call; one folder per module domain, each with its _physics.py
  plants/            Plant, the plant classes, roles.py (the one owner), _utils/ (plan, loops, serialization, doublet design, resize)
  case/              Case and its sections, economics, requirements, dataset.py, profile.py, demand_frame.py
  engine/            simulate, replay, live, resume, Results, check, schedule/ (with its dispatch policy), runner, bindings, executor
  evaluate/          costs, emissions, balances, verdict, summary, report; _utils/
  study/             Study, size, minimize, sample, sensitivity, calibrate
  analysis/          nodal.py, fits.py (and the pump curve), integrity.py
  compiler/          compile.py, executor.py, ir.py, trace/, passes/, cache.py, interpret/, run.py
```

**Folders with a single file:** none. `analysis/` (3 files), `errors/` (3) and `streams/` (4) are the
smallest, each with separate responsibilities.

**Names that break R2:** `_utils` is the one private exception (R3). `ops` and `modules` are the
words a user says (`gm.ops`, `gm.modules`).

**What stays apart, and why.** `Profile` (`case/profile.py`: one validated SI series with
`at`, `resample`), `Dataset` (`case/dataset.py`: a table of raw columns with unit metadata) and the
demand frame (`from_csv`, `from_values`: a pandas frame with `attrs["units"]`) were not merged into
one class. The engine already has one table type: `as_dataset` wraps a frame into a `Dataset`
(`attrs["units"]` is its unit metadata), and `Dataset.from_profiles` builds one from `Profile`s, so a
demand frame and a `Profile` are two constructors of the one `Dataset`, not two types the engine
chooses between. Folding `Profile` into `Dataset` removes a public constructor (`Profile.constant`
is used by 12 test, fixture and script places) and its `at` and `resample` semantics; `gm.Dataset`
stays public because measurements need it. This is open, not decided against.

**One name for the three displays.** `units/display.py` owns the table of quantity -> display unit
and the conversion of a result to it; `evaluate/_utils/display.py` owns the names of the metrics of
a table (`heat_delivered`, `lcoh`) and the two rules that need them (a difference keeps its SI unit,
a long span is shown in years).

## Moves of the folder work

`gemini/types/` mixed five jobs and was removed; each file went to the folder whose definition it
meets. The later steps of the folder work append their rows here.

| old | new | rule |
| --- | --- | --- |
| `types/quantities.py`, `types/bare.py`, `types/shapes.py` | `units/quantities.py`, `units/bare.py`, `units/shapes.py` | R2: a quantity, the unit rule and the `Value` are the unit format |
| `types/flows.py`, `fluid.py`, `ports.py`, `streams.py` | `streams/flows.py`, `fluid.py`, `ports.py`, `kinds.py` | R1: what flows between modules |
| `types/results.py`, `types/bindings.py` | `modules/results.py`, `modules/bindings.py` | R5: what a module returns and its metadata |
| `types/profile.py` | `case/profile.py` | R5: case inputs |
| `types/inputs.py` | `units/inputs.py` | the shared input formats (a value with its unit, a range, a series) are read by `case` and by `plants`, so they sit below both: they take a value with a unit and give SI |
| `runtime/` | `runtime.py` | R1: one idea in two files |
| `_utils/paths.py` | `tests/fixtures/paths.py` | the package does not know where a checkout keeps `inputs/` |
| `physics/doublet.py` | `plants/_utils/doublet_design.py` | physics knows no module |
| `physics/dispatch.py` | `engine/schedule/dispatch.py`; `circuit_flow`, `temperature_after` to `physics/energy.py` | a policy is not a correlation |
| `case/roletable.py`, `plants/_utils/roles.py` | `plants/roles.py` (`gm.case.roles()` is `gm.plants.roles()`) | the role table describes the plant, not the outside world; one owner of roles |
| `plants/_utils/serialization.py` | `plants/_utils/serialization.py` | the plant dict is a plant tool |
| `study/_utils/resize.py` | `plants/_utils/resize.py` | a plant on another number of doublets is about the doublet; the study only asks for a count |
| `modules/_utils/cost.py` | `modules/_utils/equipment.py`; the pricing to `evaluate/_utils/pricing.py` | a module never reads a case |
| `physics/costs.py` | `evaluate/_utils/pricing.py` | a unit cost times a size is not a correlation |
| `modules/_utils/wiring.py` | `modules/_utils/trace.py` | `trace_wiring` observes stream identities; "wiring" is a plant's connections |
| `plants/_utils/wiring.py`, `inputs.py`, `run.py`, `constraints.py` | `cascades.py`, `plant_inputs.py`, `call.py`, `targets.py` | a name means one thing in one folder |
| `run/` (check, simulate, results, schedule, apply) | `engine/check.py`, `simulate.py`, `results.py`, `schedule/schedule.py`, `apply.py` | one plant on one case over time is one domain; the import cycle `run` <-> `engine` and the import order of `engine/__init__.py` are gone |
| `run/_utils/dispatch.py`, `sources.py`, `limits.py`, `roles.py` | `engine/schedule/dispatch.py`, `sources.py`, `limits.py`, `fleet.py` | the schedule with its policy; the units it sets are a fleet, `plants/roles.py` stays the one owner of roles |
| `run/dataset.py` | `case/dataset.py` (`ColumnInfo` moves with it; `bound_unit` to `engine/bindings.py`) | R5: a measured series is a case input; the engine only aligns it to ticks; `case` imports nothing of `modules` |
| `engine/step.py`, `evaluation.py`, `outcome.py`, `rows.py` | `engine/bindings.py` (`RunBindings`), `chunkresult.py` (`ChunkResult`), `twinresult.py` (`TwinResult`), `rowwise.py` | one word one meaning: bindings, evaluate, outcome, failure |
| `ops/failures.py` (`Failures`) | `ops/failedrows.py` (`RowFailures`) | `Failures` is also what `gm.evaluate.failures` returns |
| `engine/runner.py` `row_code`, `error_record` | `errors/rows.py` (`row_code`, `failed_row`, `skipped_row`, `SKIPPED`) | the one record of a failed row |
| `compiler/graph/` (17 files) | `compiler/ir.py` (graph, node, body), `trace/` (tracer, proxy, breaks, rootbreak, limits, errors), `passes/`, `cache.py`, `interpret/` (interpreter, fixedpoint, codes, `rowerror.py` from `failures.py`, `graphresult.py`, `numpy.py`, `python.py`, `root.py`, `run_graph.py`), `run.py` (from `runner.py`); `compile` from `executor.py` to `compile.py` | the jobs of a compiler textbook (item 25); `Evaluation` is `GraphResult`, `evaluate` is `run_graph` |
| `data/` (`from_csv`, `from_values`, `profile_schema`) | `case/demand_frame.py`; `gm.data.*` is `gm.case.*` | R5: a demand read from a file is a case input; two files do not make a folder (R1) |
| `evaluate/` (36 files) | `costs.py` (capex, opex, annualised cost, lcoh, lcoc, lcts, npv, payback), `emissions.py` (co2), `balances.py` (energy, mass, plant balance, and the audits of one call), `verdict.py` (bounds, failures, requirements, run_all, verdict), `summary.py` (totals, capacities), `report.py` (report, compare) | grouped by job; each public function is still `gm.evaluate.<name>`. `report` is apart from `summary` because it reads the verdict, which reads the totals |
| `modules/_utils/balance.py` | `evaluate/balances.py`; `gm.modules.collect_flows`, `emissions`, `energy_balance`, `mass_balance` are `gm.evaluate.collect_flows`, `call_emissions`, `call_energy_balance`, `call_mass_balance` | the audits judge a retained call; `modules` may not import `evaluate`, so they could not stay at `gm.modules.*`. `call_` keeps them apart from the run versions of the same name |
| `evaluate/_utils/display.py` | `units/display.py` (the table quantity -> display unit, `by_si_unit`, `shown`) and `evaluate/_utils/display.py` (metric names, years, differences) | `units` knows no metric and no role |
| `analysis/calibrate.py` | `study/calibrate.py` | it runs the plant through `Engine.replay`: the test of study or analysis |
| `analysis/solves.py`, `analysis/wells.py` | `analysis/nodal.py` (the nodal analysis and its solves), `analysis/fits.py` (`pump_curve`) | two files said nodal analysis; the pump curve is a fit of one module |
| `physics/hydraulics.py` `pipe_path_profile`, `corrosion_profile`, `erosion_check` | `modules/wells/_physics.py` | they take a `Stream` and a `Fluid`; physics knows neither |
| `inputs/examples/<name>/` | `examples/<name>/` (the scripts stay beside them) | one folder a user can copy: case, plants, data |
| `inputs/doublet_heat`, `inputs/legacy_project`, `inputs/plants` | `tests/fixtures/doublet_heat`, `legacy_project`, `plants` | data the tests read; `inputs/` is removed |

`analysis/integrity.py` (`corrosion_forecast`) takes the conditions of one model, not the results of
a run, so it stays in `analysis`. `case/choices.py` and `study/_utils/choices.py` are gone, and
`study/_utils/target.py` lets `sample` and `sensitivity` move only what the case declares uncertain
(`minimize` varies the values of the plant only).
