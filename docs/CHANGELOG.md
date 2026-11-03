# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- Documents by audience: `README.md` is short and `docs/` is for people, with `docs/guide.md`,
  `docs/rules.md` (every project rule, out of `AGENTS.md`) and this file, moved from the root.
- Every git worktree goes under `.tmp/`, and a test fails if anything under `.tmp/` is tracked.

## [0.5.8] - 2026-11-03

Every public name, default and number is the same as 0.5.7.

### Changed
- A trial takes about 14% less CPU time: the table of a run is built from its arrays in one
  step, and the energy balance reads its columns from the run instead of from a table copy.
  Every table and number is identical.

## [0.5.7] - 2026-11-03

Every public name, default and number is the same as 0.5.6.

### Changed
- A study runs faster: `examples/hackathon.py` takes 2:11 instead of 3:29 on the same machine, and
  prints the same output. The frame of a run is built without a `Series` per column, a balance and
  the bounds check read only the columns they need, and `named_modules` walks without nested
  generators. No number, name or signature changes.

## [0.5.6] - 2026-11-03

Every public name and default is the same as 0.5.5 (`tests/fixtures/public_api_0_5_0.json` is the
frozen surface). Numbers change on purpose where the two streams of a counterflow heat exchanger
have equal capacity rates: LCTS of the sample plants falls by at most 0.15%. No plant of the sample
changes rank or feasibility, and a search may end on another design.

### Fixed
- The split of the heat between the heat exchanger, the heat pump and the peak boiler no longer
  depends on the last bit of a calculation (known issue of 0.5.5). The cause was not the heat pump:
  `heat_transfer.effectiveness_counterflow` lost all its digits when the capacity ratio was within
  some bits of one, as on winter days when both streams of the exchanger carry the same flow, and
  gave for example 2/3 instead of 0.6885. It now tends smoothly to `NTU/(1+NTU)`. The numbers of
  those days change: a boiler heat of the sample plants by up to 3.3%, because they were wrong.
- `heat_transfer.logarithmic_mean`, and with it `lmtd` and the Lorenz mean temperature, lost its
  digits the same way for two values a few bits apart.

### Changed
- CI and the release workflow run NumPy with AVX-512 again.

## [0.5.5] - 2026-11-02

The first version published as a package. Every public name, default and number is the same as
0.5.4 (`tests/fixtures/public_api_0_5_0.json` is the frozen surface).

### Added
- Every new version on `dev` is published automatically: the wheel and the source archive on a
  GitHub Release, and the sandbox image as `ghcr.io/geomind-spe-geohackathon-2026/gemini-sandbox`.
  See `VERSIONING.md`.

### Fixed
- `pydantic>=2.10.0` is required; it was `>=2.5.0`, and below 2.10 `gm.study.sample` and
  `gm.study.sensitivity` with worker processes fail on a pickling error.
- `doc` of `describe` no longer depends on the Python version: 3.13 strips the indentation of a
  docstring and 3.11 and 3.12 did not, so the indentation is now always removed.
- `tests/unit/test_code_quality.py` needs `mccabe`, which is now in the `test` group.
- The compatibility tests no longer compare methods gemini inherits from Python or pydantic, whose
  signatures change with those versions, nor the call of an enum class. The frozen file is unchanged.

### Known issues
- On a few winter days of the sample plants the split of the heat between the heat pump and the
  peak boiler is not unique, so a change in the last bit of a calculation moves it. The same
  installation on the same CPU always gives the same numbers, but a CPU with AVX-512 can give others:
  LCTS moves by up to 0.13% on `HeatingPlant`, and the fuel of the boiler by more. This is not new in
  this version. CI runs NumPy without AVX-512 to stay on the expected numbers.

## [0.5.4] - 2026-11-02

Backward compatible with 0.5.3 and 0.5.0 for every number: all are the same to 1e-9 (`gm.study.sample`
and `gm.study.sensitivity` compared with 0.5.3 on the hackathon design, 369 numbers), and no example
verdict changes (`tests/fixtures/public_api_0_5_0.json` is the frozen surface). Two fixes change
behaviour on purpose, for inputs the 0.5.0 code accepted.

### Fixed
- `gm.evaluate.verdict`: a requirement that could not be judged (`passed` None) beside a passed one
  is now a reason of kind `requirement`, so the run is infeasible; it was feasible. It has no
  `violation`, so a search ranks as before. Not a reason: a `when="running"` requirement on a unit
  that never ran (nothing was asked), and the supply of a service already reported as not delivered.
  All undecided and failed-beside-undecided give the reasons of before. `report`, `compare` and
  `Study` read this verdict.
- `nominal_flow` of `Doublet` and `InjectionPump`: zero or below raises `out_of_bounds` (`gt=0`); it
  priced the pump as free or cheaper. Empty stays allowed.

