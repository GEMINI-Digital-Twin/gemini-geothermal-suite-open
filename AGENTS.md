# GEMINI Python package

GEMINI is a composable geothermal digital-twin package. Preserve captured numerical behaviour.

## Start here

Test with the development profile (`make test`); see
[Testing: Test profiles](.claude/docs/testing.md#test-profiles).

A leaf module computes and a plant connects; no class does both
([modules](.claude/docs/modules.md), [plants](.claude/docs/plants.md)). A leaf has physics calls and
one method, `forward`. Every composite is a `Plant`: it declares children, ports and connections in
`__init__` and never writes `forward`. The engine closes loops and solves constraints.

Physics lives in `gemini/physics/` or `gemini/modules/<category>/_physics.py`: a module declares and
calls physics functions. `gemini/modules/` holds `Module`, the declarations, `ModuleList`,
`ModuleDict` and `gm.modules.check`; `gemini/plants/` holds `Plant` and the plant classes. Machinery
goes in an `_utils/` folder, code of one category in a private file of its folder
([where a file goes](.claude/docs/conventions.md#module-rules)). Public names are flat,
`gm.<folder>.<Name>`, exported by the folder's `__init__`; inner files are private. The run folders
(`modules`, `plants`, `case`, `physics`, `ops`, `runtime`, `engine`, `streams`, `units`, `errors`,
`_utils`) import none of `compiler`, `study`, `evaluate`, `analysis`
([dependencies](.claude/docs/conventions.md#dependencies)); the rules for folders and the table of what each
folder takes, gives and may call are in [structure](.claude/docs/structure.md).

**Read/write naming.** Every reader is `from_<format>` and every writer `to_<format>`: `from_csv`,
`from_json`, `from_dict`, `from_values`, `from_bytes`, ... and `to_csv`, `to_json`, `to_dict`,
`to_bytes`, .... A reader is a classmethod on the class it returns (`gm.Case.from_json(path)`); a
writer is a method of the object (`case.to_json(path)`). Only a reader that returns no gemini
class (a demand frame) is a plain function in its folder (`gm.case.from_csv`). No `read_*`,
`write_*`, `load_*`, `save_*`, `parse_*` or `dump_*` names; `tests/unit/test_code_quality.py` rejects
those prefixes ([conventions](.claude/docs/conventions.md#public-names-and-readwrite-naming)).

Learn the package from [examples/README.md](examples/README.md): five flat scripts, `quickstart.py`
first, then `hackathon.py`. gemini holds no data file: plants are Python classes, and JSON is only the
plant dict agents use (`gm.Plant.from_dict`, `plant.to_dict`, `gm.plants.schema`). Data lives in
`examples/<name>/` (a sample project: its case, plants and data, so a folder a user can copy) and in
`tests/fixtures/` (what the tests read); none of it is installed, and the package holds none
([data](.claude/docs/data.md#where-data-lives)).

Before adding or moving an input, apply the placement test of [inputs](.claude/docs/inputs.md#2-the-placement-test):
one owner, one file, and the reason is written there.

One `gm.Case` carries what a plant is asked to do, for every call: the sections `time`,
`site`, `demand`, `utilities`, `economics` and `requirements`, strict and typed, read from a
`case.json` with `gm.Case.from_json` ([case](.claude/docs/data.md#the-case)). A plant dict holds only the
plant. Run a plant with `gm.simulate(plant, case)`, `gm.replay`, `gm.live` and `gm.resume`; keep
`gm.Engine` for complex tasks ([functions or engine](.claude/docs/engine.md#functions-or-engine)).
`gm.schedule(plant, case)` plans the run input of a design from the demand of the case, at any
constant step: sources load from the cheapest to the dearest, limits come from the
requirements, the merit order and the outages from the plant's `control`, and the role of each unit is read from the wiring
([schedule](.claude/docs/engine.md#schedule)). The `gm.evaluate` functions take
`(plant, case, results)`: `totals`, `requirements`, `verdict`, the costs, `report` and `compare`. `gm.study`
sizes (`size`), searches (`minimize`), samples and ranks the influence of a value (`sensitivity`);
`gm.Study` runs them from a `study.json`; `gm.check(plant, case)` lists what is missing first.

gemini is a general package and knows no sample: `examples/<name>/` holds a sample project, a
`case.json`, a demand CSV and the plant dicts, and only `examples/` and `tests/` read them
([conventions](.claude/docs/conventions.md#general-package)). A whole run is:

```python
case = gm.Case.from_json("examples/shallow_district/case.json")
plant = gm.Plant.from_json("examples/shallow_district/plants/HeatingHeatPumpCoolingPlant.json")
results = gm.simulate(plant, case)
print(gm.evaluate.report(plant, case, results)["heat_delivered"].to("MWh").value)
```

**Standing rules.** They apply to every change, in code, tests and docs.

- *One unit format.* A value with a unit is a `gm.units.Quantity` with a unit of the
  `gm.units.Unit` enum, or its dict `{"value": 150, "unit": "m3/h"}`; a string such as
  `"150 m3/h"` is never accepted, and nothing in the package parses unit text. A dimensionless value
  is a number. A bare number with a dimension raises `invalid_value` at every public door
  (`set_params`, `Plant.set_inputs`, `gm.Stream`, `Stream.with_`, attribute assignment outside a call, `gm.Fluid`, `gm.call`); `gemini` itself uses the
  private SI path (`_set_si_params`, `Stream._si`, `Fluid._si`, `Stream._with_si`,
  `Module._assign_si`) ([units](.claude/docs/conventions.md#units)).
- *No defaults.* Nothing a user must decide has a default value in gemini: not a price, a
  temperature, a limit, a factor or an efficiency. Such a field is required, or absent (`None`),
  and a call that needs an absent value raises `missing_value` (`missing_assumption` below
  `economics`) naming its path. `gm.case` has no default at all, and a module or plant declaration keeps a default only if it is
  in `DECLARED_DEFAULTS` (a sourced constant or the zero of an accumulator);
  `tests/unit/test_code_quality.py` checks this
  ([no defaults](.claude/docs/conventions.md#no-defaults)).
- *The input is a case, never a problem.* The word `problem` is only the return shape of an error;
  `tests/unit/test_code_quality.py` rejects it as a name in `gemini/`.
- *Update the code, never wrap it.* When a refactor changes a name or a shape, every caller is
  changed in the same task, and no wrapper, alias or shim is written
  ([one implementation](.claude/docs/conventions.md#one-implementation-per-concept)).
- `.claude/` holds no separate rules file: this page is the coding rules for Claude.

Everything in the plant's energy and mass flow is a module, everything that crosses between modules
goes through a port, and a plant total is read from the ports of the modules at the plant's edge
([energy flow](.claude/docs/modules.md#energy-flow)). Check a run with `gm.evaluate.plant_balance(plant, case, results)`.

Every port of a module is connected or named as a plant port; there are no automatic plant ports
([plants](.claude/docs/plants.md#the-builder)). What a design holds beside its parameters, such as a
setpoint, is set with `plant.set_inputs` and stored in the plant file as a leaf of `params`. A plant may derive its children's values by
overriding `_set_si_params`
([modules](.claude/docs/modules.md#a-plant-that-sets-its-childrens-values)).

Every public return uses one of three shapes, value, problem (the shape of an error) or check, built by
`gemini/units/shapes.py` ([return shapes](.claude/docs/api.md#return-shapes)). Every public call
raises by default; `on_error="record"` reports instead ([errors](.claude/docs/errors.md)).

Read every file in `.claude/docs/` before changing the repository:

- [Public API](.claude/docs/api.md): every frozen public name, its return shape and status; start
  here to use the package.
- [Plants](.claude/docs/plants.md): plant classes, the builder, the plant dict, loops, constraints,
  outputs, dates and bindings.
- [Conventions](.claude/docs/conventions.md): dependencies, naming, comments and code quality.
- [Data](.claude/docs/data.md): read/write naming, in-memory datasets, sampling, gaps, `case.json`, the unit format
  and where data lives.
- [Engine](.claude/docs/engine.md): clocks, runs, callbacks, results, checkpoints and live.
- [Economics](.claude/docs/economics.md): `gm.evaluate` costs, totals, KPIs, requirements, the verdict and checks, `gm.study`, `gm.Study` and well analysis.
- [Equipment](.claude/docs/equipment.md): every shipped module, its model and energy audit.
- [Errors](.claude/docs/errors.md): the rule for raising, the seven `gm.errors` error classes and `GeminiWarning`, the codes.
- [Inputs](.claude/docs/inputs.md): the principles, the placement test and the file formats; where every input lives and why.
- [Glossary](.claude/docs/glossary.md): one name per concept for parameters, outputs and ports.
- [Legacy](.claude/docs/legacy.md): the old-format reader kept in `scripts/legacy/` for the tests.
- [Modules](.claude/docs/modules.md): declarations, listings, calls, outputs, hooks and state.
- [Native engine](.claude/docs/native-engine.md): the computation-graph design and its status.
- [Physics](.claude/docs/physics.md): every physics function by file, SI correlations and numerical
  constraints.
- [Refactor notes](.claude/docs/refactor-notes.md): retained numbers and known limitations.
- [Runtime](.claude/docs/runtime.md): context-local process settings.
- [Testing](.claude/docs/testing.md): tiers, test profiles, datasets, budgets, fixtures and CI.
- [Structure](.claude/docs/structure.md): the rules R1-R7 for folders, what each folder takes, gives and may call, and the words plan, bindings and graph.
- [Types](.claude/docs/types.md): streams, fluids, declarations, profiles and balances.
- [Utilities](.claude/docs/utils.md): the `gemini._utils` helpers and how to add one.

When a commit changes behaviour, structure or conventions, update the relevant document in the
same commit. The public API is frozen: a breaking change to a public name or return field raises the minor
number of `gm.__version__` ([freeze rule](.claude/docs/conventions.md#public-api-freeze)).

## Branching

- `main` is the stable line (competition delivery, releases). Change it only on the user's
  request.
- `dev` is the development line: commit there and push `origin dev`.
- `feature/<name>`, `fix/<name>` and `docs/<name>` hold one task each, with a short lowercase name
  joined by hyphens (`feature/study-speed`, `fix/budget-tests`). Branch from `dev`, merge back into
  `dev`, then delete the branch locally and on `origin`.
- Temporary worker branches and worktrees of a coordinator session stay local, are never pushed,
  and are removed at the end of the task.
- Never name a branch `dev/...`: git cannot hold both `dev` and `dev/<name>`.
- Open a pull request only when asked.

## Layout

```text
gemini/
├── __init__.py       # curated import gemini as gm API: gm.__all__ is pinned
├── _utils/           # helpers shared by two or more folders, and registry.py; leaf, imports nothing else from gemini (but errors)
├── errors/           # the gm.errors classes and codes; leaf package that imports nothing else from gemini
├── ops/              # math API and dispatcher, backend.py (registry, select), kernels/ (python, numpy, scalars, solvers)
├── physics/          # shared formulas: SI correlations; gm.physics.<topic> (the doublet design is in plants/_utils, the dispatch policy in engine/schedule)
├── units/            # unit conversions, Quantity, the quantity aliases (quantities.py), the unit rule (bare.py), the return shapes (shapes.py), the shared input formats (inputs.py), the display table (display.py)
├── streams/          # Stream, Fluid, Ports, the stream kinds
├── runtime.py        # context-local backend, precision, display units and default fluid
├── modules/          # module.py, declarations.py, container.py, call.py, check.py, results.py, bindings.py, _utils/; one folder per category with its _physics.py
├── plants/           # plant.py (Plant) and the plant classes, one file each; _utils/ holds the plant tools
├── case/             # Case and its sections (time, site, demand, utilities, economics, requirements), profile.py, dataset.py (Dataset: measured series), demand_frame.py (from_csv, from_values, profile_schema); _utils/ (node: the one reader of a section, schema, access, kinds)
├── engine/           # one run: Engine, simulate/replay/live/resume, check, Results, apply (the case on a plant copy), schedule/ (schedule, dispatch, sources, limits, fleet), bindings, loader, columns, runner, chunks, eager, executor, checkpoint, callbacks
├── compiler/         # compile.py, executor.py, ir.py (Graph), trace/, passes/, cache.py, interpret/ (per backend), run.py; gm.compiler.compile; optional, registers itself
├── study/            # size, minimize, sample, sensitivity, calibrate, Study; _utils/ (trial, variables, execute, target)
├── evaluate/         # one file per job: costs, emissions, balances, verdict, summary, report; each public function is gm.evaluate.<name>; _utils/
└── analysis/         # one module at fixed conditions: nodal, fits (and the pump curve), corrosion forecast
docs/schemas/         # generated JSON Schemas and samples of the exchanged documents
examples/             # five flat scripts (quickstart, hackathon, costs, uncertainty, plant) and one folder per sample project (case, plants, data): hackathon_2026/, shallow_district/
scripts/              # test_changed.py, write_schemas.py, legacy/ (old-project reader for the tests)
docker/               # sandbox.Dockerfile, the image of a module sandbox (make sandbox-image)
tests/                # unit mirror, integration, e2e (expected/ holds example outputs), fixtures (with the data the tests read: plants/, doublet_heat/, legacy_project/)
```

Modules declare parameters and ports in `__init__`; `forward(self, inputs, inlets, state)` is pure:
it receives the controls and boundaries in `inputs`, one immutable `Ports` mapping
(`gemini.streams.Ports`) in `inlets` and the state, reads parameters on `self`, writes nothing and
returns `(outputs, outlets)`; a stateful module also has a pure `update(self, inputs, inlets,
outlets, state, dt)` returning the next state. The combinations of a plant are returned by
`Plant.forward`, written once. Pre-hooks receive `(module, inputs, inlets, state)` and forward hooks
receive `(module, inputs, inlets, state, outputs, outlets)`. Plants ([plants.md](.claude/docs/plants.md)) own persistence, bindings,
and dated design. `gemini.engine` holds the run objects and reads files only for a `Results`. No engine loop sleeps or schedules itself.
Keep the public
API small and examples outside the package. Details are in
[conventions.md](.claude/docs/conventions.md) and [modules.md](.claude/docs/modules.md).
