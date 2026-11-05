# Our GEMINI models

Five model classes and one bug fix, written for TNO's GEMINI and living in its source tree on the fork
github.com/barteksarwa/gemini-geothermal-suite-open, branch `geothermallica`. The solution has no copies: it imports
them from that tree (`geo/gemini_path.py`: `GEMINI_DEV_SRC`, else the fork's own `src/` when the solution sits inside
it, else `~/src/gemini-geothermallica/src`). The diff against TNO's `development` branch is in `PATCH.md`.

| Model (registry name) | File in `src/` | What it does | Inputs | Tests |
|---|---|---|---|---|
| `ESPAffinity` (`esp_affinity`) | `gemini_model/pump/esp_affinity.py` | ESP with head and power read at q 60/f (pump similarity laws); GEMINI's `ESP` reads the 60 Hz curve at q | `pump_freq` (Hz), `pump_flow` (m3/s); same parameters as `ESP` | `unit_test/gemini_model/pump/test_esp_affinity.py`; `geo/test_gemini_models.py` (our pump, `geo.well.Producer`) |
| `HeatPumpLift` (`heatpump_lift`) | `gemini_model/heatpump/heatpump_lift.py` | `HeatpumpBasic` in Lorenz mode with a brine floor set per call, bracketed solve in the floor branch, COP capped at `cop_max` (8) | `T_brine_in_C`, `brine_flow_m3h`, `T_brine_floor_C`, `T_water_in_C`, `water_flow_m3h`, or `HeatpumpBasic`'s own keys | `unit_test/gemini_model/heatpump/test_heatpump_lift.py`; `geo/test_gemini_models.py` (COP and constants vs `geo.plant`) |
| `HenryGasBubblePoint` (`henry_gas`) | `gemini_model/fluid/henry_gas.py` | Bubble point of the dissolved CH4/CO2 by Henry's law with salting-out; gas, methane power and CO2 rates | `temperature` (K), `flowrate` (m3/s) | `unit_test/gemini_model/fluid/test_henry_gas.py`; `geo/test_gemini_models.py` (vs `geo.gas`) |
| `DoubletThermalBreakthrough` (`thermal_breakthrough`) | `gemini_model/reservoir/thermal_breakthrough.py` | Gringarten-Sauty breakthrough time, spacing for a lifetime, pressure interference between doublets | `flowrate` (m3/s) | `unit_test/gemini_model/reservoir/test_thermal_breakthrough.py`; `geo/test_gemini_models.py` (vs `geo.lifetime`) |
| `AbsorptionChiller` (`absorption_chiller`) | `gemini_model/chiller/absorption_chiller.py` | Brine heat above a drive floor (78 C, or what the exchanger still needs) to cold at COP 0.75, demand cap, 3 % auxiliary power | `pressure`, `temperature` (C), `flow_rate` (m3/s), optional `temperature_floor`, `cooling_demand` (W) | `unit_test/gemini_model/chiller/test_absorption_chiller.py`; `geo/test_gemini_models.py` (drive vs `plant._abs_drive`) |
| Injector friction sign | `gemini_simulator/nodal_solver.py` | Injection flow passed to DPDT as negative, so friction opposes the downward flow | - | `unit_test/gemini_simulator/test_injector_sign.py` |

`HeatpumpBasic` (TNO's) is also added to the registry as `heatpump`.

Run the cross-checks from this folder:

```bash
GEMINI_DEV_SRC=~/src/gemini-geothermallica/src ../../.venv/bin/python -m unittest geo.test_gemini_models -v
```

Sources: Guelich (2014) Centrifugal Pumps, DOI 10.1007/978-3-642-40114-5; Ommen et al. (2015) Int. J. Refrig. 55,
DOI 10.1016/j.ijrefrig.2015.02.012; Arpagaus et al. (2018) Energy 152, DOI 10.1016/j.energy.2018.03.166;
US DOE (2017) Absorption Chillers fact sheet, https://www.energy.gov/sites/prod/files/2017/06/f35/CHP-Absorption%20Chiller-compliant.pdf
