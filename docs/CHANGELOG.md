# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- Documents by audience: `README.md` is short and `docs/` is for people, with `docs/guide.md`,
  `docs/rules.md` (every project rule, out of `AGENTS.md`) and this file, moved from the root.
- Every git worktree goes under `.tmp/`, and a test fails if anything under `.tmp/` is tracked.

## [0.6.17] - 2026-11-05

### Fixed
- A plant file whose `inlets` or `outlets` entry is not a port name (such as a stream state)
  no longer raises `TypeError: unhashable type` in the reader (geomind QA-148).
- A tear stream with no first guess names the modules of the loop that would offer their
  outlet once set (a Cooler: `loop_pressure` and `flow`), so a closed chiller condenser loop
  says what it lacks (geomind QA-148).
- A module call whose inlet or outlet value is invalid says `inlet 'X': <the error>`; it no
  longer says "invalid inlet" and lists the valid names when the name is valid (geomind QA-149).

## [0.6.16] - 2026-11-05

### Fixed
- The carbon price applies to the plant's own CO2 and methane (CO2e), not again to grid
  electricity, whose price carries its CO2 (EU ETS); the co2 metric still counts it. Cost and
  the schedule's merit order both (geomind QA-128).

## [0.6.15] - 2026-11-05

### Fixed
- The schedule runs a doublet at most at its `nominal_flow` (the flow its pump is designed and
  priced for), never below the case's minimum flow (geomind QA-130).

### Added
- A plant without a class on one doublet `d0` takes a range on `size.doublets`; `resized`
  copies `d0` and joins the copies in parallel with mixers and splitters, so `minimize` searches
  the doublet count of a free plant (geomind QA-129).

## [0.6.14] - 2026-11-05

### Fixed
- `gm.evaluate.capacities`: a module rated by conductance, volume or length (an exchanger, a tank,
  a pipe) gets the reason "a rating in W/K is not a use the run measures; the module ran n of m
  steps" instead of "the run shows no use of this module" (geomind QA-123).

## [0.6.13] - 2026-11-05

### Fixed
- `gm.evaluate.requirements`: `unmet_share` of a run with failed steps is undecided (`passed`
  `None`) with the reason `no_value: N steps of the run failed, so the unmet energy of the period
  is unknown`; it was `passed` `False` with "no value" and read as a missing rule (geomind QA-104).
- `gm.evaluate.daily_coverage`: an `ElectricBoiler`'s heat is backup, found by its class; it was
  counted as geothermal (geomind QA-107).

## [0.6.12] - 2026-11-05

### Added
- Units `m/s2` (spelled also `m/s^2`, `m/s²`, `N/kg`) and `kg/m2`, so a density times an
  acceleration times a depth gives a pressure (geomind QA-074).

## [0.6.11] - 2026-11-05

### Changed
- An ESP's `out_of_range` message names where its head or power curve is below zero, from 0 to
  `maximum_flow` ("the curves give negative head at flows 0 to 0.012 m3/s"), not only the one
  flow of the row (geomind request 35). Read once per set of curves at the reference frequency;
  a pump whose curves cannot be read gives the message as before.

## [0.6.10] - 2026-11-05

### Fixed
- A plant file's inlet or outlet target given as a bare name (`"inlets": {"grid_gas": "gas"}`)
  is refused as `invalid_connection` with the expected `<module>.<port>`, instead of raising
  `KeyError('')` from the port lookup (geomind QA-083: build_plant returned a bare internal error).

## [0.6.9] - 2026-11-05

### Changed
- `gm.check` names a doublet without a depth first (`params.<doublet>.depth`), saying that the
  case's reservoir temperature and pressure reach the doublet only with it (geomind QA-082,
  QA-049); the plain missing-parameter issue of the same path is not repeated.

## [0.6.8] - 2026-11-05

### Fixed
- A schedule reads a doublet's flow range over all its `production_flow` requirements
  (`over="each"`, `when="running"`): the largest `min` and the smallest `max`, so a minimum and a
  maximum stated as two rules make one range, and one rule with both works as before (geomind
  QA-080: every simulate failed with "no requirement on doublet gives a flow range"). The brine
  cooling limit is the smallest `max` of its rules. A range whose largest min is above its
  smallest max is refused (`invalid_value`), naming the rules.

## [0.6.7] - 2026-11-05

### Fixed
- `gm.check` returns the issues of a plant with unset parameters again instead of raising
  `uninitialized parameters`: the 0.6.5 rules for `params.backup`, `params.control.*` and a split
  well's `esp_depth` read `module.segment` and the plant options through attribute access, which
  raises for an unset parameter (geomind QA-076: every check of an incomplete plant failed, so
  read_plant, build_plant and patch_plant returned errors instead of the missing values).

## [0.6.6] - 2026-11-05

### Added
- `gm.study.structure_plant(plant, structure, parameters)`: the ordinary plant of one structure
  of an `evolve` study, built as `evolve` built it (doublet count, the values the search set,
  then the bypass), from the superstructure and a design's `structure` and `parameters` as
  `Evolution.to_dict` gives them (display units) or as a `Design` holds them. `structures` in
  `to_dict` keeps no plant, so every listed structure can now be opened (evolve structures view).
  A front design's plant built so equals the one `to_dict` gives.

## [0.6.5] - 2026-11-05

### Added
- `gm.check(plant, case)` names `params.control.dispatch`, `params.control.outages`,
  `params.backup` and the `esp_depth` of a production well split at its pump when they are unset:
  a schedule, a sizing or a run stops on each (geomind requests 33 and 36; QA-040).
- A relative humidity (`site.air.relative_humidity`, `demand.cooling.indoor_relative_humidity`)
  takes a unit of a fraction: `-` or `%` (80 % is 0.8), as a gas fraction takes `mol%`; the unit
  `%` is a fraction (request 38; QA-043).
- A unit problem (`invalid_unit`) carries `quantity` and `accepted` in its `problem()` and in
  `ValidationError.problems` (request 34).

### Fixed
- A daily (or coarser) series read in a zone with daylight saving time (`time_zone:
  Europe/Amsterdam`) is matched to the case's steps by its local calendar dates, so the days of 23
  or 25 hours at the clock change are no longer refused (request 37; QA-039).

## [0.6.4] - 2026-11-04

A bug fix, additive: everything that worked on 0.6.3 works the same, and `examples/hackathon.py`
prints the same output.

### Fixed
- A case whose `site.fluid.dissolved_gas` names `H2S` (even at 0 mol%) passed `set_case` and
  `gm.check`, then failed in `build_plant`/`simulate` with `gas composition: species = 'H2S'`.
  `H2S` is now a species of `gemini.physics.gas.SPECIES`, the one list of gas species:
  `site.fluid.dissolved_gas` (`CH4`, `CO2`, `N2`, `H2S`, unchanged) and
  `utilities.gas.composition` take their species from it, so the case reader can no longer accept
  a species a stream refuses (a test holds the two together).

### Added
- `H2S` in any gas composition (`Fluid.gas_composition`, `utilities.gas.composition`): molar
  mass 34.081 g/mol, lower heating value 518.07 kJ/mol (H2S + 3/2 O2 -> SO2 + H2O, NIST
  formation enthalpies), no carbon. It adds heat in boilers, CHPs and flares and forms no CO2;
  the SO2 it forms is not reported by any module.

## [0.6.3] - 2026-11-04

The app team's requests 11, 12, 16, 17, 22 and 26 to 31, as far as they are gemini's. Additive:
nothing of 0.6.2 is removed or renamed, every existing file reads and costs as before, and
`examples/hackathon.py` prints the same output. Request 32 needs no change: `site.air.pressure`
already gives the air pressure, and a case without it is a `missing_value` naming that key.

### Added
- Units: `degC/km`, `°C/km`, `C/km` (and per m) are a temperature gradient equal to K/km (a
  difference, no offset); `W/m/K`, `W/m2/K`, `W/K`, `J/kg/K` and `J/m3/K` accept `degC` and `°C`
  (not a bare `C`, a coulomb there). A lone degC stays an absolute temperature.
- Units: a thermal conductance (W/K) takes `kW/K`, `MW/K` and `GW/K`.
- `Plant.to_dict` / `Plant.to_json` take `units=` (a map from quantity to unit, `"display"` or
  `"si"`) to write a plant file in the caller's units; the default output is unchanged, and a
  file in any fitting unit reads back to the same plant.
