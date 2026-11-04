# Task: Audit and clean up the whole codebase — consistency, duplication, simplicity, readability

## 0. Context, goals, rules

You are in the team repo (package `gemini/`, `examples/`, `tests/`, `docs/`, `.claude/docs/`,
`AGENTS.md`, `README.md`, `pyproject.toml`). Run this **after** the latest refactor task, on branch `refactor`. Work directly on branch `refactor` (no new branch). Commit on `refactor`; at the end `git push origin refactor`. No PR, no other branches.

Goal: the simplest, cleanest, most readable code that still does exactly the same thing.
Nothing new is added; behaviour and numbers do not change.

The task has **two strictly separate phases**:
1. **Audit**: read everything, change nothing, write every problem into one list.
2. **Fix**: work through the list, item by item, until every item is fixed or explicitly
   rejected with a reason.

Do not start phase 2 until the audit file is complete and committed.

Ground rules:
- Follow `.claude/docs/*` and `AGENTS.md`; where the code and the docs disagree, that is itself
  a finding (decide which one is right and record why).
- No behaviour change: golden numbers, e2e metrics, replay/simulate results, checkpoint format
  and public API stay identical, unless an item is a real bug (then mark it `bug`, fix it,
  add a test, and report the numeric effect).
- No new features, no new dependencies, no compatibility shims, no speculative abstractions.
  Simplifying means **less** code and fewer concepts, not a new layer.
- `git mv` for moves; commit per group of related fixes with a message naming the audit IDs.
- black / isort / flake8 clean and full `pytest` green after every commit.

---

## 1. Phase 0: baseline

Run full `pytest`, `pytest -m "not e2e"`, black/isort/flake8, and the replay timing. Save the
outputs (test counts, golden values, e2e metrics, replay/simulate result hashes, timing) to
`docs/cleanup/baseline.md`. Phase 2 must end with identical values.

## 2. Phase 1: audit (read only)

Read **every** file: all of `gemini/`, `examples/`, `tests/`, `docs/`, `.claude/docs/`,
`AGENTS.md`, `README.md`, `CONTRIBUTING.md`, `pyproject.toml`, `.github/workflows/`. Do not skim:
open each file fully. Keep a checklist of files read in the audit file (section 2.3) so
nothing is missed.

### 2.1 What to look for

**A. Consistency**
- Naming: modules, classes, functions, variables, ports, parameters, outputs, bindings, paths,
  test names, example names. Same concept, same name everywhere (e.g. `m_dot` vs `mass_flow`
  vs `flow`, `hx` vs `heat_exchanger`, `T`/`temperature`, `p`/`pressure`).
- Module structure: every module follows the documented style (declarations in `__init__`,
  section comments in order, `forward` shape, docstrings, units in SI, error messages).
- Units: SI inside everywhere; any unit conversion outside `physics/units.py` and the
  boundary helpers; temperature in K; hidden US-unit math.
- Error handling: same style of messages (module path, field, value, unit), same exception
  types for the same situations.
- Docstrings and comments: present where the docs require them, accurate, same style; stale
  comments that describe old code; leftover `NOTE(refactor)` that are no longer true.
- Imports: style, order, public vs private imports, the dependency rule in
  `conventions.md` (no upward imports).
- Tests: mirror rule (`tests/unit` mirrors `gemini/`), naming, fixtures, markers.
- Examples and docs: do they use the current API exactly? Same style across examples.
- Docs vs code: every claim in `.claude/docs/*`, `AGENTS.md`, README, docstrings that is false
  now.

**B. Duplication**
- Same or near-same logic in two places (physics formulas, unit conversions, validation,
  binding handling, result building, file I/O, test helpers, example boilerplate).
- Two ways to do the same thing in the public API.
- Constants defined more than once or magic numbers that should use `physics/constants.py`.

**C. Simplicity**
- Dead code: unused functions, classes, parameters, branches, imports, files, fixtures, docs.
- Over-engineering: abstractions with one user, wrappers that only forward, options nobody
  passes, generality not needed by any caller.
- Long or deeply nested functions that can be flattened; complex conditionals; clever code
  where plain code is clearer.
