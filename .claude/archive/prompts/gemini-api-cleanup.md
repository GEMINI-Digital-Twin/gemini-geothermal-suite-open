# Task: Clean public API: run functions, return shapes, errors, parameters, units; version 0.1.0

## 0. Context and rules

- The public API (`.claude/docs/api.md`) grew in steps and is not consistent: two ways to run a plant, seven shapes for a returned number, about 25 error classes beside error codes, three ways to report a problem, parameters as keyword arguments in one place and dicts in another. This task makes it one consistent API, decided with me section by section below. Physics, the runner, the graph, the backends and **every number stay as they are**.
- Only this. The `Module` base cleanup, the plant rewrite (plant dicts, removing templates and `spec` names, plants as registered classes) and the hackathon features (reservoir from depth, demand data, daily dispatch, hackathon checks) are **later prompts**. Do not start them.
- Start from the current local `refactor`, with the physics-cleanup commits in. Read `AGENTS.md` and every file in `.claude/docs/` and follow them.
- **Standing rules:** no concept has two implementations; behaviour is identical on every backend; modules declare and wire, physics computes. No aliases, shims or deprecation wrappers for removed names: one name per thing.
- Work directly on branch `refactor` (no new branch, no PR). One commit per section below, in order. **Do not push** until I have reviewed the commits.
- **Pre-check:** `git status` is clean on `refactor`, and no other Claude session or process is working **inside `gemini/`**. Sessions in other folders do not block you. If their load makes a 1 s budget test fail, rerun that test alone before treating it as a failure, and say which tests you retimed.
- Workspace `/Users/sahand/Desktop/crust-team`. Change **only** `gemini/`. You may read `geomind/` and `backend/` to find what this breaks, but never change them.
- Temporary files go to `.tmp/api-cleanup/` (git-ignored).
- One agent is enough. Subagents, if any, run on a lighter model and only for read-only searches.
- **Tests:** development profile only (`make test` / `scripts/test_changed.py`, always including `test_code_quality.py`), in parallel, under 300 s; plus the e2e tier and all numbered examples once at the end, compared with a baseline you take before the first change: every number identical; only the shape of returned dicts and the names of error classes may differ, and the report lists each such difference by kind. Never run the slow dataset locally. Never delete or shrink existing tests, datasets or goldens; a golden that only changes shape is converted, never regenerated from new numbers.
- **Quality bar** as in `.claude/docs/conventions.md`: simple, readable, just enough code; nesting at most 3; functions about 40 lines at most; guard clauses; explicit `gm.errors`; no comments inside code (docstrings only); black, isort and flake8 clean.
- If something else is needed, say so in the report.

## 1. Version 0.1.0

- The package has one version: `gm.__version__ = "0.1.0"`, read from `pyproject.toml` (`version = "0.1.0"`), the single source. `gm.API_VERSION` is removed; the public-API snapshot, checkpoints and saved results record `gm.__version__`.
- Semantic versioning while below 1.0: a breaking change to a public name or return field raises the minor number (`0.2.0`), an addition or fix raises the patch number. The freeze rule in `api.md` says this, and the snapshot test checks that the snapshot changes only together with the version.
- The change log in `api.md` starts again at `0.1.0` ("First consistent API"); the old integer entries move into one short "Before 0.1.0" paragraph.
- Checkpoints and results files written before `0.1.0` do not load: they raise `ValidationError` with code `old_format`. Nothing in production depends on them.

## 2. Run functions over the public `gm.Engine`

Two levels of one implementation: plain functions for everyday use (agents, backend workers, examples) and `gm.Engine`, kept public, for complex tasks (stateful runs over several calls, callbacks that read the engine, live runs held in memory, manual checkpoints). Each function only builds an `Engine`, calls the matching method and returns its `Results`: no run logic of its own.

