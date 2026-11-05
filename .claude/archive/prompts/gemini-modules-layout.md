# Task: Tidy `gemini/modules/`: core classes on top, tools in `_utils`, plants alone in `plants/`

## 0. Context and rules

- This is a new session. Read `AGENTS.md` and every file in `.claude/docs/` first and follow them.
- Start from the current local `refactor`, with the data-layout commits (`gemini/assets/`, `inputs/`) in. If they are not in, stop and tell me.
- This task only **moves, renames and deletes files**. No behaviour, signature or number changes. The redesign of `Module` and `Plant` comes in a later task; do not start it here.
- **The rule for where a file goes** (write it in `conventions.md` and `modules.md`):
  - A file that defines a core class users subclass or build goes directly in `gemini/modules/`: `Module`, `Plant`, `ModuleList`, `ModuleDict`.
  - Machinery goes in an `_utils/` folder, even if some of its functions are exported publicly.
  - Code shared by the modules of one category goes in that category folder as a private file.
  - `gemini/modules/plants/` holds only plant classes.
- **Version:** do **not** change the version. Public import paths that users write (`gm.Plant`, `gm.modules.*`, `gm.plants.*`, `gm.ModuleList`, ...) stay the same. Only private module paths change.
- **Git:** work directly on branch `refactor` (no new branch, no PR). One commit per section below. **Do not push** until I have reviewed the commits.
- **Pre-check:** `git status` is clean on `refactor`, and no other Claude session or process is working inside `gemini/`. Sessions in other folders do not block you.
- **Scope:** workspace `/Users/sahand/Desktop/crust-team`. Change only `gemini/` (the repository). You may read `geomind/` and `backend/`, but never change them.
- **Temporary files** go to `.tmp/modules-layout/` (git-ignored).
- **Agents:** one agent is enough. Subagents, if any, run on a lighter model and only do read-only searches.
- **Tests:**
  - Use the development profile only (`make test` / `scripts/test_changed.py`, always including `test_code_quality.py`), run in parallel, under 300 s.
  - Run the e2e tier (it runs every example) once at the end.
  - Every number and every example output must stay identical.
  - Never run the slow dataset locally.
  - Move tests with their files (`tests/unit/modules/...` mirrors `gemini/modules/...`).
- **Mechanics:**
  - Use `git mv` so history follows.
  - Update every import in `gemini/`, `tests/`, `examples/`, `scripts/` and docs.
  - Leave no re-export shim at an old path. An old path must fail to import.
- **Quality bar** as in `.claude/docs/conventions.md`: no comments inside code (docstrings only); black, isort and flake8 clean.
- If something else is needed, say so in the report.

## 1. Core classes on top of `gemini/modules/`

- Move `gemini/modules/plants/builder.py` to `gemini/modules/plant.py`. It holds the `Plant` class, next to `module.py`.
- Move `gemini/modules/_utils/container.py` to `gemini/modules/container.py` (`ModuleList`, `ModuleDict`).
- Delete `gemini/modules/_utils/parameter.py` and its test `tests/unit/modules/_utils/test_parameter.py`.
  - The file defines nothing. It only re-exports `Parameter` and `State` from `gemini.types` and `Constant` from `gemini.ops`, and nothing else imports it.
  - Move the explanation in its docstring (what a parameter, a constant and a state are to the computation graph) into the docstring of `gemini/types/declarations.py`, or wherever those classes are defined. If a test of that file checked something real, move that check to the tests of `declarations`.

## 2. Plant tools into `gemini/modules/plants/_utils/`

- Move every file in `gemini/modules/plants/` that is not a plant class into a new `gemini/modules/plants/_utils/`. As of today these are:
  - `catalogue.py`, `factory.py`, `generators.py`, `library.py`, `listing.py`, `loops.py`
  - `migration.py`, `nodal.py`, `outputs.py`, `plan.py`, `ports.py`, `reader.py`
  - `schema.py`, `spec.py`, `templating.py`, `writer.py`, `legacy_project.py`
  - and any other non-plant file you find.
- `gemini/modules/plants/` keeps only the plant classes and `__init__.py`:
  - `atesplant.py`, `boilerchpplant.py`, `coolingsubstation.py`, `districtenergyplant.py`
  - `doublet.py`, `heatingsubstation.py`, `nodaldoublet.py`, `parallelexchangerplant.py`
  - and any plant class added since.
- If a data folder such as `specs/` or `templates/` is still there, it should already have moved to `gemini/assets/`. Say so and leave it; do not move it here.

## 3. Category code into its category

- Move `gemini/modules/_utils/burner.py` to `gemini/modules/heating/_burner.py` (used by `Boiler` and `CHP`).
- Move `gemini/modules/_utils/sorption.py` to `gemini/modules/cooling/_sorption.py` (used by the absorption and adsorption machines).
- If either is used outside its category, stop and tell me who uses it instead of moving it.

## 4. What stays in `gemini/modules/_utils/`

These stay: `balance.py`, `description.py`, `design.py`, `registry.py`, `serialization.py`, `wiring.py`, `__init__.py`.

The result:

```
gemini/modules/
  __init__.py
  module.py        # Module
  plant.py         # Plant
  container.py     # ModuleList, ModuleDict
  _utils/          # balance, description, design, registry, serialization, wiring
  plants/          # plant classes only
    _utils/        # plant tools
  control/  cooling/  environment/  exchangers/  grids/  heating/
  piping/  power/  pumps/  storage/  subsurface/  treatment/  wells/
```

Add a check to `test_code_quality.py`:
- `gemini/modules/` holds only `__init__.py`, `module.py`, `plant.py`, `container.py` and folders;
- every non-private file in `gemini/modules/plants/` defines a registered plant class.

## 5. Docs

Update `modules.md`, `plants.md`, `conventions.md` (the rule in section 0), `AGENTS.md` ("Start here" layout), `api.md` ("unreleased changes": file layout only, no API change), the README tree, and every docstring or doc that names an old path.

## 6. Report

- Commits, one per section.
- Old-to-new path table.
- Where the `parameter.py` docstring and any test went.
- Anything you did not move and why.
- Confirmation that every number and example output is unchanged.
- What this breaks in `geomind/` and `backend/` (read-only, file and line) for imports of private paths.
