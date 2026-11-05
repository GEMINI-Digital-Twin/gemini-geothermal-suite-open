# Task: Every part of the energy flow is a module; totals come from ports; module and physics layout

## 0. Context and rules

- This is a new session. Read `AGENTS.md` and every file in `.claude/docs/` first and follow them. Start from the current `refactor` (the hackathon-API commits, up to `ae8a27d` "Version 0.2.0 ..." or later, are in).
- The decisions below were made with me one by one. Follow them. Where one does not fit the code, stop that section and say why in the report instead of inventing another design.
- **Main principle:** everything that takes part in the plant's energy or mass flow is a module, and everything that crosses between two modules goes through a port. This covers electricity, gas, heat to customers, cooling to customers, waste, chemicals, the air and the formation around the wells. A plant total is read from the ports of the modules at the plant's edge, never summed by a parent plant.
- **Standing rules:**
  - No concept has two implementations.
  - Behaviour is identical on every backend.
  - Modules declare and wire; physics computes (see section 1 for where physics now lives).
  - Every numeric default has a cited source in its docstring, or there is no default.
  - No inlet or outlet is left unconnected (`unconnected_port`).
- **Version:** do **not** change the version. Nothing has been released and nobody depends on it yet. Add the change-log lines under the current version in `api.md`, marked "unreleased changes".
- **Module catalogue rule:** adding, removing, moving or renaming modules is never a version matter. The API snapshot (if one exists) covers only the package API (functions, types, return shapes), not the list of modules. Write this rule in `api.md` if it is not there.
- **Git:** work directly on branch `refactor` (no new branch, no PR). One commit per section below, in order. **Do not push** until I have reviewed the commits.
- **Pre-check:** `git status` is clean on `refactor`, and no other Claude session or process is working **inside `gemini/`**. Sessions in other folders do not block you. If their load makes a 1 s budget test fail, rerun that test alone before treating it as a failure, and say which tests you retimed.
- **Scope:** workspace `/Users/sahand/Desktop/crust-team`. Change **only** `gemini/`. You may read `geomind/` and `backend/`, but never change them.
- **Temporary files** go to `.tmp/energy-flow/` (git-ignored).
- **Agents:** one agent is enough. Subagents, if any, run on a lighter model and only do read-only searches.
- **Tests:**
  - Use the development profile only (`make test` / `scripts/test_changed.py`, always including `test_code_quality.py`), run in parallel, under 300 s.
  - Run the e2e tier and all numbered examples once at the end, against a baseline taken before the first change.
  - Numbers stay identical except where a section changes physics on purpose. List every changed number with its reason.
  - Never run the slow dataset locally.
  - Never delete or shrink existing tests, datasets or goldens. Rename them where a module or port is renamed.
- **Quality bar** as in `.claude/docs/conventions.md`:
  - simple, readable, just enough code;
  - nesting at most 3, functions about 40 lines at most, guard clauses;
  - explicit `gm.errors` with codes;
  - no comments inside code (docstrings only);
  - black, isort and flake8 clean;
  - write a failing test before each bug fix.
- If something else is needed, say so in the report.

## 1. Layout: `modules/_utils` and per-category `_physics.py`

Do this first. It is pure moves, so every number must stay identical.

**Module helpers.** Helper files that are not a module or a category move to `gemini/modules/_utils/`. Read every file directly under `gemini/modules/` and in the category folders to decide which these are. My reading is: `balance.py`, `container.py`, `description.py`, `design.py`, `parameter.py`, `registry.py`, `serialization.py`, `wiring.py` and `cooling/_sorption.py`.
- `module.py` and the category folders stay where they are.
- Public names (`gm.ModuleDict`, `gm.modules.register`, ...) are still exported from the same public places.
- Leave the helpers in `modules/plants/` (factory, catalogue, templating, ...) alone. They belong to the planned plant rewrite.

