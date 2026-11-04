# Task: Native engine step 3: one implementation per concept, one runner for replay, live and simulate, identical behaviour on every backend

## 0. Context and rules

- Previous step: the 65 local commits `80cd26b..refactor` (all physics and leaf modules with ops,
  traced composites, replay through the graph, CSE). Start from the current local `refactor`.
  Read `.claude/docs/native-engine.md` (especially §12 and §13) and `.tmp/native-engine/`
  (`replay-benchmark.md` and the earlier notes) first. Where this prompt and the design doc
  differ, this prompt wins; update the doc to match.
- **The rule of this step: no concept has two implementations.** One `forward` per module, one
  version of each physics function, one runner, one results builder, one error path. The only
  thing that differs is the backend. Debugging means choosing the python backend, not a second
  code path.
- **Behaviour is identical on every backend:** values, error class and message, skips, `Results`
  structure (including children), output types, callbacks, health. Where bit-identity is
  impossible, the difference must stay within the documented relative tolerance `1e-12`.
- Work directly on branch `refactor` (no new branch, no PR). Commit there. **Do not push**
  until I have reviewed the commits.
- Read `AGENTS.md` and every file in `.claude/docs/` first and follow them.
- **Pre-check (strict):** `git status` must be clean on `refactor`, and no other Claude session
  or process may be running in this workspace, even an idle-looking one. If one is, stop and
  report.
- My workspace is `/Users/sahand/Desktop/crust-team`. This task changes **only**
  `/Users/sahand/Desktop/crust-team/gemini` (branch `refactor`). You may read, but not change,
  `backend/`, `frontend/` and `infrastructure/`. Do not edit or commit `runs/`.
- Temporary files go to `.tmp/native-engine/` (git-ignored), never to `docs/`.
- **Work multi-agent and in parallel** (section 1b). Subagents run on a lighter model (sonnet
  for code, haiku for read-only searches), not the main model.
- **Tests:** development profile only (`make test` / `scripts/test_changed.py`): tests of what
  changed and of everything that imports it, in parallel, under 300 s. Never run the whole suite
  or the slow dataset locally. New tests in the right tier, session fixtures, short-window
  dataset, no fast-tier test over about 1 s, xdist-safe. Never delete or shrink existing tests,
  datasets or goldens. Benchmarks are scripts, not tests. Run `test_code_quality.py` after every
  merge (section 2.5 makes this automatic).
- **Numbers:** every example and golden stays bit-identical where it is today; anything else
  needs the documented `1e-12` tolerance, and a larger difference is a bug to fix.
- **Quality bar** (as in `.claude/docs/conventions.md`): nesting at most 3, functions about
  40 lines max, flake8 `max-complexity = 10`, guard clauses, no dead or speculative code, no
  golfed code, full-word names, explicit `gm.errors` classes, a failing test before each bug
  fix. **No comments inside code**: only the fixed section headers and tool directives;
  explanations go in docstrings. No "magic" structures, keep the public API minimal. When
  unsure, follow PyTorch source patterns as a design reference only; never name torch in the
  repo. black, isort and flake8 clean.
- **Docs:** every commit that changes behaviour updates the matching file in `.claude/docs/`
  in the same commit. Add the "one implementation per concept" rule and the "identical on every
  backend" rule to `conventions.md`.
- If something else is needed (missing step, dependency, risk), say so in the report instead of
  staying silent.

## 1. Out of scope

A real scan op, Numba, fusion, C++, autodiff or a JAX/other backend, scenario dimension, public
`gm.*` names for the ops, turning fluid properties and correlation coefficients into
`Parameter`/`Constant` graph inputs (keep them inline for now, but list them in the docs as a
known gap), per-output compute methods for leaves.

## 1b. Parallel plan

You are the coordinator: split the work, start subagents in parallel, review and merge their
work into `refactor`, and run the development tests (including `test_code_quality.py`) after
every merge. Create every worktree **by hand from `refactor`** (`git worktree add -b <tmp>
<path> refactor`); the worktree tool branched from `main` last time. Temporary branches are never
pushed and are deleted after merging. Two agents never edit the same file in the same wave.

- **Wave 1 (in parallel):**
  - A: section 2.1 and 2.2 mechanism (backends, ops, check).
  - B: section 2.5 (test infrastructure).
  - C (read-only, haiku): section 3, the duplicate-concept audit.
  - D: section 5.1 (columnar results with children).
- **Wave 2 (in parallel, one agent per module group, same groups as last step):** section 2.1
  and 2.2 applied to physics and modules, section 2.3, section 2.4, section 5.2 (health with ops).
- **Wave 3:** section 4, the single runner. It touches the engine, results and `module.py`
  together, so one agent or you alone.
- **Wave 4:** remove what the audit (section 3) still lists, section 6 parity suite, section 7
  benchmark and report.
