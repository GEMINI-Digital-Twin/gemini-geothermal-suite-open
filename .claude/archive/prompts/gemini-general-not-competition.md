# Task: gemini knows nothing about the competition

## 0. Context and rules

- This is a new session. Read `AGENTS.md` and every file in `.claude/docs/` first and follow them.
- **The rule (most important):** gemini is a general geothermal heating and cooling package. The GEMINI hackathon inputs are only one sample problem used to **test** the code. They are never the basis of an implementation, a default, a name or a structure. Nothing in `gemini/` may know that the competition exists. What the competition needs must be supported, but in a general form that works for any other problem.
- **gemini is the source of truth.** gemini's own shapes (plant dict, rules, limits, run input) are designed to be the best general form. Inputs adapt to gemini, never the other way round: the competition's files are converted into gemini's shapes in its sample folder (data files, or a short loader in `examples/`), and gemini never takes a name, column or unit from them because the competition uses it.
- **Scope:** only this. Remove every competition-specific thing from `gemini/` and make the affected features general. No folder restructure, no API redesign beyond what this needs, no new features beyond those named here. If you find another competition-specific thing not listed, fix it in the same way and list it in the report.
- Start from the current local `refactor` in `/Users/sahand/Desktop/crust-team/gemini` (origin is at `33c7f52`). `git status` must be clean and `git pull origin refactor` must succeed. No other Claude session works inside `gemini/`.
- Where a decision below does not fit the code, stop that section and say why in the report instead of inventing another design.
- **Version:** do not change it. Add change-log lines under "unreleased changes" in `api.md`.
- **Git:** work directly on `refactor`. One commit per section, in order. **Do not push** until I have reviewed the commits.
- **Scope of changes:** only `gemini/` (the repository). You may read `geomind/` and `backend/`, never change them.
- **Temporary files** go to `.tmp/general/` (git-ignored).
- **Speed (we are short of time):** work in parallel wherever it is safe. Target: the whole task in well under an hour.
  - First, alone: section 1 (it moves files the others read). Commit it.
  - Then in parallel, three subagents on a lighter model (sonnet), each in its own git worktree on a temporary branch from that commit, each on files the others do not touch:
    - **A:** section 2 (rules, `HackathonPlant`, template values, optimiser);
    - **B:** sections 3 and 4 (profiles, schedule on any step);
    - **C:** sections 5 and 6 (defaults, sources).
    Give each its section text, the rules of section 0, and the list of files it owns. Each commits once per section on its branch and runs only the tests of its changed files.
  - You review each branch, then bring them onto `refactor` in section order (cherry-pick or merge), fix any overlap, and run the development tests once.
  - Then sections 7 and 8 (7 can be split: the quality test and coverage test by you, the second problem by a subagent), the e2e tier once, and the report.
  - Never run the same full test set twice in a row without a change in between; run targeted tests while working. Remove the worktrees and temporary branches at the end.
  - Read-only searches use a lighter model (haiku).
- **Tests:**
  - Development profile only (`make test` / `scripts/test_changed.py`, always including `test_code_quality.py`), parallel, under 300 s.
  - New fast tests stay under about 1 s each.
  - Run the e2e tier once at the end, against a baseline taken before the first change. The competition example must give the same numbers as before (heat, cold, boiler, electricity, LCTS, every requirement check); list any number that changes and why.
  - Never run the slow dataset locally. Never delete or shrink goldens or `inputs/` data (moving is fine).
  - If a 1 s budget test fails, rerun it alone before treating it as a failure, and say which tests you retimed.
- **Quality bar** as in `.claude/docs/conventions.md`: simple, readable, just enough code; nesting at most 3, functions about 40 lines at most, guard clauses; explicit `gm.errors` with codes; no comments inside code (docstrings only; the fixed section headers stay); black, isort and flake8 clean; a failing test before each bug fix.

## 1. The competition becomes one sample problem folder

- Move `inputs/hackathon/` to `inputs/examples/hackathon_2027/` (CSVs, PDF, README). Update every reader in tests, examples and docs.
- Add there what the competition example needs to run, as plain data:
  - `plant.json`: the plant dict of the design (today the values of `inputs/plants/HeatingCoolingPlant.json`, with `size`, `params` and `inputs`);
  - `rules.json`: the schedule rules (`doublet_flow`, `max_brine_cooling`, `operating_days`, `order`, `cooling_order`);
  - `limits.json`: the requirement checks as a `gm.checks.Limits` dict (flow, brine cooling, pump efficiency, volume balance, supply temperatures);
  - `assumptions.json` if the example uses prices.
- **Who may read it:** only `examples/` and `tests/`. Nothing under `gemini/` names this folder, the word hackathon or the word challenge.
- Remove `utils/paths.py`'s `hackathon` helper. If `gemini/` still needs to find files of a checkout (for `gm.plants.example`), it is one general helper with no folder name of a problem in it.

## 2. No competition rules or plant in the code

- **`gm.challenge_rules()`** and its constant in `gemini/analysis/schedule.py`: remove. `gm.schedule` takes `rules` from the caller, with no default for any limit. A missing rule that the schedule needs raises `ValidationError` code `missing_value` naming it.
- **`HackathonPlant`**: remove the class and its exports (`modules/__init__.py`, `plants/__init__.py`, registry). Its design is the `plant.json` of section 1 (as a `HeatingCoolingPlant` dict, or a structure dict if it does not fit a template class; say which). Rewrite `examples/cases/hackathon.py` to load the sample folder, and keep its output numbers.
- **Template plants' example values:** `inputs/plants/<Template>.json` must not carry the competition's sizes or site values. Either give them neutral example values with a cited source that is not the competition, or remove those files so `gm.plants.example(name)` raises `NotImplementedYet` for the template plants. Say which you chose for each.
- **`gm.optim.minimize` / `sample`**: `profile=None` no longer means the competition. The caller passes the demand (or a plan) and, with a demand, the `rules` (new argument, required then). Without them, `ValidationError` `missing_value`.