### Added
- `gm.study.sample`: each item of `samples` has `feasible` (`gm.evaluate.verdict` of the draw; False
  for a run with failed steps). `gm.study.sensitivity`: each row has `feasible_low` and
  `feasible_high`. Both are in `to_dict` and read by `from_dict`, which also reads a 0.5.3 result
  without them. `summary`, `Tornado.to_frame` and the order of the rows are unchanged; each trial
  runs one more verdict.

## [0.5.3] - 2026-11-02

Backward compatible with 0.5.2 and 0.5.0: an addition only, every number is the same to 1e-9
(`tests/fixtures/public_api_0_5_0.json` is the frozen surface; the working snapshot gains the code
`deprecated`).

### Deprecated
- A `range` on a leaf of a case or economics file, series leaves included, is read and used by
  nothing. `case.check()`, `economics.check()`, `gm.check` and `Study.check` report it as an `Issue`
  of kind `deprecated` (code `deprecated`, a warning that comes last and stops nothing), and reading
  the case emits `gm.errors.GeminiWarning`. A search range belongs on the plant leaf; to move a case
  value use `uncertainty`; the `range` will be refused in a later version. Requirement `min`/`max`,
  `uncertainty` and a plant `range` are not affected.

### Added
- Schemas for forms: `Case.schema()` and `Economics.schema()` state `kind` as a constant (`"case"`,
  `"economics"`; the plant and study schemas already did), so a generated header is accepted by the
  reader (a document without `kind` is `old_format`). Leaves gain `x-quantity`, `x-units`,
  `x-limits` (SI bounds with their SI unit) and `x-fraction` (a share between 0 and 1); the files
  gain `x-quantities` (units of every quantity used). No existing key changed.
- `gm.evaluate.metrics()`: `title` and `objective` (a target for `gm.study.minimize`) per metric.
- `gm.study.kinds()`: `[{kind, use, title, description, settings}]` for run, minimize, sample,
  sensitivity and size (a preparation), `settings` the JSON Schema of the keys the kind reads.
- `units="display"` (or `"si"`) on `Results.get`, `summary`, `to_frame`, `to_dict`,
  `energy_report` and `Comparison.to_dict`; keyword-only `units="si"` on `gm.evaluate.capex`,
  `opex`, `annualised_cost`, `lcoh`, `lcoc`, `lcts`, `npv` and `payback`, whose value and parts
  then come in display units. The default is unchanged.
- `gm.case.missing(case)`: the paths a case or a partial case dict still lacks, as `Issue`s with
  quantity and accepted units; it never raises.
- `gm.plants.capabilities()[class]["ranges"]` lists every numeric leaf of `params` (and
  `size.doublets`), not only `params.depth`.
- `Issue.is_warning` and the issue kind and code `deprecated`; `raise_issues` leaves a warning out.

## [0.5.2] - 2026-11-02

Backward compatible with 0.5.1 and 0.5.0: additions only, every number is the same to 1e-9, and a
call that does not use them behaves as before (`tests/fixtures/public_api_0_5_0.json` is the
frozen surface).

### Added
- `on_progress=None` (keyword only) on `gm.study.minimize`, `sample`, `sensitivity` and
  `gm.Study.run`: `on_progress(done, total)` is called in the calling process after each finished
  trial, also with `processes=n` and for batched trials. Raising `gm.errors.Cancelled` from it stops
  the study cleanly (later trials do not start, the worker processes are stopped, the exception
  propagates).
- `gm.evaluate.daily_coverage(plant, case, results)`: for each day and service (heating, cooling) the
  demand and the energy from the geothermal plant, from the backup (roles `boiler`, `chp`) and short,
  as quantities in display units, with the failed steps of the day. Its sums are the totals of `gm.evaluate.totals`.
- `gm.evaluate.metrics()`: the metrics of a table of results with their quantity and display unit.

## [0.5.1] - 2026-11-02

Backward compatible with 0.5.0: no name, signature, key or code changed, and every number is the
same to 1e-9 (`tests/fixtures/public_api_0_5_0.json` is the frozen surface; the working snapshot
only changed its version).

### Added
- State connections (`connect(source, target, type="state")`): the target reads what the source
  outlet gave at the previous step; the plant keeps those values in its state under `@previous`.
  They are in the plant file as a connection of type `state` (no new key) and round-trip. This
  replaces the `NotImplementedYet` of the plan compiler.
- The page [Writing a module](.claude/docs/writing-a-module.md): a pump (stateless) and a
  controller (stateful), each alone and inside a plant.