```python
gm.simulate(plant, profile, clock=None, checkpoint=None, checkpoint_every=None,
            backend="numpy", callbacks=None, on_error="raise")
gm.replay(plant, data, start=None, end=None, state=None, clock=None, only=None,
          checkpoint=None, checkpoint_every=None,
          backend="numpy", callbacks=None, on_error="raise")
gm.live(plant, source, checkpoint, step=None, now=None, sink=None,
        backend="numpy", callbacks=None, on_error="raise")
gm.resume(checkpoint, callbacks=None)
```

- Each returns `Results`, exactly what the matching `Engine` method returns, with the same numbers on every backend. The arguments keep today's meaning and names: the run arguments from `Engine.simulate`, `replay` and `live`, the runner settings from `Engine.__init__`. `plant` is always first. The `on_error` default becomes `"raise"` (section 4), on the functions and on `gm.Engine`.
- `gm.replay`: `results.end_state` is still the `state=` of the next call, so a long replay can go in pieces with no object kept between calls.
- `gm.live`: the functions keep no object between calls, so `checkpoint` (a path) is required. The first call with a path that does not exist yet starts a live run and writes the checkpoint; every later call continues from it and updates it. Read how `Engine.live` handles `checkpoint` today and keep that behaviour; if it differs, say how in the report before changing anything.
- **Checkpoints through the functions: the `checkpoint` argument.** On `gm.simulate` and `gm.replay`, `checkpoint=path` writes a checkpoint at the end of the run, also when the run stops early (cancelled through `gm.errors.Cancelled`, or failed under `on_error="raise"`), so it can always be resumed. `checkpoint_every` (a step count such as `100` or a duration such as `"1h"`) also writes it during the run, with today's `AutoCheckpoint` logic; `checkpoint_every` without `checkpoint` raises `ValidationError`. Without `checkpoint` nothing is written.
- The functions write checkpoints with the engine's own `save_checkpoint` and `AutoCheckpoint`, so a checkpoint written by a function or by an `Engine` is the same file and either can be resumed by `gm.resume` or `gm.Engine.load_checkpoint(path).resume()`. `Engine.save_checkpoint`, `load_checkpoint`, `resume` and `AutoCheckpoint` stay public.
- `gm.resume(checkpoint)` continues an interrupted `simulate` or `replay` and returns its `Results`, as `Engine.load_checkpoint(path).resume()` does: strictly after the saved position, with the saved backend and error policy, and the same results as an uninterrupted run. It keeps writing to the same file. On a finished run it returns the stored results. On a live checkpoint it raises `RunError` naming `gm.live`.
- Callbacks keep their names and arguments, including the engine as first argument; the functions pass `callbacks` through unchanged.
- **No retracing between calls.** Today each `Engine` owns its `GraphCache`, so a new engine per function call would trace the plant again. An agent or `gm.optim` calls `gm.simulate` hundreds of times on one plant with different numbers, so the traced graph must outlive the call: keep one cache per plant (for example held by the plant, or a per-thread cache keyed weakly by module), never one global cache shared across threads. The guards stay as they are: a changed numeric parameter does not retrace, a changed structure does. Test: two `gm.simulate` calls on the same plant with a changed numeric parameter make one trace in total and give the numbers of two fresh plants. Report the time of the second call against the first on the doublet example.
- `plant.simulate(profile)` (in `modules/plants/builder.py`) is removed.
- Uses in `gemini/`, `tests/`, `examples/` and `scripts/`: a one-call run becomes the function; code that keeps the engine between calls, reads it in callbacks or tests the runner keeps `gm.Engine`.

## 3. Three return shapes

Every public return that carries data uses only these three shapes, defined once in `gemini/types/` with a JSON Schema each in `docs/schemas/` (`value`, `problem`, `check`), and built by one helper each so no module assembles them by hand.