- `economics.capex.pipe` may be per W of capacity and per metre (`EUR/MW/m`, the basis of the
  Danish Energy Agency for district heating pipes) besides per metre: it multiplies the new
  optional `Pipe.nominal_capacity` (design mass flow × cp × design ΔT) by the length. A missing
  one raises `missing_value` naming it, and `gm.check` reports it. New units `EUR/W/m`,
  `EUR/kW/m`, `EUR/MW/m`, `currency/W/m` (quantity `money_per_power_length`).
- `gm.study.metrics()`: the metrics a study reads (`objective`, `objectives`, `metrics`), each
  with `title`, `unit`, `description`, `better` and `objective`; the same names
  `gm.study.kinds()` offers.
- `Case.schema()` gives every key a `description` (`about`, `initial_state`, the return
  temperatures, `time`, `requirements`, every site, demand and utilities field); `Economics.schema()`
  gains them for the header, `about` and the keys of a value.

### Fixed
- A doublet designed from its depth with one design value left out (`well_diameter`,
  `roughness`, `nominal_flow`, `pump_efficiency`, `nominal_wellhead_pressure`, or the depth
  itself) makes `gm.check`, `Plant.check` and a run name that value instead of every child it
  derives, including the reservoir permeability and thickness the case gives. A plant of doublets
  names its own `depth`. A doublet set child by child is unchanged.
- `gm.call` with a control or boundary in `parameters` raised a bare `KeyError`; it now raises
  `invalid_call` at `parameters.<name>`, pointing to `controls` (the error is still a
  `KeyError`). `set_params` of a control says it is a control set with `set_inputs`.
- `docs/cost-sources/sources.csv`: every `path` is a key of the case (`economics.capex.*`,
  `economics.opex.variable.chemical`, `utilities.electricity.co2_intensity`, ...) instead of the
  old `assumptions.finance.*` spelling; a test checks every path. No value changed.

### Documentation
- `time.end` is excluded from the period (schema description and guide); the behaviour is
  unchanged.

## [0.6.2] - 2026-11-04

Structure optimisation made a real tool, and the app team's requests 13 to 21. Additive: nothing
of 0.6.1 is removed or renamed, every existing file reads and costs as before, and
`examples/hackathon.py` prints the same output.

### Added
- `gm.study.evolve(..., stop=None)`: `{"generations": n}` ends the search when the feasible front
  has not changed for `n` generations, `{"seconds": s}` after a time limit; `study.json` takes
  `stop` for `evolve`.
- `Evolution` gains `structures` (the best design of each valid structure, with its simulation and
  feasible counts), `rejected` (each refused structure with its reasons), `objectives`, `budget`
  (what was spent and why the search stopped) and a hypervolume per generation in `history`;
  `Evolution.to_frame()` gives the front as a table and `Evolution.explain()` a short text.
- `scripts/validate_evolve.py`: the acceptance harness of `evolve` against a brute-force truth and
  random search.
- `gm.plants.union(plants, *, name)`: one superstructure plant whose structures give back each
  of several concrete plants (modules matched by name, the others optional or a choice, in series);
  `plant.union` holds `{"structures", "notes"}`. Plants it cannot merge raise `invalid_design`.
- `plant.set_bypass(name, {inlet: outlet})` and the plant file key `bypass`: how one module is
  bypassed when a structure turns it off, over its class's `bypass` and the `<x>_in`/`<x>_out`
  pairs; `{}` removes the module with all its connections, and a structure that then leaves a
  port unconnected is refused. A mixer or a splitter can now be optional, so a whole branch
  (cooling with its splitter, mixer and consumer) can go.
- Module classes declare their bypass where it is physical: `Degasser` and `Separator`
  `{fluid_in: liquid_out}`, `GasMakeup` `{gas_in: excess_out}`, and `{}` (removable) for `Flare`
  and every grid (`GasGrid`, `ElectricityGrid`, `HeatingGrid`, `CoolingGrid`, `ChemicalGrid`,
  `WasteGrid`). Such a module could not be optional before; no number changes.
- `examples/hackathon_superstructure`: the peak boiler with its gas makeup and gas grid is a
  choice on or off, and cooling off removes the cooling branch; the cooling consumer sits on the
  chillers directly. 32 valid structures.
- The unit `mol%` (`gm.units.Unit.MOL_PERCENT`, 0.01), a unit of every dimensionless quantity like
  `ppm`. The mole fractions of a composition take a unit of a fraction: `site.fluid.dissolved_gas`
  and `utilities.gas.composition` of a case accept `{"value": 20, "unit": "mol%"}` and
  `{"value": 0.2, "unit": "-"}` (the case schema lists the units, the unit is optional), and the
  `gas_composition` and `grid_composition` of `gm.Fluid` a `Quantity` or its dict per species. A
  value without a unit keeps meaning a fraction, as before.
- `IceStorage` is equipment of kind `ice_storage`, priced only when the economics gives
  `capex.ice_storage`: per m3 of the new optional `IceStorage.volume` or per energy stored
  (`EUR/MWh`) of the new optional `IceStorage.energy_capacity`, with its
  `opex.fixed.ice_storage`; a missing size is `missing_value` and `gm.check` reports it. Without
  `capex.ice_storage` the store adds no cost and `gm.check` asks nothing for it, so every
  existing case costs as before (`PRICED_WHEN_GIVEN`).
- `gm.case.Economics.schema()` (and the `economics` of `gm.Case.schema()`) gives every field and
  section a `description`: its meaning and the units it accepts. `opex.variable` says it accepts
  two consumables only, `chemical` (every product drawn from a `ChemicalGrid`, a scale or a
  corrosion inhibitor alike) and `waste_disposal`, each per kg.
- A capex factor's unit tells its basis: `economics.capex.heat_exchanger` per W of nominal duty
  (`EUR/W`) besides per W/K, `thermal_storage` and `ice_storage` per energy stored (`EUR/MWh`)
  besides per m3, `production_pump` per unit (`EUR`) besides per W. The new optional parameters
  `HeatExchanger.nominal_duty` and `ThermalStorage.energy_capacity` give those sizes
  (`Equipment.cost_size_of(quantity)`); a missing one raises `missing_value` naming it, and
  `gm.check` reports it. A unit of no basis is `invalid_unit`. `Economics.schema()` lists the
  bases in `x-bases`. Every existing file reads and costs as before.
- `economics.opex.fixed.<kind>` takes an amount per capacity and year (`EUR/MW/yr`) besides a
  share of the capex (`%/yr`), for the kinds sized by a power; it multiplies the power size of
  each module (a heat exchanger's `nominal_duty`). New units `EUR/W/yr`, `EUR/kW/yr`,
  `EUR/MW/yr` and `currency/W/yr` (quantity `annual_money_per_power`, shown in `EUR/MW/yr`).
- `economics.revenue.subsidy.amount` may be per energy of the useful heat (`EUR/MWh`), as SDE++
  pays, besides per year; the new optional `cap` limits the heat it is paid on, an energy per year
  (`MWh/yr`) or full-load hours per year (`h/yr`) times the new `capacity` it is granted for (absent
  with a cap in hours: `missing_assumption`). A cap on an amount per year is refused. `npv` and
  `payback` count it. New units `h/yr`, `s/yr` (quantity `annual_duration`, shown in `h/yr`).
- `economics.opex.per_energy.<kind>`: a variable O&M per energy produced (`EUR/MWh`) for the kinds
  that produce an energy (`chp` its electricity, `boiler`, `electric_boiler`, `heat_pump` their
  heat, the chillers their cold), on what each unit produced in the run, scaled to a year. `opex`
  gains `components["per_energy"]` and `per_energy_by_kind` only when the case gives the map;
  with it, a producing kind the plant uses needs a price. `Equipment.product()` names the ports.

### Changed
- `gm.study.evolve` searches better and faster (measured by `scripts/validate_evolve.py`): sizes of
  alternatives are not tied, genes of modules that are off are ignored, no candidate is simulated
  twice and none is kept twice in a generation, the first generation holds every valid structure
  with the plant's values, half of the children are local steps (a compass search with pattern
  moves around the best candidate of the best structures and, with several objectives, along the
  front), a child drawn with a refused structure takes the nearest valid one (it still counts in
  `invalid`, which now counts such draws), structure genes mutate at their own rate, more than
  256 structures are judged when drawn, and the candidates of one structure run as one batch on
  one plant. The same seed still gives the same result whatever the number of processes; the
  result differs from 0.6.1's.

