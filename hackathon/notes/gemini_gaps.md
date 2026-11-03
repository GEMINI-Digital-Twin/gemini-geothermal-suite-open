# GEMINI capability gaps found while building the design workflow

Branch: `development`. Status: **fix** (changed or added code), **work around**
(computed outside GEMINI and fed in), **flag** (documented limitation).
Status is proposed by Claude; the owner decides.

| # | Gap | Evidence | Proposed status | Where handled |
|---|-----|----------|-----------------|---------------|
| 1 | Wellhead temperature is a boundary input, not computed from the reservoir | `boundary_inputs: wellhead_temperature` in project .json | Work around | `subsurface.wellhead_temperature_c`: GEMINI DPDT marched upward, formation T per segment as ambient |
| 2 | Fluid is pure water at standard conditions (1000 kg/m3, 1.0 mPa·s, cp 4217) | `gemini_model/fluid/pvt_water_stp.py` | Work around | `subsurface.brine_properties()` swaps in brine constants |
| 3 | PVT validity capped at 100 C | `temperature_max = 100 + 273.15` | Flag (constants are used anyway) | Raised to 200 C in our brine class |
| 4 | No gas in the wellbore (gas mass fraction 0) | `PVTConstantSTP GMF = 0` | Flag | Gas handled only at the separator |
| 5 | Well heat loss uses fixed U = 10 W/m2K and one ambient temperature | `pressure_drop.py: Uvalue = 10` | Work around (ambient per segment); flag U | `wellhead_temperature_c` |
| 6 | Productivity index must be supplied | `productivity_index_m3h_per_bar` input | Work around | `subsurface.productivity_index_m3h_bar` (Darcy radial) |
| 7 | Heat pump model exists but is not registered in the simulator | `gemini_model/heatpump` missing from `registry.py` | Use directly; registering is a possible contribution | `surface.py` |
| 8 | No chiller, storage or annual (daily) dispatch | nothing in `gemini_model` | Add | `surface.py`, `dispatch.py` |
| 9 | Boiler/CHP heating value is pure methane (50 MJ/kg) | template `caloric_value` | Work around | `subsurface.gas_properties`: 29.5 MJ/kg for 80/20 CH4/CO2 |
| 10 | Example ESP curve is a ~200 m3/h pump: saturates at ~240 m3/h, negative head at 300 m3/h | ESP scan, any stages/frequency | Flag + work around | Design mode: generic pump, dP·Q/0.70 (brief's efficiency) |
| 11 | **Injector friction has the wrong sign**: DPDT always adds friction walking down; for injection the walk follows the flow | `pressure_drop.py: pressure + dp_fric + dp_grav`; `nodal_solver._well_bottomhole_pressure_injection` passes +Q | **Fix candidate** (one line: pass −Q); bug report + test to GEMINI | `subsurface._injector_wellhead_pressure_corrected_bar`. At 300 m3/h: 15.9 bar as-is vs 26.4 bar corrected (hand calc 26.5) |
| 12 | Default flow bracket (0.01–700 m3/h) lets the nodal solve land on a spurious root (~602 m3/h, ESP intake 0 bar) | ESP scan | Work around | `gemini_project.configure_doublet_project` sets 1–350 m3/h |

## Validation at 2,500 m (design mode D vs GEMINI project mode A vs hand estimate C)

| Q m3/h | Producer pump D / A (ESP curve) / C, MW | Injector WHP D / A (as-is) / C, bar |
|---|---|---|
| 100 | 0.084 / 0.082 / 0.084 | 5.93 / 4.71 / 5.93 |
| 150 | 0.154 / 0.133 / 0.154 | 10.62 / 7.94 / 10.62 |
| 200 | 0.245 / 0.249 / 0.245 | 15.60 / 10.89 / 15.60 |
| 300 | 0.495 / n.a. (ESP limit) / 0.495 | 26.40 / 15.94 / 26.40 |

Leg B (reference hand calculation from the owner's references) is still to add.
