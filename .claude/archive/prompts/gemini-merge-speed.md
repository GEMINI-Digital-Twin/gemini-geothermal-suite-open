# Task: merge `speed` into `refactor` now, while another session works

## 0. Context and rules

- This is a new session. Read `AGENTS.md` and `.claude/docs/testing.md` first.
- `origin/speed` (`8fbe403`) was built on `origin/refactor` at `ab9e754` and only changes `gemini/engine/`, `gemini/ops/`, `gemini/compiler/`, `gemini/runtime/`, `gemini/plants/_utils/loops.py`, `gemini/modules/module.py`, their tests, `scripts/bench*.py` and docs. It makes loops run on arrays (eager and compiled) with the same numbers (1e-9).
- **Another Claude session is working right now** in `/Users/sahand/Desktop/crust-team/gemini` on `refactor`, with local commits not yet pushed, and its own worktrees under `../gemini-blockers-tmp/` on `blockers-*` branches. **Never touch that folder, those worktrees or branches**: no checkout, reset, stash, pull or commit there.
- So do the merge in your own worktree from the pushed `refactor`:
  ```
  cd /Users/sahand/Desktop/crust-team/gemini
  git fetch origin
  git worktree add ../gemini-merge -b merge-speed origin/refactor
  cd ../gemini-merge
  ```
  Work only in `../gemini-merge`. Temporary files go to `.tmp/merge/` (git-ignored).
- The machine is loaded by the other session's tests: for each timing take the median of 5 and say the load (`uptime`). A 1 s budget test that fails is rerun alone before it counts; say which tests you retimed.
- Rules that stay: update the code, never wrap it; no comments inside code; no change of numbers.

## 1. Merge

1. Check `git log --oneline -1 origin/refactor` is still `ab9e754`. If someone pushed `refactor` since, merge onto that newer head the same way and say so.
2. `git merge --no-ff origin/speed -m "Merge speed: loops on arrays, eager and compiled"`.
3. On a conflict: keep refactor's behaviour and names and re-apply speed's change on top; never bring back a removed wrapper or old name. List every conflicted file and how you resolved it.

## 2. Checks (once each)

- Development tests (`make test` / `scripts/test_changed.py` against `origin/refactor`, with `test_code_quality.py`), parallel, under 300 s.
- `python scripts/bench_year.py`: eager and compiled daily year of every sample plant, median of 5, with the load.
- Every example in `examples/` on the merge and on `origin/refactor` (a second worktree `../gemini-merge-base` at `origin/refactor`, removed afterwards): printed numbers equal; time of each.
- The e2e tier.

## 3. Push and tidy

- If all pass: `git push origin merge-speed:refactor` (a fast-forward of `origin/refactor`). If the push is rejected because `refactor` moved, stop and report; never force.
- Do not delete `origin/speed`.
- Remove `../gemini-merge`, `../gemini-merge-base` and the local `merge-speed` branch. Also remove the finished speed worktree `../gemini-speed` and its local `speed` branch, and any `../gemini-speed-tmp/` worktrees and `speed-*` branches, only if `git status` there is clean and its last commit is in `origin/speed`; otherwise list them and leave them.

## 4. Report (at most 25 lines)

- Merge hash pushed, conflicts and resolutions (expected: none).
- Test results, and the tests you retimed.
- Benchmark table (eager and compiled, with load) and the time of every example, before and after.
- Any number that changed (expected: none).
- One line for the other session: the new `origin/refactor` hash it must merge before its push.
