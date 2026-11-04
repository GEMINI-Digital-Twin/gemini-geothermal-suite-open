# Task: Module and Plant redesign: leaves compute, plants connect; no JSON files in gemini

## 0. Context and rules

- This is a new session. Read `AGENTS.md` and every file in `.claude/docs/` first and follow them.
- Start from the current local `refactor`. These commits must be in; if they are not, stop and tell me:
  - the data layout (`gemini/assets/`, `inputs/`);
  - the modules layout (`gemini/modules/plant.py`, `container.py`, `plants/_utils/`).
- **Main idea:** a leaf module computes, and a plant connects. No class does both.
  - A leaf `Module` has physics and one method, `forward`.
  - Every composite is a `Plant`: it declares children, ports and connections in `__init__`, and never writes `forward`.
  - Plants are defined in Python. gemini keeps no JSON file. JSON exists only as the dict interface that agents (geomind) use: `gm.plants.from_dict`, `plant.to_dict`, `gm.plants.schema`, `validate`.
- The decisions below were made with me one by one. Where one does not fit the code, stop that section and say why in the report instead of inventing another design.
- **Version:** do **not** change the version (nothing is released). Add the change-log lines under "unreleased changes" in `api.md`.
- **Git:** work directly on branch `refactor` (no new branch, no PR). One commit per section below, in order. **Do not push** until I have reviewed the commits.
- **Pre-check:** `git status` is clean on `refactor`, and no other Claude session or process is working inside `gemini/`. Sessions in other folders do not block you. If their load makes a 1 s budget test fail, rerun that test alone before treating it as a failure, and say which tests you retimed.
- **Scope:** workspace `/Users/sahand/Desktop/crust-team`. Change only `gemini/` (the repository). You may read `geomind/` and `backend/`, but never change them.
- **Temporary files** go to `.tmp/redesign/` (git-ignored).
- **Agents:** one agent is enough. Subagents, if any, run on a lighter model and only do read-only searches.
- **Tests:**
  - Use the development profile only (`make test` / `scripts/test_changed.py`, always including `test_code_quality.py`), run in parallel, under 300 s.
  - Run the e2e tier (it runs every example) once at the end, against a baseline taken before the first change.
  - Numbers stay identical, except where loop closing moves from a plant into the engine (section 3). There, list each changed number, the old and new value, and why. A difference within the old loop tolerance is expected; anything larger is a bug to find.
  - Never run the slow dataset locally.
  - Never delete or shrink goldens or `inputs/` data.
- **Quality bar** as in `.claude/docs/conventions.md`:
  - simple, readable, just enough code;
  - nesting at most 3, functions about 40 lines at most, guard clauses;
  - explicit `gm.errors` with codes;
  - no comments inside code (docstrings only; the fixed section headers stay);
  - black, isort and flake8 clean;
  - write a failing test before each bug fix.
- If something else is needed, say so in the report.

## 1. Leaf modules: `forward` only

- A leaf module computes once, in `forward(self, inlets)`: it calls physics, assigns its outputs (`self.cop = ...`) and returns its outlets.
- Remove `_compute_outputs` from `Module` and from every module (about 40 today). Where a module computed the same thing twice (for example `HeatPump._performance` called from both), it is now computed once.
- Engine, graph tracing and every backend must still capture outputs assigned inside `forward`. If a backend needs a change for that, make it, and keep backend parity.
- Add a code-quality test: no class under `gemini/modules/` defines `_compute_outputs`.

## 2. Every composite is a `Plant`; plants never write `forward`

**The shape of a plant class:**

```python
class HeatingSubstation(Plant):
    def __init__(self):
        super().__init__()

        # Modules
        self.valve = Valve()
        self.heat_exchanger = HeatExchanger()
        self.consumer = HeatingGrid()
        self.pump = CirculationPump()

        # Parameters

        # Inlets
        self.supply_in = Inlet(Stream, kind="hot_water")

        # Outlets
        self.return_out = Outlet(Stream, kind="hot_water")

        # Connections
        self.connect("supply_in", "valve.fluid_in")
        self.connect("valve.fluid_out", "heat_exchanger.hot_in")
        self.connect("heat_exchanger.hot_out", "return_out")
        self.connect("heat_exchanger.cold_out", "consumer.supply_in")
        self.connect("consumer.return_out", "pump.fluid_in")
        self.connect("pump.fluid_out", "heat_exchanger.cold_in")

        # Outputs
```

