# Task: Freeze and document gemini's public interfaces (replaces step 3b)

## 0. Context and rules

- The goal: **every gemini name that the frontend, the backend and the agent package need is defined, documented and pinned now**, so that they can build against it without waiting for gemini's later implementation work. The agent package is `geomind` (`import geomind as gd`). Parts whose real work comes later still get their **final signature now** and raise `gm.errors.NotImplementedYet`, plus sample files. Once this step lands, a change to any of these names is a versioned change (section 9).
- The full list, agreed with me and reviewed by the backend and geomind sessions, is Appendix A at the end of this prompt (draft 3 of `gemini-public-interfaces.md`). **It is the specification.** Sections A to L in it map to the work below. Field names in the cross-repo contract are in `contracts.md`; the parts gemini touches are Appendix B at the end of this prompt (the full file is `docs/contracts.md` in the workspace). Where the two differ, follow the interface list and report the difference.
- This prompt **replaces** `native-engine-step3b-public-api.md`: do not run that one. Step 4 (layout and cleanup) runs after this step and must keep every public name unchanged while it moves files. So **do not move folders here** (`gemini/core` is removed in step 4), and every public name must be reachable from `gm.*` without internal paths.
- Start from the current local `refactor`, where step 3 is finished. Read `AGENTS.md`, every file in `.claude/docs/` (especially `native-engine.md` and `conventions.md`) and the step 3 notes in `.tmp/native-engine/` first, and follow them.
- **Standing rules:** no concept has two implementations; behaviour is identical on every backend (the parity suite stays green); physics and numbers do not change (every example and golden is bit-identical, otherwise within the documented `1e-12`).
- Work directly on branch `refactor` (no new branch, no PR) and commit there. **Do not push** until I have reviewed the commits.
- **Pre-check:** `git status` is clean on `refactor`, and no other Claude session or process is working **inside `gemini/`**. Sessions in other folders (`geomind/`, `backend/`, `frontend/`) do not block you. If their load makes a 1 s budget test fail, rerun that test alone before treating it as a failure, and say which tests you retimed.
- My workspace is `/Users/sahand/Desktop/crust-team`. Change **only** `gemini/`. You may read `geomind/`, `backend/`, `frontend/` and `docs/` to see how they will call these names, but never change them, including `docs/contracts.md` (section 10 says what to report instead). Do not edit or commit `runs/`.
- Temporary files go to `.tmp/interfaces/` (git-ignored), never to `docs/`.
- **Work multi-agent and in parallel** (section 1). Subagents run on a lighter model (sonnet for code, haiku for read-only searches), not the main model.
- **Tests:** development profile only (`make test` / `scripts/test_changed.py`, which always includes `test_code_quality.py`): the tests of what changed and of everything that imports it, in parallel, under 300 s. Never run the whole suite or the slow dataset locally. New tests go in the right tier, use session fixtures and the short-window dataset, stay xdist-safe, and no fast-tier test runs over about 1 s. Never delete or shrink existing tests, datasets or goldens.
- **Quality bar** (as in `.claude/docs/conventions.md`): nesting at most 3, functions about 40 lines at most, flake8 `max-complexity = 10`, guard clauses, no dead or speculative code, no golfed code, full-word names, explicit `gm.errors` classes, and a failing test before each bug fix. **No comments inside code**: only the fixed section headers and tool directives; explanations go in docstrings. No "magic" structures, and keep the public API minimal: only the names in the list. When unsure, follow PyTorch source patterns as a design reference only, and never name torch in the repo. black, isort and flake8 clean.
- **Docs:** every commit that changes behaviour updates the matching file in `.claude/docs/` in the same commit. Section 8 adds the API pages.
- If something else is needed (a missing step, a dependency, a risk), say so in the report instead of staying silent.

## 1. Parallel plan

You are the coordinator. Create every worktree by hand from `refactor` (`git worktree add -b <tmp> <path> refactor`). Temporary branches are never pushed, and they are deleted after merging. Merge one agent at a time and run the tests after each merge. Two agents never edit the same file in the same wave. Give each agent this whole prompt (with both appendices) and its own section numbers.

| Wave | Who | Sections |
|---|---|---|
| 0 | coordinator alone | 2 (foundations everyone uses) |
| 1 | three agents in parallel | A: 3 (modules); B: 4 (plant builder and spec); C: 5 (units, running, results) |
| 2 | two agents in parallel | D: 6 (example plants as specs, templates, profiles); E: 7 (signatures for analysis, economics, KPIs, checks, new modules) |
| 3 | coordinator alone | 8 and 9 (schemas, samples, contract tests, docs, freeze) |

## 2. Foundations (interface list A, K)

- `gm.API_VERSION = 1` and `gm.__version__`.
- `gm.errors`: base `GeminiError` with `to_dict() -> {class, message, path, code, suggestions}`, plus `ValidationError`, `UnknownNameError` (close-match "did you mean"), `UnitError`, `PlantFormatError` (old format, failed migration), `SolverError`, `Cancelled` and `NotImplementedYet`. `code` comes from one fixed, documented set (a frozen tuple in `gm.errors`, listed in the docs), because the backend puts it into `422` details. Reuse the existing classes where they fit: one class per concept.
- **One registry implementation** for modules and plants: every module and every plant has a stable registry name and a `category`. The categories and stream types are the fixed lists in interface list section B. Fix any module whose category or port stream does not fit, and report each one.
- **JSON-safe returns:** one internal helper turns numpy scalars and arrays into plain Python and NaN into `null`. Every public function that returns data uses it. A test calls every such function on the example plant and checks `json.dumps(result, allow_nan=False)`.

