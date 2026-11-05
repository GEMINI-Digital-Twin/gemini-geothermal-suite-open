# Task: Native engine step 2: fix the prototype, rewrite all physics and modules with ops, run replay through the graph, take validation off the hot path, add CSE

## 0. Context and rules

- Previous step: the 9 commits `8e562e8..80cd26b` on `refactor` (ESP prototype, composite
  outputs cleanup). Read `.claude/docs/native-engine.md` (especially §12, the decisions that
  turned out hard) and `.tmp/native-engine/` (`analysis.md`, `pydantic_audit.md`,
  `esp-benchmark.md`) first. Where this prompt and the design doc differ, this prompt wins;
  update the doc to match.
- Goal: all physics and all leaf modules are written with ops, the full `doublet_heat` replay
  runs each twin as one traced call with identical results and a real speedup, plus the fixes in
  section 2.
- The 9 commits of the previous step are pushed; `refactor` matches `origin/refactor`.
- Work directly on branch `refactor` (no new branch, no PR). Commit there. **Do not push**
  until I have reviewed the commits.
- Read `AGENTS.md` and every file in `.claude/docs/` first and follow them.
- **Pre-check (strict):** `git status` must be clean on `refactor`, and **no other Claude
  session or process may be running in this workspace**, even an idle-looking one. If one is,
  stop and report; do not continue on your own judgement.
- My workspace is `/Users/sahand/Desktop/crust-team`. This task changes **only**
  `/Users/sahand/Desktop/crust-team/gemini` (branch `refactor`). You may read, but not change,
  `backend/`, `frontend/` and `infrastructure/`. Do not edit or commit `runs/`.
- Temporary files go to `.tmp/native-engine/` (git-ignored), never to `docs/`.
- **Work multi-agent and in parallel** (section 1b). Subagents run on a lighter model (sonnet
  for code, haiku for read-only searches), not the main model.
- **Tests:** use the development profile only (`make test` / `scripts/test_changed.py`): the
  tests of what changed and of everything that imports it, in parallel, under 300 s. Never run
  the whole suite or the slow dataset locally; the release profile runs in CI. New tests go in
  the right tier, reuse the session fixtures and the short-window dataset, no fast-tier test
  over about 1 s, xdist-safe. Never delete or shrink existing tests, datasets or goldens.
  Benchmarks are scripts, not tests.
- **Numbers:** every example and golden stays bit-identical where it is today; anything else
  needs a documented relative tolerance of `1e-12`, and a larger difference is a bug to fix,
  not a tolerance to widen.
- **Quality bar** (as in `.claude/docs/conventions.md`): nesting at most 3, functions about
  40 lines max, flake8 `max-complexity = 10`, guard clauses, no dead or speculative code, no
  golfed code, full-word names, explicit `gm.errors` classes, a failing test before each bug
  fix. **No comments inside code**: only the fixed section headers and tool directives;
  explanations go in docstrings. No "magic" structures, keep the public API minimal. When
  unsure, follow PyTorch source patterns as a design reference only; never name torch in the
  repo. black, isort and flake8 clean.
- **Docs:** every commit that changes behaviour updates the matching file in `.claude/docs/`
  in the same commit.
- If something else is needed (missing step, dependency, risk), say so in the report instead of
  staying silent.

## 1. Out of scope

Numba, fusion, C++, a working scan (stateful modules are rewritten with ops but stay graph
breaks), autodiff, scenario dimension, removing pydantic outside streams and fluid properties,
per-output compute methods for leaves, public `gm.*` names for the ops.

## 1b. Parallel plan

You are the coordinator: split the work, start subagents in parallel, review and merge their
work into `refactor`, and run the development tests after every merge. Each code subagent works
in its own local git worktree on a temporary local branch from `refactor`; these branches are
never pushed and are deleted after merging (the only exception to "no new branches"). Give each
subagent the rules of section 0, the op-writing rules of section 3, and only its own files. Two
agents never edit the same file in the same wave; if they would, serialise them.

- **Wave 1 (in parallel):**
  - A: section 2.1 and 2.3 (ops, backends, `Constant`, ESP).
  - B: section 2.2 (reference resolution and error messages).
  - C (read-only, haiku): section 2.4 reports.
  - D: section 5, CSE graph pass with tests.
  - E: section 3.1, one `Stream` (and cheap `with_`, section 4.1).
  - F: section 3.2, fluid properties and the solver ops.
- **Merge wave 1**, one agent at a time, tests after each merge, fix conflicts yourself.
- **Wave 2 (in parallel, one agent per group, section 3.3).**
- **Merge wave 2** the same way.
- **Wave 3:** section 3.4 to 3.6 (traceable composites and engine replay). It touches
  `module.py`, the engine and the graph together, so one agent or you alone.
- **Wave 4:** sections 4.2 and 4.3, then section 6 benchmark and the report.
- In the report, say what ran in parallel and what had to be serialised.

## 2. Fixes to the prototype (one commit each)

1. **`where` branches are plain values again, not callables.** The user-facing rule is: physics
   authors write only `where(condition, a, b)` and `check(...)`. Make evaluating the unselected
   branch safe instead: on the python backend, division by zero, `log`/`sqrt` of a negative and
   overflow return `inf`/`nan` like NumPy (silenced) instead of raising. The selected branch
   must still give exactly today's values. Remove callable support and rewrite the ESP (and any
   other caller) accordingly.
