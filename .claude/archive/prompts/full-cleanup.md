# Task: Full codebase review and cleanup — `utils`, `errors`, consistency, no framework names

This replaces the older `audit-and-cleanup.md` prompt (do not run that one).

## 0. Context and rules

- Work directly on branch `refactor` (no new branch). Commit on `refactor`; at the end
  `git push origin refactor`. No PR.
- Read `AGENTS.md` and everything in `.claude/docs/` first and follow it.
- **Pre-check:** the earlier tasks must be finished and committed on `refactor` (inputs set by
  the base class, `_compute_outputs`, fixed `forward(self, inlets)` signature, faster tests,
  legacy in `core`). Check: `git status` clean, `forward(self, inlets)` everywhere,
  `gemini/core/legacy/` exists. If anything is
  missing or another task is still running on this repo, **stop and report**; do not start.
- Goal: the simplest, cleanest, most consistent code that does exactly the same thing. Less code
  and fewer concepts, never a new layer for its own sake.
- No behaviour change: golden values, e2e metrics, replay/simulate results, checkpoint format
  stay identical, except items marked `bug` (fix, add a test, report the numeric effect).
  Public API changes are allowed only where listed below or recorded as a public rename.
- No new dependencies, no compatibility shims, no deleted tests, datasets or goldens.
- `git mv` for moves. black / isort / flake8 clean.
- **Temporary files** (audit lists, baselines, notes, scratch) go to `.tmp/` at the repo root,
  never to `docs/`. Add `.tmp/` to `.gitignore` first. If earlier tasks left temporary reports
  under `docs/` (e.g. `docs/cleanup/`, `docs/testing/speed.md`), move them to `.tmp/` and
  remove them from git. `docs/` and `.claude/docs/` hold lasting documentation only.
- **Tests:** follow the two test profiles of section 2b (set them up first). While working and
  before every commit use the **development** profile: only the tests of what changed **and of
  everything that imports it**, in parallel, < 300 s. Never run the whole suite or the slow
  dataset locally; the **release** profile runs in CI. New tests must be xdist-safe.

## 0b. The quality bar (the main goal of this task)

After this task the code must have **fewer bugs** and be **simple, readable and just big
enough**: not so compressed it is clever, not so spread out it is padded. Every existing
feature keeps working. Apply this bar to every file you touch and audit every file against it.

Concrete, checkable rules:
1. **Flat code.** Nesting depth at most 3 inside a function (count `if`/`for`/`while`/`with`/
   `try`). Use guard clauses and early `return`/`continue`; no `else` after `return`/`raise`;
   no pointless indentation (e.g. a `try` or `with` wrapping more than it needs, `if x: return
   True else: return False`).
2. **Small functions.** About 40 lines max per function (excluding docstring); one job each.
   Split only along a real responsibility, never into one-line wrappers.
3. **Low complexity.** Enable flake8's built-in McCabe check: `max-complexity = 10` in the
   flake8 config (no new dependency) and make the whole code base pass it.
4. **Just enough code.** No dead code, no unused parameters or options, no speculative
   generality, no abstraction with a single trivial use, no duplicated logic. But also no
   golfed one-liners, nested comprehensions over two levels, or chained conditionals that
   hide intent.
5. **Clear names.** Full words for concepts (`heat_exchanger`, not `hx`), SI-unit suffix only
   where the type does not carry the unit, booleans read as questions (`is_leaf`,
   `has_children`).
6. **No comments inside code bodies.** The only comments allowed in code are the fixed
   section headers (in `__init__`: `# Modules`, `# Parameters`, `# Inlets`, `# Controls`,
   `# Boundaries`, `# States`, `# Outputs`, `# Outlets`; in `forward`: `# Modules`, `# Outlets`;
   and the agreed headers in other files). No inline/trailing comments, no comment lines between
   statements, no commented-out code. Anything worth explaining (the *why*, units, sources,
   non-obvious physics or numerics) goes into the docstring of the function, class or module.
   Remove the rest; if code needs a comment to be understood, rewrite the code. Exceptions only
   for tool directives (`# noqa: <code>`, `# type: ignore[...]`, `# pragma: no cover`), each with
   a specific code. Write this rule into `.claude/docs/conventions.md` (section "Comments") and
   add a fast test (`tokenize`-based) that fails on any other comment in `gemini/`, `examples/`
   and `tests/`.
7. **Explicit errors.** No bare `except`, no `except Exception: pass`, no silent fallbacks;
   raise `gm.errors` classes with useful messages (section 4.2).
