# Task: gemini correctness: units everywhere, no hidden defaults, complete roles, pump intake limit, readable reports

## 0. Context and rules

- This is a new session. Read `AGENTS.md` and every file in `.claude/docs/` first and follow them (start with `api.md`, `conventions.md`, `testing.md`).
- Repository: `/Users/sahand/Desktop/geomind-spe-geohackathon-2026/gemini`, remote `git@github.com:geomind-spe-geohackathon-2026/gemini.git`. `git fetch --prune`, `git checkout dev`, `git pull origin dev` (expected `cca153b` or later), `git status` clean.
- If `make lint` fails because `.venv` points at an old folder, recreate it first: `rm -rf .venv && python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"` (use the extra name `pyproject.toml` defines).
- **Branch:** `git checkout -b feature/correctness` from `dev`, one commit per section. At the end, if the development tests and the e2e tier pass: merge into `dev` with `--no-ff`, push `origin dev`, delete the branch locally (and on `origin` if it was pushed). No other session works in this repository now.
- **gemini is the source of truth.** Every change is the right general design for the GEMINI project, never shaped after one caller (geomind, backend) or the competition. The competition case (`inputs/examples/hackathon_2026/`) is only a test sample; nothing in `gemini/` is named after it or tuned to it.
- **Standing rules:** `(plant, case)` signatures; one unit format (`gm.units.Quantity` at every public boundary, SI inside; a bare number only for a dimensionless value); no default for anything a user must decide; `from_<format>` / `to_<format>`; update the code, never wrap it (no wrappers, shims, aliases, fallbacks to old names or old shapes); only the real design in the public API (no stubs); no comments inside code (docstrings only); quality bar of `conventions.md`; a failing test before each bug fix.
- **Temporary files** go to `.tmp/correctness/` (git-ignored).

### You are the coordinator

Run the work in parallel and do not spend your own context doing it. You plan, hand out tasks, review short reports and diffs, decide, merge onto `feature/correctness`, and run the tests once. You never edit more than a few lines yourself and never read large files whole.

- Workers are subagents on sonnet; read-only searches use haiku. Each works in its own git worktree under `../gemini-correctness-tmp/` on a local branch `correctness-<letter>` (never pushed), owns the files listed for it, commits once, runs only the tests of its files, and answers in at most 20 lines. Details go to `.tmp/correctness/<worker>.md`.
- **Phase 1, in parallel:** B (section 2), C (section 3), D (section 4), E (section 5). **Phase 2, after you merge phase 1:** A (section 1), because it touches callers everywhere. **Phase 3:** G (section 6, examples and docs).
- An overlap between workers goes back to its owner. Remove your worktrees and `correctness-*` branches at the end.

### Tests

- Development profile only (`make test` / `scripts/test_changed.py`, with `test_code_quality.py`), parallel, under 300 s. New tests under about 1 s each, on small plants and short cases. Never run the slow dataset. Never delete or shrink goldens; regenerate one only where a section changes behaviour on purpose, and list it.
- A budget test that fails under load is rerun alone before it counts; name the tests you retimed.
- **Numbers:** sections 1, 2, 5 must not change any result of the sample cases (every example prints the same numbers; check with the e2e tier and one run of each example). Sections 3 and 4 add checks; a result changes only where a new constraint of the case now rejects a design, and the report says which.
- Run `examples/hackathon.py` at most twice in the whole task, never two at a time.

## 1. One unit format at every public boundary (worker A, phase 2)

Owns `Module.set_params` and its helpers, `gemini/run/call.py` (`gm.call`), `gemini/types/` (`Stream`, `Fluid` constructors), the plant JSON reader, and the callers in `gemini/`, `examples/`, `tests/`, `scripts/` that pass bare numbers.

- Today `set_params("d0", {"well_diameter": 0.2})`, `gm.call`, `gm.Stream(...)` and `gm.Fluid(...)` accept bare SI numbers for dimensioned values. Make them take a `gm.units.Quantity` (or the JSON form `{"value", "unit"}` where the input is a dict or JSON) for every dimensioned value, check the unit against the declared quantity (same error and did-you-mean as the case), and convert to SI. A bare number for a dimensioned value raises `ValidationError` naming the path, the quantity and the accepted units. Dimensionless values (efficiencies, fractions, counts, ratios) stay bare numbers.
- Internal code (engine, study, size, apply of the case) keeps working in SI: it uses one private path that sets SI values, not the public `set_params`. Do not add a second public setter.
- Plant JSON already stores `{"value", "unit"}`; check that every stored plant in `inputs/` follows it and fix any bare dimensioned number.
- Tests: each of the four entry points accepts a `Quantity`, converts it, rejects a bare dimensioned number with the expected message, accepts a bare dimensionless number.

## 2. No hidden defaults in modules (worker B, phase 1)

Owns the declarations in `gemini/modules/**` and `gemini/plants/**` except `gemini/modules/pumps/esp.py` and `gemini/modules/pumps/injectionpump.py` (worker D), plus the plant JSON files in `inputs/` and their callers in tests.

- About 70 declarations still have a `default=` (for example circulation pump efficiency, pipe roughness, valve rangeability, filter drops, degasser drop, flare efficiency, gas-grid composition, heat-exchanger arrangement, reservoir thresholds). First let a haiku search list every one into `.tmp/correctness/defaults.md` with a class for each:
  - **physical constant or standard reference** (for example normal pressure, latent heat of a standard state): keep, with the source in the docstring of the constant;
  - **switch for an optional feature**, where the default means "this feature is off" (for example a monitoring threshold whose absence means no alarm): keep only as `None` meaning off, never as a number;
  - **design value or assumption** (efficiencies, roughness, drops, compositions, arrangements, nominal flows, labels): remove the default; the user sets it.