### Changed (same numbers)
- Time is a scan: a stateful plant carries its state from step to step in one call over the whole
  run, eager (`ops.control.scan`) and compiled (a `scan` node of the graph); a year of hourly steps
  of a storage plant no longer runs one tick at a time.
- `minimize`, `sample` and `sensitivity` run their trials on one shared plant as one array pass
  instead of one run and one plant copy each; the first population of a search is one batch. The
  sequence of trials, the history and the ranking are those of 0.5.0.
- A module takes the fluid of its inlet stream (`ThermalStorage`, `InjectionReservoir`), so
  `gm.call` works on them with `state` and `dt`.

### Fixed
- `gm.check` never raises: a module with an unset parameter is reported once and its kind is not
  read, a case wrong by itself gives its own issues, and `case.check` names a value no file can
  hold.

## [0.5.0]

From 0.5.0 the public API is backward compatible (additions allowed if nothing breaks).

### Removed or moved (the last breaking change)
| Old | New |
| --- | --- |
| `gm.evaluate.run_all(plant, case, results)` returning `{passed, checks}` | `gm.evaluate.verdict(plant, case, results)` returning `{feasible, reasons}`; the checks are `energy_balance`, `mass_balance`, `bounds` and `requirements` |
| `gm.physics.control` (`pid_error`, `pid_derivative`, `pid_command`, `pid_integral_increment`, `anti_windup_increment`) | `gemini/modules/control/_physics.py`, private to `PIDController` |

Kept on purpose: `gm.evaluate.call_*` (they audit one `gm.call`) and `gm.ops` (the math API of
module authors). `gm.physics.diagnostics` stays: five modules call it from `health` and a module
may not import `engine`.

### Added
- `tests/fixtures/public_api_0_5_0.json`, `tests/unit/test_api_compatibility.py` and
  `tests/e2e/test_competition_surface.py`.

### Also in 0.5.0 (written under "Unreleased" before the freeze)
**Added**
- `gm.call(..., state=, dt=)`: a module with state takes the state at the start and the step, and
  the result has the key `state` with the state at the end of the step.
- The quantity `gas_burned` (kg/s) of the role `plant`: the co-produced gas burned by the boilers
  and flares of the plant, so a requirement can limit it.

**Changed**
- Module contract: `forward(self, inputs, inlets, state)` is pure (it reads parameters on `self`
  and nothing else, writes nothing, returns `(outputs, outlets)`) and a stateful module has a pure
  `update(self, inputs, inlets, outlets, state, dt)` that returns the next state. A state has no
  default: it comes from `case.initial_state`. A stateful plant is stepped from
  `case.initial_state`.
- Hooks: a pre-hook is called `(module, inputs, inlets, state)` and a forward hook
  `(module, inputs, inlets, state, outputs, outlets)`; a hook that returns a mapping replaces the
  controls and boundaries (pre-hook) or the outputs (forward hook) of that call, `None` observes.
- `gm.simulate` and the engine: a physical failure of a step (`invalid_inlet`, `out_of_bounds`,
  `out_of_range`, `no_convergence`) is a failed row whatever `on_error` says, and the run finishes;
  every other failure follows `on_error`. A trial of a search whose plant fails a step is
  infeasible (violation 1e6) instead of raising, and a NaN value counts as the largest violation.
- `gm.call(module, parameters, inlets, controls, units, ...)`: `units` is required and is `"si"`
  (plain `{value, unit}` in SI) or `"display"` (`Quantity` in the display units of the report);
  the map `{quantity: unit}` is no longer taken by `gm.call`.
- `Best.to_dict()`, `Sample.to_dict()`, the history of a search and the notes of `gm.study.size`
  show the display units of the report instead of bare SI; `from_dict` reads them back.
- `gm.runtime.settings(default_fluid=...)` and `gm.runtime.state()["default_fluid"]` are removed: the
  fluid is a case input (`site.fluid`) or an entry of the plant `fluids`. A module or a `Stream`
  without a fluid raises `missing_value` naming its path; `gm.Stream(...)` requires `fluid`.

## [0.4.0] - 2026-11-02

Breaking: the folders of `gemini/` are grouped by job (rules and tree in
[structure.md](.claude/docs/structure.md)). Moves only; numbers equal to 1e-9; no old path is kept.

### Changed
- `gm.data.from_csv`, `from_values`, `profile_schema` are `gm.case.from_csv`, `from_values`,
  `profile_schema`; `gm.data` is gone.
- `gm.analysis.calibrate` and `CalibrationResult` are `gm.study.calibrate` and `CalibrationResult`.
- `gm.case.roles()` is `gm.plants.roles()`.
- `gm.modules.collect_flows`, `emissions`, `energy_balance`, `mass_balance` are
  `gm.evaluate.collect_flows`, `call_emissions`, `call_energy_balance`, `call_mass_balance`.