8. **Fewer bugs.** In phase 1 each subagent also hunts for real bugs in its area (edge cases:
   empty data, NaN, zero flow, zero denominators, timezone/DST, off-by-one in windows, unit
   mix-ups, mutable defaults, shared state between calls). Every confirmed bug gets a failing
   test **first**, then the fix. Areas with weak coverage of the main paths get tests added.

Add a fast test (or lint rule) for 1 and 3 so the bar cannot silently drop later, and write the
rules into `.claude/docs/conventions.md` section "Code quality".

## 0c. No magic; simplest for the user, simple inside

- **User side:** the simplest possible API. A user builds a module, sets values, calls it, reads
  outputs; nothing else to learn. Every feature keeps working.
- **Package side:** all features, but the plainest implementation that does the job.
  Explicit over implicit. A reader must be able to follow any call from `module(...)` to the
  physics by reading code top-down, without knowing hidden rules.
- **Not allowed** (remove where found, replace with explicit code):
  - replacing or wrapping a subclass's methods at class creation (e.g. `__init_subclass__`
    assigning `cls.forward = wrapper`); validation belongs in `__call__` only;
  - frame/stack inspection, `sys.settrace`/`setprofile`, `exec`/`eval`, generated code;
  - hidden state on modules that a user did not ask for (e.g. `last_result`,
    `last_results`) unless it is a documented, needed feature with one clear owner;
  - implicit global registries or import-by-string where an explicit reference works (keep only
    what checkpoints/JSON truly need, in one documented place);
  - `contextvars` or other implicit context except the one documented per-call record of the
    base class (and `no_outputs` / runtime settings); no second mechanism for the same thing;
  - metaclasses, descriptors or `__getattr__` tricks beyond the declaration registration that
    `Module.__setattr__` already does;
  - base-class features that only some modules use (move them to where they are used or to a
    small mixin only if several modules need them).
- **When unsure how to implement something** (registration, hooks and handles, containers,
  `state_dict`/`load_state_dict`, `named_modules`, `apply`, context managers like
  `no_outputs`), look at how the PyTorch source (`torch/nn/modules/module.py`,
  `torch/utils/hooks.py`, `torch/nn/modules/container.py`, `torch/autograd/grad_mode.py`)
  solves it and follow the same simple pattern. This is a design reference only: **never name
  PyTorch or torch anywhere in the repo** (section 4.3).

Known candidates from the last pushed state (verify against the current code; they may already
be gone or changed): `Module.__init_subclass__` wrapping `forward`; the `_evaluation`
`ContextVar` that collects child results plus `last_result`/`last_results`;
`Module._import_class` used by checkpoints; `HookHandle` in `module.py` (→ `utils/hooks.py`);
`_nested_get`/`_nested_set` in `engine/step.py` (→ `utils/mappings.py`); `MissingMeasurement`
in `engine/step.py` (→ `gemini/errors/`); `EventLog.attach` registering hooks on every module;
`fidelity`, `soft_sensors`, `health`, `capex`, `cost` on the base `Module`; the Pydantic
`RootModel` helpers `ChildInputs`/`ChildOutputs`. Add every confirmed one to the audit
(category C or A) with the explicit replacement.

## 1. Work in parallel with subagents

Use subagents (the Task/Agent tool) to go faster, with these rules:
- **Phase 1 (audit) is read-only** and fully parallel: one subagent per area (section 3).
  Each writes its findings to `.tmp/cleanup/audit-<area>.md` in the format of section 3.3; you
  merge them into `.tmp/cleanup/audit.md`.
- **Phase 2 (`utils`, `errors`, hooks/events)** touches many files: do it yourself or with one
  subagent, not in parallel.
- **Phase 3 (fixes)** is parallel by **exclusive file ownership**: split the findings into
  groups whose files do not overlap; give each subagent one group and the list of files it may
  edit (it must not touch any other file). Subagents do not commit; you review each group's
  diff, run the relevant tests, and commit per group. Findings that span many files (renames)
  are done by you, serially.
- Give each subagent: the rules of section 0, `AGENTS.md`, `.claude/docs/`, its area or file
  list, and the exact output expected. Tell it to read whole files, not skim.

## 2. Phase 0: baseline

Run the fast tier once (`pytest -n auto`) and `pytest -m "e2e or slow" --dataset=fast`; save test counts, golden
values, e2e metrics, replay/simulate result hashes and timing to `.tmp/cleanup/baseline.md`.
Count lines of `gemini/`, `tests/`, `examples/`.

## 2b. Phase 0b: test profiles (do this before anything else changes)

