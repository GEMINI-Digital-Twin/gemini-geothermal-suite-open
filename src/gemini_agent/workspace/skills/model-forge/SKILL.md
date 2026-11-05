---
name: model-forge
description: How to create a missing component model at runtime (declarative JSON spec -> validated, unit-tested, registered GEMINI component). Read before calling generate_model.
---
# Model Forge

Pass the spec to `generate_model` as `spec_json`: one JSON object with double-quoted keys
(a single line is fine; a dict is also accepted).

Use when a needed technology/calculation is not in `list_gemini_models` (e.g. seasonal storage,
network heat loss, a new chiller type). You write a JSON spec; the forge validates, generates the
GEMINI class, runs your tests and registers the model only if they pass.

Rules: snake_case names (>= 2 chars); expressions use declared names, numbers, + - * / ** %, comparisons,
`a if cond else b`, and min max abs exp log log10 sqrt pow sin cos tanh. Outputs may use earlier outputs.
Give at least one test with a hand-checked expected value, and physical invariants (energy cannot grow).

Example (seasonal HT-ATES screening):
```json
{"name": "ht_ates_screening",
 "description": "HT-ATES seasonal storage screening",
 "reference": "HEATSTORE: recovery efficiency 0.6-0.8",
 "inputs": {"summer_surplus_gwh": {"unit": "GWh"}, "winter_boiler_gwh": {"unit": "GWh"}, "annual_heat_gwh": {"unit": "GWh"}},
 "parameters": {"recovery_efficiency": {"value": 0.7}, "storage_capacity_gwh": {"value": 25.0}},
 "outputs": {"stored_gwh": {"expr": "min(summer_surplus_gwh, storage_capacity_gwh)"},
             "recovered_gwh": {"expr": "stored_gwh * recovery_efficiency"},
             "boiler_after_gwh": {"expr": "max(0, winter_boiler_gwh - recovered_gwh)"}},
 "invariants": ["recovered_gwh <= stored_gwh", "boiler_after_gwh >= 0"],
 "tests": [{"inputs": {"summer_surplus_gwh": 28.5, "winter_boiler_gwh": 31.5, "annual_heat_gwh": 111.67},
            "expect": {"recovered_gwh": 17.5, "boiler_after_gwh": 14.0}}]}
```
Workflow: seasonal_balance(design_id) -> generate_model(spec) -> run_model(name, inputs from seasonal_balance).
If generate_model returns problems, fix exactly those and retry.