- `gm.streams` joins `gm.__all__`.
- `gm.evaluate` is grouped by job (`costs`, `emissions`, `balances`, `verdict`, `summary`,
  `report`); every function is still `gm.evaluate.<name>`.
- `gm.physics.dispatch`, `gm.physics.doublet` and `gm.physics.costs` are removed from the
  namespace; `circuit_flow` and `temperature_after` are in `gm.physics.energy`.
- Sample projects are `examples/<name>/` (were `inputs/examples/<name>/`); the data the tests read
  is in `tests/fixtures/` (was `inputs/`, now removed).

## [0.3.0] - 2026-11-02

Breaking: the inputs of a project are separated by owner and every public entry point follows the
new model (rules and reasons in [inputs.md](.claude/docs/inputs.md)). A checkpoint of 0.2.0, a plant
file of `format: 2` and a `case.json` of the old shape do not load: they raise `old_format` naming the
new form. Nothing of the old names is aliased.

### Changed
- Four files, one owner each: `case.json` (`site`, `demand`, `utilities`, `economics`,
  `requirements`, `time`, `initial_state`), `economics.json`, a plant file (`kind: plant`, `format: 1`)
  and an optional `study.json`; every leaf is `{"value", "unit"}` with optional `range`, `options`,
  `uncertainty`; a series is a CSV whose first column is `time`.
- `gm.check(plant, case)` runs first in `simulate` and every study function; `gm.Study` runs
  `study.json`; the verdict (`gm.evaluate.verdict`) is the one answer to feasibility.
- Python signatures are `(plant, case, ...)` and the remaining arguments are method settings only
  (`objective`, `evaluations`, `seed`, `metrics`, `samples`): the economics file owns the discount
  rate and the analysis period, the plant owns `backup`, the case owns the requirements.
- `gm.plants.capabilities()` reports the leaves that may state a `range` (`ranges`), the cost parts
  `lifetime_years` are `analysis_period`, `gm.plants.schema()` and `gm.Case.schema()` are the file
  forms, and `docs/schemas/` holds `case`, `economics`, `plant` and `study`.
- The version of a checkpoint is 0.3.0 or later; `precision`, `processes` and `compile` stay runtime
  settings and a test keeps the last two from changing a number (1e-9).

### Removed
- With no alias: `gm.case.Choices`, `Constraint`, `Assumptions`, `Finance` and the sections under
  them, `gm.evaluate.constraints`, `gm.plants.validate`, `Module.missing_parameters`, the pydantic
  methods of `gm.Case`, the `constraints` argument of `gm.study.minimize`, the `discount_rate` and
  `lifetime` arguments of the costs, `time_column` of `gm.data.from_csv`, `backup` of
  `gm.study.size`, `docs/schemas/plant_dict.*`.

### Every changed name, old and new

#### Signatures

| Old (0.2.0) | New (0.3.0) |
| --- | --- |
| `gm.evaluate.lcoh`, `lcoc`, `lcts`, `annualised_cost`, `npv` `(plant, case, results, discount_rate=None, lifetime=None, on_error="raise")` | `(plant, case, results, on_error="raise")`: `economics.discount_rate` and `economics.analysis_period` of the case are the only source |
| `gm.study.minimize(plant, case, objective, variables=None, constraints=None, evaluations=100, *, plan=None)` | `gm.study.minimize(plant, case, objective, evaluations, seed, *, plan=None)`: `variables` is the `range` and `options` leaves of the plant, `constraints` is the `requirements` of the case (nothing real needed the argument), `evaluations` and `seed` have no default; the result has no `fixed` |
| `gm.study.sample(plant, case, metrics, count, seed, *, plan=None)` | `gm.study.sample(plant, case, metrics, samples, seed, *, plan=None)` |
| `gm.study.size(plant, case, backup=None)` | `gm.study.size(plant, case)`: the policy is `params.backup` of the plant |
| `gm.data.from_csv(path, columns, unit, time_column=None)` | `gm.data.from_csv(path, columns, unit)`: the first column is named `time` |
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

#### Return shapes and files

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

### Also in 0.3.0: the study and correctness work that was unreleased before the inputs task

#### Changed
- The plant file is `kind: plant`, `format: 1`: `type` or `modules` and `connections`, `size` beside
  `params`, `params` a tree of leaf objects `{value, unit, range, options, history}`; the keys `inputs`
  and `bindings` are gone (a control is a leaf, bindings are set in memory). A file of `format: 2`
  without `kind` raises `old_format`. `Plant.ranges`, `options`, `set_range`, `set_options`, `size`,
  `check`; `Module.check` replaces `missing_parameters`; `gm.plants.validate` is removed.

