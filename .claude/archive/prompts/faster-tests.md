# Task: Make the test suite fast, keep it fast, and document how

## 0. Context and rules

Work on branch `refactor` (after any prompts already applied). Work directly on branch `refactor` (no new branch). Commit on `refactor`; at the end `git push origin refactor`. No PR, no other branches. Read `AGENTS.md`, `.claude/docs/*`,
`pyproject.toml` (pytest config), `tests/conftest.py` and every conftest, all tests, and the CI
workflows first.

Goal: day-to-day `pytest` finishes in **under 30 s**; the full suite (incl. e2e) in CI is as
fast as possible. Nothing that is tested today stops being tested.

Rules:
- No physics, numbers or public API change. No test is deleted, skipped or weakened to gain
  speed; a test may only be moved to a slower tier, made to use less data while checking the
  same property, or made to share setup.
- Golden values, e2e metrics and replay/simulate results must stay identical (the new fast-dataset
  goldens are generated from the unchanged code, see phase 2). No dataset or golden is deleted.
- black / isort / flake8 clean. Commit per phase.

## 1. Phase 0: measure

- Run `pytest --durations=50 -q` and `pytest -m "not e2e" --durations=50 -q`; record wall time
  and the 50 slowest tests.
- Profile the 5 slowest tests (`python -m cProfile -o ... -m pytest <test>` or `pyinstrument`)
  and note where time goes (data loading, fixture setup, number of engine steps, fluid
  properties, legacy conversion, ...).
- Write the numbers to `docs/testing/speed.md` (before section).

## 2. Phase 1: tiers and markers

- Markers in `pyproject.toml`: `unit`, `integration`, `e2e`, `slow` (registered, `--strict-markers`).
  Apply them consistently (by folder via `conftest.py` hooks where possible, so new tests get
  the right marker automatically).
- Default `addopts` runs everything except `e2e` and `slow`:
  `pytest` = fast tier; `pytest -m "e2e or slow"` = slow tier; `pytest -m ""` = all.
- Any single test over ~1 s in the fast tier must be made faster (phases 2–4) or moved to
  `slow` with a one-line reason in its docstring.

## 3. Phase 2: less data, same checks

- Tests that replay/simulate the full 2024 dataset to check behaviour (not a yearly metric)
  use a short window (e.g. 2–7 days) via a shared fixture. Choose the window so the same code
  paths run (e.g. it includes a gap, a control change, a checkpoint boundary if the test needs
  one).
- Two datasets, both kept in the repo (**never delete or shrink any existing dataset, data file
  or golden**; only add):
  - **fast**: one fixed calendar month of the 2024 dataset (pick a representative month, say
    which and why), stored next to the full one, e.g.
    `examples/shared/doublet_heat/doublet_2024_15min_month.csv`, generated from the full file by
    a small reproducible script in `tests/fixtures/` (or through the legacy bridge example if
    that is where data files are produced).
  - **slow**: the existing full-year dataset, unchanged.
- A pytest option/fixture selects the dataset: `--dataset=fast` (default) or `--dataset=slow`.
  The e2e tests (one per mode: replay, simulate, live if it exists) run on whichever is selected
  and compare with the goldens of that dataset.
- Goldens: the existing full-year goldens stay as they are (slow dataset). Before adding the
  fast ones, run the e2e tests on the slow dataset with the current code and confirm they still
  match (record in `docs/testing/speed.md`). Then generate the fast-dataset goldens from the
  same current code and record how (script/command in `tests/fixtures/`).
- Short-window behaviour tests (phase 2 first bullet) always use the fast dataset or a slice
  of it.

## 4. Phase 3: shared setup

- Expensive, read-only setup becomes `scope="session"` (or `module`) fixtures in `conftest.py`:
  loading `plant.json`, the CSV/`Dataset`, legacy bridge conversion, building the shared plant.
  Tests that mutate get a cheap copy (`copy.deepcopy` or `load_state_dict` into a fresh plant),
  never the shared object.
- Remove duplicate local helpers that rebuild the same things.

## 5. Phase 4: parallel and caching

- Add `pytest-xdist` to dev dependencies; make the suite safe for `-n auto` (no shared temp
  files, use `tmp_path`; no global state leaking between tests; contextvars/runtime settings
  restored). Run `pytest -n auto` and `pytest -n auto -m ""` and fix any order-dependent failure.
- Profile-driven caching only: if fluid-property or correlation calls with identical inputs
  dominate, add a bounded cache (`functools.lru_cache` on a pure function, keyed on SI floats)
  in `core/physics`. Must be pure, results bit-identical, documented. No caching of anything
  that depends on mutable state.

## 6. Phase 5: CI

- Pull requests and pushes to feature branches: fast tier, then e2e on the **fast** dataset
  (`-n auto -m "e2e or slow" --dataset=fast`).
- Merge to `main` (push to `main` and PRs targeting `main` before merge, e.g. a required job or
  `merge_group`): full suite on the **slow** dataset (`-n auto -m "" --dataset=slow`). This is
  the gate for merging.
- pip cache enabled; same total coverage as before.

## 7. Phase 6: guard and document

- Add a check that fails the fast tier if it exceeds a budget: e.g. a `conftest.py` hook that
  reports any fast-tier test slower than 1 s as a failure with a clear message
  ("move it to slow or make it faster, see .claude/docs/testing.md").
- Write `.claude/docs/testing.md` (create or update) as the single source on testing:
  folder layout (unit mirror, integration, e2e, fixtures), markers and tiers, the commands,
  the speed budget, the fast/slow datasets and `--dataset` (which CI job uses which, never delete
  datasets or goldens), how to use shared session fixtures and the short-window fixture, when a
  test may be `slow`, xdist rules (use `tmp_path`, no global state), how goldens are produced.
- `AGENTS.md`: add a short "Start here" section at the top telling every new session to read
  `.claude/docs/` first (list each file with one line on what it covers), and to update the
  relevant doc in the same commit whenever it changes behaviour, structure or conventions.
  If a `CLAUDE.md` exists, make it point to `AGENTS.md`; if not, create a two-line `CLAUDE.md`
  that does.
- Update `README.md` testing commands and `CONTRIBUTING.md` if they mention tests.
- Finish `docs/testing/speed.md` with the after numbers.

## 8. Done when

- `pytest` (fast tier) < 30 s on the dev machine; report the exact time.
- `pytest -m ""` passes with the same number of tests as the baseline (list any test moved
  to slow).
- Golden values, e2e metrics, replay/simulate results identical.
- Lint clean; CI config updated.

## 9. Final report (last message)

1. Before → after: fast tier, full suite, with and without `-n auto`.
2. The 10 biggest wins (test or fixture, before → after, what changed).
3. Tests moved to `slow`/`e2e` and why.
4. Caches added (function, hit rate on the full replay) or "none".
5. Docs changed (`.claude/docs/testing.md`, `AGENTS.md`, `CLAUDE.md`, README, CONTRIBUTING).
6. Lint/test summary lines.
