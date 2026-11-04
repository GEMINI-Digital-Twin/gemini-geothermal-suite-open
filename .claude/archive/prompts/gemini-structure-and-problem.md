# Task: the new gemini structure, and one Problem for every call

## 0. Context and rules

- This is a new session. Read `AGENTS.md` and every file in `.claude/docs/` first and follow them.
- **The rule (most important):** gemini is a general geothermal heating and cooling package. Competition data is only a test sample, never the basis of a name, default or structure. gemini is the source of truth: inputs adapt to gemini, never the other way round.
- **Goal:** (a) move the package to the agreed folder tree (section 1), with the PyTorch layering as the design reference (never name torch in the repo); (b) one `Problem` object, so every call takes only `(plant, problem)` and, where it reads a run, `results`.
- **Scope:** only what is written here. Names marked "stub" are created with a docstring and raise `NotImplementedYet`; they are built in the next task. Keep every existing feature unless a section removes it.
- Start from `refactor` at `1773626` in `/Users/sahand/Desktop/crust-team/gemini`. `git status` must be clean and `git pull origin refactor` must succeed. No other Claude session works inside `gemini/`.
- Where a decision below does not fit the code, stop that section and say why in the report instead of inventing another design.
- **Breaking changes are fine** (nothing is released). No shims, no aliases for old names. Do not change the version; add change-log lines under "unreleased changes" in `api.md`.
- **Git:** work on `refactor`, one commit per section, in order. At the end, if the development tests and the e2e tier pass, `git push origin refactor` and report the hash.
- **Scope of changes:** only `gemini/` (the repository). Read `geomind/` and `backend/`, never change them.
- **Temporary files** go to `.tmp/structure/` (git-ignored).
- **Speed (we are short of time):** work in parallel wherever it is safe. Target: well under an hour.
  - Alone, in order: baseline, section 1 (it moves every file), section 2 (the classes the others use). Commit each.
  - Then four subagents on a lighter model (sonnet), each in its own git worktree on a temporary branch from that commit, each owning only its files:
    - **A:** section 3, owns `run/schedule*`, `run/simulate*`, `run/_utils/`;
    - **B:** section 4, owns `evaluate/`, `optim/`;
    - **C:** section 5, owns `compiler/`, `engine/`, `ops/`, `runtime/`;
    - **D:** section 6, owns `data/`, `inputs/`, `run/problem*`.
    Give each its section text, the rules of section 0, the tree of section 1 and its file list. Each commits once on its branch and runs only the tests of its changed files.
  - You review each branch, bring them onto `refactor` in section order, fix any overlap, and run the development tests once.
  - Then section 7 (the docs part may go to a subagent), the e2e tier once, the push and the report.
  - Never run the same full test set twice without a change in between. Read-only searches use haiku. Remove the worktrees and temporary branches at the end.
- **Tests:**
  - Development profile only (`make test` / `scripts/test_changed.py`, always with `test_code_quality.py`), parallel, under 300 s. New fast tests under about 1 s each.
  - **Baseline first:** before any change, save the numbers of both sample problems (`inputs/examples/hackathon_2027/`, `inputs/examples/shallow_district/`): heat, cold, boiler, electricity, unmet demand, failed steps, LCTS, every limit result. Save them to `.tmp/structure/baseline.json`.
  - After sections 1 and 2 the numbers must be identical. Section 3 may change them (cost dispatch); list every change and why.
  - Never run the slow dataset locally. Never delete or shrink goldens or `inputs/` data (moving and converting is fine).
  - If a 1 s budget test fails, rerun it alone before treating it as a failure, and say which tests you retimed.
- **Read/write naming (new standing rule):** every reader is `from_<format>` and every writer `to_<format>`: `from_csv`, `from_json`, `from_dict`, `from_values`, `from_bytes`, ... and `to_csv`, `to_json`, `to_dict`, `to_bytes`, .... A reader is a classmethod on the class it returns (`gm.Problem.from_json(path)`); a writer is a method of the object (`problem.to_json(path)`). Only a reader that returns no gemini class (a demand frame) is a plain function in its folder (`gm.data.from_csv`). No `read_*`, `write_*`, `load_*`, `save_*`, `parse_*`, `dump_*` names. Section 7 applies it everywhere.
- **Quality bar** as in `.claude/docs/conventions.md`: simple, readable, just enough code; nesting at most 3, functions about 40 lines, guard clauses; explicit `gm.errors` with codes; no comments inside code (docstrings only; the fixed section headers stay); black, isort and flake8 clean; a failing test before each bug fix.