2. **"Did you mean" on bad references.** A misspelled child or output reference in `__init__`
   (`self.heat_exchanger.dutyy`) raises a `gm.errors` class with the module path and a
   close-match suggestion, as the old string form did.
3. **Normal-path slowdown.** Writing the ESP with ops made the untraced call about 10 % slower
   (528 -> 585 ms), from the call each `Constant` goes through. Bring it back to within 2 % of
   the old time without breaking the float32 goldens. Measure before and after.
4. **Two checks, report only, change nothing:**
   - Every place an additive `Duty` (and `HydraulicPower`) is summed: is the sum physically
     meaningful, or does it double count exchangers in series? List them.
   - Search `backend/`, `frontend/`, `infrastructure/`, examples, bindings and configs for the
     old name `electricity_use` (renamed to `electricity`) and list every hit.

## 3. Physics and modules with ops, then replay through the graph

Op-writing rules (same as the ESP): value-dependent `if`s become `where` (branch choice) or
`check` (validity, same `gm.errors` class and message); `math.*` becomes ops; parameters and
physical constants are graph inputs (`Parameter`, `Constant`), only pure math and unit
conversion numbers stay literal; results bit-identical on the python backend; existing tests
unchanged and green; an equivalence test numpy vs python (`rel=1e-12`) for every rewritten
function and module.

1. **One `Stream`.** Today `Stream` is pydantic and the traced path uses a separate
   `StreamState`. Make one stream type: a plain dataclass (slots) used on both paths, with
   validation only at the boundary, raising `gm.errors`; remove `StreamState`. Do the same for
   `FluidProperties`. Physics tests that depend on pydantic behaviour are adapted to the same
   intent, never deleted or weakened; list each one in the report.
2. **Fluid properties and solvers first.** Almost every module calls `fluid.properties`, so
   `gemini/core/physics/fluid.py` is rewritten first. The Newton solver (NORSOK) and the two
   `brentq` calls become `solver` ops with per-element stopping (`scipy.optimize.newton` with
   arrays and `scipy.optimize.elementwise.find_root` on the numpy backend).
3. **All other physics and every leaf module, in parallel groups** (each group owns its physics
   files and its module folders):
   - hydraulics, geometry, ground + `modules/subsurface`;
   - heat_transfer, refrigeration, psychrometrics + `modules/heat`, `modules/demand`;
   - pumps, compression, steam + `modules/pumps` (except ESP), `modules/power`;
   - chemistry, corrosion, erosion + `modules/treatment`;
   - `modules/piping`, `modules/storage`, `modules/control`, `balance.py`.
   Start with the modules `doublet_heat` uses, so the replay can be measured early. Stateful
   modules (storage, thermal decline, aquifer storage, PID controller, ...) are rewritten too
   but stay graph breaks until scan exists; mark them clearly.
4. **Composites become traceable.** Plants are composites, so tracing must go through child
   calls, call records, automatic sums, `Output.of` and `Output.ratio`, producing one graph per
   twin. Stateful modules, pre-hooks and float32 stay graph breaks: a graph break runs only that
   module on the python path, tick by tick, and the rest stays in the graph.
5. **Connect the runner to the engine.** In `replay`, each twin runs as one traced call over the
   whole window, with graph caching and guards as in the design. The public API (`Engine`,
   `Results`, `Dataset`) does not change. Callbacks, `EventLog`, `AutoCheckpoint`, health and
   soft sensors give the same results as before (observer callbacks replayed from results).
   A setting turns the traced path off, so the old path stays available for debugging.
6. Report which twins of `doublet_heat` and of the other examples run fully traced, which have
   graph breaks, and why.

## 4. Validation off the hot path

From the pydantic audit, remove the costly per-tick validation without removing pydantic yet:
1. `Stream.with_`: a cheap copy that does not dump and re-validate (done with section 3.1).
2. Per-declaration validation of inputs, outlets and outputs: run it at the boundary (user
   construction, config loading, first call or trace) instead of on every call. Errors that
   validation used to catch must still be caught with the same `gm.errors` class, either at the
   boundary or as a `check` in the graph; add a test for each class of error that moves.
3. Building `Stream` objects for engine inlets: avoid it on the traced path.

## 5. Common-subexpression elimination

A graph pass that merges identical nodes (same op, same inputs, same attributes), so repeated
physics in `forward` and `_compute_outputs` is computed once. Tests: merged node count on the
ESP and a composite, results unchanged.

## 6. Benchmark and report

- Extend the benchmark script: full `doublet_heat` month replay, old path vs traced path, best
  of 5, plus ESP alone with and without CSE. Write `.tmp/native-engine/replay-benchmark.md` with
  the numbers and what dominates the remaining time.
- Final report to me: commits, the speed numbers, the number of physics functions and modules
  rewritten and any left out with the reason, the adapted pydantic-dependent tests, the two lists from section 2.4, graph breaks
  per twin, every design decision that turned out hard or wrong (also recorded in
  `native-engine.md`), and the next step you recommend.
