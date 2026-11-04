# Task: clean gemini after the refactors: no wrappers, least code, fix what is wrong

## 0. Context and rules

- This is a new session. Read `AGENTS.md` and every file in `.claude/docs/` first and follow them.
- **Run this after `prompts/gemini-case.md`** has been run and pushed. Start from the pushed `refactor` head in `/Users/sahand/Desktop/crust-team/gemini`; `git status` must be clean and `git pull origin refactor` must succeed. No other Claude session works inside `gemini/`.
- **Why this task exists:** during earlier refactors, old code was sometimes left in place and a new wrapper, adapter, shim or second helper was written around it, instead of the old code being updated. The package works, but it is dirtier and longer than it needs to be.
- **Goal:** the least code that does the job, one implementation per concept, every problem you find fixed. Keep every feature and every public name of `api.md` exactly as it is (names, signatures, return shapes). Numbers of the sample cases must not change, unless a change fixes a bug you show with a failing test first.
- **The rule (unchanged):** gemini is general; no competition number, name or default in `gemini/`. No defaults for anything a user must decide. One unit format (`Quantity`, SI inside).
- **Breaking internal changes are fine**; public API changes are not. If a public name is itself a wrapper that should go, do not remove it: list it in the report as a proposal.
- **Git:** work on `refactor`, one commit per folder group (section 2), in order. At the end, if the development tests and the e2e tier pass, `git push origin refactor` and report the hash.
- **Scope:** only the gemini repository. Read `../geomind/` and `../backend/`, never change them.
- **Temporary files** go to `.tmp/cleanup/` (git-ignored).

### You are the coordinator

Run the work in parallel and do not spend your own context doing it. You plan, hand out tasks, review short reports and diffs, decide, merge, and run the tests once. You never edit more than a few lines yourself and never read large files whole; a worker does that and reports a summary.

- Workers are subagents. Audits (read-only) use haiku; fixes use sonnet. Each fix worker works in its own git worktree on a temporary branch, owns a fixed list of folders, commits once, runs only the tests of its files, and answers with at most 20 lines: what changed, lines removed and added, tests run, open problems. Details go to `.tmp/cleanup/<worker>.md`.
- Never run the same full test set twice without a change in between. Remove the worktrees and temporary branches at the end. Target: about an hour.

### What counts as a problem

Each finding gets one of these labels:

1. **wrapper**: a function, class or module that only forwards to another one (renames arguments, re-exports, converts and calls), where the callers could call the real one;
2. **shim**: code kept for an old name, an old shape or an old call path (`legacy`, `compat`, `old_`, `_v1`, deprecated branches, "kept for", aliases);
3. **duplicate**: two implementations of one concept (two unit converters, two ways to read a profile, two balance checks, two registries);
4. **dead**: unused functions, parameters, branches, imports, constants, files; parameters always passed the same value;
5. **indirection**: a layer, base class, factory, registry or config object with one user, that only makes the code longer;
6. **magic**: hidden behaviour (`__getattr__` tricks, metaclass or decorator side effects, implicit registration) where a plain call would do, except the agreed automatic registration of modules;
7. **bug**: wrong behaviour, a wrong unit, a silent fallback, a swallowed error, a hidden default, a check that can never fail;
8. **quality**: breaks the quality bar of `conventions.md` (nesting over 3, functions over about 40 lines, complexity over 10, comments inside code, unclear names, golfed code, missing `gm.errors` code).

## 1. Audit (parallel, read-only, haiku)

- Run `scripts/` line counts and `flake8 --max-complexity=10` once and save them to `.tmp/cleanup/before.txt`.
- One audit worker per folder group of section 2. Each reads its folders and writes `.tmp/cleanup/audit-<group>.md`: one line per finding: label, `file:line`, what it is, the proposed fix (what to delete, what to call instead), the callers it touches, the risk. Use `git log -S` / `git blame` where it shows that code was wrapped instead of updated.
- Each worker also lists, for its folders, every public name and whether it is a wrapper of another public name.
- You read only the audit summaries, merge them into `.tmp/cleanup/plan.md`, decide per finding (fix, keep with reason, or propose in the report), and resolve findings that cross groups by giving each to one owner.

## 2. Fix (parallel, sonnet, one worktree per group)

Folder groups (one fix worker each, owning only these folders and their tests):

- **G1:** `units/`, `types/`, `errors/`, `_utils/`;
- **G2:** `modules/` (all categories), `physics/`;
- **G3:** `plants/`, `case/`;
- **G4:** `engine/`, `run/`, `ops/`, `runtime/`, `compiler/`;
- **G5:** `evaluate/`, `study/`, `analysis/`, `data/`;
- **G6:** `tests/`, `scripts/`, `examples/`: tests and helpers that duplicate each other, fixtures nobody uses, tests that test a wrapper instead of the real code.

Rules for the fix workers:

- Delete the wrapper or shim and update every caller to the real code. Never add a new layer to remove an old one.
- Merge duplicates into the one implementation that fits the conventions best; say which one survived and why.
- Remove dead code outright; no commented-out code, no "unused" markers.
- A bug fix starts with a failing test.
- Keep every public name and signature of `api.md`; keep every feature.
- A caller outside the worker's folders is changed by its owner: write it in your report and you, the coordinator, hand it over.
- Numbers of the sample cases identical before and after.

You merge G1 to G6 in order (G1 first: others import it), hand any conflict back to the owner, and run the development tests once.

## 3. Guards

Add or extend quality tests in `test_code_quality.py` so the dirt does not come back:

- no public function whose body is only a call to another gemini function with the same arguments;
- no names containing `legacy`, `compat`, `deprecated`, `_old`, `_v1`, `_v2` outside `data/legacy` (if that reader is still a public feature);
- no unused private function (a simple AST check of definitions against references inside `gemini/`);
- the flake8 complexity limit enforced in the test run.

## 4. Docs

Update `conventions.md` with the rule "update the code, never wrap it": when a refactor changes a name or a shape, every caller is changed in the same task, and no wrapper, alias or shim is written. Put the same rule in `AGENTS.md` and the Claude coding rules. Update every doc the fixes touched.

## 5. Report

- Commits, one per group, and the pushed hash.
- Lines of `gemini/` before and after, per folder; flake8 complexity findings before and after.
- Every finding with its label, its fix, or why it was kept.
- Every bug found, with its test.
- Public names that are wrappers and should go (proposals only).
- Anything in `../geomind/` or `../backend/` that calls internals removed here (read-only, file and line).