## 1. The folder tree (moves only, numbers identical)

Target tree. There is no `core/`, `base/`, `registry/` or `testing/` folder.

```
gemini/
  __init__.py   see section 7
  modules/      module.py (Module), declarations.py (Parameter, Inlet, Outlet, Output),
                container.py (ModuleList, ModuleDict), check.py (check),
                subsurface/ wells/ pumps/ treatment/ exchangers/ heating/ cooling/
                power/ storage/ piping/ grids/ environment/ control/
  plants/       plant.py (Plant), one file per plant class, _utils/
  physics/      as today, without units.py
  ops/          math API and dispatcher as today, kernels/ (python, numpy, scalars, solvers)
  runtime/      settings, state
  engine/       Engine, Clock, eager runner, executor interface, chunks, checkpoint, ...
  run/          Problem, Constraint, Assumptions, schedule, simulate, replay, live,
                resume, call, Results, Dataset
  types/  units/  errors/  _utils/
  compiler/     graph/ (Tracer, Graph, passes, cache, ...), compile
  data/         from_csv, from_values, profile_schema, synthesize (stub), legacy reader
  optim/        minimize, sample, size (stub), sensitivity (stub)
  evaluate/     totals, capacities (stub), report (stub), compare (stub),
                energy_balance, mass_balance, plant_balance, bounds, run_all, constraints,
                capex, opex, lcoh, lcoc, lcts, annualised_cost, co2, npv, payback
  analysis/     calibrate, calibrate_pump, nodal, injectivity, pump_curve,
                calibrate_corrosion, corrosion_forecast, erosion, fit_head_coefficients,
                fit_head_correction, estimate_reservoir_pressure, estimate_conductance
```

Moves (current → target):
- `modules/plants/*` → `plants/`; `modules/plants/_utils/` → `plants/_utils/`; `modules/plant.py` → `plants/plant.py`.
- `types/declarations.py` → `modules/declarations.py`.
- `modules/_utils/registry.py` → `_utils/registry.py`. Registration becomes automatic through `Module.__init_subclass__`, with the category taken from the folder; classes marked abstract are not registered; a second class with the same name raises `duplicate_name`. Remove public `register` and `load_file`. Keep `gm.modules.get`, `names`, `categories` and `gm.plants.get`, `names`.
- `testing/module.py` (`check_module`) → `modules/check.py` as `gm.modules.check`. Remove `testing/`.
- `engine/evaluate.py` (`evaluate`) → `run/call.py` as `gm.call` (same behaviour: one module or plant, one step, given params, inlets and controls).
- `engine/run.py` (`simulate`, `replay`, `live`, `resume`) and `engine/results.py` → `run/`.
- `utils/data/dataset.py` (`Dataset`) → `run/dataset.py`; its loader becomes `Dataset.from_<format>` (section 7).
- `utils/legacy/` and `plants/_utils/legacy_project.py` → `data/` (renamed by the read/write rule in section 7).
- the rest of `utils/` → `_utils/`.
- `physics/units.py` → `units/`.
- `backends/python.py`, `numpy.py`, `scalars.py`, `solvers.py` → `ops/kernels/`; `backends/base.py` (backend registry, `select`, `implementation`) → `ops/`; `backends/runtime.py` → `runtime/`, merged with `backends.settings(backend)` into one `gm.runtime.settings(backend, precision, display_units, default_fluid)` plus `state()`. Remove `backends/`.
- `graph/` → `compiler/graph/` (section 5 makes the dependency one-way).
- `profiles/` → `data/`.
- `analysis/schedule.py`, `analysis/roles.py` → `run/` (schedule) and `run/_utils/`.
- `analysis/kpi.py`, `analysis/series.py` → `evaluate/` (`totals`; merge `kpi.compute` into `totals` if it duplicates it, say which).
- `checks/` → `evaluate/` (`limits`, `Limits`, `operating_time` stay until section 4 replaces them).
- `economics/` → `evaluate/`; `economics/assumptions.py` → `run/assumptions.py`.
- `optim/calibrate.py` → `analysis/` (`calibrate`); `optim/search.py` stays in `optim/`.
- `analysis/fits.py`, `integrity.py`, `wells.py`, `solves.py` stay in `analysis/`.
- `physics/dispatch.py` and `physics/doublet.py` stay in `physics/`.

