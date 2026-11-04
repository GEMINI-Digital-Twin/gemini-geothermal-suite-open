# Inputs: what a project is made of, and where each value lives

This page is the rule for every input of a gemini project, written for the developer who adds, moves
or reads one. It is Appendix A of the input design adapted to the names of the code: `gm.Case`,
`gm.Plant`, `gm.Study`, `ValidationError`. Its section numbers follow the appendix, so "section 7 of
inputs.md" is the list of decisions. Every row of the inventory of inputs has a home and a reason in
`.tmp/inputs/placement.md`; this page holds the rules and the reasons that are not specific to one
row. A new input goes where the placement test of section 2 says; the reason is written here.

Status: built in 0.3.0 and extended to 0.5.3 (7.19, 7.27, 7.50, 7.51). The code, the sample files, the public API and the other docs follow this
page; what is not built yet is listed in section 8 and under "Decisions not built yet" in section 7.
Where a table of this page says "today", it describes the code of 0.2.0 that the row replaced.

## 1. Principles

- **P1 One owner, one place.** Every input value has exactly one owner, the party who may
  legitimately change it, and lives in exactly one file. A value is never written twice; a rule that
  checks a value is not a copy of it.
- **P2 Separate what varies separately.** Things that change independently live in separate objects,
  so each can be swapped without touching the others: one plant on many worlds, many plants on one
  world, one run reported two ways.
- **P3 The plant boundary is the control volume.** Inside it is what the designer selects. Outside
  it are the conditions that cross the boundary (heat demanded, brine from the reservoir,
  electricity from the grid, money) and the rules imposed by third parties.
- **P4 An input is anything that can change a result.** If a setting can change a number it is an
  input and is recorded. If it provably cannot (the number of processes; eager against compiled,
  equal to 1e-9) it is not an input and lives in no file.
- **P5 Files decide everything.** The project files plus the gemini version determine every result.
  No default, no value hidden in code or in an example script.
- **P6 One representation per concept.** One way to write a quantity, a range, a distribution, a
  time series, a reference to another file, a choice.
- **P7 Strict.** An unknown key, a wrong unit or a missing value is an error at load time that names
  the path. Never a silent fix.
- **P8 General.** A field exists only if it means something for any geothermal heating and cooling
  project. A competition rule is a value of a general field, never a field. gemini knows no sample.

## 2. The placement test

Ask in order; the first yes decides.

1. Can it change a result? No: runtime, not a file (P4).
2. Is it something the designer selects inside the boundary? Plant (P3).
3. Is it a rule a third party imposes on the outcome (brief, contract, permit, law, grid operator)?
   Case, `requirements`.
4. Is it a condition outside the boundary that the designer cannot change? Case: `site`, `demand`,
   `utilities`, `economics`.
5. Is it a choice of how to analyse (method, objective, metrics, budget, seed)? Study.

A value that passes none of them is not needed. A value that seems to pass two is two values; the
split is written (a setpoint that equals a supply temperature is a supply temperature in the case
and a margin in the plant, 7.14). Two deliberate exceptions are stated in section 7: the period and
resolution of a case (7.7) and the reporting conventions in economics (7.2).

Two classes of value are outside the test because they are not settings of any party. A constant of
nature, a unit factor, a published coefficient or a closed vocabulary defines the model and is
determined by the gemini version (7.30). A numerical tolerance or iteration limit is an input by P4
and stays in code for now (7.5). Neither is ever a value that a party can legitimately choose.

## 3. Shared formats (P6)

| concept | form | rule |
| --- | --- | --- |
| file header | `{"format": 1, "kind": "case" \| "economics" \| "plant" \| "study", "name": "..."}` | `kind` lets a reader refuse a wrong file, `format` lets it refuse an old one (7.11) |
| quantity | `{"value": 3000, "unit": "m"}` | `unit` present if and only if the quantity has a dimension; units from `gm.units.Unit`; text such as `"150 m3/h"` is refused as today |
| dimensionless | `{"value": 0.7}` | same object, so every leaf has one shape |
| choice | `{"value": "counterflow"}` | the module declares the closed list of allowed strings |
| range | `{"min": a, "max": b}` | either side optional; bare numbers in the leaf's unit; for search ranges, distribution bounds, requirements and declared bounds alike (`gm.case.Range` is this object). A `range` key on a leaf of a case or economics file (or a series leaf) is deprecated (7.51): read, used by nothing, warned about |
| search freedom | `"range": {...}` or `"options": [...]` on a plant leaf | `options` is a subset of the module's list |
| uncertainty | `"uncertainty": {"kind": "uniform", "min", "max"}`, `"triangular"` (mode = value), `{"kind": "normal", "std", "min"?, "max"?}` | numbers in the leaf's unit; `value` is always the nominal; `gm.case.Uncertainty` |
| time series | `{"file": "data/demand.csv", "column": "heat_mw", "unit": "MW"}` in place of `value` | every CSV has a first column `time`, ISO 8601 with offset or `Z`; no `time_column` key (7.38) |
| reference | a section given as a string is a path to a file of the same shape | paths are relative to the file that contains them |
| metadata | `"about": {...}` | free text and labels (site name, coordinates, notes); never read by code, so it can never change a result |
| names | snake_case keys, module paths with dots (`d0.esp.efficiency`) | in messages and issue paths; the plant `params` is a nested tree (7.12) |

## 4. The files and every field

The project is a folder: `case.json`, `economics.json` (usually given by path from the case), one or
more plant files, an optional `study.json`, and `data/*.csv`. `gm.Case.from_json` reads the case and
the CSV files and economics file it names; `gm.Plant.from_json` a plant; `results/` is written,
never edited.

### case.json (`kind: case`, `gm.Case`): the outside conditions over one period

A case in the engineering sense (a design case, a load case): the conditions outside the boundary
over a stated period, and the rules of third parties. It is the same for every plant compared (P2).
The name stays `Case`: the reason to rename it (freeing the word for design points) went when design
alternatives became plant files.

| field | why here |
| --- | --- |
| `about` | metadata (site name, coordinates); never read |
| `time`: `start`, `end`, `step` | a design case is the conditions over a period; the period and its resolution are part of the case (7.7). A step finer than a series is an error; a coarser step averages (mean power over the step) |
| `initial_state` (only if the plant has stateful modules) | the condition at the start of the period; a design case states it, an operation case takes it from measurements. Every `State` declaration is filled from here and has no code default (7.19) |
| `site.ground`: `surface_temperature`, `gradient`; and the ground and rock properties a module needs (`ground_conductivity`, `ground_diffusivity`, volumetric heat capacities, `porosity`, `soil_temperature`, `groundwater_flow`) | nature, outside the boundary (test 4). Replaces `environment.ground`; today `apply_case` sets the first two by class |
| `site.reservoir`: `reference_depth`, `thickness`, `permeability`, `pressure`, `temperature` if measured, and the properties of the aquifer (`top_depth`, `productivity_index`, `injectivity_index`) | nature (test 4). Pressure and temperature at another depth follow the laws of 7.35 |
| `site.fluid`: `density`, `viscosity`, `gas_liquid_ratio`, `dissolved_gas` (mole fractions of `CH4`, `CO2`, `N2`, `H2S`), `sand_concentration` | the brine is what the reservoir delivers (test 4). `dissolved_gas` is named so it is not confused with grid gas; sand per 7.17 |
| `site.air`: `temperature`, `relative_humidity` (constant or series), `pressure` | weather (test 4); humidity because wet and dry coolers depend on it, pressure per 7.20 |
| `demand.heating`, `demand.cooling`: series, `supply_temperature`, `return_temperature`, `return_pressure`; cooling also `indoor_temperature`, `indoor_relative_humidity`, `dew_point_margin` | the consumer side of the boundary: how much, at what temperature it is wanted, at what temperature and pressure it comes back (test 4, 7.18). `supply_temperature` is what the plant's margin refers to (7.9). The series replaces `demand.file`, `column`, `unit`, `time_column` |
| `utilities.electricity`: `co2_intensity` (constant or series), `import_limit`, `export_limit`, connection voltage level if a module needs it | physical property of the grid (test 4, 7.21). Replaces `assumptions.emissions.CO2.electricity` |
| `utilities.gas`: `composition`, `heating_value` | physical property of the gas grid (test 4). Replaces the plant parameter `GasGrid.composition` |
| `economics` (usually a path) | money conditions, see economics.json |
| `requirements` | third-party rules (test 3), see below. Replaces `constraints` |

`requirements`: each entry is `{"name", "on": role, "quantity", "unit"?, "over", "when"?, "min"?,
"max"?}`, with `over` and `when` as today (`each`, `sum`, `mean`, `max`, `min`, `duration`;
`always`, `running`). `over` and `when` keep the two defaults of the case, `each` and `always`.

- `on` is a role (`doublet`, `heat_pump`, `plant`, `heating_supply`, ...) from the closed table
  `gm.plants.roles()`, never a module name, so one case judges any plant (P2).
- A requirement may judge a result (flow, brine cooling, running time, unmet energy) or a plant
  property (pump efficiency). Both are rules about the outcome; the value itself stays in the plant
  (P1).
- `equals` is dropped: one form, the range (P6). An exact rule on a discrete quantity is `min` =
  `max`; on a continuous one the brief's tolerance is written as the band. gemini invents no
  tolerance (P5); the comparison slack of 7.5 is floating-point, not a tolerance of the brief.
