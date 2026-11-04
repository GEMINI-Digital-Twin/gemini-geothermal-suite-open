# Task: Step 4: package layout, physics out of modules, one naming glossary, and what geomind needs

## 0. Context and rules

- Run this **after step 3** (`native-engine-step3.md`) and the interface freeze
  (`gemini-interfaces-freeze.md`, which replaced step 3b) are finished and reviewed. The freeze
  defined every public name (`.claude/docs/api.md`, pinned by the public-API snapshot and
  `gm.API_VERSION`), the plant builder and spec format, registries, `describe()` and units; in
  this step keep every public name and return shape unchanged while moving files, and skip any
  item below that the freeze already did. Start from the
  current local `refactor`. Read `.claude/docs/` (especially `native-engine.md` and
  `conventions.md`) and the step 3 report notes in `.tmp/native-engine/` first.
- The findings behind this prompt are in `gemini-cleanup-findings.md` (given next to this prompt). They
  were made on an older GitHub version, so re-check every item against the current code;
  report items that no longer apply.
- Standing rules: **no concept has two implementations**; **behaviour identical on every
  backend** (the parity suite from step 3 must stay green); physics and numbers do not change
  (every example and golden bit-identical, otherwise the documented `1e-12`).
- Work directly on branch `refactor` (no new branch, no PR). Commit there. **Do not push**
  until I have reviewed the commits.
- Read `AGENTS.md` and every file in `.claude/docs/` first and follow them.
- **Pre-check:** `git status` clean on `refactor`, and no other Claude session or process working
  **inside `gemini/`**. Sessions working in other folders of the workspace (for example
  the agent package `geomind/`) do not block you; if their load makes a 1 s budget test fail, rerun that test
  alone before treating it as a failure and say which ones you retimed.
- My workspace is `/Users/sahand/Desktop/crust-team`. This task changes **only**
  `/Users/sahand/Desktop/crust-team/gemini` (branch `refactor`). You may read, but not change,
  `geomind/`, `backend/`, `frontend/` and `infrastructure/`. Do not edit or commit `runs/`.
- Temporary files go to `.tmp/cleanup/` (git-ignored), never to `docs/`.
- **Work multi-agent and in parallel** (section 1b). Subagents run on a lighter model (sonnet
  for code, haiku for read-only searches), not the main model.
- **Tests:** development profile only (`make test` / `scripts/test_changed.py`, which always
  includes `test_code_quality.py`): tests of what changed and of everything that imports it, in
  parallel, under 300 s. Never run the whole suite or the slow dataset locally. New tests in the
  right tier, session fixtures, short-window dataset, no fast-tier test over about 1 s,
  xdist-safe. Never delete or shrink existing tests, datasets or goldens.
- **Quality bar** (as in `.claude/docs/conventions.md`): nesting at most 3, functions about
  40 lines max, flake8 `max-complexity = 10`, guard clauses, no dead or speculative code, no
  golfed code, full-word names, explicit `gm.errors` classes, a failing test before each bug
  fix. **No comments inside code**: only the fixed section headers and tool directives;
  explanations go in docstrings. No "magic" structures, keep the public API minimal. When
  unsure, follow PyTorch source patterns as a design reference only; never name torch in the
  repo. black, isort and flake8 clean.
- **Docs:** every commit that changes behaviour updates the matching file in `.claude/docs/`
  in the same commit; the new layout, the glossary and the "modules declare and wire, physics
  computes" rule go into the docs.
- If something else is needed (missing step, dependency, risk), say so in the report instead of
  staying silent.

## 1. Out of scope

Scan, Numba, fusion, C++, autodiff, scenario dimension, per-output compute methods for leaves,
turning fluid properties and correlation coefficients into graph inputs.

## 1b. Parallel plan

You are the coordinator. Create every worktree by hand from `refactor`
(`git worktree add -b <tmp> <path> refactor`); temporary branches are never pushed and are
deleted after merging. Merge one agent at a time and run the tests after each merge. Two agents
never edit the same file in the same wave.

- **Wave 1 (alone, mechanical):** section 2, the package layout. Everything else depends on the
  new paths, so do it first, in one commit, with no other change mixed in.
- **Wave 2 (in parallel):**
  - C (read-only, haiku): section 4.1, the naming inventory.
  - One agent per module group (same groups as step 2): section 3 (physics out of modules,
    unused parameters, module constants) for its own modules and physics files.
  - D: section 5.1 (`float32` removal), only after confirming no group agent touches the same
    files; otherwise move it to wave 3.
