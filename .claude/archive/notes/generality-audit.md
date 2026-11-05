# Everything in gemini that is specific to the competition

Review on `refactor` at `33c7f52`, 2026-10-31. Rule: the competition inputs are only one example of a problem, and the code knows nothing about them.

---

# 1. Code that knows the competition (must be removed)

## 1.1 Competition rules in the code
### `gm.challenge_rules()`
`gemini/analysis/schedule.py:36-47`: the numbers 50 to 300 m3/h, 40 K and 330 days.
**Change:** remove. Constraints come only from `Problem.requirements`.

### Optimizer default
`gemini/optim/search.py:11, 78, 168-170, 278`: `profile=None` means the competition demand and rules.
**Change:** the optimizer takes `problem`; without it, a clear error.

## 1.2 Competition-specific plant
### `HackathonPlant`
`gemini/modules/plants/hackathonplant.py`, exported in `modules/__init__.py` and `plants/__init__.py`.
**Change:** remove from the library. If the same design is needed, it becomes a plant dictionary in the competition example folder.

## 1.3 Built-in hackathon profiles
### `gm.profiles`
`gemini/profiles/library.py` (`SOURCE`, `demand()` "competition year"), `profiles/__init__.py:6`, `utils/paths.py:29` (`paths.hackathon`).
**Change:** `gm.profiles` has no built-in profiles; a profile is built from a file or values (`from_csv`, `from_values`). The competition example is only a file in the example folder.

## 1.4 Physical defaults from the competition
### Gradient and surface temperature
`gemini/physics/ground.py:69-72`: 12 degC and 30 K/km labeled "competition value"; the default of `Doublet.gradient` and `surface_temperature` (`plants/doublet.py:37`).
**Change:** no default; they come from `Problem.site`, and without it a `missing_value` error.

## 1.5 Sources that refer to the competition
### physics docstrings
- `physics/gas.py:18, 21, 123`: normal conditions (0 degC, 1.01325 bar). The physics is general; the source should become a general one (DIN 1343 / ISO 13443), and the GLR reference conditions should be an input.
- `physics/ground.py:103`: linear geotherm.
- `physics/hydraulics.py:1035`: reservoir hydrostatic pressure.
- `physics/pumps.py:81`: pump from the design point.
- `physics/combustion.py:258`: dispatch rule.
- `plants/_utils/catalogue.py:65`: "template plants those of the challenge".
**Change:** a general scientific or technical source; no reference to the competition.

---

# 2. Assumptions built into the structure

## 2.1 Daily time step
### `gm.schedule` daily only
`analysis/schedule.py:1, 32`: the schedule is "daily" and `operating_days` counts days.
**Change:** any time step (hourly, daily, ...); operating time as a number of steps or hours, not only days.

## 2.2 Sizes tuned for one demand
### Sample values of the template plants
`inputs/plants/HeatingCoolingPlant.json` and the rest: boiler 30 MW, heat pump 15 MW, exchanger conductance 1.5 MW/K, nominal flow rate 300 m3/h, all for the competition demand.
**Change:** sizes come from `gm.design.size(plant, problem)`; the sample file is only an example.

## 2.3 Site data mixed with design
### The `inputs/plants/*.json` files
Depth, permeability, reservoir pressure and pump efficiency (problem data) next to capacities (design decisions).
**Change:** two separate files: `problem.json` (demand, site, fluid, constraints, prices) and the plant dictionary (design only).

## 2.4 Fixed injection pump pressure
### Fixed setpoint of 30 or 60 bar
On the template plants.
**Change:** compute it from the reservoir and injectivity (a constraint on the plant), not a fixed number.

---

# 3. Tests and examples

## 3.1 Only one problem
### All e2e on the hackathon
**Change:** at least two problems: the hackathon and one other example (a different demand, a colder reservoir, an hourly step).

## 3.2 Quality test
### Preventing regression
**Change:** a test that searches `gemini/` for `hackathon`, `challenge` and the competition numbers.

## 3.3 Location of the competition data
### `inputs/hackathon/`
**Change:** `inputs/examples/hackathon_2027/` with `problem.json`, CSVs and PDF; only examples and tests use it.

---

# 4. Outside gemini

## 4.1 geomind
`geomind/tools/gemini/brief.py` has the competition numbers; the prompt `phases/geomind/general-briefs-and-fixes.md` turns it into data. The Brief must become the same `Problem` dictionary.

## 4.2 backend and frontend
Not reviewed yet.
