# Task: a fast year run, eager and compiled (on its own branch, in parallel with another session)

## 0. Context and rules

- This is a new session. Read `AGENTS.md` and every file in `.claude/docs/` first and follow them (start with `engine.md`, `conventions.md`, `testing.md`).
- **Another Claude session is working at the same time** in `/Users/sahand/Desktop/crust-team/gemini` on branch `refactor` (the `gm.Case` task). You must not touch that folder or that branch.
  - Create your own worktree and branch from the pushed `refactor`:
    ```
    cd /Users/sahand/Desktop/crust-team/gemini
    git fetch origin
    git worktree add ../gemini-speed -b speed origin/refactor
    cd ../gemini-speed
    ```
  - Work only in `../gemini-speed` on branch `speed`. Your own temporary worktrees go under `../gemini-speed-tmp/` with branch names starting `speed-`. Never delete or reset a worktree or branch you did not create.
  - At the end push `origin speed` only. Do not merge into `refactor` and do not push `refactor`; the merge is done after the other task finishes.
- **Why:** a year of a plant with loops (bypasses, mixing back, recirculation) takes about 6 to 9 seconds, because those plants run row by row (`engine/eager.py`: a module that `_iterates()` or is `stateful` is called per row). The design study (`minimize`, `sample`, `sensitivity`) runs the year hundreds of times, so the year run sets how long every design study and every agent run takes.
- **Goal:** the same numbers, much faster, in both eager mode and with the optional compiler. Target: a daily year of the two-doublet heating and cooling sample plant in under 1 s eager and under 0.5 s compiled, on this machine, after warm-up. If a target cannot be met, get as close as the design allows and explain what limits it.
- **Your files:** `gemini/engine/`, `gemini/ops/`, `gemini/compiler/`, `gemini/runtime/`, their tests, and `scripts/bench*.py` (new). Do **not** change `gemini/run/`, `gemini/plants/`, `gemini/modules/`, `gemini/physics/`, `gemini/evaluate/`, `gemini/optim/`, `gemini/data/`, `examples/`, `inputs/`, or any public signature: the other session rewrites those. If a speed-up needs a change there (a module's `forward`, `simulate`'s arguments), do not make it: write it in the report with the expected gain.
- **Rules that stay:** gemini is general (no competition number or name in code); the run needs no compiler (nothing outside `compiler/` imports it; the compiler registers itself); every value inside the engine is plain SI; one implementation per concept; no wrappers, shims or aliases: update the code, never wrap it.
- **Numbers identical:** every result column of the benchmark runs equal to the baseline within a relative 1e-9 (same failed steps, same errors). A loop solved for all rows at once must reach the same tolerance as row by row; if a row converges differently, that is a bug to fix, not a tolerance to loosen.
- **Git:** one commit per section on `speed`. Push `origin speed` at the end if the development tests and the e2e tier pass.
- **Temporary files** go to `.tmp/speed/` (git-ignored).

### You are the coordinator

Run the work in parallel and do not spend your own context doing it. You plan, hand out tasks, review short reports and diffs, decide, merge onto `speed`, and run the tests once. You never edit more than a few lines yourself and never read large files whole; a worker does that and reports a summary.

- Workers are subagents on sonnet; read-only searches and profiling summaries use haiku. Each fix worker works in its own worktree under `../gemini-speed-tmp/` on a `speed-*` branch, owns a fixed list of files, commits once, runs only the tests of its files, and answers in at most 20 lines: what changed, timing before and after, tests run, open problems. Details go to `.tmp/speed/<worker>.md`.
- Never run the same full test set twice without a change in between. Remove your temporary worktrees and branches at the end (only yours).
- **Machine load:** the other session runs tests at the same time. Benchmarks: run each case 5 times and keep the median; say the load (`uptime`) next to each number. A 1 s budget test that fails: rerun it alone before treating it as a failure, and say which tests you retimed.

### Tests

- Development profile only (`make test` / `scripts/test_changed.py`, always with `test_code_quality.py`), parallel, under 300 s. New fast tests under about 1 s each. Never run the slow dataset locally. Never delete or shrink goldens.
- Quality bar as in `conventions.md`: nesting at most 3, functions about 40 lines, guard clauses, explicit `gm.errors` codes, no comments inside code (docstrings only), black, isort and flake8 clean, a failing test before each bug fix.

## 1. Benchmark and profile (one worker, then you decide)

- Add `scripts/bench_year.py`: runs, eager and compiled, a daily year and an hourly month of each sample plant in `inputs/examples/` with its problem file, plus one small plant without loops. It prints, per run: wall time (median of 5 after one warm-up), rows run row by row versus on arrays, loop iterations, and the top 10 functions by cumulative time (`cProfile`). It writes `.tmp/speed/bench-<label>.json`. It only calls public gemini names that exist on the branch today.
- Save the baseline numbers (every result column) to `.tmp/speed/baseline.parquet` (or `.npz`), and a small checker script that compares a run against it at 1e-9.
- Report to the coordinator: where the time goes (row-by-row loops, Python overhead per call, unit handling, result assembly, health checks, dispatch), with percentages. You choose the work of section 2 from this, and write the plan to `.tmp/speed/plan.md`.

## 2. Speed-ups (parallel workers, disjoint files)

Default split; change it only if the profile shows the time elsewhere, and keep the files disjoint:

- **W1, loops on arrays (eager):** owns `engine/eager.py`, `engine/rows.py`, `engine/step.py`, `engine/runner.py`, `engine/chunks.py`. Solve loops for all rows at once: iterate the loop's fixed point on whole arrays, with a mask of the rows that have converged, so only the unconverged rows keep iterating; fall back to row by row only for modules with state between steps (`stateful`), and only for the steps that need it. Keep failure handling per row (a failed row is recorded exactly as today).
- **W2, loops in the compiled graph:** owns `compiler/`. The same masked fixed-point iteration as a graph construct, so a compiled plant with loops runs on arrays too; reuse the graph cache across trials of a design study (same structure, other parameter values) so a study compiles once.
- **W3, per-call overhead:** owns `ops/`, `runtime/`, `engine/evaluation.py`, `engine/columns.py`, `engine/outcome.py`, `engine/health.py`. Cut the Python work per call: dispatch lookups, repeated array allocation and conversion, health checks run row by row when they could run on arrays, result columns built more than once.
- Each worker: before and after timings from `scripts/bench_year.py`, and the checker at 1e-9 on every benchmark run.
- You merge W1, W2, W3 in that order, hand any overlap back to its owner, rerun the benchmark and the checker once, and the development tests once.

## 3. Guards and docs

- A fast test that a small plant with a loop runs on arrays (no row-by-row call), eager and compiled, with the same numbers as row by row.
- A timing test in the e2e tier only: the daily year of the sample plant under a budget of 3 times the measured eager time (so it catches a large regression without being flaky).
- Docs: `engine.md` (how loops and stateful modules run, eager and compiled), `testing.md` (the benchmark script and how to read it), "unreleased changes" in `api.md` only if something public changed (it should not).

## 4. Report

- Commits on `speed` and the pushed hash; your worktrees and branches removed.
- A table of every benchmark run: baseline, after each section, eager and compiled, with the load.
- Whether the targets were met, and what limits the rest.
- The checker result (all runs equal at 1e-9, or each difference with its cause).
- Every speed-up that needs a change outside your files (module `forward`, `run/`, public signatures), with the expected gain.
- Files changed, so the merge into `refactor` after the `gm.Case` task can be planned; list any file both tasks are likely to have touched.
