# Task: rule-based project inputs for gemini: `Case`, economics, plant files, `Study`, one `check`

## 0. Context and rules

- This is a new session. Read `AGENTS.md` and every file in `.claude/docs/` first and follow them (start with `api.md`, `conventions.md`, `testing.md`).
- Repository: `/Users/sahand/Desktop/geomind-spe-geohackathon-2026/gemini`, remote `git@github.com:geomind-spe-geohackathon-2026/gemini.git`. `git fetch --prune`, `git checkout dev`, `git pull origin dev` (expected `fde7178b` or later), `git status` clean.
- **Branch:** `git checkout -b feature/inputs` from `dev`, one commit per section. At the end, if the development tests and the e2e tier pass: merge into `dev` with `--no-ff`, push `origin dev`, delete the branch locally (and on `origin` if it was pushed). No other session works in this repository now.
- **The design is in Appendix A** (the input specification: principles, placement test, formats, every field with the reason it is where it is, definitions, checks, naming). It is the source of truth for this task. Where the code already has a different name for the same thing, keep the code's name only if Appendix A gives no reason against it, and record the choice. Where Appendix A does not place something you find, apply its placement test (section 2) and record the decision in the docs (section 7 of `.claude/docs/inputs.md`); never guess silently.
- **gemini is the source of truth** and general. The competition case (`inputs/examples/hackathon_2026/`) is only a test sample; nothing in `gemini/` is named after it or tuned to it. Do not look at, mention or adapt to any other repository.
- **Standing rules:** one unit format (`gm.units.Quantity` at every public boundary, SI inside); no defaults for anything a user decides; `from_<format>` / `to_<format>`; update the code, never wrap it (no wrappers, shims, aliases, fallbacks to old names or shapes; old formats are refused with a clear error naming the new form, never read silently); only the real design in the public API (no stubs); no comments inside code (docstrings only); quality bar of `conventions.md`; a failing test before each bug fix.
- **Numbers do not change.** The same plant on the same conditions gives the same numbers before and after (1e-9 on the e2e tier and every example). The only intended new output is the second competition ranking (section 8). Any other difference is a bug to find, not a golden to regenerate.
- **Temporary files** go to `.tmp/inputs/` (git-ignored).

### You are the coordinator

Run the work in parallel and do not spend your own context doing it. You plan, hand out tasks, review short reports and diffs, decide, merge onto `feature/inputs`, and run the tests once per phase. You never edit more than a few lines yourself and never read large files whole.

- Workers are subagents on sonnet; read-only searches use haiku. Each works in its own git worktree under `../gemini-inputs-tmp/` on a local branch `inputs-<letter>` (never pushed), owns the files listed for it, commits once, runs only the tests of its files, and answers in at most 20 lines. Details go to `.tmp/inputs/<worker>.md`.
- **Phase 0, rules before code:** section 1. Nothing else starts until its docs are committed.
- **Phase 1:** A (section 2), the shared formats and the check machinery every other section uses.
- **Phase 2, in parallel:** B (section 3), C (section 4), D (section 5), E (section 6).
- **Phase 3, in parallel:** F (section 7, study), G (section 8, examples and inputs).
- **Phase 4:** H (section 9, public API and docs).
- An overlap between workers goes back to its owner. Remove your worktrees and `inputs-*` branches at the end.

### Tests

- Development profile only (`make test` / `scripts/test_changed.py`, with `test_code_quality.py`), parallel, under 300 s. New tests under about 1 s each, on small plants and short cases. Never run the slow dataset. Never delete or shrink goldens.
- A budget test that fails under load is rerun alone before it counts; name the tests you retimed.
- Run `examples/hackathon.py` at most twice in the whole task (once before any change as the control, once at the end), never two at a time; save both outputs in `.tmp/inputs/` and diff them.

## 1. Rules and definitions first (phase 0: coordinator + one sonnet worker R + haiku inventory)