- Remove the third class. Every stored plant in `inputs/` and every test plant then sets these values explicitly, with the value it effectively used before, so no number changes. Where a value in `inputs/examples/*` has no source, its README says it is an assumption.
- A quality test: no declaration in `gemini/modules/` or `gemini/plants/` has a numeric or string default unless it is listed as a constant in one allow-list (with the reason for each).
- Tests: a plant missing one of the removed values raises the missing-value error listing it (with its description).

## 3. Complete roles (worker C, phase 1)

Owns `gemini/case/roletable.py`, the role finding it uses, `gemini/evaluate/constraints.py`, `gemini/plants/` capabilities (roles part only), and their tests.

- The role table lacks the outputs of the units and the plant as a whole, so a case cannot limit, for example, what a heat pump or a chiller delivers, or the plant's bought electricity or its CO2. Add:
  - `heat_output` (power) to `heat_pump`, `boiler`, `chp`; `cold_output` (power) to `chiller`; each read from the unit's own result;
  - a role `plant` (the plant itself) with `electricity_bought` (power), `gas_bought` (power), `heat_surplus` (power), `co2` (mass rate or mass, choose one and document it), read from the plant's results.
- The aggregates (`over each|sum|mean|max|min|duration`) and `when` work for the new quantities as for the others. `gm.case.roles()` and `gm.plants.capabilities()` list them.
- Tests: a small case with a `heat_output` max on a heat pump and a `plant.electricity_bought` max: a design over the limit fails with the right name, value and limit; under the limit passes.

## 4. Pump intake limit (worker D, phase 1)

Owns `gemini/modules/pumps/esp.py`, `gemini/modules/pumps/injectionpump.py` (including their defaults, as in section 2), the pump physics they call, the role quantities of the pumps (coordinate the table change with C: C owns the file, D gives C the two rows), and `inputs/examples/*/case.json` constraints for it.

- The study found the ESP's suction pressure falling near zero at low permeability, so liberated gas inflated the volume flow to 9.4e6 m3/s and the curve extrapolated; today that row only fails as `out_of_range`. The physical rule is that a pump needs enough pressure at its intake. Make it a stated, checkable quantity:
  - the ESP outputs its `intake_pressure` and the `gas_volume_fraction` at its intake (free gas volume over total volume at intake conditions, from the fluid's gas-liquid ratio and the gas law the fluid already uses);
  - the `doublet` role gains `intake_pressure` (pressure) and `intake_gas_fraction` (fraction), so a case limits them with ordinary constraints (`min` for the pressure, `max` for the fraction); no limit is built into the module (no default);
  - the `out_of_range` failure for a row outside the curve stays.
- Add both limits to `inputs/examples/hackathon_2026/case.json` and `shallow_district/case.json` with values from a published ESP design reference you can open (for example a manufacturer's handbook or a paper on gas handling of ESPs); if you cannot open one, mark the values in the README as "assumption, no verified source". These are case data, never in `gemini/`.
- Tests: intake pressure and gas fraction on a small doublet; a case with a minimum intake pressure rejects a design whose suction drops below it.

## 5. Readable reports through and through, and `validate` on a plant (worker E, phase 1)

Owns `gemini/evaluate/report.py`, `gemini/evaluate/_utils/display.py`, `gemini/plants/` `validate` (the catalogue module), and their tests.

- `report.to_dict(units=...)` shows LCTS and CO2 in display units, but their parts stay SI (`currency/yr`, `J/yr`, `kg`, `J`, `s`). Apply the one display table to every part (annualised cost in EUR/yr, energies in MWh or GWh per year, masses in t or kt, durations in days), with the same `units` override. Values inside the report stay SI.
- `gm.plants.validate` takes a plant dict or a `Plant` (it calls `to_dict(structure=True)` itself); one implementation, no second function. Update the callers that build the dict by hand.
- Tests: every part of a report's dict has a display unit; `validate` on a `Plant` and on its dict give the same result.

## 6. Examples and docs (worker G, phase 3)

- Every example runs and prints the same numbers as before, except where a new constraint of section 4 changes a result (say which and why).
- `examples/plant.py` shows `set_params` with quantities, `missing_parameters()` and `validate(plant)`; `examples/costs.py` shows a `plant.electricity_bought` or `heat_output` constraint.
- Docs: `api.md` (contract table and "unreleased changes": quantities in `set_params`, `gm.call`, `Stream`, `Fluid`; removed defaults; new roles; ESP outputs; report units; `validate(plant)`), `conventions.md` (the defaults allow-list rule), `equipment.md` (ESP intake outputs). Every docstring touched.

## 7. Report (at most 40 lines)

- Commits, the merge into `dev`, the pushed hash; branch and worktrees removed.
- Section 1: the four entry points, and how many callers changed.
- Section 2: counts per class (kept constants, `None` switches, removed), the allow-list, and confirmation that no number changed.
- Section 3: the new roles and quantities.
- Section 4: the intake values on the competition case at the chosen design, the limits used and their source, and whether any searched design is now rejected.
- Section 5: a sample report dict.
- Tests run and retimed; example times.
- An old -> new table of every public change that geomind or the backend must follow.
- Anything not done, with the reason.