### Fixed
- `gm.study.evolve` called a design with no unit for a service (a structure without cooling)
  feasible; it is infeasible now. A candidate whose run raises is infeasible with the error as its
  reason instead of stopping the search. `Evolution.to_dict()` wrote verdict reasons that are not
  plain JSON.
- `gm.study.minimize` told `on_progress` a total below the trials it runs when the plant has two
  variables or more (a population is five per variable times the variables); the trials and the
  numbers are unchanged.
- `study.json` of `evolve`: an objective given twice and `evaluations` below `population` are
  refused when the file is read, and `Study.check` reports a superstructure with no valid structure.
- `gm.Case.from_dict` and `from_json` list every issue of a case in one `ValidationError`
  (`error.issues`, each with `path`, `kind` and `message`): a wrong `time` (a step without a unit,
  no `time` at all) or a header without a `name` no longer stops the read before the sections, and
  an economics without a `name` still has its values judged. A series is not aligned while the
  time is wrong and adds no issue of its own. A file of another `kind` is still refused alone.
- A list parameter with a unit (the sections of a well path: `section_length`,
  `section_diameter`, ...): `describe()` gives its `type` as `array`, not `number`;
  `parameter_schema()` accepts `{"value": [...], "unit": "m"}`, the form it is given in; the error
  of a bare list, a single number, a list without a unit or with a wrong unit, from `set_params`,
  `validate_params` or attribute assignment, shows the value as given and asks for
  `{'value': [<number>, ...], 'unit': <unit>}` instead of a number. In a plant file the unit of a
  list is one issue at `<path>.unit`, not one per item. Codes and paths of other values are
  unchanged.

## [0.6.1] - 2026-11-03

Structure optimisation, approved by the owner. Additive: nothing of 0.6.0 changes, and
`examples/hackathon.py` prints the same output.

### Added
- A plant may state a superstructure: `plant.set_optional(name)` (the module may be off, then
  bypassed: each stream inlet `<x>_in` joined to its outlet `<x>_out`, or the `bypass` pairs its
  class declares; power ports dropped) and `plant.set_choice(name, {group: [modules]})` (exactly
  one group on; `"none": []` allowed). `plant.optional`, `plant.choices`, `plant.structures()`
  (every valid structure) and `plant.with_structure(structure)` (the ordinary plant of one). The
  plant file keys `optional` and `choices`; `plant.check()` reports a superstructure with no valid
  structure.
- `gm.study.evolve(plant, case, objectives, evaluations, seed, *, population, polish, plan=None,
  on_progress=None)`: a genetic search of the structure, the doublet count and the ranges and
  options of a plant; with two objectives or more it is NSGA-II and gives the Pareto front. It
  returns `gm.study.Evolution` `{front, best, history, evaluations, invalid}` of
  `gm.study.Design`s. Invalid structures are refused before any simulation, a candidate seen before
  is not run again, generations run in worker processes, and the same seed gives the same result.
  `polish` refines the best designs with `minimize`. No new dependency.
- `study.json` method `evolve` with `objectives`, `evaluations`, `population`, `seed` and `polish`;
  `gm.study.kinds()` lists it.
- `examples/evolve.py`: the hackathon superstructure searched on cost and emissions.

## [0.6.0] - 2026-11-03

A breaking release, approved by the owner: the ports of a module are one class, `Port`, with
typed fields, so a connection is checked by what it carries and a plant can suggest its
connections. Every number of 0.5.14 is the same: `examples/hackathon.py` prints the same output.

### Removed (breaking)
- `gm.Inlet`, `gm.Outlet`, `gm.modules.Inlet`, `gm.modules.Outlet` and their `kind=`, `drawn=`
  arguments. A module declares `Port(Direction.IN, ...)` or `Port(Direction.OUT, ...)` instead:
  `Inlet(Stream, kind="hot_water")` is
  `Port(Direction.IN, fluid=Fluid.WATER, phase=Phase.LIQUID, level=Level.HOT)`,
  `Inlet(Power, kind="electricity")` is `Port(Direction.IN, energy=Energy.ELECTRICITY)`, and
  `Inlet(Stream)` is `Port(Direction.IN, fluid=Fluid.ANY)`. `drawn=True` is `flow=Flow.DRAWN`.
  A port still reports its label of before as `port.kind`, and `describe()` still gives `kind`.

### Added
- `gm.Port` (also `gm.modules.Port`): `Port(direction, *, fluid=None, energy=None, phase, level,
  generic, many, flow, required, temperature, pressure, offered, description)`. Exactly one of
  `fluid` (a stream port) and `energy` (a power port) is given; a field not given is any.
- `gm.modules.Direction`, `Phase`, `Level`, `Flow`; `gm.streams.Energy` (`Energy.ELECTRICITY`,
  `HEAT`, `FUEL`, `ANY`); the `gm.Fluid` presets `Fluid.WATER`, `BRINE`, `GLYCOL`, `STEAM`, `AIR`,
  `NATURAL_GAS`, `FLUE_GAS`, `CHEMICAL`, `WASTE`, `ANY` and `Fluid.family`, by which a port
  compares fluids; `Fluid.kind` takes `chemical` and `waste`.
- One rule for a connection: an outlet to an inlet, a stream to a stream or a power to a power,
  and each of phase, fluid, level and energy equal or any. `connect` refuses the rest with
  `stream_mismatch`, naming both ends, their fields, the field that differs and the free ports
  that would fit (`suggestions`). Gas into a pipe of liquid is now refused.
- Generic ports: a pipe, a pump, a mixer, a splitter, a valve, each side of a heat exchanger and
  the source of a heat pump carry what they are connected to, the same through the module.
- `Plant.check()` also reports, at once, every connection the inferred fields refuse
  (`stream_mismatch`) and every generic letter asked to carry two values (`generic_conflict`).
- `Plant.suggest(port=None, *, free=True, loose=True, limit=None)`: the ports a port, a module
  or every open port may connect to, best first, as `gm.plants.Suggestion(port, match, exact,
  loose, closes_loop)` with `match` `gm.plants.Match.EXACT` or `LOOSE`; no score. The partner
  that closes a loop comes first. `plant.connect(end, suggestion)` takes a suggestion.
- The code `generic_conflict`.

### Changed
- `docs/rules.md`: the freeze is from 0.6.0.

## [0.5.14] - 2026-11-03

Every public name, default and number is the same as 0.5.13; a speed exception to the freeze,
approved by the owner.

### Changed
- `gm.Study.run` runs its plants (and cases) in worker processes at once when
  `gm.runtime.settings(processes=n)` gives more than one, instead of one after the other; the
  result is the same, in the same order. `examples/hackathon.py` (six plants, 8 processes) takes
  62 s instead of 89 s with the same output. A study of one plant is unchanged.

## [0.5.13] - 2026-11-03

The last feature release: from this version gemini is frozen and takes bug fixes only, each as a
new 0.5.x patch. Every existing name, default and number is the same as 0.5.12.

### Added
- A series may state the zone of its CSV times: `{"file", "column", "unit", "time_zone"}` with an
  IANA name (`"Europe/Oslo"`, `"UTC"`). A time without an offset, such as the dates of a daily
  demand (`2027-01-01`), is then a local time in that zone; one the clock skips or repeats at a
  change of the clock, or an unknown zone, is an issue. Without `time_zone` nothing changes: a
  time without an offset is refused, and there is no default zone.

## [0.5.12] - 2026-11-03

Every public name, default and number is the same as 0.5.11. (0.5.13 added `time_zone` after it
and is the last feature release.)

### Changed
- `docs/rules.md` states the freeze.

## [0.5.11] - 2026-11-03

Every public name, default and number is the same as 0.5.10.

### Changed
- A schedule, the requirements of a verdict and `gm.check` read the roles of a plant once per call
  instead of once per question: a study takes about 4% less CPU, `examples/hackathon.py` 89 s
  instead of 92 s, with the same output.

## [0.5.10] - 2026-11-03

An addition; every name, signature, default and number of 0.5.9 is unchanged.

### Added
- The time unit `ms` (millisecond): `gm.units` converts it like `s`, `min`, `h` and `d`, and it is
  a member of `gm.units.Unit`.

## [0.5.9] - 2026-11-03

Additions and one fix; every name, signature, default and number of 0.5.8 is unchanged
(`tests/fixtures/public_api_0_5_0.json` is the frozen surface).

### Added
- `gm.evaluate.missing(plant, case, results)`: every value of the economics the costs and the
  CO2 of a run need and the case lacks, at once, as `Issue`s of kind `missing` (the shape of
  `gm.case.missing`). Each cost still raises its first missing value.