1. **Value** `{value, unit}`. `value` is a number, an array or `null`; when it is `null`, a `reason` key says why. The key is `value` for arrays too. A time series is a value with a `time` key beside it: `{time, value, unit}`. Statistics are `{min, max, mean}`, each a value.
2. **Problem** `{path, code, message, suggestions}`, for every error, validation result and failed run row. A run row adds `time`. There is no `class` key: `code` is the stable key for machines.
3. **Check** `{name, passed, value, limit}`, where `value` and `limit` are values. A failed check is an answer, not an error (section 4).

Rules:

- A number always travels with its unit in the same dict: no separate `units` map anywhere (`gm.analysis.nodal` changes too).
- Public returns are plain dicts. A DataFrame comes only from a method named `to_frame`; the one exception is run input (`gm.profiles.get`), because the run-input format is a DataFrame. Text comes only from `help()` and `summary()`, meant for people.
- Apply to every public return in `api.md`: `gm.evaluate` (outlets and outputs), `Results.get`, `Results.summary`, `Results.to_dict` (series), `Results.errors`, `Results.energy_report` (returns a dict; if a table form is still needed, give it one route through a method named `to_frame` and say which you chose), `gm.economics.*`, `gm.kpi.*`, `gm.checks.*`, `gm.analysis.*`, `validate_params`, `p.validate`, `gm.plants.validate`, `GeminiError.to_dict`. List in the report every return whose shape changed, old and new.

## 4. Errors

- **One rule for raising.** Every public call raises on failure by default. Calls that can report instead take one argument with one name everywhere, `on_error="raise" | "record"`, default `"raise"`. With `"record"` nothing is raised and the problems go to the call's fixed place: `validate` functions return the list of problems; `gm.evaluate` returns them under `errors`; a run records them in `results.errors()` and continues; an economics value the inputs cannot give is `{value: null, reason}`. `gm.evaluate` loses its "never raises" rule; the "never raises" behaviour agents need belongs to geomind's tool layer, which catches and calls `to_dict()`.
- A raised error that comes from several problems (for example `gm.plants.from_dict`, `validate`) carries all of them in `error.problems` (a list of problem dicts), the same list `on_error="record"` returns, so a caller sees every problem in one try.
- **Checks are not errors.** `gm.checks.*` always return check dicts with `passed`; a violated limit never raises. A real failure inside a check (wrong input) still raises.
- **Seven public classes**, each deriving from `GeminiError`:

```text
GeminiError
  ValidationError    wrong input: values, dicts, bindings, units, unknown names
  DefinitionError    a module class written wrongly (developer side)
  PhysicsError       out of range, no convergence, missing chemistry, too little data
  RunError           dataset, clock, checkpoint, step
  Cancelled
  NotImplementedYet
GeminiWarning
```

- Every other class goes; what it meant becomes a `code` (for example `unknown_name`, `unknown_port`, `missing_column`, `missing_value`, `out_of_range`, `no_convergence`, `old_format`, `checkpoint`). Keep `CODES` and `ROW_CODES` as the fixed lists, documented with their meaning in `errors.md`.
- Built-in bases only where Python needs them, never two error meanings in one class: `ValidationError` is a `ValueError`; where Python's protocols need `AttributeError` or `KeyError` (`getattr` with a default, `hasattr`, mapping lookups), raise `ValidationError` with code `unknown_name` through a small private subclass that also derives from that built-in, documented as such and not public. `TraceError` becomes internal to `gemini/graph/`: users never see it.
- Update every `raise`, every `except`, the code-quality test that enforces `gm.errors`, and `errors.md`. Report every `except gm.errors.<Removed>` and every check of `.to_dict()["class"]` in `geomind/` and `backend/` (file and line).

## 5. Parameters and bindings

```python
p.add("HeatPump", name="hp", params={"capacity": "12 MW"})
p.add("Doublet", name="d0", params={"reservoir.temperature": "87 degC"})
p.set_params("hp", {"capacity": "14 MW"})
p.set_bindings("heat_users", {"heat_demand": "heating_demand_MWth"})
p.set_bindings("heat_users", {"heat_demand": {"column": "q", "unit": "kW"}})
```

