# Task: Data layout: `gemini/assets/` (installed) and `inputs/` (repository only)

## 0. Context and rules

- This is a new session. Read `AGENTS.md` and every file in `.claude/docs/` first and follow them. Start from the current `refactor` (the examples cleanup, up to `9128a07` "Docs for the new examples ..." or later, is in).
- **Goal:** two homes for data, with one rule between them:
  - `gemini/assets/` (inside the package, installed) holds only small files that a public gemini function needs to work: plant structures and plant templates.
  - `inputs/` (repository root, next to `gemini/`, **not installed**) holds everything else that code reads: the hackathon inputs, example parameter values of plants, measured data and the legacy project.
  - There is no `datasets/` folder any more.
- The layout was agreed with me. Where it does not fit the code, stop that section and say why in the report instead of inventing another design.
- **Decision change:** this replaces the earlier plan that well-known plants would only be Python classes and that templates would be dropped. Plant structures and templates stay as data files. Remove any doc text, TODO or plan that still says otherwise.
- **Version:** do **not** change the version. Public function names do not change. The two renamed templates are catalogue entries, not API.
- **Git:** work directly on branch `refactor` (no new branch, no PR). One commit per section below, in order. **Do not push** until I have reviewed the commits.
- **Pre-check:** `git status` is clean on `refactor`, and no other Claude session or process is working inside `gemini/`, `examples/`, `tests/` or `scripts/`. Sessions in other folders do not block you. If their load makes a 1 s budget test fail, rerun that test alone before treating it as a failure, and say which tests you retimed.
- **Scope:** workspace `/Users/sahand/Desktop/crust-team`. Change only `gemini/` (the repository). You may read `geomind/` and `backend/`, but never change them.
- **Temporary files** go to `.tmp/data-layout/` (git-ignored).
- **Agents:** one agent is enough. Subagents, if any, run on a lighter model and only do read-only searches.
- **Tests:**
  - Use the development profile only (`make test` / `scripts/test_changed.py`, always including `test_code_quality.py`), run in parallel, under 300 s.
  - Run the e2e tier (it runs every example) once at the end.
  - This is a move, so every number and every example output must stay identical.
  - Never run the slow dataset locally.
  - Never delete or shrink data files or goldens, except the duplicates named in section 3, and only after proving them redundant.
- **Quality bar** as in `.claude/docs/conventions.md`:
  - simple, readable, just enough code;
  - no comments inside code (docstrings only);
  - black, isort and flake8 clean.
- If something else is needed, say so in the report.

## Target layout

```
gemini/assets/                    # installed, read by gemini functions
  plants/                         # structure only: modules, connections, ports, outputs; no parameter values
    Doublet.json  DoubletHeatPlant.json  DistrictNetwork.json
    MultiWellPlant.json  HackathonPlant.json
  templates/
    heating_only.json  heating_cooling.json  heating_full_cooling.json
    heating_absorption_cooling.json  heating_heat_pump_compression_cooling.json
    district_network.json         # was DistrictNetwork.json (generator-based)
    multi_well.json               # was MultiWellPlant.json (generator-based)

inputs/                           # repository only, not installed
  hackathon/
    README.md
    GEMINI_Heating_Demand_Daily_2027.csv
    GEMINI_Cooling_Demand_Daily_2027.csv
    GEMINI_Hackathon_Challenge_Requirements.pdf
  plants/                         # example values only: {"plant": <name>, "params": {...}}
    Doublet.json  DoubletHeatPlant.json  DistrictNetwork.json  MultiWellPlant.json
    HackathonPlant.json  ATESPlant.json  HeatingSubstation.json  CoolingSubstation.json
    NodalDoublet.json  BoilerChpPlant.json  DistrictEnergyPlant.json  ParallelExchangerPlant.json
  doublet_heat/
    doublet_2024_15min.csv  doublet_2024_15min_month.csv
  legacy_project/
    (the 14 files of today's datasets/legacy_project/)
```

These stay where they are:
- `tests/fixtures/` (goldens, baselines);
- `tests/e2e/expected/` (example outputs);
- `docs/schemas/` (generated documentation).

## 1. One module for paths

- Add one private module, for example `gemini/utils/paths.py`. Choose the name that fits `gemini/utils/`, and do not make it public API. It is the only place that knows where `gemini/assets/` and `inputs/` are.
- It gives one function or constant per folder. Choose the simplest form and use it everywhere.
- `inputs/` is found relative to the source checkout. When it is not there (gemini installed from a wheel), a function that needs it raises a `gm.errors` error with code `inputs_missing`. The message names the file and says that it needs a source checkout of the repository. Nothing fails at import time.
- No other file builds a path to these folders. Add a check for this in `test_code_quality.py` (a text search for the folder names is enough).

## 2. `gemini/assets/`

- `git mv`:
  - the structure files from `gemini/modules/plants/specs/*.json` to `gemini/assets/plants/`;
  - the templates from `gemini/modules/plants/templates/` to `gemini/assets/templates/`.
