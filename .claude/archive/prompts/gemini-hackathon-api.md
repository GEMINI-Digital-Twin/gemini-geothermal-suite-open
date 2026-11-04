# Task: Hackathon API: demand data, gas chain, doublet from depth, schedule, limits, costs

## 0. Context and rules

- The hackathon inputs are out (2026-10-29): daily heating and cooling demand for 2027, a fixed reservoir, brine with co-produced gas, and hard limits. The agent (geomind) must design a 1 to 3 doublet heating-and-cooling plant with gemini. This task gives gemini every public name that design needs, implemented where it is plain, `NotImplementedYet` with the final signature where it is not. The decisions below were made with me one by one; follow them, and where one does not fit the code, stop and say why in the report instead of inventing another design.
- The inputs, for reference and for the example: `/Users/sahand/Desktop/crust-team/inputs/` holds `GEMINI_Heating_Demand_Daily_2027.csv` (`date,heating_demand_MWth`), `GEMINI_Cooling_Demand_Daily_2027.csv` (`date,cooling_demand_MWcool`) and `GEMINI_Hackathon_Challenge_Requirements.pdf`. Read the PDF. If the folder is missing, stop and ask me for it.
- Key figures: 365 daily averages; heating peak 30.0 MWth (2027-01-28), 111.67 GWh/yr; cooling peak 10.0 MWcool (2027-07-19), 23.74 GWh/yr. Reservoir midpoint 2,500 m TVD, 100 m thick, 30 °C/km, surface 12 °C (so about 87 °C), 250 bar(g) (hydrostatic for other depths), 200 mD. Brine 1,030 kg/m³, 0.40 mPa·s, gas-liquid ratio 0.8 Nm³/m³ (0 °C, 1.01325 bar a), gas 80 mol% CH₄, 20 mol% CO₂. Limits: 1–3 doublets, 50–300 m³/h per active doublet, brine cooling at most 40 K, pump efficiency 70 %, production equals injection volume, supply 100 °C heating and 20 °C cooling.
- The upstream `development` branch (`GEMINI-Digital-Twin/gemini-geothermal-suite-open`, last merge 2026-10-29) is the reference the organisers name. It models the co-produced gas chain: a separator with `gas_water_ratio`, and a gas boiler and CHP that burn co-produced and grid gas and report CO₂. Read its `src/gemini_model/{separator,boiler,chp}` and `src/gemini_simulator/` for intent and cited constants; rebuild in our architecture, never copy its structure.
- Start from the current local `refactor`, with the API-cleanup commits (version 0.1.0) in. Read `AGENTS.md` and every file in `.claude/docs/` and follow them.
- **Standing rules:** no concept has two implementations; behaviour is identical on every backend; physics only in `gemini/physics/`, modules declare and wire and call physics; every numeric default has a cited source in its docstring, or no default.
- Work directly on branch `refactor` (no new branch, no PR). One commit per section below, in order. **Do not push** until I have reviewed the commits.
- **Pre-check:** `git status` is clean on `refactor`, and no other Claude session or process is working **inside `gemini/`**. Sessions in other folders do not block you. If their load makes a 1 s budget test fail, rerun that test alone before treating it as a failure, and say which tests you retimed.
- Workspace `/Users/sahand/Desktop/crust-team`. Change **only** `gemini/`. You may read `geomind/` and `backend/`, never change them.
- Temporary files go to `.tmp/hackathon-api/` (git-ignored).
- One agent is enough. Subagents, if any, run on a lighter model and only for read-only searches.
- **Tests:** development profile only (`make test` / `scripts/test_changed.py`, always including `test_code_quality.py`), in parallel, under 300 s; plus the e2e tier and all numbered examples once at the end against a baseline taken before the first change. Existing numbers stay identical except where a section below changes the physics on purpose (the gas chain, the two-phase well check); list every changed number with its reason. Never run the slow dataset locally. Never delete or shrink existing tests, datasets or goldens.
- **Quality bar** as in `.claude/docs/conventions.md`: simple, readable, just enough code; nesting at most 3; functions about 40 lines at most; guard clauses; explicit `gm.errors` with the agreed codes; no comments inside code (docstrings only); black, isort and flake8 clean.
- If something else is needed, say so in the report.

## 1. Demand profiles

