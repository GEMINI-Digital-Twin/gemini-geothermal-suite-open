# Task: Start the native-engine work: output cleanup, then the computation-graph prototype on the ESP

## 0. Context and rules

- Goal, in this order: (a) a small speed fix, (b) a cleanup of how composite modules declare
  outputs, (c) prove the agreed computation-graph design on one module, the ESP, before building
  it for the whole package: a minimal working tracer, IR, interpreter and two backends (python,
  numpy) for the ESP path, equivalence tests, a pydantic audit, and a real speed number.
- Start from the current local state of `refactor` (including any commits not yet pushed).
- The full design is in `native-engine-design.md` (next to this prompt; copy it to
  `.claude/docs/native-engine.md` in your first docs commit). Follow it. Where this prompt and
  the design differ, this prompt wins for this task; report any conflict you find.
- Work directly on branch `refactor` (no new branch, no PR). Commit there. **Do not push**
  until I have reviewed the commits.
- Read `AGENTS.md` and every file in `.claude/docs/` first and follow them.
- **Pre-check:** `git status` must be clean on `refactor` and no other task may be running on
  this repo. Otherwise stop and report.
- My workspace is `/Users/sahand/Desktop/crust-team`. This task touches **only**
  `/Users/sahand/Desktop/crust-team/gemini` (the GEMINI package repo, branch `refactor`).
  Do not change `backend/`, `frontend/` or `infrastructure/`. Do not edit or commit `runs/`.
- Temporary files (audit lists, baselines, benchmark notes, scratch) go to `.tmp/native-engine/`
  at the repo root (git-ignored), never to `docs/`.
- Subagents, if you use any, run on a lighter model (sonnet or haiku), not the main model.
- **Tests:** use the development profile only (`make test` / `scripts/test_changed.py`): the
  tests of what changed and of everything that imports it, in parallel, under 300 s. Never run
  the whole suite or the slow dataset locally; the release profile runs in CI. New tests go in
  the right tier, reuse the session fixtures and the short-window dataset, no fast-tier test
  over about 1 s, xdist-safe. Never delete or shrink existing tests, datasets or goldens.
  Benchmarks are not tests: put them in a script, not in the fast tier.
- **Quality bar** (as in `.claude/docs/conventions.md`): nesting at most 3, functions about
  40 lines max, flake8 `max-complexity = 10`, guard clauses, no dead or speculative code, no
  golfed code, full-word names, explicit `gm.errors` classes, a failing test before each bug
  fix. **No comments inside code**: only the fixed section headers (`# Modules`,
  `# Parameters`, ... `# Outlets`) and tool directives; explanations go in docstrings. No
  "magic" structures, no string registries beyond the op registry the design asks for, keep the
  public API minimal. When unsure how to build something, follow the patterns of PyTorch's
  `torch.fx` (Node, Graph, Proxy, Tracer, Interpreter) as a design reference only; never name
  torch in the repo. black, isort and flake8 clean.
- **Docs:** every commit that changes behaviour updates the matching file in `.claude/docs/`
  (and `AGENTS.md` "Start here" for the new `native-engine.md`) in the same commit.
- If something else is needed (missing step, dependency, risk, a design decision that does not
  survive contact with the code), say so in the report instead of staying silent.

## 1. Out of scope

C++, Numba, fusion, per-output compute methods for leaf modules (leaves keep `_compute_outputs`), a working scan (define the op kind only), autodiff, scenario dimension
(design for it, implement time only), Engine integration, hooks and callbacks on the traced path beyond what section 5 tests (design section 9), removing pydantic outside the ESP path,
any change to the public API (`Engine`, `Results`, `Dataset`).

## 2. Small independent commit first

`AttributeMapping` in `gemini/utils/mappings.py` has no `__contains__`, so every failed lookup
builds a `difflib` "did you mean" message. Add `__contains__` (about 4 lines) with a test.
Measured before: `doublet_heat` one-month replay 9.66 s -> 7.29 s with identical results.
Re-measure and put both numbers in the commit message.

## 2b. Composite outputs cleanup (independent of the graph work)

All declarations stay in `__init__`. Leaf modules keep `_compute_outputs` exactly as today.
Only composite modules and the output types change. Physics and numbers must not change.

1. **Additive semantic types.** Add quantity types for the five quantities that are summed
   today with `Output.total`: `Electricity`, `HeatLoss`, `HeatSupplied`, `HeatAbsorbed`,
   `HeatAccumulation` (unit W, each with its own quantity name) and mark them additive. Keep
   mass flow additive as today. Leaf modules that declare these outputs as `Output(Power)` switch
   to the new type (same name, same unit, same values).
2. **Automatic aggregation.** A composite that declares `Output(<additive type>)` without a
   formula gets, automatically, the sum of the output with the **same name and type** over its
   descendant leaf calls in this call (a child called twice counts twice, as today). This
   replaces every `Output.total("...")`; remove `Output.total`. Keep today's checks: no
   descendant declares it, or names match with different types/units -> clear error with a
   close-match suggestion. A composite that computes its own value for that name is not summed.
3. **Direct references instead of strings.** `Output.of` and `Output.ratio` take declaration
   objects instead of path strings: `Output.of(self.heat_exchanger.duty)`,
   `Output.of(self.producers[0].riser.wellhead_temperature)`,
   `Output.ratio(self.thermal_power, self.electricity)`. Child modules are created first in
   `__init__` (`# Modules` section), so the references exist. Each declaration must know its
   owner module and name to resolve the path; a wrong reference fails when the class is built,
   not during a run. Remove the string form; keep the exactly-once rule of `Output.of`.
