# gemini public interfaces: the list to freeze (draft 3, 2026-10-30)

Draft 3 adds section D0 (building plants from data, agreed with Sahand 15:37).

Draft 2 adds the backend thread's review (marked *backend*) and the geomind thread's review (marked *geomind*; full text in `gemini-public-interfaces-geomind-review.md`).

Goal: every name that frontend, backend and geomind need from gemini is defined, documented and pinned now, so the other repos build against it without waiting. A part not built yet still has its final signature and raises `gm.errors.NotImplementedYet` (see question 1).

Sources read: `phases/contracts.md` v16, `geomind/design.md` sections 4, 9, 12, `phases/geomind/s2-*` and drafts, `phases/backend/phase-3a`, `phase-3`, `phase-4`, `frontend/design.md`, `frontend/feature-map.md`.

Status: **exists** (built, maybe renamed), **3b** (in the drafted step 3b prompt), **new** (not planned yet).

## A. Package rules

| Name | Who | Status |
|---|---|---|
| `gm.__version__`, `gm.API_VERSION` (raised on every interface change, written in contracts.md) | all | new |
| `__all__` everywhere, pinned by `tests/unit/test_public_api.py`; `gm.utils` stays private | all | 3b |
| `.claude/docs/api.md`: one page listing every public name, with links | all | new |
| Every return value is plain JSON: no numpy types, no NaN; pinned by a test *geomind* | all | new |
| Results are deterministic (same input, same numbers) *geomind* | geomind evals | new |
| JSON schemas of the three exchanged documents (module description, plant file, results summary) in `gemini/schemas/*.json`, plus sample files | backend, frontend, geomind | new |

## B. Module catalogue

| Name | Returns | Who | Status |
|---|---|---|---|
| `gm.modules.names(category=None)` | registry names | geomind `list_modules`, backend palette | 3b |
| `gm.modules.get(name)` | the class; unknown name raises with "did you mean" | all | 3b |
| `gm.modules.register(cls)` and `gm.modules.load_file(path)`: a new module joins the registry and a plant inside the sandbox *geomind* | geomind | new |
| `gm.modules.categories()` | the fixed category list | frontend icons/palette | new |
| `gm.streams.names()` | the fixed stream-type list | frontend colours | new |

Proposed categories: `subsurface`, `well`, `pump`, `separation`, `heat_exchange`, `heat_pump`, `chiller`, `boiler`, `storage`, `network`, `consumer`, `plant`.
Proposed streams: `brine`, `hot_water`, `chilled_water`, `gas`, `electricity`, `fuel`.

## C. Module description (one JSON dict)

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

## D0. Building plants: three levels, one representation (agreed 15:37)

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

## D. Plants (file format and loading)

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

## E. Parameters by date and bindings

| Name | Does | Who | Status |
|---|---|---|---|
| `plant.set_params(path, params, valid_from=None)` | dated parameter entry, validated | backend parameters, geomind `configure_plant` | new (today: edit `param_history` by hand) |
| `plant.params_at(path, time=None)` / `plant.param_history(path)` | values on a date, history | backend, frontend "as on date" | new |
| `plant.bindable(path)` | `{controls, boundaries, inlets: {port: [field]}, measured, state}` | backend bindings | new |
| `plant.set_bindings(path, bindings)`; binding = `{column, unit}` | replace bindings, units checked | backend | exists partly (`Bindings`) |
| Trajectory and tally: which module, which parameter, which shape | upload routes | backend | decide (documented only) |

## F. Units

| Name | Does | Who | Status |
|---|---|---|---|
| Inputs accept `"150 m3/h"` strings or numbers in SI | geomind tools, backend | exists partly |
| `gm.units.names()`, `gm.units.parse(text)`, `gm.units.convert(value, from, to)` | listed units, frontend unit choice later | new |
| Every output states its SI unit | all | exists |
| `gm.units.fits(unit, quantity)`: binding units checked against declarations, CSV headers `name [unit]` validated *backend* | backend | new |

## G. Running a plant

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

### Demand profiles *geomind*

| Name | Does | Status |
|---|---|---|
| `gm.profiles.names()`, `gm.profiles.get(name)` | heating and cooling design-year demand profiles; profile format as a JSON schema | new |

## H. Well performance (backend B4, frontend section 6)

Proposed namespace `gm.analysis`:

| Name | Returns | Status |
|---|---|---|
| `nodal(plant, well, conditions)` | IPR and VLP curves, operating point; what-if = several conditions | new (physics partly in modules) |
| `injectivity(data, well)` | Hall integral, derivative, skin lines | new |
| `pump_curve(plant, pump, measured=None)` | manufacturer curve and measured points (head in m, the `a × h + b` correction moves here from legacy JS) | new |
| `calibrate_pump(plant, pump, measured)` | correction factors, ready for `set_params` | new (over `gm.optim.calibrate`) |

## I. Well integrity (frontend 7.8, 7.9)

| Name | Returns | Status |
|---|---|---|
| `gm.analysis.calibrate_corrosion(logs)` / `corrosion_forecast(model, until)` | wall thickness over time, years left | new (corrosion model exists) |
| `gm.analysis.erosion(plant, well)` | wear of pump and tubing (DNV RP O501) | new (erosion model exists) |

Barriers, schematic, annulus limits, maintenance and history are backend data only; gemini is not involved.

## J. Design, economics and checks (Challenge 2, geomind S3/S4)

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

## K. Errors

`gm.errors`: `GeminiError` (base) with `to_dict() = {class, message, path, code, suggestions}` used for `422` details and geomind tool results. Classes: `ValidationError`, `UnknownNameError` (did you mean), `UnitError`, `PlantFormatError` (old format, failed migration), `SolverError`, `Cancelled`, `NotImplementedYet`. `code` comes from a fixed, listed set, because it goes into `422` details *backend*. Row error codes listed with their meaning.

Status: partly exists; `to_dict`, the fixed class list and `NotImplementedYet` are new.

## L. New modules written by the agent (Challenge 1)

| Name | Does | Status |
|---|---|---|
| `gm.testing.check_module(cls)` | runs gemini's module rules on a new class (declarations, units, describe works, one call); returns a report, never raises *geomind* | new |
| `.claude/docs/modules.md` as the "write a module" guide | geomind skill | exists (check) |

## Questions to agree on

1. Not built yet: final signature now, raising `NotImplementedYet`, plus sample JSON files (recommended), or leave them out until built?
2. Performance and integrity calculations in one `gm.analysis` namespace (recommended), or as methods on the modules?
3. Results file: own `save/load` on `.npz`, no new dependency (recommended), or Parquet?
4. The category and stream lists in section B: OK, or change?
5. Challenge 2 templates: one plant with switchable units plus a few presets (recommended), or several separate plants?
6. Freeze rule: after this step any change to these names raises `gm.API_VERSION` and contracts.md in the same commit.

geomind thread's answers: 1, 2, 4, 5, 6 yes; 3 npz fine plus `to_bytes`/`from_bytes`.

Backend thread's answers: 1 yes (NotImplementedYet + samples), 2 `gm.analysis`, 3 npz, 4 lists fine, 5 switchable plant + presets, 6 yes, and the backend checks `gm.API_VERSION` at startup.
