# gemini gaps found by geomind 0.2.0 adaptation (2026-11-01 20:16)

geomind main fcb1450 runs on gemini dev cca153b. Source: geomind `.claude/docs/plan.md` section 7.
Status column: is it already in a gemini prompt?

| # | gap | kind | status |
| --- | --- | --- | --- |
| 1 | `Case.to_dict()` demand round trip: kW column keeps unit name, values in W, 1000x off | bug | new |
| 6 | `Report.to_dict()` shows a temperature difference as temperature (40 K -> -247 degC) | bug | new (touches correctness section 5 display table) |
| 2 | `gm.case.missing(case, job)` listing every missing value at once | feature | new |
| 3 | `Case.from_dict(data, files={name: bytes})` / in-memory demand | feature | new |
| 4 | readable units option for `gm.call` | feature | partly (correctness section 1 = Quantity in, not display out) |
| 5 | constraint quantity for co-produced gas burned | feature, low | new |
| 7 | money sub-parts of report (capex per module, opex parts) in display units | feature | in correctness section 5 |
| 8 | `gm.simulate` should record no_convergence rows, not raise PhysicsError (cold reservoir 20 K/km) | bug | new |
| 9 | `Best.to_dict()`, `Sample.to_dict()`, sizing notes in display units | feature | new |
| 10 | each `gm.evaluate` call copies the plant and re-applies the case (slow) | speed | new |
| 11 | `gm.study.minimize` default `evaluations=100` breaks no-defaults rule | rule | new (correctness section 2 covers modules/plants only) |
| 12 | demand shorter than case file/time window (30-day profile vs full-year case) needs a 3-step workaround; let case time follow demand, or clip/validate with a clear error | feature | new |
| 13 | no single public feasibility verdict: report.passed = constraints only, minimize = constraints + no failed steps, physics balances (energy/mass/bounds/plant_balance) not included; one verdict with reasons used by minimize/compare/report | design | new |
| 14 | optional id on a constraint so references survive list edits | feature, low | new |

Plan: fold all "new" rows into the next gemini prompt after feature/correctness is merged.

## Left over from feature/correctness (dev b1db49f7, 2026-11-01 20:31)
- two bare-SI public doors kept: attribute assignment (esp.frequency = 50) and Stream.with_ -> break the one-unit-format rule
- report shows lifetime and payback in days (display.py maps every duration to d; payback.py reports yr): long-horizon durations (lifetime, payback) should display in yr, operating durations in d
- ~25 snippets in equipment.md fail (outputs that no longer exist)
- 4 CPU-budget tests fail under full parallel load (pass alone)
- ESP intake limits sit in case.json constraints; by the new boundary they belong to ESP parameters in the plant (min intake 5 bar unsourced; gas 18.75% Baker Hughes is for STANDARD stages only, gas handlers take 75% -> pump type should be a design choice; gemini has no gas-handler pump; report competition result both with organiser-only constraints and with standard-ESP limit)

## Coverage by prompts/gemini-inputs.md (2026-11-01 23:41)
Covered: 1, 2 (gm.check), 3, 6, 10, 11, 12, 13, 14 (rule name), payback/lifetime display, unit doors, ESP limits.
NOT covered -> small fix prompt after feature/inputs merges: 8 simulate raises PhysicsError on cold reservoir instead of recording no_convergence rows (most important); 9 display units for Best/Sample/size notes; 4 gm.call display units (optional). Later: 5 gas-burned quantity.
