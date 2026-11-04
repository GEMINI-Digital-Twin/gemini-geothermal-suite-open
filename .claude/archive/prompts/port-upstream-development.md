# Task: Port upstream `development` into `refactor`, adapted to the refactored structure

## 0. Context and rules

- Goal: bring everything that the upstream repo's `development` branch adds over its `main`
  branch into my `refactor` branch, rebuilt in the refactor's architecture. Do not copy
  upstream files over refactored code and do not revert or overwrite any refactor change.
- Work directly on branch `refactor` (no new branch, no PR). Commit there. **Do not push**
  until I have reviewed the commits.
- Read `AGENTS.md` and every file in `.claude/docs/` first and follow them.
- **Pre-check:** `git status` must be clean on `refactor` and no other task may be running on
  this repo. Otherwise stop and report.
- Temporary files (diff dumps, notes, scratch) go to `.tmp/` at the repo root (git-ignored),
  never to `docs/`. The upstream clone lives outside the repo.
- Subagents, if you use any, run on a lighter model (sonnet or haiku), not the main model.
- **Tests:** use the development profile only (`make test` / `scripts/test_changed.py`): the
  tests of what changed and of everything that imports it, in parallel, under 300 s. Never run
  the whole suite or the slow dataset locally; the release profile runs in CI. New tests go in
  the right tier, reuse the session fixtures and the short-window dataset, no fast-tier test
  over about 1 s, xdist-safe. Never delete or shrink existing tests, datasets or goldens.
- **Quality bar** (as in `.claude/docs/conventions.md`): nesting at most 3, functions about
  40 lines max, flake8 `max-complexity = 10`, guard clauses, no dead or speculative code, no
  golfed code, full-word names, explicit `gm.errors` classes, a failing test before each bug
  fix. **No comments inside code**: only the fixed section headers (`# Modules`,
  `# Parameters`, ... `# Outlets`) and tool directives; explanations go in docstrings. No
  "magic" structures, no string registries, keep the public API minimal. black, isort and
  flake8 clean.
- **Docs:** every commit that changes behaviour updates the matching file in `.claude/docs/`
  (and `AGENTS.md` "Start here" if a new doc is added) in the same commit.
- If something else is needed (missing step, dependency, risk), say so in the report instead of
  staying silent.

## 1. Setup

- My workspace is `/Users/sahand/Desktop/crust-team` (with `backend/`, `frontend/`,
  `gemini/`, `infrastructure/`). This task touches **only** `/Users/sahand/Desktop/crust-team/gemini`
  (the GEMINI package repo, branch `refactor`). Do not change `backend/`, `frontend/` or
  `infrastructure/`.
- Clone upstream outside the workspace:

```bash
git clone https://github.com/GEMINI-Digital-Twin/gemini-geothermal-suite-open /tmp/gemini-upstream
cd /tmp/gemini-upstream && git fetch origin main development
cd /Users/sahand/Desktop/crust-team/gemini && git checkout refactor && git status
```

- If `/Users/sahand/Desktop/crust-team/gemini` is not itself a git repo (the `.git` is in
  `crust-team`), run the git commands from the folder that holds `.git` and keep every change
  inside `gemini/`.
- The local package has `gemini/agentic/` and `gemini/design/` next to `gemini/core/` and
  `gemini/optim/`; include them when you search for existing features.
- `runs/` (checkpoints, parquet results, `my_plant.json`) and the report/JSON files in `docs/`
  are not part of this task; do not edit, move or commit them.

## 2. Analysis (before changing anything)

1. In the upstream clone:
   ```bash
   git log --oneline origin/main..origin/development
   git diff --stat origin/main...origin/development
   ```
   The 16 commits are 8 changes applied twice (rebased, then merged again), e.g. "simulator is
   implemented (#43)", "add heatpump model", "Adder and Splitter model". Work from the final
   three-dot diff, not commit by commit, so nothing is applied twice.
2. Group the diff into features: simulator (`src/gemini_simulator/`: solver, project loader,
   registry, nodal solver, well components, well flow, KPI), each model in
   `src/gemini_model/` (adder, splitter, mixer, boiler, CHP, booster pump, injector pump,
   compressor, filter, separator, heat exchanger, heat pump), examples
   (`simulator_examples/`), unit tests (`unit_test/gemini_model/*`,
   `unit_test/gemini_simulator/*`), Sphinx docs (`src/gemini_documentation/source/*.rst`),
   dependency files.
3. For each feature, check whether `refactor` already has it, possibly under other names or
   paths. Search by behaviour and symbols, not file paths. Starting hints from a first review
   (verify each one, do not trust them blindly):
   - Most upstream models are the simple GEMINI DDT "doubletA" formulas (linear resistance,
     fixed temperature drop, bar/degC/m3/s scalars). `refactor` already has richer `Module`
     versions: `Boiler`, `CHP`, `HeatExchanger`, `Filter`, `Degasser`/`Separator`,
     `GasCompressor`, `InjectionPump`, `CentrifugalPump` (the removed `BoosterPump`),
     two-way `Mixer`/`Splitter` with cascades in `MultiWellPlant`, and `Output.total` for the
     adder.
   - The JSON connection solver and string registry are replaced by Python composites,
     `Module.save/load` and the engine; `refactor` forbids string registries on purpose.
   - The MD/TVD/ID survey conversion exists as `gemini.core.physics.geometry.build_path`.
   - Likely missing or partial: the nodal well solve (production flow from wellhead pressure,
     injection flow or wellhead pressure, `brentq`), a topology-agnostic CO2 emissions helper
     for `fuel` and `electricity`, the heat pump's Lorenz COP mode and minimum source-outlet
     temperature, and the parallel heat exchanger and boiler/CHP examples.
   - Upstream compressor power is `n m R T1/(k-1) (r^((k-1)/k) - 1)`, which is low by the
     factor `k`; do not port it, list it as a conflict.
   - Upstream changed no dependency file; check this.
4. Write the mapping table to `.tmp/porting-plan.md`, one row per feature:
   upstream file(s) -> target location in `refactor` | status (missing / partial / already
   present) | adaptation notes. Show me the table and **stop. Wait for my confirmation before
   implementing.**

## 3. Implementation (only after I confirm)

1. Port only the rows marked missing or partial, in the refactor's architecture, naming,
   imports and style (declarations in `__init__`, `forward(self, inlets)`, SI streams,
   `_compute_outputs`, energy audit documented in `equipment.md`).
2. Port the matching upstream tests (`unit_test/gemini_simulator/*` for the nodal solve and
   wells, the heat pump tests for Lorenz) rewritten for the new API and imports. Do not port
   tests of upstream-only code (JSON solver, loader, registry, doubletA formula validations).
3. Port the related documentation into the existing `.claude/docs/` files, not as `.rst`.
4. If upstream changed dependencies, merge only the needed additions into `pyproject.toml`.
5. Run the development test profile and black/isort/flake8. Fix failures caused by the port.
   If a failure already existed before your changes, report it, do not hide or skip it.
6. Commit in small logical commits, one per feature, e.g.
   `port: nodal well solve from upstream development`,
   `port: heat pump Lorenz COP from upstream development`. Do not push.

## 4. Report

Give me a summary: what was ported, what was skipped and why, what was already present, and
every open question or conflict where upstream logic and the refactor disagree (with the
numbers if they differ).
