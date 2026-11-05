# Task: Physics only in `physics/`: no formulas in modules, no duplicate physics, clean modules

## 0. Context and rules

- **The rule this step enforces:** a module **declares and wires**; **physics computes**. No formula is written inside a module. A module calls functions from `gemini/physics/` and combines them; when a module needs something new, the function is added to `physics/` (or an existing one is generalised), never written in the module. **Every formula exists exactly once.** Existing physics is reused wherever it fits, and a new physics function is only added when nothing existing can do the job.
- Only this. The `Module` base-class cleanup (methods, splitting `module.py`), the plant-code rewrite and everything under `gemini/modules/plants/` are **later prompts**. Do not touch `modules/plants/` and do not change `module.py` beyond what a moved formula strictly needs.
- Start from the current local `refactor` (`gemini/core` is gone; modules live in `gemini/modules/<category>/`). Read `AGENTS.md` and every file in `.claude/docs/` (especially `conventions.md`, `modules.md`, `physics.md`, `equipment.md`, `native-engine.md`) and follow them.
- **Standing rules:** no concept has two implementations; behaviour is identical on every backend (the parity suite stays green); physics and numbers do not change. Every example and golden stays bit-identical. Where merging two copies of a formula changes the floating-point order, a relative difference up to `1e-12` is allowed, and every such case is listed in the report. A larger difference means the two copies were different models: keep both as separately named physics functions and report it.
- Work directly on branch `refactor` (no new branch, no PR) and commit there. **Do not push** until I have reviewed the commits.
- **Pre-check:** `git status` is clean on `refactor`, and no other Claude session or process is working **inside `gemini/`**. Sessions in other folders do not block you. If their load makes a 1 s budget test fail, rerun that test alone before treating it as a failure, and say which tests you retimed.
- Workspace `/Users/sahand/Desktop/crust-team`. Change **only** `gemini/`. You may read `geomind/` and `backend/`, never change them.
- Temporary files go to `.tmp/physics/` (git-ignored).
- **Work multi-agent and in parallel** (section 1). Subagents run on a lighter model (sonnet for code, haiku for read-only searches), not the main model.
- **Tests:** development profile only (`make test` / `scripts/test_changed.py`, always including `test_code_quality.py`), in parallel, under 300 s; plus the e2e tier and all numbered examples at the end, compared byte for byte with a baseline you take before the first change. Never run the slow dataset locally. New physics functions get their own unit tests in the right tier (no fast-tier test over about 1 s). Never delete or shrink existing tests, datasets or goldens; a test that moves with its formula keeps its assertions.
- **Quality bar** as in `.claude/docs/conventions.md`: nesting at most 3, functions about 40 lines, flake8 complexity 10, full-word names, explicit `gm.errors`, no comments inside code (docstrings only), no "magic". black, isort and flake8 clean.
- If something else is needed, say so in the report.

## 1. Parallel plan

You are the coordinator. Create worktrees by hand from `refactor` (`git worktree add -b <tmp> <path> refactor`); temporary branches are never pushed and are deleted after merging. Merge one agent at a time and run the tests after each merge. Two agents never edit the same file in the same wave; **physics files are owned by one agent per wave** (assign each physics file to exactly one agent), so two agents never add to the same physics file at once.

| Wave | Who | Work |
|---|---|---|
| 0 | coordinator, haiku helpers read-only | baseline; the audit (section 2); split the work by physics file and module folder |
| 1 | agents in parallel | remove duplicates inside `physics/` itself (section 3) |
| 2 | agents in parallel, by module folder | move every formula out of modules (section 4) |
| 3 | agents in parallel | unused parameters and the naming glossary (section 5) |
| 4 | coordinator | the enforcement test, docs, final checks (sections 6, 7) |

## 2. Audit (wave 0)

Write `.tmp/physics/audit.md`: for every module file under `gemini/modules/` (except `plants/`) and every file in `gemini/physics/`, list

- each formula or numeric expression in a module (arithmetic on physical quantities, `ops.exp/log/sqrt/power`, `**`, numeric coefficients other than unit factors), with the physics function it should call or the one to add;
- each formula that exists more than once (in modules, in physics, or both), with every location;
- fitting, regression or calibration code inside modules;
- unused parameters and inconsistent names (section 5).

Known cases from a first look (re-check each one; report any that no longer apply):

- The quadratic pressure drop `dp_nominal * (m_dot / m_dot_nominal) ** 2` is written separately in `Valve`, `Filter` and `Desander`.
- `IceStorage` computes the coil effectiveness `1 - exp(-UA / C)` itself; `heat_transfer.effectiveness_parallel(ntu, 0)` already gives it (`Pipe` uses that).
- `Pipe` computes the laminar and transition friction itself and calls `hydraulics.darcy_weisbach_dp` only from Re = 4000.
- `HeatPump`: the Carnot and Lorenz COP models (`_carnot_heating_cop`, `_carnot_cooling_cop`, `_lorenz_cop`) are defined in the module file; `physics/refrigeration.py` holds the Carnot and Lorenz COP functions.
- `CentrifugalPump` writes its affinity-law curve in the module; `ESP`, `LineShaftPump` and `InjectionPump` use `physics.pumps`.
- `ESP` fits curve coefficients (a regression) inside the module.
- `IceStorage`, `BoreholeField`, `HeatExchanger`, `ORC`, `GasCompressor` and `Reservoir` have many expressions each.
- `physics/units.py` (57 functions) and `gm.units`: check that unit conversion has one implementation.
- `CoolingConsumer._dew_point` is a thin wrapper of `psychrometrics.dew_point`; wrappers that only rename a physics call go away.

