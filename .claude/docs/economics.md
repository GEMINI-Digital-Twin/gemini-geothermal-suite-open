# Economics, KPIs, checks and well analysis

The packages `gemini.evaluate`, `gemini.analysis` and `gemini.study` sit above the run folders
(`engine`, `run`, `modules`, `plants`, ...), which import none of them. They read a plant, a
`gm.Case` and a finished run through the public API only. Every `gm.evaluate` function takes
`(plant, case, results, ...)`, and its return is a `Value` or a check in the
[return shapes](api.md#return-shapes): in Python a `gm.units.Quantity` in SI that also holds a
`reason` and its `parts`, and `to_plain` gives the plain JSON (no NumPy types, `NaN` and infinity
are `null`). A value the inputs cannot give is never a guess. Every name is real.

## What a run gives

`Results` stores the leaf columns (`path.field`, the outputs and the port quantities), not the
composite outputs. Everything below is read from the edge modules:

- Heat delivered is what the water loses across the `HeatingGrid` leaves and cold delivered what
  it gains across the `CoolingGrid` leaves (`evaluate/_utils/series.py`: `delivered_heat`,
  `delivered_cold`). **Useful** heat and cold are that less the `surplus` of the grid, so at most the
  demand (`useful_heat`, `useful_cold`). `gm.evaluate.totals` gives all three; every KPI and levelised
  cost reads the useful energy: a heat nobody needed costs money and earns nothing.
- Electricity bought and sold are `net_import` and `net_export` of the `ElectricityGrid`, gas
  bought is `gas_out.chemical_flow` of the `GasGrid`, waste `waste_in.mass_flow` of the `WasteGrid`
  and chemicals `chemical_out.mass_flow` of the `ChemicalGrid` (`edge_total`). `gm.evaluate.totals`
  gives them, with the emissions and the losses.
- CO2 comes from one place: `Atmosphere` computes `co2_emission` and `methane_emission` [kg/s] from
  the gas that reaches `gas_in`.
- A tick with no value (a skipped or failed row) adds no energy and is left out of ratios and peaks.
- The window of a run is the sum of its tick durations. Annual figures scale the window to one year
  (`SECONDS_PER_YEAR`, 365.25 days): the run is taken as representative of a year.

A plant without a consumer leaf, such as the doublet heat plant, delivers no heat in these terms, so
its heat and cold KPIs and levelised costs are `null` with that reason.

## Costs

Every cost function returns a `Value`, a `gm.units.Quantity` in SI with the parts of its result in
`.parts`, each a value or a text; `to_plain` gives the JSON, the parts as more keys. `unit` is
`currency` (a label for the case's currency, `economics.currency`; nothing converts between
currencies), `currency/yr`, `currency/J`, `yr` or `kg`; `result.to("EUR/MWh")` converts. `A` is the
annuity factor, the sum over the years of the analysis period of `1 / (1 + discount_rate) ** t`, in years. Every
function takes `on_error="raise"`: a value the inputs cannot give raises `ValidationError`, code
`no_value`, or `missing_assumption`, naming its path in the case (`economics.capex.heat_pump`),
for an assumption nobody gave. With `on_error="record"` nothing is raised and `value` is `None` with a
`reason`. Prices, rates and factors are those of `case.economics`; gemini holds none of its own.

| Name | Returns |
|---|---|
| `gm.evaluate.capex(plant, case)` | the sum of the capex of the equipment, per module in `parts["modules"]`, with the `price_year` of the case |
| `opex(plant, case, results)` | the fixed opex of each kind of equipment (`parts["fixed_by_kind"]`), plus the yearly bill of grid electricity and purchased gas at `economics.energy`, waste and chemicals at `economics.opex.variable` (a profile price is integrated step by step; co-produced gas costs nothing), plus the CO2 emitted at `economics.carbon.price` when the case gives it; `components` lists the parts. There is no variable opex |
| `lcoh(plant, case, results, on_error="raise")` | `(capex + opex A) / (useful heat A)` in currency/J |
| `lcoc(...)` (as `lcoh`) | the same with the useful cold |
| `annualised_cost(plant, case, results, on_error="raise")` | `capex / A + opex` in currency/yr, with `capex`, `opex`, `annuity_factor`, `discount_rate`, `analysis_period` |
| `lcts(...)` (as `lcoh`) | levelised cost of thermal supply: `annualised_cost / (heat + cold)` in currency/J; it needs no `heat_cost_share` |
| `co2(plant, case, results)` | kg of CO2-equivalent over the window, step by step: the leaf `co2_emission`, `methane_emission` times `economics.accounting.gwp.CH4`, grid electricity times `utilities.electricity.co2_intensity`; a factor is asked for only when its source is non-zero |
| `npv(plant, case, results, on_error="raise")` | `-capex + (revenue - opex) A`, with the `revenue` prices of the case and the discounted subsidy (`economics.revenue.subsidy`: its amount per year for its duration, within the lifetime; an amount per energy, `EUR/MWh` as SDE++ pays, is paid on the useful heat of a year up to its `cap`, `MWh/yr` or full-load hours `h/yr` times its `capacity`) |
| `payback(plant, case, results)` | `capex / (revenue - opex)` in `yr`, undiscounted; a subsidy of the case adds its amount per year to the cash flow for its duration only |

The discount rate and the analysis period are `economics.discount_rate` and `economics.analysis_period` of the case; no function takes
either as an argument (the economics file owns them) and the analysis period is read in years. There is no `Cost` type and no `total_cost`: a module that is equipment is a subclass of the
mixin `Equipment` (`gemini/modules/_utils/equipment.py`), sets `equipment_kind` to one of the kinds of
`gm.case.Capex` and defines `cost_size()`, the size its cost scales with. A module never reads the
case: `gemini/evaluate/_utils/pricing.py` multiplies that size by the factor of the kind (for
`drilling`, the cost per metre of the length drilled) and the fixed opex is the share
`opex.fixed[kind]` times that capex.

The unit of a capex factor tells its basis. Besides the basis of the table below, some kinds take
another (`CAPEX_BASES` of `gemini/case/_utils/kinds.py`), so that a factor of a cost catalogue
is used as it is published:

| Kind | Other basis | Unit | Size |
| --- | --- | --- | --- |
| `heat_exchanger` | per W of nominal duty | `EUR/W` | `HeatExchanger.nominal_duty` |
| `thermal_storage`, `ice_storage` | per energy stored | `EUR/MWh` | `ThermalStorage.energy_capacity` (no module is `ice_storage`) |
| `production_pump` | per unit | `EUR` | one per `Doublet`, whatever its flow |

A module gives the size of another basis with `cost_size_of(quantity)` (`"power"`, `"energy"`). A
size it lacks raises `missing_value` naming the design value (`<path>.nominal_duty`), and
`gm.check` reports it as `params.<path>.<name>`; a module with no size of that quantity has no
value (`no_value`). A unit of no basis of the kind is refused when the economics is read
(`invalid_unit`, listing the units of every basis), and `Economics.schema()` lists the bases of a
kind in `x-bases`. A study or a sensitivity varies such a factor in the unit of its basis.

A fixed opex is a share of the capex per year (`%/yr`), or, for a kind sized by a power
(`POWER_KINDS`: the kinds priced per W, and `heat_exchanger` by its nominal duty), an amount per
capacity and year (`EUR/MW/yr`, `EUR/kW/yr`, `EUR/W/yr`, as a catalogue publishes fixed O&M): that
amount times the power size of the module, whatever basis its capex is on. A heat exchanger needs
its `nominal_duty` for it (`missing_value`, and `gm.check` reports it); a kind with no power (a
pipe, a well, a tank, a degasser) refuses that unit (`invalid_unit`). A composite adds only its own part. A factor or a share that
the case lacks for a kind the plant uses raises `missing_assumption` naming
`economics.capex.<kind>` or `economics.opex.fixed.<kind>`; nothing is
estimated. A plant with no equipment has no value.

The kinds, with the size the factor multiplies:

| Kind | Modules | Size |
| --- | --- | --- |
| `drilling` | the wells of a `Doublet` (its production well by segment, the injection well by path: twice the depth together) | m of well |
| `production_pump` | `Doublet` | shaft power at `nominal_flow` [W] |
| `circulation_pump` | `CirculationPump`, `CentrifugalPump` | shaft power [W] |
| `heat_pump`, `compression_chiller` | `HeatPump` (a kind by its `mode`) | `capacity` [W] |
| `boiler`, `electric_boiler` | `Boiler`, `ElectricBoiler` | capacity [W] |
| `chp` | `CHP` | `electric_capacity` [W] |
| `absorption_chiller`, `adsorption_chiller` | `AbsorptionUnit`, `AdsorptionChiller` | capacity [W] |
| `heat_exchanger`, `cooler` | `HeatExchanger`; `Cooler` | conductance [W/K]; capacity [W] |
| `pipe`, `thermal_storage` | `Pipe`; `ThermalStorage` | length [m]; volume [m3] |
| `degasser`, `flare`, `gas_makeup` | `Degasser`, `Flare`, `GasMakeup` | a fixed amount |
| `injection_pump` | `InjectionPump` | shaft power at `nominal_flow` (and `nominal_head` without curves) [W] |
| `ice_storage` | none | no module has a size for it |

Known limits. `InjectionPump` without `nominal_flow` raises `missing_value` when it is priced; `size` sets it.
`IceStorage` (its size in m3
needs the water density, which is not a parameter), `ESP` and `LineShaftPump` (an ESP is paid
inside the `Doublet`), `AquiferStorage`, `BoreholeField`, `DownholeHeatExchanger`, `ORC`,
`FlashTurbine`, `Separator`, `GasCompressor`, `PressurizationTank`, `Filter`, `Desander`, `Blowdown`
and `InhibitorDosing` have no kind either, so a plant that contains them is cheaper in the model
than in life. Grids, environment modules, mixers, splitters, valves and controllers are not
equipment.

`lcoh` charges the whole plant cost to the heat. A plant that also delivers cold has no value ("the
split of its cost is not defined") unless `heat_cost_share` gives the part charged to heat; `lcoc`
gets the rest. `lcts` needs no share: with a `heat_cost_share` of 1, `lcts` is `lcoh` times its
energy over `heat + cold`. It has no value when the run delivers neither. `lcoh` and `lcoc` keep the
one expression `(capex + opex A) / (energy A)`: `annualised_cost` and they share `period_cost`
(`capex + opex A`) and not the division, which would move the last bits of their numbers. Levelised
cost, `npv` and `payback` assume constant yearly energy and cost over the
analysis period, with no degradation, tax, replacement or residual value.

Missing user inputs raise `ValidationError` with code `missing_assumption` and the path
`economics.<name>`: a discount rate or analysis period given nowhere, an electricity or gas price for an
energy the run buys, a heat or cold price for a product it delivers, an electricity emission factor
for grid electricity drawn. A price is asked for only when its energy is non-zero.

### The values of the assumptions

gemini gives no value to any of these: each is a field of `case.economics` (see
[data.md](data.md#the-case)) that the user states, and a call that needs an absent one raises
`missing_assumption`. `gm.evaluate.missing(plant, case, results)` lists every one that the costs
of a run need and the case lacks, at once, as issues. The sample case `examples/hackathon_2026/case.json` states them, in
price year 2015 and with the currency label EUR. Where a value is cited, the source is:

| Field | Value in the sample | Source |
|---|---|---|
| `capex.drilling` | 5.7e6 / (2 x 2300) = 1239.13 EUR/m | SDE+ 2013 reference case, 5.7 MEUR net drilling for a doublet at 2300 m, over two wells of 2300 m (Mijnlieff et al. 2013, EGC, Geothermal energy and support schemes in the Netherlands, slide 26). A 2013 figure, not escalated |
| `capex.degasser` | 1.0e6 EUR | same slide: reserve for separation of hydrocarbons per doublet, a 2013 figure, not escalated |
| `capex.heat_pump` | 0.67 EUR/W | Danish Energy Agency, Technology Data for Energy Plants, April 2020, ch. 40, compression heat pump, excess heat, 10 MW, 2020 in 2015 prices |
| `capex.boiler` | 0.06 EUR/W | same catalogue, ch. 44, district heating boiler, natural gas, 2020 |
| `capex.chp` | 0.95 EUR/W electric | same catalogue, ch. 06, spark ignition engine, natural gas, 1-10 MWe, 2020 |
| `accounting.gwp.CH4` | 29.8 | IPCC Sixth Assessment Report, WG I, ch. 7, table 7.15 (Forster et al. 2021): fossil methane over 100 years |

The other factors of the sample (`production_pump`, `injection_pump`, `compression_chiller`,
`absorption_chiller`, `adsorption_chiller`, `heat_exchanger`, `flare`, `gas_makeup`, `cooler`,
`pipe`), the fixed opex shares, the prices, the discount rate, the analysis period and the CO2 intensity
of electricity are placeholders for the test: the organisers gave no source, and they are not a
recommendation. The shallow district sample states invented placeholders for every factor, as its README says; leave a factor out of a case file and the call that needs it raises `missing_assumption`.

Convert at the boundary: EUR/MWh divided by 3.6e9 is EUR/J, kg/GJ divided by 1e9 is kg/J.

`gm.case.Economics.schema()` gives each field and section a `description` (its meaning and the units
it accepts), so a cost catalogue can be matched against it; the consumables of `opex.variable` are
`chemical` (every product a `ChemicalGrid` supplies, inhibitors included) and `waste_disposal`, and
no other name is read.

## Totals and KPIs

`gm.evaluate.totals(plant, case, results)` returns `{name: value}` (each a `Value`, `{value, unit}` in JSON) of what crossed the
plant's edge (`heat_delivered`, `heat_useful`, `heat_surplus`, `cold_delivered`, `cold_useful`,
`cold_surplus`, `electricity_bought`, `electricity_sold`, `gas_bought`, `losses`, `co2_emitted`,
`methane_emitted`, `waste`, `chemicals`) and of the KPIs below; one the run cannot give is `null`
with a `reason`. There is no separate KPI call. With E(x) the sum over ticks of x times the tick
duration:

| Name | Unit | Definition |
|---|---|---|
| `heating_coverage` | - | E(useful heat) / E(useful heat + `unmet_demand`) over the `HeatingGrid` leaves |
| `cooling_coverage` | - | E(useful cold) / E(useful cold + `unmet_sensible` + `unmet_latent`) over the `CoolingGrid` leaves |
| `cop` | - | E(useful heat) / E(`ElectricityGrid.power_out`); cooling not counted |
| `peak_heat` | W | largest tick sum of useful heat (delivered power, not the demand peak) |
| `peak_cold` | W | largest tick sum of useful cold |

### Daily coverage

`gm.evaluate.daily_coverage(plant, case, results)` says, for each day of a run and each service the
plant has a consumer for (`heating`, `cooling`), how much was asked and who gave it. The result is
`{service: [{date, source, demand, geothermal, backup, short, failed_steps}, ...]}`, the energies
`Quantity` values in the display unit of energy (`gm.units.display`, MWh) and `failed_steps` a count;
`to_plain` gives the JSON, whose `date` and `source` are what the frontend's days strip reads. A day is a
UTC calendar day (the time of a case is UTC) and a tick belongs to the day it starts in. With the
useful power U and the unmet power M of the totals above: `demand = U + M`, `short = M`, `backup` is
the part of U that the units of the roles `boiler` and `chp` of `gm.plants.roles()` gave their
water in the same tick (the roles of the plant, never a list of classes), `geothermal = U - backup`.
No role is a backup of cooling, so its `backup` is 0. A tick that failed, was skipped or shows no
demand adds no energy (as `totals` skips it) and counts in `failed_steps`; a day with one is
`short`. `source` is `short` with such a tick or an unmet demand above a millionth of the day's
demand, else `backup` when the backup is above that, else `geothermal`. The sum of `geothermal +
backup` over the days is `heat_useful` (`cold_useful`) and its ratio to the sum of `demand` is
`heating_coverage` (`cooling_coverage`).

`gm.evaluate.metrics()` lists the metrics a table of results shows as `[{name, quantity, unit}]`
(the table of `gemini/evaluate/_utils/display.py`, kept private); `unit` is the display unit of the
quantity, `yr` for the durations of years.

## Checks and constraints

Each check returns the check `{name, passed, value, limit}`, `value` and `limit` being values; a
violated limit is `passed: false`, never an error (`passed` is `None`, with a `reason` in `value`,
when the results hold nothing the check can judge). Because `Results` has no streams, the enthalpy and mass
closure of `evaluate/balances.py` (sum in minus sum out per call) cannot be recomputed from
it, and the checks audit what the columns hold:

| Check | Covers | `value`, `limit` |
|---|---|---|
| `energy_balance(plant, case, results)` | the leaf columns named in `ENERGY_INPUTS` and `ENERGY_OUTPUTS` of `evaluate/balances.py`, except the signed `heat_accumulation`: finite or missing, not negative | smallest power [W], 1e-9 W |
| `plant_balance(plant, case, results)` | mass and energy in = out + losses + change of stored energy, per module (1e-9) and for the root (1e-6) | a list of checks, the worst relative residual of each |
| `mass_balance(plant, case, results)` | the leaf outputs whose unit in `results.units` is kg/s: finite or missing, not negative | smallest flow [kg/s], 1e-12 kg/s |
| `bounds(plant, case, results)` | every recorded output with a declared limit (`ge`, `gt`, `le`, `lt` of its `Declaration`) | number of values outside, 0 |
| `requirements(plant, case, results)` | every `gm.case.Requirement` of the case and the supply temperatures of the services, below | one check per matched module and requirement |

The limits of a run are the `requirements` of its `gm.Case`: each names a **role** and a
**quantity** of it, never a module path or a field (`gm.plants.roles()` is the closed table):

```python
import gemini as gm

case = gm.Case.from_json("examples/hackathon_2026/case.json")
plant = gm.Plant.from_json("examples/hackathon_2026/plants/HeatingPlant.json")
results = gm.simulate(plant, case)
checks = gm.evaluate.requirements(plant, case, results)
print(case.requirements[0].on, case.requirements[0].quantity, checks[0]["name"])
```

The units of a role are found in the plant by module class and wiring, never by name: `doublet` is
every `Doublet`, `heat_pump` a `HeatPump` whose sink reaches a `HeatingGrid`, `chiller` a machine
whose cold output reaches a `CoolingGrid`, and so on. A requirement applies to each unit of its role
on its own.

`over` says how the run is read: `each` judges every step and reports the worst (`worst_step` gives
its time); `sum`, `mean`, `max` and `min` judge one figure of the run; `duration` judges the total
time of the steps that count, `min` and `max` then being durations, passing within half a step.
`when="running"` counts only the steps on which the module carried flow: the minimum flow holds
while a doublet runs. A bound is a `Quantity` or its dict; a value on the limit passes within a
relative 1e-9.

The role `plant` is the plant as a whole (`unit_path` `""`):
`electricity_bought`, `gas_bought` and `heat_surplus` are powers, read from the same edge ports as
`gm.evaluate.totals` (the net import of the electricity grid, the gas out of the gas grid, the surplus
of the heating grid), and `co2` is the mass emitted in one step [kg] as `gm.evaluate.co2` counts it, so
`over: "sum"` is the mass of the run and needs `utilities.electricity.co2_intensity` when the run
buys electricity (`missing_assumption` otherwise). `gas_burned` is the co-produced gas burned in the plant, a mass flow [kg/s]: what its gas makeups give to a burner (the gas they receive less the excess they send on) and what its flares burn (`burned_mass_flow`), so a rule "burned gas at most X" is `{"on": "plant", "quantity": "gas_burned", "over": "max", "max": ...}`; a run with neither module gives no value. `heat_output` of a `heat_pump`, `boiler` or `chp` and
`cold_output` of a `chiller` are the enthalpy delivered, the difference of the flows of two ports (a
heat pump heating: sink out less sink in; cooling: source in less source out; absorption and adsorption:
chilled in less chilled out; boiler and `CHP`: fluid out less fluid in). `doublet` also has
`reinjection_ratio` (the injected over the produced liquid volume flow of the doublet, judged per step),
`count` (the number of doublets of the plant, one check with `unit_path` `""`) and
`intake_pressure` and `intake_gas_fraction`, the outputs of its `ESP`. A `sum` of a power adds the step
values, with no integration; `when="running"` of the plant counts the steps on which any unit carried flow. The service requirement is checked as well: each `HeatingGrid` must receive water at
least at `demand.heating.supply_temperature` and each `CoolingGrid` at most at
`demand.cooling.supply_temperature`; a service without a supply temperature adds no check.

`gm.evaluate.requirements` returns one check `{name, role, unit_path, quantity, passed, value, limit,
worst_step}` per unit and requirement, `name` the name of the requirement (the supply temperatures of
the services are `heating_supply_temperature` and `cooling_supply_temperature`), `value` the worst value of the run (or the figure) and `limit` the
bound that was violated, else the nearest. `unmet_share` of `heating_supply` and `cooling_supply` is the unmet energy over the energy demanded in the run, one figure of the period (the demand is that of the case, `case.demand.frame`; a service that demands nothing has share 0). A role with no unit in the plant gives one check with `passed` `None` and
`unit_path` `None`; a name that is not in `gm.plants.roles()` raises `ValidationError`, code `unknown_name`,
with suggestions. A violated limit is an answer, and a run with no value of
the field, every row having failed, gives `passed: null` with the reason `no_value`. `Results`
holds leaf columns, so an output of a composite is read through the paths its combination names:
`Doublet` declares `brine_cooling`
(`Output.difference("riser.wellhead_out.T", "injector.wellhead_in.T")`), and the liquid volume flow of
a doublet is `reservoir.liquid_flow` of its reservoir. `gm.schedule` enforces some forms of the same
constraints and lists the others in `plan.attrs["check_only"]`, see
[engine.md](engine.md#schedule); `requirements` judges them all.

A real closure check needs the engine to record each call's residual (`balance.energy_balance`)
as a result column; that is a change to the engine, not to this package.

## `gm.analysis`

`gm.study.calibrate` and `CalibrationResult` fit parameters through replay; the other names:

| Name | Status | Notes |
|---|---|---|
| `nodal(plant, well, conditions)` | real | IPR, VLP and operating point from `gemini/analysis/nodal.py`, for production and injection wells; the plant is not changed |
| `pump_curve(plant, pump, measured=None)` | real | the polynomial head curve of the pump at 60 Hz (the private `_head_curve` of `gemini/analysis/fits.py`), theoretical head of measured points, `gm.analysis.fit_head_correction` |
| `corrosion_forecast(model, until)` | real | `co2_corrosion_rate`, `wall_loss`, `time_to_minimum_wall` |

`nodal` takes `conditions` as one dict or a list of dicts (a what-if): `wellhead_pressure` [Pa],
`rates` as the `[low, high]` bracket [kg/s] and `frequency` [Hz] for an ESP; quantities such as
`{"value": 3, "unit": "bar"}` are accepted. A case whose bracket leaves the well model's domain raises `PhysicsError`; with `on_error="record"`
the case carries the problem in `error` and the other cases still run. The VLP is the wellhead pressure the well, ESP and riser
deliver at each rate; the operating point is where it falls to the wellhead pressure asked for.

`well` naming an injection well, or its aquifer, solves the injection side (`doublet.injector`: the
path of a doublet itself is its production chain). A case has `rates`, `temperature` at the wellhead
and either `rate` or `wellhead_pressure`. `ipr` is the sandface pressure the aquifer needs, `vlp` the
wellhead pressure that delivers it, and the operating point the pressure of the rate or the rate of
the pressure. A rate the column of brine injects alone has no pressure to give: `null` on `vlp`, and a
`null` value with a reason in `operating_point`.

`pump_curve` head is a pressure difference in Pa; the head of a fluid column in metres is
`head / (density g)`. The correction is `theoretical = slope * measured + offset` (offset in Pa).

## `gm.study`

`gm.modules.check` is described in [modules.md](modules.md#registry-categories-and-streams).

`gm.study.size(plant, case)` returns a new plant with first sizes from the case, by gemini
physics only. It runs `gm.check` first and raises its issues, except the parameters of the plant
that have no value, since completing a template plant is what it is for. `backup` is a design policy
of the plant (`params.backup`, with no default: `missing_value` naming `params.backup` when
absent, `invalid_value` for another word on `set_params`): `"peak"` rates a boiler for the whole heating peak (and drive heat) with
the doublets off, so it carries the peak when a doublet is out; `"none"` rates it for the heat the
doublets cannot reach, the larger of the peak less the heat of the doublets at their limits and the
part of the peak the reservoir temperature cannot reach. The sizes: the number of doublets (the
smallest in the `range` of `size.doublets` of the plant whose heat at the flow limit and the brine cooling limit of the
case's constraints covers the heating peak, the largest with a note when none does); the nominal
flow of each doublet, which is the flow limit of the case, the largest flow it may run, so its
`share` in `gm.evaluate.capacities` is at most one; the capacity of each boiler (the policy above),
heat pump and chiller; and the rating of the injection pump (the total flow of the doublets it
serves and the head to inject at that flow less the wellhead pressure). A heat pump gets the part of
the peak the reservoir water cannot reach by itself, `peak (T_supply - T_reservoir) / (T_supply -
T_return)` shared by its units (the formula assumes an ideal exchanger), and none (listed with a
note) when the reservoir is hotter than the supply. A chiller gets the cooling peak shared, except
the chiller that closes the chilled-water series, which gets the whole peak: a sorption unit
delivers less than its rating when its characteristic map says so at the peak conditions (an
adsorption chiller 6 kW short at the peak, which the chillers in series pass on as 3 mK), and the
last chiller makes up the difference. A boiler is rated for the step where the heating demand and the drive heat of the
sorption chillers it feeds (their duty over `thermal_cop`, found from the wiring) peak together:
the whole of it for `"peak"`, and for `"none"` that less the heat of the doublets, at least its
lift share (the ideal-exchanger assumption may leave the supply short, which `broken` lists). The sized plant is then
simulated once on the case. The plant is not changed; the notes are `plant.sizing`: `{"sized":
[{path, value, reason}], "unchanged": [{path, reason}], "broken": [{unit_path, role, quantity,
value, limit, worst_step}], "simulation": str}`, where `broken` lists each requirement the sized
design breaks (empty when it meets them all) and `simulation` says `simulated` or `not simulated:
<code>: <reason>`. A plant class that takes no structural size `doublets` (see
`gm.plants.capabilities()`) keeps the doublets it has and says so in `unchanged`; a size the case
lacks the input for raises `missing_value` naming its path. A size that is not computed for a
module kind (`chp`, `heat_exchanger`) is left unchanged and listed.

`gm.study.minimize(plant, case, objective, evaluations, seed, *, plan=None)`
searches the design space that the plant states. The variables are the plant's: every leaf with a
`range` (continuous, or integer when its parameter is) and every leaf with `options` (strings), and
`size.doublets` when it has a `range` (a discrete variable: the search runs once for each count,
from the lowest to the highest, on a new plant of that size, and the best trial of all counts
wins). Leaves with the same parameter name, the same role (`gm.plants.roles()`) and an equal range
are one variable that sets them all (`heat_pump.capacity`, `chiller.capacity` for three chillers,
`doublet.nominal_flow`, `doublet.depth`); the order is that of the file; a plant that states
nothing to search raises `invalid_design`. `evaluations` and `seed` have no default (7.28). Each
trial sets the variables on the one plant the trials of a batch share (nothing is copied for a
trial), plans the demand of the case on that design with `gm.schedule`, simulates and reads the
metric, so neither the plant nor the case is changed. A `plan` stays fixed over the
trials and lets `case` be `None` for a building block; with neither the call raises
`missing_value`. `gm.check` runs first. `evaluations` is the largest number of simulations **for
each doublet count**; with four variables 20 gave 80 trials. The search is
`scipy.optimize.differential_evolution` from a Latin hypercube with the given seed, with five
candidates per variable, so a smaller budget than one population raises `ValidationError`; the
integer and the option variables are searched as integers.

`gm.study.evolve(plant, case, objectives, evaluations, seed, *, population, polish, plan=None,
on_progress=None)` (`gemini/study/evolve.py`, the operators in `gemini/study/_utils/genetic.py`)
searches the structure and the values together. The genome is one gene per optional module (on or
off), per choice (its group), the doublet count when `size.doublets` has a range, and one per
variable of `minimize` (tied over the doublet counts by name, role and range); a gene of a module
that is off is ignored and is not part of the key a candidate is remembered by. `objectives` is a
metric or a list (`["lcts", "co2"]`, a leading `-` maximises): one is a genetic algorithm, two or
more NSGA-II, with fronts of non-domination and the crowding distance. Ranking is constraint
domination, the rule of `minimize`: a feasible candidate beats every infeasible one, infeasible ones
are ordered by their violation. Parents are drawn by binary tournament; continuous and integer genes
cross by simulated binary crossover (probability 0.9, index 15) and mutate by polynomial mutation
(index 20, probability one over the number of genes), choices cross uniformly and mutate by a random
reset; each generation keeps the best `population` of parents and children. The first generation is
the plant's own values (a sized plant's, clipped to the ranges) in each valid structure, in the order
of `plant.structures()` while they fit, then random candidates from the seed. A candidate whose structure gives no valid plant is refused before any
simulation and counted in `invalid`; a candidate seen before is not run again. The new candidates of
a generation run in the worker processes of `gm.runtime.settings(processes=n)`, each alone, so the
result does not depend on `n`. Each candidate's values are set on the superstructure (on its doublet
count) and then the structure is taken, so the values of a class plant stay genes. `evaluations` is
the total number of simulations of the genetic search; it ends there, or after ten generations in a
row with no new candidate (the space is seen). `polish` (0 for none) searches the first `polish`
designs again with `minimize` on the first objective, from the design, in the ranges its plant keeps,
with `population` evaluations per doublet count (the budget `minimize` reads), so `population` must
be at least five per variable; the best plant of each is run once more for every objective and joins
the designs, and these simulations add to `evaluations` in the result. It returns an `Evolution`
`{front, best, history, evaluations, invalid}`: `front` the designs no other beats on every objective
(the best one alone for one objective, the least violating one when none is feasible), ordered by
the first objective; `best` the best on the first objective; `history` per generation the
simulations so far, the best feasible value of each objective so far and the size of the feasible
first front. A `Design` is `{structure, plant, metrics, feasible, reason, violation, parameters}`;
`to_dict()` of both is plain JSON in display units, a design's plant as its plant file.

A trial is feasible when its `gm.evaluate.verdict` has no reason that a design variable can change:
the reasons with a `violation` (a failed requirement, the supply temperatures of the services
included, an operating limit, a failed step, a balance out of its tolerance), and every limit of
the `constraints` argument (limits on *metrics*, `{metric, minimum, maximum}`, not the
`case.requirements` on roles) holds. A reason with no `violation` is structural (a service the
plant has no unit for, `cold_delivered` of a heating plant) and does not rank the trials; the
verdict of the run of the best plant keeps it. The violation of a trial is the sum of those of its
reasons (relative excess), at most 1e6 for a failed step. A trial that does not run, such as a negative injection head at great depth, is
infeasible and the search goes on. The optimiser sees every feasible trial as better than every
infeasible one and the infeasible ones ordered by their relative violation. `history` holds every
trial with its `reason` (`None` when feasible; the first failed check, a dict, or a text) and
`parts["violation"]`. The result is `{best, feasible, history, evaluations}`; `best` is the
objective as a `Value` whose `parts["parameters"]` are `{name: Quantity}` (an option is its string)
and whose `["plant"]` is the best feasible plant (a `Plant`; its `to_json` runs), or with none the least violating trial that ran, then `feasible` is
`False`. A trial costs about 1.5 times one `gm.simulate` of the same plant and case (0.15 s against
0.10 s on the year of the hackathon sample), see below. The first population of a search is one
batch (one array pass for all its candidates); each candidate of a later generation is built from
the members replaced before it, so they run one by one.

`gm.study.sample(plant, case, metrics, samples, seed, *, plan=None)` draws `normal`,
`uniform` and `triangular` values (the `uncertainty` of the case, `case.<path>`) with
`numpy.random.default_rng(seed)`, one simulation each, and summarises each metric as `mean`, `p5`,
`p50`, `p95`, with `failed`, the number of draws left out. A run with failed steps is no valid
design: its metrics are `None` with a `reason` (the count of failed steps and the most frequent
failure group of `gm.evaluate.failures`), it stays out of the summary, and in `sensitivity` its
end and the effect are `None` with that reason. `minimize` calls such a trial infeasible with the
same reason, never the best, and `compare` calls a report with `failed_steps > 0` infeasible
(`failed_steps`). The evaluate cost functions still report what was delivered.
`gm.study.sensitivity(plant, case, metrics, *, plan=None)` runs each value the case declares an
`uncertainty` for at its low and its high end with the others as they are, and returns a list of `{parameter, metric, low, high,
at_low, at_high, effect}`, the largest effect first, with `to_frame(units=None)`: the metric columns
in the display unit of the metric, or the unit of `units`, and a `unit` column.

`gm.Study` (`gemini/study/study.py`) is the same functions from a `study.json` (`kind: study`, see
[inputs.md](inputs.md#studyjson-kind-study-gmstudy-optional-what-to-run-how)): `cases`, `plants`,
`prepare`, `method` (`run`, `minimize`, `sample`, `sensitivity`, `evolve`), `objective`, `metrics`,
`evaluations`, `samples`, `seed`, and for `evolve` `objectives`, `population` and `polish` (it
refuses `objective`), with no default for a setting the method needs. An `evolve` run's design is
the `best` of the search. `Study.run()`
prepares (`size`), calls `minimize`, `sample` or `sensitivity`, simulates and reports each plant on
each case and returns a `StudyResult`: `runs` (`plant_name`, `case_name`, `verdict`, `metrics`,
`plant`, `report`, `found`, `note`), `comparison` (a `gm.evaluate.compare` of the reports of each
case, by the objective then the metrics) and `best` (the feasible run ranked first by the
objective, per case); `to_json(folder)` writes the run records. A `minimize` on a plant that states
no range and no options runs the plant as it is, with a `note`. `Study.run(plants={name: Plant})`
takes plants in memory instead of the files. `gm.check(plant, case)` (`gemini/engine/check.py`)
returns the issues that need both: a capex and a fixed opex for every equipment kind (when the case
has economics), a requirement on a role the plant lacks (not `heating_supply` or `cooling_supply`: a
plant without a supply is judged infeasible for that service), an initial state for every state of
every stateful module, the energy prices of a `least_cost` dispatch, and the parameters without a
value; `simulate` and every study function run it first.

**What a trial costs.** The trials of a batch share one plant: a trial sets its variables and the
values of the case on it (`applied_in_place` of `gemini/engine/apply.py`), keeps the state it has
(`gemini/study/_utils/shared.py`) and puts it back whenever it goes on, so nothing is copied for a
trial. The trials run side by side: each plans and prepares its run, the array pass of all of them
is one (a parameter or a sampled value is a column over the rows of the trial), and each reads its
metrics from its own results, which are those of a run alone. The ESP depth and the pipe path of
a well (`section_length`, `section_inclination`, `section_diameter`, `section_roughness`,
`esp_depth`) are numeric graph inputs, so one traced graph serves every trial of a study (a
different number of sections, or an ESP that is added or removed, traces once more), and trials
that differ in a structural value (a text option that changes the structure, a doublet count) form
batches of their own. A plant that holds a graph break (a root solve such as `NodalDoublet`, a
pre-hook) runs its trials one at a time. There is no batch-size setting: one batch for the first
population of a search, for the draws of `sample` or `sensitivity` of a process.

**Parallel trials.** `with gm.runtime.settings(processes=4):` splits the draws of `sample` and
`sensitivity` into four consecutive parts, each one batch in its own worker process, and runs the
searches of `minimize` for the different doublet counts in the processes (a search over one count
is sequential after its first population: each candidate uses the generation before it). The
results are those of a serial run, in the same order. Workers start from a `forkserver`, so a
script needs the `if __name__ == "__main__":` guard; the first parallel call of a process pays the
import of gemini once (about a second and a half) and every worker traces its own graphs, so a
study of fewer than a dozen trials is faster serial.

**Progress and cancelling.** `minimize`, `sample`, `sensitivity` and `Study.run` take the keyword
`on_progress=None`, a callable `on_progress(done, total)` with the meaning of the engine's
`on_progress` ([engine.md](engine.md#callbacks)): it is called in the calling process after each
finished trial, in a serial call, in a batch and with `processes=n` (the workers tell the parent
through a queue). `total` is the trial count the call knows: `samples`, two for each uncertain value,
the budget of a search summed over its doublet counts (a population times its generations); for
`Study.run` the sum over every plant and case, a pair that runs no trial counting as one. A search
that ends before its budget still ends with `done == total`. Raising `gm.errors.Cancelled` from it
stops the study cleanly: no later trial starts (the trials of a batch that already ran in the same
pass are lost with it), the workers are stopped, and the exception propagates, the class of the
engine's callbacks; any other exception it raises propagates too. The trials, their order, the
random draws and the numbers do not depend on it, and a call without it is that of 0.5.1.
`gm.study.size` runs no trials and has no `on_progress`.

`gm.study.kinds()` gives the kinds in plain words with the JSON Schema of their settings; `objective` of `gm.evaluate.metrics()` marks the metrics `minimize` may target. The cost functions take the keyword-only `units="display"`: the value and its parts in the display table (MEUR, MEUR/yr, EUR/MWh, yr).

A metric is a KPI or total of `gm.evaluate.totals` or one of `lcoh`, `lcoc`, `lcts`,
`annualised_cost`, `co2`; the economic ones read the economics of `case`, so they need a case with
the factors they use. `parameters` in `best`, `history` and `samples` are `Quantity` values in SI,
the input of the next `set_params`.

## Verdict

`gm.evaluate.verdict(plant, case, results)` is the one place that decides feasibility
([inputs.md](inputs.md#6-what-gemini-checks-on-every-run-not-inputs)). It returns `{feasible,
reasons}`; a reason is `{kind, name, message}` and, when it has them, `path`, `value`, `limit`,
`worst_step`. `requirement`: a requirement of the case or the supply temperature of a service
failed (`name` that of the requirement), no requirement could be checked, a check that could not
be judged beside a passed one and none failed (no `violation`; not an idle unit nor the supply of an
undelivered service), or a service the case
asks for is not delivered (`name` `heat_delivered` or `cold_delivered`). `failed_step`: failed or
skipped rows (`failed_steps`). `numerical`: `mass_balance` below -1e-12 kg/s, `energy_balance`
below -1e-9 W, a leaf residual above 1e-9 or the root above 1e-6 (`plant_balance`), a loop that did
not converge; the constants of inputs.md 7.5. `bound`: `bounds` found values outside the limits a
module declares, or a module with `operating_limits` `(output, "min" | "max", parameter)` has the
output past the value of the parameter in the steps in which it carried flow (`path` the module,
`name` the output). A limit never changes a run. `report` applies the case once and holds the
verdict under `verdict`; `report` reads `economics.accounting`, which a second economics file
changes (two allocations, two reports).

## Report and comparison

`gm.evaluate.capacities(plant, case, results)` returns `{path: {kind, capacity, peak, share}}` for
each module that is equipment and has a rating: the design capacity, the largest use of any step
and their ratio. `gm.evaluate.report(plant, case, results)` returns a `Report`, a `dict` with
`heat_delivered`, `cold_delivered`, `boiler_heat`, `electricity_bought`, `gas_bought` (J over the
run), `capacities`, `capex`, `opex`, `lcts`, `lcoh`, `lcoc`, `co2`, `requirements`, `verdict`, `passed` and
`failed_steps`; its costs are read with `on_error="record"`, so a cost the case cannot give is a
value `None` with a `reason` and many designs stay comparable. `report.to_dict()` is plain JSON in display units, the parts of each value too: the annualised cost and the opex components in MEUR/yr, an energy per year in MWh/yr, a mass in kt, a duration in days (`analysis_period`, `payback` and `lifetime_years` in yr) and a temperature difference in K; `units=` reaches the parts of the same SI unit (`co2="t"` shows the kg parts in t); the values inside the report stay SI.
`gm.evaluate.compare(reports, by)` ranks reports by the metrics `by` (a name, a list, or a
`{metric: "min" | "max"}` dict) and returns a `Comparison`, a list with one entry per report in the
order given (`index`, `values`, `ranks`, `pareto`, `feasible`, and `reasons` when not feasible) and
`to_frame(units=None)`. A report is feasible when its `verdict` has no reason; feasible reports rank first, only
they can be on the front, and `reasons` are those of the verdict. `values` stay floats in SI; `to_frame` shows the metrics in display units, columns
`<metric> [<unit>]`. A report with no value of a metric ranks last for it and is never on the
front.