- `add(kind, name=None, params=None)`: parameters are one dict, dotted names allowed, the same dict `set_params` takes. No `**params`.
- `set_bindings(path, bindings)`: keys are declaration names (controls, boundaries, measured outputs, state and inlet fields are unique within a module, so the kind is not needed; if a name is not unique, raise `ValidationError` naming the clash and say where it happens in the report). A value is a column name, whose unit comes from the run input's metadata or else the declaration's SI unit, or `{column, unit}`. The stored plant dict format for bindings stays readable: write it in the new flat form and read only that form.

## 6. Where functions live

```python
gm.economics.capex(plant, assumptions=None)
gm.economics.opex(plant, results, assumptions=None)
gm.economics.lcoh(plant, results, discount_rate=None, lifetime=None, assumptions=None)
gm.economics.lcoc(plant, results, discount_rate=None, lifetime=None, assumptions=None)
gm.economics.co2(plant, results, assumptions=None)
gm.economics.npv(plant, results, discount_rate=None, lifetime=None, assumptions=None)
gm.economics.payback(plant, results, assumptions=None)
gm.kpi.compute(plant, results)
gm.kpi.names()
gm.evaluate(module, parameters, inlets, controls)
gm.testing.check_module(cls, example=None)
```

- Every economics function takes `(plant, results, ...)` (only `capex` has no results), `co2` included.
- `gm.kpi` becomes a namespace, not a function with an attribute: `compute` and `names`.
- `gm.evaluate` stays top-level, beside `gm.simulate`: it is a run at one point. `gm.testing` is for developers only and says so in `api.md`.

## 7. Output units

- Outputs stay SI by default. Every public call that returns values takes an optional `units` argument, a map from quantity to unit: `results.get("hx", "duty", units={"power": "MW"})`, `results.summary(units=...)`, `results.to_dict(units=...)`, `results.to_frame(units=...)`, `gm.evaluate(..., units=...)`, `gm.analysis.*(..., units=...)`.
- Conversion uses `gm.units` only, on the way out; nothing inside the run changes. An unknown quantity or a unit that does not fit it raises `ValidationError` with suggestions. The returned `unit` keys say the unit actually used.

## 8. Docs and tests

- `api.md` is rewritten to match, with the version rules of section 1, the run levels of section 2 (one line on when to use the functions and when `gm.Engine`), the three shapes, and the error rule. Update `engine.md` (a short "functions or engine" section at the top), `errors.md`, `economics.md`, `plants.md`, `types.md`, `runtime.md`, `AGENTS.md` ("Start here"), the README, every docstring and every example.
- The documented short example becomes:

```python
import gemini as gm

plant = gm.plants.example("DoubletHeatPlant")
results = gm.simulate(plant, profile)
print(results.summary(units={"power": "MW", "temperature": "degC"}))
```

- Tests: one test per shape helper and schema; a test that every public return validates against its schema (walk `api.md` entries on the doublet example); the trace-count and cancel-and-resume tests of section 2; one test per `on_error` place of section 4; the public-API snapshot at `0.1.0`.

## 9. Report

- Commits, one per section.
- Final signatures of `gm.simulate`, `gm.replay`, `gm.live`, `gm.resume`; trace count and second-call time from section 2; what `gm.live` does on the first and on later calls.
- Every return whose shape changed, old and new; every removed error class and the code that replaces it.
- Any binding-name clash from section 5.
- Test, e2e and example results against the baseline: numbers identical, differences in shape listed by kind.
- What this breaks in `geomind/` and `backend/` (read-only, file and line): uses of `plant.simulate`, one-call `gm.Engine(...)`, `gm.API_VERSION`, removed error classes, `to_dict()["class"]`, `add(**params)`, nested `set_bindings`, old return shapes, `gm.kpi(...)`. This list is the input for updating `phases/contracts.md` and those repos.