Public names are flat: `gm.<folder>.<Name>`, exported by the folder's `__init__`; inner files are private. `physics`, `ops` and `runtime` are sub-namespaces (`gm.physics.fluid`).
Update every import in `gemini/`, `tests/` (mirror the new tree), `examples/` and the docs. Numbers identical to the baseline.

## 2. Problem, Constraint, Assumptions (in `run/`)

All three are plain data objects with `to_dict`, `from_dict`, `schema` and validation through `gm.errors` codes. No defaults that belong to a problem.

**`gm.Problem(demand, site, constraints, assumptions)`**
- `demand`: the run input of `gm.data.from_csv` / `from_values` (any constant step and length).
- `site`: values of plant parameters that describe the site, keyed by parameter path with `*` (`{"d*.gradient": "30 K/km", "d*.surface_temperature": "12 degC"}`), values with units.
- `constraints`: a list of `gm.Constraint`.
- `assumptions`: a `gm.Assumptions`.
- `to_dict` stores the demand in the shape `from_values` takes (start, step, units, quantities, values per column).

**`gm.Constraint(path, min=None, max=None, equals=None, over="each", when=None)`**
- `path`: a result field or a parameter path, `*` allowed; each match is checked on its own.
- `over`: `each` (every step), `sum`, `mean`, `max`, `min` (aggregated over the run), `duration` (total time of the steps where `when` holds; `min` / `max` are durations).
- `when`: `None` or `"running"` (the module of the path carries flow).
- A parameter path takes only `over="each"`; anything else is `ValidationError` `invalid_value`.
- At least one of `min`, `max`, `equals`.

**`gm.Assumptions`**: today's economics assumptions, plus `prices` (per carrier: a constant with unit or a profile on the demand index) and `co2_price`. Lifetime and discount rate as today.

Tests: round trip of all three through `to_dict` / `from_dict`; each validation error code.

## 3. schedule and simulate take the problem (subagent A)

- `gm.schedule(plant, problem)` and `gm.simulate(plant, problem, plan=None, ...)`. Without a plan, `simulate` schedules first. `replay`, `live`, `resume` keep their inputs.
- **Site:** `problem.site` values are applied for the run without changing `plant`. A site path that the plant has also set explicitly is a `ValidationError` (an existing code, or add `conflicting_value`) naming the path.
- **Constraints in the schedule:** `rules` is removed. The schedule enforces the constraints it can (today: flow range per doublet when running, maximum brine cooling, operating duration with outages as the lowest-demand steps spread over the doublets) and lists every other constraint in `plan.attrs["check_only"]`. A constraint it needs and does not find is `missing_value` naming it.
- **Cost dispatch:** `order` and `cooling_order` are removed. In each step every heat and cold source of the plant gets a marginal cost `price / efficiency + co2_price * emission`, with the efficiency (COP, boiler efficiency, pump electricity of the doublets) from the modules at that step; sources are loaded from cheapest to dearest until the demand is met, within the constraints. Ties keep plant order. A price needed by a source of the plant and missing in `problem.assumptions` is `missing_value`.
- Put the sample problems' prices in their `problem.json` (section 6); list every number that changes against the baseline and why.
- Tests: hourly and daily demand; a site conflict; a missing price; dispatch order follows the prices (swap two prices, the order swaps).

## 4. evaluate and optim take the problem (subagent B)

- **Signatures:** every `evaluate` function is `f(plant, problem, results, ...)`, or `f(plant, problem)` when it needs no run (`capex`). Every `optim` function is `f(plant, problem, ...)`; remove `profile`, `rules` and `assumptions` arguments.
- **`gm.evaluate.constraints(plant, problem, results)`**: checks every constraint of the problem; per match `path`, `passed` (`None` when the field is not in the results), `value`, `limit`, `worst_step`. It replaces `Limits`, `limits` and `operating_time` (remove them). `run_all` includes it.
- Stubs: `capacities`, `report`, `compare`, `optim.size`, `optim.sensitivity`.
- Tests: every `over` kind, `when="running"`, a parameter path, a missing field.

## 5. The run needs no compiler (subagent C)

