# Task: trustworthy design search and comparison, and priced equipment

## 0. Context and rules

- This is a new session. Read `AGENTS.md` and every file in `.claude/docs/` first and follow them (start with `api.md`, `conventions.md`, `testing.md`).
- Start from `refactor` at `ab9e754` in `/Users/sahand/Desktop/crust-team/gemini`. `git status` must be clean and `git pull origin refactor` must succeed.
- **Another Claude session works at the same time** in `../gemini-speed` (branch `speed`, speed of the run). Never touch that folder, its branches or worktrees. To keep the later merge easy, **do not change** these files: everything under `gemini/engine/`, `gemini/ops/`, `gemini/compiler/`, `gemini/runtime/`, and `gemini/plants/_utils/loops.py`, `gemini/modules/module.py`. If a fix needs one of them, stop that item and say so in the report.
- **Speed is out of scope.** Do not optimise run time. Keep the examples' evaluation counts small enough that the e2e tier stays usable, and say what you chose.
- **The rule (most important):** gemini is a general geothermal heating and cooling package. The hackathon case is only a test sample; nothing in `gemini/` may be named after it or tuned to it. Every fix must be right for any case.
- **Standing rules:** `(plant, case)` signatures; one unit format (`Quantity`, SI inside); no default for anything a user must decide; read/write naming `from_<format>` / `to_<format>`; update the code, never wrap it (no wrappers, shims or aliases); no comments inside code (docstrings only); quality bar of `conventions.md`.
- **Git:** work on `refactor`, one commit per section, in order. At the end, if the development tests and the e2e tier pass, `git push origin refactor` and report the hash.
- **Temporary files** go to `.tmp/blockers/` (git-ignored).

### What is wrong today (measured on `ab9e754` with `python examples/hackathon.py`)

| Candidate | Searched | Failed constraints | LCTS EUR/MWh | CO2 kt |
| --- | --- | --- | --- | --- |
| `HackathonPlant` (hand design, structure form) | no: `invalid_design`, no `size.doublets` | none | 57.05 | 13.8 |
| `HeatingAbsorptionCoolingPlant` | yes | none | 64.51 | 24.6 |
| `HeatingCoolingPlant` | yes | cooling supply temperature | 67.05 | 16.9 |
| `HeatingFullCoolingPlant` | yes | cooling supply temperature | 66.30 | 24.5 |
| `HeatingHeatPumpCoolingPlant` | yes | none | 58.17 | 14.2 |
| `HeatingPlant` (no cooling) | yes | cooling supply | 58.45 | 20.2 |

1. `gm.study.minimize` ignores the case's constraints: two searched designs break the cooling supply temperature.
2. Every searched design is dearer than the hand design, so `size` + `minimize` does not find good designs.
3. `gm.evaluate.compare` ranks designs that break a constraint, and even `HeatingPlant`, which delivers no cooling for a case with cooling demand.
4. `compare(...).to_frame()` and `sensitivity(...).to_frame()` show raw SI (EUR per joule, kg).
5. The injection pump has no priced module (`injection_pump` is in `finance.capex` but no module uses it).
6. Every price and cost factor of the hackathon case is a placeholder without a source.

### You are the coordinator

Run the work in parallel and do not spend your own context doing it. You plan, hand out tasks, review short reports and diffs, decide, merge, and run the tests once. You never edit more than a few lines yourself and never read large files whole; a worker does that and reports a summary.

- Workers are subagents on sonnet; read-only searches use haiku. Each works in its own git worktree under `../gemini-blockers-tmp/` on a branch starting `blockers-`, owns a fixed list of files, commits once, runs only the tests of its files, and answers in at most 20 lines. Details go to `.tmp/blockers/<worker>.md`.
- Order:
  1. one worker: section 1 (diagnosis, read-only plus throwaway scripts in `.tmp/`); you read its summary and decide the fix of section 3;
  2. four workers in parallel: **A** section 2 (owns `gemini/study/minimize.py`, `gemini/study/_utils/`), **B** section 3 (owns `gemini/study/size.py` and the plant classes or plant dicts the diagnosis names), **C** section 4 (owns `gemini/evaluate/compare.py`, `gemini/evaluate/report.py`, `gemini/study/sensitivity.py`), **D** section 5 (owns `gemini/modules/pumps/injectionpump.py` and its tests, `inputs/examples/*/case.json`, the READMEs of `inputs/examples/`);
  3. you merge A, B, C, D in order, hand any overlap back to its owner, run the development tests once;
  4. one worker: section 6 (examples and docs), then the e2e tier once, the push and the report.
- Never run the same full test set twice without a change in between. Remove your worktrees and temporary branches at the end (only yours).

### Tests

- Development profile only (`make test` / `scripts/test_changed.py`, always with `test_code_quality.py`), parallel, under 300 s. New fast tests under about 1 s each, on small plants and short cases, never on the hackathon year. Never run the slow dataset locally. Never delete or shrink goldens.
- A failing test before each bug fix.
- If a 1 s budget test fails under load, rerun it alone before treating it as a failure, and say which tests you retimed.

## 1. Diagnosis (one worker, before any fix)

Find why the searched designs lose to the hand design, with numbers, not guesses. Write `.tmp/blockers/diagnosis.md`:

