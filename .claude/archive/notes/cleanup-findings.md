# GEMINI modules and physics: cleanup findings (2026-10-30)

Source: GitHub `swarmax/gemini` branch `refactor` at `c2e4b9f`. This is older than the local
branch (step 2 and step 3 changes are not on GitHub), so file names and some details may have
moved; the structural points still hold. Input for the next prompt, not yet a prompt.

## 1. Folder layout (agreed in discussion)

- Remove `gemini/core/`; its folders move to the top level of `gemini/`.
- `data/` and `legacy/` move into `gemini/utils/` (like `torch.utils.data`).
- `runtime.py` next to `backends/`; `errors/` stays top level (`gm.errors`).
- Target: `gemini/{modules, physics, types, engine, ops, graph, backends, optim, errors, utils}`.

## 2. Rule: modules declare and wire, physics computes

A module only declares parameters/ports/outputs and calls physics functions. Formulas go to
`physics/`. Module files with the most arithmetic (binary operations counted):

| module | arithmetic | private helpers that are physics |
|---|---|---|
| heat/heatpump.py | 52 | `_performance`, `_cop`, `_source_outlet_T`, `_sink_outlet_T` |
| heat/heatexchanger.py | 40 | `_heat_balance`, LMTD/approach in `_performance`, `ua_from_measurements` |
| storage/icestorage.py | 38 | `_rate`, `_effectiveness`, `_conductance`, `_sensible`, `_latent` |
| subsurface/aquiferstorage.py | 36 | `_decay`, `_production_temperature`, `_store_conductance`, ... |
| subsurface/reservoir.py | 33 | `_calculate_outputs`, `estimate_pressure`, `*_from_measurements` |
| subsurface/boreholefield.py | 33 | `_ground_temperature`, `_effective_conductance`, ... |
| pumps/esp.py | 33 | `efficiency_function` |
| piping/pipe.py | 31 | `_laminar_drop` (Hagen-Poiseuille written inline), `_outlet_temperature` |
| power/orc.py | 29 | `_design` |
| storage/thermalstorage.py | 25 | `_conductance`, `_circuit_heat`, `_outlet_temperature` |
| heat/absorptionunit.py, adsorptionchiller.py, chp.py, cooler.py | 17-25 | `_performance`, `_available_duty` |
| pumps/centrifugalpump.py | 23 | `_performance` |
| piping/valve.py, mixer.py; treatment/desander.py | 11-15 | `_pressure_drop`, `_mixed_temperature` |
| demand/coolingconsumer.py | 12 | `_dew_point` (psychrometrics exists in physics) |

Duplicate concepts found: `pipe.py` writes the laminar drop itself while
`physics/hydraulics.darcy_weisbach_dp` exists; `coolingconsumer._dew_point` next to
`physics/psychrometrics`. Thin wrappers that only pass the module's own parameters to one physics
function (`ESP.head_function`) may stay.

## 3. Unused parameters (declared, never read by their module)

`ESP.pump_type`, `ESP.setting_depth`, `ESP.correction_factor`, `ESP.tubing`,
`InjectionPump.pump_type`, `_Reservoir.liquid_density`, `_Reservoir.liquid_viscosity`,
`Degasser.heat_transfer_coeff`. Most are filled only by `legacy/tables.py`. Use or remove.

## 4. Naming is inconsistent (full-word rule and same concept, same name)

- Counts: `no_stages` (ESP, 3 modules) vs `stage_count` (gas compressor) vs `borehole_count`.
- Coefficients: `head_coeff`, `power_coeff`, `heat_transfer_coeff` vs `evaporator_coefficient`,
  `heat_loss_coefficient`, `rejection_coefficient`.
- Limits: `min_flow`/`max_flow` vs `minimum_*`/`maximum_*` vs `output_min`/`output_max`.
- Abbreviations against the full-word rule: `dp`, `dp_nominal`, `dp_hot_nominal`, `clogging_dp`,
  `ua`, `u_value`, `m_dot_*`, `p_out`, `cop`.
- Same concept, two names: `carnot_efficiency` vs `fraction_of_carnot`; `correction_factor` vs
  `correction_factors`; depth: `esp_depth`, `setting_depth`, `depth`, `top_depth`; `thickness` vs
  `aquifer_thickness`; `setpoint` vs `temperature_setpoint` / `pressure_setpoint`.
- Method names: `reservoir._calculate_outputs` next to the standard `_compute_outputs`.
- Proposal: one glossary in `.claude/docs/` (name, meaning, unit) and every parameter, output and
  physics argument follows it. Renames touch legacy mappings, bindings and examples.

## 5. Other points

- `float32` global precision (`runtime.get_precision`, `ESP._coefficients` and similar): a second
  execution mode, against "one implementation per concept", and a graph break. Proposal: remove.
- `health` is optional (base returns `None`); only 5 modules implement it. Keep optional.
- Fitting and plotting helpers in module classes (`ESP.fit_head_coefficients`,
  `fit_head_correction`, `head_curve`, `HeatExchanger.ua_from_measurements`,
  `Reservoir.*_from_measurements`, `estimate_pressure`): off the run path. Proposal: the formulas
  move to physics; whether the thin classmethods stay on the class is open.
- `module.py` is about 1,200 lines with ~120 methods: declarations, tree navigation, dated
  parameter snapshots (`params_at`, `apply_params_at`, `update_params`), formula outputs, states,
  hooks, serialisation. Candidate to split by concern (as torch splits `Module` helpers), and to
  check whether dated parameter snapshots are still needed.
- Module-level constants in modules (`DEFAULT_CP`, `LAMINAR_REYNOLDS`, `COMMERCIAL_STEEL_ROUGHNESS`,
  `REFERENCE_DENSITY`, `MAX_SEGMENTS`, ...): physical ones become `Constant` in
  `physics/constants.py`; numerical settings stay where used.

## 6. Needs from the agent package geomind

1. Public `Module.describe()` returning one JSON dict: name, docstring summary, category, and
   every declaration with its schema, unit and bounds. (With pydantic leaving, schemas come from
   our own types.)
2. Heating-and-cooling plant templates the agent can pick and size (biggest risk for
   Challenge 2).
3. LCOH and annual opex next to `total_cost` and emissions.
4. Confirm `energy_balance` and `mass_balance` work on simulated time series (now also through
   the single runner).
- The agent package CI checks out `origin/refactor`, so it cannot pass until local `refactor` is pushed.
