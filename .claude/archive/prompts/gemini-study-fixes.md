# Task: what an agent needs from gemini: study fixes, uncertainty in the case, readable reports, failure diagnosis, self-describing plants, and a fast study

## 0. Context and rules

- This is a new session. Read `AGENTS.md` and every file in `.claude/docs/` first and follow them (start with `api.md`, `conventions.md`, `testing.md`, `engine.md`).
- Repository: `/Users/sahand/Desktop/geomind-spe-geohackathon-2026/gemini`. If `git remote get-url origin` is not `git@github.com:geomind-spe-geohackathon-2026/gemini.git`, run `git remote set-url origin git@github.com:geomind-spe-geohackathon-2026/gemini.git`. Then `git fetch --prune`, `git checkout dev`, `git pull origin dev` (expected `b8d0282` or later), `git status` clean.
- **Branch:** `git checkout -b feature/study` from `dev`. Commit there, one commit per section. At the end, if the development tests and the e2e tier pass: merge `feature/study` into `dev` with `--no-ff`, push `origin dev`, delete `feature/study` locally and on `origin` (the branch rule in `AGENTS.md`). No other session works in this repository now.
- **The rule (most important):** gemini is a general geothermal heating and cooling package. The competition case (`inputs/examples/hackathon_2026/`) is only a test sample; nothing in `gemini/` may be named after it or tuned to it.
- **Standing rules:** `(plant, case)` signatures; one unit format (`Quantity`, SI inside); no default for anything a user must decide (design values, assumptions, policies); `from_<format>` / `to_<format>`; update the code, never wrap it (no wrappers, shims, aliases or fallbacks to old names); no comments inside code (docstrings only); quality bar of `conventions.md`; a failing test before each bug fix.
- **gemini is the source of truth.** Agents (such as geomind), the backend and the frontend are built on gemini's public API and adapt to it; every capability here is designed as the right general feature of gemini, never shaped after one caller or after the competition. The goal is a lasting contribution to the GEMINI project.
- **What an agent needs (why this task):** an agent drives gemini only through public names and JSON. It must be able to: load a case; list plant types and what each can do; find every parameter a plant still needs, with its quantity, unit and meaning; size a plant to a feasible starting design or learn exactly why not; search, sample and compare; read results in readable units; learn why steps failed; and get every result as JSON.
- **The case is read-only.** It is built once and never changed; a study that varies a value of the case works on a temporary copy per trial.
- **Temporary files** go to `.tmp/study/` (git-ignored).

### You are the coordinator

Run the work in parallel and do not spend your own context doing it. You plan, hand out tasks, review short reports and diffs, decide, merge onto `feature/study`, and run the tests once. You never edit more than a few lines yourself and never read large files whole.

- Workers are subagents on sonnet; read-only searches use haiku. Each works in its own git worktree under `../gemini-study-tmp/` on a local branch `study-<letter>` from `feature/study` (never pushed), owns the files listed for it, commits once, runs only the tests of its files, and answers in at most 20 lines. Details go to `.tmp/study/<worker>.md`.
- Phase 1, in parallel: **A** (section 1), **B** (section 2), **C** (section 3), **D** (section 4), **F** (section 6), **H** (section 7). Phase 2, after you merge phase 1: **E** (section 5, speed), so it measures the final behaviour, and **I** (section 8) in parallel with it (disjoint files). Phase 3: **G** (section 9, examples and docs).
- An overlap between workers goes back to its owner. Remove your worktrees and `study-*` branches at the end.

### Tests

- Development profile only (`make test` / `scripts/test_changed.py`, with `test_code_quality.py`), parallel, under 300 s. New tests under about 1 s each, on small plants and short cases, never on the competition year. Never run the slow dataset locally. Never delete or shrink goldens; regenerate a golden only where a section changes behaviour on purpose, and list it.
- A 1 s budget test that fails under load is rerun alone before it counts (section 6 should make this rare); say which tests you retimed.
- Run `examples/hackathon.py` at most twice in the whole task (once after phase 2, once in phase 3), never two at a time; iterate on short scripts in `.tmp/study/`.

## 1. Pumps at depth (worker A)

Owns `gemini/modules/pumps/esp.py`, `gemini/modules/pumps/injectionpump.py`, the pump physics they call, and their tests.