- Nothing in `modules`, `plants`, `physics`, `ops`, `runtime`, `engine`, `run`, `types`, `units`, `errors`, `_utils` imports `compiler` (today `engine/engine.py`, `engine/outcome.py`, `engine/run.py`, `modules/module.py`, `ops/dispatch.py` import `graph`).
- `engine` exposes an executor interface and `register_executor`; `ops` keeps `register_backend`. `compiler/__init__` registers its graph executor when imported. `gm.compiler.compile(plant)` returns a compiled executor.
- The eager runner runs `forward` on arrays over the whole run (numpy kernels), and step by step only for modules with state or a loop.
- **Speed check:** time the competition year eager and with the compiler. If eager is more than 3 times slower than today, keep the default fast: `gemini/__init__` imports `compiler` last so it registers itself, and `simulate(..., compile=False)` forces eager. Report both times. The dependency rule holds either way.
- Tests: the run modules import and simulate a small plant with `compiler` blocked from import; eager and compiled give the same numbers.

## 6. Data and the sample problems (subagent D)

- `gm.Problem.from_json(path)` / `problem.to_json(path)`: a `problem.json` with the demand in a CSV next to it (in `run/`, built here by D on top of section 2).
- Convert each sample folder (`hackathon_2027`, `shallow_district`) to `problem.json` + demand CSV: demand, site (the site values now in `plant.json`), constraints (from `rules.json` and `limits.json`), assumptions with prices (from `assumptions.json`; cite the source of each price in the folder README, none from gemini code). `plant.json` keeps only design values. Remove `rules.json` and `limits.json`.
- Stub: `gm.data.synthesize`.

## 7. Public API, guards, examples, docs

- **`gemini/__init__`** exports exactly: `Module`, `Plant`, `Parameter`, `Inlet`, `Outlet`, `Output`, `Stream`, `Fluid`, `BRINE`, `WATER`, `Problem`, `Constraint`, `Assumptions`, `schedule`, `simulate`, `replay`, `live`, `resume`, `call`, `Results`, `Dataset`, `Engine`, and the folders `modules`, `plants`, `physics`, `ops`, `runtime`, `units`, `errors`, `data`, `optim`, `evaluate`, `analysis`, `compiler`. Anything else from today's top level moves under its folder; list each in the report.
- `gm.plants.capabilities()`: stub.
- **Read/write rule everywhere:** apply the naming rule of section 0 to every reader and writer in `gemini/`. At least: `gm.plants.from_dict` → `gm.Plant.from_dict` (builds any plant class or a class-less plant), plus `Plant.from_json` / `to_json`; `Results.to_bytes` / `from_bytes` stay; the dataset loader → `Dataset.from_<format>`; the legacy project reader → `gm.Plant.from_legacy` (or the name the rule gives; say which); any `read_*`, `write_*`, `load_*`, `save_*`, `parse_*`, `dump_*`. List each rename. Add a quality test that rejects those prefixes in public names.
- **Quality tests** (`test_code_quality.py`):
  - the run folders of section 5 import none of `compiler`, `data`, `optim`, `evaluate`, `analysis`;
  - `modules` never imports `plants`;
  - no folder named `core`, `base`, `testing`, `backends`, `checks`, `economics`, `profiles` under `gemini/`;
  - a snapshot of `gm.__all__` and of each folder's `__all__`.
- **Examples:** rewrite every example to the new API. The competition example is the short form:
  ```python
  problem = gm.Problem.from_json("inputs/examples/hackathon_2027/problem.json")
  plant = gm.Plant.from_json("inputs/examples/hackathon_2027/plant.json")
  results = gm.simulate(plant, problem)
  print(gm.evaluate.totals(plant, problem, results), gm.evaluate.constraints(plant, problem, results))
  ```
- **Docs:** `api.md` (every moved, removed and new name, unreleased changes), `architecture` / `engine.md` (the tree, the dependency rules, eager and compiler), `data.md` (`problem.json`, `from_*` / `to_*`), `plants.md`, `testing.md`, `conventions.md` (the import rules, `(plant, problem)` signatures, the read/write naming rule as a standing coding rule), the Claude coding rules in `AGENTS.md` and `.claude/docs/` (the read/write rule, so every future session follows it), `AGENTS.md` "Start here", README, every docstring touched.

## 8. Report

- Commits, one per section, and the pushed hash.
- The final tree, and every old public name with its new place or "removed".
- Numbers of both sample problems before and after, and every change with its reason.
- Eager and compiled times of the competition year, and which default you kept.
- Stubs created.
- What this breaks in `geomind/` and `backend/` (read-only, file and line).
