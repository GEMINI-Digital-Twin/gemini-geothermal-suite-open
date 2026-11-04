# Task: Clean up `examples/`: quickstart, basics, recipes, cases

## 0. Context and rules

- This is a new session. Read `AGENTS.md` and every file in `.claude/docs/` first and follow them. Start from the current `refactor` (the energy-flow commits, up to `9673a8d` "Docs: energy flow, ..." or later, are in).
- Goal: examples a new reader can learn gemini from, in a fixed order, each one short, standalone and in one style. The layout and rules below were agreed with me. Where one does not fit the code, stop that section and say why in the report instead of inventing another design.
- The layout follows the common "quickstart, basics, recipes" pattern of large Python libraries. Never name another library in the repo.
- **Do not change** the version. This is not an API change.
- Work directly on branch `refactor` (no new branch, no PR). One commit per section below, in order. **Do not push** until I have reviewed the commits.
- **Pre-check:** `git status` is clean on `refactor`, and no other Claude session or process is working inside `gemini/`, `examples/` or `tests/`. Sessions in other folders do not block you. If their load makes a 1 s budget test fail, rerun that test alone before treating it as a failure, and say which tests you retimed.
- **Scope:** workspace `/Users/sahand/Desktop/crust-team`. Change only `gemini/` (the repository). You may read `geomind/` and `backend/`, but never change them.
- **Temporary files** go to `.tmp/examples/` (git-ignored).
- **Agents:** one agent is enough. Subagents, if any, run on a lighter model and only do read-only searches.
- **Tests:**
  - Use the development profile only (`make test` / `scripts/test_changed.py`, always including `test_code_quality.py`), run in parallel, under 300 s.
  - Run the e2e tier and every example once at the end.
  - Before the first change, record what every current example prints (fast dataset) in `.tmp/examples/baseline/`. Each rewritten example must print the same numbers for the same case. List every number that changed and why.
  - Never run the slow dataset locally.
  - Never delete or shrink datasets or goldens. Only move them (section 1).
- **Quality bar** as in `.claude/docs/conventions.md`:
  - simple, readable, just enough code;
  - nesting at most 3, functions about 40 lines at most;
  - no comments inside code (docstrings only);
  - black, isort and flake8 clean.
- If something else is needed, say so in the report.

## 1. Data and shared code out of `examples/`

- Move the data to a top-level `datasets/` folder:
  - `examples/shared/doublet_heat/` (both CSVs and `plant.json`) goes to `datasets/doublet_heat/`;
  - `examples/legacy/gemini_project_bridge/old_project/` goes to `datasets/legacy_project/`.
  - Keep the files byte-identical.
  - Update every reader: tests, `tests/fixtures`, `scripts/` (`write_schemas.py`, `benchmark_esp.py`, `migrate_plants.py`), `gemini/modules/plants/catalogue.py` if it points there, and docs.
  - `test_changed.py`'s data rule must still select the readers of a changed data file.
- `NodalDoublet` (`examples/shared/nodal_doublet/plant.py`) is library code. Move it into gemini as a registered plant in `gemini/modules/plants/`, in the style of the other plants. It may import from `gemini.modules.plants.nodal` there. Give it tests under `tests/unit/modules/plants/`, built from the values its examples use.
- After this section, `examples/` holds no data, no `__init__.py` and no shared code. No test imports from `examples/`, except the one test that runs them (section 4). `tests/e2e/test_backend_parity.py` takes its list of examples from that test or from a fixture, never from importing an example.

## 2. New layout

```
examples/
  README.md
  quickstart.py
  basics/
    01_streams_and_fluids.py
    02_modules.py
    03_build_a_plant.py
    04_parameters.py
    05_simulate_and_results.py
    06_save_and_load.py
  recipes/
    replay_measurements.py
    live_update.py
    calibrate.py
    schedule_demand.py
    check_limits.py
    energy_balance.py
    economics.py
    write_a_module.py
    legacy_project.py
  cases/
    parallel_exchangers.py
    boiler_chp.py
    district_heating_cooling.py
    hackathon.py
```

**`quickstart.py`.** About 20 lines: load the doublet heat plant, run `gm.simulate` on the fast dataset, and print a few results in MW and °C.

**`basics/`** is read in order and numbered.
- `01`: `gm.Stream`, `gm.Fluid` and unit strings.
- `02`: call one module, read its outlets, outputs and port quantities.
- `03`: `gm.Plant`, `add`, `connect` and `validate`. Show an `unconnected_port` problem and its fix.
- `04`: `set_params` (including dated values), controls, boundaries and `set_bindings`.
- `05`: `gm.simulate`, `Results`, `units=` and `to_frame`.
- `06`: `to_dict`, `gm.plants.from_dict`, and saving and loading a plant.
- Today's `plants/basics/00_inspect_plant.py`, `01_module_api.py` and `02_custom_plant.py` are split across these. The `assert`s of `01_module_api.py` move to tests where they are not already covered there. List where each one went.