#### Removed
- `gm.Plant.from_legacy`, `gemini.data.legacy`, `gemini/plants/_utils/legacy/`, `paths.legacy_project`
  and `Plant.validate`: the package reads no old project. Use
  `gm.plants.validate(plant.to_dict(structure=True))`. The old-project reader the tests still need
  is `scripts/legacy/`.

#### Changed
- `gm.Case` and the folder `gm.case` replace `gm.Problem`, `gm.Constraint` and `gm.Assumptions`:
  fixed sections in a `case.json`, SI storage, no default for anything a user must decide. Every
  call takes `(plant, case)`, plus `results` when it reads a run. The plant dict holds only the
  plant.
- One unit format: a `Quantity` or `{"value", "unit"}`; unit text is refused and `gm.units.parse`
  is removed.
- `gm.study.minimize` respects the case: a trial is feasible when no step fails and every constraint
  of the case passes; the result has `feasible` and `fixed`, a `history` item its `reason` and
  `parts["violation"]`. `gm.study.size` gives a heat pump the part of the peak the reservoir cannot
  reach. `compare` entries have `feasible` and `reasons`; `to_frame(units=None)` of `compare` and
  `sensitivity` shows display units.
- `gm.optim` is `gm.study`; `gm.types.Cost` is removed, equipment declares `capex(finance)` and
  `fixed_opex(finance)` for its kind; `examples/` holds five flat scripts.
- `gm.study.size(plant, case, backup)`: the policy of the top-up units (`"none"` or `"peak"`) has no
  default; rated units carry the largest duty the case allows; the sized plant is simulated once
  and `plant.sizing` lists what it breaks. `gm.study.sample(plant, case, metrics, count, seed)` and
  `sensitivity(plant, case, metrics)` read the `uncertainty` the case declares; the `distributions`
  and `parameters` arguments are gone. `Comparison` values are `Quantity`; `report.to_dict` and
  `str(report)` show display units. A well's `pipe_path` is four `section_*` lists. An `ESP` row
  outside its curve or over its speed-scaled maximum flow fails with `out_of_range`; a failed step makes a study trial infeasible (metrics `None`), and `sample` counts `failed`; an `InjectionPump` below its suction does not pump.
- Removed, with no alias: `gm.plants.example` (read a plant with `gm.Plant.from_json` or build the
  class), `gm.data.synthesize`, `gm.analysis.injectivity`, `calibrate_pump`, `calibrate_corrosion`,
  `erosion`. The old -> new table is in [api.md](.claude/docs/api.md).

#### Added
- `uncertainty` next to a number of the case and `gm.case.Uncertainty`; `plant.missing_parameters()`
  and an error that lists every missing value with its meaning; `gm.evaluate.failures`; `to_dict()`
  and `from_dict` of every study result; `gm.runtime.settings(processes=n)` for parallel trials, with
  one compiled graph per study.
- Variables `<role>.<parameter>` for `minimize`; `report["services"]`; `InjectionPump.nominal_flow`
  and `nominal_head`, priced as `injection_pump`; cited prices in the hackathon case.
- `gm.evaluate.capacities`, `report` and `compare`; `gm.study.size` and `sensitivity`;
  `gm.plants.capabilities`; costs on every equipment kind; the hackathon example from case to
  compared designs.

The full list, with the removed names, is the change log of [api.md](.claude/docs/api.md).

## [0.2.0] - 2026-10-31

The API for the hackathon: see the change log of [api.md](.claude/docs/api.md). Checkpoints written
before 0.2.0 do not load; `gm.plants.migrate` converts a plant file of an older version.

### Changed
- Fluids: `density` and `viscosity` replace `liquid_density` and `liquid_viscosity`; reservoirs read
  their fluid.
- Plants: an unconnected port is an error, and the automatic plant ports are gone.
- Boilers and CHP burn from `fuel_in`; `ElectricBoiler` replaces `Boiler(fuel_type="electric")`.
- Economics: `co2` sums `co2_emission` and `methane_emission`; `gas_price` and `methane_gwp` replace
  `fuel_price` and `fuel_emission_factor`; a missing assumption has the code `missing_assumption`.

### Added
- `gm.data.get` with the demand of 2027; `gm.plants.Doublet`, designed from its depth;
  `GasGrid`, `GasMakeup`, `Flare`, `ElectricBoiler`; `Fluid.gas_liquid_ratio`, `gas_composition` and
  `kind="gas"`; `gm.schedule`; `gm.evaluate.Limits` and `gm.evaluate.limits`; `capex(assumptions)` on
  equipment with sourced cost factors.

### Fixed
- Wells: the two-phase gas superficial velocity follows the gas mass flow.

## [0.1.0] - 2026-10-30