## 3. Modules (agent A; interface list B, C)

- `gm.modules.names(category=None)`, `get(name)`, `categories()`; `gm.streams.names()`.
- `Module.describe()` on a class or an instance returns exactly the shape in section C of the list: parameters, controls, boundaries, measured and state with type, unit, quantity, default, minimum, maximum, enum, description and section; inlets and outlets with stream and fields; outputs with unit, `kind` (one of the 9 additive types or `null`) and `soft_sensor`; for composites, children and connections. On an instance it also carries the current values (`values`), which geomind's `read_plant` needs.
- `Module.parameter_schema()`: plain JSON Schema (draft 2020-12), each property with `unit`, usable with ajv in the browser.
- `gm.modules.get(name).validate_params(params) -> [{path, message, code}]`: no raise, the same item shape as `gm.plants.validate`. Unit strings are accepted.
- Tests: a leaf, a composite, and every registered module serialised with `json.dumps`; the schema of every module is valid JSON Schema; `validate_params` catches a wrong unit, an out-of-bounds value and an unknown name with a suggestion.

## 4. Plant builder and spec (agent B; interface list D0, D, E)

This is the main new feature: plants built like Keras builds models over TensorFlow, so an agent can build and simulate a plant from JSON without writing Python. There are three levels and **one representation**.

1. **Builder:** `p = gm.Plant(name)`; `p.add(type, name=None, **params)` (registry name or class, unit strings accepted, returns a handle); `p.connect(a, b, ...)` (handles or `"path.port"`; ports are matched automatically when exactly one free port of the same stream type fits, otherwise a `ValidationError` lists the candidates); `p.summary()` (a text table like a Keras model summary: module, type, category, connections, parameter count); `p.validate()`; `p.simulate(profile)`.
2. **Spec:** `p.to_spec()`, `gm.plants.from_spec(spec)`, `gm.plants.validate(spec) -> [{path, message, code, suggestions}]` (every problem at once, paths into the spec such as `connections[1].target`, no raise) and `gm.plants.spec_schema()` (JSON Schema of the spec; geomind uses it as the input schema of its `build_plant` tool). The spec is the format shown in section D0 of the list (`format: 2`, `name`, `modules`, `connections`, `bindings`, `param_history`). **It is the stored plant file**: `gm.plants.from_dict` and `plant.to_dict()` are the same function as `from_spec` and `to_spec`. Keep one implementation and one name pair if that is cleaner, and say which you chose.
3. **Subclassing** `Module` with `forward` stays for leaf modules and special cases only.

Rules:

- **A built plant is a normal composite `Module`.** Its forward runs the modules in topological order of the connections and is traced into the graph like any other module, so `describe()`, the automatic output sums, `simulate`, `replay` and `live` all work unchanged, on every backend (add it to the parity suite).
- **Only `connect` wires modules**: no call syntax.
- An inlet has exactly one source, and an outlet feeds exactly one inlet. Splitting and mixing are modules (`Splitter`, `Mixer`): add them as leaf modules if they do not exist.
- **Loops** are closed by an explicit connection with `"kind": "state"`, which reads the value of the previous step. A cycle without a state connection is a validation error. Use the existing path for stateful modules (until scan exists). If a state connection cannot run correctly without scan, keep it in the spec, the schema and validation, make running such a plant raise `NotImplementedYet` with a clear message, and report it.
- A spec module's `type` may name a registered plant (a nested spec), so templates can contain sub-plants.
- **Round trip:** `to_spec(from_spec(x)) == x` for every current-format spec, JSON-safe, no float drift, keys in a stable order. The backend digests sorted-key JSON and refuses identical saves.
- **Parameters by date and bindings** (list section E): `plant.set_params(path, params, valid_from=None)`, `plant.params_at(path, time=None)`, `plant.param_history(path)`, `plant.bindable(path) -> {controls, boundaries, inlets: {port: [field]}, measured, state}`, `plant.set_bindings(path, bindings)` with binding `{column, unit}` and units checked against the declaration. `plant.get_module(path)` and `plant.named_modules()` keep or take these names.
- **Migration:** `gm.plants.migrate(old) -> spec` converts every older stored format (class paths such as `gemini.core...`, the class-based plant dicts) to format 2. A one-off script in `scripts/` runs it over files given on the command line; run it on every stored plant file inside `gemini/` in the same commit. Loading an old file without migrating raises `PlantFormatError` naming `gm.plants.migrate`.
- Tests: build the example doublet three ways (builder, spec, `from_dict` of a migrated old file) with bit-identical results; validation messages for each rule; the round trip; a nested spec.

## 5. Units, running, results (agent C; interface list F, G)

