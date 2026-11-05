# Task: rename the branches of gemini (`refactor` -> `dev`), set the branch rule, rename the competition folder

## 0. Context and rules

- Run this only after the blockers session has pushed `refactor` and finished. No other Claude session may be working in this repository. Work in `/Users/sahand/Desktop/crust-team/gemini`.
- Small task: do it yourself, no subagents.
- Why: `refactor` no longer says what the branch is. The new scheme:
  - `main`: stable line (competition delivery, releases). Not changed by this task.
  - `dev`: the development line, replacing `refactor`.
  - `feature/<name>`, `fix/<name>`, `docs/<name>`: one task each, short lowercase names with hyphens (for example `feature/study-speed`, `fix/budget-tests`); branched from `dev`, merged back into `dev`, then deleted locally and on `origin`.
  - Temporary worker branches and worktrees of a coordinator session stay local, are never pushed, and are removed at the end of the task.
  - Git cannot hold both `dev` and `dev/<name>`, so task branches use the prefixes above, never `dev/...`.
- Never force-push, never rewrite history, never delete `main`.

## 1. Checks

- `git status` clean; `git fetch origin --prune`; `git worktree list` shows only the main worktree (if any other is listed, stop and report).
- `git rev-parse origin/refactor` equals the local `refactor`; `origin/speed` is an ancestor of `origin/refactor` (`git merge-base --is-ancestor origin/speed origin/refactor`). If either fails, stop and report.

## 2. Rename

```
git checkout refactor
git branch -m refactor dev
git push -u origin dev
git tag archive/speed origin/speed
git push origin archive/speed
```

## 3. Rule and references (one commit on `dev`)

- `AGENTS.md`, section "Branching": replace the rule with the scheme of section 0 (`dev` as the development line, the three prefixes, merge into `dev` then delete, local-only worker branches, no `dev/...` names, `main` only on the user's request).
- Every other place that names the branch `refactor` (docs, scripts, CI, `Makefile`, `scripts/test_changed.py` default base, prompts or notes in the repo): change it to `dev`. Do not rename `refactor-notes.md` or change the words "refactor" / `NOTE(refactor)` where they mean a code change, not the branch. List each changed line in the report.
- CI: `.github/workflows/*` run on every branch (`"**"`); keep that, and check nothing else names `refactor`.

## 3b. Rename the competition sample folder (one commit on `dev`)

- The competition is the 2026 GeoHackathon, so the folder is named after it: `git mv inputs/examples/hackathon_2027 inputs/examples/hackathon_2026`.
- Change every reference (`git grep -n hackathon_2027`: about 23 lines in `.claude/docs/`, `README.md`, `examples/`, `scripts/bench_year.py`, `tests/fixtures/sample_cases.py`, and any golden or schema that stores the path). Do not leave an alias or a fallback to the old name.
- Do **not** change the data: the demand year stays 2027 (the official files `GEMINI_*_Demand_Daily_2027.csv` keep their names, and `case.json` keeps its `time` range). The folder README says in one line: "Sample of the SPE Europe Energy GeoHackathon 2026; the demand profiles are for the year 2027."
- If a test pins a hash or a stored path that contains the folder name, update it and name it in the report.

## 3c. Tests and push

- Development tests once (`make test` with `test_code_quality.py`); a 1 s budget test that fails is rerun alone before it counts.
- Every example in `examples/` runs and prints the same numbers as before the rename (run `hackathon.py` once).
- `git push origin dev`.

## 4. Remove the old branches

Only after `origin/dev` holds the commits of sections 3 and 3b:

```
git push origin --delete refactor
git push origin --delete speed
```

Delete any local branch other than `main` and `dev` that is fully merged into `dev` (`git branch --merged dev`); list any branch that is not merged and leave it.

## 5. Report (at most 15 lines)

- `origin/dev` hash; branches on `origin` now (`git ls-remote --heads origin`); the tag.
- Every changed reference (branch and folder), and the new "Branching" text.
- Test result.
- Remind the user: on GitHub, Settings -> Branches -> default branch -> `dev` (this cannot be done from git), and every open clone must run `git fetch --prune && git checkout dev`.