- Competition rules as values: doublet count 1 to 3 (a plant `range`, not a requirement); flow 50 to
  300 m3/h while running; brine cooling at most 40 K while running; running time at most 330 d; pump
  efficiency 0.7 (`min` = `max`); reinjection ratio (7.3, 7.13); heat and cold delivered (unmet
  share at most a stated band).
- Not requirements: equipment operating limits (plant), search ranges (plant), numerical
  conservation residuals (gemini checks them on every run, section 6), and a limit that clips a
  value (7.21).

### economics.json (`kind: economics`): all money

A separate file because money varies independently of nature and demand (price cases, another
country, another year) and pure physics runs do not need it (P2). It is a case section given by
path, so the world stays one object and signatures stay `(plant, case)`. It replaces
`assumptions.finance` and the money part of `assumptions.emissions`.

| field | why here |
| --- | --- |
| `currency`, `price_year` | every price is meaningless without them; the currency is a label and nothing converts between currencies, as today |
| `discount_rate`, `analysis_period` | the investor's terms, not the designer's (test 4). `analysis_period` is the old `lifetime`, see 7.1 |
| `capex.<equipment kind>` | market prices of equipment kinds; the kind list is `gm.case.Capex` (the `equipment_kind` of the modules), so a case prices kinds, not modules. The unit tells the basis a catalogue publishes: a heat exchanger per W/K or per W of nominal duty, a storage per m3 or per MWh, a production pump per W or per unit; the size of another basis is a design value of the module (`nominal_duty`, `energy_capacity`), so it stays in the plant |
| `capex.drilling` | per metre, or a depth table (`{"depth": [...], "cost_per_metre": [...]}`) because published costs rise with depth |
| `opex.fixed.<kind>` | percent of capex per year, market practice per kind; or, for a kind sized by a power, an amount per capacity and year (`EUR/MW/yr`), the unit telling which |
| `opex.per_energy.<kind>` | variable O&M per energy each unit of a producing kind makes (`EUR/MWh`), market practice per kind like the fixed opex |
| `opex.variable`: `chemical`, `waste_disposal` (no other name) | consumables priced by the market, per kg; `chemical` is every product drawn from a `ChemicalGrid` (a scale or a corrosion inhibitor alike) |
| `energy.electricity`, `energy.gas` (constant or series) | money, so here, not in `utilities` (P1: the grid's physics and its tariff are two values with two owners) |
| `carbon.price` | money per tonne CO2-equivalent |
| `revenue.heat`, `revenue.cold`, `revenue.subsidy` (amount, duration; an amount per energy may have a `cap` and the `capacity` it is granted for) | money; the subsidy's terms are those of the grant, so here, not in the plant |
| `accounting`: `allocation` (heat cost share), `gwp` (CH4 and others, with the standard named) | conventions the report cannot be built without; a second convention is a second economics file (7.2) |

Each value may carry `uncertainty`. Sources are not fields: no per-value source tag; the example
README cites the `docs/cost-sources` ids ([economics.md](economics.md#the-values-of-the-
assumptions)).

### plants/*.json (`kind: plant`, `gm.Plant`): what the designer selects

| field | why here |
| --- | --- |
| `type` or `modules` + `connections` (+ `outputs`, `constraints`) | structure is the designer's choice (test 2). `type` = structure from a gemini class (`gm.plants.names()`); without it, from `modules` and `connections`; both given must agree |
| `size` | the structural arguments of a class plant (`doublets`, `producers`, `injectors`, `consumers`, `service`); beside `params` because they change the module tree (7.12). May carry `range` (the old `choices.doublets`). No default |
| `params` | one nested tree mirroring the module tree exactly; the plant itself is a module, so plant-level parameters (`depth`, `backup`, `control`) sit at the top (7.33) |
| geometry, sizes, equipment properties | designer (test 2) |
| equipment operating limits (ESP minimum intake pressure, maximum free gas fraction, minimum flow) | property of the equipment chosen; a gas-handling stage has other limits than a standard stage (test 2). The old case `constraints` on `intake_pressure` and `intake_gas_fraction` become ESP parameters |
| model choices and calibrated coefficients (friction correlation, correction factors, fouling and decline thresholds, skin) | describe how this plant behaves; a calibrated plant is a new plant file (test 2) |
| control: setpoints and their margins, flows, doses, `dispatch`, `outages` | the control strategy is a design decision (test 2). A setpoint on a supply line is a margin over `demand.<service>.supply_temperature` (7.14). `"dispatch": {"value": "least_cost"}` writes the merit order that `gm.schedule` applies silently today; `outages` the choice of outage steps (7.37). Replaces the plant `inputs` key |
| `backup` (`"peak"` or `"none"`) | design criterion used by sizing: how much redundancy is a design decision (test 2); moves from the `size(backup=)` call into the plant |
| `technical_life` per equipment kind where replacement matters | equipment property, see 7.1 |
| `fluids` | the working fluid of a closed circuit, where it differs from the module's own (test 2, 7.27) |
| `history` on a leaf (in memory `param_history`) | a value by date: what was built and when (7.16) |
| `range` / `options` on any leaf | the design space is the designer's statement of what is acceptable to build (test 2); how it is explored is the study's business. Replaces `case.choices` (7.8) |
| `sized`: true on a leaf | which leaves `size` computes from the demand (7.32) |

Connections run from an outlet to an inlet; a fluid outlet feeds one inlet (branching goes through a
splitter module); electricity and gas reach several consumers through a grid module. A plant file
holds no description of the world: the code already refuses a parameter that is declared with
`case=<path>` (the ground, the reservoir, the consumers' temperatures) with `invalid_value` naming
the case path, and the placement above extends that to every value of nature.

### study.json (`kind: study`, `gm.Study`, optional): what to run, how

Optional: the Python functions work without it; the file records their arguments so a run is
reproducible from files (P5) and an agent can write JSON instead of code. It is not a second layer.

| field | why here |
| --- | --- |
| `cases`, `plants` (paths) | which conditions and designs; every plant runs on every case |
| `prepare`: `["size"]` | an action before the method; its criteria (`backup`) come from the plant |
| `method`: `run` \| `minimize` \| `sample` \| `sensitivity` \| `evolve` (later `replay`, `calibrate` with `measurements`) | how (test 5); the algorithm and its fixed hyper-parameters are the method (7.28) |
| `objective`, `metrics`, `compare` keys | what the analyst wants to know |
| `evaluations`, `samples`, `seed`; for `evolve` `objectives`, `population`, `polish` | budget and reproducibility; required where the method needs them, no defaults (the old `evaluations = 100` and `SEED = 0` go) |
| `plan` (a path) | a run input that replaces the scheduled one (7.24) |
| `measurements`, bindings | outline only (7.15, section 8) |

### data/*.csv

Time series only, first column `time`. Referenced from the case or the study. Measurements of a real
plant live here too (operation loop).

### runtime (not a file)

Processes, eager or compiled (`backend`, `compile`), display units, error mode (`on_error`),
callbacks, checkpoint locations. Allowed only because they cannot change results (P4); a test keeps
that true. `precision` can change a result and is not runtime in this sense (7.26).

### results/ (written, never edited)

Per case: the full plant form (`to_json(structure=True)`), copies of every input file, the gemini
version, the report, the verdict and the series. P5 made concrete.

## 5. What moves, compared with today

| today | moves to | rule |
| --- | --- | --- |
| `Case.choices` (`doublets`, `depth`) | `range` on plant leaves (`size.doublets`, `params.depth`) | test 2, 7.8, 7.33 |
| `Case.environment` | `site` | test 4, 7.10 |
| `demand.time_column`, `demand.file` | fixed CSV column `time`; series leaf | P6, 7.38 |
| `Case.constraints` (`Constraint`) | `requirements` (`Requirement`) | test 3, 7.10 |
| `constraints` on ESP intake pressure and gas fraction | ESP parameters in the plant | test 2 |
| `constraints` `equals` | range with `min` = `max` | P6 |
| `volume_imbalance` (band 1e-6 / 1e-5 m3/s) | requirement `reinjection_ratio` and gemini's own balance check | 7.3, 7.13 |
| `assumptions.finance.*` | `economics.json` | P2 |
| electricity and gas prices (`opex.electricity`, `opex.gas`) | `economics.energy` | P1 |
| CO2 intensity of electricity (`assumptions.emissions.CO2.electricity`) | `utilities.electricity.co2_intensity` | test 4 |
| CH4 GWP, heat cost share | `economics.accounting` | 7.2 |
| `lifetime` | `economics.analysis_period` (+ plant `technical_life`) | 7.1 |
| `lifetime`, `discount_rate` arguments of `gm.evaluate` costs | removed; the economics file owns them | P1, 7.39 |
| `size(backup=...)` argument | plant-level `backup` | test 2 |
| hidden least-cost dispatch and outage choice in `gm.schedule` | plant `control.dispatch`, `control.outages` | P5, 7.37 |
| plant `inputs` (setpoints, flows, dose) | plant `params` control leaves; supply setpoints as margin | test 2, 7.14 |
| plant `inputs` `indoor_temperature`, `indoor_relative_humidity` | `demand.cooling` | test 4, 7.18 |
| plant `inputs` `sand_concentration` | `site.fluid.sand_concentration` | test 4, 7.17 |
| gas grid composition, consumer return pressure (plant file) | `utilities.gas`, `demand` | test 4 |
| `initial_*` parameters of storage modules; code defaults of states | `initial_state` | 7.7, 7.19 |
| `Atmosphere.pressure` default | `site.air.pressure` | 7.20 |
| `ElectricityGrid` import and export limits | `utilities.electricity` | 7.21 |
| `bindings` of the plant | `study` (`measurements`) | P2, 7.15 |
| plant dict `format: 2`, no `kind` | header `format: 1`, `kind: plant` | 7.11 |
| flat dotted `params` of a class plant | nested `params` tree | P6, 7.12 |
| study settings in `examples/hackathon.py` | `study.json` | P5 |
| `simulate(clock=)`, `Dataset` `tz`, `DEFAULT_STEP` | `case.time`; offsets in timestamps | P1, 7.25 |
| fixed solver tolerances in code | stay in code, documented | 7.5 |

## 6. What gemini checks on every run (not inputs)

Mass and energy conservation residuals (`gm.evaluate.mass_balance`, `energy_balance`,
`plant_balance`), bounds declared by modules (`gm.evaluate.bounds`), and steps that failed to
converge. These are not rules anyone imposes; they say whether the numbers can be trusted. They feed
the verdict with kind `numerical`. Their tolerances are the constants of 7.5.

## 7. Where the rules needed a decision (honest list)

7.1 to 7.9 are the decisions of Appendix A with their numbers. 7.10 on are the decisions of the
placement step, one for each place where the rules did not decide or where the code's name or value
had to be reconciled with them. Each names the rule that puts the row there.

**7.1 Lifetime was two values** (rule: test 4, test 2). The investor's analysis period (economics)
and the years a pump or heat pump lasts before replacement (plant) were one field,
`assumptions.finance.lifetime`. It splits into `economics.analysis_period` and the plant
`technical_life` of an equipment kind where replacement matters. The samples state 25 yr and 30 yr;
both are the analysis period. No sample states a technical life and replacement is not modelled
today, so no `technical_life` value is written.

**7.2 GWP and cost allocation** (rule: reporting conventions). They are reporting conventions,
sometimes fixed by a regulation (a carbon market prices CO2-equivalent with a named GWP set). They
sit in `economics.accounting` because no report can be built without them
(`allocation.heat_cost_share`, `gwp`); reporting one run two ways means two economics files. This is
one of the two deliberate exceptions to the placement test.

**7.3 Production equals injection** (rule: test 3, section 6). Two different things: a third-party
rule (full reinjection is a permit condition) and a conservation residual (the solver's mass
balance). The first is a requirement `reinjection_ratio` with the brief's band, the second is
gemini's own check. The band is expressed in 7.13.

**7.4 Pump efficiency 0.7** (rule: test 2, test 3). The value is the designer's
(`params.<doublet>.pump_efficiency`). The brief also imposes it, so a requirement on role `doublet`,
quantity `pump_efficiency`, checks it (`min` = `max` = 0.7). Two different things, not a copy (P1).
The requirement is judged with the relative slack of 7.5, as `equals` is today, so the verdict does
not change.

**7.5 Numerical tolerances** (rule: P4, P5 relaxed). By P4 they are inputs, but most users should
not touch them. They stay constants in code, listed in this document, until a test shows one changes
a reported number beyond its display precision; then it becomes an input. This is the one place P5
is relaxed. The list is in section 7.5 below.

**7.6 Capex keyed by equipment kind** (rule: test 4). The case has to know gemini's equipment
vocabulary (the `kind` of a module). No rule removes this; `gm.check(plant, case)` makes the
coupling explicit.

**7.7 Time and initial state** (rule: test 4). A design case is conditions over a period, so the
period (`time.start`, `end`, `step`) and the state at its start (`initial_state`) belong to the case
and signatures stay `(plant, case)`. This is the other deliberate exception to the placement test.

**7.8 Search ranges in the plant** (rule: test 2). They make one file both the design and the design
space. Accepted: an alternative space is another plant file.

**7.9 Supply temperature** (rule: P1, test 4). The supply temperature is a condition in `demand`,
and the plant states only a margin over it, so the value is not written twice. How this maps onto
today's setpoints is in 7.14.

**7.10 Names: where the code's name is kept and where it changes** (rule: section 11, section 4).
Kept, because Appendix A gives no reason against: `Case` / `gm.Case`, `Results`, `Dataset`, `size`
(see 7.12), `bindings` (see 7.15), `param_history` (kept as the name of the dated values, see 7.16),
`kind` and `role`, the closed role table `gm.plants.roles()`, `over`, `when`, `metrics`, `objective`,
`seed`, `evaluations`, `temperature_setpoint`, `return_temperature`, `supply_temperature`. Changed,
because Appendix A gives the reason: `environment` becomes `site` (the word names the party that
owns it, test 4); `environment.fluid.gas` becomes `site.fluid.dissolved_gas` (not confused with grid
gas); `constraints` becomes `requirements` (the case holds rules of third parties, and `constraint`
is already `Plant.constrain`, the plant dict `constraints` and `gm.evaluate.constraints`);
`assumptions.finance.lifetime` becomes `economics.analysis_period` (7.1); `assumptions.finance`
becomes `economics` (a file, P2); `opex.electricity` and `opex.gas` become `economics.energy.*`;
`opex.co2` becomes `economics.carbon.price`; `opex.chemical` and `opex.waste_disposal` become
`economics.opex.variable.*`; `emissions.CO2.electricity` becomes
`utilities.electricity.co2_intensity`; `count` of `gm.study.sample` becomes `samples`; the
structural key `choices` disappears (7.8). `Constraint` (the class) becomes `Requirement` with the
case.

**7.11 File header and the format number** (rule: section 3, P7). Every file starts with `{"format":
1, "kind": ..., "name": ...}`. Today's plant dicts say `format: 2` and carry no `kind`; case and
demand files have no header. The new numbering is per kind and starts at 1: the generation marker 2
of the old plant dict (`FORMAT` in `gemini/plants/_utils/serialization.py`) is retired, a file with
`format: 2` and no `kind` raises `ValidationError` with code `old_format` (the plant dict already
does this for older formats), and the shipped sample files are rewritten once. `name` is metadata
like `about`: it never changes a result. Numbers do not change because the conversion only moves
values.

**7.12 Where the plant's `size` goes, and the shape of `params`** (rule: test 2, P6). A structural
parameter (the doublet count, `producers`, `injectors`, `consumers`, `service`) changes the module
tree, so it cannot sit inside `params`, which mirrors the module tree. It stays a key beside
`params`, named `size` as today, and it may carry `range` (the old `choices.doublets`). Its
constructor defaults (`doublets = 1`, `consumers = 2`, `service = 'heating'`, `producers = 2`,
`injectors = 1`) are removed: a count is the designer's. `params` is one nested tree, module by
module (`params.d0.esp.efficiency`); the flat dotted keys of today's class form (`"d0.roughness":
...`) are read only by the old-format reader and disappear. `to_dict(structure=True)` writes the
same tree.

**7.13 How the `volume_imbalance` band becomes `reinjection_ratio`** (rule: 7.3, test 3). Today: a
constraint on role `doublet`, quantity `volume_imbalance` (produced less injected liquid volume
flow, a plant output), `over: each`, `when: running`, band -1e-6 / +1e-6 m3/s (hackathon_2026) and
-1e-5 / +1e-5 m3/s (shallow_district). New: quantity `reinjection_ratio` of role `doublet`,
dimensionless, the injected over the produced liquid volume flow, `over: each`, `when: running`,
`min` and `max` around 1. Both samples carry the relative band `min` 0.99999 and `max` 1.00001. The
band is not the old one converted: the old band was absolute (1e-6 m3/s hackathon_2026, 1e-5 m3/s
shallow_district), a ratio band is relative to the flow. The first conversion (0.999999 to 1.000001
for hackathon_2026) failed the check of `HackathonPlant` sized with `backup="peak"`, whose worst
imbalance is 2.2e-3 m3/h at about 300 m3/h (a ratio of 0.9999925, 6.2e-7 m3/s, inside the old
1e-6 m3/s), so the verdict changed; 0.99999 to 1.00001 keeps the verdict of every sample plant.
The band is not the brief's: the brief's tolerance for full reinjection is not in the repository,
and gemini invents none (P5), so the sample states a band that keeps the old verdicts and the open
list says it must be replaced by the brief's. `when: running` never divides by a zero flow. A scheduled run is unaffected: `gm.schedule`
reads no `volume_imbalance` limit.

**7.14 Setpoints, plant `inputs` and the margin over the supply temperature** (rule: 7.9, P1, test
2). The plant dict key `inputs` disappears; there are no plant `inputs` any more, because a setpoint
is a control and a control is a parameter of the module that owns it (test 2, `control`). Each of
today's 21 plant inputs goes as follows. The setpoint of a unit on a supply line (`heat_pump`,
`boiler`, `peak_boiler`: heating; `chiller`, `absorption_chiller`, `compression_chiller`: cooling)
is today a copy of the demand's supply temperature: 100 degC against
`demand.heating.supply_temperature` 100 degC, 65 against 65, 20 against
`demand.cooling.supply_temperature` 20, 16 against 16. Under 7.9 the plant states a margin,
`params.<unit>.supply_margin` = {"value": 0, "unit": "K"}, and gemini derives `temperature_setpoint`
= supply temperature plus margin for a heating unit and supply temperature minus margin for a
cooling unit (the cooling requirement is a maximum, so the unit must stay colder). The margin is the
difference of the two sample values, 0 K in every sample, so the setpoint is the same float (373.15
K + 0.0, 338.15 K + 0.0, 293.15 K - 0.0, 289.15 K - 0.0). A project whose setpoint is not at the
demand's supply temperature states the difference. The unit is the wiring role found by
`plant.feeds` (the rule `gm.schedule` already uses). A setpoint that equals no case value is an
absolute control leaf, `params.<unit>.temperature_setpoint`: the three coolers' 15 and 25 and 18
degC and the flows of the coolers (800, 200, 400, 60 kg/s). `injection_pump.pressure_setpoint` (30,
36, 60 bar) is an absolute control leaf. `dosing.dose` (10 ppm) is a control leaf.
`cooling_consumer.indoor_temperature` and `indoor_relative_humidity` go to `demand.cooling` (test 4:
the building's state). `desander.sand_concentration` goes to `site.fluid` (7.17). A value that a run
supplies per step (a column of `plan`, or what `gm.schedule` computes) wins over a constant control,
as today.

**7.15 `bindings` and the data columns** (rule: P2, section 8). A binding names a column of a data
file for a control or boundary of a module. A plant that holds column names is tied to one dataset,
which P2 forbids (one plant on many datasets), so `bindings` leaves the plant file and belongs to
the study (`measurements` of the methods `replay`, `calibrate`; designed only in outline, section
8). All samples hold `{}`, so no value moves. `gm.Plant.set_bindings` and `bindable` remain as the
in-memory door until the study shape exists.

**7.16 `param_history`** (rule: test 2). Dated values (a pump replaced on a date) are a statement of
what the designer built and when. They stay in the plant: a leaf may carry `history`, a list of
`{valid_from, value}`; the in-memory name stays `param_history`. All samples hold `{}`.

**7.17 Sand and the other solids of the brine** (rule: test 4). `desander.sand_concentration` (20
mg/l) is a boundary of the desander and the brine brings the sand from the reservoir:
`site.fluid.sand_concentration`. The erosion function also needs the particle material, diameter and
shape factor, which describe the same sand: when an erosion module needs them they are `site.fluid`
leaves too (open list). The pipe's material, hardness and density are plant parameters.

**7.18 Consumer side of the boundary** (rule: test 4). `return_pressure` (and the temperature limits
`minimum_return_temperature`, `maximum_return_temperature`) of the heating and cooling grids, and
`dew_point_margin` of the cooling grid, are conditions of the consumer, not choices of the designer:
the building decides how cold the water may be before it condenses. They move to `demand.heating`
and `demand.cooling` next to `supply_temperature` and `return_temperature`, with
`indoor_temperature` and `indoor_relative_humidity`. If a project wants the dew-point margin as the
designer's safety factor it is a different field, not a different place for this one.

**7.19 Initial state, and no default for a state** (rule: 7.7, P5; built). Every `State` declaration
of a shipped module is the value at the start of the period and comes from `case.initial_state`, a
section present if and only if the plant has stateful modules. A state has no code default and no
`initial_*` parameter is left (`IceStorage.initial_ice_fraction`, `IceStorage.initial_temperature`
and `ThermalStorage.initial_temperature` moved into the state, and the accumulator zeros of
`AquiferStorage`, `ThermalDecline`, `BoreholeField` and the `PIDController` integrator left
`DECLARED_DEFAULTS`). The form is `initial_state: {module path: {state name: {"value", "unit"}}}`
(for a plant, the path of the stateful child); the unit is read as a plain unit and the dimension
is the declaration of the state, which `gm.check` compares (7.43). `apply.started(case)` turns it
into the nested state tree the engine scans from, and a checkpoint or `results.end_state` starts a
later run. A stateful module without a stated start raises `missing_value` naming the case path
(`gm.check` lists it first as a `missing` issue); a state or module the plant lacks is
`unknown_name`. "None yet" is a value, not `None`: a `PIDController` starts with `integral = 0`,
`previous_error = 0` and `previous_step = 0` (no previous step), written in the case like any other
state, because the rule has no exception for a zero that is a definition. A state connection
(`type: state` in `connections`) keeps its previous values in the plant's own state and has no entry
in the case: the first step reads the stream at rest at the temperature the source module guesses
([engine.md](engine.md#time-as-a-scan)). The samples have no stateful module, so no number changes.

**7.20 Ambient air pressure** (rule: test 4, P5). `Atmosphere.pressure` has a declared default, the
normal pressure of DIN 1343. Air pressure is weather and depends on the altitude of the site, so it
is `site.air.pressure`, required where a module needs it. The samples that contain an `Atmosphere`
state 101325 Pa, the same float.

**7.21 Grid connection limits** (rule: test 4, definition of requirement).
`ElectricityGrid.import_limit` and `export_limit` clip the exchange (`min(demand, limit)`), so they
set a value. A requirement judges and never sets a value, so they cannot be requirements even though
a grid operator imposes them: they are `utilities.electricity.import_limit` and `export_limit`. A
cap the operator imposes on the outcome without clipping it (the 6 MW limit of `examples/costs.py`
on `electricity_bought`) is a requirement on role `plant`.

**7.22 `DECLARED_DEFAULTS`** (rule: P5, 7.5). The registry in `tests/unit/test_code_quality.py` is a
rule about code, not an input. Of its entries, the standard references stay: `Cooler.latent_heat`,
`IceStorage.latent_heat`, `freezing_temperature`, `water_specific_heat`, `ice_specific_heat`
(constants of nature with a source, 7.30); a plant file may override them as an equipment property
(test 2). `Atmosphere.pressure` goes to the case (7.20). `InjectionPump.frequency = 60 Hz` is an
operating frequency, a control the designer decides: the default is removed and the plant states
`frequency` (the same float). `_Reservoir.role` is the identity of the subclass, not a value, and
stays. The accumulator zeros go (7.19). After this, the registry lists only sourced constants and
one identity.

**7.23 Fallbacks hidden in physics functions and constants** (rule: P5, P7, tests 2 and 4). A
default in a physics signature or a module constant that stands in for a value a user decides is
removed, so the function takes the value and a missing one raises `missing_value`: `minimum_lift =
0.0` (owner: `HeatPump.minimum_temperature_lift`), `inclination_sine = 1.0` (the well section
inclination), the friction correlation names and the corrosion model (plant choices), the pipe
material, hardness and density, the brine chemistry of `co2_corrosion_rate` (viscosity, bicarbonate,
ionic strength: `site.fluid` when a module needs them), the pipe diameter and roughness (plant), the
sand particle (7.17), `FILTER_CLOGGING_BAR`, `DEFAULT_CARNOT_FRACTION`, `FLARE_EFFICIENCY` and
`DEFAULT_CP` (fallbacks for plant parameters the samples already state), `DEFAULT_LIQUID_DENSITY` (a
missing density raises), and `physics.gas.GRID_COMPOSITION` (a gas grid composition hidden in code:
`utilities.gas.composition`, required). Where a published figure documents a source it stays in the
docstring. Each is dead code for the samples because the modules pass the value; the worker must
check reachability per row and delete or keep accordingly. No number changes.

**7.24 The run input (`plan`)** (rule: P5, test 5). `plan` is a table of per-step controls and
boundaries (what `gm.schedule` writes, or measurements). When it is not the scheduled one it is an
input that changes a result, so a run from files names it: `study.plan`, a `data/*.csv` whose first
column is `time`. `gm.simulate(plant, case, plan=None)` keeps the argument as the in-memory form of
that file.

**7.25 Time defaults** (rule: P5, P6, P7). `DEFAULT_STEP` (1 h), `tz = 'UTC'` of the `Dataset`
readers, and the `step`/`tz` defaults of `Clock.year` and `Clock.days` hide the case's time. They
are removed: `case.time` is the only owner of the period and the step, the `clock` of `gm.simulate`
is built from it (the argument is removed), and every timestamp carries an offset or `Z`, a naive
one is an error. `Clock` stays for `Engine` and for data without a case.

**7.26 Precision** (rule: P4). `runtime.precision` (`float64` or `float32`) can change a number (it
selects the legacy float32 ESP arithmetic kept for golden parity), so by P4 it is an input. It stays
a setting of the run call, recorded in the run record, and `float64` is the one reference
arithmetic. Open: whether `float32` should exist outside the golden tests at all.

**7.27 The default fluid and `fluids`** (rule: P5, tests 2 and 4). `runtime.default_fluid` (the
brine of `gemini.streams.fluid.BRINE`) was copied into every new module and stream, a hidden value that
changed results. It is removed as a setting. The brine of the reservoir is `site.fluid` (it already
is, through `apply_case`); the working fluid of a closed circuit (water, glycol 30 %) is the
designer's choice and is the plant's `fluids` entry (`{path: {...}}`, test 2), which stays. The
modules of the samples that relied on the default state it in their `fluids` entry with the values of
the default, so numbers do not change. Built: a module has no fluid until the case or `fluids` sets
it, and reading `module.fluid` then, or building a `Stream` without `fluid`, raises `missing_value`
naming the path. The plant `boundary` section stays: the measured twin reads its `stream_defaults`
(`gemini/engine/bindings.py`), so it is no empty section in every file.

**7.28 The definition of a method** (rule: P5, test 5). The population size per variable (5), the
smallest population (5), the rejection attempts of `sample` (10000), the penalty for an infeasible
trial (1e6), and `tol = 0`, `polish = False` of the differential evolution are the definition of the
methods `minimize` and `sample`, versioned with gemini. Changing one is another method, not a
setting. The `evaluations` budget and the `seed` are inputs (`study.json`); the hidden `SEED = 0` of
`minimize` becomes a required `seed`.

**7.29 Hidden design values in a plant class** (rule: P5, test 2). `ParallelExchangerPlant.SHARES =
(0.5, 0.3, 0.2)` are the split fractions of the designer, written in a class. They become parameters
(`split_fraction`) of the splitters in the plant file, with the same values.

**7.30 Constants of nature and of the model** (rule: P4, P5). Physical constants, standard
properties (IAPWS tables, gas species, molar masses), published correlation coefficients, unit
factors and the closed vocabularies of gemini are no setting of any party: they define the model,
and the gemini version determines them (P5 reads "project files plus the gemini version"). They stay
in code, each with its source in its docstring. A value that a party can legitimately choose is
never in this class.

**7.31 A search range given as a share of the peak** (rule: test 2, P1). `examples/hackathon.py`
searches each capacity from 10 % to 100 % of the peak demand. A `range` is absolute (P6), so the
sample plant files state the numbers computed from the case's peak. If the peak changes, the ranges
are rewritten by the author. Open: a derived range (a share of the case's peak) would need a second
representation, which P6 forbids; no rule decides it yet.

**7.32 Which leaves `size` computes** (rule: test 2). `examples/plant.py` keeps a list of name
endings (`capacity`, `nominal_flow`, `nominal_head`) that it drops before `size`. Which leaves are
derived from the demand is a statement about the design, so a leaf may carry `"sized": true` and
`prepare: ["size"]` computes exactly those. Open: the exact marker is not in Appendix A and must be
confirmed.

**7.33 Plant-level `depth`** (rule: test 2). `params.depth` of a class plant is the depth the
designer drills to; it goes to every doublet, which derives its reservoir from it with the case's
geotherm (`Doublet.depth`). It stays a plant leaf in the `params` tree at the top, with the `range`
of the old `choices.depth`. A value stated on one doublet wins, as today.

**7.34 `case.uncertainty`** (rule: P1, P6). `Case.uncertainty` is the in-memory index of the
`uncertainty` objects written next to the leaves (by dotted path). It is not a field of any file and
has no second place in a file; it is derived (P1) and `gm.study.sample` / `sensitivity` read it. The
same index serves the economics file, with paths below `economics`.

**7.35 Laws with depth in `site.reservoir`** (rule: test 4, P8). `reference_depth` and `pressure`
stay; the pressure at another depth is hydrostatic with `site.fluid.density`, and the temperature is
linear with `site.ground.gradient` (`gemini/physics/ground.py`). These laws are physics, not choices
of a party, so they are no keys. When a second law exists the choice becomes a required leaf
(`pressure_law`, a closed list). A temperature measured at the reference depth is
`site.reservoir.temperature`, optional as today.

**7.36 `Plant.constrain` and its bounds** (rule: test 2, 7.5). A plant constraint (`target`,
`equals` or `at_least`, `by`, `bounds`) is structure of the plant (which control is solved to reach
which target): it is written in the class or in `constraints` of a structure plant (test 2). The
bounds that are paths to plant parameters (`production_rates`, `maximum_injection_pressure`) are
plant parameters; a bracket that is only the root finder's interval is a numerical setting (7.5).
Only `NodalDoublet`, a building block, uses it.

**7.37 What `gm.schedule` reads** (rule: P1, test 2, test 3). `gm.schedule` reads the `doublet`
rules (flow range, brine cooling, running time) from `requirements`: planning to respect a rule is
not the rule setting a value, and the numbers stay in the case (P1). The load order of sources is
`control.dispatch = least_cost` (Appendix A), and the choice of outage steps (the steps of lowest
total demand first, a duration rounded to the nearest whole step, ties earliest) is a second hidden
rule: it is written as `control.outages = lowest_demand`, a closed list of one string, so it is
visible and replaceable (P5). The values that the plan computes are results, not inputs.

**7.38 `time_column` and the CSV readers** (rule: P6). `demand.time_column` ("date", "timestamp")
and `gm.case.from_csv(time_column=)` disappear: the first column is always `time`. The sample CSVs
are rewritten once with that header and ISO 8601 timestamps with offset, so the index values do not
change (the readers parse them to UTC as today).

**7.39 Arguments that are not inputs** (rule: P4). `on_error`, `callbacks`, `units`, `table`,
`checkpoint`, `checkpoint_every`, `backend`, `compile`, `processes` and display units cannot change
a result (a test keeps `backend`, `compile` and `processes` true). They are runtime or interface, in
no file. `discount_rate` and `lifetime` arguments of the `gm.evaluate` costs are removed (P1: the
economics file owns them).

**7.40 The reader of the shared formats** (rule: P6, section 10). `gemini/units/inputs.py` is the one
reader and writer of the leaf forms of section 3, below `plants` and `case` and above `units`. A
leaf is always an object: a bare number or text for a quantity is a `unit` issue, a bare number for
a dimensionless value or a choice a `missing` issue. A `Leaf` keeps the value and unit as given and
derives SI, so `to_json` returns exactly what was read (a series in kW keeps kW values in its CSV).
An older file without `kind` is an issue of code `old_format`, a wrong `kind` of `invalid_format`.

**7.41 The key of a demand series** (rule: P6, section 3). Appendix A lists the series among the
fields of `demand.heating` and `demand.cooling` without a key. The key is `power`: it says what the
series is, it has the dimension `power`, and `case.demand.heating.power` is the array in W on
`time.index`. The old `file`, `time_column`, `column` and `unit` of the demand are refused with code
`old_format` and the new form.

**7.42 The form of a requirement** (rule: P6, section 4). `over` is stated for a per-step quantity
and is absent for a window quantity or a property of the plant (`pump_efficiency`, `count`,
`unmet_share`): a missing `over` on the first and a given one on the second are issues. `when` is
optional and absent means every step; a quantity read over the whole period takes none. The role
table (`gm.plants.roles()`) says for each quantity its dimension and whether it takes `over`.
`reinjection_ratio` of `doublet` is the plant output `Doublet.reinjection_ratio` (injected over
produced liquid volume flow, none without production); `volume_imbalance` stays a `Doublet` output
for gemini's own balance check and leaves the role table. `count` (the number of doublets) and
`unmet_share` (unmet energy over the demanded energy of the service) are in the table; their
evaluation belongs to `gm.evaluate`.

**7.43 Initial state without a dimension** (rule: 7.19). `case.initial_state` is read before the
plant is known, so its leaves are `{"value", "unit"}` whose unit must exist in the unit table; the
dimension is the declaration of the state, which `gm.check` compares. `Leaf.si` converts as a plain
unit, the right reading for the absolute quantities a state holds.

**7.44 Text and map leaves** (rule: P6). A label is a leaf with a text value (`currency`,
`gwp.standard`: `{"value": "EUR"}`), a composition (`site.fluid.dissolved_gas`,
`utilities.gas.composition`) a map of dimensionless leaves per species that adds up to 1, and
`opex.fixed` a map of leaves per equipment kind; each is stored as a dict in SI. Bounds that were
strict (`> 0`) are inclusive (`>= 0`) because the shared reader checks `min` and `max`. A price
series in a stand-alone `Economics` needs `time=`; the case passes its own.

**7.45 The callers on the new case** (rule: P1, P6). The package reads `case.site`,
`case.utilities`, `case.economics` and `case.requirements`; nothing reads an old name. Four
placements the code needed: (a) the name of a check of `gm.evaluate.requirements` is the name of its
requirement, one row per unit of the role (`unit_path` tells them apart), and the supply temperatures
of the services are the requirements `heating_supply_temperature` and `cooling_supply_temperature`;
(b) `count` is one check of the plant (`unit_path` `""`, the number of units of the role found in the
plant, with no slack) and `unmet_share` one figure per supply unit, the unmet energy over the energy
the demand of the case holds for the service (`case.demand.frame`), 0 when nothing was demanded; (c) a subsidy
(`economics.revenue.subsidy`, amount per year for a duration) adds to `npv` the amount discounted
over the shorter of its duration and the analysis period, and to `payback` the amount per year for its
duration only, so the payback is the time at which the cash flows add up to the capex; without a
subsidy, or with only one of its two figures, nothing changes; (d) a value of the case that a study
varies or draws around is the mean of the steps when the case holds a series, and the ends of a
one-at-a-time sensitivity are `min` and `max` of the uncertainty, else the value minus and plus
`std`. `Well.capex` is the length times `economics.drilling_cost_per_metre(length)`, the constant or
the depth table. The module glossary has the word `reinjection`, for `Doublet.reinjection_ratio`.

**7.46 The plant file as built** (rule: P6, 7.11, 7.12, 7.15, 7.16). `gemini/plants/_utils/form.py`
converts the file to the flat plant dict the reader builds a plant from, and back, so there is one
reader and one writer of the flat dict (the private form a checkpoint also uses for a tree that is
no plant); `leaves.py` reads every leaf against the declaration it sets, with the readers of
`gemini/units/inputs.py`, collecting all issues. (a) `type` with `modules`/`connections` is read as
the class and the structure is compared with the class's (`modules` issue when they differ);
`to_json(structure=True)` writes both. (b) `size` is one leaf per structural argument, an integer
at least 1, or a choice of the class (`DistrictNetwork.service`, `size_choices`); `plant.size` is the
plain mapping. The constructor defaults of 7.12 are not removed yet. (c) `params.control.dispatch`
and `params.control.outages` are the plant parameters `dispatch` and `outages` of any plant at any
depth; `backup` and `depth` sit at the top. (d) A leaf may carry no value (a template): its issue
`missing` at `...value` is not raised by `from_dict`, which raises every other issue, and
`check()` lists the parameters without a value as `missing`, with a path `params.<path>`. A leaf
with `history` and no value is a dated parameter whose current value is the history's. (e) A leaf
that names a control or a boundary of a module, or a field of a plant inlet (`return_in.T`), sets
a plant input; the `inputs` key is refused. (f) `bindings` is refused in a file (7.15); they stay in
memory, a checkpoint stores them in its own `bindings` key, and the bindings of the measured
examples are `tests/fixtures/doublet_heat/bindings.json`, read by the test fixture. (g) `fluids` and
`boundary` stay keys by module path (7.27 is built: no default fluid). (h) A string parameter without a `Literal`
is a free label (`pump_type`, a pump catalogue name): it has no closed list and no options; every
other string parameter of the modules and plants declares its list as a `Literal`. (i) The search
rule below.

**The variable of a search** (for `gm.study.minimize`, worker F). `plant.ranges` and
`plant.options` give the leaves in file order. A variable is the set of leaves with the same
parameter name (the last part of the path), the same role of the module that owns it (the roles of
`gm.plants.roles()`; the plant itself is the role `plant`) and an equal range in SI; options are
grouped the same way, with equal options. Three chillers of one plant with the same `capacity` range
are one variable; `depth` and `nominal_flow` of `d0` and `d1` are one variable each; the `depth` of
the plant is tied to the doublets by the class. The order of the variables is the first appearance
of a member in the file order of `plant.ranges` and `plant.options`, `size.doublets` first. A leaf
with a range and one without the same name and role are not tied: only the leaves that state a
range are variables.

**7.47 The moves between plant and case as built** (rule: the placement test, 7.9, 7.14, 7.17 to
7.23, 7.29, 7.37). (a) ESP operating limits: `esp.minimum_intake_pressure` and
`esp.maximum_gas_fraction` are plant parameters (default empty), stated on every `esp` of every sample
plant (5 bar and 0.1875, the values of the former requirements); `resize` repeats the values of `d0`
on an added doublet, as it does every value. A limit never fails or alters a step: a breach is a
`bound` reason of `gm.evaluate.verdict`, and `gm.study.minimize` judges a trial by the same breach
(`study/_utils/trial.judged` adds `evaluate/_utils/operating.breaches` to the requirement checks,
with the relative excess as the violation), so a search still rejects the designs the requirements
rejected. The role quantities `intake_pressure` and `intake_gas_fraction` stay in the role table. (b)
`GasGrid.composition`, `Atmosphere.pressure`, the `ElectricityGrid` limits, the consumer conditions
of `HeatingGrid` and `CoolingGrid` and the indoor state are declared with `case=<path>` (a
`Boundary` takes `case=` too); `apply_case` sets what the case gives, and requires the gas
composition and the air pressure where their module is present (`missing_value` naming the path). A
plant leaf on any of them is refused with `invalid_value`. `utilities.gas.composition` takes the
species of `gemini.physics.gas` (`GRID_GAS_SPECIES`), the natural-gas hydrocarbons that
`site.fluid.dissolved_gas` does not list. `heating_value` is not an input of any module (the
heating value is computed from the composition), so no sample states it. `physics.gas.GRID_COMPOSITION`
is removed: nothing in `gemini/` used it; tests that need a grid gas read
`tests/fixtures/gas.GRID_COMPOSITION`. (c) `supply_margin` is a parameter of `HeatPump`, the boilers,
`AbsorptionUnit` and `AdsorptionChiller`; `apply_case` finds the units on a supply line with
`plant.feeds` (`roles.supply_service`) and sets `temperature_setpoint` = supply temperature plus the
margin (minus for cold), the same float as the stated setpoint (373.15 + 0.0). A margin on a unit
on no supply line, or a unit on both grids, is `invalid_design`; a unit without a margin keeps the
setpoint the plant states (a control, as the coolers' 15, 25 and 18 degC). (d) `InjectionPump.frequency`
has no default and the plants state 60 Hz; `Atmosphere.pressure` has none and the cases state 101325
Pa (both rows left `DECLARED_DEFAULTS`). (e) `gm.schedule` raises `missing_value` naming
`params.control.dispatch` or `params.control.outages` when the plant does not state them; the
`Literal` of each parameter holds the one implemented value and refuses another. (f)
`ParallelExchangerPlant.SHARES` is replaced by `EXCHANGERS = 3`; the split fractions 0.5 and 0.6 (a
50/30/20 split) are the `split_fraction` controls of both splitter cascades in the plant file. (g)
`technical_life` is not built: gemini models no replacement (`npv` has "no degradation, tax,
replacement"), so a value would be read by nothing; it stays in section 8. (h) The plant files of
`tests/fixtures/plants/` have no case: the values that moved out of them are in
`tests/fixtures/plant_case_values.json` and the test fixture `example_plant` sets them on the modules.
`.tmp/inputs/convert_moves.py` made the moves and checked against the files before that nothing else
changed.

**7.48 The study and `gm.check` as built** (rule: P5, section 10, 7.28, test 5). (a) `gm.check(plant,
case)` (`gemini/engine/check.py`, exported at `gm.check`, imported by `simulate` and every study
function; the run folder imports nothing from `study` or `evaluate`) applies the case to a copy of
the plant and returns the issues of: a parameter without a value (`missing`, path `params.<path>`),
a capex and a fixed opex for every equipment kind the plant contains (`missing`, code
`missing_assumption`, `economics.capex.<kind>`, `economics.opex.fixed.<kind>`), a requirement on a
role the plant lacks (`incompatible`, `requirements[n].on`), an initial state for every state of
every stateful module (`missing`; a module, a state or a unit that does not fit is `unknown_key` or
`unit`), and the energy prices when the plant states `control.dispatch = least_cost` (the
electricity price, and the gas price when the plant has a `boiler` or `chp` role). (b) A case with
no `economics` is a pure physics case and has no price issue; `simulate(plant, case=None,
plan=...)` runs no check. `size` runs `gm.check` and tolerates the `missing` issues of plant
parameters (`params.*`), since it completes a template plant; `simulate`, `minimize` (the plant is
sized first), `sample` and `sensitivity` do not tolerate them. (c) An absent `heating_supply` or
`cooling_supply` role is no check issue: a heating-only plant runs on a case with cooling demand
and is judged infeasible, P2 (one case judges any plant), for the reason `cold_delivered` that
`gm.evaluate.verdict` already gives. Any other absent role is `incompatible`. The verdict
dedupes its reasons by name, so a requirement on an absent supply role and the service reason are
one. (d) `case.initial_state` is wired: `apply_case` checks the names and `gm.simulate` starts the run
from it (`apply.started`), so the code defaults of the states of the modules not yet converted and
the `initial_*` parameters are gone (7.19): the case is the only source of a state; a case that
states a state wins. No sample has a stateful
module. (e) `case.choices` is gone (the class, the field, `gemini/case/choices.py`, the sample
case files, `study/_utils/choices.py`); the key is refused with `old_format` naming the plant
`range`. `minimize` has no `variables` argument; `size` reads `params.backup` (a plant without it is
`missing_value` naming `params.backup`) and the range of `size.doublets` (without it,
`missing_value` naming `size.doublets.range`). (f) `minimize(plant, case, objective, evaluations,
seed, *, plan=None)`: the variables are the ranges and options of the plant by
the rule above (strings and integers are searched as integers, `differential_evolution(integrality=)`
only when there is one); `evaluations` and `seed` have no default (the old `100` and `SEED = 0` are
gone); the result is `{best, feasible, history, evaluations}` and has no `fixed` (a leaf without a
range is not a variable). `sample(plant, case, metrics, samples, seed)` renamed `count` (7.10). The
best design is a `Plant`; its `to_json` runs. (g) **One verdict** (decision of this step). `compare`
requires a `verdict` in each report (`missing_value` otherwise); the study uses the verdict and
nothing else decides feasibility. Today's search counted requirement checks, operating-limit
breaches and failed steps, and did not count the service reasons (`cold_delivered` of a plant with
no cooling grid), which `compare` added after; if every such reason made every trial infeasible, the
search of `HeatingPlant` would change. The form chosen: a reason of the verdict carries a
`violation` (the relative excess of a failed check, of a breach, of a balance; 1e6 for a failed
step or a loop that did not converge) when a design variable can change it, and none when it is
structural (a service the plant has no unit for, no requirement checkable). A trial is infeasible
by the reasons with a `violation` (`gm.evaluate.verdict.ranked`), ranked by their sum (at most 1e6);
the reasons without one stay in the verdict of the run of the best plant, so `report`, `compare` and
`Study` give `cold_delivered` for `HeatingPlant` as before. Measured: the violations of 8
random trials of a plant with a chiller of 0.1 to 10 MW agree with the old count to the last
digit, and `.tmp/inputs/guard_search.py` (below) agrees on the search. A reason of kind `numerical`
or a declared `bound` now also ranks a trial (it did not): none occurs on the samples. (h)
`gm.Study` (`gemini/study/study.py`): header `kind: study`; keys `cases`, `plants` (paths relative
to the file, or `files` in memory), `prepare` (`["size"]`), `method` (`run`, `minimize`, `sample`,
`sensitivity`, a closed list), `objective`, `metrics`, `evaluations`, `samples`, `seed`; a key the
method needs and the file lacks is `missing`, one the method does not read (`evaluations` and
`samples` of other methods, `seed` of `run` and `sensitivity`) is `incompatible`, an unknown key
`unknown_key`; `from_dict` raises all issues at once and `check()` returns them with the files that
do not read and the `gm.check` of each pair. `run(plants=None)` calls `size`, `minimize`, `sample`
or `sensitivity` as a caller does, simulates and reports the design (the best plant of a search),
and returns a `StudyResult`: `runs`, `comparison` (per case, by the objective then the metrics, a
leading `-` meaning a maximum) and `best` (per case, the feasible run ranked first by the
objective). A `minimize` on a plant with no range and no options runs the plant as it is, with a
`note`. `to_json(folder)` writes `study.json`, `version.json`, `result.json`, per case the case,
its economics and series, and per plant `source.json` (as given), `plant.json` (the full form that
ran), `report.json`, `verdict.json`, `series.csv` and `found.json`. `plan` (7.24) and
`measurements` are not built. (i) Data fix: `HackathonPlant.json` had no `range` on `d0.depth` and
`d1.depth`, so a search of it lost the variable the old search had (`depth`, 2000 to 3500 m, on
each doublet); both leaves carry it, which gives 80 trials as before. The variable order is the
first appearance of a leaf in the `params` tree (the tree mirrors the module tree, P6): for the
structure plant `HackathonPlant` it is heat pump, chiller, depth, flow, where the old search had
depth first. A dotted key in `params` (`d0.depth` at the head, to force depth first) is refused by
the reader with the nested form named (`not_allowed`, `params.d0.depth`), so the order cannot be
forced from outside the tree. The trial histories differ between orders (checked: the sequence of
LCTS values of the 80 trials), the best design does not: `guard_search` compares only the best
design, and in `HackathonPlant` that is the start design (trial 1, depth 2500 m), so it passes for
any order and is the evidence only for that. (j) Search equivalence: `.tmp/inputs/guard_search.py <plant>`
runs `size` and `minimize(objective="lcts", evaluations=20, seed=0)` under `processes=4` on a
sample plant and compares `lcts`, `co2` and `capex` of the best design with the report of the old
code within 1e-6: `HackathonPlant` (80 trials), `HeatingPlant` (120) and
`HeatingHeatPumpCoolingPlant` (240) pass. (k) `unmet_share` of a supply is the unmet energy of
the run over the demand of the case for the service (`case.demand.frame`), read from the results and
the case; a service that demands nothing has share 0. Before this it gave no value on a simulated
run, because the demand column is not among the results.

**7.49 The public face as built** (rule: P1, P4, P6, section 11). (a) `gm.study.minimize(plant, case,
objective, evaluations, seed, *, plan=None)` has no `constraints`: a rule on a result is a
requirement of the case (P1, test 3) and nothing in `gm.Study`, the examples or the samples passed the
argument. A cap on a metric that is no role quantity (for example `lcts`) has no home yet; if a brief
imposes one, the role table gains the quantity, not the search an argument. (b) `Case.from_dict(data,
files=None, folder=None)` and `Study.from_dict(data, files=None, folder=None)` keep `folder`: a
caller that edits a dict read from a `case.json` (the limits of `examples/costs.py`) has its files on
disk, and a case in memory needs only `files` (`{name: bytes}`, no folder). The sections and
`gm.case.Economics.from_dict(data, files=None, time=None)` have no `folder`; `from_json` reads the
folder of its file through a private path. (c) `gm.plants.capabilities()` reports `ranges`, the
leaves of the plant file that may state a `range` (`size.doublets`, `params.depth`), in place of
`choices`. (d) `gm.case.from_csv(path, columns, unit)` requires the first column `time` (7.38);
`gm.Dataset.from_frame(frame, time_column=)` stays, because a pandas frame has any column names and
is no file of the project. (e) The cost functions of `gm.evaluate` take no `discount_rate` or
`lifetime` (7.39); the part of their results is `analysis_period`, not `lifetime_years`.
(f) `missing_assumption` stays the code of a value that is absent below `economics`: it names a
money assumption of the investor, errors.md documents it, and it is in the frozen code list. (g)
`gm.replay`, `gm.live` and `Engine` keep `(plant, data, ...)`: they run a plant on measurements with
no case, the open item of section 8. (h) `gm.Study.schema()` is the schema of `study.json`, with
`gm.Case.schema()`, `gm.case.Economics.schema()` and `gm.plants.schema()` it gives
`docs/schemas/{study,case,economics,plant}.schema.json`. (i) A checkpoint of a version before 0.3.0
is refused with `old_format`, because it holds a plant file of `format: 2`. (j) `tests/unit/test_api_contract.py`
compares the table "Names and signatures" of api.md with the code; `tests/unit/test_docs.py` runs the
`python` snippets of the docs; the names `assumptions`, `finance` and `lifetime` join the old names
that `test_no_name_keeps_something_old` refuses in a name of `gemini/`.

**Decisions not built yet.** The rule of each decision below stands, and it is listed in section 8
until the code follows it. Today's behaviour stays and no number depends on it in a sample. 7.19 is
built in full (`case.initial_state`, its check in `gm.check`, no `State` default, no `initial_*`
parameter). 7.23 is built for `GRID_COMPOSITION` only. 7.12:
the constructor defaults of the class plants (`doublets=1`, `consumers=2`, `service='heating'`,
`producers=2`, `injectors=1`) stay, because hundreds of calls use them; `size` is a leaf of the file.
7.1: `technical_life` is not built (see 7.47 g). 7.24 (`study.plan`), 7.25 (time defaults, the `clock`
argument) and 7.32 (a `sized` marker) are not built: `simulate`
keeps `plan` and `clock`, and `size` computes what it computes today.

### 7.5 The numerical settings that stay in code

| setting | value | where |
| --- | --- | --- |
| `Plant.loop_tolerance` | 1e-9 (K, SI) | `gemini/plants/_utils/loops.py` `TOLERANCE`; the change of a tear stream per pass |
| `Plant.loop_passes` | 50 | `loops.MAX_PASSES`; a loop that does not converge raises `loop_not_converged` |
| `ops.brentq` `xtol`, `maxiter` | 2e-12, 100 | `gemini/ops/solvers.py`; `BRENT_RTOL` 8.88e-16 |
| `ops.newton` `tolerance`, `max_iterations` | 1e-6, 100 | `gemini/ops/solvers.py` |
| call-site `xtol` of `brentq` | 1e-9 (psychrometrics), 1e-14 (ground) | `physics/psychrometrics.py:114`, `physics/ground.py:236` |
| requirement slack | 1e-9, relative | `evaluate/verdict.py` `TOLERANCE`: a value on a limit passes (this is also how `equals`, now min = max, passes) |
| mass, energy and plant balance residuals | 1e-12, 1e-9, 1e-9 (module), 1e-6 (plant) | `evaluate/balances.py`: when a `numerical` reason is raised (section 6) |
| gas composition sum | 1e-9 | `physics/gas.py` `COMPOSITION_TOLERANCE` |
| saturation and corrosion Newton | 1e-9; 1e-6, 100 | `physics/steam.py` `SATURATION_TOLERANCE`; `physics/corrosion.py` |
| floors and guards | `DRIFT_FLOOR` 1e-12, `MIN_PATH_PRESSURE` 1e-3 Pa, `ESP_MIN_EFFICIENCY_POWER` 0.1 W, `DUTY_AGREEMENT_TOLERANCE` 0.05, ground angle guards | `physics/diagnostics.py`, `physics/constants.py`, `physics/pumps.py`, `physics/heat_transfer.py`, `physics/ground.py` |

`Plant.loop_tolerance` and `Plant.loop_passes` are class attributes today; they stay settings in
code and are no key of the plant file. Every row of this table is documented with its source in its
docstring.

**7.50 A failed step is a result** (rule: 7.39, P4). What a plant cannot do is the answer to the
question of a run, so it is not an input and not an error of the run. In `gm.simulate` a step that
fails with one of the codes `invalid_inlet`, `out_of_bounds`, `out_of_range` or `no_convergence`
(`PHYSICAL_ROW_CODES` of `gemini/errors/rows.py`) is a **failed row** whatever `on_error` says: its
values are NaN (never zero), the state of a stateful plant stays as it was before the step, the run
goes on, and `results.errors()` lists the row with its code. `on_error` only decides the rest: under
`"raise"` (the default) any other failure of a step is a bug of the plant, the module or the call
and stops the run after committing the ticks before it; under `"record"` it is a failed row too.
A replay or a live run of measured data stays strict. The one answer to feasibility, `gm.evaluate.verdict`,
lists the failed and skipped rows as one reason of kind `failed_step` (name `failed_steps`, with a
`violation` of 1e6, so a search ranks a plant that fails below any plant that runs) and a loop that
did not converge as kind `numerical`. `minimize`, `sample`, `sensitivity` and `compare` read the
verdict, so an infeasible design is an infeasible trial with a reason, never a crash; a NaN value of
a metric counts as the largest violation. Where it lives: [engine.md](engine.md#errors).

**7.51 A `range` on a case or economics leaf is deprecated** (rule: test 2, P6). The reader accepts
`range` on every leaf (`LEAF_KEYS` and `SERIES_KEYS` of `gemini/units/inputs.py`) and the case keeps
it, but nothing reads it: a case with a `range` on a value, an economics value or a series gives the
same numbers as without (`tests/integration/test_range_deprecated.py`). A search range is the
designer's statement and belongs on the plant leaf (7.8); a case value that may be other is moved by
`uncertainty`. So `case.check()`, `economics.check()` and `gm.check` report each such `range` as an
`Issue` of kind `deprecated` (code `deprecated`, path ending in `.range`), and reading the case
(`Case.from_dict`, `from_json`, `Economics.from_json`) emits one `gm.errors.GeminiWarning` naming the
path. It is a warning and stops nothing: `raise_issues` leaves a `deprecated` issue out, so reading,
`gm.simulate`, `size` and the studies run as before, and `Issue.is_warning` lets a caller that judges
readiness skip it (it comes last in the list). The message says: a search range belongs on the plant
leaf, to move a case value use `uncertainty`, this will be refused in a later version. A requirement
`min`/`max`, an `uncertainty` and a plant `range` are not affected. Where it lives:
`gemini/case/_utils/unused.py`.

## 8. Still open

- Profile uncertainty (for example demand times a factor), multi-year runs (reservoir decline, price
  escalation), several reservoir layers: the formats above leave room (a series leaf, an
  `uncertainty` on a series, a list under `reservoir`) without changing what exists.
- Operation-loop methods (`replay`, `calibrate`, `live`): they fit the study shape with
  `measurements`; the bindings of 7.15 are designed only in outline.
- Decisions whose rule stands and whose code does not follow yet: 7.12 (constructor defaults of the
  class plants), 7.23 (fallbacks in physics
  signatures other than the grid gas), 7.24 (`study.plan`), 7.25 (time defaults), 7.32 (`sized`).
- `technical_life` per equipment kind (7.1): gemini models no replacement, so no module would read it.
- The tolerance of the brief for full reinjection (7.13): the samples carry the band they had, as a
  ratio. The brief says only "equal liquid volumes" and gives no number, so a
  tolerance needs a statement from the organisers.
- A derived search range, a share of the case's peak demand (7.31), and the exact marker for the
  leaves `size` computes (7.32).
- `site.fluid` leaves that a corrosion or an erosion module needs (bicarbonate, ionic strength,
  particle material, diameter and shape factor, 7.17 and 7.23).
- Whether `precision: float32` should exist outside the golden tests (7.26).
- Decided: the name `Case` (`gm.Case`, `case.json`).

## 9. Definitions

| term | definition |
| --- | --- |
| plant boundary | the control volume around everything the designer selects; what crosses it is described by the case |
| module | a unit of equipment or a grid with declared parameters, inlets, outlets, outputs, an optional `kind` and an optional `role` |
| plant | a module made of modules and connections; a gemini class (`type`) or a structure written out (`modules`, `connections`) |
| parameter | a value of a module that the designer sets before a run and that does not change during it; a control constant is one |
| leaf | one parameter or case value in a file: an object with `value` and, if dimensioned, `unit`; optionally `range`, `options`, `uncertainty`, or a series in place of `value` |
| quantity | a dimensioned value; in Python `gm.units.Quantity`, in JSON `{"value", "unit"}`; SI inside gemini |
| range | `{"min", "max"}`, either side optional, numbers in the leaf's unit; the one form for search ranges, distribution bounds, requirement bands and declared bounds |
| bounds | the physically valid range a module declares for a parameter; a search range must lie inside it |
| options | the allowed choices of a choice parameter in this plant; a subset of the closed list the module declares |
| uncertainty | a distribution on a case or economics value: `uniform`, `triangular` (mode = value), `normal` (`std`, optional bounds); `value` is the nominal |
| series | a time-varying value read from a CSV whose first column is `time` |
| kind | the equipment catalogue entry a module is priced as (`equipment_kind`: `heat_pump`, `production_pump`, `drilling`...); keys of `economics.capex` and `opex.fixed` |
| role | the function a module plays in a plant (`doublet`, `heat_pump`, `chiller`, `heating_supply`, `plant`...), found from the class and the wiring; what requirements refer to. Kind says what it is (for cost), role says what it does (for rules) |
| role quantity | a result or property a role exposes to requirements, with a dimension (`production_flow`, `brine_cooling`, `reinjection_ratio`, `unmet`, ...). A per-step quantity takes `over`; a window quantity (a total or share over the period) does not |
| over | how per-step values are reduced: `each` (every step), `sum`, `mean`, `max`, `min`, `duration` (time the condition holds) |
| when | which steps count: `always` or `running` |
| case | the outside conditions over one period and the third-party rules (`gm.Case`) |
| economics | all money conditions and reporting conventions; a case section, usually its own file |
| requirement | a third-party rule on a result or a plant property; it judges, it never sets a value |
| margin | the amount a plant adds to (or, for cold, takes from) a supply temperature of the demand to get a setpoint (7.14) |
| study | which plants on which cases, with which method, objective, budget and seed (`gm.Study`); optional |
| method | `run`, `minimize`, `sample`, `sensitivity`, `evolve` (later `replay`, `calibrate`) |
| objective | the one metric `minimize` lowers; `evolve` takes `objectives`, one or several |
| metric | a reported number (`lcts`, `co2`, `capex`...) |
| verdict | the single feasibility answer of one run: `feasible` plus reasons, each of kind `requirement`, `failed_step`, `numerical` or `bound` |
| issue | one problem found by a check: `path`, `kind` (`missing`, `unknown_key`, `unit`, `out_of_bounds`, `not_allowed`, `incompatible`, `coverage`), `message`, and for values the quantity and accepted units |
| check | a function that returns the list of issues and never raises |
| runtime setting | a setting that cannot change a result (processes, eager or compiled); never in a file |
| run record | what `results/` holds for one run: full plant form, copies of the inputs, gemini version, report, verdict, series |

## 10. Checks and errors

- `case.check()`, `economics.check()`, `plant.check()`: what each object can know alone (units,
  coverage of series over `time`, ranges inside bounds, options allowed, every required parameter
  set, connections valid; today `gm.plants.validate` and `gm.modules.check` do part of this).
- `gm.check(plant, case)`: what needs both (a capex and fixed-opex entry for every kind the plant
  contains, the design value that sizes a capex on another basis, every role a requirement names exists in the plant, an initial state for every stateful
  module, energy prices present when the plant's dispatch is `least_cost`, a `site`, `demand` and
  `utilities` value for every module that needs one).
- One name, `check`, everywhere. It returns a list of issues and never raises; an empty list means
  ready. `from_json` / `from_dict` run the object's own check and raise `ValidationError` carrying
  the same issues; `simulate` and every study function run `gm.check` first and raise the same way.
  `gm.check` reports a case that is wrong by itself (`case.check()`) with its own issues and does
  not apply it; a module with a parameter still unset is reported once (`params.<path>`) and its
  equipment kind is not looked up, since a kind may depend on that parameter.
  The codes are those of [errors.md](errors.md): `missing_value`, `missing_assumption`,
  `invalid_unit`, `invalid_value`, `unknown_name`, `out_of_bounds`, `old_format`.

## 11. Naming

- Readers `from_<format>` (class methods on the class they return), writers `to_<format>`:
  `gm.Case.from_json`, `gm.Plant.from_json`, `gm.Study.from_json`, `gm.Economics.from_json`
  ([conventions](conventions.md#public-names-and-readwrite-naming)).
- One verb per action: `check`, `simulate`, `size`, `minimize`, `sample`, `sensitivity`, `report`,
  `verdict`, `compare`.
- Python signatures are `(plant, case, ...)`; the remaining arguments are only method settings
  (objective, budget, seed, metrics). Everything else comes from the files.
- Keys are snake_case; the name of a key in a file is the name of the declaration in code
  (`temperature_setpoint`, `supply_margin`), so a reader finds one from the other.

**Forms.** `Case.schema()` states `kind` as a constant and marks each leaf with `x-quantity`, `x-units`, `x-limits` (SI) and `x-fraction`, and each file with `x-quantities`, from the one unit table; every field and section of the economics has a `description` (`Field.description`, `Node.description`), its meaning and accepted units; `gm.case.missing(case)` lists what a document still lacks.