**The rules:**
- `Plant.forward` is written once, in `gemini/modules/plant.py`. It runs the children in connection order and closes loops (section 3).
- No subclass of `Plant` defines `forward`. A code-quality test enforces this.
- No `Module` subclass may hold child modules except through `Plant`. A leaf has no children (also a code-quality test).
- Children assigned as attributes (`self.valve = Valve()`) are registered as with `add`; `add(type, name, params)` still works.
- A plant may override `set_params` to derive its children's values from design values (the `Doublet` pattern). The formulas go into physics, not into the plant file.
- **Doublet:** its derivation helpers (`_derived`, `_column`, `_flow_paths`, `_pump`, about 100 lines) move to `gemini/physics/` or `modules/subsurface/_physics.py`. The plant keeps only a short `set_params`.
- The bookkeeping `Doublet` carries today (`_baselines`, `_stated`, its `to_spec` override, its `fluid` setter) is done once in `Plant` for every plant:
  - explicit values given in a call are remembered and win over derived ones;
  - derived values are never stored;
  - the plant's fluid passes to its children.

**Rewrite every composite as a `Plant` with this shape:**
- `ATESPlant`, `HeatingSubstation`, `CoolingSubstation`, `NodalDoublet`
- `Doublet`, `DoubletHeatPlant`, `MultiWellPlant`, `DistrictNetwork`
- `HackathonPlant`, `BoilerChpPlant`, `DistrictEnergyPlant`, `ParallelExchangerPlant`
- any other composite you find.

**Flow in loops.** Where a substation fixed its building-circuit flow with a parameter (`building_flow`, and the like), the flow now comes from a pump module in the loop, so it is part of the energy flow and its electricity is counted. Use the existing pump that fits, or add a simple `CirculationPump` with a fixed flow, a pressure rise and an efficiency (cited default). Say which.

## 3. Loops and nodal solves in the engine

**Loops.**
- Move loop closing out of plants and into the plant plan:
  - `plants/_utils/loops.py`, `close_loop` (Wegstein, tolerance, max passes, `PhysicsError`);
  - every `trial_outlets` use.
- A connection that closes a cycle is a tear stream. `Plant.forward` iterates the cycle until the tear stream converges, the same way for every plant.
- Tolerance and maximum passes are settings with today's values. On failure, raise `PhysicsError` with code `loop_not_converged` and the tear path.
- It must trace and run the same on every backend. If a backend cannot, stop and report.

**Nodal solve.**
- `NodalDoublet` finds the production rate at which reservoir, well, ESP and riser deliver a wellhead pressure, and the injection pressure the injector needs. Today it does this in `forward`. Express it instead as a constraint on the plant that the engine solves:

```python
self.constrain("riser.wellhead_out.p", equals="wellhead_pressure", by="reservoir.flow")
```

- Choose the exact name and form. Keep it small: one target path, one value (a parameter or boundary path), and one free variable path with bounds. Use the existing `ops.brentq`.
- `plants/_utils/nodal.py` keeps only the physics it needs, or moves to `gm.analysis` (a public `nodal` analysis already planned). Say where.
- `BoilerChpPlant` and `ParallelExchangerPlant` use `NodalDoublet` and must print the same numbers.

## 4. Plant outputs: combinations only

- Remove `Output.of`. Anything it aliased is read by path: a child's output (`results["sub.consumer.unmet_demand"]`) or a port quantity (`results["sub.heat_exchanger.hot_out.T"]`). Update every use, example and doc.
- A plant's own outputs are only combinations of paths. Allowed forms:
  - `Output.difference(a, b)`
  - `Output.ratio(a, b)`
  - `Output.sum(a, b, ...)`
- Paths are strings, so they store the same way in a plant dict (`"outputs": {"brine_cooling": {"difference": ["riser.wellhead_out.T", "injector.wellhead_in.T"]}}`).
- The engine computes them after the children, traced, the same on every backend.
- Simplify `plants/_utils/outputs.py` and the formula code in `module.py` to these three forms. Delete any other form.

## 5. No JSON files in gemini

- Delete `gemini/assets/plants/` and `gemini/assets/templates/`, and with them every reader of plant or template files:
  - `plants/_utils/library.py` (`fill`, `shipped`, `register_shipped`);
  - the file parts of `catalogue.py`;
  - `templating.py`'s file loading.
- If `gemini/assets/` is then empty, delete it and its paths entry. The rule becomes: no data files inside `gemini/`. Update the code-quality test, `data.md` and `conventions.md`.
- **Well-known plants** are the Python classes of section 2, registered by class name in the module registry.
- **Templates become plant classes.**
  - The five spec templates (`heating_only`, `heating_cooling`, `heating_full_cooling`, `heating_absorption_cooling`, `heating_heat_pump_compression_cooling`) become plant classes with the same modules, wiring and parameters. Suggested names: `HeatingPlant`, `HeatingCoolingPlant`, `HeatingFullCoolingPlant`, `HeatingAbsorptionCoolingPlant`, `HeatingHeatPumpCoolingPlant`. Choose clearer names if they exist, and list them.
  - The `enabled` switches and `bypass` rules of optional units are removed. An agent removes a unit by editing the plant dict.
  - The two generator templates (`district_network`, `multi_well`) become `DistrictNetwork` and `MultiWellPlant` classes that take their size (number of consumers or wells) as a constructor argument. `to_dict` stores it next to `type` (for example `{"type": "MultiWellPlant", "size": {"wells": 3}, "params": {...}}`). Choose one key name for every structural argument and document it.
  - `gm.plants.templates()` and `from_template` are removed, together with `templating.py` and `generators.py`. Anything an agent used them for is now `gm.plants.names(category=...)` plus `gm.plants.get(name)`. If geomind uses them, list file and line.