- **Units:** `gm.units.names(quantity=None)`, `parse(text) -> (value, unit)`, `convert(value, from_unit, to_unit)`, `fits(unit, quantity) -> bool` (backend checks binding units and CSV headers `name [unit]` with it). Accept at least `km`, `mm`, `in`, `kPa`, `MPa`, `rpm`, `degC`, `m3/h`, `MW`, `kW`, and `bar(g)` if there is a gauge-pressure convention. One unit implementation, used by `validate` everywhere. Every output states its SI unit.
- **Run input:** freeze one profile and replay input format: a pandas DataFrame or a `gm.Dataset` with a timezone-aware UTC index, columns named by binding `column`, units from the binding. Document and test what happens with a missing column (a clear `ValidationError` listing them) and NaN rows (row error code, the run continues).
- **Engine:** `gm.Engine(plant, backend="numpy")` with `simulate(profile)`, `replay(data, start=None, end=None, state=None)` returning results and the end state (so the backend can run soft sensors incrementally), and `live(source)`. Public callbacks: progress `(done, total)`, and a callback may raise `gm.errors.Cancelled` to stop cleanly (partial results stay readable). Document that plants and engines are not shared across threads: each worker loads its own.
- **One-module call:** `gm.evaluate(module, parameters, inlets, controls) -> {outlets, outputs, errors}`, where `module` is a registry name or a class. Plain JSON with units.
- **Results:** `names()`, `get(path, field, start=None, end=None) -> {time, values, unit}` (plain JSON), `summary(path=None, start=None, end=None)` (min, max, mean and unit per field), `errors()` (row codes with meaning), `to_frame()`, `to_dict()`, `save(path)` / `gm.Results.load(path)` (`.npz`, no new dependency), and `to_bytes()` / `gm.Results.from_bytes(data)` (geomind stores results without a file path). Calculated-tag column names are `path.field`.
- **Determinism:** the same input gives the same numbers, on every backend; add a test.

## 6. Example plants as specs, templates, profiles (agent D; interface list D0, D, J)

- **Rewrite every existing plant class** (`Doublet`, `DoubletHeatPlant`, `HeatingSubstation`, `CoolingSubstation`, `DistrictNetwork`, `AtesPlant` and any other) **as a spec file** inside the package, registered by name. No handwritten plant classes remain. If a plant's forward does more than wiring (control logic, splits, mixing), move that logic into a leaf module, so the plant is wiring only, and report each case. Every example, golden and legacy-import result stays bit-identical.
- `gm.plants.names()`, `get(name)` (returns the built plant), `example(name)` (real parameter values; for the doublet the `doublet_heat` values) and `templates() -> [{name, title, description, purpose}]`, where purpose is `heating`, `cooling` or `both`; `from_template(name, parameters)`.
- **The Challenge 2 template:** one integrated heating-and-cooling plant spec (doublet, heat exchanger, heat pump, absorption chiller, compression or adsorption chiller, hot and cold storage, peak boiler, network, heating and cooling consumers), sizes as parameters, and every optional unit switched on and off by an `enabled` parameter. Add a few presets as specs (for example heating only, heating plus absorption cooling, with storage). Use only modules that exist. For each missing piece, write a short spec of what it needs into the report and leave the unit out; do not write new physics in this step.
- **Demand profiles:** `gm.profiles.names()`, `gm.profiles.get(name)` (in the run-input format of section 5) and the profile format as a JSON schema. Look for the hackathon task inputs (heating and cooling demand) in the workspace. If you find them, ship them as profiles with their source in the docs. If you do not, never invent numbers silently: ship the format, the names and `NotImplementedYet`, and ask me in the report where the data is.
- `gm.plants.convert_legacy(folder) -> spec`, with the files it expects documented. If it still needs internals, give the signature, raise `NotImplementedYet` and report.

## 7. Signatures for later work (agent E; interface list H, I, J, L)

Each name gets its final signature, a docstring with inputs, outputs and units, and a return shape that is plain JSON. **Implement it now when existing code already does the work**; otherwise raise `NotImplementedYet`. Report which ones are real.