- `gm.study.Search`: what `gm.study.minimize` returns, the same dict, now with `to_dict()` that
  gives the best and the whole history as plain JSON, so the progress of a search can be stored
  or shown.

### Fixed
- `gm.plants.capabilities()[class]["ranges"]` lists the leaves of every doublet the class may have
  (`params.d1.*`, `params.d2.*`), read at its largest size; it listed only `d0`. The shape is the
  same, and every range of the example plant files is now in the list.

## [0.5.8] - 2026-11-03

Every public name, default and number is the same as 0.5.7.

### Changed
- A trial takes about 14% less CPU time: the table of a run is built from its arrays in one
  step, and the energy balance reads its columns from the run instead of from a table copy.
  Every table and number is identical.

## [0.5.7] - 2026-11-03

Every public name, default and number is the same as 0.5.6.

### Changed
- A study runs faster: `examples/hackathon.py` takes 2:11 instead of 3:29 on the same machine, and
  prints the same output. The frame of a run is built without a `Series` per column, a balance and
  the bounds check read only the columns they need, and `named_modules` walks without nested
  generators. No number, name or signature changes.

## [0.5.6] - 2026-11-03

Every public name and default is the same as 0.5.5 (`tests/fixtures/public_api_0_5_0.json` is the
frozen surface). Numbers change on purpose where the two streams of a counterflow heat exchanger
have equal capacity rates: LCTS of the sample plants falls by at most 0.15%. No plant of the sample
changes rank or feasibility, and a search may end on another design.

### Fixed
- The split of the heat between the heat exchanger, the heat pump and the peak boiler no longer
  depends on the last bit of a calculation (known issue of 0.5.5). The cause was not the heat pump:
  `heat_transfer.effectiveness_counterflow` lost all its digits when the capacity ratio was within
  some bits of one, as on winter days when both streams of the exchanger carry the same flow, and
  gave for example 2/3 instead of 0.6885. It now tends smoothly to `NTU/(1+NTU)`. The numbers of
  those days change: a boiler heat of the sample plants by up to 3.3%, because they were wrong.
- `heat_transfer.logarithmic_mean`, and with it `lmtd` and the Lorenz mean temperature, lost its
  digits the same way for two values a few bits apart.

### Changed
- CI and the release workflow run NumPy with AVX-512 again.

## [0.5.5] - 2026-11-02

The first version published as a package. Every public name, default and number is the same as
0.5.4 (`tests/fixtures/public_api_0_5_0.json` is the frozen surface).

### Added
- Every new version on `dev` is published automatically: the wheel and the source archive on a
  GitHub Release, and the sandbox image as `ghcr.io/geomind-spe-geohackathon-2026/gemini-sandbox`.
  See `VERSIONING.md`.

### Fixed
- `pydantic>=2.10.0` is required; it was `>=2.5.0`, and below 2.10 `gm.study.sample` and
  `gm.study.sensitivity` with worker processes fail on a pickling error.
- `doc` of `describe` no longer depends on the Python version: 3.13 strips the indentation of a
  docstring and 3.11 and 3.12 did not, so the indentation is now always removed.
- `tests/unit/test_code_quality.py` needs `mccabe`, which is now in the `test` group.
- The compatibility tests no longer compare methods gemini inherits from Python or pydantic, whose
  signatures change with those versions, nor the call of an enum class. The frozen file is unchanged.

### Known issues
- On a few winter days of the sample plants the split of the heat between the heat pump and the
  peak boiler is not unique, so a change in the last bit of a calculation moves it. The same
  installation on the same CPU always gives the same numbers, but a CPU with AVX-512 can give others:
  LCTS moves by up to 0.13% on `HeatingPlant`, and the fuel of the boiler by more. This is not new in
  this version. CI runs NumPy without AVX-512 to stay on the expected numbers.

## [0.5.4] - 2026-11-02

Backward compatible with 0.5.3 and 0.5.0 for every number: all are the same to 1e-9 (`gm.study.sample`
and `gm.study.sensitivity` compared with 0.5.3 on the hackathon design, 369 numbers), and no example
verdict changes (`tests/fixtures/public_api_0_5_0.json` is the frozen surface). Two fixes change
behaviour on purpose, for inputs the 0.5.0 code accepted.

### Fixed
- `gm.evaluate.verdict`: a requirement that could not be judged (`passed` None) beside a passed one
  is now a reason of kind `requirement`, so the run is infeasible; it was feasible. It has no
  `violation`, so a search ranks as before. Not a reason: a `when="running"` requirement on a unit
  that never ran (nothing was asked), and the supply of a service already reported as not delivered.
  All undecided and failed-beside-undecided give the reasons of before. `report`, `compare` and
  `Study` read this verdict.
- `nominal_flow` of `Doublet` and `InjectionPump`: zero or below raises `out_of_bounds` (`gt=0`); it
  priced the pump as free or cheaper. Empty stays allowed.

### Added
- `gm.study.sample`: each item of `samples` has `feasible` (`gm.evaluate.verdict` of the draw; False
  for a run with failed steps). `gm.study.sensitivity`: each row has `feasible_low` and
  `feasible_high`. Both are in `to_dict` and read by `from_dict`, which also reads a 0.5.3 result
  without them. `summary`, `Tornado.to_frame` and the order of the rows are unchanged; each trial
  runs one more verdict.

## [0.5.3] - 2026-11-02

Backward compatible with 0.5.2 and 0.5.0: an addition only, every number is the same to 1e-9
(`tests/fixtures/public_api_0_5_0.json` is the frozen surface; the working snapshot gains the code
`deprecated`).

### Deprecated
- A `range` on a leaf of a case or economics file, series leaves included, is read and used by
  nothing. `case.check()`, `economics.check()`, `gm.check` and `Study.check` report it as an `Issue`
  of kind `deprecated` (code `deprecated`, a warning that comes last and stops nothing), and reading
  the case emits `gm.errors.GeminiWarning`. A search range belongs on the plant leaf; to move a case
  value use `uncertainty`; the `range` will be refused in a later version. Requirement `min`/`max`,
  `uncertainty` and a plant `range` are not affected.

### Added
- Schemas for forms: `Case.schema()` and `Economics.schema()` state `kind` as a constant (`"case"`,
  `"economics"`; the plant and study schemas already did), so a generated header is accepted by the
  reader (a document without `kind` is `old_format`). Leaves gain `x-quantity`, `x-units`,
  `x-limits` (SI bounds with their SI unit) and `x-fraction` (a share between 0 and 1); the files
  gain `x-quantities` (units of every quantity used). No existing key changed.
- `gm.evaluate.metrics()`: `title` and `objective` (a target for `gm.study.minimize`) per metric.
- `gm.study.kinds()`: `[{kind, use, title, description, settings}]` for run, minimize, sample,
  sensitivity and size (a preparation), `settings` the JSON Schema of the keys the kind reads.
- `units="display"` (or `"si"`) on `Results.get`, `summary`, `to_frame`, `to_dict`,
  `energy_report` and `Comparison.to_dict`; keyword-only `units="si"` on `gm.evaluate.capex`,
  `opex`, `annualised_cost`, `lcoh`, `lcoc`, `lcts`, `npv` and `payback`, whose value and parts
  then come in display units. The default is unchanged.
- `gm.case.missing(case)`: the paths a case or a partial case dict still lacks, as `Issue`s with
  quantity and accepted units; it never raises.
- `gm.plants.capabilities()[class]["ranges"]` lists every numeric leaf of `params` (and
  `size.doublets`), not only `params.depth`.
- `Issue.is_warning` and the issue kind and code `deprecated`; `raise_issues` leaves a warning out.

## [0.5.2] - 2026-11-02

Backward compatible with 0.5.1 and 0.5.0: additions only, every number is the same to 1e-9, and a
call that does not use them behaves as before (`tests/fixtures/public_api_0_5_0.json` is the
frozen surface).

### Added
- `on_progress=None` (keyword only) on `gm.study.minimize`, `sample`, `sensitivity` and
  `gm.Study.run`: `on_progress(done, total)` is called in the calling process after each finished
  trial, also with `processes=n` and for batched trials. Raising `gm.errors.Cancelled` from it stops
  the study cleanly (later trials do not start, the worker processes are stopped, the exception
  propagates).
- `gm.evaluate.daily_coverage(plant, case, results)`: for each day and service (heating, cooling) the
  demand and the energy from the geothermal plant, from the backup (roles `boiler`, `chp`) and short,
  as quantities in display units, with the failed steps of the day. Its sums are the totals of `gm.evaluate.totals`.
