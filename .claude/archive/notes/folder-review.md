# gemini folder and file review (2026-11-02 00:10)

Read from `origin/dev` 061fbe9 (before `feature/inputs` is merged): every file of `gemini/` with its size and first docstring line. Not run. Rules referred to: R1-R7 and the folder definition table of `prompts/gemini-forward-scan.md` section 1b; P1-P8 of the input spec.

Count: 315 files. Per folder: modules 83, evaluate 36, plants 37, compiler 21, physics 21, ops 19, case 18, engine 17, study 14, _utils 12, types 11, run 10, analysis 6, errors 3, units 2, runtime 2, data 2.

## Layer 0: units, errors, types, _utils

1. **`types/` is an implementation word (R2) and mixes five jobs.** 11 files:
   - `quantities.py` and `bare.py` (the rule "a boundary takes a quantity") are units → `units/`
   - `shapes.py` (value / problem / check returns) is errors → `errors/`
   - `flows.py`, `fluid.py`, `ports.py`, `streams.py` are what modules exchange → a `streams/` domain (`gm.Stream`, `gm.Fluid`)
   - `results.py` (per-call module results, Health) → `modules/`
   - `profile.py` (time series) → `case/`, see item 14
   - `bindings.py` (sensor and dated-parameter metadata) → `modules/`
   - After this, `types/` is gone.
2. **`units/` has one real file today (`conversions.py`, 655 lines).** With item 1 and the display table (`evaluate/_utils/display.py`), it has three jobs: quantity, conversions, display. So it stays a folder for a real reason (R1). Otherwise it would become `units.py`.
3. **`errors/` (base, lookup)** plus `shapes.py` from types, plus the issue type from feature/inputs, is a real folder.
4. **`_utils/paths.py` names the repo's `inputs/` folder.** The package must not know where a checkout keeps its examples (P8 general), and nothing imports it. → remove.
5. **Three context-setting places:** `_utils/context.py` (generic `with` blocks), `runtime/context.py`, `ops/backend.py` (context-local backend). → one owner: `runtime.py` uses `_utils/context.py`; backend selection is a runtime setting.

## Layer 1: ops, physics

6. **`ops/control.py` is a stub** ("scan: defined only, with no backend implementation"). It is already covered: section 4 of the prompt builds it.
7. **Physics lives in two places.**
   - `physics/` has 21 files.
   - Also `modules/<folder>/_physics.py` in 7 folders, plus `_sorption.py` and `_burner.py`, about 5,000 lines.
   - Fix: one rule. A correlation that is true for any equipment goes to `physics/`. Only code that needs the module's own declarations stays beside it, and gets a name that says what it is.
8. **Not physics in `physics/`** (the definition is: physical states in, properties out, no module known):
   - `physics/costs.py` (unit cost times size) → `evaluate/`
   - `physics/dispatch.py` (which doublet runs at what for a heat need) is a control policy → with `schedule`, item 11
   - `physics/doublet.py` (child values of a doublet from its depth) knows a plant's children → `plants/`
   - `physics/diagnostics.py` (drift, health score) is monitoring → beside `engine/health.py`
9. **`physics/separation.py` docstring says "filter defaults".** This may break the no-defaults rule; check it and remove any defaults.
10. **Two fluid models.** `physics/fluid.py` ("constant fluid properties") and `types/fluid.py` ("stream composition and cached constant-property models"). P6 (one representation per concept): fluid properties go to `physics/fluid.py`; the stream composition type goes to `streams/`.

## Layer 2: modules, plants

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

## Layer 3: run, engine, compiler

19. **Running is split over two folders with no rule.**
    - `run/` holds simulate/replay/live/resume, schedule, Results, Dataset and the case application.
    - `engine/` holds Engine, the runner, chunks, clock, the eager executor, the binding plan, health and the archive.
    - By the definition, one plant plus one case gives one run over time, and that is one domain.
    - Fix: merge `run/` into `engine/`.
      - Public names stay at `gm.simulate` and the rest.
      - `Results` goes with the engine.
      - `Dataset` and the time series go to item 14b below.
      - `schedule` goes with its policy (`physics/dispatch.py`, `run/_utils/sources.py` marginal costs, `run/_utils/limits.py` enforced requirements) in `engine/schedule/`.
    - A design question for later: the schedule is really a supervisory controller of the plant (`control.dispatch` in the plant file), so it could become a control module. Not in this prompt.
    - 14b. **Five time-series representations:** `types/profile.py`, `case/_utils/profile.py`, `case/_utils/demand.py`, `run/dataset.py`, plus `engine/loader.py` and `engine/columns.py` aligning them. P6 says one series type. `case/` owns series that are inputs, measurements included. The engine only aligns them to ticks.
20. **The word "evaluate" means three things.** `gm.evaluate` (judge results), `engine/evaluation.py` `Evaluation` (what an executor gives for one module over rows), and `compiler/graph/evaluation.py` `evaluate` (run a graph). Keep the word for the public folder only; rename the other two (for example `ChunkResult`, `run_graph`).
21. **"Plan" twice.** `plants/_utils/plan.py` (module order) and `engine/step.py` ("the binding plan of a run": which columns feed which inputs). Name the first `plan` and the second `bindings`; the compiler's traced form is `graph`, as already in the prompt.
22. **"Outcome" twice.** `engine/outcome.py` (one twin over a block of ticks) and `evaluate/_utils/outcome.py` (what an economics function does when inputs are missing). Rename by meaning.
23. **"Failure" in five places.** `ops/failed.py`, `ops/failures.py`, `compiler/graph/failures.py`, `evaluate/failures.py`, `engine/rows.py` (row-by-row fallback). The failed-row record is one concept (it is bug 1 of section 6b). One type in `errors/` or `ops/`, used by engine, compiler and evaluate.
24. **"Executor" twice.** `engine/executor.py` (the interface) and `compiler/executor.py` (the graph executor). That is correct (interface in the core, implementation in the compiler), so keep it, and write it in `structure.md` as the one allowed cross-folder name because it is the plug.
25. **The compiler layout** (already in the prompt): `graph/` holds tracer, proxy, graph, node, cache, passes, interpreter, runner, breaks, fixed point and evaluation, 17 files in one folder. Split it into `trace`, `ir`, `passes`, `cache`, `backends` / `interpret`; `breaks` and `rootbreak` join `trace`.

## Layer 4: case, evaluate, study, analysis

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

## Outside the package

31. **The top-level `inputs/` folder** holds the example cases while `examples/` holds the scripts. One place: `examples/<name>/` with its case, plants and data, so an example is one folder a user can copy. The goldens under `tests/` keep their own fixtures.

## Suggested order inside section 1b

The pure moves and renames (items 1-5, 8, 10-12, 14-17, 19-28, 31) go to worker S. Items 13 and 7 (splitting `module.py`, moving `_physics.py`) touch the same code as the forward contract, so they go to worker A and workers B-E. Item 9 is a check. Items 29 and 30 are checks after feature/inputs.