- **Inventory (haiku):** list into `.tmp/inputs/inventory.md` every input that can reach a result today: every key of every `inputs/examples/*/case.json` and plant file, every parameter declared in `gemini/modules/**` and `gemini/plants/**`, every argument of every public function in `gemini/` (`simulate`, `schedule`, `call`, `study.*`, `evaluate.*`, `plants.*`, `case.*`), every constant in `gemini/` that a result depends on (solver tolerances, iteration limits), and every value written in `examples/*.py`.
- **Placement (R):** for each inventory row write its new home and the rule from Appendix A that puts it there (principle, placement-test question, or section 7 decision). A row the appendix does not place gets the placement test applied, written out. A row that seems to pass two tests is split into two values, and the split is written down. Output: `.tmp/inputs/placement.md`.
- **Docs (R):** write `.claude/docs/inputs.md` from Appendix A, adapted to the real names in the code: principles, placement test, formats, every file and field with its reason, definitions, checks and errors, naming, the honest decisions list (Appendix A section 7 plus every new decision from the placement step), and the open list. Add a short "Inputs" rule to `conventions.md` pointing to it ("a new input goes where the placement test says; the reason is written in inputs.md"), and a line in `AGENTS.md` "Start here".
- **Review (you):** every inventory row has a home and a reason; no reason is "convenience" or "it was there". Commit `docs: input rules and definitions`. Report the counts per home and every new decision in your final report.

## 2. Shared formats and the check machinery (worker A)

Owns a new internal module for input files (for example `gemini/_utils/inputs.py`, name by the existing layout), `gemini/units/` where it parses leaves, `gemini/errors/` (the issue type), and their tests.

- One reader for every leaf form of Appendix A section 3: quantity, dimensionless, choice, `range`, `options`, `uncertainty`, series (`file`, `column`, `unit`; first CSV column `time`, ISO 8601 with offset), section-as-path (relative to the containing file), `about` (kept, never read), file header (`format`, `kind`, `name`; wrong `kind` or unknown `format` refused).
- One issue type (`path`, `kind`, `message`, quantity, accepted units) and one way to raise: `ValidationError` carrying the issues. Every reader collects all issues of a file before raising, so one load reports everything wrong at once.
- One writer: `to_json` writes every leaf in the same form it reads (round trip exact, including a series given in kW: today a kW column keeps its unit name while values become W, a 1000x round-trip error; write the failing test first).
- Tests: every leaf form, every issue kind, round trip, all issues reported at once.

## 3. `Case` and economics (worker B)

Owns `gemini/case/`, the case schema in `docs/schemas/`, and their tests.

- `gm.Case` exactly as Appendix A section 4 (`case.json`): `about`, `time`, `initial_state`, `site` (with `fluid.dissolved_gas`, `air.relative_humidity`), `demand` (with return pressure), `utilities` (electricity CO2 intensity, gas composition and heating value), `economics`, `requirements`.
- `economics` as Appendix A (`economics.json`): `currency`, `price_year`, `discount_rate`, `analysis_period`, `capex` per kind (with the drilling depth-table form, interpolated linearly on measured length, no extrapolation), `opex.fixed`, `opex.variable`, `energy`, `carbon.price`, `revenue` (with subsidy amount and duration), `accounting` (`allocation`, `gwp` with the standard named). Its own class with `from_json`, `to_json`, `check`; the case holds it.
- `requirements`: role-based, `{name, on, quantity, unit?, over?, when?, min?, max?}`; `equals` removed (min = max); window quantities take no `over`. Add the role quantities Appendix A names that do not exist yet (`reinjection_ratio` on `doublet`, `unmet_share` on `heating_supply` and `cooling_supply`, `count` on `doublet`) where needed for the samples.
- `Case.from_dict(data, files={name: bytes})` reads series from the mapping with the same reader (no folder needed).
- Coverage: a series not covering `time` is an issue (`coverage`) naming file, column, covered and requested window; a coarser `step` averages, a finer one is an issue.
- `case.check()` and `economics.check()` per Appendix A section 10.
- `gm.case.roles()` lists roles and role quantities with dimension and whether they take `over`.
- Tests: every section; round trip; in-memory files; coverage; the requirements form; a depth table.

## 4. Plant files (worker C)

Owns plant reading and writing (`Plant.from_json` / `to_json` / `from_dict` / `to_dict`), parameter declarations in `gemini/modules/**` and `gemini/plants/**` for the moves below, and their tests.