- `gm.evaluate.metrics()`: the metrics of a table of results with their quantity and display unit.

## [0.5.1] - 2026-11-02

Backward compatible with 0.5.0: no name, signature, key or code changed, and every number is the
same to 1e-9 (`tests/fixtures/public_api_0_5_0.json` is the frozen surface; the working snapshot
only changed its version).

### Added
- State connections (`connect(source, target, type="state")`): the target reads what the source
  outlet gave at the previous step; the plant keeps those values in its state under `@previous`.
  They are in the plant file as a connection of type `state` (no new key) and round-trip. This
  replaces the `NotImplementedYet` of the plan compiler.
- The page [Writing a module](.claude/docs/writing-a-module.md): a pump (stateless) and a
  controller (stateful), each alone and inside a plant.

### Changed (same numbers)
- Time is a scan: a stateful plant carries its state from step to step in one call over the whole
  run, eager (`ops.control.scan`) and compiled (a `scan` node of the graph); a year of hourly steps
  of a storage plant no longer runs one tick at a time.
- `minimize`, `sample` and `sensitivity` run their trials on one shared plant as one array pass
  instead of one run and one plant copy each; the first population of a search is one batch. The
  sequence of trials, the history and the ranking are those of 0.5.0.
- A module takes the fluid of its inlet stream (`ThermalStorage`, `InjectionReservoir`), so
  `gm.call` works on them with `state` and `dt`.

### Fixed
- `gm.check` never raises: a module with an unset parameter is reported once and its kind is not
  read, a case wrong by itself gives its own issues, and `case.check` names a value no file can
  hold.

## [0.5.0]

From 0.5.0 the public API is backward compatible (additions allowed if nothing breaks).

### Removed or moved (the last breaking change)
| Old | New |
| --- | --- |
| `gm.evaluate.run_all(plant, case, results)` returning `{passed, checks}` | `gm.evaluate.verdict(plant, case, results)` returning `{feasible, reasons}`; the checks are `energy_balance`, `mass_balance`, `bounds` and `requirements` |
| `gm.physics.control` (`pid_error`, `pid_derivative`, `pid_command`, `pid_integral_increment`, `anti_windup_increment`) | `gemini/modules/control/_physics.py`, private to `PIDController` |

Kept on purpose: `gm.evaluate.call_*` (they audit one `gm.call`) and `gm.ops` (the math API of
module authors). `gm.physics.diagnostics` stays: five modules call it from `health` and a module
may not import `engine`.

### Added
- `tests/fixtures/public_api_0_5_0.json`, `tests/unit/test_api_compatibility.py` and
  `tests/e2e/test_competition_surface.py`.

### Also in 0.5.0 (written under "Unreleased" before the freeze)
**Added**
- `gm.call(..., state=, dt=)`: a module with state takes the state at the start and the step, and
  the result has the key `state` with the state at the end of the step.
- The quantity `gas_burned` (kg/s) of the role `plant`: the co-produced gas burned by the boilers
  and flares of the plant, so a requirement can limit it.

**Changed**
- Module contract: `forward(self, inputs, inlets, state)` is pure (it reads parameters on `self`
  and nothing else, writes nothing, returns `(outputs, outlets)`) and a stateful module has a pure
  `update(self, inputs, inlets, outlets, state, dt)` that returns the next state. A state has no
  default: it comes from `case.initial_state`. A stateful plant is stepped from
  `case.initial_state`.
- Hooks: a pre-hook is called `(module, inputs, inlets, state)` and a forward hook
  `(module, inputs, inlets, state, outputs, outlets)`; a hook that returns a mapping replaces the
  controls and boundaries (pre-hook) or the outputs (forward hook) of that call, `None` observes.
- `gm.simulate` and the engine: a physical failure of a step (`invalid_inlet`, `out_of_bounds`,
  `out_of_range`, `no_convergence`) is a failed row whatever `on_error` says, and the run finishes;
  every other failure follows `on_error`. A trial of a search whose plant fails a step is
  infeasible (violation 1e6) instead of raising, and a NaN value counts as the largest violation.
- `gm.call(module, parameters, inlets, controls, units, ...)`: `units` is required and is `"si"`
  (plain `{value, unit}` in SI) or `"display"` (`Quantity` in the display units of the report);
  the map `{quantity: unit}` is no longer taken by `gm.call`.
- `Best.to_dict()`, `Sample.to_dict()`, the history of a search and the notes of `gm.study.size`
  show the display units of the report instead of bare SI; `from_dict` reads them back.
- `gm.runtime.settings(default_fluid=...)` and `gm.runtime.state()["default_fluid"]` are removed: the
  fluid is a case input (`site.fluid`) or an entry of the plant `fluids`. A module or a `Stream`
  without a fluid raises `missing_value` naming its path; `gm.Stream(...)` requires `fluid`.

## [0.4.0] - 2026-11-02

Breaking: the folders of `gemini/` are grouped by job (rules and tree in
[structure.md](.claude/docs/structure.md)). Moves only; numbers equal to 1e-9; no old path is kept.

### Changed
- `gm.data.from_csv`, `from_values`, `profile_schema` are `gm.case.from_csv`, `from_values`,
  `profile_schema`; `gm.data` is gone.
- `gm.analysis.calibrate` and `CalibrationResult` are `gm.study.calibrate` and `CalibrationResult`.
- `gm.case.roles()` is `gm.plants.roles()`.
- `gm.modules.collect_flows`, `emissions`, `energy_balance`, `mass_balance` are
  `gm.evaluate.collect_flows`, `call_emissions`, `call_energy_balance`, `call_mass_balance`.
- `gm.streams` joins `gm.__all__`.
- `gm.evaluate` is grouped by job (`costs`, `emissions`, `balances`, `verdict`, `summary`,
  `report`); every function is still `gm.evaluate.<name>`.
- `gm.physics.dispatch`, `gm.physics.doublet` and `gm.physics.costs` are removed from the
  namespace; `circuit_flow` and `temperature_after` are in `gm.physics.energy`.
- Sample projects are `examples/<name>/` (were `inputs/examples/<name>/`); the data the tests read
  is in `tests/fixtures/` (was `inputs/`, now removed).

## [0.3.0] - 2026-11-02

Breaking: the inputs of a project are separated by owner and every public entry point follows the
new model (rules and reasons in [inputs.md](.claude/docs/inputs.md)). A checkpoint of 0.2.0, a plant
file of `format: 2` and a `case.json` of the old shape do not load: they raise `old_format` naming the
new form. Nothing of the old names is aliased.

### Changed
- Four files, one owner each: `case.json` (`site`, `demand`, `utilities`, `economics`,
  `requirements`, `time`, `initial_state`), `economics.json`, a plant file (`kind: plant`, `format: 1`)
  and an optional `study.json`; every leaf is `{"value", "unit"}` with optional `range`, `options`,
  `uncertainty`; a series is a CSV whose first column is `time`.
- `gm.check(plant, case)` runs first in `simulate` and every study function; `gm.Study` runs
  `study.json`; the verdict (`gm.evaluate.verdict`) is the one answer to feasibility.
- Python signatures are `(plant, case, ...)` and the remaining arguments are method settings only
  (`objective`, `evaluations`, `seed`, `metrics`, `samples`): the economics file owns the discount
  rate and the analysis period, the plant owns `backup`, the case owns the requirements.
- `gm.plants.capabilities()` reports the leaves that may state a `range` (`ranges`), the cost parts
  `lifetime_years` are `analysis_period`, `gm.plants.schema()` and `gm.Case.schema()` are the file
  forms, and `docs/schemas/` holds `case`, `economics`, `plant` and `study`.
- The version of a checkpoint is 0.3.0 or later; `precision`, `processes` and `compile` stay runtime
  settings and a test keeps the last two from changing a number (1e-9).

### Removed
- With no alias: `gm.case.Choices`, `Constraint`, `Assumptions`, `Finance` and the sections under
  them, `gm.evaluate.constraints`, `gm.plants.validate`, `Module.missing_parameters`, the pydantic
  methods of `gm.Case`, the `constraints` argument of `gm.study.minimize`, the `discount_rate` and
  `lifetime` arguments of the costs, `time_column` of `gm.data.from_csv`, `backup` of
  `gm.study.size`, `docs/schemas/plant_dict.*`.

### Every changed name, old and new

#### Signatures

