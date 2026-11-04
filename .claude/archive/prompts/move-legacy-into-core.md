# Task: Move `gemini/legacy/` into `gemini/core/legacy/`

Work on branch `refactor` (after any prompts already applied). Work directly on branch `refactor` (no new branch). Commit on `refactor`; at the end `git push origin refactor`. No PR, no other branches. Read `AGENTS.md` and
`.claude/docs/conventions.md` first.

Change **location only**: no code, behaviour, numbers or file formats change.

1. Baseline: run full `pytest` and note the summary line.
2. `git mv gemini/legacy gemini/core/legacy` (keep history).
3. Update every import and reference in `gemini/`, `tests/`, `examples/`, `docs/`,
   `.claude/docs/`, `AGENTS.md`, `README.md`, `pyproject.toml` (package data, entry points,
   coverage paths, lint excludes) and CI workflows: `gemini.legacy` → `gemini.core.legacy`.
   Fix relative imports inside the moved package.
4. Public access stays `gm.legacy.<...>`: in `gemini/__init__.py` import it from the new place
   (`from gemini.core import legacy`). Do not keep a `gemini/legacy` package or any alias module.
5. Tests mirror the package: move `tests/unit/legacy/` → `tests/unit/core/legacy/` with
   `git mv`; integration/e2e tests stay where they are, only imports change.
6. Check the dependency rule in `conventions.md` (no upward imports): if `core` modules other than
   `core/legacy` now import `legacy`, or `legacy` imports something above `core`, report it and
   fix it without changing behaviour; update the rule text to mention `core/legacy`.
7. `grep -rn "gemini.legacy\|gemini/legacy" .` must return nothing outside git history.
8. black / isort / flake8 clean; full `pytest` green with the same test count as the baseline;
   run the legacy bridge example once and confirm it regenerates identical files
   (`git status` clean afterwards).

Commit: `refactor: move legacy into core`.

Final report: moved paths, files whose imports changed (count), any dependency-rule issue found,
`pytest` summary before → after, bridge example check result.