- For `HackathonPlant` and the best searched `HeatingHeatPumpCoolingPlant`: every equipment size and design value side by side (doublets, depth, flows, heat pump, boiler, chillers, exchanger conductance, coolers), and capex, opex and LCTS split by module.
- Which differences carry the cost gap. Candidates to check: sizes that `size` sets badly (oversized boiler or chillers, heat pump sized when not needed); design values the search never varies (heat pump and chiller capacities, exchanger conductance); too few evaluations (`EVALUATIONS = 5` in `examples/hackathon.py`); the depth range; the topology (the hand design routes cooling differently).
- Why `HackathonPlant` cannot be searched (a structure-form plant without `size.doublets`) and the smallest general way to search such a plant over the choices it can take (for example depth only, with the doublet count reported as fixed by the plant).
- A short list of fixes, each with its expected effect. You decide which go into section 3.

## 2. `minimize` respects the case (worker A)

- A trial is feasible only if its run has no failed step and every constraint of the case passes, including the services' supply temperatures (the same checks as `gm.evaluate.constraints`). An infeasible trial is never `best`; its history entry has `reason` naming the first failed constraint (role, quantity, unit path, value, limit).
- Feasibility must not hide a near-feasible design: rank infeasible trials by their total relative violation, so the search moves towards feasibility, and report `feasible: false` with the least-violating trial when no trial is feasible.
- The extra `constraints` argument (limits on metrics) stays and is checked the same way.
- A plant that does not take `size.doublets` is searched over the choices it does take; the result says which choices were fixed by the plant and why. It no longer fails with `invalid_design` when at least one choice can be searched.
- Tests: a small case where the cheapest trial breaks a constraint and a dearer one is feasible: `best` is the feasible one; no feasible trial: `feasible: false` and the least violation; a plant without `size.doublets` searched over depth.

## 3. Sizing and search that find good designs (worker B)

Apply the fixes you chose from section 1. Whatever they are, they must be general (right for any case, no number tuned to the hackathon) and follow these rules:

- `size` gives each unit the smallest size that meets its share of the peak under the case's constraints, and leaves a unit unsized (with a note) instead of guessing.
- Design values that set cost and are not fixed by the case (for example the heat pump and chiller capacities) can be searched: `minimize` takes them as variables when the caller lists them; the docstring and the example show how. Do not add them to `case.choices` (that section is not to be extended in this task).
- Acceptance: on the hackathon case, at least one searched candidate is feasible and at most as dear as the hand design (57.05 EUR/MWh with the same prices). If that is not reachable, report the best you got and the reason, with numbers.
- Tests on small plants: `size` on a case with a lower peak gives smaller units; a searched capacity variable changes the result as expected.

## 4. `compare`, `report` and readable tables (worker C)

- **Feasibility in `compare`:** a report is feasible if `passed` is `True`, it has no failed step, and it delivers every service the case asks for (a case with cooling demand needs `cold_delivered` with a value). `compare` ranks feasible reports first and puts only feasible reports on the Pareto front; each entry gets `feasible` and, if not, `reasons` (the failed constraints or the missing service).
- **Readable units:** `Comparison.to_frame(units=None)` and the sensitivity table's `to_frame(units=None)` show each metric in a display unit: the unit the report uses for that metric when printed (for example `EUR/MWh` for LCTS, `kt` for CO2), or the units given as `{metric: unit}`. Column names carry the unit (`lcts [EUR/MWh]`). The values inside `Comparison` and the sensitivity list stay `Quantity` in SI. The display unit comes from one table in `gemini/evaluate/` with the metric's quantity, never from the case.
- Tests: an infeasible report never on the front; a report with a missing service ranks after all feasible ones; `to_frame` with default and given units.

## 5. Priced injection pump and cited prices (worker D)

- **Injection pump:** `InjectionPump` declares the equipment kind `injection_pump` with `capex(finance)` per W of shaft power at the nominal flow and `fixed_opex(finance)`, like the production pump. A plant with an injection pump and no `finance.capex.injection_pump` raises `missing_assumption` naming that path. Test both.
- **Cited prices and cost factors for the sample cases.** For every value under `assumptions` in `inputs/examples/hackathon_2027/case.json` (and the same values in `shallow_district`): find a published source with web search, and use it only if you can open the page or document and see the figure. Write in the folder README, per value: the number used, the source (title, publisher, year, URL), the figure as the source states it and any conversion (currency year, unit). Prefer official or widely used references (national energy agencies, Danish Energy Agency technology catalogues, IEA, Eurostat, peer-reviewed papers). A value with no source you could verify stays as it is, marked "placeholder, no verified source" in the README. Never invent a source or a number. These values live only in `inputs/`, never in `gemini/`.
- Also list the two physics claims that still lack a source (the Arpagaus 10 to 80 K lift range and `lorenz_fraction` 0.5): search for a verifiable source; if found, cite it in the docstring where the value is used; if not, say so in the report.

## 6. Examples and docs (one worker, after the merge)

- `examples/hackathon.py`: search every candidate (the hand design too), print per candidate its feasibility and reasons, compare with readable units, and show the Pareto front of the feasible designs only. Use the evaluation count you need for section 3's acceptance; say the runtime (speed is not a goal here).
- `examples/costs.py`: the injection pump appears in the capex list.
- Docs: `api.md` (the geomind contract table: `minimize` result with `feasible`, `compare` entries with `feasible` and `reasons`, `to_frame(units=...)`; remove the "known limits" lines this task fixes), `conventions.md` if a rule changed, "unreleased changes". Every docstring touched.

## 7. Report

- Commits and the pushed hash; your worktrees and branches removed.
- The diagnosis summary and the fixes you chose.
- The hackathon table above, after the fixes: searched or not, feasible, reasons, LCTS, CO2, and the Pareto front.
- Every price and cost factor: new value and source, or "placeholder, no verified source".
- The two physics citations: found or not.
- Files changed, and confirmation that none of the speed task's files (section 0) were touched.