- `gm.profiles.get("heating_demand")` and `gm.profiles.get("cooling_demand")` return the two hackathon profiles: a UTC daily DataFrame of 365 rows (2027-01-01 to 2027-12-31), one column each (`heating_demand` in W, `cooling_demand` in W, units in `attrs["units"]`), with the source file named in `attrs`.
- Ship the two organiser CSV files unchanged as package data in `gemini/profiles/data/` (data, not a JSON schema or plant file) and read them; the name, unit, description and source of each profile live in Python in `profiles/library.py`. If `profile_schema()` only describes the old JSON layout, make it describe what `get` returns and say what you changed.
- Test the key figures above (peak values and dates, annual energies to 0.01 GWh).

## 2. No dangling ports

- Every inlet and outlet of every module in a plant is connected to another module or to an explicitly named plant port. An unconnected port is an error: `p.validate()`, `gm.plants.validate` and `from_dict` report it with code `unconnected_port` and the port path.
- Plant ports exist only when named: `p.connect("heating_return", "hx.cold_in")` (a bare word is a plant port) or the `inlets` / `outlets` of a plant dict. The automatic `<path>_<port>` plant ports are removed.
- Update every shipped plant, example and test plant to name its boundary ports. List the ports you had to name.

## 3. A module may set its children's values

- A composite module may derive its children's parameters from its own: it overrides `set_params`, computes the child values with functions from `gemini/physics/`, and calls `super().set_params` with them. Document the pattern in `modules.md`.
- Every route that sets parameters goes through `set_params`: `add(..., params=)`, `from_dict`, dated `set_params(..., valid_from=)` and `param_history`. Find any route that bypasses it and fix it.
- An explicit child value in the same call wins over the derived one (`{"depth": "3000 m", "producer.well.pipe_path": [...]}` keeps the given pipe path).
- `to_dict` stores the module's own parameters and the explicit child values only, never derived values, so `from_dict(p.to_dict())` rebuilds the same plant with the same numbers.

## 4. Fluid

```python
brine = gm.Fluid(density="1030 kg/m3", viscosity="0.4 mPa*s",
                 gas_liquid_ratio="0.8 Nm3/m3",
                 gas_composition={"CH4": 0.8, "CO2": 0.2})
```

