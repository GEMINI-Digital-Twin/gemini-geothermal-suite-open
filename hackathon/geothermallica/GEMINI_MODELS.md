# Our GEMINI models

Five model classes and one bug fix, written for TNO's GEMINI and living in its source tree on this branch. The
solution has no copies: it imports them from `src/` (`geo/gemini_path.py`: `GEMINI_DEV_SRC` if set, else this
branch's own `src/`).

| Model (registry name) | File in `src/` | What it does | Inputs | Tests |
|---|---|---|---|---|
| `ESPAffinity` (`esp_affinity`) | `gemini_model/pump/esp_affinity.py` | ESP with head and power read at q 60/f (pump similarity laws); GEMINI's `ESP` reads the 60 Hz curve at q | `pump_freq` (Hz), `pump_flow` (m3/s); same parameters as `ESP` | `unit_test/gemini_model/pump/test_esp_affinity.py`; `geo/test_gemini_models.py` (our pump, `geo.well.Producer`) |
| `HeatPumpLift` (`heatpump_lift`) | `gemini_model/heatpump/heatpump_lift.py` | `HeatpumpBasic` in Lorenz mode with a brine floor set per call, bracketed solve in the floor branch, COP capped at `cop_max` (8) | `T_brine_in_C`, `brine_flow_m3h`, `T_brine_floor_C`, `T_water_in_C`, `water_flow_m3h`, or `HeatpumpBasic`'s own keys | `unit_test/gemini_model/heatpump/test_heatpump_lift.py`; `geo/test_gemini_models.py` (COP and constants vs `geo.plant`) |
| `HenryGasBubblePoint` (`henry_gas`) | `gemini_model/fluid/henry_gas.py` | Bubble point of the dissolved CH4/CO2 by Henry's law with salting-out; gas, methane power and CO2 rates | `temperature` (K), `flowrate` (m3/s) | `unit_test/gemini_model/fluid/test_henry_gas.py`; `geo/test_gemini_models.py` (vs `geo.gas`) |
| `DoubletThermalBreakthrough` (`thermal_breakthrough`) | `gemini_model/reservoir/thermal_breakthrough.py` | Gringarten-Sauty breakthrough time, spacing for a lifetime, pressure interference between doublets | `flowrate` (m3/s) | `unit_test/gemini_model/reservoir/test_thermal_breakthrough.py`; `geo/test_gemini_models.py` (vs `geo.lifetime`) |
| `AbsorptionChiller` (`absorption_chiller`) | `gemini_model/chiller/absorption_chiller.py` | Brine heat above a drive floor (78 C, or what the exchanger still needs) to cold at COP 0.75, demand cap, 3 % auxiliary power | `pressure`, `temperature` (C), `flow_rate` (m3/s), optional `temperature_floor`, `cooling_demand` (W) | `unit_test/gemini_model/chiller/test_absorption_chiller.py`; `geo/test_gemini_models.py` (drive vs `plant._abs_drive`) |
| Injector friction sign | `gemini_simulator/nodal_solver.py` | Injection flow passed to DPDT as negative, so friction opposes the downward flow | - | `unit_test/gemini_simulator/test_injector_sign.py` |

`HeatpumpBasic` (TNO's) is also added to the registry as `heatpump`.

## The solver fix

`_well_bottomhole_pressure_injection` in `src/gemini_simulator/nodal_solver.py` passed the injection flow to DPDT as a
positive number with `direction = "down"`, so friction was added to the injection pressure instead of opposing the flow.
`solve_injection_flow_rate`, `solve_injection_wellhead_pressure` and `well_flow.solve_injector_wellhead_pressure_bar`
all go through this helper, so one line fixes all three:

```diff
         "temperature_ambient": wellhead_temperature,
-        "flowrate": flow_rate,
+        "flowrate": -flow_rate,  # signed: injection flows down, friction opposes it
         "direction": "down",
```

`unit_test/gemini_model/well/test_pressure_drop.py::test_calculate_bottomhole` (TNO's own) injects with a negative
flow rate and `direction = "down"`. `unit_test/gemini_simulator/test_injector_sign.py` fails on the old line and passes
on the new one. The DPDT docstring in `src/gemini_model/well/pressure_drop.py` now states the sign convention:
positive flow is upward (production), negative is downward (injection); `direction` only sets the walk order.
TNO's `unit_test/gemini_simulator/test_nodal_solver.py::test_solve_injection_flow_rate_balances_pressures` built its
reference with the old positive flow, so its reference DPDT call now passes `-flow_rate`; it fails otherwise.
`pyproject.toml` gains `testpaths = ["unit_test"]` so a bare `pytest` runs TNO's tests only.

## Cross-checks against the solution

From `hackathon/geothermallica/solution`:

```bash
PYTHONPATH=../../../src python -m unittest geo.test_gemini_models -v
```

Sources (each module docstring cites its own): Guelich (2014) Centrifugal Pumps, DOI 10.1007/978-3-642-40114-5; Ommen et al. (2015) Int. J. Refrig. 55,
DOI 10.1016/j.ijrefrig.2015.02.012; Arpagaus et al. (2018) Energy 152, DOI 10.1016/j.energy.2018.03.166;
US DOE (2017) Absorption Chillers fact sheet, https://www.energy.gov/sites/prod/files/2017/06/f35/CHP-Absorption%20Chiller-compliant.pdf
