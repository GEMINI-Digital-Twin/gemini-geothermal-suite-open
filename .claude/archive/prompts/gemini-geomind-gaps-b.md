# Task: what geomind needs from gemini, part B (every remaining gap)

## 0. Context and rules

- This is a new session. Read `AGENTS.md` and every file in `.claude/docs/` first and follow them.
- geomind (the agent package) sent a list of gemini names it needs. Part A built `operating_days`, `gm.checks.operating_days`, `annualised_cost`, `lcts`, the `flow` message in `gm.evaluate`, and `gm.optim.minimize` / `sample`, on branch `gaps` in the worktree `../gemini-gaps`. The Module/Plant redesign is done on `refactor` (commits `89986dc` to `dfb0b9e`). This prompt merges the two and fills every gap that is left.
- Start from the current local `refactor` in `/Users/sahand/Desktop/crust-team/gemini`. `git status` must be clean, and no other Claude session or process works inside `gemini/` or `gemini-gaps/`.
- Where a decision below does not fit the code, stop that section and say why in the report instead of inventing another design.
- **Version:** do not change it. Add change-log lines under "unreleased changes" in `api.md`.
- **Git:** work directly on `refactor` (no new branch, no PR). One commit per section below, in order. **Do not push** until I have reviewed the commits.
- **Scope:** change only `gemini/`. You may read `geomind/` and `backend/`, never change them.
- **Temporary files** go to `.tmp/gaps-b/` (git-ignored).
- **Agents:** one agent is enough. Subagents, if any, run on a lighter model and only do read-only searches.
- **Tests:**
  - Use the development profile only (`make test` / `scripts/test_changed.py`, always including `test_code_quality.py`), run in parallel, under 300 s.
  - New tests go in the fast tier, reuse the session fixtures and the short-window data, and each stays under about 1 s. A full-year check is an e2e example, not a unit test.
  - Run the e2e tier once at the end, against a baseline taken after section 1.
  - Numbers stay identical, except where a section says they change. List each changed number with old and new value and why.
  - Never run the slow dataset locally. Never delete or shrink goldens or `inputs/` data.
  - If a 1 s budget test fails, rerun it alone before treating it as a failure, and say which tests you retimed.
- **Quality bar** as in `.claude/docs/conventions.md`:
  - simple, readable, just enough code;
  - nesting at most 3, functions about 40 lines at most, guard clauses;
  - explicit `gm.errors` with codes;
  - no comments inside code (docstrings only; the fixed section headers stay);
  - black, isort and flake8 clean;
  - write a failing test before each bug fix.
- Every result is one of the three shapes in the docs (value `{value, unit}`, problem, check). If something else is needed, say so in the report.

## 1. Merge part A

- `git merge gaps` into `refactor` (a merge commit is fine). The expected conflict is the hash line of the API snapshot: regenerate `tests/fixtures/public_api.json` and take the new hash.
- Part A was written against the old structure. Fix what the redesign broke in it: `plan.py`, `plant._connections`, `has_input_value`, `update_params`, `Output.of` paths, `d0.flow` style labels (now `d0.reservoir.liquid_flow`). Use the public wiring of `Plant`, never private attributes of another class.
- Run the part A tests and the schedule and hackathon examples on top of `refactor`.
- When everything passes: `git worktree remove ../gemini-gaps` and `git branch -d gaps`.

## 2. Inputs are stored with the plant

Today values set as inputs (setpoints such as `heat_pump.temperature_setpoint`) are lost by `to_dict`, and neither `from_dict`, `gm.schedule` nor `gm.simulate` applies them. So no stored design with a heat pump, boiler or chiller can be scheduled ("temperature_setpoint has no value"). geomind has a bridge that calls `plant.set_inputs`, which the redesign made private.

- **One public way to set them:** `plant.set_inputs({"heat_pump.temperature_setpoint": "100 degC", ...})`, with paths and unit strings like `set_params`. Make it public again on `Plant` (not on leaf modules), and list it in `api.md`.
- **Stored in the plant dict:** both dict forms (class and structure) get one top-level key `inputs`, `{path: value}`, written by `to_dict` and applied by `from_dict`. Today `boundary[""]["inputs"]` (and `boundary["root_inputs"]` in the schedule docstring) holds something like this: merge them into the one key and remove the other names. Say what you merged.
- `gm.plants.schema()` and `validate` know the key: unknown path, wrong unit, a path that is not an input.
- `gm.schedule` reads the setpoints through a public reader (for example `plant.input_value(path)`, or the `get(path)` declaration), not through a private method.
- **Tests:** round-trip of a plant with inputs in both dict forms; `from_dict` then `gm.schedule` on a heat pump plant works with no extra call; a bad path in `inputs` gives `unknown_name` with suggestions.

## 3. Template plants: number of doublets and depth

geomind's Designer needs 1 to 3 doublets and a chosen depth.