- `gm.analysis`: `nodal(plant, well, conditions)`, `injectivity(data, well)`, `pump_curve(plant, pump, measured=None)`, `calibrate_pump(plant, pump, measured)`, `calibrate_corrosion(logs)`, `corrosion_forecast(model, until)`, `erosion(plant, well)`.
- `gm.economics`: `Assumptions` (one object with sourced defaults: discount rate, lifetime, prices, emission factors; each default documented with its source), `capex(plant, assumptions=None)`, `opex(plant, results, assumptions=None)`, `lcoh(...)`, `lcoc(...)`, `co2(results, assumptions=None)`, `npv(...)`, `payback(...)`. Every return carries its unit. Reuse `Cost` and `total_cost`: one cost implementation.
- `gm.kpi(plant, results)` and `gm.kpi.names()`: fixed names, at least `heating_coverage`, `cooling_coverage`, `cop`, `peak_heat`, `peak_cold`. The problem state's `metric` field uses these names.
- `gm.checks`: `energy_balance(results)`, `mass_balance(results)` over time series, bounds checks, and `run_all(plant, results)`. Each check returns `{name, passed, value, tolerance}`. Reuse the existing balance code.
- New modules written by the agent (Challenge 1): `gm.testing.check_module(cls) -> report` (gemini's module rules: declarations, units, `describe()` works, one call runs; returns a report and never raises), `gm.modules.register(cls)` and `gm.modules.load_file(path)`, so a new module can join a plant inside geomind's sandbox.
- Signatures only, `NotImplementedYet`: `gm.optim.minimize(...)` and uncertainty sampling (pick the name, document it).

## 8. Schemas, samples, contract tests, docs (coordinator)

- `gemini/schemas/`: JSON schemas of the exchanged documents: the module description, the plant spec, the results summary, the error dict, the profile. Next to each one, one sample file generated from the example plant (with a test that the samples are up to date). Other repos build against these samples before the real work lands.
- `tests/unit/test_public_api.py` pins every public name and its signature (parameter names), including the `NotImplementedYet` ones. `gm.utils` stays out of `__all__`.
- Contract tests: the JSON-safety test (section 2), schema validation of every sample, determinism, and the three-ways doublet test.
- **Docs:** `.claude/docs/api.md` is one page with every public name, its signature, return shape, units and status (`real` or `NotImplementedYet`), grouped as in the interface list. `.claude/docs/plants.md` explains the three levels with the doublet example in both Python and JSON. Update `AGENTS.md` "Start here". Keep the design doc `native-engine.md` in step with the plant builder.

## 9. Freeze rule

Write this into `.claude/docs/api.md` and `conventions.md`: after this step, changing, renaming or removing any public name or return field raises `gm.API_VERSION` in the same commit, with a line in the change log section of `api.md`. Adding a new optional field does not. The public-API test enforces it: it compares against a stored snapshot that may only change together with `API_VERSION`.

## 10. Report

- Commits, wave by wave.
- Every public name with its status (`real` or `NotImplementedYet`).
- How the plant builder works, which plants were rewritten as specs, and the logic moved into new leaf modules.
- Whether state connections run or wait for scan.
- The Challenge 2 template and presets, with the missing modules and a short spec of each.
- Where the demand profiles came from (or the question for me).
- Categories or streams you changed.
- Behaviour changes, if any.
- **A ready-to-paste section "gemini public API" for `docs/contracts.md`** (I add it myself): names, shapes, `API_VERSION`.
- Anything `geomind/` or `backend/` call today that does not match (read-only check).

---

# Appendix A: gemini-public-interfaces.md (the specification)

## gemini public interfaces: the list to freeze (draft 3, 2026-10-30)

Draft 3 adds section D0 (building plants from data, agreed with Sahand 15:37).

Draft 2 adds the backend thread's review (marked *backend*) and the geomind thread's review (marked *geomind*; full text in `gemini-public-interfaces-geomind-review.md`).

Goal: every name that frontend, backend and geomind need from gemini is defined, documented and pinned now, so the other repos build against it without waiting. A part not built yet still has its final signature and raises `gm.errors.NotImplementedYet` (see question 1).

Sources read: `phases/contracts.md` v16, `geomind/design.md` sections 4, 9, 12, `phases/geomind/s2-*` and drafts, `phases/backend/phase-3a`, `phase-3`, `phase-4`, `frontend/design.md`, `frontend/feature-map.md`.

Status: **exists** (built, maybe renamed), **3b** (in the drafted step 3b prompt), **new** (not planned yet).

### A. Package rules

| Name | Who | Status |
|---|---|---|
| `gm.__version__`, `gm.API_VERSION` (raised on every interface change, written in contracts.md) | all | new |
| `__all__` everywhere, pinned by `tests/unit/test_public_api.py`; `gm.utils` stays private | all | 3b |
| `.claude/docs/api.md`: one page listing every public name, with links | all | new |
| Every return value is plain JSON: no numpy types, no NaN; pinned by a test *geomind* | all | new |
| Results are deterministic (same input, same numbers) *geomind* | geomind evals | new |
| JSON schemas of the three exchanged documents (module description, plant file, results summary) in `gemini/schemas/*.json`, plus sample files | backend, frontend, geomind | new |

### B. Module catalogue

| Name | Returns | Who | Status |
|---|---|---|---|
| `gm.modules.names(category=None)` | registry names | geomind `list_modules`, backend palette | 3b |
| `gm.modules.get(name)` | the class; unknown name raises with "did you mean" | all | 3b |
| `gm.modules.register(cls)` and `gm.modules.load_file(path)`: a new module joins the registry and a plant inside the sandbox *geomind* | geomind | new |
| `gm.modules.categories()` | the fixed category list | frontend icons/palette | new |
| `gm.streams.names()` | the fixed stream-type list | frontend colours | new |

Proposed categories: `subsurface`, `well`, `pump`, `separation`, `heat_exchange`, `heat_pump`, `chiller`, `boiler`, `storage`, `network`, `consumer`, `plant`.
Proposed streams: `brine`, `hot_water`, `chilled_water`, `gas`, `electricity`, `fuel`.

### C. Module description (one JSON dict)

`Module.describe()` (class or instance) returns:

```text
{name, type, category, summary, doc,
 parameters: {name: {type, unit, quantity, default, minimum, maximum, enum, description, section}},
 controls, boundaries, measured, state: same shape as parameters,
 inlets / outlets: {port: {stream, fields: {name: {unit}}}},
 outputs: {name: {unit, kind}}            kind = one of the 9 additive types or null
 children: {name: type},                  composites only
 connections: [{source: "path.port", target: "path.port", stream}]}
```

| Name | Who | Status |
|---|---|---|
| `Module.describe()` as above | geomind `describe_module`, backend flowsheet | 3b (category + connections); rest new |
| `Module.parameter_schema()`: plain JSON Schema, each property with `unit` (frontend forms with ajv) | backend parameters, frontend | new |
| `Module.help()` text | geomind | exists |
| `gm.modules.get(name).validate_params(params)` -> `[{path, message, code}]`, same shape as `gm.plants.validate` (catalogue entries hold params without a plant) *backend* | backend catalogue | new |

`outputs` also carry `soft_sensor: bool`, so the backend knows which outputs become calculated tags *backend*.

### D0. Building plants: three levels, one representation (agreed 15:37)

Like Keras over TensorFlow, so agents build and simulate plants without writing Python.

1. **Builder:** `p = gm.Plant(name)`, `p.add(type, name=None, **params)` (registry name or class, unit strings accepted), `p.connect(a, b, ...)` (module or `"path.port"`; ports matched automatically when exactly one port of the same stream type fits, otherwise an error that lists the candidates), `p.summary()` (table like Keras `model.summary()`), `p.validate()`, `p.simulate(profile)`.
2. **Spec (JSON):** `p.to_spec()` / `gm.plants.from_spec(spec)` / `gm.plants.validate(spec)` / `gm.plants.spec_schema()`. The spec is the stored plant file (replaces the class-based format in section D):

```json
{"format": 2, "name": "doublet",
 "modules": {"res": {"type": "Reservoir", "params": {"depth": "2.5 km"}},
             "prod": {"type": "ProductionWell", "params": {}}},
 "connections": [{"source": "res.outlet", "target": "prod.inlet"},
                 {"source": "inj.outlet", "target": "res.inlet", "kind": "state"}],
 "bindings": {}, "param_history": {}}
```

3. **Subclassing:** `Module` with `forward`, only for leaf modules and special cases.

Decisions:
- One plant representation: every existing example plant (Doublet, HeatingSubstation, CoolingSubstation, DistrictNetwork, AtesPlant, DoubletHeatPlant, ...) is rewritten as a spec; no handwritten plant classes remain. Templates and presets are spec files (`gm.plants.templates()`, `from_template(name, parameters)` fill a spec).
- Only `connect` wires modules; no call syntax.
- Loops are closed by an explicit connection with `"kind": "state"` (reads the previous step's value); fits the future scan. A loop without a state connection is a validation error.
- The built plant is a normal `Module` (traced into the graph like any other), so `describe()`, outputs auto-sum, `simulate`, `replay` all work unchanged.
- validate returns all problems at once with spec paths (`connections[1].target`) and "did you mean" suggestions.
- geomind gets one tool `build_plant(spec)` whose input schema is `spec_schema()`; the frontend can draw freely later because wiring is data.

### D. Plants (file format and loading)

| Name | Does | Who | Status |
|---|---|---|---|
| `gm.plants.names()` / `get(name)` | plant classes by registry name | backend, geomind | 3b |
| `gm.plants.templates()` | `[{name, title, description, purpose}]`, purpose heating, cooling or both | backend templates route, geomind `list_plants` | new |
| `gm.plants.from_template(name, parameters)` *geomind* | geomind `configure_plant` | new |
| `plant.describe()` includes current parameter values *geomind* | geomind `read_plant` | new |
| `gm.plants.example(name)` | a plant with real values | all tests | 3b |
| `gm.plants.from_dict(data)` / `plant.to_dict()` | load and save; file = the spec of section D0 (format 2) | backend storage, geomind workspace | 3b |
| `gm.plants.validate(data)` | list of problems `[{path, message, code}]`, no raise | backend `422 plant_invalid` details | new |
| Round trip: `to_dict(from_dict(x)) == x` for current-format files, JSON-safe, no float drift (the backend digests sorted-key JSON and refuses identical saves) *backend* | backend | | new |
| `gm.plants.migrate(old)` | old file to current format | backend data migration, geomind | 3b |
| `gm.plants.convert_legacy(folder)` | legacy project to plant dict; documents which files it expects in the folder *backend* | backend import | new |
| `plant.get_module(path)`, `plant.named_modules()` | walk the tree by dotted path | all | exists (check names) |

### E. Parameters by date and bindings

| Name | Does | Who | Status |
|---|---|---|---|
| `plant.set_params(path, params, valid_from=None)` | dated parameter entry, validated | backend parameters, geomind `configure_plant` | new (today: edit `param_history` by hand) |
| `plant.params_at(path, time=None)` / `plant.param_history(path)` | values on a date, history | backend, frontend "as on date" | new |
| `plant.bindable(path)` | `{controls, boundaries, inlets: {port: [field]}, measured, state}` | backend bindings | new |
| `plant.set_bindings(path, bindings)`; binding = `{column, unit}` | replace bindings, units checked | backend | exists partly (`Bindings`) |
| Trajectory and tally: which module, which parameter, which shape | upload routes | backend | decide (documented only) |

### F. Units

| Name | Does | Who | Status |
|---|---|---|---|
| Inputs accept `"150 m3/h"` strings or numbers in SI | geomind tools, backend | exists partly |
| `gm.units.names()`, `gm.units.parse(text)`, `gm.units.convert(value, from, to)` | listed units, frontend unit choice later | new |
| Every output states its SI unit | all | exists |
| `gm.units.fits(unit, quantity)`: binding units checked against declarations, CSV headers `name [unit]` validated *backend* | backend | new |

### G. Running a plant

| Name | Does | Who | Status |
|---|---|---|---|
| `gm.Engine(plant, backend="numpy")` | one runner | all | exists |
| `engine.simulate(profile)` | profile = table with a time index and binding columns (DataFrame or dict of arrays) | geomind `simulate`, design loop | exists (freeze profile format) |
| `engine.replay(data, start=None, end=None, state=None)` returns results + end state | backend soft sensors (incremental runs) | exists partly (state handover new) |
| Replay and simulate input frozen: `gm.Dataset` or DataFrame, tz-aware UTC index, columns = binding `column`, units from the binding; documented behaviour for missing columns and NaN rows *backend* | backend, geomind | new |
| `callbacks=[...]` with progress (`i / n`) and a clean stop (a callback raises `gm.errors.Cancelled`) for long Celery runs *backend* | backend | new |
| Threading rule documented: plants and engines are not shared across threads; each worker loads its own *backend* | backend | new |
| `engine.live(source)` | live mode | later users | exists |
| `gm.evaluate(module, parameters, inlets, controls)` | one call of one module; `module` is a registry name or a class; fixed return shape `{outlets, outputs, errors}` *geomind* | geomind `evaluate_module` | new (one function instead of hand setup) |
| `Results`: `names()`, `get(path, field)` (series + unit), `summary(path=None, start=None, end=None)` (min, max, mean, unit), `get` also takes `start`, `end` *geomind*, `to_bytes()` / `gm.Results.from_bytes(data)` for storage without a file path *geomind*, `errors()` (row codes), `to_frame()`, `to_dict()`, `save(path)` / `gm.Results.load(path)` | geomind `read_result`, artifacts, backend calculated tags (column name = `path.field`) | exists partly (freeze names and file format) |

#### Demand profiles *geomind*

| Name | Does | Status |
|---|---|---|
| `gm.profiles.names()`, `gm.profiles.get(name)` | heating and cooling design-year demand profiles; profile format as a JSON schema | new |

### H. Well performance (backend B4, frontend section 6)

Proposed namespace `gm.analysis`:

| Name | Returns | Status |
|---|---|---|
| `nodal(plant, well, conditions)` | IPR and VLP curves, operating point; what-if = several conditions | new (physics partly in modules) |
| `injectivity(data, well)` | Hall integral, derivative, skin lines | new |
| `pump_curve(plant, pump, measured=None)` | manufacturer curve and measured points (head in m, the `a × h + b` correction moves here from legacy JS) | new |
| `calibrate_pump(plant, pump, measured)` | correction factors, ready for `set_params` | new (over `gm.optim.calibrate`) |

### I. Well integrity (frontend 7.8, 7.9)

| Name | Returns | Status |
|---|---|---|
| `gm.analysis.calibrate_corrosion(logs)` / `corrosion_forecast(model, until)` | wall thickness over time, years left | new (corrosion model exists) |
| `gm.analysis.erosion(plant, well)` | wear of pump and tubing (DNV RP O501) | new (erosion model exists) |

Barriers, schematic, annulus limits, maintenance and history are backend data only; gemini is not involved.

### J. Design, economics and checks (Challenge 2, geomind S3/S4)

| Name | Does | Status |
|---|---|---|
| Heating-and-cooling plant template(s): wiring in Python, sizes as parameters, unused units switched off by a parameter | new (biggest risk) |
| `gm.economics.capex(plant)`, `opex(plant, results)`, `lcoh(plant, results, discount_rate, lifetime)`, `lcoc(...)` for cooling, `co2(results, factors)` | `Cost`, `total_cost` exist; rest new |
| `gm.economics.Assumptions`: one object with sourced defaults (discount rate, lifetime, prices, emission factors); units on every return *geomind* | new |
| `gm.economics.npv(...)`, `payback(...)` *geomind* | new |
| `gm.kpi.names()` *geomind* | new |
| `gm.kpi(plant, results)`: fixed KPI names such as `heating_coverage`, `cooling_coverage`, `cop`, `peak_heat`, `peak_cold` (the problem state's `metric` uses these names) | new |
| `gm.checks.energy_balance(results)`, `mass_balance(results)` over time series; each check returns `{name, passed, value, tolerance}` | exist for one call; time series new |
| `gm.checks.run_all(plant, results)` including bounds checks *geomind* | new |
| Optional, signatures only: `gm.optim.minimize`, uncertainty sampling *geomind* | new |

### K. Errors

`gm.errors`: `GeminiError` (base) with `to_dict() = {class, message, path, code, suggestions}` used for `422` details and geomind tool results. Classes: `ValidationError`, `UnknownNameError` (did you mean), `UnitError`, `PlantFormatError` (old format, failed migration), `SolverError`, `Cancelled`, `NotImplementedYet`. `code` comes from a fixed, listed set, because it goes into `422` details *backend*. Row error codes listed with their meaning.

Status: partly exists; `to_dict`, the fixed class list and `NotImplementedYet` are new.

### L. New modules written by the agent (Challenge 1)

| Name | Does | Status |
|---|---|---|
| `gm.testing.check_module(cls)` | runs gemini's module rules on a new class (declarations, units, describe works, one call); returns a report, never raises *geomind* | new |
| `.claude/docs/modules.md` as the "write a module" guide | geomind skill | exists (check) |

### Questions to agree on

1. Not built yet: final signature now, raising `NotImplementedYet`, plus sample JSON files (recommended), or leave them out until built?
2. Performance and integrity calculations in one `gm.analysis` namespace (recommended), or as methods on the modules?
3. Results file: own `save/load` on `.npz`, no new dependency (recommended), or Parquet?
4. The category and stream lists in section B: OK, or change?
5. Challenge 2 templates: one plant with switchable units plus a few presets (recommended), or several separate plants?
6. Freeze rule: after this step any change to these names raises `gm.API_VERSION` and contracts.md in the same commit.

geomind thread's answers: 1, 2, 4, 5, 6 yes; 3 npz fine plus `to_bytes`/`from_bytes`.

Backend thread's answers: 1 yes (NotImplementedYet + samples), 2 `gm.analysis`, 3 npz, 4 lists fine, 5 switchable plant + presets, 6 yes, and the backend checks `gm.API_VERSION` at startup.

---

# Appendix B: contracts.md excerpt (cross-repo contract, read-only)

Excerpt: the header, section 1 general rules, workspace/projects, plant (B3a) and section 3's Workspace protocol. Identity, assistant and live-event parts are left out because gemini does not touch them.

## Contracts between the repos

Version 18 (2026-10-30). Version 18: flowsheet `layout` (stored beside the spec, not versioned) and `PUT /plant/flowsheet/layout`. Version 17: plant routes follow gemini's JSON plant spec (format 2): flowsheet returns the `spec`, takes a whole `spec` or a `template`, adds `palette` and `validate`; modules are addressed by spec id; `plant_invalid` details list `problems`. Version 16: from geomind S2: stored sequence numbers can have gaps, saved problem state may carry a `compaction` key, `gd.Run` takes an optional `agent=` for manual testing only. Version 15: internal `compaction` event (geomind S2). Version 14: `step.finished` carries `text`, the step's full assistant text. Version 13: how `RunStore` stores events (full `event.to_dict()`, not `data()`), nested runs share the root run's log, `text.delta` is stream-only from S2. Version 12: flowsheet modules carry `category`, connections carry `stream`. Version 11: plant domain routes (backend B3a, frontend F3) in section 1. Version 10: creates answer 201, code `unavailable` (503), refresh tokens rotate (from the B1 report). Version 9: geomind drops checkpoints (the event log is the only run state): `save_checkpoint`/`load_checkpoint` and the internal `checkpoint` event are removed. Version 8: the agent package is now `geomind` (`import geomind as gd`) in sections 2 and 3; `step.started.model`, option answers and `run.error` from geomind defined. Version 7: assistant routes for B2 (runs list per project, chat problem state, the user message carries its run). Version 6: the agent package `geomind` is being renamed `geomind` (`import geomind as gd`), see section 3. File version, raised on every change: section 1 from the backend design (refresh, `active`, project owner and plant version, run request and error, chat edit and delete, error codes, `?cursor=`, validation details); sections 2 and 3 from the geomind design (section 3 keeps its own interface version, now 2.2). Covers steps 1 and 2 of every repo. Later steps add their routes here before they start.

### 1. HTTP API (frontend ↔ backend)

- Base: `/api/v1`. JSON. Times are ISO 8601 with a timezone, UTC.
- Path = `/<domain>/<feature>/...`, the same names as the folders in both repos.
- Auth: bearer access token from `identity/authn`, renewed with `POST /identity/authn/refresh`. A refresh token works once: the response carries a new one, which the client must keep. Tokens never go in URLs.
- Live events (section 2) are read with `fetch` and the bearer header (for example `@microsoft/fetch-event-source`), because the browser's `EventSource` cannot send an `Authorization` header.
- Errors: `{"error": {"code": "<snake_case>", "message": "<human text>", "details": {...}}}` with a matching HTTP status. Codes are stable; messages may change.
- Lists: `{"items": [...], "next": "<cursor or null>"}`; the next page is `?cursor=<next>` (optional `?limit=`, default 50).
- Stable error codes: `unauthorized` (401), `forbidden` (403), `not_found` and `<thing>_not_found` (404), `validation_failed` (422, `details = {"fields": {"<field>": "<message>"}}`), `conflict` (409), `run_not_waiting` (409), `plant_invalid` (422), `rate_limited` (429), `unavailable` (503, a backing service such as Redis is down), `internal` (500). Every `POST` that creates something (user, project, import, chat, message) answers `201`. A project the caller may not see answers `404 project_not_found`, the same as a missing one.

#### workspace/projects

| Method | Path | Body → Response |
|---|---|---|
| GET | `/workspace/projects` | → list of `project` |
| POST | `/workspace/projects` | `{name}` → `project` |
| GET | `/workspace/projects/{id}` | → `project` |
| DELETE | `/workspace/projects/{id}` | → `204` |
| GET | `/workspace/projects/{id}/export` | → zip file |
| POST | `/workspace/projects/import` | multipart `file` → `project` |

`project = {id, name, owner: {id, name}, plant_version, created, updated}`; `plant_version` is the latest plant version number or `null`. Only the owner or an admin may read or change a project.

Export zip: `project.json` (`{format: 1, name, exported}`) and `plant/<number>.json` (`{number, note, created, content}`, `content` in gemini's plant format), one file per plant version. Import takes the same zip.

#### plant (B3a)

New codes: `plant_not_found`, `module_not_found`, `entry_not_found`.

Shapes:

```text
version    = {number, note, author: {id, name}, created}
spec       = gemini's plant spec, format 2 (see step 2), stored and returned unchanged
template   = {name, title, description, purpose}       purpose: heating, cooling or both
palette    = {type, title, category, summary}          one module type from gemini's registry
flowsheet  = {project, version, spec, layout,
              modules: [{id, type, title, category}],
              connections: [{source: "<id>.<port>", target: "<id>.<port>", stream, kind}]}
             category: the module's gemini category (icon, palette group, layout)
             stream: the stream type of the connection, from gemini (colour)
             kind: "state" for a connection that closes a loop, else null
             layout: {<module id>: {x, y}} saved by the editor, or null (the frontend lays out automatically)
problem    = {path, message, code}                     path into the spec, e.g. "connections[1].target"
parameters = {module, type, schema, values, history: [{valid_from, params}]}
             schema: JSON schema of the module's parameters, each property with "unit"
             values: effective at ?at= (or latest)
bindings   = {module, type, bindable: {controls: [name], boundaries: [name],
              inlets: {port: [field]}, measured: [name], state: [name]},
              bindings: {controls: {name: binding}, boundaries: {...},
              inlets: {port: {field: binding}}, measured: {...}, state: {...}}}
binding    = {column, unit}
entry      = {id, kind, name, manufacturer, params, created, updated}
```

##### plant/flowsheet

| Method | Path | Body → Response |
|---|---|---|
| GET | `/plant/flowsheet/palette?category={name?}` | → list of `palette` |
| GET | `/plant/flowsheet/templates` | → list of `template` |
| GET | `/plant/flowsheet?project={id}` | → `flowsheet` of the latest version; `404 plant_not_found` if none |
| POST | `/plant/flowsheet` | `{project, base, note, spec, layout?}` or `{project, base, note, template, parameters?}` → `201 flowsheet` (new version) |
| PUT | `/plant/flowsheet/layout` | `{project, base, layout}` → `flowsheet` (latest version's layout replaced; no new version) |
| POST | `/plant/flowsheet/validate` | `{spec}` → `{problems: [problem]}` (empty when valid; nothing saved) |
| GET | `/plant/flowsheet/versions?project={id}` | → list of `version`, newest first |
| GET | `/plant/flowsheet/versions/{number}?project={id}` | → `flowsheet` of that version |

##### plant/parameters

| Method | Path | Body → Response |
|---|---|---|
| GET | `/plant/parameters?project={id}&module={id}&at={time?}` | → `parameters` |
| POST | `/plant/parameters` | `{project, base, module, params, valid_from?, note}` → `201 version` |
| POST | `/plant/parameters/fill` | `{project, base, module, entry, valid_from?, note}` → `201 version` |

##### plant/bindings

| Method | Path | Body → Response |
|---|---|---|
| GET | `/plant/bindings?project={id}&module={id}` | → `bindings` |
| POST | `/plant/bindings` | `{project, base, module, bindings, note}` → `201 version` |

##### plant/catalogue

| Method | Path | Body → Response |
|---|---|---|
| GET | `/plant/catalogue?kind={name?}` | → list of `entry` |
| POST | `/plant/catalogue` | admin, `{kind, name, manufacturer?, params}` → `201 entry` |
| PATCH | `/plant/catalogue/{id}` | admin, `{name?, manufacturer?, params?}` → `entry` |
| DELETE | `/plant/catalogue/{id}` | admin → `204` |

Rules for every save: `base` must equal the latest version number (`null` when there is none), else `409 conflict` with `{"latest": n}` in `details`; identical content is `409 conflict`; gemini validation failures are `422 plant_invalid` with `details = {"problems": [problem]}`. `module` in the parameters and bindings routes is a module id from the spec.


### 3. geomind interfaces (excerpt)

```python
class Workspace(Protocol):
    def plant(self, project_id): ...            # the stored plant as a gemini plant
    def documents(self, project_id, query): ... # document search: [{id, title, text, score}]
```
