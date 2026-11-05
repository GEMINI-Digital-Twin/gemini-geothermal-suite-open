# Task: tidy the package folders, then pure `forward` / `update` for every module, time as a `scan`, state connections, batched trials for speed, and the open bugs

## 0. Context and rules

- This is a new session. Read `AGENTS.md` and every file in `.claude/docs/` first and follow them (start with `api.md`, `conventions.md`, `testing.md`, `engine.md`, `inputs.md`).
- **Run this only after `feature/inputs` is merged into `dev`** (it moves inputs and touches every module's declarations). If `.claude/docs/inputs.md` does not exist on `origin/dev` yet (`git fetch origin dev` then `git cat-file -e origin/dev:.claude/docs/inputs.md`), another session is probably still finishing it: wait, checking every 5 minutes for up to 6 hours, and start as soon as it appears. Never start on top of an unmerged branch. If it never appears, stop and say so.

### Unattended run: questions only at the start

The person who started this is asleep and cannot answer during the run.

- **Before any work** (right after reading the docs and the inventory of section 1), ask every question you have in one message, all at once, numbered, each with your proposed answer. Then wait at most 15 minutes. If no answer comes, go on with your proposed answers.
- **After that, never ask, never wait, never stop for a decision.** When something is unclear, choose the option that fits `AGENTS.md`, `.claude/docs/` and the standing rules best, write it to `.tmp/forward/decisions.md` (the question, the options, the choice, the reason), and continue. Every such choice is listed in the report.
- A failing test, a worker that fails, or a number that differs is work to fix, not a reason to stop: find the cause, fix it, or (only if it truly cannot be done in this task) record it in the report and continue with the rest. Never leave `dev` broken: merge into `dev` only when the development tests and the e2e tier pass; if they do not by the end, push `feature/forward-scan` to `origin` instead and say so.
- Do not run commands that need an interactive answer (no `-i`, no editors, no prompts); pass flags that make them non-interactive.
- Repository: `/Users/sahand/Desktop/geomind-spe-geohackathon-2026/gemini`, remote `git@github.com:geomind-spe-geohackathon-2026/gemini.git`. **Another session may still be working in that folder** (feature/inputs): never run `checkout`, `pull`, `reset`, `stash` or any command that changes its working tree or branch; only `git fetch`. Once `origin/dev` has `.claude/docs/inputs.md`, create your own worktree: `git worktree add ../gemini-forward -b feature/forward-scan origin/dev` and do all work there (worker worktrees under `../gemini-forward-tmp/`).
- **Branch:** `feature/forward-scan` (the worktree above), one commit per section. At the end, if the development tests and the e2e tier pass: `git fetch origin dev`; if `origin/dev` moved, merge it into `feature/forward-scan` first and rerun the tests; then merge from your worktree without touching the main folder: `git checkout -b merge-forward origin/dev`, `git merge --no-ff feature/forward-scan`, `git push origin merge-forward:dev`; delete `merge-forward`, `feature/forward-scan` and remove `../gemini-forward` and every worker worktree.
- **gemini is the source of truth** and general; nothing is shaped after one caller or after the competition sample. Do not look at, mention or adapt to any other repository.
- **Standing rules:** one unit format (`Quantity` at the public boundary, SI inside); no defaults for anything a user decides; `from_<format>` / `to_<format>`; update the code, never wrap it (no shims, aliases, compatibility paths for the old module style); only the real design in the public API (no stubs; remove every remaining `NotImplementedYet` this task makes possible); no comments inside code (docstrings only); quality bar of `conventions.md`; a failing test before each bug fix.
- **The compiler stays separate and optional**, like `torch.compile`: the core (modules, plants, engine) never imports `gemini/compiler/` and runs fully eager on its own; the core is written so the compiler can trace it (no structural `None`, no Python branching on values that change per step where an array form exists).
- **Numbers do not change:** every example, the e2e tier and the goldens give the same numbers to 1e-9, eager and compiled. A difference is a bug to find, never a golden to regenerate.
- **Temporary files** go to `.tmp/forward/` (git-ignored).

### The design (agreed)

Today modules write their outputs onto `self` during `forward`, read time-varying inputs from `self`, and keep state inside the object. That makes a module impure: two trials cannot share one plant object, the compiler has to work around hidden writes, and time cannot be expressed as one scan.

- **Every module:** `forward(self, inputs, inlets, state) -> (outputs, outlets)`. Pure: it writes nothing to `self`; outputs are returned; time-varying inputs (controls, boundaries, setpoints, measurements, frequency) arrive in `inputs`, never read from `self`. `self` holds only parameters, set before a run and fixed during it.
- **Stateful modules only:** `update(self, inputs, inlets, outlets, state, dt) -> state`, pure, returning the next state. Today's private state-advance code becomes this. A stateless module has `state = {}` and no `update`.
- **State is declared** (`State(...)` with its quantity and description, like a parameter) and has **no default**: the initial state of every stateful module comes from the case's `initial_state` (see `inputs.md`); a missing one is a `check` issue.
- **No structural `None`:** for example a PID's "no previous step" is a value (`previous_step = 0` meaning none yet), not `None`, so the compiler can trace it (today the PID is a graph break).
- **Declared keys are enforced:** a `forward` or `update` returning a missing or an extra key is an error naming the module and the key.
- **The plant implements `forward` and `update` once** for any graph (users never write a plant's `forward`); the plant's state is the nested dict of its children's states. `Plant` stays a subclass of `Module`.
- **Time is a scan:** the engine runs `state[t+1] = update(..., state[t], dt)` with `forward` inside each step. Stateless plants keep today's fast path (all steps as arrays at once, masked fixed-point loops). Stateful plants scan in time.
- **State connections** (a state or a delayed value fed back as an input; today `NotImplementedYet` in the plan compiler) are implemented on top of the scan.
- **Batched trials:** because modules are pure and parameters are the only thing on `self`, many trials (different parameter sets, or different sampled case values) can run as one array pass with a leading batch axis, sharing one plant object, each with its own state. `minimize`, `sample` and `sensitivity` use it; no deep copies per trial.

### You are the coordinator

Run the work in parallel and do not spend your own context doing it. This task is long; your context must last to the end.

- **You do none of the work yourself, in any phase**, including the inventory, the baseline and the test runs: each is a subagent. You plan, hand out tasks, read short reports, decide, merge onto `feature/forward-scan`, and start one test worker per phase. You never edit more than a few lines, never read a source file, a diff or a log whole; ask a worker for the part you need.
- **One worker per job, fresh context each:** a big section is split into several workers one after another (for example S1 to S4 below) rather than one worker that fills up.
- **State file:** after every phase write `.tmp/forward/state.md` (phase done, commits, open items, decisions so far, next step). If your context is compacted or the session restarts, read it first and continue from there.

- Workers are subagents on sonnet; read-only searches use haiku. Each works in its own git worktree under `../gemini-forward-tmp/` on a local branch `forward-<letter>` (never pushed), owns the files listed for it, commits once, runs only the tests of its files, and answers in at most 20 lines. Details go to `.tmp/forward/<worker>.md`.
- Order (the person's): folders, then the module contract, then scan and speed, then bugs. **Phase 0:** section 1 (inventory and baseline). **Phase 1:** S1, S2, S3, S4 one after another (section 1b, folders; they move files, so nothing runs beside them). **Phase 2:** A (section 2). **Phase 3, in parallel:** B, C, D, E (section 3, modules by folder). **Phase 4, in parallel:** F (section 4, eager scan and state connections, plus bug 1 of section 6b), G (section 5, compiler), J (section 6b, bugs 2 to 5). **Phase 5:** H (section 6, batched trials in the study). **Phase 6:** I (section 7, docs and API).
- An overlap between workers goes back to its owner. Remove your worktrees and `forward-*` branches at the end.

### Tests

- Development profile only (`make test` / `scripts/test_changed.py`, with `test_code_quality.py`), parallel, under 300 s. New tests under about 1 s each, on small plants and short cases. Never run the slow dataset. Never delete or shrink goldens.
- A budget test that fails under load is rerun alone before it counts; name the tests you retimed.
- Run `examples/hackathon.py` at most twice (baseline in phase 0, final), never two at a time.

## 1. Inventory and baseline (phase 0: a haiku worker for the inventory, a sonnet worker for the baseline)

- List into `.tmp/forward/inventory.md`, per module: every attribute written to `self` inside `forward` or helpers it calls; every time-varying value read from `self`; every state it keeps and how it advances; every `None` used as a structural marker; every override of `forward` in a plant class. Count them; this is the work list.
- Baseline, saved to `.tmp/forward/baseline.npz` and `.tmp/forward/baseline.md`: results of every example and the e2e tier (for the 1e-9 comparison), and timings (median of 3, no other load): one daily year eager and compiled for every sample plant, one hourly year for the smallest sample, one `minimize` with 20 evaluations, one `sample` with 50 draws, the full `examples/hackathon.py`.

## 1b. Package folders (workers S1 to S4, phase 1, one after another)

Goal: a folder layout where every folder has a reason a reviewer can check, written down, and enforced by a test. Moves only: no behaviour change, numbers equal to 1e-9, every public name (`gm.X`, `gm.<folder>.X`) the same unless a rule below says otherwise.

**Rules** (write them into a new `.claude/docs/structure.md`, each with its reason, and link it from `AGENTS.md`):

- **R1 A folder exists only if both hold:** it is a domain a user addresses by name (`gm.study.minimize`, `gm.case.Case`), and it has several files with separate responsibilities. Otherwise it is one file (`gemini/runtime.py` still gives `gm.runtime.settings`). Reason: a folder is a promise of a domain; a folder with one idea in it costs a hop to read and says nothing.
- **R2 The folder name is the word the user says** (the `gm.<name>` namespace), never an implementation word (`utils`, `helpers`, `core`, `base`, `common`, `misc`).
- **R3 Private helpers live next to their only user:** `<folder>/_utils/` or a `_name.py` file; a top-level `gemini/_utils/` holds only helpers used by two or more folders.
- **R4 One direction of imports:** `units`, `errors`, `_utils` -> `ops` -> `physics` -> `streams` -> `modules` -> `plants` -> `engine` -> `evaluate` -> `study`; `case` is read by `engine`, `evaluate`, `study`; `analysis` sits on top; nothing imports `compiler`; `compiler` may import everything above it. A quality test checks this from the real imports (extend the existing one if there is one).
- **R5 A file belongs where its inputs belong:** code that reads or builds case inputs (series from CSV, synthetic profiles) is part of `case`; code that runs time is `engine`; code that judges results is `evaluate`. Reason: P1 of `inputs.md`, one owner, one place.
- **R6 Tests and docs mirror the package:** `tests/unit/<folder>/`, one docs page per public folder.
- **R7 No compatibility paths:** a move updates every import in the repo (package, tests, examples, docs); no re-export left at the old place.

**Definition of every folder.** Each folder is defined by what it takes, what it gives back, and what it may call. A file goes to the one folder whose definition it meets; if it meets two, it is two files. Write this table into `structure.md` with the reason column, and make the import-direction test (R4) check the "may call" column.

| folder | takes | gives | may call | never | reason it is separate |
| --- | --- | --- | --- | --- | --- |
| `units` | a number with a unit | SI number, or display `Quantity` | nothing in gemini | knows any equipment | one unit format at every boundary needs one owner |
| `errors` | an issue | exception and issue types | nothing | decides anything | every folder reports problems the same way |
| `ops` | numbers or arrays | numbers or arrays | `units` | knows a physical meaning | the same math runs on scalars, arrays and the compiler's backends |
| `physics` | physical states (T, p, composition) | properties and correlations | `ops`, `units` | holds parameters or state; knows a module | a correlation is true for any equipment that uses it |
| `streams` | fluid composition and state | `Stream`, `Fluid`, ports | `physics`, `units` | knows a module | what flows between modules is one type for every module |
| `modules` | parameters, inputs, inlets, state | outputs, outlets, next state, for one step | `physics`, `ops` | loops over time; reads a case | one piece of equipment, testable alone with `gm.call` |
| `plants` | modules and connections | one module (a `Plant`) and its plan | `modules` | loops over time | a plant is a module, its plan is built once |
| `case` | files or values written before any plant exists | `Case`, economics, requirements, series | `units`, `errors` | runs or judges a plant | the outside world and its rules change without the plant (P2 of `inputs.md`) |
| `engine` | one plant, one case | one run: results over time | `plants`, `case` | judges, repeats runs, chooses | time is handled in one place (schedule, scan) |
| `evaluate` | plant, case, results of one run | numbers and judgement: report, verdict, metrics, compare | `case`, `units` | runs the plant | judging must not change what was computed; it can be redone on saved results |
| `study` | plants and cases plus a method | many runs and a choice (best, samples, sensitivities, fitted parameters) | `engine`, `evaluate` | changes the physics | a question answered only by running the whole system many times |
| `analysis` | one module and a set of fixed conditions | curves or operating points (nodal, injectivity, pump curve) | `modules` via `gm.call` | runs the engine; uses time or a case | engineering questions about one piece of equipment, answered without a plant or a year |
| `runtime` | how to run (processes, batch size, backend, precision, display units) | settings | nothing | changes a result value | it changes speed or display only, so it is not an input (P4 of `inputs.md`) |
| `compiler` | a plant and a case | a faster runner with results equal to eager | everything above | is imported by any of them | optional, like `torch.compile` |

**Study and analysis, the test:** a function that calls the engine (a run over time on a case) is `study`; a function that calls one module at fixed conditions, with no time and no case, is `analysis`. So `calibrate` (fit plant parameters to measured series by running the plant) is `study`; nodal analysis (where the well curve meets the pump curve) is `analysis`; corrosion and erosion computed from the results of a run are `evaluate`, and their rate correlations are `physics`.

**Work list:** Appendix B is a review of every file of `gemini/` on `dev` 061fbe9 (31 items, layer by layer, each with the evidence, the rule it breaks and the proposed fix). Re-check each item on the current `dev` (feature/inputs may have changed it), then apply it. An item that turns out wrong is skipped with the reason in `decisions.md`. Split by layer: **S1** items 1-6, 8-10 (units, errors, types, _utils, ops, physics); **S2** items 11, 12, 14-18 (modules, plants); **S3** items 19-25 (run, engine, compiler); **S4** items 26-31 (case, evaluate, study, analysis, the top-level `inputs/` folder). Items 7 and 13 go to the module workers (sections 2 and 3), because they change the same code.

**Expected tree** (the rules decide where the real tree differs; log every such choice):

```
gemini/
  __init__.py        public top names
  runtime.py         settings (processes, batch size, backend, precision, display units); was runtime/
  units/             Quantity, conversions, display table (takes types/quantities.py, types/bare.py, evaluate display)
  errors/            error classes, issues, return shapes (takes types/shapes.py)
  _utils/            only helpers shared by two or more folders
  ops/               math API, dispatch, kernels, scan
  physics/           correlations and fluid properties only (costs, dispatch, doublet design, diagnostics leave)
  streams/           Stream, Fluid, ports, stream kinds (takes types/flows, fluid, ports, streams)
  modules/           Module, declarations, containers, results, gm.call + one folder per module domain
  plants/            Plant, templates, doublet, roles (the one owner), plant dict reader and writer, plan, loops
  case/              Case, economics, requirements, the one time-series type, synthesize (takes data/, types/profile)
  engine/            simulate, replay, live, resume, Results, schedule and its dispatch policy, runner, bindings (takes run/)
  evaluate/          costs, emissions, balances, verdict, summary (takes physics/costs, modules audits)
  study/             Study, size, minimize, sample, sensitivity, calibrate
  analysis/          one module at fixed conditions: nodal (one file), fits, integrity if it takes conditions
  compiler/          optional, imported by nothing: compile.py, trace/, ir.py, passes/, cache.py, interpret/
```

- `runtime/` becomes `runtime.py`. Remove `default_fluid` if it is still there: the fluid is a case input (`case.site.fluid`), and a runtime default breaks the no-defaults rule.
- `compiler/`: split by the job of each part, as in a compiler textbook: capture (tracer, proxy, breaks), the intermediate form (`ir.py`: `Graph` and its node kinds `op`, `fixed_point`, `scan`), transforms (`passes/`, one file per pass), caching (`cache.py`), execution (`interpret/`, one per backend), and the entry `compile.py`. Three words keep one meaning each: **plan** (the plant's module order), **bindings** (which columns feed which inputs in a run), **graph** (the compiler's traced form). Write this into `structure.md` and `engine.md`.
- Any folder kept with a single file, or any name kept that breaks R2, is listed in the report with the reason.

Output: `.tmp/forward/folders.md` (old path -> new path, rule used), one commit, every import updated, `public_api.json` unchanged except the listed changes (old -> new table in the report). Tests: the import-direction test and the full development run. Sections 2 to 7 below use the new paths; where they name an old path, use its new place.

## 2. The module contract (worker A)

Owns `gemini/modules/module.py` (and the declaration classes it uses), `gemini/plants/plant.py` (plant forward and update), and their tests.

- `forward(self, inputs, inlets, state) -> (outputs, outlets)` and `update(self, inputs, inlets, outlets, state, dt) -> state` as above; `State(...)` declarations without defaults; initial state from the case; returned keys enforced.
- The plant's `forward` / `update` written once for any graph, nested state, closed loops solved by the engine as today.
- A purity guard used by the tests: running `forward` or `update` leaves `self.__dict__` (and every child's) unchanged; a quality test applies it to every registered module.
- Appendix B item 13: split `modules/module.py` (about 1,450 lines) by job; the class stays in `module.py`, each other job gets its own named file in `modules/`.
- Tests: contract, key enforcement, purity guard, plant nested state.

## 3. Every module to the contract (workers B, C, D, E, split by folder)

Each owns a disjoint set of `gemini/modules/**` folders (split so the work is about even by the inventory counts; for example B subsurface, wells and pumps; C exchangers, heating and power; D cooling, storage and environment; E treatment, piping, grids and control), plus their tests.

- Remove every write to `self` inside `forward` and helpers; return outputs. Move every time-varying read from `self` to `inputs`. Make stateful modules declare `State` and implement `update` (today at least PID controller, thermal storage, ice storage, aquifer storage, borehole field, thermal decline; use the inventory). Replace structural `None` with values. Remove any helper that existed only to write outputs onto `self`.
- Appendix B item 7: move each `_physics.py` / `_sorption.py` / `_burner.py` correlation that holds for any equipment into `physics/` (the right topic file); keep beside the module only code that needs the module's own declarations, under a name that says what it is.
- Each module's numbers stay equal to 1e-9 on its own tests and on the e2e cases that use it.

## 4. Eager engine: time as a scan, state connections (worker F)

Owns `gemini/engine/` and the plan compiler in `gemini/plants/_utils/` (where state connections are `NotImplementedYet` today), and their tests.

- One eager runner: stateless plants keep the all-steps-as-arrays path; stateful plants scan in time; the choice is made from the plant's declared states, never from a flag.
- Implement state connections on the scan (a state or a previous-step value fed back as an input); remove the `NotImplementedYet`.
- Storage modules now run inside a normal schedule and simulation (today they cannot), with their initial state from the case.
- Speed: no per-step Python overhead that scales with the number of modules where an array form exists; profile the scan on the smallest stateful sample and remove the top costs.
- Tests: a storage plant over a short case equals a hand-stepped reference; a state connection; stateless results equal the baseline.

## 5. Compiler: a `scan` node (worker G)

Owns `gemini/compiler/` and its tests. The core does not import it.

- The traced graph gets a `scan` node for stateful plants (body = one step's `forward` + `update`), alongside today's `fixed_point` node; stateless plants compile as today. The PID and every module that was a graph break because of `None` or writes to `self` now trace.
- Tests: compiled equals eager to 1e-9 on every sample and on a storage plant; no graph breaks left on the sample plants (list any that remain and why).

## 6. Batched trials in the study (worker H)

Owns `gemini/study/` and its tests (except `Best` / `Sample` display, which is J's in section 6b).

- Trials that differ only in parameter values or sampled case values run as one batch (leading batch axis on parameters, inputs and state), sharing one plant object; no deep copy per trial. Structural changes (a different doublet count) form separate batches.
- `minimize` evaluates each generation of candidates as a batch; `sample` and `sensitivity` evaluate draws as batches; `gm.runtime.settings(processes=...)` splits batches across processes. Results per trial are identical to running each trial alone (test it).
- Batch size is a runtime setting (memory only, never results), with no hidden default: if not set, one batch per generation or per draw set.

## 6b. Open bugs (worker F for bug 1, worker J for bugs 2 to 5)

Each bug starts with a failing test that shows it, on a small plant and a short case. Fix the cause, never the symptom. If a bug turns out to be already fixed on `dev`, say so with the test that proves it and move on.

1. **A step that does not converge stops the whole run (worker F, inside the scan work).** `gm.simulate` raises `PhysicsError` on a cold reservoir (for example a 20 K/km gradient, where the brine cannot reach the demand temperature) instead of finishing. Expected: the run finishes; each step that fails is recorded as a row with its reason (no convergence, outside a module's physical bounds), its outputs marked invalid (not silently zero), and the verdict (see `inputs.md`) lists these steps under a numerical-failure kind so the plant is infeasible with a reason. `minimize`, `sample` and `compare` then treat such a plant as infeasible instead of crashing. A real programming error (wrong key, bad shape) still raises. Tests: the 20 K/km case finishes with failed rows and an infeasible verdict; a normal case has no failed rows; batched trials (section 6) where one trial fails and the others do not give the same rows as running each alone.
2. **Results of a study show bare SI (worker J).** `Best.to_dict()`, `Sample.to_dict()` and the notes written by sizing (`prepare: size`) print values in SI (W, Pa, s) while the report uses display units. Use the one display table (the same one the report uses; durations in yr for long horizons, temperature differences in K); no second table. Tests: each `to_dict` shows display units and reads back to the same values.
3. **`gm.call` returns bare SI (worker J).** Add a readable-units choice to `gm.call` that returns `Quantity` values in display units, using the same display table. It is a required argument or an explicit setting, with no hidden default (no-defaults rule); state the chosen design in `api.md`. Tests: SI and display results are equal after conversion.
4. **No quantity for co-produced gas that is burned (worker J).** A requirement cannot refer to the gas burned (for example in a flare or boiler) because no role exposes it. Add it as a role quantity with its unit, so a rule like "burned gas at most X" can be written. Tests: a plant that burns gas reports it, and a requirement on it passes and fails as expected.
5. **Budget tests fail under parallel load (worker J).** Four CPU-budget tests pass alone and fail with the full parallel run. Make them measure the code, not the machine (for example CPU time of the process, or a margin set from a measured reference in the same run), never by raising the limit until it passes or by skipping them. Tests: the full development run passes three times in a row.

## 7. Docs, API, report numbers (worker I, phase 6)

- Bug fixes in the docs: failed steps and their verdict kind in `engine.md` and `inputs.md`; the display table rule and `gm.call` units in `api.md`; the burned-gas quantity in the role table; how budget tests measure in `testing.md`.
- `.claude/docs/engine.md` (contract, scan, state connections, batches), a "Writing a module" page with two worked examples, a PID controller (stateful: `forward` + `update`) and an ESP (stateless), each shown alone and inside a plant; `inputs.md` (state declarations, `initial_state`); `api.md` contract table and "unreleased changes"; `conventions.md` (pure modules rule, purity guard).
- `structure.md` final (rules R1-R7 and the tree as built).
- `public_api.json` with its hash, `docs/schemas/` where state appears, `CHANGELOG.md` and the version per `VERSIONING.md`.
- Re-run the phase-0 timings under the same conditions; write before/after into `.tmp/forward/speed.md`.

## 8. Report (at most 40 lines)

- Commits, the merge into `dev`, the pushed hash; branch and worktrees removed.
- Inventory counts (writes to `self`, time-varying reads, stateful modules, `None` markers) before and after (all after must be 0).
- Numbers: confirmation of 1e-9 equality eager and compiled on every example and the e2e tier.
- Speed table, before and after: daily year eager and compiled per sample plant, hourly year, `minimize` 20 evaluations, `sample` 50 draws, `examples/hackathon.py`.
- Graph breaks left, if any, with the reason.
- `NotImplementedYet` left in the package (should be none).
- Tests run and retimed.
- An old -> new table of every public change (module authors' API in particular).
- Folders: old -> new table, rules applied, any folder kept against R1/R2 and why.
- Every choice from `.tmp/forward/decisions.md` (one line each).
- Bugs of section 6b: for each, the failing test, the cause found, the fix, and the test after.
- Anything not done, with the reason.

## Appendix B. Review of every file of `gemini/` (dev 061fbe9)

Read from `origin/dev` 061fbe9 (before `feature/inputs` is merged): every file of `gemini/` with its size and first docstring line. Not run. Rules referred to: R1-R7 and the folder definition table of section 1b; P1-P8 of `.claude/docs/inputs.md`.

Count: 315 files. Per folder: modules 83, evaluate 36, plants 37, compiler 21, physics 21, ops 19, case 18, engine 17, study 14, _utils 12, types 11, run 10, analysis 6, errors 3, units 2, runtime 2, data 2.

### Layer 0: units, errors, types, _utils

1. **`types/` is an implementation word (R2) and mixes five jobs.** 11 files:
   - `quantities.py` and `bare.py` (the rule "a boundary takes a quantity") are units → `units/`
   - `shapes.py` (value / problem / check returns) is errors → `errors/`
   - `flows.py`, `fluid.py`, `ports.py`, `streams.py` are what modules exchange → a `streams/` domain (`gm.Stream`, `gm.Fluid`)
   - `results.py` (per-call module results, Health) → `modules/`
   - `profile.py` (time series) → `case/`, see item 19b
   - `bindings.py` (sensor and dated-parameter metadata) → `modules/`
   - After this, `types/` is gone.
2. **`units/` has one real file today (`conversions.py`, 655 lines).** With item 1 and the display table (`evaluate/_utils/display.py`), it has three jobs: quantity, conversions, display. So it stays a folder for a real reason (R1). Otherwise it would become `units.py`.
3. **`errors/` (base, lookup)** plus `shapes.py` from types, plus the issue type from feature/inputs, is a real folder.
4. **`_utils/paths.py` names the repo's `inputs/` folder.** The package must not know where a checkout keeps its examples (P8 general), and nothing imports it. → remove.
5. **Three context-setting places:** `_utils/context.py` (generic `with` blocks), `runtime/context.py`, `ops/backend.py` (context-local backend). → one owner: `runtime.py` uses `_utils/context.py`; backend selection is a runtime setting.

### Layer 1: ops, physics

6. **`ops/control.py` is a stub** ("scan: defined only, with no backend implementation"). It is already covered: section 4 of the prompt builds it.
7. **Physics lives in two places.**
   - `physics/` has 21 files.
   - Also `modules/<folder>/_physics.py` in 7 folders, plus `_sorption.py` and `_burner.py`, about 5,000 lines.
   - Fix: one rule. A correlation that is true for any equipment goes to `physics/`. Only code that needs the module's own declarations stays beside it, and gets a name that says what it is.
8. **Not physics in `physics/`** (the definition is: physical states in, properties out, no module known):
   - `physics/costs.py` (unit cost times size) → `evaluate/`
   - `physics/dispatch.py` (which doublet runs at what for a heat need) is a control policy → with `schedule`, item 19
   - `physics/doublet.py` (child values of a doublet from its depth) knows a plant's children → `plants/`
   - `physics/diagnostics.py` (drift, health score) is monitoring → beside `engine/health.py`
9. **`physics/separation.py` docstring says "filter defaults".** This may break the no-defaults rule; check it and remove any defaults.
10. **Two fluid models.** `physics/fluid.py` ("constant fluid properties") and `types/fluid.py` ("stream composition and cached constant-property models"). P6 (one representation per concept): fluid properties go to `physics/fluid.py`; the stream composition type goes to `streams/`.

### Layer 2: modules, plants

11. **`modules/_utils/cost.py` reads the finance section of a case.** A module must never read a case (definition table). Its price belongs to `evaluate/` by kind; the module only declares its kind and rating.
12. **The plant dict lives in `modules/`.** `modules/_utils/serialization.py` ("the plant dict, format 2") → `plants/` (reader and writer are already there). Mass/energy audits in `modules/_utils/balance.py` (407 lines) → `evaluate/`, item 20.
13. **`modules/module.py` is 1,451 lines.** It holds declarations use, calling, parameters, description and validation. Split by job inside `modules/` (`module.py` keeps the class; the rest goes to named files). The forward-scan contract work touches it anyway.
14. **Roles in four places, and they contradict each other.**
    - `plants/_utils/roles.py` says roles come "from its class and its wiring" and keeps a hard-coded class → role table.
    - `run/_utils/roles.py` says "read from the wiring, not from its class".
    - Also `case/roletable.py` and `study/_utils/roles.py`.
    - Fix: one owner. Each module class declares its `kind`, and `role` is derived once in `plants/` from kind plus wiring. The other three files become users of that one place. The role table describes the plant, not the outside world, so `case/roletable.py` leaves `case/`.
15. **"Wiring" twice.** `modules/_utils/wiring.py` (observe stream identities) and `plants/_utils/wiring.py` (mixer and splitter cascades), with different meanings. Rename by meaning.
16. **`plants/_utils/` has 20 files, and some names clash with other folders.**
    - `inputs.py` (inputs of a plant by path) clashes with the new input-file module of feature/inputs.
    - `run.py` (one run of a plant's steps) clashes with `run/`.
    - `constraints.py` (solve a free value so that a target is met) is a design spec, not a requirement. Rename it `targets.py`.
    - `catalogue.py` and `capabilities.py` overlap with `_utils/registry.py`: one place lists what exists.
17. **Doublet logic in five places.**
    - `plants/doublet.py`, `plants/nodaldoublet.py`, `plants/_utils/doublets.py`, `physics/doublet.py`, `study/_utils/resize.py`.
    - Fix: everything about the doublet as equipment goes to `plants/`. The study only asks for a doublet count.
18. **Plant file names are run together** (`heatingheatpumpcoolingplant.py`). The modules folders use the same style, so it is consistent but hard to read. Decide once in `conventions.md`, either class name in lower case or snake_case, and apply it everywhere. (Lower risk: keep the style, write the rule down.)

### Layer 3: run, engine, compiler

19. **Running is split over two folders with no rule.**
    - `run/` holds simulate/replay/live/resume, schedule, Results, Dataset and the case application.
    - `engine/` holds Engine, the runner, chunks, clock, the eager executor, the binding plan, health and the archive.
    - By the definition, one plant plus one case gives one run over time, and that is one domain.
    - Fix: merge `run/` into `engine/`.
      - Public names stay at `gm.simulate` and the rest.
      - `Results` goes with the engine.
      - `Dataset` and the time series go to item 19b below.
      - `schedule` goes with its policy (`physics/dispatch.py`, `run/_utils/sources.py` marginal costs, `run/_utils/limits.py` enforced requirements) in `engine/schedule/`.
    - A design question for later: the schedule is really a supervisory controller of the plant (`control.dispatch` in the plant file), so it could become a control module. Not in this prompt.
    - **Five time-series representations (item 19b):** `types/profile.py`, `case/_utils/profile.py`, `case/_utils/demand.py`, `run/dataset.py`, plus `engine/loader.py` and `engine/columns.py` aligning them. P6 says one series type. `case/` owns series that are inputs, measurements included. The engine only aligns them to ticks.
20. **The word "evaluate" means three things.** `gm.evaluate` (judge results), `engine/evaluation.py` `Evaluation` (what an executor gives for one module over rows), and `compiler/graph/evaluation.py` `evaluate` (run a graph). Keep the word for the public folder only; rename the other two (for example `ChunkResult`, `run_graph`).
21. **"Plan" twice.** `plants/_utils/plan.py` (module order) and `engine/step.py` ("the binding plan of a run": which columns feed which inputs). Name the first `plan` and the second `bindings`; the compiler's traced form is `graph`, as already in the prompt.
22. **"Outcome" twice.** `engine/outcome.py` (one twin over a block of ticks) and `evaluate/_utils/outcome.py` (what an economics function does when inputs are missing). Rename by meaning.
23. **"Failure" in five places.** `ops/failed.py`, `ops/failures.py`, `compiler/graph/failures.py`, `evaluate/failures.py`, `engine/rows.py` (row-by-row fallback). The failed-row record is one concept (it is bug 1 of section 6b). One type in `errors/` or `ops/`, used by engine, compiler and evaluate.
24. **"Executor" twice.** `engine/executor.py` (the interface) and `compiler/executor.py` (the graph executor). That is correct (interface in the core, implementation in the compiler), so keep it, and write it in `structure.md` as the one allowed cross-folder name because it is the plug.
25. **The compiler layout** (already in the prompt): `graph/` holds tracer, proxy, graph, node, cache, passes, interpreter, runner, breaks, fixed point and evaluation, 17 files in one folder. Split it into `trace`, `ir`, `passes`, `cache`, `backends` / `interpret`; `breaks` and `rootbreak` join `trace`.

### Layer 4: case, evaluate, study, analysis

26. **`data/` holds only `schema.py`** (the JSON Schema of a demand profile). Its docstring promises "old project files", which live elsewhere → `case/`, and `data/` goes.
27. **`evaluate/` has 36 files, many tiny** (`lcoc.py` 14 lines), with balances in three files plus `modules/_utils/balance.py`, and `run_all.py` next to the verdict of feature/inputs. Group by job, with each public function still `gm.evaluate.<name>`:
    - `costs` (capex, opex, annualised, lcoh, lcoc, lcts, npv, payback, cashflow, discounting)
    - `emissions` (co2)
    - `balances` (energy, mass, plant, the module audits)
    - `verdict` (constraints, bounds, failures, run_all merged into the one verdict)
    - `summary` (totals, capacities, report, compare)
    - display → `units/`
28. **`analysis/`** by the test (calls the engine → study; calls one module at fixed conditions → analysis):
    - `calibrate.py` uses `Engine.replay`, so it goes to `study/`
    - `solves.py` and `wells.py` both say "nodal analysis", a duplicate → one `nodal.py`
    - `fits.py` (pump curve, reservoir pressure, UA from measurements) fits one module → stays
    - `integrity.py` (corrosion forecast): check what it takes. Results of a run → `evaluate/`; conditions → stays.
29. **`case/choices.py` and `study/_utils/choices.py`** are removed by feature/inputs (ranges move into the plant). Check that this happened.
30. **`study/_utils/target.py` lets a study vary `case.<path>`.** By the agreed design, `minimize` varies plant values only, and `sample` / `sensitivity` move only what the case declares uncertain. Check that this agrees after feature/inputs.

### Outside the package

31. **The top-level `inputs/` folder** holds the example cases while `examples/` holds the scripts. One place: `examples/<name>/` with its case, plants and data, so an example is one folder a user can copy. The goldens under `tests/` keep their own fixtures.