- Plant file as Appendix A (`plants/*.json`): header, `type` or `modules` + `connections` (+ `outputs`), both given must agree; `params` mirrors the module tree; every leaf an object; `range` / `options` on any leaf.
- Every module declares its `kind` (pricing) and `role` (rules) where it has them, and the closed list for every choice parameter; `options` must be a subset; `range` must lie inside the declared bounds.
- Moves into the plant, with the same values in every stored plant: ESP `minimum_intake_pressure` and `maximum_gas_fraction` (today requirements in the case), `control.dispatch` (`least_cost` today, written explicitly; the schedule reads it; any other value is refused until implemented), plant-level `backup` (`peak` or `none`; today a `size` argument), and the search ranges and options that are today `case.choices` and the variables in `examples/hackathon.py`.
- Moves out of the plant into the case: gas grid composition (`utilities.gas`), consumer return pressure (`demand`).
- `technical_life`: add it only if gemini already models equipment replacement; otherwise list it in the open list of `inputs.md`.
- `plant.set_range(path, min=..., max=...)` and `plant.set_options(path, [...])` for Python use, same checks as the file.
- `plant.check()` per Appendix A section 10; `to_json(structure=True)` writes the full form.
- Remove `missing_parameters()` and `gm.plants.validate`; their callers use `check` (section 7 owns `gm.check`).
- Tests: both plant forms round trip; a range outside bounds and an option not allowed are issues; ESP limits fail a step as before.

## 5. Verdict, report, display (worker D)

Owns `gemini/evaluate/` and its tests.

- One verdict, `gm.evaluate.verdict(plant, case, results)`, `feasible` plus reasons of kind `requirement`, `failed_step`, `numerical` (mass and energy residuals, non-converged steps), `bound`. `report`, `compare` and the study use it; nothing else decides feasibility.
- `report` reads `economics.accounting`; no accounting argument.
- Display fixes (failing tests first): a temperature difference displays in K (today 40 K shows as -247 degC); long durations (`analysis_period`, payback) in `yr`, operating durations in `d`.
- Apply the case to a plant once per `(plant, case)` and reuse it inside `report`, `verdict`, `compare` (today every call copies the plant and re-applies the case). Same numbers.
- Tests: each verdict kind; the display cases; report with two economics files giving two allocations.

## 6. One unit format at the last two doors (worker E)

Owns parameter attribute assignment on modules and `Stream.with_`, and their tests.

- `esp.frequency = 50` and `Stream.with_(...)` still take bare SI numbers for dimensioned values. Same rule as `set_params`: a `Quantity`, a bare number only for a dimensionless value, same error. Internal code uses the private SI paths.

## 7. Study and `gm.check` (worker F, phase 3)

Owns `gemini/study/`, the top-level `gm.check`, and their tests.

- `gm.check(plant, case)` per Appendix A section 10. `simulate` and every study function run it first and raise with its issues.
- `size(plant, case)` reads `backup` from the plant. `minimize(plant, case, objective=..., evaluations=..., seed=...)` searches every `range` and `options` of the plant (continuous, integer and discrete), no default for `evaluations` (today 100: remove). `sample` and `sensitivity` read uncertainty from the case and its economics. Their results return plants (the best design is a plant, `to_json` gives a runnable plant file).
- `gm.Study` from `study.json` per Appendix A: `cases`, `plants`, `prepare`, `method`, `objective`, `metrics`, `evaluations`, `samples`, `seed`; `Study.run()` calls the same functions (no second implementation) and returns a result with every run's verdict and metrics, the comparison, the best plant, and `to_json(folder)` writing the run records of Appendix A (full plant form, copies of inputs, gemini version, report, verdict, series).
- Tests: a two-plant study on a short case; `minimize` over a range and an option; missing `evaluations` raises; best plant round trip gives the same metrics.

## 8. Example inputs and examples (worker G, phase 3)

Owns `inputs/examples/**`, `examples/**`, their expected outputs, and their tests.