Two profiles, both always parallel (`pytest-xdist`, `-n auto` in `addopts`; make every test
xdist-safe: `tmp_path` only, no shared files or leaking global/runtime state, session fixtures
read-only; run 3 times to catch flaky/order-dependent tests and fix them):

**development** (default, local, every task, every commit):
- Runs only the tests affected by the change: the tests of the changed files **and the tests
  of every module that imports a changed module, directly or transitively**.
- Implement `scripts/test_changed.py` (+ a documented short command, e.g. `make test`):
  1. changed files = `git diff --name-only` against `HEAD` plus working tree (or `--base <ref>`);
  2. build the import graph of `gemini/` with `ast` (cache it in `.tmp/`), find every module
     that imports a changed module (transitive);
  3. map changed + importing modules to tests: mirror rule
     (`gemini/<path>/<name>.py` → `tests/unit/<path>/test_<name>.py`) plus every test file that
     imports any of them; changed test files and `conftest.py` scopes run themselves; changes
     in `pyproject.toml` or root `conftest.py` → the whole fast tier;
  4. run `pytest -n auto` on the selection with the **fast** dataset and print what it chose
     and why.
- Budget: **< 300 s** wall time. A session-end guard in the root `conftest.py` fails the run if
  a development-profile run exceeds 300 s, printing the 10 slowest tests and a pointer to
  `.claude/docs/testing.md`. Keep the per-test guard (fast-tier test > 1 s).
- Unit tests for the selection logic (fast).

**release** (CI before merging to `main` and for releases):
- Full suite: every tier (`-m ""`), **slow** (full-year) dataset, parallel. No time budget,
  but report its time.
- CI: pull requests / feature pushes run the development profile against the PR base
  (`scripts/test_changed.py --base origin/<base>`); merge to `main` and release tags run the
  release profile and must pass.

Write `.claude/docs/testing.md` section "Test profiles" with exactly these rules, the commands,
the 300 s budget, and the sentence: "Always test what changed and everything that imports it;
never run the full suite locally." Add one line to `AGENTS.md` "Start here" pointing to it.
Commit: `test: development and release profiles`.

## 3. Phase 1: audit (read only, parallel)

### 3.1 Areas (one subagent each)

1. `gemini/core/modules/` (base class, declarations, containers, all equipment, plants)
2. `gemini/core/engine/` and `gemini/core/data/`
3. `gemini/core/physics/` and `gemini/core/types/`
4. `gemini/core/legacy/`, `gemini/optim/`, `gemini/design/`, `gemini/agentic/`, `gemini/__init__.py`,
   runtime
5. `tests/` and `scripts/`
6. `examples/`, `docs/`, `.claude/docs/`, `AGENTS.md`, `CLAUDE.md`, `README.md`,
   `CONTRIBUTING.md`, `pyproject.toml`, `.github/workflows/`

Every tracked text file belongs to exactly one area (generate the list from `git ls-files`).

### 3.2 What to look for

**U. Utilities (to `gemini/utils/`)**: any general-purpose helper not specific to geothermal
physics or to one module: string handling (names, dotted paths, splitting/joining paths, case
conversion, close-match "did you mean" suggestions, formatting values/tables/reprs), time
handling (parsing timestamps, timezones/UTC, step size from an index, ranges/windows, durations
like `"15min"`), nested-mapping helpers (flatten/unflatten by dotted path, deep merge), file
helpers (JSON/CSV read/write with consistent options), the hook handle (`RemovableHandle`),
generic publish/subscribe or event-bus code, small validation helpers. Report each with all
places it occurs (including duplicates).

**X. Errors (to `gemini/errors/`)**: every `raise` and `warnings.warn`: what is raised, where,
message style. Group project-specific situations into proposed error/warning classes.

**F. Framework names**: every occurrence of `torch`, `PyTorch`, `pytorch`, "PyTorch-style",
"like torch" (case-insensitive) in code, comments, docstrings, docs, test names, messages.

**A. Consistency**: naming of the same concept everywhere (modules, classes, functions,
variables, parameters, outputs, bindings, paths, tests, examples); **port and control naming**
(one rule for inlet/outlet names, e.g. `inlet`/`outlet` vs `suction`/`discharge` vs
`hot_in`/`hot_out`, and for controls, e.g. `m_dot` vs `production_rate`; propose the rule and
list every deviation); module structure vs the documented template (section order, `forward`,
`_compute_outputs`, docstrings); SI units inside (conversions only in `core/physics/units.py`
and boundary helpers); error message style; import style and the dependency rule; test mirror
rule, markers, fixtures; examples and docs using the current API; every doc claim that is false.