**Physics split.**
- `gemini/physics/` keeps only well-known textbook formulas, and anything used by more than one category or by `analysis/`, `optim/`, `economics/` or `checks/`. Examples: fluid properties, hydraulics (Darcy-Weisbach, two-phase), heat transfer, combustion, gas, ground, corrosion, erosion, Carnot/COP, pump affinity laws, units, constants.
- Physics used by only one category moves to `gemini/modules/<category>/_physics.py`. The current imports suggest these moves. Check each one against the code, and list every function you move and why:
  - `compression` to `pumps`
  - `control` to `control`
  - `electricity` to the new `grids` (do it in section 4)
  - `power_cycles` and `steam` to `power`
  - `storage` to `storage`
  - the sorption-specific part of `refrigeration` to `cooling`
  - the ESP-curve part of `pumps` to `pumps`
- A `_physics.py` imports only from `gemini.physics`, `gemini.ops` and `gemini.types`, never from another category's `_physics.py`. When a second category needs a function, it moves up into `gemini/physics/`.
- Functions keep `@ops.physics` and stay traceable on every backend.
- Update the "physics lives only in `gemini/physics/`" test in `test_code_quality.py` to the new rule, and enforce the import rule above. Update `physics.md`.

## 2. Port label and port names

**Port label.**
- Rename the port label argument `stream=` to `kind=` everywhere: `Inlet(Stream, kind="hot_water")`.
- The first positional argument of `Inlet`, `Outlet` and the other declarations is today also named `kind`. Rename it to `type`, or another name that fits the declarations, so that `kind` means only the connection label. Do this the same way in every declaration and in plant dicts and schemas.
- "Port" stays the general word. `Inlet` and `Outlet` stay the classes.

**Naming rule.**
- Every port name is `<role>_in` or `<role>_out`.
- A module with one circuit uses `fluid_in` / `fluid_out`. This replaces `inlet`, `outlet`, `suction`, `discharge` and the like.
- Port names that lack the suffix today (`wellhead`, `bottom`, `sandface`, `gas`, `liquid`) get it.
- Splitter and mixer branches use `branch1_out`, `branch2_out` / `branch1_in`, `branch2_in` (instead of `first`/`second`) and `fluid_in` / `fluid_out` for the common side.
- Role glossary:
  - `hot`, `cold`
  - `source`, `sink`
  - `generator`, `chilled`, `cooling`
  - `charge`, `discharge`
  - `supply`, `return`
  - `gas`, `liquid`, `fuel`
  - `power`, `loss`, `air`
  - `waste`, `chemical`
  - `wellhead`, `bottom`, `sandface`
  - `production`, `injection`
  - `fluid`, `branch<N>`
- Put the glossary in `conventions.md` and `glossary.md`. Add a role only when no existing one fits, and say which roles you added.
- A test in `test_code_quality.py` checks every port of every registered module against the rule and the glossary.

Rename every port in modules, plants, examples, tests and docs. Give the full old-to-new table in the report.

## 3. Ports that carry power and heat; many-to-one ports

- A port may carry a `Power` value instead of a `Stream`:
  - `Inlet(Power, kind="electricity")` for electricity;
  - `Outlet(Power, kind="heat")` for heat that leaves without mass, such as losses.
  - Connections check that `kind`s match, as they do for streams.
- `many=True` on a port lets several ports connect to it. Its value is the list of what arrives, and the module sums it with an explicit function, not a hidden one.
- Electricity consumers get `power_in` (pumps, heat pump, electric boiler, chiller auxiliaries, compressor, fans of the cooler). Generators get `power_out` (CHP, ORC, flash turbine).
- Each `electricity` / `electricity_generated` output that only repeated the port value goes (see section 7).
- A sub-plant whose children use electricity exposes one `power_in`. Inside, it distributes power to its children with a `many=True` port on a plant-level port, or the least hidden equivalent. Explain the choice in the report.
- If the engine or a backend cannot carry a non-`Stream` value through a port, stop this section and report what is missing.

## 4. Category `grids`: the plant's edge for bought and delivered carriers

New category `grids` (`gemini/modules/grids/`, listed by `gm.modules.categories()`). It holds **only edge modules**: things that take a carrier from outside the plant or deliver one to outside. A module that processes a flow inside the plant stays in its own category. Write this rule in `modules.md`. Each module's carrier name follows `<Carrier>Grid`.