- **ESP outside its curve:** today the power curve extrapolates (3.7e13 W at 3443 m depth on the competition case). A row whose flow or head is outside the range the curve is valid for must be a failed row with an explicit `gm.errors` code (for example `out_of_range`, with the path, the value and the valid range), never a number. The valid range comes from the pump's own parameters (flow window and the curve), not from a constant.
- **Injection pump with negative head:** from about 3000 m the required injection head is negative and the module raises. A negative required head means no pumping is needed: pump power 0, the outlet pressure is the inlet pressure, and an output (for example `is_pumping`) says so. Positive head behaves as today.
- Tests: an ESP row outside its curve fails with the code; an injection pump with negative head gives zero power and no error; numbers unchanged inside the valid range.

## 2. Sizing: backup policy, pump ratings, a feasible start (worker B)

Owns `gemini/study/size.py` and its tests.

- Today `size` always gives the boiler the whole heating peak (so it covers a doublet outage). That is a design policy, not physics, so it must be an argument the caller sets, with no default, for example `size(plant, case, backup=...)` with values such as `"none"` (top-up units cover only the share the doublets cannot reach) and `"peak"` (top-up units cover the whole peak with the doublets off). Pick clear names, document each in the docstring, raise `missing_value` if it is not given.
- **Pumps rated for their duty:** today `size` rates the production pump below its peak flow (on the competition case: capacity 0.0576 m3/s, peak 0.0833 m3/s, share 1.45 in `gm.evaluate.capacities`), so its capex is understated. Every pump `size` rates (production and injection) gets the capacity of the largest duty the case allows it (the flow limit of the case's constraints for its role, else the plant's nominal flow), so `share <= 1` on the sized plant. Same check for every other unit `size` rates.
- **Feasible start or a clear reason:** `size` simulates the sized plant once on the case and returns it with a list of notes: each constraint the sized design breaks (role, quantity, value, limit, worst step) and each unit left unsized. Today a sized `HeatingFullCoolingPlant` breaks the cooling supply temperature by 3 mK (293.1532 K against 293.15 K) on its peak day; find whether that is a sizing margin (the chiller rated exactly at the peak with no approach margin) or a solver tolerance, and fix the cause, generally. `size` never hides an infeasible start.
- The heat pump share formula stays (peak × (T_supply − T_reservoir) / (T_supply − T_return)); its docstring says it assumes an ideal exchanger.
- Update every caller in `examples/` and `tests/` to pass the policy explicitly; the competition example uses `"peak"` so its numbers stay as today.
- Tests: `"none"` gives a smaller boiler than `"peak"` on a small case; missing policy raises.

## 3. `Comparison` values are `Quantity`, readable report (worker C)

Owns `gemini/evaluate/compare.py`, `gemini/evaluate/_utils/display.py`, and their tests.

- The values inside `Comparison` entries are `gm.units.Quantity` in SI (the unit rule); `to_frame(units=None)` keeps its display units and column names (`lcts [EUR/MWh]`).
- **Readable report:** `Report.to_dict(units=None)` and the report's printed form use the same display table as `to_frame` (LCTS in EUR/MWh, CO2 in t or kt, energy in MWh or GWh, power in MW, flow in m3/h, temperature in °C), or the units given as `{metric: unit}`; values inside the report stay SI. One display table in `gemini/evaluate/`, never a second one. (C also owns `gemini/evaluate/report.py` for this.)
- Tests: a value is a `Quantity` with the right unit; `to_frame` unchanged; `report.to_dict(units=...)` with default and given units.

## 4. Uncertainty declared in the case (worker D)

Owns `gemini/case/` (fields, sections, schema), `gemini/study/sample.py`, `gemini/study/sensitivity.py`, `docs/schemas/` for the case, `inputs/examples/*/case.json`, and their tests.

- **Format.** Any numeric value under `environment` or `assumptions` may carry an `uncertainty` next to its value, in the value's unit:
  ```json
  "electricity": {"value": 0.10575, "unit": "EUR/kWh",
    "uncertainty": {"kind": "uniform", "min": 0.08, "max": 0.14}},
  "permeability": {"value": 200, "unit": "mD",
    "uncertainty": {"kind": "triangular", "min": 100, "max": 400}},
  "discount_rate": {"value": 0.06,
    "uncertainty": {"kind": "normal", "std": 0.01, "min": 0.02, "max": 0.10}}
  ```
  - `kind` is required, one of `uniform` (needs `min`, `max`), `triangular` (mode is `value`, needs `min`, `max`), `normal` (mean is `value`, needs `std`; `min`/`max` optional, truncating).
  - `value` must lie inside `[min, max]`; an unknown key or a missing required key is an error naming the path; units are converted to SI like the value.
  - `time`, `demand`, `choices` and `constraints` cannot carry uncertainty (error if they do).
  - The case stays frozen; a normal run, `size` and `minimize` use only `value`.