| Old (0.2.0) | New (0.3.0) |
| --- | --- |
| `gm.evaluate.lcoh`, `lcoc`, `lcts`, `annualised_cost`, `npv` `(plant, case, results, discount_rate=None, lifetime=None, on_error="raise")` | `(plant, case, results, on_error="raise")`: `economics.discount_rate` and `economics.analysis_period` of the case are the only source |
| `gm.study.minimize(plant, case, objective, variables=None, constraints=None, evaluations=100, *, plan=None)` | `gm.study.minimize(plant, case, objective, evaluations, seed, *, plan=None)`: `variables` is the `range` and `options` leaves of the plant, `constraints` is the `requirements` of the case (nothing real needed the argument), `evaluations` and `seed` have no default; the result has no `fixed` |
| `gm.study.sample(plant, case, metrics, count, seed, *, plan=None)` | `gm.study.sample(plant, case, metrics, samples, seed, *, plan=None)` |
| `gm.study.size(plant, case, backup=None)` | `gm.study.size(plant, case)`: the policy is `params.backup` of the plant |
| `gm.data.from_csv(path, columns, unit, time_column=None)` | `gm.data.from_csv(path, columns, unit)`: the first column is named `time` |
| `gm.Case.from_dict(data, folder=None)` | `gm.Case.from_dict(data, files=None, folder=None)`: series and economics from `files` (`{name: bytes}`), else from `folder` |
| (none) | `gm.case.Economics.from_dict(data, files=None, time=None)`, `from_json(path, time=None)`, `to_json`, `check`, `schema`, `drilling_cost_per_metre(length)`: the file `economics.json`, held as `case.economics` |
| `gm.Case(*, time, environment=None, demand=None, choices=None, constraints=None, assumptions=None, uncertainty=None)` | `gm.Case(**found)`, built by `from_dict` or `from_json`; no pydantic methods (`model_dump`, `model_copy`, `copy`, `json`, ...): `to_dict`, `with_value` |
| `gm.Plant.to_json(path)` | `gm.Plant.to_json(path, structure=False)` |
| `gm.case.Range(min=None, max=None, *, unit=None)`; `gm.case.Uncertainty(*, kind, min, max, std)`; `gm.case.Time(*, start, end, step)` | `Range(min=None, max=None)` (the bounds are in the unit of the leaf); `Uncertainty(kind, min=None, max=None, std=None)`; `Time.from_dict({...})` |
| `gm.modules.Boundary(type, *, default=UNSET, description=None, **bounds)` | `gm.modules.Boundary(type, *, case=None, **kwargs)`: a boundary that the case owns names its path |
| `gm.case.Constraint(*, on, quantity, over='each', when='always', min=None, max=None, equals=None)` | `gm.case.Requirement` `(name, on, quantity, over?, when?, min, max)`, built by `Requirement.from_dict`; `equals` is `min` = `max`; `over` is absent for a window quantity |
| `gm.case.Environment(ground, reservoir, fluid, air)`; `Fluid(gas=)`; `Air(temperature)` | `gm.case.Site(ground, reservoir, fluid, air)`; `Fluid.dissolved_gas`; `Air(temperature, relative_humidity, pressure)` |
| `gm.case.Demand(file, time_column, heating, cooling)`; `Service(column, unit, supply_temperature, return_temperature)` | `gm.case.Demand(heating, cooling)`; `Service`, `CoolingService`: `power` (a series), the supply and return conditions of the consumer |
| `gm.case.Assumptions(finance, emissions)`, `Finance`, `Allocation`, `Emissions`, `CO2`, `CH4`, `Capex`, `Opex(fixed, electricity, gas, chemical, waste_disposal, co2)`, `Revenue(heat, cold)` | `gm.case.Economics` with `Capex`, `Opex(fixed, variable)`, `Energy`, `Carbon`, `Revenue(heat, cold, subsidy)`, `Subsidy`, `Accounting`, `Gwp`, `DepthTable`; `gm.case.Utilities` with `Electricity`, `Gas` |
| `gm.case.Choices(doublets, depth)` | removed: a `range` on `size.doublets` and `params.depth` of the plant file (`plant.set_range`) |
| `gm.evaluate.constraints` | `gm.evaluate.requirements` (the same arguments); new `gm.evaluate.verdict` |
| `gm.plants.validate(data, on_error="raise")`; `Module.missing_parameters()`, `Plant.missing_parameters()` | `plant.check()` (a list of issues, never raises); `Plant.from_dict` raises the same issues |
| (none) | new: `gm.Study`, `gm.check(plant, case)`, `gm.study.Study`, `StudyResult`, `Run`; `Case.check`, `files`, `field`, `leaf`, `with_value`; `Plant.check`, `set_range`, `set_options`, `ranges`, `options`, `size`; `Study.from_dict(data, files=None, folder=None)`, `from_json`, `run(plants=None)`, `check`, `to_dict`, `to_json`, `schema` |

#### Return shapes and files

| Old (0.2.0) | New (0.3.0) |
| --- | --- |
| `gm.plants.capabilities()[class]["choices"]` (`["doublets", "depth"]`) | `["ranges"]` (`["size.doublets", "params.depth"]`): the leaves of the plant file that may state a `range` |
| cost parts `lifetime_years` of `lcoh`, `lcoc`, `annualised_cost`, `npv` | `analysis_period` (in yr) |
| `report["constraints"]` | `report["requirements"]` and `report["verdict"]`; `compare` reads the verdict |
| result of `minimize` `{best, feasible, fixed, history, evaluations}` | `{best, feasible, history, evaluations}` |
| `docs/schemas/plant_dict.*` | `docs/schemas/plant.*`; new `study.*`; `case.*` and `economics.*` regenerated |
| plant dict `format: 2` without `kind`; keys `inputs`, `bindings`, flat dotted `params` | plant file `format: 1`, `kind: plant`; `params` a tree of leaf objects; a control is a leaf; `bindings` stay in memory; the key `inputs` is refused |
| `case.json` keys `environment`, `constraints`, `assumptions`, `choices`, `demand.file`, `time_column` | `site`, `requirements`, `economics` (a file), `utilities`, ranges in the plant, a series leaf with a `time` column: the old keys are refused with `old_format` |
| checkpoints written by 0.2.0 | refused with `old_format` (they hold a plant of `format: 2`) |

### Also in 0.3.0: the study and correctness work that was unreleased before the inputs task

#### Changed
- The plant file is `kind: plant`, `format: 1`: `type` or `modules` and `connections`, `size` beside
  `params`, `params` a tree of leaf objects `{value, unit, range, options, history}`; the keys `inputs`
  and `bindings` are gone (a control is a leaf, bindings are set in memory). A file of `format: 2`
  without `kind` raises `old_format`. `Plant.ranges`, `options`, `set_range`, `set_options`, `size`,
  `check`; `Module.check` replaces `missing_parameters`; `gm.plants.validate` is removed.

#### Removed
- `gm.Plant.from_legacy`, `gemini.data.legacy`, `gemini/plants/_utils/legacy/`, `paths.legacy_project`
  and `Plant.validate`: the package reads no old project. Use
  `gm.plants.validate(plant.to_dict(structure=True))`. The old-project reader the tests still need
  is `scripts/legacy/`.

#### Changed
- `gm.Case` and the folder `gm.case` replace `gm.Problem`, `gm.Constraint` and `gm.Assumptions`:
  fixed sections in a `case.json`, SI storage, no default for anything a user must decide. Every
  call takes `(plant, case)`, plus `results` when it reads a run. The plant dict holds only the
  plant.
- One unit format: a `Quantity` or `{"value", "unit"}`; unit text is refused and `gm.units.parse`
  is removed.
- `gm.study.minimize` respects the case: a trial is feasible when no step fails and every constraint
  of the case passes; the result has `feasible` and `fixed`, a `history` item its `reason` and
  `parts["violation"]`. `gm.study.size` gives a heat pump the part of the peak the reservoir cannot
  reach. `compare` entries have `feasible` and `reasons`; `to_frame(units=None)` of `compare` and
  `sensitivity` shows display units.
- `gm.optim` is `gm.study`; `gm.types.Cost` is removed, equipment declares `capex(finance)` and
  `fixed_opex(finance)` for its kind; `examples/` holds five flat scripts.