First consistent API: see the change log of [api.md](.claude/docs/api.md). The version restarts at
0.1.0 from one source, `pyproject.toml`, and `gm.API_VERSION` is removed; the integer versions
below are the history before it. Checkpoints and results files written before 0.1.0 do not load.

### Changed
- Runs: `on_error` is `"raise"` by default, on the run functions and on `gm.Engine`.
- Returns: every public return is a value, a problem or a check, built by `gemini.types.shapes`,
  with a JSON Schema each in `docs/schemas/`; a number travels with its unit and `units` maps are
  gone. `Results.energy_report` is a dict and `to_frame(table="energy")` its table.
- Errors: seven error classes and `GeminiWarning`; what the others meant is a `code`. Every public call raises by
  default and `on_error="record"` reports instead. `error.problems` carries every problem.
- Parameters and bindings: `add(kind, name=None, params=None)`, flat `set_bindings` and plant files.
- `gm.evaluate` is a namespace of `compute` and `names`; `gm.evaluate.co2` takes `(plant, results)`.

### Added
- `units`, a map from quantity to unit, on every view of `Results`, on `gm.evaluate` and on
  `gm.analysis`.

The package was rebuilt as composable modules with handwritten plants, in-memory data and one
finite engine, and then cleaned up. Old import paths are not retained.

### Added
- Run functions `gm.simulate`, `gm.replay`, `gm.live` and `gm.resume` over the public `gm.Engine`,
  with `checkpoint` and `checkpoint_every` on `simulate` and `replay`. The plant holds its traced
  graphs, so repeated calls on one plant trace it once (`gm.API_VERSION = 5`).
- The public API is frozen at `gm.API_VERSION = 1` ([api.md](.claude/docs/api.md)). New: the plant
  builder `gm.Plant` and the JSON plant spec (format 2, `gm.plants.from_spec`, `validate`,
  `spec_schema`, `migrate`, `from_template`, `example`); `describe`, `parameter_schema`,
  `validate_params`; one registry with categories and stream types; `gm.evaluate`; `gm.analysis`,
  `gm.evaluate`, `gm.evaluate`, `gm.evaluate`, `gm.testing`, `gm.data`; `gm.errors` codes and
  `to_dict`; JSON Schemas and samples in `docs/schemas/`.
- Physics and leaf modules are written with `gemini.ops`, so one source runs on floats, arrays and
  traced graphs, and `Engine.replay` evaluates each twin as one traced call with identical results.
  `gemini.compiler.graph.settings(traced=False)` selects the old tick-by-tick path.
- Composable `Module` equipment with declared parameters, ports, controls, boundaries and
  outputs, the handwritten `Doublet` plant and the example `DoubletHeatPlant`, portable plant
  JSON with dated parameters and bindings, and the `gm.plants.convert_legacy` bridge from old GEMINI projects.
- `Engine.simulate`, `Engine.replay` and `Engine.live` with callbacks, results, checkpoints and
  resume; bounded calibration through replay; quantity declarations, immutable fluids, profiles,
  costs and mass/energy audits. Eight runnable examples under `examples/`.
- Leaf packages `gemini._utils` (shared string, time, hook, mapping, context and file helpers;
  `python -m gemini._utils.collect_env`) and `gemini.errors` (every error class, also deriving
  from the matching built-in exception, as `gm.errors`).
- Development and release test profiles: `make test` runs `scripts/test_changed.py` on what
  changed and what imports it within a 300 s budget, `make test-release` runs every tier on the
  full-year data; CI runs the development profile on feature branches and the release profile
  for `main`.
- Quality gates: `tests/unit/test_code_quality.py` (comments, nesting, function length,
  framework name), flake8 `max-complexity = 10` without ignoring bare `except`, the package
  boundary test and mirror tests for every source file.
- Equipment classes in `gm.modules`, each described in `.claude/docs/equipment.md`:
  - pumps `CentrifugalPump`, `LineShaftPump`, `GasCompressor`;
  - piping `Pipe`, `Valve`, `Splitter`, `Mixer`, `PressurizationTank`;
  - treatment `Desander`, `InhibitorDosing`, `Vent`;
  - heat `HeatPump`, `AbsorptionUnit`, `AdsorptionChiller`, `CHP`, `Cooler`;
  - subsurface `ThermalDecline`, `AquiferStorage`, `BoreholeField`, `DownholeHeatExchanger`;
  - storage `ThermalStorage`, `IceStorage`; control `PIDController`;
  - power `ORC`, `Separator`, `FlashTurbine`, `GridConnection`;
  - demand `HeatConsumer`, `CoolingConsumer`.
- Composite plants in `gm.plants`: `MultiWellPlant`, `HeatingSubstation`, `CoolingSubstation`,
  `DistrictNetwork` (heating or cooling) and `ATESPlant`, with the example
  `examples/cases/district_heating_cooling.py`; `Module.trial_outlets` and
  `Module.start_states` for loops closed within one call.