- **Wave 3:** section 4.2 (apply the glossary; touches everything, so one agent or you alone),
  then section 5.2 (`module.py` split).
- **Wave 4 (in parallel):** section 6 items, one agent each.
- In the report, say what ran in parallel and what had to be serialised.

## 2. Package layout

- Remove `gemini/core/`; move its folders to the top level of `gemini/`.
- Move `data/` and `legacy/` into `gemini/utils/` (`gemini.utils.data`, `gemini.utils.legacy`);
  move `runtime.py` next to the backends; `errors/` stays top level.
- Target: `gemini/{modules, physics, types, engine, ops, graph, backends, optim, errors, utils}`.
  Report anything else at the top level and where it should go.
- The public names exported from `gemini` (`gm.Dataset`, `gm.Engine`, ...) do not change.
  Everything other repos use must be in gemini's public `__all__` (pinned by
  `tests/unit/test_public_api.py`); keep `gm.utils` out of it.
- No compatibility shims for the old import paths; update every import, test, example, doc,
  `pyproject.toml` entry and CI path.
- **Stored files name classes by import path** (plant files, checkpoints, saved results store
  paths like `gemini.core...`), so the move would break loading them (the agent package's
  `FileWorkspace.plant` and old checkpoints). Fix the cause, not with a path alias: stored files
  name module and type classes by their stable registry name (for example `ESP`), never by
  import path, so future moves cannot break them. Bump the plant/checkpoint format version.
  Write a one-off migration script in `scripts/` that rewrites existing files (plant files under
  the repo, examples, `runs/` copies you are told about, and any path given on the command line)
  from the old format to the new one, and run it on every stored file inside `gemini/` in the
  same commit. Loading an old-format file without migrating raises a clear `gm.errors` message
  that names the script. Tell me which stored files outside `gemini/` (for example under
  `geomind/`) need the script run.
- The conversion is one public function, `gm.plants.migrate(old: dict) -> dict` (same for
  checkpoints if their format differs), used by the script and by other repos. The backend
  stores plant versions as JSON rows with `plant_type` holding a gemini class path, checks it
  against `gm.plants.__all__`, and swaps in the current path before `from_dict`; it will call
  this function in its own data migration, so do not touch the backend. After the change,
  `plant_type` and every class reference hold the registry name (for example
  `DoubletHeatPlant`), the dict carries a `format` version, and `gm.plants.__all__` (or the
  registry) is the list of valid plant names. Document this format in `.claude/docs/` and in the
  report, so the backend and geomind can follow it.
- **Public plant loading for other repos** (the backend needs it; its database has no real plant
  data yet, so it needs no migration):
  - `gm.plants.from_dict(data)` builds a plant from a stored dict when the class is not known in
    advance, resolving `plant_type` by registry name, and `gm.plants.get(name)` returns the plant
    class. One implementation: `Plant.from_dict` and these two share the same code.
  - `DoubletHeatPlant` is exported in `gm.plants`, and so is every other plant the examples or
    legacy import use.
  - `example_plant()` (or a new `gm.plants.example(name)`) returns a plant with real parameter
    values (the `doublet_heat` example values), so the backend and geomind can load and run it
    without the legacy files. Legacy import must work through the public API only.

## 3. Modules declare and wire, physics computes

1. A module only declares parameters, ports and outputs and calls physics functions. Move every
   formula from module files into the matching file in `physics/` as a public, tested function
   written with ops. Thin wrappers that only pass the module's own parameters to one physics
   function may stay. The findings list the heaviest cases (heat pump, heat exchanger, ice
   storage, aquifer storage, reservoir, borehole field, ESP efficiency, pipe, ORC, thermal
   storage, absorption/adsorption, CHP, cooler, centrifugal pump, valve, mixer, desander, cooling
   consumer).
2. Remove the duplicate concepts the findings name (pipe laminar drop next to
   `hydraulics`, `coolingconsumer._dew_point` next to `psychrometrics`) and any other you find.
3. Unused parameters (findings §3, re-check each): use them where the physics needs them,
   otherwise remove them and their legacy mappings. List every decision.
4. Physical constants defined in module files become `Constant` in `physics/constants.py`;
   numerical settings (iteration limits, segment counts) stay where they are used.