**Listing methods (decided rule, apply everywhere):** every declaration listing on `Module`
takes `recurse` with **default `True`** and yields dotted paths relative to the module
(`"doublet.production_well.esp.frequency"`), plus a `named_*` form where one exists:
`parameters()`, `controls()`, `boundaries()`, `inputs()`, `outputs()`, `states()` and any other
declaration listing. **Exception:** `inlets()` and `outlets()` are the module's own interface
only (no `recurse` argument), because a child's ports are internal connections, not ports of the
parent. `children()` stays direct children only and `modules()` stays recursive. Audit every
listing for this rule and fix deviations; update callers (engine, legacy, calibration, results)
so behaviour stays identical, and document the rule in `.claude/docs/modules.md`.

**B. Duplication**: same or near-same logic in two places; two public ways to do one thing;
constants defined twice or magic numbers instead of `core/physics/constants.py`.

**C. Simplicity**: dead code (unused functions, classes, parameters, branches, imports, files,
fixtures, docs), wrappers that only forward, options nobody passes, leftovers from earlier
refactors (old names, temporary helpers, stale `NOTE(refactor)`), long/nested functions.

**D. Readability**: unclear or misleading names, functions doing several things, files mixing
responsibilities, ordering inside files, any comment other than the allowed section headers and tool
directives (section 0b rule 6); missing *why* in docstrings for non-obvious physics or numerics.

**E. Correctness smells** (report; fix only if clearly a bug): swallowed exceptions, mutable
defaults, shared mutable state, float equality, timezone handling, off-by-one in time windows,
unit mistakes, unchecked `None`.

### 3.3 Audit file format

`.tmp/cleanup/audit.md`:

```markdown
# Code audit
## Summary
- Files read: N / N
- Findings: N (U x, X x, F x, A x, B x, C x, D x, E x)
- Biggest themes: 3–6 bullets
## Proposed `gemini/utils/` layout (files and what goes in each)
## Proposed `gemini/errors/` classes (name, base classes, where used)
## Proposed port and control naming rule
## Findings
| ID | Category | Severity | File:line | Problem | Proposed fix | Status |
```
- IDs `U-001`, `X-001`, `F-001`, `A-001`, ...; severity `high` / `medium` / `low`.
- One concrete, verifiable sentence each for problem and fix; group the same issue across files
  into one row listing all locations.
- Coverage checklist at the end: every tracked text file with ✓.

The audit stays in `.tmp/` (not committed).

## 4. Phase 2: new packages (serial)

### 4.1 `gemini/utils/`

- Files by topic. Required:
  - `strings.py`: names, dotted paths, case conversion, "did you mean" suggestions, formatting.
  - `time.py`: timestamp parsing, UTC/timezones, step size from an index, ranges/windows,
    durations like `"15min"`.
  - `hooks.py`: `RemovableHandle` (ordered hook dicts, `remove()`, safe double remove), used
    by every hook registration.
  - `mappings.py`: flatten/unflatten nested mappings by dotted path, get/set by path, deep
    merge; replaces every ad-hoc nested-dict helper (e.g. `_nested_get`/`_nested_set`).
  - `context.py`: a small helper that turns a context manager class into something usable as
    both `with ...:` and a decorator (sync functions), contextvars-based and nestable;
    `gm.no_outputs()` and any other on/off context (runtime settings) are built on it.
  - `collect_env.py`: `python -m gemini.utils.collect_env` prints Python, OS, `gemini` version,
    git commit if available, and versions of the main dependencies, for bug reports; mention it
    in `CONTRIBUTING.md`.
  Optional (only if the audit finds a real need): `files.py` (JSON/CSV with consistent options),
  `events.py` (generic publish/subscribe), `timer.py` (a minimal timer, only if timing code is
  duplicated in several places). No `misc.py` / `helpers.py` catch-alls. Do not name a file after
  a standard-library module (`contextlib.py`, `time.py` is allowed only because imports are
  absolute; verify nothing shadows the stdlib).
- `gemini/utils` imports **nothing** from the rest of `gemini` (only the standard library and
  existing dependencies). Physics, units and quantities stay in `core/physics` and
  `core/types`. Code that depends on the engine or modules stays where it is.
- Move each helper, replace every duplicate with the single `utils` version, delete the old
  copies. Unit tests in `tests/unit/utils/` (mirror rule), fast.
- Public access: `gemini.utils.<file>.<name>`; `gemini/utils/__init__.py` exports nothing
  implicitly unless the docs say so.

### 4.2 `gemini/errors/`