- Every template plant class that has a doublet (`HeatingPlant`, `HeatingCoolingPlant`, `HeatingFullCoolingPlant`, `HeatingAbsorptionCoolingPlant`, `HeatingHeatPumpCoolingPlant`) takes `size={"doublets": n}` (1 to 3 by default, `ValidationError` outside the range of the class), with doublets `d0 ... d{n-1}` wired in parallel through splitters and mixers. `to_dict` stores the size, as for `MultiWellPlant`.
- **Depth as a design value:** a plant-level parameter `depth` (and the same on `Doublet`) that `set_params` passes to every doublet. Reservoir temperature and pressure follow from depth when not given explicitly: surface temperature plus gradient times depth, and hydrostatic pressure of the brine. The gradient and surface temperature are parameters with the challenge values (`30 K/km`, `12 degC`). The formulas go into `gemini/physics/doublet.py`. Explicit values win, as the redesign's Plant bookkeeping already does.
- **Tests:** a plant with 1, 2 and 3 doublets builds, round-trips and runs one day; depth 3000 m gives the expected reservoir temperature (12 + 30 * 3 = 102 degC) and pressure; an explicit temperature wins over the derived one.

## 4. Cooling units dispatched by role

`gm.schedule` takes at most one `HeatPump` and dispatches only an `AbsorptionUnit` as chiller. In `HeatingCoolingPlant` the compression chiller is a `HeatPump`, so "heat pump plus compression chiller" fails with "expected at most one". Adsorption and compression chillers are not dispatched.

- **Role from the wiring, not the class:** a unit whose useful outlet feeds the `CoolingGrid` (directly or through mixers and splitters) is a cooling unit; one that feeds the `HeatingGrid` is a heating unit. A `HeatPump` can be either. Add a small public helper on `Plant` for "what does this outlet feed" if one is not there, and use it in the schedule.
- **Cooling units:** absorption (heat driven, `thermal_cop`), adsorption (heat driven, its own COP, `cooling/_sorption.py`), and compression (electric: a `HeatPump` in cooling mode or a `CompressionChiller` class if one exists or is clearer; choose and say which). Heat-driven units add their drive heat to the heat need, as absorption does today. A compression chiller adds electricity, and its condenser heat goes to the environment.
- **Several cooling units:** `rules["cooling_order"]`, default heat-driven first (`absorption`, `adsorption`, `compression`), each up to its design capacity. Unmet cooling is no error, as unmet heat.
- At most one unit per role and kind stays a rule, with a clear `invalid_design` message if broken.
- The ATES plant's three commands (`storage.mode`, `source_valve.split_fraction`, `load_valve.split_fraction`) are set together if `gm.schedule` supports ATES; if it does not, say so and leave it.
- **Tests:** heat pump plus compression chiller; adsorption chiller; absorption plus compression with the order rule; a heat pump that feeds the cooling grid is not taken as the heating heat pump.

## 5. Heat delivered above demand

With an absorption chiller in series before the boiler, the whole drive flow passes the heating users at a fixed return temperature, so `gm.kpi.totals` heat delivered is 145.6 GWh against a demand of 111.7 GWh on the hackathon year. `HackathonPlant` avoids it by mixing the chiller return into the heating supply, which drops the supply to 66 degC on 219 days.

- **`HeatingGrid` output `surplus` [W]:** heat delivered above the demand, beside `unmet_demand`. Do the same for `CoolingGrid` if it can happen there.
- **`gm.kpi.totals`:** report useful heat (at most the demand) beside delivered heat and surplus. Say which one LCOH and LCTS use; it must be useful heat.
- **Fix the topology:** in every shipped plant with a heat-driven chiller, drive water the users do not need returns through a bypass (splitter plus mixer) without passing the users. The redesign closes loops in the engine, so the loop is allowed now. `gm.schedule` sets the bypass split from the balance. The heating supply must stay at its setpoint (100 degC in the challenge) on every day.
- **Tests:** surplus is zero when supply equals demand and positive when not; on a short window the fixed plant delivers the demand within tolerance with supply at the setpoint.
- List the changed numbers of the hackathon example (heat delivered, supply temperature, boiler, electricity), old and new.

## 6. Checks for the challenge requirements

- **Volume balance:** a `Doublet` output `volume_imbalance` = produced minus injected liquid volume flow [m3/s], both at the same conditions (say which: standard or reservoir). Today `d0.reservoir.liquid_flow` and `d0.sink.sandface_in.volume_flow` differ by about 7e-7 relative and are at different conditions. Use `Output.difference` if both sides are paths at the same conditions; otherwise add the produced volume at injection conditions as an output first.
- **Limits on parameters:** `gm.checks.Limits.add` also accepts a parameter path (`"d*.pump_efficiency"`, min 0.7). A parameter is checked once against its value in the run (or each valid-from value if it changes over time). The result is the same check shape.
- **No columns:** `gm.checks.limits` on a run whose every row failed raises a bare pandas `KeyError` (old `checks/limits.py:141`). Make it return a check with `passed: null`, `value: null` and a reason (`no_value`), for every limit. Failing test first.
- **Tests:** `volume_imbalance` is near zero on a balanced doublet; a parameter limit passes and fails; a run with no rows gives `passed: null`.