- **`sample`** reads its distributions only from the case: `gm.study.sample(plant, case, metrics, count, seed)`. Each draw is a temporary copy of the case with the drawn values. Remove the `distributions` argument (update the code, never wrap it). Plant parameters are not sampled (they are design decisions, searched by `minimize`). A case with no `uncertainty` raises a clear error.
- **`sensitivity`** uses the same declarations: each uncertain value at its `min` and `max` (for `normal` without bounds: `value ± std`), one at a time. Remove any argument that duplicated this.
- Add uncertainty to a few values in `inputs/examples/hackathon_2026/case.json` (electricity, gas and CO2 prices, permeability, reservoir temperature gradient or temperature, discount rate) with ranges stated in its README as assumptions.
- Tests: parsing and validation of each kind and each error; `sample` draws only declared values and leaves the case unchanged; `sensitivity` uses the declared bounds.

## 5. Fast study (worker E, after phase 1 is merged)

Owns `gemini/study/_utils/` (trial, target, resize), `gemini/run/` (case application), the cost and LCTS functions in `gemini/evaluate/` other than `compare.py` and `display.py`, the structural-parameter handling of the plants that set the ESP depth and the pipe path, and `scripts/bench*.py`. Do not change `gemini/engine/`, `gemini/compiler/`, `gemini/ops/` except to remove a cache that becomes unused.

- **Goal:** one trial of `minimize`, `sample` or `sensitivity` costs at most about 2 × one `gm.simulate` of the same plant and case. Today a trial costs about 1.5 s against about 0.2 to 0.4 s for the simulation.
- Known causes (measured by the speed task; confirm with `cProfile` on a 20-trial study first, write the profile summary to `.tmp/study/profile.md`):
  - the LCTS and report path builds a pandas frame per trial (about 23 % of study time): compute the metrics from the result arrays directly;
  - applying the case to the plant per trial (about 23 %): apply the case once per study and set only the values a trial changes;
  - the ESP depth and the pipe path are structural, so the compiled graph is rebuilt per trial (about 20 %): make them ordinary numeric parameters so one graph serves every trial of a study;
  - `Module._executor_cache` is unused: remove it or use it.
- **Parallel trials:** trials of a study are independent; run them in parallel processes when the caller asks, with the number of processes set through `gm.runtime.settings(...)` like the backend. Results must be identical to a serial run (same order, same numbers).
- **Numbers equal:** every study result of the examples equal to the phase-1 merge at 1e-9 (keep a baseline in `.tmp/study/`), except where a trial was previously retraced and now is not (must still be 1e-9).
- Report: per-trial time before and after (median of 5 with `uptime`), `uncertainty.py` and `hackathon.py` times.

## 6. Budget tests that do not fail under load, and `CONTRIBUTING.md` (worker F)

Owns the test-budget plugin or fixture in `tests/` (`conftest.py` or the file that enforces the 1 s budget), `.claude/docs/testing.md` (only the budget part), `CONTRIBUTING.md`.

- Every full development run fails 10 to 15 tests on the 1 s budget under load, and they pass alone. Measure the budget on the process CPU time of the test (`time.process_time`), not wall time, so other processes do not count; keep the 1 s limit. If a test spawns processes or threads whose time would be missed, say so and count them.
- A test of the plugin: a test that sleeps does not fail the budget; a test that burns CPU over the limit does.
- `CONTRIBUTING.md` lines that say to branch from `main`: follow the branch rule of `AGENTS.md` (`dev`, `feature/`, `fix/`, `docs/`).

## 7. Why steps failed, JSON results, only the real design in the API (worker H)

Owns a new `gemini/evaluate/failures.py`, the removals below (and their callers, coordinated with the other owners), the result types of `gemini/study/` (`minimize`, `sample`, `sensitivity` results; not their algorithms), and their tests.