4. Update every composite module (`plants/` and any other), examples, tests and
   `.claude/docs/` (module template and outputs docs). List every changed declaration in the
   report.
5. Tests: aggregation by type (including nested composites like a district network of
   substations), same name with different type raises, own value overrides the sum, wrong
   reference fails at class creation, results identical to before for every example (compare
   with `rel=1e-12`; anything larger is a bug).
6. Hooks keep their fixed order after the change (`forward` -> `_compute_outputs` -> formula
   outputs and automatic sums -> forward hooks -> `_check_outputs`); a hook still sees every
   output, including automatic sums.
7. One commit per step (types, aggregation, references, migration).

## 3. Analysis (before writing the prototype)

Write `.tmp/native-engine/analysis.md` with:

1. **pydantic audit:** every place pydantic is used (models, validators, coercion, config
   loading, serialisation), grouped by purpose, with what must replace each use when pydantic is
   removed (dataclass with slots + validation at the boundary raising `gm.errors`). Do not remove
   it yet outside the ESP path.
2. **ESP path:** the ESP module, its physics functions in `gemini/core/physics`, the types it
   passes through, its parameters, and every value-dependent `if`, `raise`, `math.*` call and
   solver on that path. Classify each `if` as a validity check (-> `gm.check`) or a branch choice
   (-> `gm.where`).
3. **Existing parameter mechanism:** how `named_parameters` and parameters work today, and how
   `Parameter`, `Constant`, `State` (design section 4) fit on top of it without breaking it.
4. **Baseline numbers:** time of the ESP physics over the short-window dataset run tick by tick
   on the current code, and the `doublet_heat` replay time.

Stop after the analysis only if you find a blocker (for example Proxy cannot pass through a type
on the ESP path even with validation off). Otherwise continue.

## 4. Prototype

Build only what the ESP path needs, in the layout of design section 10:

1. `gemini/ops/`: registry with op name, kind and signature; only the ops the ESP physics uses,
   plus `where` and `check`.
2. `gemini/backends/`: `Backend` base, `register`, `settings`; `python.py` (scalars with
   `math`) and `numpy.py` (arrays); numpy fallback for missing ops; numpy warnings silenced
   inside the backend.
3. `gemini/graph/`: `Node` (with op, kind, inputs, unit metadata and the source file and line),
   `Graph`, `Proxy`, `Tracer` (one Module at a time), `Interpreter`, and a minimal `cache`.
4. `gemini/core/modules/parameter.py`: `Parameter`, `Constant`, `State` on top of the existing
   mechanism; physical constants used by the ESP path become `Constant` in
   `gemini/core/physics/constants.py`. Parameters and constants are graph inputs, never literals;
   only pure math and unit-conversion numbers are literals.
5. ESP types without pydantic validation during tracing (dataclasses with slots, validation at
   the boundary only).
6. Trace the whole ESP call, not only `forward`: `_compute_outputs` and any formula outputs
   are traced with it in the fixed order (design section 9), `_check_outputs` runs at trace
   time, and `gm.no_outputs()` gives a graph without the output step. Every ESP output must be
   in the graph and equal to today's values.
7. Rewrite the ESP physics with `gm` ops. The existing ESP tests must pass unchanged on the
   python backend.
8. Errors as in design section 6: `check` yields per-row error codes that travel with values,
   `where` selects them with the chosen branch, only errors reaching an output raise, with the
   same `gm.errors` class and message as today.

## 5. Tests

- Nothing that already runs may break: on the normal (untraced) path, forward pre-hooks, forward
  hooks, `_compute_outputs`, formula outputs, `_check_outputs`, `gm.no_outputs()`, `health()`,
  `soft_sensors()`, engine callbacks, `EventLog` and `AutoCheckpoint` behave exactly as before.
  List them in the report with the tests that cover them.
- Hooks on the traced ESP (design section 9): a read-only forward hook is replayed and sees the
  same values as on the python path; a hook that writes an output with `gm` ops ends up in the
  graph; a hook that writes an output and cannot be traced makes the ESP fall back to the python
  path (graph break) with the same results, and the fallback is reported.

- Existing ESP and physics tests: unchanged and green.
- Equivalence: numpy backend vs python backend on the short-window dataset, documented relative
  tolerance `1e-12`.
- Trace: the ESP graph has parameters and constants as named inputs, no baked-in parameter
  values; retrace happens only when a guard changes.
- Outputs: every ESP output (from `_compute_outputs` and formulas) comes out of the traced
  numpy run and matches the python backend; `gm.no_outputs()` works on the traced path.
- Errors: a `check` inside the unselected branch of `where` does not raise; one in the selected
  branch raises the right `gm.errors` class with the original message and points to the physics
  source line.

## 6. Benchmark and report

- A script (not a test) under `scripts/` that runs the ESP over the short-window dataset tick by
  tick (current path) and as one traced numpy call, and prints both times and the speedup.
- Write `.tmp/native-engine/esp-benchmark.md` with the numbers, trace time, and what dominated
  the remaining time.
- Final report to me: commits, the composite-outputs changes, the two speed numbers (section 2 and section 6), the pydantic
  audit summary, every design decision that turned out hard or wrong, and the next step you
  recommend.