- Leftovers from earlier refactors: compatibility code, old names, temporary helpers, migration
  scripts, report files that no longer serve a purpose.

**D. Readability**
- Unclear names, abbreviations without reason, misleading names.
- Functions doing more than one thing; files mixing unrelated responsibilities.
- Ordering inside files (public first, helpers after, or the documented order).
- Comments that explain *what* instead of *why*; missing *why* for non-obvious physics or
  numerical choices.

**E. Correctness smells** (report; fix only if clearly a bug)
- Silent exception swallowing, mutable defaults, shared mutable state, float equality,
  timezone handling, off-by-one in time windows, unit mistakes, unchecked `None`.

### 2.2 Audit file format

Write everything to `docs/cleanup/audit.md`:

```markdown
# Code audit

## Summary
- Files read: N / N
- Findings: N (consistency X, duplication Y, simplicity Z, readability W, correctness V)
- Biggest themes: 3–6 bullet points

## Findings

| ID | Category | Severity | File:line | Problem | Proposed fix | Status |
|----|----------|----------|-----------|---------|--------------|--------|
| A-001 | consistency | medium | gemini/core/modules/pumps/esp.py:42 | ... | ... | open |
```
- **ID**: category letter + number (`A-001`, `B-003`, ...).
- **Severity**: `high` (bug, misleading API or doc, real duplication of logic), `medium`
  (inconsistency users or developers will trip on), `low` (style, naming polish).
- **Problem**: one concrete sentence; quote the code when short.
- **Proposed fix**: one concrete sentence (what to delete, merge, rename, move). If several
  findings share one fix, give them the same fix text and reference the main ID.
- **Status**: `open` in phase 1.
- Group related findings (e.g. one naming inconsistency across 12 files = one finding listing
  all locations, not 12 findings).
- No vague findings ("could be cleaner"). Each must be actionable and verifiable.

### 2.3 Coverage checklist

At the end of `audit.md`, list every file read with a ✓ (generated from `git ls-files`,
excluding binary data files). Every tracked text file must appear.

Commit: `docs: code audit` (only `docs/cleanup/`). **Then stop editing the audit structure**;
phase 2 only updates the Status column and adds notes.

## 3. Phase 2: fix

Order:
1. `high` correctness/bug items (each with a test).
2. Dead code and leftovers (C) — deleting first makes the rest smaller.
3. Duplication (B) — merge into the single right place.
4. Consistency (A) — renames and structure, one theme per commit.
5. Readability (D).
6. Docs and examples last, so they describe the final code.

For each item:
- Make the smallest change that fully fixes it.
- Update `Status` to `fixed (<commit short hash>)`, or `rejected: <reason>` if on closer
  inspection the fix would make things worse or change behaviour. Rejections must be rare and
  justified.
- New problems found while fixing → add them as new rows (`A-0xx`, status `open`) and fix them
  too.
- After each commit: lint + `pytest -m "not e2e"`; after each group: full `pytest`.

Renames: if a rename touches the public API, saved files (`plant.json`, checkpoints) or
binding keys, list it in `audit.md` under "Public renames" with old → new, regenerate
`examples/shared/doublet_heat/` through the legacy bridge if needed, and keep the bridge e2e
test green.

## 4. Done when

- Every row in `audit.md` is `fixed` or `rejected` with a reason; no `open` rows.
- Values identical to `docs/cleanup/baseline.md` (same golden numbers, e2e metrics,
  replay/simulate hashes; timing not worse by more than 10%), except documented `bug` fixes.
- Lint clean; full `pytest` green; test count not lower except for deleted tests of deleted
  code (list them).
- Net line count of `gemini/` reported (before → after).

## 5. Final report (last message)

1. Summary table: findings per category and severity; fixed / rejected counts.
2. The 10 most important changes, one line each, with IDs.
3. Public renames (old → new).
4. Deleted files and code (paths, line counts).
5. Bugs found and fixed, with their numeric effect.
6. Baseline comparison (values, test counts, timing).
7. Line count of `gemini/`, `tests/`, `examples/` before → after.
8. Anything you chose not to change and why.
9. Lint/test summary lines.