- Physics modules `compression`, `refrigeration`, `steam` (IAPWS-IF97), `ground` and
  `psychrometrics`.
- `State(kind, default=...)` declarations with `_advance_states(inlets, outlets, dt)`: any module
  steps with `module.step(state, dt, inlets)`, and a composite steps every stateful descendant
  through its own `forward`, without a hand-written step method.
- Energy-balance terms beyond `electricity`, `fuel` and `heat_loss`: `heat_absorbed`,
  `heat_supplied`, `electricity_generated` and the signed stored-heat rate `heat_accumulation`
  (`ENERGY_INPUTS` and `ENERGY_OUTPUTS` in `gemini/modules/balance.py`).
- Quantities `Elevation`, `MassConcentration`, `MoneyRate`, `LinearThermalResistance`,
  `TemperatureGradient`, `Speed`, `Mass`, `SpecificEnthalpy`, `HeatCapacity`,
  `VolumetricHeatCapacity`, `ThermalDiffusivity` and `LinearPower`; units `g/m3`, `mg/l`, `ppm`,
  `currency/s`, `currency/h`, `m.K/W`, `K/m`, `K/km`, `kJ/kg`, `kWh/K`, `MJ/m3/K`, `t` and
  `m3/h/bar^0.5`; the `Fluid` kind `"steam"` and the `STEAM` constant.
- `Degasser.separation_efficiency` (default 0, which keeps the former results).
- Python 3.12, 3.13 and 3.14 support (was 3.11 only). The Test workflow runs its profile on each
  of them with the newest dependencies and on 3.11 and 3.14 with the declared lower bounds
  (`uv pip install --resolution lowest-direct`); free-threaded 3.14t and the 3.15 beta run as
  non-blocking jobs, and a manual run (`workflow_dispatch`) runs the release profile on any
  branch. CI installs with uv; `poetry install` still works.

### Changed
- `gm.API_VERSION = 2`: one classification. A module's `category` is the folder that holds it, the
  class attribute is gone, `heat/` became `exchangers/`, `heating/` and `cooling/`, the wells moved
  to `wells/` and `AquiferStorage` to `storage/`. The old to new names are in the change log of
  [api.md](.claude/docs/api.md).
- `gm.Engine(plant, ...)` owns its plant: `engine.simulate(profile)`, `engine.replay(data)`,
  `engine.live(source)`. `Results` are JSON views and `.npz` files, `to_frame()` has `path.field`
  columns, the old `summary()` is `energy_report()`, and the `parquet` extra is gone. Plant files are
  format 2; `gm.plants.migrate` converts older ones. `Doublet`, `MultiWellPlant`, `DistrictNetwork`
  and `DoubletHeatPlant` are specs, no longer classes.
- The `Module` base class is explicit: modules are built without arguments and configured with
  `update_params`, which returns the module; there is no class registry or `__init__` wrapping;
  the values of one call live in a single `_Call` context record; `fluid` is a validated
  property; plant files and checkpoints import classes only through `class_path`/`import_class`.
- Declaration listings recurse by default and key results by dotted path; `inlets()` and
  `outlets()` list the module's own ports. `health(result, measured)` receives the call's
  `ModuleResult`; `load_state_dict` takes `strict`; `has_input_value` and
  `clear_param_overrides` were added.
- Ports and controls follow one naming rule: `ProductionReservoir.production_rate` (was `m_dot`),
  `DoubletHeatPlant.secondary_in` (was `secondary`, also in `plant.json` and the data columns),
  `Doublet.return_in`/`supply_out` (were `return_stream`/`supply`) and
  `Boiler.temperature_setpoint` (was `setpoint_T`). `MissingMeasurement` became
  `gm.errors.MissingMeasurementError`, and costs are summed by
  `gemini.types.cost.total_cost(plant)` over modules that define `capex()`.
- Physics consists of plain functions with one unit table; `ConstantWater` became
  `FluidProperties`, and `Profile.constant(value, unit=, clock=)` is the only constant form.
- Runtime settings are context-local; ESP efficiency is a fraction; undefined radial
  diagnostics are reported as unavailable.
- `Blowdown` is a bleed split: `feed_in` -> `retained_out`, `blowdown_out` under the
  `blowdown_fraction` control (was a pass-through `inlet` -> `outlet` with a `modelled`
  output). `FlowCoefficient` allows zero, so a closed valve reports it.