5. Fitting and plotting helpers (`fit_*`, `*_from_measurements`, `estimate_pressure`,
   `head_curve`): their formulas move to physics; the thin classmethods may stay on the module.
6. `health` stays optional (the base returns `None`).

## 4. One naming glossary

1. Inventory (read-only): every parameter, control, output, port and physics-function argument
   name across the package, with module, unit and meaning, grouped by concept. Write
   `.tmp/cleanup/names.md` and flag inconsistencies (findings §4: `no_stages` vs `stage_count`,
   `coeff` vs `coefficient`, `min_`/`max_` vs `minimum_`/`maximum_`, abbreviations like `dp`,
   `ua`, `m_dot`, `p_out`, `cop`, two names for one concept such as `carnot_efficiency` and
   `fraction_of_carnot`, the depth names, `setpoint` variants, `_calculate_outputs` vs
   `_compute_outputs`).
2. Write the glossary to `.claude/docs/glossary.md` (name, meaning, unit, used by) and apply it
   everywhere: modules, physics, outputs, results columns, legacy mappings, bindings, examples,
   docs. Stream fields (`p`, `T`, `m_dot`) may keep their short physics names if the glossary
   says so explicitly; decide once and apply consistently. Add a test that every declared name is
   in the glossary.
3. The backend stores plants as `Plant.to_dict()` and exports them in gemini's plant format.
   Every rename that changes that format must be listed, and the format gets a version number
   so old exports fail with a clear `gm.errors` message instead of loading wrongly.
4. List every rename in the report, especially results columns, because `geomind/` and
   `backend/` read them; search those folders (read-only) for every renamed column and list the
   hits.

## 5. Remove second modes and split `module.py`

1. **`float32` global precision:** remove it (`runtime.get_precision`, `_coefficients` and
   similar) with its float32 goldens moved to the float64 path only if they are duplicates;
   never delete a golden that checks something else. It is a second execution mode and a graph
   break.
2. **`module.py`:** split by concern into a few files (declarations and tree, dated parameter
   snapshots, formula outputs and sums, states, hooks, serialisation), keeping `Module` as the
   one public class. Check whether dated parameter snapshots (`params_at`, `apply_params_at`,
   `update_params`) are used outside tests and legacy loading; report, do not remove them in
   this step.

## 6. What the agent package needs from gemini

The agent package is `geomind` (`import geomind as gd`; `gm` stays gemini).
Its contract with gemini is in the shared `contracts.md` (given next to this prompt, Version 12
or later); follow it where it covers these items.


1. **`Module.describe()`:** a public method returning one JSON-serialisable dict: name,
   docstring summary, category, and every declaration (parameters, controls, inlets, outlets,
   outputs, states) with kind, unit, bounds, default, calibratable and soft-sensor flags. Works
   for leaves and composites (children nested). Schema comes from our own types, not pydantic.
   For composites it also lists the **connections** between children: from (module path, port),
   to (module path, port) and the stream type, so a flowsheet diagram can be drawn from it
   (the backend's `describe_plant` returns `modules[].category` and `connections[].stream`;
   follow `contracts.md` for the exact field names). `category` must be set for every module.
   Tests for a leaf, a composite and every module in the registry.
2. **Heating and cooling plant templates:** composite plants the agent can pick and size for
   Challenge 2 (deep geothermal heat supplying heating and cooling): at least a heating-only
   doublet plant, a doublet with heat pump boost, and a doublet with absorption chiller for
   cooling (plus storage if the existing modules allow it). Each template: clear sizing
   parameters, `describe()` output, an example, and a simulate test. Reuse existing modules;
   if a needed module is missing, say so instead of inventing physics.
3. **Economics:** `LCOH` and annual opex next to `total_cost` and emissions, as physics functions
   plus whatever the engine needs to report them per run. Document every assumption (discount
   rate, lifetime, prices) as parameters, not literals.
4. **Balances on simulated series:** confirm, with tests, that `energy_balance` and
   `mass_balance` work on simulated time series through the single runner; fix what does not.

## 7. Report

Commits, the layout move, every formula moved to physics, removed or used parameters, the
glossary and every rename (with hits in other folders), `float32` removal, the `module.py` split,
the agent-package items, behaviour changes, adapted tests (none deleted or weakened), anything that
turned out hard or wrong, and the next step you recommend.