```
gemini/errors/
    __init__.py    # re-exports every class; users only use gm.errors.<Name>
    base.py        # GeminiError(Exception), GeminiWarning(UserWarning)
    module.py      # declarations, ports, inputs, outputs
    engine.py      # runs, bindings, datasets, checkpoints
    physics.py     # out of range, no convergence (errors and warnings)
    legacy.py      # converting old GEMINI files
```
- Every class derives from `GeminiError` (or `GeminiWarning`) **and** the matching built-in
  (`ValueError`, `TypeError`, `KeyError`, `RuntimeError`, ...), so existing `except ValueError`
  code keeps working, e.g. `class MissingInputError(GeminiError, ValueError)`.
- `gemini/errors` imports nothing from the rest of `gemini`.
- Replace every project-specific `raise`/`warn` with the right class; keep built-ins for plain
  programming errors where no project meaning exists. One message style: module path, field,
  value with unit, what is expected, and a "did you mean" suggestion where useful (via
  `utils.strings`).
- `gm.errors` exported from `gemini/__init__.py`. Tests assert the class, not only the message.
- Add a file only if it has classes; merge tiny ones rather than keeping empty files.

### 4.3 No framework names

Remove every occurrence found in category F: describe the concept itself instead (e.g.
"declarations are registered in `__init__`", "hooks run before and after `forward`"). Add a
fast test that scans tracked text files (excluding `.git`) and fails if `torch` or `pytorch`
appears (case-insensitive). Git history is not rewritten.

## 5. Phase 3: fixes (parallel by file ownership)

Order:
1. `high` correctness/bug items (each with a test).
2. Dead code and leftovers (C).
3. Duplication (B) — merge into the single right place (often `utils`).
4. Consistency (A) — including the port/control naming rule; one theme per commit.
5. Readability (D).
6. Docs and examples last, so they describe the final code.

For each item: smallest change that fully fixes it; set Status to `fixed (<hash>)` or
`rejected: <reason>` (rare, justified). New problems found while fixing → new rows, fixed too.

Renames that touch the public API, saved files (`plant.json`, checkpoints), data columns or
binding keys: list them under "Public renames" in the audit; regenerate
`examples/shared/doublet_heat/` through the legacy bridge example if needed; the bridge test must
stay green.

## 6. Phase 4: docs

- `.claude/docs/`: add `utils.md` (what lives in `utils`, the no-import rule, how to add a
  helper) and `errors.md` (hierarchy, which class when, message style, how to add one); update
  `conventions.md` (dependency rule incl. `utils` and `errors` as leaf packages, naming rules
  incl. ports/controls, no framework names), `modules.md`, `testing.md` (test profiles stay as in 2b).
- `AGENTS.md` "Start here" lists every doc in `.claude/docs/` with one line each.
- **Examples:** update every file in `examples/` (and the README snippets) to the final API:
  new listing rule, `gm.errors`, `utils`, renamed ports/controls, no comments except section
  headers, quality bar. Each example must run end to end: add a smoke test per example
  (fast dataset / short window; mark `slow` if it cannot stay under ~1 s so it runs in the
  release profile). The legacy bridge example must still regenerate identical files.

## 7. Done when

- Every audit row is `fixed` or `rejected` with a reason.
- Values identical to `.tmp/cleanup/baseline.md` (except documented `bug` fixes); development
  profile green and < 300 s; one final release-profile run (full suite, slow dataset) green;
  test count not lower except tests of deleted code (listed).
- No `torch`/`pytorch` anywhere in tracked files; `utils` and `errors` import nothing else from
  `gemini` (add a fast test for this rule).
- No item of section 0c left; every remaining implicit mechanism is listed in
  `.claude/docs/conventions.md` with why it is needed.
- Quality bar of section 0b met everywhere: nesting ≤ 3, `max-complexity = 10` passes, no
  function over ~40 lines without a stated reason in the report.
- Every example runs (its smoke test passes) and uses the final API.
- Lint clean; pushed to `origin refactor`.

## 8. Final report (last message)

1. Findings per category and severity; fixed / rejected counts.
2. `gemini/utils/` layout: files and what moved in (from where).
3. `gemini/errors/` classes and how many `raise`/`warn` sites now use them.
4. Port/control naming rule chosen and the public renames (old → new).
5. The 10 most important other changes, one line each, with IDs.
6. Deleted files and code (paths, line counts).
7. Bugs found and fixed (each with its new test), with numeric effect.
7b. Quality metrics before → after: functions over complexity 10, max nesting depth, functions
    over 40 lines, total lines.
8. Baseline comparison; development-profile time for a typical change, release-profile time; line counts of `gemini/`, `tests/`,
   `examples/` before → after.
9. How the work was split between subagents.
10. Anything not changed and why. Lint/test summary lines.
