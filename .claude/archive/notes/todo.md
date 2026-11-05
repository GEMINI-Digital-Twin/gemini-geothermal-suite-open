# gemini: work done, agreed next steps and open questions (2026-10-30 21:00)

Repo `swarmax/gemini`, branch `refactor` (local `/Users/sahand/Desktop/crust-team/gemini`). Rules for every prompt: one concept = one implementation; identical behaviour on every backend; numbers and goldens unchanged; modules declare and wire, physics computes; develop on `refactor`, no push before review; prompts are written only when Sahand says «go».

## Done

1. Native engine steps 1–3: traced computation graph, one runner for replay/live/simulate, python and numpy backends with a parity suite, columnar results. Design: `prompts/native-engine-design.md`.
2. Interface freeze (`prompts/gemini-interfaces-freeze-full.md`): every public name in `.claude/docs/api.md`, pinned by a snapshot test; `gm.Plant` builder plus plant dicts; registries, `describe()`, units, `Results`, economics, KPIs, checks; unbuilt parts raise `NotImplementedYet`. Pushed at `58360ea`.
3. Module categories (`prompts/gemini-module-categories.md`): folder = category, 13 categories (subsurface, wells, pumps, treatment, exchangers, heating, cooling, power, storage, piping, demand, control, plants). API_VERSION 2.
4. `gemini/core` removed (`prompts/gemini-flatten-core.md`): modules, physics, types, engine at top level; data and legacy in `utils`; runtime in `backends`; schemas in `docs/schemas`; `gm.legacy` private. API_VERSION 3.

## In progress

5. Physics cleanup (`prompts/gemini-physics-cleanup.md`, given 19:32): physics only in `physics/`, no formulas or duplicates in modules, fitting out of modules, unused parameters removed, naming glossary, enforcement tests. API_VERSION 4.

## Agreed, not started

6. **`Module` base cleanup:** merge overlapping parameter methods (`update_params`, `set_params`, `apply_params_at`, `clear_param_overrides`); one getter instead of `get_parameter` / `get_control` / `get_boundary`; `to_dict`, `from_dict`, `save`, `load` only on `Plant`; engine-internal methods private (`start`, `advance`, `start_states`, `trial_outlets`); split `module.py` (1318 lines) into files per concern.
7. **Plant rewrite** (about 2100 lines in 19 files today):
   - `gemini/modules/plant.py` holds the `Plant` class; helpers in `modules/plants/`: `wiring.py` (ports, run order, loops; replaces `ports`, `plan`, old `wiring`) and `dicts.py` (`from_dict`, `to_dict`, `validate`, `schema`; replaces `reader`, `writer`, `schema`, `spec`, `factory`, `modules/serialization.py`).
   - Only `gm.plants.from_dict`, `plant.to_dict`, `gm.plants.validate`, `gm.plants.schema`; drop `from_spec`, `to_spec`, `spec_schema` and the word "spec" ("plant dict").
   - gemini takes and returns plain dicts only; JSON, YAML or databases are the caller's job. No JSON files inside Python package folders.
   - **No templates in gemini:** remove `templates/`, `templating.py`, `generators.py`, `catalogue.py`, `library.py`, `gm.plants.templates`, `from_template` and the plant JSON files in `specs/`.
   - **Well-known plants are modules:** registered `gm.Plant` subclasses in `modules/plants/`, wired in `__init__` with `add` and `connect`, usable in Python and as a `type` in a plant dict.
   - `loops.py` moves into `HeatingSubstation`; plant outputs through the existing `Output.of` / `Output.ratio`; `nodal.py` to `gm.analysis`; `legacy_project.py` to `utils/legacy`.
   - Target about 800–900 lines of plant tooling in three files.
8. **contracts.md and other repos:** update `phases/contracts.md` with the new categories, plant names and API versions; backend template route becomes "start from an empty plant dict or another project"; geomind builds plants from plant dicts and keeps any starting plants itself; backend and geomind tests use `gm.plants.Doublet`, which no longer exists (use the registry); `backend/tests/core/gemini/test_plant.py` and `backend/AGENTS.md` still mention `gemini.core`.

## Open questions for Sahand

- Which plants count as well-known (proposed: Doublet, DoubletHeatPlant, MultiWellPlant, DistrictNetwork, HeatingSubstation, CoolingSubstation, ATESPlant)?
- Real example values (for example `doublet_heat`) as class defaults, or empty defaults with real values only in tests?
- Remove `plant.save(path)` and `Module.load(path)`?
- Remove `gm.plants.migrate` and `migration.py` (backend database is empty; a one-off script if old files appear)?
- Public route for old-project CSV data and the other legacy functions, or keep them private?

## Gaps for Challenge 2

- No module declares a capex, so LCOH and NPV return `null`.
- No hot or cold storage in a heating-and-cooling plant: needs `state` connections, which wait for scan.
- No demand profiles: `gm.profiles.get` raises `NotImplementedYet` until the hackathon demand data is found.
- `gm.analysis.injectivity`, `calibrate_pump`, `calibrate_corrosion`, `erosion` are signatures only.

## Later topics (discussed, not decided)

Scan for stateful modules and `state` connections; incremental checkpoint; autodiff (own or an optional JAX/torch backend); Numba vs C++; fusion; scenario dimension; calibration on the graph; fluid properties and correlation coefficients as graph inputs; per-output methods for leaf modules; generating the three hand-written schemas from code.