## 3. No built-in demand profiles

- `gm.profiles` ships no profile. Remove `profiles/library.py`'s competition source, `gm.profiles.demand()`, and `get` / `names` of built-in profiles.
- Add the general way in:
  - `gm.profiles.from_csv(path, columns, unit, time_column=None)`;
  - `gm.profiles.from_values(values, unit, start, step, quantity)`.
  Both return the run input `gm.schedule` takes (UTC index, `heating_demand` / `cooling_demand` in W, `units` and `quantities` in `attrs`), and validate: monotonic index with no gaps or duplicates, a constant step, no negative or missing value, a known quantity. Problems use the existing codes.
- Any step works (hourly, daily, ...), and any length (a month, a year).
- Keep `gm.profiles.profile_schema` if it describes this input; otherwise update it.

## 4. Schedule on any time step

- `gm.schedule` today assumes daily rows. Make it work on any constant step of the demand.
- `operating_days` becomes general: `rules["operating_time"]` as a duration (`"330 d"`, `"7920 h"`) or a fraction of the period, or a list of outage dates / intervals. Outages are whole steps, chosen as the lowest-demand steps and spread over the doublets as today. Remove `operating_days` (nothing is released); if you keep it as a name, say why.
- `gm.checks.operating_days` becomes `gm.checks.operating_time(plant, results, duration)`, counting the time each doublet carried flow.
- **Tests:** an hourly demand of a few days schedules and runs; operating time on hourly and daily steps gives the same fraction.

## 5. No competition values as physical defaults

- `gemini/physics/ground.py`: the 12 degC surface temperature and 30 K/km gradient ("the challenge value") are not defaults. `Doublet.gradient`, `Doublet.surface_temperature` (and any plant parameter that inherits them) have **no default**: a doublet built from `depth` without them raises `missing_value`.
- **Fixed injection pump setpoint** (30 bar or 60 bar on the template plants): not a hidden default. It is a required parameter or input of the plant, set in the sample `plant.json`.
- Find any other default whose value or docstring comes from the competition (supply 100 degC / 20 degC, brine 1030 kg/m3 and 0.40 mPa s, GLR 0.8, 80 % CH4 / 20 % CO2, 250 bar, 200 mD, 2500 m, 50 to 300 m3/h, 40 K, 330) and treat it the same way. A default stays only if it is a physical constant or a general equipment value with a source that is not the competition.

## 6. Sources that cite the competition

Rewrite every docstring and comment in `gemini/` that cites the competition as a source, with a general technical source:
- `physics/gas.py` (normal conditions 0 degC and 1.01325 bar: cite DIN 1343 or ISO 13443; make the reference conditions of a gas-liquid ratio an explicit argument with that default if they are not already);
- `physics/ground.py` (linear conductive geotherm);
- `physics/hydraulics.py` (hydrostatic reservoir pressure);
- `physics/pumps.py` (pump from a design point);
- `physics/combustion.py` (dispatch rule);
- `modules/plants/_utils/catalogue.py` and `modules/plants/doublet.py`.

## 7. Guards and tests

- **Code-quality test:** no file under `gemini/` contains `hackathon` or `challenge` (case-insensitive), or names `inputs/examples/`. Add it to `test_code_quality.py`.
- **Competition example (e2e):** loads `inputs/examples/hackathon_2027/` only through general functions (`gm.profiles.from_csv`, `gm.plants.from_dict`, `gm.checks.Limits.from_dict`, `gm.schedule`, `gm.simulate`), runs the year with no failed step and every limit passing, and prints the same numbers as before.
- **Coverage test** (`tests/e2e` or `tests/integration`): one test per need of the competition input, each with a general name: heating and cooling demand from CSV, 1 to 3 doublets, a chosen depth, co-produced gas, each limit kind (flow range per doublet, brine cooling, operating time, a parameter limit, volume balance, supply temperatures), LCTS. A list of these needs goes in `.claude/docs/testing.md`.
- **A second, different problem** in `inputs/examples/second_case/` (choose a clear name), with values you choose and document: an hourly demand of a few weeks with a different shape, a colder and shallower reservoir, one doublet, and other limits. It runs end to end through the same functions. It must not reuse any competition number.
- Update unit tests that relied on removed names to use the general functions.

## 8. Docs

- `api.md`: removed names (`challenge_rules`, `HackathonPlant`, `gm.profiles.demand`, built-in `get` / `names`, `operating_days`), new names (`from_csv`, `from_values`, `operating_time`, the `rules` argument of `minimize` / `sample`), unreleased changes.
- `data.md`: the `inputs/examples/` layout and the rule that only examples and tests read it.
- `conventions.md`: the rule of section 0, in two lines.
- `engine.md` (schedule on any step), `plants.md`, `testing.md`, `AGENTS.md` "Start here", the README, every docstring touched.

## 9. Report

- Commits, one per section.
- Every competition-specific thing removed, with file and what replaced it, including ones found that were not in this prompt.
- For each template plant: neutral example values (with source) or none.
- The competition example's numbers before and after (must match), and any changed number with the reason.
- The second problem: its values, and its results (heat, cold, unmet, failed steps, each limit).
- The coverage test list.
- What this breaks in `geomind/` and `backend/` (read-only, file and line), for example `gm.profiles.get`, `gm.profiles.names`, `gm.challenge_rules`, `HackathonPlant`, `operating_days`, `inputs/hackathon/`.
