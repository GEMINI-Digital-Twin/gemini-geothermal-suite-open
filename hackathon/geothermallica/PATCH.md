# Upstream patch for GEMINI (development branch, commit d86e8bb)

Applied on the fork github.com/barteksarwa/gemini-geothermal-suite-open, branch `geothermallica`; this file
describes that diff. Line numbers are those of d86e8bb. The solution imports the five models from that tree
(`geo/gemini_path.py`); there are no copies in the solution.

## 1. Injector friction sign — `src/gemini_simulator/nodal_solver.py`, line 150

One line. `solve_injection_flow_rate`, `solve_injection_wellhead_pressure` and
`well_flow.solve_injector_wellhead_pressure_bar` all walk the injector through this helper, so all three are fixed by it;
`well_flow.py` itself needs no change (its +q into the IPR is right).

```diff
@@ def _well_bottomhole_pressure_injection(dpdt, flow_rate, wellhead_pressure, wellhead_temperature):
         "temperature_ambient": wellhead_temperature,
-        "flowrate": flow_rate,
+        "flowrate": -flow_rate,  # signed: injection flows down, friction opposes it
         "direction": "down",
```

Evidence: `unit_test/gemini_model/well/test_pressure_drop.py::test_calculate_bottomhole` injects with
`flowrate = -10/3600, direction = "down"` and expects friction -6264.02 Pa. Existing simulator tests to re-baseline:
`unit_test/gemini_simulator/test_injector_well.py` (its wellhead floors at 0.001 bar either way, so it should still pass)
and any nodal-solver test that compares injection numbers.

## 2. Docstring for DPDT — `src/gemini_model/well/pressure_drop.py`, line 67

```diff
-        flowRate = u["flowrate"]  # m3/s
+        # m3/s, signed: positive = upward (production), negative = downward (injection)
+        flowRate = u["flowrate"]
```

and in `calculate_output`'s docstring:

> `flowrate` is signed: positive = upward (production), negative = downward (injection); `direction` only sets the walk
> order (wellhead to bottom for "down", bottom to wellhead for "up").

## 3. Registry — `src/gemini_simulator/registry.py`

```diff
+from gemini_model.chiller.absorption_chiller import AbsorptionChiller
+from gemini_model.fluid.henry_gas import HenryGasBubblePoint
+from gemini_model.heatpump.heatpump_basic import HeatpumpBasic
+from gemini_model.heatpump.heatpump_lift import HeatPumpLift
 from gemini_model.injector_pump.injector_pump import InjectorPump
+from gemini_model.reservoir.thermal_breakthrough import DoubletThermalBreakthrough
@@ COMPONENT_REGISTRY = {
     "chp": CHP,
+    "absorption_chiller": AbsorptionChiller,
     "esp": ESP,
+    "esp_affinity": ESPAffinity,
+    "heatpump": HeatpumpBasic,
+    "heatpump_lift": HeatPumpLift,
+    "henry_gas": HenryGasBubblePoint,
     "producer_well": ProducerWell,
+    "thermal_breakthrough": DoubletThermalBreakthrough,
```

with `from gemini_model.pump.esp_affinity import ESPAffinity` beside the ESP import.

## 4. New files

- `src/gemini_model/pump/esp_affinity.py` (`ESPAffinity`)
- `src/gemini_model/heatpump/heatpump_lift.py` (`HeatPumpLift`)
- `src/gemini_model/fluid/henry_gas.py` (`HenryGasBubblePoint`)
- `src/gemini_model/reservoir/thermal_breakthrough.py` (`DoubletThermalBreakthrough`)
- `src/gemini_model/chiller/absorption_chiller.py` (`AbsorptionChiller`, new package `chiller/` with an `__init__.py`)
- tests: `unit_test/gemini_model/{pump,heatpump,fluid,reservoir,chiller}/test_*.py` and
  `unit_test/gemini_simulator/test_injector_sign.py`. The cross-checks against our plant model stay in the
  solution, `geo/test_gemini_models.py`, because they import `geo.plant` and `geo.well`.