- In the report, say what ran in parallel and what had to be serialised.

## 2. Make physics authoring simple and identical across backends

1. **Plain operators everywhere.** Today `/` or `**` on two plain floats can raise before any op
   runs, so authors must write `ops.truediv` / `ops.pow`. On the python backend, wrap scalar
   inputs as `numpy.float64` (same IEEE arithmetic, so values stay bit-identical) so that
   division by zero, invalid powers and overflow give `inf`/`nan` silently, exactly like the
   numpy backend. Then replace every `ops.truediv` / `ops.pow` that existed only for this with
   plain operators. Outputs leave the backend as the same Python type on every backend (define
   the rule, for example `float` for scalars), so `erosion_rate` and friends no longer return
   NumPy scalars on one backend and floats on another.
2. **One version of each physics function.** Physics functions with a `check` were split into a
   checked wrapper and an unchecked helper, because a check in the unselected branch of `where`
   would fire. Make `check` branch-aware instead (its error code is carried with the values and
   `where` keeps only the selected branch's errors, as the design says), so every function has a
   single version again. Remove the helpers.
3. **One stream, one fluid-properties type**: verify nothing else of `StreamState` or the old
   pydantic stream remains.
4. **Solvers:** one vectorised Brent and one Newton implementation per backend (fine, that is
   the backend's job), but the python and numpy versions must give the same iterates; document
   the measured maximum difference (last run: 6.4e-16).
5. **Test infrastructure:**
   - `scripts/test_changed.py` always selects `test_code_quality.py`.
   - The 7 tests that exceed the 1 s budget only under parallel load: make them genuinely
     faster, or measure the budget in a way that is stable under xdist (for example CPU time of
     the test itself). Never skip, mark as flaky or raise the budget blindly. `make test` must be
     green on this machine.

## 3. Duplicate-concept audit

Write `.tmp/native-engine/duplicates.md`: every concept that still has two implementations
anywhere in the package (execution loops, result builders, error paths, validation paths,
settings that switch between two paths, physics or helpers with two versions, two ways to call a
module, two places that compute the same output, two stream or type representations, old
compatibility code). For each: where, which one stays, what replaces the other. Everything on
the list is removed in this step unless you justify in the report why it must stay.

## 4. One runner for replay, live and simulate

1. **Delete the old tick-by-tick loop** and the setting that turns the traced path off. There is
   one runner: for each twin it builds (or takes from the cache) the graph and runs it on the
   selected backend. The python backend runs the same graph row by row with floats.
2. **replay:** the whole window as one run. No fallback to another path: per-row error codes
   from the graph produce exactly today's errors and skips (same class, message, row and
   summary).
3. **live:** the same runner with a one-row window per tick, graph taken from the cache.
4. **simulate:** the same runner. Until scan exists, graph breaks (stateful modules, the Python
   loop in `heatingsubstation.py`, the nodal solve in `nodal.py`) are stepped by the runner
   itself, in time order, inside the same run; this is the single implementation of a graph
   break, used by every mode. Results identical to today for every simulate example.
5. **Callbacks:** observer callbacks are replayed from results; callbacks that change the run
   (early stop, control logic) declare it and the runner calls them between chunks, as in design
   section 9. `EventLog` and `AutoCheckpoint` are built from results; checkpoints and resume keep
   working.
6. A direct module call (`esp(suction=...)`) stays eager on the python backend: the same
   `forward` and the same ops, no graph. Document that this is not a second implementation.

## 5. Results and health

1. **Columnar results with children.** Commit a whole run into `Results` column by column
   instead of building one result per row. Rows computed by the graph contain their children,
   exactly like today's composite results, so `Results` has the same structure on every backend
   and mode.
2. **Health with ops.** Rewrite every module's `health` with ops so it runs on the whole window
   at once; same scores, alarms, messages and metrics as today. `fit_*` and plotting helpers stay
   plain Python (they are not on the run path).

## 6. Backend parity suite

A dedicated test suite that runs every example and every module on the python and the numpy
backend and compares: values (bit-identical or within `1e-12`), error class and message for each
failing row, skips, `Results` structure including children, output types, callbacks, health and
`EventLog` content (except durations). Cheap module cases go in the fast tier; whole examples go
in the slow tier (CI). Adding a backend later must only mean adding it to this suite's list.

## 7. Benchmark and report

- Re-run the benchmark: month replay (old numbers: 5.22 s old path, 1.07 s last step), ESP alone,
  live per tick, one simulate example. Write `.tmp/native-engine/step3-benchmark.md` with what
  dominates the remaining time.
- Final report to me: commits, speed numbers, the duplicate list and what was removed, behaviour
  changes, adapted tests (none deleted or weakened), anything that turned out hard or wrong (also
  recorded in `native-engine.md`), and the next step you recommend.
