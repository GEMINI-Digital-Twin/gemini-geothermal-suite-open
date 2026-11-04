# Task: `gm.Case`, one unit format, and a complete hackathon example

## 0. Context and rules

- This is a new session. Read `AGENTS.md` and every file in `.claude/docs/` first and follow them.
- **The rule (most important):** gemini is a general geothermal heating and cooling package. Competition data is only a test sample, never the basis of a name, default or structure. gemini is the source of truth: inputs adapt to gemini, never the other way round.
- **Goal:**
  (a) one unit format in the whole package: every value with a unit is a `Quantity` with a unit from a `Unit` enum;
  (b) `gm.Problem` becomes `gm.Case`, a strict, typed entry boundary with fixed sections;
  (c) everything that does not describe the plant leaves the plant dict and goes into the case;
  (d) no defaults in the package for anything a user must decide;
  (e) the stubs that the hackathon flow needs are built, so the hackathon example runs from case to compared designs, and geomind has every call it needs;
  (f) only two examples remain: a JSON quickstart and the hackathon example.
- The design was agreed in discussion. The reference (case.json, the Python form, the quickstart) is the **Appendix** at the end of this prompt. Save it to `.tmp/case/design.md` and read it before section 1. Where the sections of this prompt and the appendix differ, the sections win.
- Start from `refactor` at `2453af1` in `/Users/sahand/Desktop/crust-team/gemini`. `git status` must be clean and `git pull origin refactor` must succeed. No other Claude session works inside `gemini/`.
- Where a decision below does not fit the code, stop that section and say why in the report instead of inventing another design.
- **Breaking changes are fine** (nothing is released). No shims, no aliases, no old names kept. Do not change the version; add change-log lines under "unreleased changes" in `api.md`.
- **Git:** work on `refactor`, one commit per section, in order. At the end, if the development tests and the e2e tier pass, `git push origin refactor` and report the hash.
- **Scope of changes:** only the gemini repository. Read `../geomind/` and `../backend/`, never change them.
- **Temporary files** go to `.tmp/case/` (git-ignored).
- **You are the coordinator (standing rule).** Run the work in parallel and do not spend your own context doing it. You plan, hand out tasks, review short reports and diffs, merge, and run the tests once. You never edit more than a few lines yourself and never read large files whole; a subagent does that and reports a summary.
  - Workers are subagents on a lighter model (sonnet); read-only searches use haiku. Each works in its own git worktree on a temporary branch, owns a fixed list of files, commits once, runs only the tests of its files, and answers with at most 20 lines: what changed, tests run, open problems. Details go to `.tmp/case/<worker>.md`.
  - Order:
    1. one worker: the baseline;
    2. one worker: section 1 (units), then one worker: section 2 (`gm.case`) together with the folder rename `optim/` → `study/` (moves and imports only, numbers identical); you merge each onto `refactor` and commit;
    3. four workers in parallel from that commit:
       - **A:** sections 3 and 4, owns `plants/`, `modules/` (except each module's `capex` / `fixed_opex` methods), `run/`;
       - **B:** section 5, owns `evaluate/` and the `capex` / `fixed_opex` methods of the modules;
       - **C:** section 6, owns `study/` (renamed from `study/`), `plants/capabilities*`;
       - **D:** section 7, owns `examples/`, `inputs/`, `tests/e2e/`, `tests/fixtures/`.
       Give each its section text, the rules of section 0, the reference file and its file list. C and D build on the names of sections 4 and 5 as written here; where they need something A or B has not built yet, they write against the agreed signature and you reconcile at the merge;
    4. you merge A, B, C, D in that order, hand any overlap back to the worker that owns it, and run the development tests once;
    5. one worker: section 8 (docs may be split over two workers); then the e2e tier once, the push and the report.
  - Never run the same full test set twice without a change in between. Remove the worktrees and temporary branches at the end. Target: well under an hour.
- **Tests:**
  - Development profile only (`make test` / `scripts/test_changed.py`, always with `test_code_quality.py`), parallel, under 300 s. New fast tests under about 1 s each.
  - **Baseline first:** before any change, run both sample problems (`inputs/examples/hackathon_2027/problem.json` with `plant.json`, and `inputs/examples/shallow_district/`) and save heat, cold, boiler, electricity, unmet demand, failed steps, LCTS, CO2 and every constraint result to `.tmp/case/baseline.json`.
  - After sections 1 to 4 the numbers of those runs must be identical (the same plant and the same values, now in the new shapes). Section 5 may change cost results (new capex items, fixed opex); list every change and why.
  - Never run the slow dataset locally. Never delete or shrink goldens; `inputs/` data may be converted and the files this prompt removes may be removed.
  - If a 1 s budget test fails, rerun it alone before treating it as a failure, and say which tests you retimed.
- **Standing rules, unchanged:** read/write naming (`from_<format>` classmethods, `to_<format>` methods, no `read_*`, `write_*`, `load_*`, `save_*`, `parse_*`, `dump_*`); `(plant, case)` signatures, plus `results` when a run is read; the run folders import no `compiler`, `data`, `study`, `evaluate`, `analysis`; the compiler stays optional.
- **Quality bar** as in `.claude/docs/conventions.md`: simple, readable, just enough code; nesting at most 3, functions about 40 lines, guard clauses; explicit `gm.errors` with codes; no comments inside code (docstrings only; the fixed section headers stay); black, isort and flake8 clean; a failing test before each bug fix.

## 1. One unit format (alone)

- **`gm.units.Unit`**: a `str` enum generated from the existing unit table in `units/conversions.py`, so there is one source of units. Member names are upper case words (`M`, `KM`, `M3_PER_H`, `DEG_C`, `BARG`, `EUR_PER_MWH`, `G_PER_KWH`, `PERCENT_PER_YR`, ...); values are today's unit strings. Add what the case needs and the table lacks: currency units built from `EUR` (`EUR`, `EUR/MWh`, `EUR/kWh`, `EUR/kg`, `EUR/t`, `EUR/W`, `EUR/m`, `EUR/(W/K)`), `g/kWh`, `t`, `yr`, `%/yr`. The currency is a label: an amount in `EUR` is stored as a number of the case's currency; do not convert between currencies.
- **`gm.units.Quantity(value, unit)`**: the existing frozen dataclass, now the one public shape. `value` is a number or an array; `unit` a `Unit` (a known unit string is accepted and turned into the member). Methods: `.si` (the value in SI), `.to(unit)` (a new `Quantity`), `to_dict()` → `{"value": ..., "unit": ...}`, `Quantity.from_dict(d)`. Equality compares SI values.
- **Quantity per field:** every declared quantity (`types/quantities.py`, `define_quantity`) knows its units (`gm.units.names(quantity)` today). A field typed with a quantity accepts only units of that dimension; anything else is `ValidationError` `invalid_unit` naming the field and listing the allowed units. The JSON schema of such a field is `{"value": number, "unit": enum of the allowed units}`.
- **At the public boundary only:** every public input with a dimension takes a `Quantity` (or its dict); a raw number is accepted only for a dimensionless quantity (efficiency, fraction, ratio, count, discount rate). Text such as `"2500 m"` is no longer accepted anywhere: remove `split_quantity`, `units.parse` and every place that reads unit text, and make them `invalid_value` with a message that shows the dict form. Inside the engine, physics and ops, values stay plain SI numbers; conversion happens once at the boundary, so the speed is unchanged.
- **Outputs:** every public scalar result (each value of `evaluate`, each `Check` value, `study` results) is a `Quantity` in SI. `Results.to_frame()` keeps SI numbers in its columns and gets a `units` mapping (`results.units[column]`), so no caller guesses a unit.
- Quality test: no public function signature or dict input accepts unit text; a fixed list of a few public inputs is called with a raw number with a dimension and must raise.
- Tests: round trip of `Quantity` through `to_dict` / `from_dict`; `.to` across offset units (`degC`, `barg`) and difference quantities; a wrong dimension; unit text rejected.

## 2. `gm.case` (alone, after section 1)

New folder `gemini/case/`. It replaces `run/problem.py`, `run/constraint.py` and `run/assumptions.py` (remove them). Every class is a strict pydantic model (`extra="forbid"`, frozen) with `to_dict`, `from_dict`, `schema`; `Case` adds `from_json(path)` and `to_json(path)` (the CSV files sit next to the JSON and are named in it). **Inside the case every value is stored in SI**: a `Quantity` given at construction is converted once; attributes are plain SI numbers or arrays; `to_dict` / `to_json` write `{"value", "unit"}` with the SI unit. No field has a default except "absent" (`None`); an absent value that a call needs raises `missing_value` naming its path (for an assumption the code is `missing_assumption`).

Public names: `gm.Case` at the top level, and under `gm.case`: `Case`, `Time`, `Environment`, `Ground`, `Reservoir`, `Fluid`, `Air`, `Demand`, `Service`, `Choices`, `Range`, `Constraint`, `Assumptions`, `Finance`, `Capex`, `Opex`, `Revenue`, `Allocation`, `Emissions`, `CO2`, `CH4`, `roles()`. Nothing else of the case is at the top level (remove `gm.Problem`, `gm.Constraint`, `gm.Assumptions`).

Sections, in this order:

- **`time`**: `start`, `end` (dates; `end` is excluded, so `2027-01-01` to `2028-01-01` is 365 days), `step` (a duration). Every profile of the case (demand, air, prices, CO2 intensity) is checked against it: same start, step and number of rows, else `invalid_value` naming the file and the first row that differs.
- **`environment`**:
  - `ground`: `surface_temperature`, `gradient`.
  - `reservoir`: `reference_depth`, `thickness`, `permeability`, `pressure` (at the reference depth), optional `temperature` (at the reference depth). Temperature at a depth: the given `temperature` shifted by the gradient, or, without it, `surface_temperature + gradient * depth`. Pressure at a depth: `pressure + fluid.density * g * (depth - reference_depth)`, with `g` the package's standard gravity. Put both rules in one function each in `physics/` and cite them in the docstring.
  - `fluid`: `density`, `viscosity`, `gas_liquid_ratio`, `gas` (mole fractions by species, keys from a closed list `CH4`, `CO2`, `N2`, `H2S`, summing to 1 within 1e-9). This replaces the plant dict's `fluids`.
  - `air` (optional): `temperature`, a constant `Quantity` or a CSV profile `{"file", "column", "unit"}`.
- **`demand`**: `file`, `time_column`, and `heating` / `cooling` (each optional, at least one), each a `Service` with `column`, `unit` (a power unit), `supply_temperature`, `return_temperature`. Profiles come only from CSV for now. Electricity and hot-water demand are not part of this task.
- **`choices`**: `doublets` (`Range` of integers) and `depth` (`Range` of lengths). A `Range` is `{min, max}` with `min <= max`. Nothing else for now.
- **`constraints`**: a list of `Constraint(on, quantity, min=None, max=None, equals=None, over="each", when="always")`.
  - `on` is a role and `quantity` a quantity of that role, both from the closed table `gm.case.roles()` (below); a quantity that the role does not have is `invalid_value` listing the role's quantities.
  - `over`: `each`, `sum`, `mean`, `max`, `min` (over the run) or `duration` (total time of the steps where `when` holds; bounds are durations). `when`: `always` or `running` (the unit carries flow).
  - A constraint applies to every unit of its role on its own. There is no constraint over the total of several units.
  - Supply temperatures are not constraints: the demand's `supply_temperature` is checked by gemini as a requirement of the service.
- **`assumptions`**:
  - `finance`: `currency` (a label), `discount_rate` (dimensionless), `lifetime`, `price_year`, and
    - `capex`: one factor per equipment kind (keys: the closed list of section 5), each a `Quantity` per capacity, per metre or a fixed amount, as the kind declares;
    - `opex`: `fixed` (per equipment kind, same keys as `capex`, each in `%/yr` of that kind's capex), `electricity`, `gas`, `chemical`, `waste_disposal`, `co2` (each a constant `Quantity` or a CSV profile);
    - `revenue`: `heat`, `cold` (same forms);
    - `allocation`: `heat_cost_share` (dimensionless).
  - `emissions`: by species, keys from the same closed list as `fluid.gas`: `CO2.electricity` (CO2 per energy of grid electricity bought; constant or profile), `CH4.gwp` (dimensionless).
- **Roles table** (`gm.case.roles()` returns `{role: [quantities]}`). A role is found from the module class, never from a module name. First version:
  - `doublet` (each `Doublet` child of the plant): `production_flow`, `brine_cooling`, `production_temperature`, `injection_temperature`, `pump_power`, `pump_efficiency`, `volume_imbalance`, `wellhead_pressure`;
  - `heat_pump`: `heat_output`, `cop`, `lift`; `boiler`: `heat_output`, `fuel_input`; `chp`: `heat_output`, `power_output`; `chiller` (absorption, adsorption, compression): `cold_output`, `cop`; `heat_exchanger`: `duty`, `approach`;
  - `heating_supply`, `cooling_supply` (the consumer side): `temperature`, `unmet`;
  - `plant`: `electricity_bought`, `gas_bought`, `co2`, `heat_surplus`, `cold_surplus`.
  Each entry maps to the result field or parameter it reads (one private table). If one of these fields does not exist in the results today, add it in section 4 or 5, or drop it from the table and say which.
- **No defaults in the package:** remove every default of the old `Assumptions` (`currency`, `methane_gwp`, `price_year`, the cited cost factors in `COST_SOURCES`). Their values and sources move into the hackathon `case.json` and its README (section 7). Universal physical constants and standard correlations stay in the package.
- Tests: round trip of a full case through `to_dict` / `from_dict` and `to_json` / `from_json`; SI storage (`Quantity(12, degC)` → 285.15); every validation error code; a profile off the time range; a quantity outside its role; the two reservoir rules.

## 3. The plant dict holds only the plant (subagent A)

- Remove from the plant dict, every plant class and every module parameter list what the case now holds: the `fluids` key; the consumers' return temperature and return pressure; air temperature; reservoir and ground values (`gradient`, `surface_temperature`, `thickness`, `permeability`, reservoir and sink pressure). Remove `Problem.site`, `apply_site` and the `*` path keys.
- **The case reaches the modules by class:** at the start of a run gemini sets, without changing the user's plant: the ground, reservoir and fluid values on every `Formation`, reservoir and `Doublet` (at the doublet's own depth, by the rules of section 2); air on every `Atmosphere` and on every module with an air input (coolers); return temperatures on the heating and cooling consumers from `demand`; the supply temperature requirement on the consumers. One private function per kind, in `run/_utils/`, with a test each.
- Plant parameters keep only design values (depths, diameters, nominal flows, efficiencies, sizes). Their values in the plant dict use `{"value", "unit"}` (section 1); `Plant.to_dict` writes that form.
- `gm.plants.schema()` and the class docstrings show the new form.
- Tests: a plant dict with a removed key is `invalid_value` naming the case section where the value now lives; the same plant on two cases with different reservoirs gives different production temperatures.

## 4. schedule and simulate take the case (subagent A)

- `gm.schedule(plant, case)` and `gm.simulate(plant, case, ...)`: rename every `problem` argument to `case`. Time comes from `case.time`.
- Constraints are found through roles. The schedule enforces what it can (flow range per doublet when running, maximum brine cooling, operating duration with outages as the lowest-demand steps spread over the doublets), and lists every other constraint in `plan.attrs["check_only"]`.
- Cost dispatch reads `finance.opex` prices and `opex.co2` with `emissions`; a price that a source of the plant needs and the case lacks is `missing_assumption` naming its path. The air profile, when given, is the air of each step.
- Numbers identical to the baseline for both sample problems.
- Tests: hourly and daily cases; a missing price; a constraint by role on a plant whose doublets have other names.

## 5. evaluate: costs on every equipment kind, and the stubs (subagent B)

- **Equipment kinds and capex:** a closed list of equipment kinds, each with its cost basis: `drilling` (per metre of well), `production_pump`, `injection_pump`, `circulation_pump` (per W of shaft power at the nominal flow), `heat_pump`, `boiler`, `electric_boiler`, `chp` (per W of capacity; CHP per W electric), `absorption_chiller`, `adsorption_chiller`, `compression_chiller` (per W of capacity), `heat_exchanger` (per W/K of conductance), `cooler` (per W of capacity), `pipe` (per metre), `thermal_storage`, `ice_storage` (per m3), `degasser`, `flare`, `gas_makeup` (fixed amount). Every module that is equipment declares its kind and has `capex(finance)` (and `fixed_opex(finance)` from `opex.fixed[kind]`); grids, environment, control, mixers, splitters and valves have none. At least every module used by the hackathon plants and by the plant classes `gm.plants.names()` returns must have it; list any equipment module left without a kind and why.
- A capex factor the case lacks for a kind the plant uses is `missing_assumption` naming `assumptions.finance.capex.<kind>`. There is no default factor anywhere.
- `gm.evaluate.capex(plant, case)` sums the items and returns them per module; `opex(plant, case, results)` adds fixed opex per kind to the energy and material costs; `lcoh`, `lcoc`, `lcts`, `npv`, `payback`, `annualised_cost` read `finance`; `co2` reads `emissions`.
- **`gm.evaluate.constraints(plant, case, results)`** checks every constraint by role and the service supply temperatures; each item `{name, role, unit_path, quantity, passed, value, limit, worst_step}` with `Quantity` values.
- **Build the stubs:**
  - `capacities(plant, case, results)`: for each equipment module, its design capacity and its peak use in the run (`Quantity`), and the share used.
  - `report(plant, case, results)`: one dict: energy totals, capacities, capex per module, opex, LCTS/LCOH/LCOC, CO2, every constraint result, failed steps. Plain JSON through `to_dict`, `Quantity` values in Python.
  - `compare(reports, by)`: rank reports by the given metrics, and mark the Pareto front when `by` has two or more metrics; returns a list with `to_frame()`.
- The legacy `results_to_frame` follows the naming rule (for example `Results.to_legacy_frame(project)`; say which name).
- Tests: capex of each kind; a missing factor; fixed opex per kind; capacities on a small plant; report keys; compare with two metrics and a known Pareto front.

## 6. study (was optim): sizing, discrete choices, sensitivity, capabilities (subagent C)

- **`gm.study.size(plant, case)`** returns a new plant with first sizes from the case: the doublet count (the smallest in `choices.doublets` that covers the heating peak with the brine cooling limit and the flow limits of the case's constraints, at the plant's depth), the nominal flows, and the capacities of the heat pump, boiler and chillers from the demand peaks and supply temperatures. It uses gemini physics only, explains each size in `plant.describe()` or a returned note, and raises `missing_value` when the case lacks what a size needs. A size it cannot compute for a module kind is left unchanged and listed.
- **`gm.study.minimize(plant, case, objective, ...)`**: the variables come from `case.choices` by default: `doublets` as an integer variable (the plant's structural size) and `depth` as a continuous one. Extra variables may still be given as today. A discrete variable is searched over all its values (with at most three doublet counts, run each count and search the continuous variables inside it). The result keeps today's shape, with `best.plant` as the best plant.
- **`gm.study.sensitivity(plant, case, parameters, metrics)`**: one at a time, each parameter at its low and high value, the change of each metric; returns a list sorted by effect (a tornado table) with `to_frame()`.
- **`gm.plants.capabilities()`**: for each plant class, the roles it contains, whether `gm.schedule` can plan it, and the choices it supports (doublets, depth). Built from the code, not from a hand list.
- Tests: `size` on the shallow sample gives one doublet and a covered peak; `minimize` over doublets 1 to 3 finds the cheapest of three precomputed runs on a small case; sensitivity order on a known plant; capabilities lists every plant class.

## 7. Examples and sample data (subagent D)

- **Keep 4 to 5 flat example files** (`quickstart.py`, `hackathon.py`, `costs.py`, `uncertainty.py`, `plant.py`; one-word file names, no underscore; 20 to 60 lines each, one function per step, public names only, values read with `.to(unit)`) and remove every other example. Remove `examples/basics/`, `recipes/`, `cases/` and their tests; keep any test the removed examples carried that tests gemini itself, rewritten as a unit test.
- **`examples/quickstart.py`**: about 20 lines on `inputs/examples/shallow_district/`: `gm.Case.from_json`, `gm.Plant.from_json`, `gm.simulate`, `gm.evaluate.constraints`, `gm.evaluate.report`, printing a few values with `.to(...)`.
- **`examples/hackathon.py`**: the whole flow geomind will drive, end to end, on `inputs/examples/hackathon_2027/case.json`:
  1. read the case and print its sections;
  2. for each candidate plant in `inputs/examples/hackathon_2027/plants/`: `gm.study.size`, then `gm.study.minimize` over the case's choices with objective `lcts`;
  3. simulate the best plant, check every constraint, print failed steps if any;
  4. `gm.evaluate.report` per candidate: capacities of every unit, heat and cold delivered, boiler and grid use, capex per unit, opex, LCTS, CO2;
  5. `gm.evaluate.compare(reports, by=["lcts", "co2"])` and the Pareto front;
  6. `gm.study.sensitivity` of the best design on LCTS for a few parameters;
  7. write the reports to `.tmp/` as JSON.
  Keep it readable: one function per step, no logic gemini should own. Every number printed comes from gemini. Its runtime should stay under a few minutes; use the smallest evaluation counts that give a stable answer and say what you chose.
- **Sample data:**
  - `inputs/examples/hackathon_2027/`: the organiser files unchanged, `demand.csv`, `case.json` (the reference file's case, plus the cited cost factors and `CH4.gwp` that leave the package, each with its source in the README; prices and the other factors stay marked as placeholders), and `plants/` with one plant dict per candidate (the current `plant.json` and the four `templates/` plants, converted). Merge `problem_with_treatment.json` into the one case; keep `plant_with_treatment.json` as a candidate if it runs on that case, else remove it and say why. Remove `problem.json`, `templates/`.
  - `inputs/examples/shallow_district/`: `case.json`, `demand.csv`, `plant.json`.
  - Rewrite both READMEs: what each file holds, which values are given by the organisers and which are assumptions of the example.
- `tests/e2e/test_examples.py` runs both examples; the hackathon one in the e2e tier only. The coverage test of the hackathon sample is kept and moved to the case.

## 8. Public API, quality tests, docs

- `gm.__all__`: replace `Problem`, `Constraint`, `Assumptions` with `Case` and the folder `case`; rename the folder `optim` to `study` (`gm.study.size`, `minimize`, `sample`, `sensitivity`; no `gm.optim` left); update the snapshot.
- Quality tests: no `Problem` / `problem` name left in `gemini/` (code and docstrings); no unit text accepted (section 1); `case` imports no `run`, `evaluate`, `study`, `compiler`; the case schema has `additionalProperties: false` at every level; no default value in `gm.case` other than absent.
- **geomind contract:** a section in `api.md` listing every call the hackathon example makes, with its signature and return shape. That is the list geomind follows.
- **Docs:** `api.md` (every moved, removed and new name, unreleased changes), `data.md` (`case.json` section by section, the unit format, CSV profiles), `conventions.md` (the unit rule, the no-defaults rule, `(plant, case)` signatures), `plants.md` (what the plant dict holds now), `engine.md` (how the case reaches modules by class), `testing.md`, `AGENTS.md` "Start here" and the Claude coding rules (the unit rule and the no-defaults rule as standing rules), README, every docstring touched.

## 9. Report

- Commits, one per section, and the pushed hash.
- Every removed and new public name.
- Numbers of both sample problems before and after, and every change with its reason.
- Equipment kinds, and any equipment module left without capex.
- The hackathon example's output summary: candidates, best design per candidate (doublets, depth, capacities), LCTS, CO2, the Pareto front, and its runtime.
- Any role quantity dropped from the table, and any decision of this prompt that did not fit the code.
- What this breaks in `../geomind/` and `../backend/` (read-only, file and line).

## Appendix: the agreed reference

# `gm.Case` example: JSON, Python and quickstart

Proposal, 2026-10-31. Nothing is implemented yet. The example problem is the competition inputs; prices and cost factors are placeholders.

Rules:
- Every dimensional value is `{"value", "unit"}` and the unit comes from `gm.units.Unit` (enum)
- A raw number only for a dimensionless quantity (efficiency, fraction, discount rate)
- An unknown key is an error; there is no default in the package
- Profiles come only from CSV, and all are checked against `time`
- Order of sections: `time`, `environment`, `demand`, `choices`, `constraints`, `assumptions`
- Assumptions in two groups: `finance` (anything that is money) and `emissions` (per substance, with the same names as `fluid.gas`)
- `opex.fixed` is an annual percent of capex, separate for each equipment type; the keys of `capex` and `opex.fixed` are the same closed list of equipment types in section 5 of the prompt
- `optim` is named `study`
- Inside `Case` everything is stored in SI; `Quantity` only at the input and output boundary
- Only `gm.Case` at the top level; the rest under `gm.case`
- Run prompt: `prompts/gemini-case.md` (where it differs from this file, the prompt is right)
- `end` is not included in the range (half-open): `2027-01-01` to `2028-01-01` means 365 days

---

### 1. `case.json`

```json
{
  "time": {
    "start": "2027-01-01",
    "end": "2028-01-01",
    "step": {"value": 1, "unit": "d"}
  },

  "environment": {
    "ground": {
      "surface_temperature": {"value": 12, "unit": "degC"},
      "gradient": {"value": 30, "unit": "K/km"}
    },
    "reservoir": {
      "reference_depth": {"value": 2500, "unit": "m"},
      "thickness": {"value": 100, "unit": "m"},
      "permeability": {"value": 200, "unit": "mD"},
      "pressure": {"value": 250, "unit": "barg"}
    },
    "fluid": {
      "density": {"value": 1030, "unit": "kg/m3"},
      "viscosity": {"value": 0.4, "unit": "mPa.s"},
      "gas_liquid_ratio": {"value": 0.8, "unit": "Nm3/m3"},
      "gas": {"CH4": 0.8, "CO2": 0.2}
    },
    "air": {"temperature": {"value": 10, "unit": "degC"}}
  },

  "demand": {
    "file": "demand.csv",
    "time_column": "date",
    "heating": {
      "column": "heating_demand_MWth",
      "unit": "MW",
      "supply_temperature": {"value": 100, "unit": "degC"},
      "return_temperature": {"value": 60, "unit": "degC"}
    },
    "cooling": {
      "column": "cooling_demand_MWcool",
      "unit": "MW",
      "supply_temperature": {"value": 20, "unit": "degC"},
      "return_temperature": {"value": 25, "unit": "degC"}
    }
  },

  "choices": {
    "doublets": {"min": 1, "max": 3},
    "depth": {
      "min": {"value": 2000, "unit": "m"},
      "max": {"value": 3500, "unit": "m"}
    }
  },

  "constraints": [
    {"on": "doublet", "quantity": "production_flow", "over": "each", "when": "running",
     "min": {"value": 50, "unit": "m3/h"}, "max": {"value": 300, "unit": "m3/h"}},
    {"on": "doublet", "quantity": "brine_cooling", "over": "each", "when": "running",
     "max": {"value": 40, "unit": "K"}},
    {"on": "doublet", "quantity": "production_flow", "over": "duration", "when": "running",
     "max": {"value": 330, "unit": "d"}},
    {"on": "doublet", "quantity": "pump_efficiency", "equals": 0.7},
    {"on": "doublet", "quantity": "volume_imbalance", "over": "each", "when": "running",
     "min": {"value": -1e-6, "unit": "m3/s"}, "max": {"value": 1e-6, "unit": "m3/s"}}
  ],

  "assumptions": {
    "finance": {
      "currency": "EUR",
      "discount_rate": 0.05,
      "lifetime": {"value": 25, "unit": "yr"},
      "price_year": 2015,
      "capex": {
        "drilling":   {"value": 1239,    "unit": "EUR/m"},
        "production_pump":    {"value": 0.5,  "unit": "EUR/W"},
        "injection_pump":     {"value": 0.5,  "unit": "EUR/W"},
        "heat_pump":  {"value": 0.67,    "unit": "EUR/W"},
        "boiler":     {"value": 0.06,    "unit": "EUR/W"},
        "chp":        {"value": 0.95,    "unit": "EUR/W"},
        "absorption_chiller":  {"value": 0.3, "unit": "EUR/W"},
        "compression_chiller": {"value": 0.3, "unit": "EUR/W"},
        "heat_exchanger":      {"value": 0.5, "unit": "EUR/(W/K)"},
        "degasser":   {"value": 1000000, "unit": "EUR"},
        "flare":      {"value": 100000,  "unit": "EUR"},
        "gas_makeup": {"value": 50000,   "unit": "EUR"}
      },
      "opex": {
        "fixed": {
          "heat_pump": {"value": 2, "unit": "%/yr"},
          "boiler":    {"value": 1.5, "unit": "%/yr"}
        },
        "electricity":    {"value": 100, "unit": "EUR/MWh"},
        "gas":            {"value": 40,  "unit": "EUR/MWh"},
        "chemical":       {"value": 3,   "unit": "EUR/kg"},
        "waste_disposal": {"value": 0.2, "unit": "EUR/kg"},
        "co2":            {"value": 80,  "unit": "EUR/t"}
      },
      "revenue": {
        "heat": {"value": 60, "unit": "EUR/MWh"},
        "cold": {"value": 60, "unit": "EUR/MWh"}
      },
      "allocation": {"heat_cost_share": 0.8}
    },
    "emissions": {
      "CO2": {"electricity": {"value": 300, "unit": "g/kWh"}},
      "CH4": {"gwp": 29.8}
    }
  }
}
```

Notes:
- The reservoir temperature is not given, so it is computed from the surface temperature and gradient (87 degrees at 2500 meters). If `reservoir.temperature` is given, it is the basis and the gradient is used only for another depth.
- Pressure at another depth is always: `p(z) = p_ref + rho_brine * g * (z - z_ref)`.
- Air temperature can also be a profile: `"air": {"temperature": {"file": "air.csv", "column": "t_air", "unit": "degC"}}`. The same shape for the `opex` and `revenue` prices and for `emissions.CO2.electricity`.
- There is no supply temperature constraint; `demand` has it itself and gemini checks it.
- Moved out of `plant.json`: consumer return temperature and pressure, fluid, air temperature, and all ground and reservoir values.

---

### 2. The same case in Python

```python
import gemini as gm
from gemini.units import Quantity as Q, Unit as U

case = gm.Case(
    time=gm.case.Time(
        start="2027-01-01",
        end="2028-01-01",
        step=Q(1, U.D),
    ),
    environment=gm.case.Environment(
        ground=gm.case.Ground(
            surface_temperature=Q(12, U.DEG_C),
            gradient=Q(30, U.K_PER_KM),
        ),
        reservoir=gm.case.Reservoir(
            reference_depth=Q(2500, U.M),
            thickness=Q(100, U.M),
            permeability=Q(200, U.MD),
            pressure=Q(250, U.BARG),
        ),
        fluid=gm.case.Fluid(
            density=Q(1030, U.KG_PER_M3),
            viscosity=Q(0.4, U.MPA_S),
            gas_liquid_ratio=Q(0.8, U.NM3_PER_M3),
            gas={"CH4": 0.8, "CO2": 0.2},
        ),
        air=gm.case.Air(temperature=Q(10, U.DEG_C)),
    ),
    demand=gm.case.Demand(
        file="demand.csv",
        time_column="date",
        heating=gm.case.Service(
            column="heating_demand_MWth",
            unit=U.MW,
            supply_temperature=Q(100, U.DEG_C),
            return_temperature=Q(60, U.DEG_C),
        ),
        cooling=gm.case.Service(
            column="cooling_demand_MWcool",
            unit=U.MW,
            supply_temperature=Q(20, U.DEG_C),
            return_temperature=Q(25, U.DEG_C),
        ),
    ),
    choices=gm.case.Choices(
        doublets=gm.case.Range(1, 3),
        depth=gm.case.Range(Q(2000, U.M), Q(3500, U.M)),
    ),
    constraints=[
        gm.case.Constraint(on="doublet", quantity="production_flow", over="each",
                      when="running", min=Q(50, U.M3_PER_H), max=Q(300, U.M3_PER_H)),
        gm.case.Constraint(on="doublet", quantity="brine_cooling", over="each",
                      when="running", max=Q(40, U.K)),
        gm.case.Constraint(on="doublet", quantity="production_flow", over="duration",
                      when="running", max=Q(330, U.D)),
        gm.case.Constraint(on="doublet", quantity="pump_efficiency", equals=0.7),
        gm.case.Constraint(on="doublet", quantity="volume_imbalance", over="each",
                      when="running", min=Q(-1e-6, U.M3_PER_S), max=Q(1e-6, U.M3_PER_S)),
    ],
    assumptions=gm.case.Assumptions(
        finance=gm.case.Finance(
            currency="EUR",
            discount_rate=0.05,
            lifetime=Q(25, U.YR),
            price_year=2015,
            capex=gm.case.Capex(
                drilling=Q(1239, U.EUR_PER_M),
                heat_pump=Q(0.67, U.EUR_PER_W),
                boiler=Q(0.06, U.EUR_PER_W),
                degasser=Q(1_000_000, U.EUR),
            ),
            opex=gm.case.Opex(
                fixed={"heat_pump": Q(2, U.PERCENT_PER_YR), "boiler": Q(1.5, U.PERCENT_PER_YR)},
                electricity=Q(100, U.EUR_PER_MWH),
                gas=Q(40, U.EUR_PER_MWH),
                co2=Q(80, U.EUR_PER_T),
            ),
            revenue=gm.case.Revenue(
                heat=Q(60, U.EUR_PER_MWH),
                cold=Q(60, U.EUR_PER_MWH),
            ),
            allocation=gm.case.Allocation(heat_cost_share=0.8),
        ),
        emissions=gm.case.Emissions(
            CO2=gm.case.CO2(electricity=Q(300, U.G_PER_KWH)),
            CH4=gm.case.CH4(gwp=29.8),
        ),
    ),
)

case.to_json("case.json")
assert gm.Case.from_json("case.json") == case
```

Location of the classes: all under `gm.case` (the `gemini/case/` folder): `Case`, `Constraint`, `Assumptions` and all the sections. Only `gm.Case` is also at the top level, like `gm.Plant`.

Errors at construction time:

```python
Q(300, U.M)                    # as production_flow max
### ValidationError: constraints[0].max: unit 'm' is not a volume flow; expected one of m3/s, m3/h, m3/d

gm.case.Reservoir(depth=Q(2500, U.M))
### ValidationError: reservoir: unknown key 'depth'; did you mean 'reference_depth'?

gm.case.Constraint(on="doublet", quantity="cop", max=5)
### ValidationError: constraint: 'cop' is not a quantity of 'doublet'; expected one of production_flow, ...

gm.evaluate.lcts(plant, case_without_prices, results)
### ValidationError (missing_assumption): assumptions.finance.opex.electricity is needed for lcts
```

---

### 3. quickstart

```python
"""Quickstart: one case, one plant, one year."""

import gemini as gm

case = gm.Case.from_json("inputs/examples/shallow_district/case.json")
plant = gm.Plant.from_json("inputs/examples/shallow_district/plant.json")

results = gm.simulate(plant, case)

for check in gm.evaluate.constraints(plant, case, results):
    print(check["name"], "ok" if check["passed"] else "VIOLATED", check["value"])

report = gm.evaluate.report(plant, case, results)
print("heat delivered:", report["heat_delivered"].to("GWh"))
print("cold delivered:", report["cold_delivered"].to("GWh"))
print("LCTS:          ", report["lcts"].to("EUR/MWh"))
print("CO2:           ", report["co2"].to("t/yr"))
```

The outputs are `Quantity`, so we no longer subtract and add table columns by hand and no longer convert units by hand.

The `examples/hackathon.py` path (summary):

```python
from pathlib import Path

case = gm.Case.from_json("inputs/examples/hackathon_2027/case.json")
reports = []
for path in sorted(Path("inputs/examples/hackathon_2027/plants").glob("*.json")):
    plant = gm.study.size(gm.Plant.from_json(path), case)
    best = gm.study.minimize(plant, case, objective="lcts")
    results = gm.simulate(best.plant, case)
    reports.append(gm.evaluate.report(best.plant, case, results))

print(gm.evaluate.compare(reports, by=["lcts", "co2"]).to_frame())
```

`minimize` reads its variables from `case.choices` (`doublets`, `depth`).