| Module | From | Ports |
|---|---|---|
| `ElectricityGrid` | today's `GridConnection`, moved and renamed, no alias | `power_out` (`many=True`, to consumers), `power_in` (`many=True`, from generators) |
| `GasGrid` | moved from where it is now | `gas_out` |
| `HeatingGrid` | today's `HeatConsumer`, moved and renamed | `supply_in`, `return_out` |
| `CoolingGrid` | today's `CoolingConsumer`, moved and renamed | `supply_in`, `return_out` |
| `WasteGrid` | new | `waste_in` (`many=True`) |
| `ChemicalGrid` | new | `chemical_out` |

Notes on the table:
- **ElectricityGrid:** import, export and limits come from its ports. The `consumption` / `generation` `Boundary` values and the plant's summing of children's electricity go.
- **HeatingGrid and CoolingGrid:**
  - The demand stays a `Boundary` and is bound to `gm.profiles.get("heating_demand")` / `("cooling_demand")`.
  - The return temperature is a fixed parameter for now; the network values are still to come from me.
  - Unmet demand is reported, never an error.
  - The `demand` category is removed.
- **WasteGrid:** blowdown, desander, filter and other discarded flows end here. Disposal cost per unit is an `Assumptions` field (cited, or `None` with `missing_assumption`).
- **ChemicalGrid:**
  - It feeds `InhibitorDosing` (and any other dosing) through a `chemical_in` port with `kind="chemical"`.
  - Chemical price is an `Assumptions` field.
  - The dosed amount is read from the port.