- Convert every sample to the new files with the same numbers: `case.json`, `economics.json`, `data/*.csv` (first column `time`), `plants/*.json`, `study.json`, `README.md`. The README of each sample lists every value that is an assumption, and for `hackathon_2026` cites `docs/cost-sources` ids where a value comes from there (values themselves unchanged in this task).
- Competition rules from the brief as requirement values: doublet count 1-3, flow 50-300 m3/h while running, brine cooling at most 40 K while running, running time at most 330 d, pump efficiency 0.7, reinjection ratio 1 (band stated in the README as the brief's), heat and cold met (band stated and marked as an assumption).
- `examples/hackathon.py` becomes: load `study.json`, run it with `gm.runtime.settings(processes=...)`, print the comparison. It prints the ranking twice: with the brief's rules only (ESP limits not applied), and with the standard-stage ESP limits, because the 18.75 % free-gas limit holds for standard stages and the brief does not state it. Do not add a gas-handling pump.
- Every other example uses the new files and `check`.

## 9. Public API and docs (worker H, phase 4)

- Every public entry point follows the new model: `gm.Case`, `gm.case.*`, `gm.Study`, `gm.check`, `gm.simulate`, `gm.replay`, `gm.live`, `gm.resume`, `gm.Engine`, `gm.study.*`, `gm.evaluate.*`, `gm.analysis.*`, `gm.plants.*`, `Plant`: signatures, keyword names, return values, error paths, docstrings. Removed names are gone, not aliased.
- `public_api.json` regenerated with its hash; `docs/schemas/` regenerated for case, economics, plant, study; `.claude/docs/api.md` contract table lists every public name with its signature, and a quality test fails if a public name is missing from it or a listed name does not exist.
- `.claude/docs/inputs.md` updated with anything the implementation changed; `equipment.md` snippets that fail today (about 25) fixed; a docs test runs every `python` snippet in `.claude/docs/`.
- `CHANGELOG.md` and the version per `VERSIONING.md`; every changed signature, old and new, listed.

## 10. Report (at most 40 lines)

- Commits, the merge into `dev`, the pushed hash; branch and worktrees removed.
- Phase 0: inventory rows per new home, and every new decision with its rule.
- The final public shape (`Case`, economics, plant file, `Study`, `check`, `verdict`) with one short JSON or call each.
- Numbers: the control diff of `examples/hackathon.py` (empty apart from the second ranking), and the e2e tier result.
- Tests run and retimed; example times.
- An old -> new table of every public change.
- Anything not done, with the reason.

---

# Appendix A: input specification

## gemini project inputs: rules first, then every field placed by the rules (draft 3, agreed 2026-11-01 22:25)

Goal: every field has one home, and the reason it is there is a rule written below, not a habit or a taste. Where the rules do not decide, the doc says so (section 7).

### 1. Principles

- **P1 One owner, one place.** Every input value has exactly one owner, the party who may legitimately change it, and lives in exactly one file. A value is never written twice; a rule that *checks* a value is not a copy of it.
- **P2 Separate what varies separately.** Things that change independently live in separate objects, so each can be swapped without touching the others (one plant on many worlds, many plants on one world, one run reported two ways).
- **P3 The plant boundary is the control volume.** Inside it: what the designer selects. Outside it: conditions that cross the boundary (heat demanded, brine from the reservoir, electricity from the grid, money) and rules imposed by third parties.
- **P4 An input is anything that can change a result.** If a setting can change a number, it is an input and is recorded. If it provably cannot (number of processes; eager vs compiled, equal to 1e-9), it is not an input and lives in no file.
- **P5 Files decide everything.** The project files plus the gemini version determine every result. No default, no value hidden in code or in an example script.
- **P6 One representation per concept.** One way to write a quantity, a range, a distribution, a time series, a reference to another file, a choice.
- **P7 Strict.** Unknown key, wrong unit, missing value: error at load time, naming the path. Never a silent fix.
- **P8 General.** A field exists only if it means something for any geothermal heating and cooling project. A competition rule is a *value* of a general field, never a field.

### 2. The placement test

Ask in order; the first yes decides.

1. Can it change a result? No: runtime, not a file (P4).
2. Is it something the designer selects inside the boundary? Plant (P3).
3. Is it a rule a third party imposes on the outcome (brief, contract, permit, law, grid operator)? Case, `requirements`.
4. Is it a condition outside the boundary that the designer cannot change? Case: `site`, `demand`, `utilities`, `economics`.
5. Is it a choice of how to analyse (method, objective, metrics, budget, seed)? Study.

A value that passes none of them is not needed. A value that seems to pass two is two values. Two deliberate exceptions are stated in section 7: the period and resolution of a case (7.7) and the reporting conventions in economics (7.2).

### 3. Shared formats (P6)

| concept | form | rule |
| --- | --- | --- |
| file header | `{"format": 1, "kind": "case" \| "economics" \| "plant" \| "study", "name": "..."}` | `kind` lets a reader refuse a wrong file; `format` lets a reader refuse an old one |
| quantity | `{"value": 3000, "unit": "m"}` | `unit` present if and only if the quantity has a dimension; units from gemini's unit table |
| dimensionless | `{"value": 0.7}` | same object, so every leaf has one shape |
| choice | `{"value": "counterflow"}` | the module declares the closed list of allowed strings |
| range | `{"min": a, "max": b}` | either side optional; bare numbers in the leaf's unit; used for search ranges, distribution bounds, requirements and declared bounds alike |
| search freedom | `"range": {...}` or `"options": [...]` on a plant leaf | `options` is a subset of the module's list |
| uncertainty | `"uncertainty": {"kind": "uniform", "min", "max"}`, `{"kind": "triangular", "min", "max"}` (mode = `value`), `{"kind": "normal", "std", "min"?, "max"?}` | numbers in the leaf's unit; `value` is always the nominal |
| time series | `{"file": "data/demand.csv", "column": "heat_mw", "unit": "MW"}` in place of `value` | every CSV has a first column `time`, ISO 8601 with offset (or `Z`); no `time_column` key |
| reference | a section given as a string is a path to a file of the same shape | paths are relative to the file that contains them |
| metadata | `"about": {...}` | free text and labels (site name, coordinates, notes); never read by code, so it can never change a result |
| names | snake_case keys, module paths with dots (`d0.esp.efficiency`) | |

### 4. The files and every field

#### case.json (`kind: case`, `gm.Case`): the outside conditions over one period

A case in the engineering sense (a design case, a load case): the conditions outside the boundary over a stated period, and the third-party rules. Same for every plant compared (P2). The name stays `Case`: the earlier reason to rename it (freeing the word for design points) disappeared when design alternatives became plant files.

| field | why here |
| --- | --- |
| `about` | metadata (site name, coordinates); never read |
| `time`: `start`, `end`, `step` | a design case is the conditions *over a period*; the period and its resolution are part of the case. A step finer than a series is an error; coarser averages (mean power over the step) |
| `initial_state` (only if the plant has stateful modules) | the condition at the start of the period; a design case states it, an operation case takes it from measurements. Today a storage silently starts empty |
| `site.ground` surface temperature, gradient | nature, outside the boundary (test 4) |
| `site.reservoir` reference depth, thickness, permeability, pressure, pressure law with depth, temperature if measured | nature (test 4) |
| `site.fluid` density, viscosity, gas-liquid ratio, `dissolved_gas` composition | the brine is what the reservoir delivers (test 4); `dissolved_gas` named so it is not confused with grid gas |
| `site.air` temperature, relative humidity (constant or series) | weather (test 4); humidity because wet and dry coolers depend on it |
| `demand.heating`, `demand.cooling`: series, supply temperature, return temperature, return pressure | the consumer side of the boundary: how much, at what temperature it is wanted, at what temperature and pressure it comes back (test 4). Consumer return pressure moves here from plant.json |
| `utilities.electricity`: CO2 intensity (constant or series), connection voltage level if a module needs it | physical property of the grid (test 4) |
| `utilities.gas`: composition, heating value | physical property of the gas grid (test 4). Gas grid composition moves here from plant.json |
| `economics` (usually a path) | money conditions, see economics.json |
| `requirements` | third-party rules (test 3), see below |

`requirements`: each `{"name", "on": role, "quantity", "unit"?, "over", "when"?, "min"?, "max"?}`.

- `on` is a role (`doublet`, `heat_pump`, `plant`, `heating_supply`...), never a module name, so one case judges any plant (P2).
- A requirement may judge a result (flow, brine cooling, running time, unmet energy) or a plant property (doublet count, pump efficiency). Both are rules about the outcome; the value itself stays in the plant (P1).
- `equals` is dropped: one form, the range (P6). An exact rule on a discrete quantity is `min = max`; on a continuous one the brief's tolerance is written as the band. No tolerance is invented by gemini (P5).
- Competition rules as values: doublet count 1-3; flow 50-300 m3/h while running; brine cooling at most 40 K while running; running time at most 330 d; pump efficiency 0.7 (min = max); reinjection ratio 1 (see 7.3); heat and cold delivered (unmet share at most a stated band).
- Not requirements: equipment operating limits (plant), search ranges (plant), numerical conservation residuals (gemini checks them on every run, section 6).

#### economics.json (`kind: economics`): all money

Separate file because money varies independently of nature and demand (price cases, other country, other year) and pure physics runs do not need it (P2). It is a case section given by path, so the world stays one object and signatures stay `(plant, case)`.

| field | why here |
| --- | --- |
| `currency`, `price_year` | every price is meaningless without them |
| `discount_rate`, `analysis_period` | the investor's terms, not the designer's (test 4). Renamed from `lifetime`, see 7.1 |
| `capex.<equipment kind>` | market prices of equipment kinds; the kind list is gemini's catalogue, so a case prices kinds, not modules |
| `capex.drilling` | per metre, or a depth table (`{"depth": [...], "cost_per_metre": [...]}`) because published costs rise with depth |
| `opex.fixed.<kind>` | percent of capex per year, market practice per kind |
| `opex.variable` chemicals, waste disposal | consumables priced by the market |
| `energy.electricity`, `energy.gas` prices (constant or series) | money, so here, not in `utilities` (P1: the grid's physics and its tariff are two values with two owners) |
| `carbon.price` | money per tonne CO2-equivalent |
| `revenue.heat`, `revenue.cold`, `revenue.subsidy` (amount, duration) | money |
| `accounting`: `allocation` (heat cost share), `gwp` (CH4 and others, with the standard named) | conventions the report cannot be built without; a second convention is a second economics file (P2 kept by swapping the file) |

Each value may carry `uncertainty`. Sources are not fields (rejected earlier: no per-value source tag); the example README cites `docs/cost-sources` ids.

#### plants/*.json (`kind: plant`): what the designer selects

| field | why here |
| --- | --- |
| `type` or `modules` + `connections` (+ `outputs`) | structure is the designer's choice (test 2). `type` = structure from a gemini class; without it, from `modules`/`connections`; both given = must agree |
| `params` | one tree mirroring the module tree exactly; the plant itself is a module, so plant-level parameters sit at the top |
| structural parameters (doublet count) | designer (test 2); only class plants can rebuild themselves from a count |
| geometry, sizes, equipment properties | designer (test 2) |
| equipment operating limits (ESP minimum intake pressure, maximum free gas fraction, minimum flow) | property of the equipment chosen; a gas-handling stage has other limits than a standard stage (test 2) |
| model choices and calibrated coefficients (friction correlation, correction factors, fouling thresholds) | describe how *this* plant behaves; a calibrated plant is a new plant file (test 2) |
| control: setpoint margins, dispatch rule (`"dispatch": {"value": "least_cost"}`) | the control strategy is a design decision (test 2). gemini today applies least-cost merit order silently; writing it makes it visible and replaceable (P5) |
| design criteria used by sizing: `backup` (`"peak"` or `"none"`) | how much redundancy is a design decision (test 2), so it moves from the `size` call into the plant |
| `technical_life` per equipment kind where replacement matters | equipment property, see 7.1 |
| `range` / `options` on any leaf | the design space is the designer's statement of what is acceptable to build (test 2); how it is explored is the study's business |

Connections: from an outlet to an inlet; a fluid outlet feeds one inlet (branching through a splitter module); electricity and gas reach several consumers through a grid module.

#### study.json (`kind: study`, optional): what to run, how

Optional: the Python functions work without it; the file records their arguments so a run is reproducible from files (P5) and an agent can write JSON instead of code. It is not a second layer.

| field | why here |
| --- | --- |
| `cases`, `plants` (paths) | which conditions and designs; every plant runs on every case |
| `prepare`: `["size"]` | an action before the method; its criteria (`backup`) come from the plant |
| `method`: `run` \| `minimize` \| `sample` \| `sensitivity` (later `replay`, `calibrate` with `measurements`) | how (test 5) |
| `objective`, `metrics` | what the analyst wants to know |
| `evaluations`, `samples`, `seed` | budget and reproducibility; required where the method needs them, no defaults |

#### data/*.csv

Time series only, first column `time`. Referenced from the case or the study. Measurements of a real plant live here too (operation loop).

#### runtime (not a file)

Processes, eager or compiled. Allowed only because they cannot change results (P4); a test keeps that true.

#### results/ (written, never edited)

Per case: full plant form (`to_json(structure=True)`), copies of every input file, gemini version, report, verdict, series. P5 made concrete.

### 5. What moves, compared with today

| today | moves to | rule |
| --- | --- | --- |
| `case.choices` | `range` on plant leaves | test 2 |
| `demand.time_column` | fixed CSV column `time` | P6 |
| `constraints` ESP intake limits | ESP parameters in plant | test 2 |
| `constraints` `equals` | range with min = max | P6 |
| `volume_imbalance` | requirement `reinjection_ratio` + gemini's own balance check | 7.3 |
| `assumptions.finance.*` | `economics.json` | P2 |
| electricity and gas prices | `economics.energy` | P1 |
| CO2 intensity of electricity | `utilities.electricity` | test 4 |
| CH4 GWP, heat cost share | `economics.accounting` | report needs them; swap the file for another convention |
| `lifetime` | `economics.analysis_period` (+ plant `technical_life`) | 7.1 |
| `size(backup=...)` argument | plant-level `backup` | test 2 |
| hidden least-cost dispatch | plant `control.dispatch` | P5 |
| gas grid composition, consumer return pressure (plant.json) | `utilities.gas`, `demand` | test 4 |
| study settings in `examples/hackathon.py` | `study.json` | P5 |
| fixed solver tolerances in code | stay in code, documented | 7.5 |

### 6. What gemini checks on every run (not inputs)

Mass and energy conservation residuals, bounds declared by modules, steps that failed to converge. These are not rules anyone imposes; they say whether the numbers can be trusted. They feed the verdict with kind `numerical`.

### 7. Where the rules needed a decision (honest list)

1. **"Lifetime" was two values.** The investor's analysis period (economics) and how long a pump or heat pump lasts before replacement (plant). One field hid both; split.
2. **GWP and cost allocation.** Reporting conventions, sometimes fixed by a regulation (a carbon market prices CO2e with a named GWP set). They sit in `economics.accounting` because no report can be built without them; reporting one run two ways means two economics files.
3. **Production equals injection.** Two different things: a third-party rule (full reinjection is a permit condition) and a conservation residual (the solver's mass balance). The first is a requirement `reinjection_ratio` with the brief's band; the second is gemini's own check.
4. **Pump efficiency 0.7.** The value is the designer's (plant). The brief also imposes it, so a requirement checks it. Two different things, not a copy (P1).
5. **Numerical tolerances.** By P4 they are inputs, but most users should not touch them. Decision: they stay constants in code, listed in the docs, until a test shows one changes a reported number beyond its display precision; then it becomes an input. This is the one place P5 is relaxed, and it is stated.
6. **Capex keyed by equipment kind.** The case has to know gemini's equipment vocabulary. No rule removes this; `gm.check(plant, case)` makes the coupling explicit.
7. **Time and initial state.** First placed in the study (who picks the window: the analyst). Back in the case once the name stayed `Case`: a design case is conditions over a period, so the period and the state at its start belong to it, and signatures stay `(plant, case)` with no extra analysis object.
8. **Search ranges in the plant** make one file both "the design" and "the design space". Accepted: an alternative space is another plant file.
9. **Supply temperature** is a condition in `demand` and the plant only states a margin over it, so the value is not written twice.

### 8. Still open

- Profile uncertainty (for example demand times a factor), multi-year runs (reservoir decline, price escalation), several reservoir layers: formats above leave room (a series leaf, an `uncertainty` on a series, a list under `reservoir`) without changing what exists.
- Operation-loop methods (`replay`, `calibrate`, `live`): fit the study shape with `measurements`; not designed in detail.
- Decided: name `Case` (`gm.Case`, `case.json`).

### 9. Definitions

| term | definition |
| --- | --- |
| plant boundary | the control volume around everything the designer selects; what crosses it is described by the case |
| module | a unit of equipment or a grid with declared parameters, inlets, outlets, outputs, an optional `kind` and an optional `role` |
| plant | a module made of modules and connections; a gemini class (`type`) or a structure written out (`modules`, `connections`) |
| parameter | a value of a module the designer sets before a run and that does not change during it |
| leaf | one parameter or case value in a file: an object with `value` and, if dimensioned, `unit`; optionally `range`, `options`, `uncertainty`, or a series in place of `value` |
| quantity | a dimensioned value; in Python `gm.units.Quantity`, in JSON `{"value", "unit"}`; SI inside gemini |
| range | `{"min", "max"}`, either side optional, numbers in the leaf's unit; the one form for search ranges, distribution bounds, requirement bands and declared bounds |
| bounds | the physically valid range a module declares for a parameter; a search range must lie inside it |
| options | the allowed choices of a choice parameter in this plant; a subset of the closed list the module declares |
| uncertainty | a distribution on a case or economics value: `uniform`, `triangular` (mode = value), `normal` (std, optional bounds); `value` is the nominal |
| series | a time-varying value read from a CSV whose first column is `time` |
| kind | the equipment catalogue entry a module is priced as (`heat_pump`, `production_pump`, `drilling`...); keys of `economics.capex` and `opex.fixed` |
| role | the function a module plays in a plant (`doublet`, `heat_pump`, `chiller`, `heating_supply`, `plant`...); what requirements refer to. Kind says what it is (for cost), role says what it does (for rules) |
| role quantity | a result or property a role exposes to requirements, with a dimension (`production_flow`, `brine_cooling`, `reinjection_ratio`, `unmet_share`, `count`...). A per-step quantity takes `over`; a window quantity (a total or share over the period) does not |
| over | how per-step values are reduced: `each` (every step), `sum`, `mean`, `max`, `min`, `duration` (time the condition holds) |
| when | which steps count: `always` or `running` |
| case | the outside conditions over one period and the third-party rules (`gm.Case`) |
| economics | all money conditions and reporting conventions; a case section, usually its own file |
| requirement | a third-party rule on a result or a plant property; it judges, it never sets a value |
| study | which plants on which cases, with which method, objective, budget and seed (`gm.Study`); optional |
| method | `run`, `minimize`, `sample`, `sensitivity` (later `replay`, `calibrate`) |
| objective | the one metric `minimize` lowers |
| metric | a reported number (`lcts`, `co2`, `capex`...) |
| verdict | the single feasibility answer of one run: `feasible` plus reasons, each of kind `requirement`, `failed_step`, `numerical` or `bound` |
| issue | one problem found by a check: `path`, `kind` (`missing`, `unknown_key`, `unit`, `out_of_bounds`, `not_allowed`, `incompatible`, `coverage`), `message`, and for values the quantity and accepted units |
| check | a function that returns the list of issues and never raises |
| runtime setting | a setting that cannot change a result (processes, eager or compiled); never in a file |
| run record | what `results/` holds for one run: full plant form, copies of the inputs, gemini version, report, verdict, series |

### 10. Checks and errors

- `case.check()`, `economics.check()`, `plant.check()`: what each object can know alone (units, coverage of series over `time`, ranges inside bounds, options allowed, every required parameter set, connections valid).
- `gm.check(plant, case)`: what needs both (a capex and fixed-opex entry for every kind the plant contains, every role a requirement names exists in the plant, an initial state for every stateful module, energy prices present when the plant's dispatch is `least_cost`).
- One name, `check`, everywhere. It returns a list of issues and never raises; an empty list means ready. `from_json` / `from_dict` run the object's own check and raise `ValidationError` carrying the same issues; `simulate` and every study function run `gm.check` first and raise the same way.

### 11. Naming

- Readers `from_<format>` (class methods on the class they return), writers `to_<format>`.
- One verb per action: `check`, `simulate`, `size`, `minimize`, `sample`, `sensitivity`, `report`, `verdict`, `compare`.
- Python signatures are `(plant, case, ...)`; the remaining arguments are only method settings (objective, budget, seed, metrics). Everything else comes from the files.