- Rename the generator-based templates `DistrictNetwork.json` to `district_network.json` and `MultiWellPlant.json` to `multi_well.json`, so every template name is snake_case and none shares a name with a plant. Update their readers and docs, and list the renamed template names in the report.
- The structure files must hold no parameter values. If one does today, move the values to its `inputs/plants/` file (section 3) and say which.
- Change their readers (`modules/plants/library.py`, `catalogue.py`, `templating.py` and any others) to the paths module.
- Build a wheel into `.tmp/data-layout/`. Show in the report that it contains `gemini/assets/` with every file and nothing from `inputs/`. Report the wheel size. Fix `pyproject.toml` if needed.

## 3. `inputs/`

**Hackathon.**
- `git mv gemini/profiles/data/*.csv inputs/hackathon/`, unchanged.
- Copy `/Users/sahand/Desktop/crust-team/inputs/GEMINI_Hackathon_Challenge_Requirements.pdf` into it. If the file is missing, ask me for it.
- Write `inputs/hackathon/README.md` with:
  - the source (organisers, released 2026-10-29);
  - the key figures (heating peak 30.0 MWth on 2027-01-28, 111.67 GWh/yr; cooling peak 10.0 MWcool on 2027-07-19, 23.74 GWh/yr);
  - the reservoir, brine and limit values of the PDF.
- `gm.profiles.get("heating_demand")` / `("cooling_demand")` read from there through the paths module, so they raise `inputs_missing` outside a checkout.
- Name in the report every place in code that hard-codes a value that is also in these files.

**Example values of plants.**
- Today `gemini/modules/plants/specs/examples/<Name>.json` repeats the whole plant structure plus values. Replace each with `inputs/plants/<Name>.json` holding only `{"plant": "<Name>", "params": {"<dotted path>": <value>, ...}}`.
  - Write values as unit strings where the file today has bare SI numbers, if `set_params` accepts them. Otherwise keep SI and say so.
  - Fluids, bindings or param history that an example file carries today also go in this file, under keys with the same names as in a plant dict. List any you needed.
- `gm.plants.example(name)` becomes `get(name)`, then `set_params` with the file's `params` (and the other keys), and nothing else. A plant with no file raises `NotImplementedYet` as today. Outside a checkout it raises `inputs_missing`.
- Prove for every plant that `example(name).to_dict()` equals the plant built from today's example file (write the comparison as a test before deleting the old files). Then delete `specs/examples/`.

**Measured data and legacy project.**
- `git mv datasets/doublet_heat/*.csv inputs/doublet_heat/`.
- `git mv datasets/legacy_project inputs/legacy_project`.

**Duplicate.**
- `datasets/doublet_heat/plant.json` has the same md5 as today's `specs/examples/DoubletHeatPlant.json`. Prove it, delete it, and change its readers to `gm.plants.example("DoubletHeatPlant")`. Today's readers are:
  - `scripts/migrate_plants.py`, `scripts/benchmark_esp.py`
  - `examples/quickstart.py`
  - `examples/basics/02`, `04`, `05`, `06`
  - `examples/recipes/live_update.py`, `calibrate.py`, `check_limits.py`, `replay_measurements.py`, `sweep_esp_frequency.py`, `legacy_project.py`
  - `tests/conftest.py`, `tests/unit/modules/plants/test_spec.py`, `test_migration.py`, `tests/unit/test_public_api.py`, `tests/unit/analysis/test_wells.py`
  - `.claude/docs/legacy.md`, `equipment.md`
- A test that needs a plant file itself, for example to test migration of a file, writes one from `to_dict()` into `tmp_path`.

**Readers.**
- Remove `datasets/`.
- Update every reader: examples, tests, `tests/fixtures`, `scripts/`, `scripts/test_changed.py`'s data rule (a changed file under `inputs/` selects its readers), the e2e example test, the Makefile and docs.
- List any other file that exists in both `tests/fixtures/` and `inputs/` or `gemini/assets/`. Do not delete it without asking me.

## 4. Enforce it

In `test_code_quality.py`:
- No JSON, CSV, PDF or other data file inside `gemini/` outside `gemini/assets/`.
- Every file in `gemini/assets/plants/` holds no parameter values.
- Every file in `inputs/plants/` has only the allowed keys and names a registered plant.
- No `datasets/` folder in the repository.
- The paths check from section 1.

## 5. Docs

- Write the rule in `data.md` and `conventions.md`:
  - `gemini/assets/` is for what a public function needs, and is installed;
  - `inputs/` is for everything else, is not installed, and raises `inputs_missing` when absent;
  - `docs/schemas/` is generated documentation.
- Update `plants.md`, `api.md` ("unreleased changes": data layout, `inputs_missing`, two template names, no API change), `errors.md` (the new code), `AGENTS.md` ("Start here" layout), the README tree, `examples/README.md`, and every docstring that names an old path.

## 6. Report

- Commits, one per section.
- Old-to-new path table.
- Wheel listing of `gemini/assets/` and the wheel size.
- The `example()` equality test result per plant.
- Values moved out of structure files, and extra keys needed in `inputs/plants/`.
- The md5 proof and readers changed for the duplicate.
- Hard-coded hackathon values found.
- Confirmation that every number and example output is unchanged.
- What this breaks in `geomind/` and `backend/` (read-only, file and line), for example paths to `specs/`, `templates/`, `profiles/data` or `datasets/`, or the old template names.
