# Task: Freeze and document gemini's public interfaces (replaces step 3b)

## 0. Context and rules

- The goal: **every gemini name that the frontend, the backend and the agent package need is defined, documented and pinned now**, so that they can build against it without waiting for gemini's later implementation work. The agent package is `geomind` (`import geomind as gd`). Parts whose real work comes later still get their **final signature now** and raise `gm.errors.NotImplementedYet`, plus sample files. Once this step lands, a change to any of these names is a versioned change (section 9).
- The full list, agreed with me and reviewed by the backend and geomind sessions, is `gemini-public-interfaces.md`, given next to this prompt (draft 3). **It is the specification.** Sections A to L in it map to the work below. Field names in the cross-repo contract are in `contracts.md`, also given next to this prompt. Where the two differ, follow the interface list and report the difference.
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

You are the coordinator. Create every worktree by hand from `refactor` (`git worktree add -b <tmp> <path> refactor`). Temporary branches are never pushed, and they are deleted after merging. Merge one agent at a time and run the tests after each merge. Two agents never edit the same file in the same wave. Give each agent this prompt, the interface list and its own section numbers.

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
