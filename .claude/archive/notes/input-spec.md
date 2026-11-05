# gemini project inputs: rules first, then every field placed by the rules (draft 3, agreed 2026-11-01 22:25)

Goal: every field has one home, and the reason it is there is a rule written below, not a habit or a taste. Where the rules do not decide, the doc says so (section 7).

## 1. Principles

- **P1 One owner, one place.** Every input value has exactly one owner, the party who may legitimately change it, and lives in exactly one file. A value is never written twice; a rule that *checks* a value is not a copy of it.
- **P2 Separate what varies separately.** Things that change independently live in separate objects, so each can be swapped without touching the others (one plant on many worlds, many plants on one world, one run reported two ways).
- **P3 The plant boundary is the control volume.** Inside it: what the designer selects. Outside it: conditions that cross the boundary (heat demanded, brine from the reservoir, electricity from the grid, money) and rules imposed by third parties.
- **P4 An input is anything that can change a result.** If a setting can change a number, it is an input and is recorded. If it provably cannot (number of processes; eager vs compiled, equal to 1e-9), it is not an input and lives in no file.
- **P5 Files decide everything.** The project files plus the gemini version determine every result. No default, no value hidden in code or in an example script.
- **P6 One representation per concept.** One way to write a quantity, a range, a distribution, a time series, a reference to another file, a choice.
- **P7 Strict.** Unknown key, wrong unit, missing value: error at load time, naming the path. Never a silent fix.
- **P8 General.** A field exists only if it means something for any geothermal heating and cooling project. A competition rule is a *value* of a general field, never a field.

## 2. The placement test

Ask in order; the first yes decides.

1. Can it change a result? No: runtime, not a file (P4).
2. Is it something the designer selects inside the boundary? Plant (P3).
3. Is it a rule a third party imposes on the outcome (brief, contract, permit, law, grid operator)? Case, `requirements`.
4. Is it a condition outside the boundary that the designer cannot change? Case: `site`, `demand`, `utilities`, `economics`.
5. Is it a choice of how to analyse (method, objective, metrics, budget, seed)? Study.

A value that passes none of them is not needed. A value that seems to pass two is two values. Two deliberate exceptions are stated in section 7: the period and resolution of a case (7.7) and the reporting conventions in economics (7.2).

## 3. Shared formats (P6)

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

## 4. The files and every field

### case.json (`kind: case`, `gm.Case`): the outside conditions over one period

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

### economics.json (`kind: economics`): all money

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

### plants/*.json (`kind: plant`): what the designer selects

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

### study.json (`kind: study`, optional): what to run, how

Optional: the Python functions work without it; the file records their arguments so a run is reproducible from files (P5) and an agent can write JSON instead of code. It is not a second layer.

| field | why here |
| --- | --- |
| `cases`, `plants` (paths) | which conditions and designs; every plant runs on every case |
| `prepare`: `["size"]` | an action before the method; its criteria (`backup`) come from the plant |
| `method`: `run` \| `minimize` \| `sample` \| `sensitivity` (later `replay`, `calibrate` with `measurements`) | how (test 5) |
| `objective`, `metrics` | what the analyst wants to know |
| `evaluations`, `samples`, `seed` | budget and reproducibility; required where the method needs them, no defaults |

### data/*.csv

Time series only, first column `time`. Referenced from the case or the study. Measurements of a real plant live here too (operation loop).

### runtime (not a file)

Processes, eager or compiled. Allowed only because they cannot change results (P4); a test keeps that true.

### results/ (written, never edited)

Per case: full plant form (`to_json(structure=True)`), copies of every input file, gemini version, report, verdict, series. P5 made concrete.

## 5. What moves, compared with today

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

## 6. What gemini checks on every run (not inputs)

Mass and energy conservation residuals, bounds declared by modules, steps that failed to converge. These are not rules anyone imposes; they say whether the numbers can be trusted. They feed the verdict with kind `numerical`.

## 7. Where the rules needed a decision (honest list)

1. **"Lifetime" was two values.** The investor's analysis period (economics) and how long a pump or heat pump lasts before replacement (plant). One field hid both; split.
2. **GWP and cost allocation.** Reporting conventions, sometimes fixed by a regulation (a carbon market prices CO2e with a named GWP set). They sit in `economics.accounting` because no report can be built without them; reporting one run two ways means two economics files.
3. **Production equals injection.** Two different things: a third-party rule (full reinjection is a permit condition) and a conservation residual (the solver's mass balance). The first is a requirement `reinjection_ratio` with the brief's band; the second is gemini's own check.
4. **Pump efficiency 0.7.** The value is the designer's (plant). The brief also imposes it, so a requirement checks it. Two different things, not a copy (P1).
5. **Numerical tolerances.** By P4 they are inputs, but most users should not touch them. Decision: they stay constants in code, listed in the docs, until a test shows one changes a reported number beyond its display precision; then it becomes an input. This is the one place P5 is relaxed, and it is stated.
6. **Capex keyed by equipment kind.** The case has to know gemini's equipment vocabulary. No rule removes this; `gm.check(plant, case)` makes the coupling explicit.
7. **Time and initial state.** First placed in the study (who picks the window: the analyst). Back in the case once the name stayed `Case`: a design case is conditions over a period, so the period and the state at its start belong to it, and signatures stay `(plant, case)` with no extra analysis object.
8. **Search ranges in the plant** make one file both "the design" and "the design space". Accepted: an alternative space is another plant file.
9. **Supply temperature** is a condition in `demand` and the plant only states a margin over it, so the value is not written twice.

## 8. Still open

- Profile uncertainty (for example demand times a factor), multi-year runs (reservoir decline, price escalation), several reservoir layers: formats above leave room (a series leaf, an `uncertainty` on a series, a list under `reservoir`) without changing what exists.
- Operation-loop methods (`replay`, `calibrate`, `live`): fit the study shape with `measurements`; not designed in detail.
- Decided: name `Case` (`gm.Case`, `case.json`).

## 9. Definitions

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

## 10. Checks and errors

- `case.check()`, `economics.check()`, `plant.check()`: what each object can know alone (units, coverage of series over `time`, ranges inside bounds, options allowed, every required parameter set, connections valid).
- `gm.check(plant, case)`: what needs both (a capex and fixed-opex entry for every kind the plant contains, every role a requirement names exists in the plant, an initial state for every stateful module, energy prices present when the plant's dispatch is `least_cost`).
- One name, `check`, everywhere. It returns a list of issues and never raises; an empty list means ready. `from_json` / `from_dict` run the object's own check and raise `ValidationError` carrying the same issues; `simulate` and every study function run `gm.check` first and raise the same way.

## 11. Naming

- Readers `from_<format>` (class methods on the class they return), writers `to_<format>`.
- One verb per action: `check`, `simulate`, `size`, `minimize`, `sample`, `sensitivity`, `report`, `verdict`, `compare`.
- Python signatures are `(plant, case, ...)`; the remaining arguments are only method settings (objective, budget, seed, metrics). Everything else comes from the files.