## 7. A hackathon example plant that runs the year

No example plant runs the demand year from its dict today: `DoubletHeatPlant` fails every day (`out_of_range`, a negative pressure) under the challenge schedule, several plants need input columns the schedule does not write, and template plants have no reservoir or well values.

- `inputs/plants/HeatingCoolingPlant.json` (and the other template plants where it makes sense) with the challenge values: reservoir (2500 m, 100 m thick, 200 mD, 250 barg or derived from depth), brine (1030 kg/m3, 0.40 mPa s, GLR 0.8 Nm3/m3, 80 % CH4 20 % CO2), pump efficiency 0.7, 2 doublets, supply 100 degC heating and 20 degC cooling, and the inputs of section 2. Read the values from `inputs/hackathon/` (README and PDF), not from memory.
- `gm.plants.example("HeatingCoolingPlant")` plus `gm.schedule` with the challenge rules runs all 365 days with no failed day, every doublet within 50 to 300 m3/h, brine cooling at most 40 K, 330 operating days, and the volume balance. Add it as an e2e example (`examples/cases/`) with its numbers in the output.
- Size the example `DoubletHeatPlant` so it runs at 50 to 300 m3/h without a negative pressure.
- For the other examples (`Doublet`, `NodalDoublet`, `MultiWellPlant`, `DistrictNetwork`, the substations), either make `gm.schedule` write the columns they need, or document in `plants.md` and in each class docstring that they are building blocks, not schedulable on their own. Say which for each.

## 8. Defaults for the optimiser

- **Default `profile`:** `profile=None` in `gm.optim.minimize` and `sample` means the hackathon demand year (heating and cooling from `gm.profiles`) and the challenge rules: `doublet_flow` 50 to 300 m3/h, `max_brine_cooling` 40 K, `operating_days` 330. Keep these rules in one public place (for example `gm.schedule.CHALLENGE_RULES` or a function), read from `inputs/hackathon/` if they are stored there, so geomind can show them.
- **Schedule per trial:** when `profile` is `None` (or a demand frame is given instead of a plan), each trial builds its plan with `gm.schedule` on the trial's plant, so a variable that changes the design changes the plan too.
- **Speed:** a trial took about 2.7 s on the hackathon year, mostly reading results (`opex` about 0.3 s, `lcts` about 0.6 s). Find why reading is slow (repeated column scans, recomputed annual energies) and fix it in the economics and results code. Target under 1 s per trial; report before and after.
- `assumptions=None` added in part A stays and is documented.

## 9. Injection wells in `gm.analysis.nodal`

- `gm.analysis.nodal` is declared `later` for injection wells. The redesign moved the nodal code to `gemini/analysis/solves.py`. Build the injection case as declared: the wellhead pressure an injection well needs for a given rate (and the rate for a given wellhead pressure, if declared).
- Return the same shapes as the production case. Tests on one well with a known answer.

## 10. Docker image for module sandboxes

geomind's `test_module` tool runs agent-written modules in a `DockerSandbox` and needs an image with gemini's dependencies.

- Add `docker/sandbox.Dockerfile`: a slim Python base of the version in `pyproject.toml`, gemini installed from the repository with its runtime dependencies, no network use at run time, a non-root user.
- Add `make sandbox-image` that builds it as `gemini-sandbox:<version>`.
- Build it once locally if Docker is available and run `python -c "import gemini"` inside it. Do not push the image anywhere; say what publishing it would need (registry name, login).
- Document it in `.claude/docs/` (where geomind can read the image name).

## 11. Docs

- `api.md`: `set_inputs`, the `inputs` key, `size` on template plants, `depth`, `surplus`, `volume_imbalance`, parameter limits, `cooling_order`, the challenge rules, `profile=None`, nodal injection, `attrs["quantities"]` of `gm.profiles.get` (only `units` is listed today), unreleased changes.
- `plants.md`, `modules.md`, `engine.md`, `equipment.md`, the checks, economics and schedule docs, `data.md` for the new value files, `AGENTS.md` "Start here", the README.
- Docs that still name removed things after the redesign (`spec`, templates, `Output.of`).
- Every docstring touched.

## 12. Report

- Commits, one per section.
- What the merge of part A needed.
- The `inputs` key and what it replaced.
- How roles are found, the compression chiller class chosen, and the cooling order.
- Hackathon year with `gm.plants.example("HeatingCoolingPlant")`: heat and cold delivered and useful, surplus, unmet, boiler, electricity, supply temperatures, LCTS, failed days (must be zero), and every requirement check.
- Every changed number from the baseline, with old and new value and why.
- Optimiser time per trial, before and after.
- Which examples are building blocks and which are schedulable.
- The Docker image: built or not, its size, what publishing needs.
- What this breaks in `geomind/` and `backend/` (read-only, file and line), including the geomind bridge `apply_inputs` in `geomind/tools/gemini/plants.py` that can now be removed.