- `gm.study.size(plant, case, backup)`: the policy of the top-up units (`"none"` or `"peak"`) has no
  default; rated units carry the largest duty the case allows; the sized plant is simulated once
  and `plant.sizing` lists what it breaks. `gm.study.sample(plant, case, metrics, count, seed)` and
  `sensitivity(plant, case, metrics)` read the `uncertainty` the case declares; the `distributions`
  and `parameters` arguments are gone. `Comparison` values are `Quantity`; `report.to_dict` and
  `str(report)` show display units. A well's `pipe_path` is four `section_*` lists. An `ESP` row
  outside its curve or over its speed-scaled maximum flow fails with `out_of_range`; a failed step makes a study trial infeasible (metrics `None`), and `sample` counts `failed`; an `InjectionPump` below its suction does not pump.
- Removed, with no alias: `gm.plants.example` (read a plant with `gm.Plant.from_json` or build the
  class), `gm.data.synthesize`, `gm.analysis.injectivity`, `calibrate_pump`, `calibrate_corrosion`,
  `erosion`. The old -> new table is in [api.md](.claude/docs/api.md).

#### Added
- `uncertainty` next to a number of the case and `gm.case.Uncertainty`; `plant.missing_parameters()`
  and an error that lists every missing value with its meaning; `gm.evaluate.failures`; `to_dict()`
  and `from_dict` of every study result; `gm.runtime.settings(processes=n)` for parallel trials, with
  one compiled graph per study.
- Variables `<role>.<parameter>` for `minimize`; `report["services"]`; `InjectionPump.nominal_flow`
  and `nominal_head`, priced as `injection_pump`; cited prices in the hackathon case.
- `gm.evaluate.capacities`, `report` and `compare`; `gm.study.size` and `sensitivity`;
  `gm.plants.capabilities`; costs on every equipment kind; the hackathon example from case to
  compared designs.

The full list, with the removed names, is the change log of [api.md](.claude/docs/api.md).

## [0.2.0] - 2026-10-31

The API for the hackathon: see the change log of [api.md](.claude/docs/api.md). Checkpoints written
before 0.2.0 do not load; `gm.plants.migrate` converts a plant file of an older version.

### Changed
- Fluids: `density` and `viscosity` replace `liquid_density` and `liquid_viscosity`; reservoirs read
  their fluid.
- Plants: an unconnected port is an error, and the automatic plant ports are gone.
- Boilers and CHP burn from `fuel_in`; `ElectricBoiler` replaces `Boiler(fuel_type="electric")`.
- Economics: `co2` sums `co2_emission` and `methane_emission`; `gas_price` and `methane_gwp` replace
  `fuel_price` and `fuel_emission_factor`; a missing assumption has the code `missing_assumption`.

### Added
- `gm.data.get` with the demand of 2027; `gm.plants.Doublet`, designed from its depth;
  `GasGrid`, `GasMakeup`, `Flare`, `ElectricBoiler`; `Fluid.gas_liquid_ratio`, `gas_composition` and
  `kind="gas"`; `gm.schedule`; `gm.evaluate.Limits` and `gm.evaluate.limits`; `capex(assumptions)` on
  equipment with sourced cost factors.

### Fixed
- Wells: the two-phase gas superficial velocity follows the gas mass flow.

## [0.1.0] - 2026-10-30

First consistent API: see the change log of [api.md](.claude/docs/api.md). The version restarts at
0.1.0 from one source, `pyproject.toml`, and `gm.API_VERSION` is removed; the integer versions
below are the history before it. Checkpoints and results files written before 0.1.0 do not load.

### Changed
- Runs: `on_error` is `"raise"` by default, on the run functions and on `gm.Engine`.
- Returns: every public return is a value, a problem or a check, built by `gemini.types.shapes`,
  with a JSON Schema each in `docs/schemas/`; a number travels with its unit and `units` maps are
  gone. `Results.energy_report` is a dict and `to_frame(table="energy")` its table.
- Errors: seven error classes and `GeminiWarning`; what the others meant is a `code`. Every public call raises by
  default and `on_error="record"` reports instead. `error.problems` carries every problem.
- Parameters and bindings: `add(kind, name=None, params=None)`, flat `set_bindings` and plant files.
- `gm.evaluate` is a namespace of `compute` and `names`; `gm.evaluate.co2` takes `(plant, results)`.

### Added
- `units`, a map from quantity to unit, on every view of `Results`, on `gm.evaluate` and on
  `gm.analysis`.

The package was rebuilt as composable modules with handwritten plants, in-memory data and one
finite engine, and then cleaned up. Old import paths are not retained.

### Added
- Run functions `gm.simulate`, `gm.replay`, `gm.live` and `gm.resume` over the public `gm.Engine`,
  with `checkpoint` and `checkpoint_every` on `simulate` and `replay`. The plant holds its traced
  graphs, so repeated calls on one plant trace it once (`gm.API_VERSION = 5`).
- The public API is frozen at `gm.API_VERSION = 1` ([api.md](.claude/docs/api.md)). New: the plant
  builder `gm.Plant` and the JSON plant spec (format 2, `gm.plants.from_spec`, `validate`,
  `spec_schema`, `migrate`, `from_template`, `example`); `describe`, `parameter_schema`,
  `validate_params`; one registry with categories and stream types; `gm.evaluate`; `gm.analysis`,
  `gm.evaluate`, `gm.evaluate`, `gm.evaluate`, `gm.testing`, `gm.data`; `gm.errors` codes and
  `to_dict`; JSON Schemas and samples in `docs/schemas/`.
- Physics and leaf modules are written with `gemini.ops`, so one source runs on floats, arrays and
  traced graphs, and `Engine.replay` evaluates each twin as one traced call with identical results.
  `gemini.compiler.graph.settings(traced=False)` selects the old tick-by-tick path.
- Composable `Module` equipment with declared parameters, ports, controls, boundaries and
  outputs, the handwritten `Doublet` plant and the example `DoubletHeatPlant`, portable plant
  JSON with dated parameters and bindings, and the `gm.plants.convert_legacy` bridge from old GEMINI projects.
- `Engine.simulate`, `Engine.replay` and `Engine.live` with callbacks, results, checkpoints and
  resume; bounded calibration through replay; quantity declarations, immutable fluids, profiles,
  costs and mass/energy audits. Eight runnable examples under `examples/`.
- Leaf packages `gemini._utils` (shared string, time, hook, mapping, context and file helpers;
  `python -m gemini._utils.collect_env`) and `gemini.errors` (every error class, also deriving
  from the matching built-in exception, as `gm.errors`).
- Development and release test profiles: `make test` runs `scripts/test_changed.py` on what
  changed and what imports it within a 300 s budget, `make test-release` runs every tier on the
  full-year data; CI runs the development profile on feature branches and the release profile
  for `main`.
- Quality gates: `tests/unit/test_code_quality.py` (comments, nesting, function length,
  framework name), flake8 `max-complexity = 10` without ignoring bare `except`, the package
  boundary test and mirror tests for every source file.
- Equipment classes in `gm.modules`, each described in `.claude/docs/equipment.md`:
  - pumps `CentrifugalPump`, `LineShaftPump`, `GasCompressor`;
  - piping `Pipe`, `Valve`, `Splitter`, `Mixer`, `PressurizationTank`;
  - treatment `Desander`, `InhibitorDosing`, `Vent`;
  - heat `HeatPump`, `AbsorptionUnit`, `AdsorptionChiller`, `CHP`, `Cooler`;
  - subsurface `ThermalDecline`, `AquiferStorage`, `BoreholeField`, `DownholeHeatExchanger`;
  - storage `ThermalStorage`, `IceStorage`; control `PIDController`;
  - power `ORC`, `Separator`, `FlashTurbine`, `GridConnection`;
  - demand `HeatConsumer`, `CoolingConsumer`.
- Composite plants in `gm.plants`: `MultiWellPlant`, `HeatingSubstation`, `CoolingSubstation`,
  `DistrictNetwork` (heating or cooling) and `ATESPlant`, with the example
  `examples/cases/district_heating_cooling.py`; `Module.trial_outlets` and
  `Module.start_states` for loops closed within one call.
- Physics modules `compression`, `refrigeration`, `steam` (IAPWS-IF97), `ground` and
  `psychrometrics`.
- `State(kind, default=...)` declarations with `_advance_states(inlets, outlets, dt)`: any module
  steps with `module.step(state, dt, inlets)`, and a composite steps every stateful descendant
  through its own `forward`, without a hand-written step method.
- Energy-balance terms beyond `electricity`, `fuel` and `heat_loss`: `heat_absorbed`,
  `heat_supplied`, `electricity_generated` and the signed stored-heat rate `heat_accumulation`
  (`ENERGY_INPUTS` and `ENERGY_OUTPUTS` in `gemini/modules/balance.py`).