- Rename `liquid_density` to `density` and `liquid_viscosity` to `viscosity` (matching `specific_heat` and `thermal_conductivity`). They describe the liquid of a brine or water fluid and the gas of a gas fluid; a mixture density is a computed property, never an input.
- `gas_liquid_ratio` (normal m³ of free gas per m³ of produced liquid at 0 °C and 1.01325 bar a) and `gas_composition` (mole fractions, summing to 1; species `CH4`, `CO2` and `N2` at least) derive `gas_mass_fraction`. Give either `gas_liquid_ratio` with `gas_composition` or `gas_mass_fraction`, never both (`ValidationError`). The formulas (ideal-gas normal density, molar mass, lower heating value per kg, combustion CO₂ per kg of gas, CO₂ carried in the gas) go in a new `gemini/physics/gas.py` with cited constants.
- New `kind="gas"`: a gas fluid with `gas_composition`, whose properties come from the composition (ideal-gas density at the stream's p and T, lower heating value). It is what a degasser's gas outlet carries.
- `co2_mass_fraction` (dissolved CO₂ for corrosion) stays and is a different thing from the CO₂ in the free gas; say so in `types.md` and the docstring.
- `ProductionReservoir` and `InjectionReservoir` lose `liquid_density` and `liquid_viscosity`: the fluid owns its properties. Move the values of shipped examples onto their fluids.
- Test: for the hackathon brine, the normal gas density is about 0.97 kg/Nm³ and the gas mass fraction about 7.5e-4; state the exact values you get.

## 5. Gas chain

```python
p.connect("degasser.gas", "makeup.inlet")       # co-produced gas
p.connect("makeup.outlet", "boiler.fuel_in")     # boiler takes what it needs
p.connect("boiler.gas_out", "flare.inlet")       # surplus is burned
# without co-produced gas: p.connect("grid.outlet", "boiler.fuel_in")
```

- `Degasser`: its `gas` outlet carries a `kind="gas"` fluid with the inlet's `gas_composition`, at the vessel pressure.
- `Boiler` (gas) and `CHP` get a `fuel_in` inlet (stream `gas`) and a `gas_out` outlet. Each step the unit needs `duty / efficiency` of fuel energy; it burns the co-produced gas first, up to its need, and takes the rest from the grid. Outputs: `fuel` (total), `fuel_coproduced`, `fuel_purchased`, `co2_emission` (kg/s: combustion CO₂ of what it burned plus the CO₂ carried in the co-produced gas). `gas_out` carries the unburned co-produced gas. An electric boiler keeps no gas ports.
- New category `supply` (folder `modules/supply/`, added to `gm.modules.categories()`) for everything the plant buys from outside, with names built the same way, `<Carrier>Grid`:
  - `ElectricityGrid`: today's `GridConnection`, moved and renamed (no alias).
  - `GasGrid`: a source with one `outlet` (stream `gas`), the grid gas composition as a parameter with a cited default.
  - `GasMakeup`: in-line, `inlet` from the degasser and `outlet` to the burner; it marks that the burner may draw grid gas and is how the flowsheet shows that connection.
- `Flare` (category `treatment`) burns its inlet and reports `co2_emission`. `Vent` reports the methane it releases (`methane_emission`, kg/s).
- **Supply rules** (write them in `modules.md`):
  1. Every carrier bought from outside has a supply module, and every consumer reaches one: no electricity or gas use without a supply module in the plant (`validate` code `missing_supply`). The rule applies to the plant that is run (the root), not to sub-plants: a `Doublet` used inside a bigger plant has no grid of its own, and its pumps are served by the root's `ElectricityGrid`. A plant that also generates electricity (CHP, ORC) still needs the grid for the export or shortfall.
  2. What has mass and composition (brine, water, gas) moves through ports; electricity has no ports. The plant sums the `electricity` outputs of its modules (and the generation of CHP or ORC) and feeds them to `ElectricityGrid` itself: its consumption and generation stop being `Boundary` values read from data.
  3. Supply modules hold physics and limits only (connection limits, gas composition, pressure). Prices and emission factors of electricity and gas are `gm.economics.Assumptions` fields; `GridConnection.import_price` and `export_price` move there. A price may be a constant or a profile over time.
- Carbon: every module that emits declares `co2_emission` (and `Vent` `methane_emission`) as additive outputs. `gm.economics.co2(plant, results, assumptions)` sums them, converts methane with `Assumptions.methane_gwp` (cited), and adds grid electricity times `electricity_emission_factor`. The single `fuel_emission_factor` goes, since emissions now come from the composition; say if anything else used it.
- `Assumptions.gas_price` (per MWh of fuel energy, constant or a profile) prices `fuel_purchased` in `opex`; co-produced gas costs nothing. A missing assumption raises `ValidationError` with code `missing_assumption` naming it (record mode: `{value: null, reason}`).
- Test the chain closes its mass and energy balance, a boiler with enough co-produced gas buys nothing, one with none buys everything, and the surplus reaches the flare.

## 6. Doublet from depth

```python
p.add("Doublet", name="d0", params={
    "depth": "2500 m", "gradient": "30 K/km", "surface_temperature": "12 degC",
    "permeability": "200 mD", "thickness": "100 m", "well_diameter": "0.244 m"})
```

- With the pattern of section 3, `Doublet.set_params` derives: reservoir temperature at the midpoint (`surface + gradient * depth`), hydrostatic reservoir pressure from the fluid density, productivity and injectivity indices from permeability, thickness, viscosity, drainage radius and wellbore radius (radial Darcy, with the existing skin), vertical pipe paths of both wells from the depth and `well_diameter`, and the pump setting depth. The formulas live in `physics/`; reuse existing ones (`ground.py`, `hydraulics.py`, the reservoir IPR) instead of adding duplicates.
- Every derived value can be overridden explicitly. The old way (setting every child value directly) keeps working.
- Test: at 2,500 m the reservoir is 87 °C and close to 250 bar(g) with the hackathon brine; state the PI you get.

## 7. Two-phase well check

- Check that the wells' two-phase pressure drop takes the gas fraction from the stream fluid (now set by `gas_liquid_ratio`). Upstream `gemini_model/well/pressure_drop.py` computes the superficial gas velocity as `gmf / rho_g / A` where the gas mass flow `mg` looks intended. If the refactored code carries this, write a failing test from a hand calculation first, fix it, and report the change in numbers. If it was already fixed or does not exist, say so.

## 8. Schedule

```python
plan = gm.schedule(plant, demand, rules={
    "order": ["geothermal", "heat_pump", "boiler"],
    "doublet_flow": {"min": "50 m3/h", "max": "300 m3/h"},
    "max_brine_cooling": "40 K",
    "operating_days": None})
results = gm.simulate(plant, plan)
```

- `gm.schedule` decides, for each day of `demand`, the controls a run needs: flow and on/off of each doublet, heat pump setpoint, boiler duty and the chiller's share, from a simple daily energy balance on the plant's design values (no simulation inside). Rule of thumb: the absorption chiller's heat need is cooling demand over its thermal COP; geothermal heat comes first, doublets in order, each at the flow that gives the needed heat at no more than `max_brine_cooling`, clipped to `doublet_flow`; below the minimum flow a doublet runs at the minimum with less cooling; the heat pump lifts to the supply setpoint; the boiler covers the rest, co-produced gas first.
- It returns the run input (a UTC DataFrame) with the demand columns and one column per scheduled control. The sequence `plan = gm.schedule(...); gm.simulate(plant, plan)` must work without the caller writing bindings for the scheduled controls. Choose the least hidden way (for example `schedule` returns the bindings it needs in a documented place and `simulate` uses them, or `schedule` binds them on the plant and says so in its docstring) and explain the choice in the report.
- `operating_days`: `None` means every doublet may run every day. The meaning of the organisers' "330 daily steps" is not known yet: accept an integer and a list of outage dates in the signature, and raise `NotImplementedYet` for both until I decide.
- Unmet demand is not an error: the run reports it in `unmet_demand`.

## 9. Limits

```python
limits = gm.checks.Limits()
limits.add("d*.flow", min="50 m3/h", max="300 m3/h")
limits.add("d*.brine_cooling", max="40 K")
limits.add("heat_users.supply_T", min="100 degC")
checks = gm.checks.limits(plant, results, limits)
```

- `Limits` holds `(path pattern, output, min, max)` entries; `add` validates the pattern against nothing yet (a plant is not needed to build limits) and the units. `gm.checks.limits` matches the patterns against the plant (an unmatched pattern raises `ValidationError` `unknown_name` with suggestions), reads each output over the run, and returns one check per matched module and output: `{name, passed, value, limit}`, `value` being the worst value of the run. A violated limit is an answer, never an error.
- `Doublet` gets the outputs the hackathon limits need if they are missing: production flow (volume) and brine cooling (production minus injection temperature).
- `Limits` round-trips through a plain dict (`to_dict`, `from_dict`) so geomind can store it.

## 10. Costs

- Every equipment module that has a cost declares `capex(assumptions)` from its own design values: the doublet from depth (drilling per metre, per well) and its pumps, the heat pump, boiler, CHP and chiller from capacity, the exchanger from its UA or area, the degasser, flare and gas makeup as fixed items. The factors are fields of `gm.economics.Assumptions` with a cited source each; where no source can be found, the field is `None` and using it raises `missing_assumption`. List every factor with its value and source in `economics.md` and in the report.
- `gm.economics.capex`, `opex`, `lcoh`, `lcoc`, `npv` and `payback` then give numbers for the hackathon plant once the assumptions are set.

## 11. Hackathon example

- Add a numbered example `examples/<next number>_hackathon_plant/` that builds the hackathon case with these APIs: two doublets at 2,500 m, degasser, heat exchanger, heat pump, gas boiler with makeup and flare, absorption chiller, an `ElectricityGrid`, heating and cooling consumers, plant ports `heating_return` and `cooling_return` at fixed temperatures (assume 60 °C and 25 °C for now and print that these are assumptions), the hackathon brine; then `gm.schedule`, `gm.simulate`, `gm.checks.limits` with the hackathon limits, `gm.kpi.compute`, the economics, and a printed summary in MW and °C.
- Where a step raises `NotImplementedYet`, the example stops there and prints which step; say in the report how far it gets.

## 12. Version and docs

- Raise the version to `0.2.0` (renames and removed names are breaking) with a change-log line per section in `api.md`.
- Update `api.md`, `types.md`, `modules.md`, `plants.md`, `equipment.md`, `economics.md`, `physics.md`, `engine.md`, `AGENTS.md` ("Start here"), the README, every docstring and example touched.

## 13. Report

- Commits, one per section.
- The exact values of the tests in sections 1, 4 and 6.
- Every changed number from the baseline with its reason.
- The ports you named in section 2; the routes you fixed in section 3.
- What you chose for bindings in section 8.
- The cost factors and their sources, and the ones left `None`.
- How far the hackathon example gets.
- What this breaks in `geomind/` and `backend/` (read-only, file and line), for `phases/contracts.md`.