- Dependencies are version ranges instead of exact pins: pandas >= 2.2.2, including pandas 3;
  scipy >= 1.13.0; numpy >= 2.0.0; pydantic >= 2.5.0; pytz >= 2020.1 (>= 2023.4 on Python
  3.12+); the `parquet` extra's pyarrow >= 16.0.0. On Python 3.13 and 3.14 the floors rise to
  the first releases with wheels for them (for example numpy >= 2.3.2 on 3.14). Package metadata
  is in the PEP 621 `[project]` table.
- Development tools are PEP 735 dependency groups (`test`, `lint`, `docs` and `dev` with all
  three): pytest 9.2.0, pytest-xdist 3.8, flake8 7.5.0, Flake8-pyproject 1.2.4, black 26.10.1,
  isort 9.0.2, sphinx-rtd-theme 3.1.0 and Sphinx 9.2.0 (9.1.1 on Python 3.12 and 9.0.4 on 3.11,
  the last releases for them).
  Under pandas 3, results have a microsecond time index and `str` text columns, ambiguous local
  times raise `ValueError` instead of pytz's `AmbiguousTimeError`, and CSV decimals parse
  correctly rounded, which moves replays of the example data by up to 1.7e-13 relative (see
  `.claude/docs/refactor-notes.md`).

### Removed
- `plant.simulate(profile)`: use `gm.simulate(plant, profile)`.
- `gm.modules.list/get/create`, the module catalogue and engine registry, `Sequential`,
  `fidelity`, `apply`, `column_units`, `last_result(s)`, `Module.cost`, keyword-value
  construction, `runtime.dtype` and `runtime.manual_seed`, `gemini.design`, `gemini.agentic`, the
  legacy `nodes=` options and `plant.legacy_info`, `Results.save_csv/save_parquet`,
  `Dataset.frame/describe/reopen`, `Progress`, `AlarmCollector` and `Output(optional=)`.
- `BoosterPump` (a pass-through placeholder with `modelled=False`); use `CentrifugalPump`.
- The Flask interface, application/UI workflows, container stack, platform launcher scripts and
  UI-only dependencies.

### Fixed
- Engine: resume gives the same results as an uninterrupted run; daily clocks follow local
  midnight across DST; offset timestamps load across DST switches; the event log no longer turns
  NaN into errors and always removes its hooks; live runs anchor their grid at the committed
  position, reuse the checkpointed step for single rows and keep the caller's plant and error
  policy; NumPy integer durations are seconds; text time axes are accepted.
- Modules: redefining a module class or reusing a built-in class name no longer fails; assigned
  fluids are kept; slicing a `ModuleList` no longer re-paths its children; `UNSET` keeps its
  identity under copy and pickling.
- Physics: differences convert without unit offsets; the Beggs–Brill map covers its exact
  regime boundaries; two-phase reverse flow uses mirrored friction; zero flow, zero CO2, NaN and
  out-of-range inputs raise `PhysicsRangeError` instead of crashing; `Stream(flow="10")` raises
  `UnitError`.
- Legacy: conversion reads the in-memory project; `write_csv` writes midnight timestamps;
  calibration tolerates a NaN duty row; the t/h ESP head guess is correct; `check_wiring` works
  on a copy; `barg` converts from SI correctly; an ambiguous data CSV and unknown runtime keys
  raise explicit errors; mixed timestamp spellings parse.
- Data: replay, simulation and clocks work with timestamp indexes of any resolution (s, ms, us,
  ns). Under pandas 3, which parses text times as microseconds, the loader compared them with
  nanosecond tick values, so every tick looked like a gap and replay silently skipped every twin;
  `native_step` and clock durations were also 1000 times too short.
- Clocks: daily `Clock.days`/`Clock.year` steps follow local midnight across DST under pandas 3,
  which reads a `Timedelta` frequency as a fixed 24 hours.

## [1.0.3] - 2026-10-13
### Added
- parameters and tag names of the original doublet example using CSV data
### Fixed
- fix influxdb writing data float

## [1.0.2] - 2026-10-12
### Fixed
- fix grafana reverse-proxy authentication inside iframe

## [1.0.1] - 2026-08-20
### Fixed
- add python-dotenv package to pyproject.toml
### Changed
- more info for setting up environment variables in documentation
- change naming environment variables of OLLAMA and CHROMADB


## [1.0.0] - 2026-07-19

### Added
- Initial open-source release of the GEMINI Geothermal Suite.
- Initial release of the GEMINI Geothermal Model.
- Initial release of the GEMINI Geothermal Framework.
- Initial release of the GEMINI Geothermal Application.
  - Diagram Builder Application
  - ESP Monitoring Application
  - Productivity Application
  - Injectivity Application
  - Well Schematic Application
  - Well Integrity Monitoring Application
  - Time-series Visualization Application
  - Report Generation Application
  - Chatbot Application
- Initial release of the GEMINI Geothermal Interface.
