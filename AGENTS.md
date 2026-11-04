# GEMINI Python package

GEMINI is a composable geothermal digital-twin package. Preserve captured numerical behaviour.

## Read both: `.claude/` for agents, `docs/` for people

`.claude/` is written for agents: start with [.claude/README.md](.claude/README.md) (its
`docs/` reference, `notes/` current work, `archive/` history). `docs/` is written for people.
Read both, and the project-wide context in the project root `geomind-spe-hackathon-2026/`: its
`AGENTS.md`, the shared memory `.claude/memory/MEMORY.md` and `docs/`.

## Start here

Read [docs/rules.md](docs/rules.md) first: it holds every rule of the project. This page is orientation.

Test with the development profile (`make test`); see
[Testing: Test profiles](.claude/docs/testing.md#test-profiles).

A leaf module computes and a plant connects; no class does both
([modules](.claude/docs/modules.md), [plants](.claude/docs/plants.md)). A leaf has physics calls and
one pure method, `forward`, and a pure `update` when it has states; to write one, follow
[Writing a module](.claude/docs/writing-a-module.md) (a pump and a controller, each alone and
inside a plant). Every composite is a `Plant`: it declares children, ports and connections in
`__init__` and never writes `forward`. The engine closes loops and solves constraints.

Physics lives in `gemini/physics/`, and in a `_physics.py` beside a category only when it needs
streams (`wells/_physics.py`): a module declares and calls physics functions. `gemini/modules/` holds `Module`, the declarations, `ModuleList`,
`ModuleDict` and `gm.modules.check`; `gemini/plants/` holds `Plant` and the plant classes. Machinery
goes in an `_utils/` folder, code of one category in a private file of its folder
([where a file goes](.claude/docs/conventions.md#module-rules)). Public names are flat,
`gm.<folder>.<Name>`, exported by the folder's `__init__`; inner files are private. The run folders
(`modules`, `plants`, `case`, `physics`, `ops`, `runtime`, `engine`, `streams`, `units`, `errors`,
`_utils`) import none of `compiler`, `study`, `evaluate`, `analysis`
([dependencies](.claude/docs/conventions.md#dependencies)); the rules for folders and the table of what each
folder takes, gives and may call are in [structure](.claude/docs/structure.md).

Learn the package from [examples/README.md](examples/README.md): six flat scripts, `quickstart.py`
first, then `hackathon.py`. gemini holds no data file: plants are Python classes, and JSON is only the
plant dict agents use (`gm.Plant.from_dict`, `plant.to_dict`, `gm.plants.schema`). Data lives in
`examples/<name>/` (a sample project: its case, plants and data, so a folder a user can copy) and in
`tests/fixtures/` (what the tests read); none of it is installed, and the package holds none
([data](.claude/docs/data.md#where-data-lives)).

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

Everything in the plant's energy and mass flow is a module, everything that crosses between modules
goes through a port, and a plant total is read from the ports of the modules at the plant's edge
([energy flow](.claude/docs/modules.md#energy-flow)). Check a run with `gm.evaluate.plant_balance(plant, case, results)`.

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
- [Writing a module](.claude/docs/writing-a-module.md): the pure contract (`forward`, `update`), a stateless pump and a stateful controller, each alone and inside a plant; its snippets run in `test_docs`.
- [Native engine](.claude/docs/native-engine.md): the computation-graph design and its status.
- [Physics](.claude/docs/physics.md): every physics function by file, SI correlations and numerical
  constraints.
- [Refactor notes](.claude/docs/refactor-notes.md): retained numbers and known limitations.
- [Runtime](.claude/docs/runtime.md): context-local process settings.
- [Testing](.claude/docs/testing.md): tiers, test profiles, datasets, budgets, fixtures and CI.
- [Structure](.claude/docs/structure.md): the rules R1-R7 for folders, what each folder takes, gives and may call, and the words plan, bindings and graph.
- [Types](.claude/docs/types.md): streams, fluids, declarations, profiles and balances.
- [Utilities](.claude/docs/utils.md): the `gemini._utils` helpers and how to add one.

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
├── runtime.py        # context-local backend, precision, display units
├── modules/          # module.py, declarations.py, container.py, call.py, check.py, results.py, bindings.py, _utils/; one folder per category (a `_physics.py` only where code needs streams)
├── plants/           # plant.py (Plant) and the plant classes, one file each; _utils/ holds the plant tools
├── case/             # Case and its sections (time, site, demand, utilities, economics, requirements), profile.py, dataset.py (Dataset: measured series), demand_frame.py (from_csv, from_values, profile_schema); _utils/ (node: the one reader of a section, schema, access, kinds)
├── engine/           # one run: Engine, simulate/replay/live/resume, check, Results, apply (the case on a plant copy), schedule/ (schedule, dispatch, sources, limits, fleet), bindings, loader, columns, runner, chunks, eager, executor, checkpoint, callbacks
├── compiler/         # compile.py, executor.py, ir.py (Graph), trace/, passes/, cache.py, interpret/ (per backend), run.py; gm.compiler.compile; optional, registers itself
├── study/            # size, minimize, sample, sensitivity, calibrate, Study; _utils/ (trial, variables, execute, target)
├── evaluate/         # one file per job: costs, emissions, balances, verdict, summary, report; each public function is gm.evaluate.<name>; _utils/
└── analysis/         # one module at fixed conditions: nodal, fits (and the pump curve), corrosion forecast
docs/                 # for people: guide.md, rules.md, CHANGELOG.md, the Sphinx sources
docs/schemas/         # generated JSON Schemas and samples of the exchanged documents
examples/             # six flat scripts (quickstart, hackathon, costs, uncertainty, plant, evolve) and one folder per sample project (case, plants, data): hackathon_2026/, hackathon_superstructure/, shallow_district/
scripts/              # test_changed.py, write_schemas.py, legacy/ (old-project reader for the tests)
docker/               # sandbox.Dockerfile, the image of a module sandbox (make sandbox-image)
tests/                # unit mirror, integration, e2e (expected/ holds example outputs), fixtures (with the data the tests read: plants/, doublet_heat/, legacy_project/)
```

Details are in [conventions.md](.claude/docs/conventions.md) and [modules.md](.claude/docs/modules.md).