## 3. Duplicates inside `physics/` (wave 1)

- One function per formula. Merge copies; keep the clearest name; update every caller.
- Group functions by subject (hydraulics, heat transfer, refrigeration, pumps, ...). A function used by only one module still belongs in `physics/` if it is physics.
- Generalise rather than copy: for example one quadratic-loss function used by valves, filters and desanders, one effectiveness function family used by exchangers, storages and pipes.
- Every physics function has a docstring with the equation, units of every input and output, the validity range and the source (book, standard or paper), and works on both backends (written with `ops`, no Python branching on values).

## 4. Formulas out of modules (wave 2)

- Each module's `forward` and `_compute_outputs` only read inputs, call physics functions, combine their results with plain wiring (passing one result into the next call, picking with `ops.where`, checks with `ops.check`), and set outlets and outputs. Arithmetic that is physics (a balance, a correlation, a curve, an efficiency) moves to `physics/`. Simple bookkeeping stays (for example adding two flows into one outlet, or `duty = m_dot * cp * dT` only if no physics function for it exists, in which case add it to `physics/`).
- Fitting, regression and calibration move out of modules: into `gm.analysis` or `gm.optim`, reusing what exists there (`gm.optim.calibrate`). The module keeps only the parameters the fit produces.
- Modules that are genuinely different models (for example the ESP polynomial curve and the centrifugal affinity laws) keep different physics functions with names that say which model they are.
- Private helper methods in modules that only wrap one physics call are removed; the call goes inline.
- Every module ends up with the same structure in `__init__` and the same order of sections as `conventions.md` describes. Where the conventions do not yet describe one shape, write it down there and apply it to every module.

## 5. Unused parameters and names (wave 3)

- Remove parameters that no computation reads (known from an earlier review, re-check each one: `ESP.pump_type`, `ESP.setting_depth`, `ESP.correction_factor`, `ESP.tubing`, `InjectionPump.pump_type`, `_Reservoir.liquid_density`, `_Reservoir.liquid_viscosity`, `Degasser.heat_transfer_coeff`). If a parameter is read only by docs or a legacy import, say so instead of removing it.
- Write `.claude/docs/glossary.md`: one name per concept for parameters, outputs and ports across all modules, and apply it. Known cases: `no_stages` vs `stage_count`; `coeff` vs `coefficient`; `min_` vs `minimum_`; abbreviations such as `dp`, `ua`, `m_dot`; `carnot_efficiency` vs `fraction_of_carnot`. Stream fields that are part of the frozen `Stream` type (`m_dot`, `T`, `p`) keep their names. Full words, the same word for the same thing everywhere.
- A test checks every parameter, output and port name of every registered module against the glossary.
- Renaming or removing parameters changes the public API: raise `gm.API_VERSION` to 4, update the public-API snapshot and add a change-log line in `.claude/docs/api.md` with every old to new name.

## 6. Enforcement

- A test in `test_code_quality.py` scans `gemini/modules/` (except `plants/` for now) and fails on formulas in modules: calls to `ops.exp`, `ops.log`, `ops.sqrt`, `ops.power`, `math.*`, `numpy` maths, the `**` operator, and numeric literals other than `0`, `1` and declared unit factors. Exceptions are listed by name in one place in the test, each with its reason, and the list should be empty or nearly empty at the end.
- A test fails when two physics functions have the same body (normalised), so copies cannot come back.

## 7. Docs

Add to `.claude/docs/conventions.md` and `modules.md`, in the same commit as the first code change:

> **Physics lives only in `gemini/physics/`.** Modules declare and wire; they never define physics. Reuse existing physics functions wherever possible and combine them; add a new physics function only when nothing existing can do the job, and generalise an existing one rather than writing a second copy. Never write a formula inside a module, and never write the same formula twice. Fitting and calibration belong in `gm.analysis` or `gm.optim`, not in modules.

Also update `physics.md` (what each physics file holds, one line per function), `equipment.md` (which physics each module uses), `glossary.md` and `AGENTS.md` "Start here".

## 8. Report

- Commits, wave by wave.
- The audit summary: formulas moved per module, duplicates removed (with their old locations), physics functions added or generalised, fitting code moved.
- Every case with a difference up to `1e-12`, and every case kept as two models.
- Parameters removed and names changed (old to new).
- The exception list of the enforcement test, if not empty.
- Test, e2e and example results against the baseline; retimed tests.
- Every use in `geomind/` and `backend/` of a parameter name that changed (read-only check, file and line).