- **`gm.plants.example(name)`** stays: `get(name)` plus `set_params` with the values in `inputs/plants/<name>.json`. Rename or add value files for renamed plants and for the new template plants. A plant without values raises `NotImplementedYet` as today.
- **The dict interface** stays and gets simpler:
  - **Class plants:** a plant that is an instance of a registered class stores `{"type": <class name>, "params": {...}}` (plus `size` if it has one), never its structure or derived values.
  - **Plants built with `gm.Plant(name)` + `add`/`connect`:** these have no class and store `modules`, `connections`, `inlets`, `outlets` and `outputs`.
  - **Round-trip:** `gm.plants.from_dict(plant.to_dict())` rebuilds the same plant with the same numbers, for every shipped plant and example (a test).
  - **Schema:** `gm.plants.schema()` is generated from code: the dict shape, the enum of registered types, the output forms. It is the input schema of an agent's plant-building tool. Make sure it describes the shape above and nothing removed.
  - `validate` keeps reporting problems (`unconnected_port`, `unknown_name` with suggestions, ...) on the dict paths.
- Remove `to_spec`, `from_spec` and the word "spec" from names and docs; the term is "plant dict". `migration.py` (format 1 to format 2) stays only if `inputs/legacy_project` or a test needs it; say which.

## 6. Smaller Module API

Public methods of `Module` after this section:

- **Tree and declarations:** `named_modules`, `modules`, `children`, `named_children`, `get_submodule`, `named_parameters`, `parameters`, `controls`, `boundaries`, `states`, `inputs`, `outputs`, `inlets`, `outlets`, `soft_sensors`
- **Values:** `set_params`, `params_at`, `param_history`, `set_bindings`, `bindable`, `missing_parameters`, `is_initialized`
- **Lookup:** `get(path)` returns the declaration at a path, whatever its kind. It replaces `get_parameter`, `get_control` and `get_boundary`.
- **Run:** `forward`, `__call__`, `register_forward_pre_hook`, `register_forward_hook`, `state_dict`, `load_state_dict`, `health`
- **Description:** `describe`, `help`, `capex`

The rest changes as follows:
- `update_params`, `apply_params_at` and `clear_param_overrides` are removed. `set_params` with `valid_from` covers them. Find every caller.
- `offer`, `offered_outlets`, `start_states`, `trial_outlets`, `set_inputs`, `has_input_value` and `initial_state` / `step` (if only the engine calls them) become private (leading underscore). Engine and backends are updated. If a module author must still override one, such as `initial_state` / `step` for stateful modules, keep that one public and say so.
- `to_dict`, `from_dict`, `save` and `load` live only on `Plant`. A single module is stored by wrapping it in a plant.
- `describe` and `parameter_schema` stop being `_ClassOrInstance` descriptors that work on both the class and an instance. Choose one form (instance methods, or class methods if no instance state is needed), use it everywhere, and remove `_ClassOrInstance`.
- List every public name removed or renamed, with what replaces it. Update `.claude/docs/api.md` and the API snapshot test.

## 7. Docs

Update:
- `modules.md`: leaf versus plant, the shapes of both with the section headers, loops and constraints, outputs;
- `plants.md`: plant classes, the dict interface, round-trip, schema, no files;
- `api.md`: unreleased changes and removed names;
- `conventions.md`, `data.md`, `engine.md`, `equipment.md`, `AGENTS.md` ("Start here"), the README;
- `examples/` (`write_a_module`, `basics/03` and `06` show the new shapes);
- every docstring touched.

## 8. Report

- Commits, one per section.
- Composites rewritten, and the pump added or used for loop flows.
- Every changed number from the baseline, with old and new value and the reason (sections 2 and 3).
- How the engine closes loops (tear choice, tolerance), and the constraint form chosen for the nodal solve.
- New names of the template plants, and the structural-argument key.
- Removed public names, with replacements.
- Round-trip test results for every shipped plant.
- What this breaks in `geomind/` and `backend/` (read-only, file and line): templates, `from_template`, `to_spec`, `Output.of` paths, removed methods, shipped plant names.