- **GasMakeup** is a mixer, not an edge module. It moves to (or stays in) `piping` next to `Mixer`, with ports:
  - `gas_in` (co-produced gas);
  - `grid_in` (from `GasGrid`, the shortfall);
  - `fuel_out` (to the burner's `fuel_in`);
  - `excess_out` (surplus, to `Flare`).
- **Plant ports:**
  - With every edge a module, a root plant needs no plant ports. `validate` reports a plant port on the root plant (choose a code, e.g. `root_plant_port`).
  - Named plant ports remain for sub-plants such as `Doublet`.
  - Update the "every bought carrier has a grid" rule (`missing_supply`) to the new category and port wiring. It applies to the root plant only.
- Prices and emission factors stay in `gm.economics.Assumptions`, as a constant or a profile.
- If any of the `supply`-category work from the previous task exists, fold it into `grids` and say what you merged.

## 5. Category `environment`: air and formation

New category `environment`, again only edge modules.

**`Atmosphere`**
- Holds the ambient temperature (and wet-bulb temperature, if the cooler needs it) as `Boundary` values. No other module keeps its own `ambient_temperature`; remove it from `Pipe`, `Cooler`, `ThermalStorage` and any other module.
- Ports:
  - `air_out` (`many=True`): an air stream at ambient conditions, for every module that exchanges heat with air;
  - `air_in` (`many=True`): air coming back;
  - `heat_in` (`many=True`, `kind="heat"`): losses;
  - `gas_in` (`many=True`, `kind="gas"`): flue gas, flare exhaust and any released gas.
- `co2_emission` and `methane_emission` of the whole plant are computed **only here**, from what arrives at `gas_in`. The per-module emission outputs go, and `Vent` is removed: a vent is a pipe to the air, so its inlet connects to `Atmosphere.gas_in`. `gm.economics.co2` reads `Atmosphere` plus `ElectricityGrid` import times the emission factor.
- `Boiler`, `CHP` and `Flare` get a `flue_out` (`kind="gas"`) to `Atmosphere.gas_in`. Use `exhaust_out` instead if it reads better, but use one name for all three.

**Air side of the cooler.**
- `Cooler` takes `air_in` from `Atmosphere.air_out` and returns heated air through `air_out` to `Atmosphere.air_in`. The heat it rejects is read from these ports.
- If an air stream at ambient conditions fanned out to many modules does not fit the engine, stop and report the least hidden alternative.

**`Formation`**
- Lives inside `Doublet`. Doublet creates it and wires it, so the user never connects it.
- It holds the rock around the wells: geothermal gradient and surface temperature, which Doublet passes through `set_params`, the same values the wells get.
- It receives each well's heat loss through the wells' `loss_out` into its `heat_in`.

## 6. Losses are ports

- Every module that loses heat to its surroundings has `loss_out` (`kind="heat"`): pipes, storage, wells, boiler shell if modelled, and any other module.
- `loss_out` connects to `Atmosphere.heat_in`, or to `Formation.heat_in` for wells.
- Total heat lost by the plant is read from those ports.
- Update every shipped plant, example and test plant so no `loss_out` is left unconnected. List the connections you added per plant.

## 7. Plant totals and quantities come from ports; outputs only for internal values

**Port quantities.** Every port gets derived quantities in `Results`, computed by **one** function in `gemini/physics/` (or the physics helper `balance` already uses), never per module:
- fluid port: mass flow, volume flow, temperature, pressure, enthalpy flow (state the reference temperature in the docstring), gas flow, CO₂ flow;
- power or heat port: power.

Example: `results.series("hp.hot_out.enthalpy_flow")`, `results.series("grid.power_out")`. Pick the exact names, use them the same way in `results`, `gm.kpi`, `gm.checks.limits` and economics, and document them in `types.md` and `engine.md`.

**Outputs.**
- An `Output` that repeats a port quantity, or the difference of two ports of the same module (for example `useful_duty`, `condenser_duty`, `electricity`, `co2_emission`, `fuel`, the consumer's delivered heat), is removed. Anything that read it reads the port quantity instead.
- `Output`s stay only for values that are on no port: states (reservoir temperature, cumulative volume, storage state), internal physics (well pressure drop and velocity, pump head, COP, corrosion and erosion rates, `is_running`, `is_capped`) and design values.
- List every removed output with the port quantity that replaces it. Also list every output you kept that you were unsure about.

**Plant totals.**
- Remove summation of children's outputs in parent plants wherever it exists.
- `gm.kpi` totals (heat delivered, cooling delivered, electricity bought and sold, gas bought, emissions, waste, chemicals, losses) read the edge modules' ports.

## 8. Balance checks

- Build on the existing `modules/balance.py` and `gm.checks.balances`. For every module, and for the root plant as a whole, mass and energy in equal mass and energy out plus losses plus change of stored energy, within a stated tolerance.
- For the root plant, "in" and "out" are exactly the ports of the `grids` and `environment` modules.
- They return `Check`s (`{name, passed, value, limit}`). A failed balance is an answer, not an error.
- Add the plant balance to the e2e tests of every shipped plant and example. A failing balance there is a bug to fix (test first), or a physics gap to report.

## 9. Hackathon example

Update the hackathon example (and every other example) to the new modules:
- `ElectricityGrid`, `GasGrid`, `HeatingGrid`, `CoolingGrid`, `WasteGrid`, `ChemicalGrid`, `Atmosphere`;
- `GasMakeup` with `excess_out` to `Flare`;
- a `Cooler` for the absorption chiller's heat rejection, with its air from and to `Atmosphere`;
- losses wired, no plant ports;
- the fixed return temperatures of 60 °C and 25 °C still printed as assumptions.

Print the plant balance check, and the totals read from the edge modules. Say in the report how far it gets.

## 10. Docs

- Update `api.md` (unreleased changes), `types.md`, `modules.md` (edge-module rule, supply rule, port rule), `conventions.md` (port naming and glossary, `_physics.py` and `_utils` rules), `glossary.md`, `plants.md`, `equipment.md`, `economics.md`, `physics.md`, `engine.md`, `AGENTS.md` ("Start here"), the README, and every docstring and example touched.
- Add a short "energy flow" picture (text) to `modules.md`: edge modules, processing modules, and which ports carry what.

## 11. Report

- Commits, one per section.
- Section 1: files moved to `_utils`, and functions moved to each `_physics.py` with the reason.
- Section 2: the full old-to-new port table and the roles added.
- Section 3: how sub-plants pass power to their children.
- Sections 4 and 5: what you merged from the previous task's supply work, and the fan-out decision for air.
- Section 6: the loss connections added per plant.
- Section 7: removed outputs with their replacement, and kept outputs you were unsure about.
- Section 8: balance results per shipped plant (passed, worst value).
- Every changed number from the baseline with its reason.
- How far the hackathon example gets.
- What this breaks in `geomind/` and `backend/` (read-only, file and line), for `phases/contracts.md`.