**`recipes/`** hold one task each, unnumbered and independent.
- From today's examples:
  - `replay_measurements` from `plants/replay/00_doublet_soft_sensors.py`;
  - `live_update` from `plants/live/00_daily_update.py`;
  - `calibrate` from `optim/calibrate/00_heat_exchanger_ua.py`;
  - `legacy_project` from `legacy/00_gemini_project_bridge.py`.
- New, each short and on a small plant:
  - `schedule_demand` uses `gm.schedule` with the `gm.profiles` demand;
  - `check_limits` uses `gm.checks.Limits` and `gm.checks.limits`;
  - `energy_balance` runs the module and plant balance checks and reads the edge-module totals;
  - `economics` uses `Assumptions`, `capex`, `opex`, `lcoh` and `co2`;
  - `write_a_module` writes a small custom `Module` with parameters, ports and one output, and uses it in a plant;
  - `plants/simulate/00_esp_frequency_sweep.py` becomes a recipe if it is still useful (name it), or its content goes into `basics/02`. Say which.
- Where a step raises `NotImplementedYet`, the recipe stops there and prints which step.

**`cases/`** hold the full plants from `plants/simulate/01`–`04`, with the same physics and printed numbers.
- Each case is at most about 150 lines. Plant building that would make it longer belongs in gemini, as a registered plant or a `set_params` override, not in the example. Today's hackathon example is 365 lines: say what you moved and where.
- `parallel_exchangers` and `boiler_chp` use the registered `NodalDoublet` from section 1.

## 3. One style for every example

- **Runs standalone:** `python examples/<folder>/<file>.py` works from any working directory, without `PYTHONPATH`. Paths come from `Path(__file__)`, and data from `datasets/` or `gm.profiles`.
- **Shape:**
  - module docstring first: what it shows, the gemini names it uses, and how to run it;
  - constants;
  - small functions if needed;
  - `main()` and `if __name__ == "__main__": main()`.
- **Values and prints:**
  - All values are given as unit strings (`"60 degC"`, `"150 m3/h"`), never bare SI numbers such as `333.15`.
  - Prints use MW, kW, °C, bar and m³/h with labels, never raw objects or long frames.
  - Assumptions that are not from the source data are printed as assumptions.
- **Public API only:** no `get_parameter` / `get_control` if one getter replaced them, no private modules, and no `gemini.modules.plants.nodal`.
- **Dataset:** the fast (one month) dataset by default. An environment variable may select the full year, and it is named the same way everywhere. Document it once in `examples/README.md`.

## 4. One test runs every example

- `tests/e2e/test_examples.py` finds every `.py` under `examples/` and runs each as a subprocess from a temporary working directory (to prove it is standalone) on the fast dataset. Each must exit 0 within its time budget.
- It also compares each example's printed numbers with a stored expected output, with tolerances, so a silent change in physics shows up. Store the expected outputs under `tests/e2e/expected/`.
- Update `scripts/test_changed.py`: any changed file under `examples/` selects this test, not only numbered ones, and the regex is replaced.
- Update `test_code_quality.py` and the Makefile if they assume the old layout. Make the code-quality test enforce the style of section 3 where it can be checked:
  - a docstring is present;
  - `main()` and the `__main__` guard are present;
  - no `__init__.py` under `examples/`;
  - no import from `examples`.

## 5. README and docs

- `examples/README.md`:
  - one table per folder: file, what it shows, main gemini names used;
  - how to run an example;
  - the dataset variable;
  - the reading order (quickstart, then basics 01–06, then any recipe, then cases).
- Update the repository README, `AGENTS.md` ("Start here"), `.claude/docs/` (`testing.md`, `data.md`, `plants.md`, `equipment.md`, `legacy.md`, `conventions.md`, `api.md`, `native-engine.md` and any other file that names an example path) and docstrings that point to example paths.

## 6. Report

- Commits, one per section.
- Old-to-new path table for every example and data file.
- Where each `assert` of `01_module_api.py` went.
- What moved out of the hackathon case into gemini.
- The esp-sweep decision.
- Every changed printed number, with its reason.
- Run time of each example on the fast dataset.
- What this breaks in `geomind/` and `backend/` (read-only, file and line), for example paths or `examples.shared` imports.