- **Failure diagnosis:** `gm.evaluate.failures(results)` groups the failed and skipped rows of a run by module path and error code: count, first and last step, one example message, and the inputs that most often go with it if the row record has them. Sorted by count. `to_dict()` and `to_frame()`. `gm.evaluate.report` includes it (empty when nothing failed).
- **Every result is JSON:** the results of `minimize`, `sample`, `sensitivity`, `compare` and `report` each have `to_dict()` that `json.dumps` accepts with no custom encoder (plants as their `to_dict()`, quantities as `{"value", "unit"}`), and `from_dict()` where a caller needs to read one back. A test dumps each to JSON.
- **Only the real design in the public API.** Remove every public name that is not part of gemini's design, update every caller in `gemini/`, `examples/`, `tests/` and the docs, and keep no alias or fallback; outside callers (geomind, backend) move to the new way themselves, from the old -> new table of the report.
  - Stubs that only raise `NotImplementedYet`: today `gm.plants.example`, `gm.data.synthesize`, `gm.analysis.injectivity`, `calibrate_pump`, `calibrate_corrosion`, `erosion`. Remove them; a feature is added to the public API when it is built. Keep the list of removed planned features in `.claude/docs/refactor-notes.md` so they are not forgotten.
  - A starting plant comes from a stored plant JSON or a plant class plus its missing parameters (section 8).
  - First let a haiku search list every other public name (`gm.__all__` and each subpackage's `__all__`, public methods of `Plant`, `Case`, `Results`) that looks like a leftover: legacy converters (for example `Plant.from_legacy`, `Case.from_orm`, `gemini/plants/_utils/legacy/`), old-format fields, compatibility paths. Write the list with the reason for each to `.tmp/study/leftovers.md`; remove the ones that are clearly not in the design, and list the doubtful ones in the report for the user to decide.
- Tests: failures on a small run with two injected failing modules; JSON round trip of each result.

## 8. Plants that describe what they need (worker I, phase 2)

Owns the `description` of `Parameter`, `Control`, `Boundary`, `Output` declarations across `gemini/modules/` and `gemini/plants/` (text only, no behaviour change), `Module.describe` and `Module.missing_parameters`, and their tests. Do not change physics or signatures.

- An agent builds a plant from a class and must know what to fill: `plant.missing_parameters()` returns, for each parameter still unset, its path, quantity, the units it accepts, bounds, and a one-line description of its meaning. Today `describe()` returns `"description": null` for parameters (for example `HeatingCoolingPlant.depth`), and `HeatingPlant()` then `size` fails with `d0.esp.stage_count: parameter is uninitialized` and no hint of what it is.
- Give every declaration a short description (from the existing docstrings where they exist; physical meaning, not a default). A quality test fails on any public declaration without one.
- A missing-parameter error from `size`, `simulate` or `validate` lists every missing path with its description, all at once (not the first one only).
- Tests: `missing_parameters()` on a bare plant class lists every required path with a description; the error lists all of them.

## 9. Examples and docs (worker G, phase 3)

- `examples/uncertainty.py` uses the case's uncertainty only; `examples/hackathon.py` passes the backup policy, and shows sampling from the case after the comparison; `examples/costs.py` unchanged in behaviour.
- `examples/hackathon.py` with `EVALUATIONS = 20`: report its runtime (target under 120 s) and its table (feasible, reasons, LCTS, CO2, Pareto front).
- `examples/plant.py` shows building a plant from a class with `missing_parameters()`, filling it, `size` with its notes, and `gm.evaluate.failures`.
- Docs: `api.md` (contract table: `missing_parameters()`, `gm.evaluate.failures`, `to_dict()` of every result, `report.to_dict(units=...)`, `plants.example` removed, `size(..., backup=...)`, `sample(plant, case, metrics, count, seed)`, `sensitivity` from the case, `Comparison` with `Quantity`, the case's `uncertainty` format; "unreleased changes"), `engine.md` (one compiled graph per study, parallel trials), `testing.md` (CPU budget), `conventions.md` only if a rule changed. Every docstring touched.

## 10. Report (at most 50 lines)

- Commits, the merge into `dev`, the pushed hash; `feature/study` and your worktrees removed.
- Section 1: rows that now fail at depth on the competition case, and what `minimize` picks.
- Section 2: the policy names and the competition numbers with `"peak"` (same as before) and `"none"`.
- Section 4: the format as built, and an example `sample` result on the competition case.
- Section 5: per-trial time before and after, the profile summary, the 1e-9 check, `uncertainty.py` and `hackathon.py` times.
- Section 6: tests that still needed a rerun.
- Section 2: pump shares after the fix, `size` notes on the competition case, and the cause of the 3 mK miss.
- Sections 7 and 8: `failures` on the competition case (if any), the JSON check, and the count of declarations that got a description.
- Every public change that geomind or the backend must follow, as an old -> new table.
- Anything you could not do, with the reason.
