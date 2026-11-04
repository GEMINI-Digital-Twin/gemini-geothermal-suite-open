# Task: Step 3b: the public API that geomind and the backend are blocked on

## 0. Context and rules

- Run this **right after step 3** (`native-engine-step3.md`) and **before step 4**. Start from the
  current local `refactor`. Two other repos are blocked on exactly these names: the agent package
  `geomind` (`import geomind as gd`) and the backend. They may only use gemini's **public** names
  (`import gemini as gm`, everything in gemini's `__all__`, pinned by
  `tests/unit/test_public_api.py`). Their contract is `contracts.md` (given next to this prompt,
  Version 12 or later); follow it for field names.
- Do not move folders in this step (`gemini/core` is removed in step 4). The public names below
  must stay the same when step 4 moves the files, so other repos never import internal paths.
- Standing rules: no concept has two implementations; behaviour identical on every backend;
  physics and numbers do not change.
- Work directly on branch `refactor` (no new branch, no PR). Commit there. **Do not push**
  until I have reviewed the commits.
- Read `AGENTS.md` and every file in `.claude/docs/` first and follow them.
- **Pre-check:** `git status` clean on `refactor`, and no other Claude session or process working
  **inside `gemini/`**. Sessions in other folders (`geomind/`, `backend/`) do not block you; if
  their load makes a 1 s budget test fail, rerun it alone before treating it as a failure.
- Workspace `/Users/sahand/Desktop/crust-team`; change **only** `gemini/`. You may read
  `geomind/` and `backend/` to see how they will call these names, but never change them.
- Temporary files go to `.tmp/public-api/` (git-ignored).
- Small enough for one agent; use subagents (lighter model) only for read-only searches.
- **Tests:** development profile only (`make test` / `scripts/test_changed.py`, always including
  `test_code_quality.py`), parallel, under 300 s. New tests in the right tier, no fast-tier test
  over about 1 s. Never delete or shrink existing tests, datasets or goldens.
- **Quality bar** as in `.claude/docs/conventions.md` (nesting at most 3, functions about 40
  lines, flake8 complexity 10, full-word names, explicit `gm.errors`, no comments inside code,
  docstrings for explanations, no "magic", minimal public API; PyTorch patterns as reference
  only, never named in the repo). black, isort, flake8 clean.
- **Docs:** update `.claude/docs/` in the same commit, including a short "public API for other
  repos" page listing every name below with its signature and return shape.
- If something else is needed, say so in the report.

## 1. Registries

- `gm.modules.get(name)` returns a module class by its stable registry name (for example
  `"ESP"`); `gm.modules.names()` (or the name in `contracts.md`) lists them with their category.
  Same for plants: `gm.plants.get(name)` and `gm.plants.names()`.
- Every module and plant has a registry name and a `category`. One registry implementation used
  by both.
- Unknown name: a `gm.errors` class with a close-match suggestion.

## 2. `Module.describe()`

A public method returning one JSON-serialisable dict: name, docstring summary, category, and
every declaration (parameters, controls, inlets, outlets, outputs, states) with kind, unit,
bounds, default, calibratable and soft-sensor flags. For composites: children nested, and the
connections between children (from module path and port, to module path and port, stream type),
so a flowsheet diagram can be drawn. Field names as in `contracts.md`. Tests: a leaf, a
composite, and every registered module and plant serialises with `json.dumps`.

## 3. Plants by name, examples, migration

1. **Stored files use registry names.** Plant dicts, checkpoints and saved results name classes
   by registry name, never by import path, and carry a `format` version. `Plant.to_dict` /
   `from_dict` and `gm.plants.from_dict(data)` (class not known in advance, resolved from
   `plant_type`) share one implementation.
2. **`gm.plants.migrate(old: dict) -> dict`** converts the old format (class paths such as
   `gemini.core...`) to the new one; the same for checkpoints if their format differs. A
   one-off script in `scripts/` runs it over files given on the command line; run it on every
   stored file inside `gemini/` in the same commit. Loading an old-format dict without migrating
   raises a clear `gm.errors` message naming `gm.plants.migrate`.
3. **Example plants inside the package.** `DoubletHeatPlant` and every plant used by the
   examples or legacy import are exported in `gm.plants`. `gm.plants.example(name)` returns a
   plant with real parameter values (for the doublet: the `doublet_heat` example values), so other
   repos can load and run it without `gemini/examples/` and without legacy files. Examples in
   `gemini/examples/` use these public names instead of defining plants themselves. Legacy import
   works through the public API only.
4. Add `gm.plants` (and `gm.modules` if not already) to the public `__all__`; keep `gm.utils` out
   of it.

## 4. Units

The agent package found that unit strings `km`, `mm`, `in`, `kPa`, `MPa` and `rpm` are
rejected. Accept every common engineering unit for the quantities gemini declares (at least
these, plus `bar(g)` if there is a convention for gauge pressure) through the existing unit
conversion, with tests. List the supported units per quantity in the public API doc page.

## 5. Report

Commits, every new public name with its signature, the stored-file format and version, files
migrated, the example plants and their parameter source, units added, behaviour changes, and
anything `geomind/` or `backend/` currently call that does not match (read-only check).
