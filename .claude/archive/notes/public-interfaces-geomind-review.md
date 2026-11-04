# geomind review of gemini-public-interfaces.md (draft 1)

From the geomind thread, 2026-10-30. Checked against geomind's tools (design §4, §12.2), the S2 code on crust-team/geomind main, the analyst/designer/verifier/economist agents and Challenge 1 (agent-written modules).

## Answers to the questions

1. Yes: final signature now, raising `NotImplementedYet`, plus sample JSON files. geomind's FakeLLM tests and evals can then run against the samples before the code exists.
2. `gm.analysis`: fine. geomind does not need it in S2/S3.
3. `.npz` is fine, but add `results.to_bytes()` / `gm.Results.from_bytes(data)` next to `save(path)` / `load(path)`. geomind stores results through `Workspace` and `RunStore.save_artifact`, which the backend implements on MinIO; a file path does not exist there.
4. Lists: fine. Add `cooling_tower` (or put it under `chiller`) if dry/wet coolers are separate modules.
5. One plant with switchable units plus presets: yes. It is the best fit for agents, since one `configure_plant` tool can cover it.
6. Yes. Also: geomind checks `gm.API_VERSION` at import and raises a clear error on a mismatch.

## Missing or wrong for geomind

### Must have (blocks S2b/S3)

1. **Everything returned is plain JSON.** `describe()`, `to_dict()`, `summary()`, `evaluate()`, `kpi()`, economics and checks return only dict/list/str/float/int/bool/None: no numpy scalars, NaN as `null`, no pandas. They go straight into tool results and events. Pin it with a `json.dumps(..., allow_nan=False)` test per function.
2. **`gm.evaluate`:** `module` accepts a registry name or a class. Inputs accept numbers in SI or `"150 m3/h"` strings. The return value is fixed: `{outputs: {name: {value, unit}}, outlets: {port: {field: {value, unit}}}, errors: [code], checks: [...]}`.
3. **Building a plant from a template:** `gm.plants.from_template(name, parameters)` (or say that `get(name)(**parameters)` is the way). geomind `configure_plant` needs one call. Also `gm.plants.templates()` should return each template's parameter schema, or point to `describe()`.
4. **Demand profiles (Challenge 2):** `simulate` needs a heating and cooling demand profile, so there is nothing to design against without one. Add `gm.profiles.names()` / `gm.profiles.get(name)` for at least one design year (hourly heating and cooling demand, ambient temperature), plus the profile format (columns and units) written down as a schema.
5. **Reading plant values:** on an instance, `plant.describe()` (or `describe(values=True)`) includes the current parameter values. geomind `read_plant` shows that to the model; `to_dict()` is a storage format, not a readable view.
6. **Results by reference:** `Results.get(path, field, start=None, end=None)` and `summary(path=None)`, so `read_result` can ask for a slice without loading everything into the context.

### Agent-written modules (Challenge 1, S3)

7. **`gm.testing.check_module(cls)` returns a report and does not raise:** `[{rule, passed, message}]`. It runs inside the sandbox, and geomind passes the report to the model.
8. **Using a new module in a plant:** `gm.modules.register(cls, name=None, category=...)`, and a way to load a module from a file (`gm.modules.load_file(path)`). A plant dict that names an unregistered module raises `UnknownNameError` with the name, and does not silently pass. This is the only way an agent-written module can join a simulated plant, inside the sandbox.
9. A module template, or a `.claude/docs/modules.md` section, that geomind can ship as its `writing-a-gemini-module` skill text unchanged.

### Economics and verification (S3/S4)

10. **Economics assumptions in one object:** `gm.economics.Assumptions` (prices, discount rate, lifetime, currency and year, CO2 factors) with documented defaults and `describe()`. Every function takes it, and every return carries units, e.g. `capex` = `{total: {value, unit: "EUR"}, by_module: {path: {...}}}`. The economist agent cites these numbers and must know where they come from (source per default).
11. Add `npv` and `payback` next to `lcoh`/`lcoc`, so alternatives can be compared on more than one number.
12. **`gm.kpi`** returns `{name: {value, unit, description}}`, and `gm.kpi.names()` lists the fixed names. The problem state's `metric` field is validated against that list.
13. **Checks:** add `gm.checks.run_all(plant, results)` -> list of `{name, passed, value, tolerance, unit, message}`, including bounds checks (temperatures and pressures inside declared limits). The `Verified` hook on `before_finish` calls only this.
14. **Determinism:** the same plant, profile and backend always give the same results bit for bit. geomind's replay and evals rely on it; say it in api.md.

### Nice to have (bonus points)

15. Optimisation: `gm.optim.minimize(plant, variables, objective, constraints)`, with variables as dotted parameter paths and bounds from `describe()`. Signature now, `NotImplementedYet` until built.
16. Uncertainty: `engine.simulate(profile, samples=...)` or `gm.uncertainty.sample(plant, distributions, n)`. Signature only.

## Unchanged and fine

Registry (`gm.modules.names/get`, `gm.plants.*`), `describe()` shape, `GeminiError.to_dict()` (geomind already returns `{error: {class, message}}`, and will use `to_dict()` as it is), `gm.units`, `Engine` / `simulate`.