- Quantities `Elevation`, `MassConcentration`, `MoneyRate`, `LinearThermalResistance`,
  `TemperatureGradient`, `Speed`, `Mass`, `SpecificEnthalpy`, `HeatCapacity`,
  `VolumetricHeatCapacity`, `ThermalDiffusivity` and `LinearPower`; units `g/m3`, `mg/l`, `ppm`,
  `currency/s`, `currency/h`, `m.K/W`, `K/m`, `K/km`, `kJ/kg`, `kWh/K`, `MJ/m3/K`, `t` and
  `m3/h/bar^0.5`; the `Fluid` kind `"steam"` and the `STEAM` constant.
- `Degasser.separation_efficiency` (default 0, which keeps the former results).
- Python 3.12, 3.13 and 3.14 support (was 3.11 only). The Test workflow runs its profile on each
  of them with the newest dependencies and on 3.11 and 3.14 with the declared lower bounds
  (`uv pip install --resolution lowest-direct`); free-threaded 3.14t and the 3.15 beta run as
  non-blocking jobs, and a manual run (`workflow_dispatch`) runs the release profile on any
  branch. CI installs with uv; `poetry install` still works.

### Changed
- `gm.API_VERSION = 2`: one classification. A module's `category` is the folder that holds it, the
  class attribute is gone, `heat/` became `exchangers/`, `heating/` and `cooling/`, the wells moved
  to `wells/` and `AquiferStorage` to `storage/`. The old to new names are in the change log of
  [api.md](.claude/docs/api.md).
- `gm.Engine(plant, ...)` owns its plant: `engine.simulate(profile)`, `engine.replay(data)`,
  `engine.live(source)`. `Results` are JSON views and `.npz` files, `to_frame()` has `path.field`
  columns, the old `summary()` is `energy_report()`, and the `parquet` extra is gone. Plant files are
  format 2; `gm.plants.migrate` converts older ones. `Doublet`, `MultiWellPlant`, `DistrictNetwork`
  and `DoubletHeatPlant` are specs, no longer classes.
- The `Module` base class is explicit: modules are built without arguments and configured with
  `update_params`, which returns the module; there is no class registry or `__init__` wrapping;
  the values of one call live in a single `_Call` context record; `fluid` is a validated
  property; plant files and checkpoints import classes only through `class_path`/`import_class`.
- Declaration listings recurse by default and key results by dotted path; `inlets()` and
  `outlets()` list the module's own ports. `health(result, measured)` receives the call's
  `ModuleResult`; `load_state_dict` takes `strict`; `has_input_value` and
  `clear_param_overrides` were added.
- Ports and controls follow one naming rule: `ProductionReservoir.production_rate` (was `m_dot`),
  `DoubletHeatPlant.secondary_in` (was `secondary`, also in `plant.json` and the data columns),
  `Doublet.return_in`/`supply_out` (were `return_stream`/`supply`) and
  `Boiler.temperature_setpoint` (was `setpoint_T`). `MissingMeasurement` became
  `gm.errors.MissingMeasurementError`, and costs are summed by
  `gemini.types.cost.total_cost(plant)` over modules that define `capex()`.
- Physics consists of plain functions with one unit table; `ConstantWater` became
  `FluidProperties`, and `Profile.constant(value, unit=, clock=)` is the only constant form.
- Runtime settings are context-local; ESP efficiency is a fraction; undefined radial
  diagnostics are reported as unavailable.
- `Blowdown` is a bleed split: `feed_in` -> `retained_out`, `blowdown_out` under the
  `blowdown_fraction` control (was a pass-through `inlet` -> `outlet` with a `modelled`
  output). `FlowCoefficient` allows zero, so a closed valve reports it.
- Dependencies are version ranges instead of exact pins: pandas >= 2.2.2, including pandas 3;
  scipy >= 1.13.0; numpy >= 2.0.0; pydantic >= 2.5.0; pytz >= 2020.1 (>= 2023.4 on Python
  3.12+); the `parquet` extra's pyarrow >= 16.0.0. On Python 3.13 and 3.14 the floors rise to
  the first releases with wheels for them (for example numpy >= 2.3.2 on 3.14). Package metadata
  is in the PEP 621 `[project]` table.
- Development tools are PEP 735 dependency groups (`test`, `lint`, `docs` and `dev` with all
  three): pytest 9.2.0, pytest-xdist 3.8, flake8 7.5.0, Flake8-pyproject 1.2.4, black 26.10.1,
  isort 9.0.2, sphinx-rtd-theme 3.1.0 and Sphinx 9.2.0 (9.1.1 on Python 3.12 and 9.0.4 on 3.11,
  the last releases for them).
  Under pandas 3, results have a microsecond time index and `str` text columns, ambiguous local
  times raise `ValueError` instead of pytz's `AmbiguousTimeError`, and CSV decimals parse
  correctly rounded, which moves replays of the example data by up to 1.7e-13 relative (see
  `.claude/docs/refactor-notes.md`).

### Removed
- `plant.simulate(profile)`: use `gm.simulate(plant, profile)`.
- `gm.modules.list/get/create`, the module catalogue and engine registry, `Sequential`,
  `fidelity`, `apply`, `column_units`, `last_result(s)`, `Module.cost`, keyword-value
  construction, `runtime.dtype` and `runtime.manual_seed`, `gemini.design`, `gemini.agentic`, the
  legacy `nodes=` options and `plant.legacy_info`, `Results.save_csv/save_parquet`,
  `Dataset.frame/describe/reopen`, `Progress`, `AlarmCollector` and `Output(optional=)`.
- `BoosterPump` (a pass-through placeholder with `modelled=False`); use `CentrifugalPump`.
- The Flask interface, application/UI workflows, container stack, platform launcher scripts and
  UI-only dependencies.

### Fixed
- Engine: resume gives the same results as an uninterrupted run; daily clocks follow local
  midnight across DST; offset timestamps load across DST switches; the event log no longer turns
  NaN into errors and always removes its hooks; live runs anchor their grid at the committed
  position, reuse the checkpointed step for single rows and keep the caller's plant and error
  policy; NumPy integer durations are seconds; text time axes are accepted.
- Modules: redefining a module class or reusing a built-in class name no longer fails; assigned
  fluids are kept; slicing a `ModuleList` no longer re-paths its children; `UNSET` keeps its
  identity under copy and pickling.
- Physics: differences convert without unit offsets; the Beggs–Brill map covers its exact
  regime boundaries; two-phase reverse flow uses mirrored friction; zero flow, zero CO2, NaN and
  out-of-range inputs raise `PhysicsRangeError` instead of crashing; `Stream(flow="10")` raises
  `UnitError`.
- Legacy: conversion reads the in-memory project; `write_csv` writes midnight timestamps;
  calibration tolerates a NaN duty row; the t/h ESP head guess is correct; `check_wiring` works
  on a copy; `barg` converts from SI correctly; an ambiguous data CSV and unknown runtime keys
  raise explicit errors; mixed timestamp spellings parse.
- Data: replay, simulation and clocks work with timestamp indexes of any resolution (s, ms, us,
  ns). Under pandas 3, which parses text times as microseconds, the loader compared them with
  nanosecond tick values, so every tick looked like a gap and replay silently skipped every twin;
  `native_step` and clock durations were also 1000 times too short.
- Clocks: daily `Clock.days`/`Clock.year` steps follow local midnight across DST under pandas 3,
  which reads a `Timedelta` frequency as a fixed 24 hours.

## [1.0.3] - 2026-10-13
### Added
- parameters and tag names of the original doublet example using CSV data
### Fixed
- fix influxdb writing data float

## [1.0.2] - 2026-10-12
### Fixed
- fix grafana reverse-proxy authentication inside iframe

## [1.0.1] - 2026-08-20
### Fixed
- add python-dotenv package to pyproject.toml
### Changed
- more info for setting up environment variables in documentation
- change naming environment variables of OLLAMA and CHROMADB


## [1.0.0] - 2026-07-19

### Added
- Initial open-source release of the GEMINI Geothermal Suite.
- Initial release of the GEMINI Geothermal Model.
- Initial release of the GEMINI Geothermal Framework.
- Initial release of the GEMINI Geothermal Application.
  - Diagram Builder Application
  - ESP Monitoring Application
  - Productivity Application
  - Injectivity Application
  - Well Schematic Application
  - Well Integrity Monitoring Application
  - Time-series Visualization Application
  - Report Generation Application
  - Chatbot Application
- Initial release of the GEMINI Geothermal Interface.
