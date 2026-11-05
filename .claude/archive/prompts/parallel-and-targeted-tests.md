> OBSOLETE: merged into full-cleanup.md (section 2b). Do not run.

# Task: Tests always run in parallel, verification under 120 s, and only relevant tests per change

Work directly on branch `refactor` (no new branch). Commit on `refactor`; at the end `git push origin refactor`.
No PR. Read `AGENTS.md`, `.claude/docs/*` (especially `testing.md`), `pyproject.toml`, all
`conftest.py` files and the CI workflows first.

Rules: no physics, numbers or API change; no test deleted, skipped or weakened; no dataset or
golden deleted. black / isort / flake8 clean.

## 1. Parallel by default

- `pytest-xdist` in dev dependencies; `addopts` in `pyproject.toml` includes `-n auto` (plus
  `--dist loadgroup` if some tests must share a worker; mark those with
  `@pytest.mark.xdist_group`). Plain `pytest` is always parallel.
- Make every test xdist-safe: `tmp_path` only, no shared files, no global/runtime state leaking,
  session fixtures read-only. Run `pytest` 3 times and `pytest -p no:randomly` / random order if
  available; fix any flaky or order-dependent test.

## 2. Hard budget: 120 s

- Default `pytest` (fast tier, fast dataset, parallel) must finish in **< 120 s** wall time on the
  dev machine; target well below.
- Add a guard in the root `conftest.py`: at session end, if the default run took longer than
  120 s, fail with the 10 slowest tests and a pointer to `.claude/docs/testing.md`. Keep the
  existing per-test guard.
- If the budget is not met: profile (`--durations=30`), then shorten data, share fixtures, or
  move tests to `slow` (with a one-line reason) until it is. Report what you did.
- The slow tier / slow dataset stays for CI before merging to `main` only; it has no 120 s limit.

## 3. Only relevant tests while working

- Add `scripts/test_changed.py` (and a `make test-changed` / documented command) that:
  1. takes the changed files (`git diff --name-only` against `HEAD` and the working tree, or
     against a given ref with `--base`);
  2. maps them to tests: `gemini/<path>/<name>.py` → `tests/unit/<path>/test_<name>.py` (mirror
     rule), plus integration/e2e tests that import the changed module (find by import scan, cache
     the import map); changed test files run themselves; changes in `conftest.py`,
     `pyproject.toml`, `gemini/core/modules/module.py`, the engine or shared types → the whole
     fast tier;
  3. runs `pytest -n auto` on that selection and prints which tests it chose and why.
- Unit test for the mapping logic (fast).

## 4. Documentation (so every new session follows it)

- `.claude/docs/testing.md`: add a section "How to verify a change", the single rule for agents
  and humans:
  1. while working: run only the relevant tests (`scripts/test_changed.py`);
  2. before every commit: run the default `pytest` (parallel, fast tier, < 120 s);
  3. never run the slow tier / slow dataset locally unless asked; CI runs it before merging to
     `main`;
  4. any new test must be xdist-safe and keep the default run under 120 s.
- `AGENTS.md` "Start here": one line pointing to this rule. `CLAUDE.md` still points to
  `AGENTS.md`.
- `README.md` / `CONTRIBUTING.md` test commands updated.

## 5. Report (last message)

1. Default `pytest` wall time (3 runs) and full suite time, before → after.
2. Tests fixed for xdist safety or flakiness.
3. Anything moved to `slow` and why.
4. Example output of `scripts/test_changed.py` for a change in one leaf module and for a change
   in `module.py`.
5. Docs changed. Lint/test summary lines.
