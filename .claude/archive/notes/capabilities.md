# List of gemini capabilities

The status of each capability is shown with a mark:
- ✅ built (on `refactor`, after the redesign and part one)
- 🔧 gets built in part two
- 🆕 new geomind need, not decided yet
- ⚪ exists, but is not used for the competition (operations and digital twin)

---

# 1. Building a plant

## 1.1 Ready-made plants

### Template classes ✅
```
HeatingPlant, HeatingCoolingPlant, HeatingFullCoolingPlant,
HeatingAbsorptionCoolingPlant, HeatingHeatPumpCoolingPlant
```
### Number of doublets and depth 🔧
```python
HeatingCoolingPlant(size={"doublets": 3});  plant.set_params({"depth": "3000 m"})
```
### Subsurface plants ✅
```
Doublet, NodalDoublet, MultiWellPlant(size={"wells": n})
```
### Network and substation plants ✅
```
DistrictNetwork(size={"consumers": n}), HeatingSubstation, CoolingSubstation
```
### Combined and example plants ✅
```
DoubletHeatPlant, HackathonPlant, BoilerChpPlant, DistrictEnergyPlant,
ParallelExchangerPlant, ATESPlant
```
### Catalogue ✅
```python
gm.plants.names(category=...);  gm.plants.get(name);  gm.plants.example(name)
```

## 1.2 Custom plant

### Building with code ✅
```python
plant = gm.Plant("p");  plant.add(type, name, params);  plant.connect("a.out", "b.in")
```
### Plant outputs ✅
```
Output.difference(a, b), Output.ratio(a, b), Output.sum(a, b, ...)
```
### Constraints and loops ✅
```python
self.constrain("riser.wellhead_out.p", equals="wellhead_pressure", by="reservoir.production_rate")
```
The engine closes loops itself (Wegstein, `loop_not_converged` error).

## 1.3 Plant dictionary (agent interface)

### Reading and writing ✅
```python
gm.plants.from_dict(d);  plant.to_dict();  plant.to_dict(structure=True)
```
### Validation and schema ✅
```python
gm.plants.validate(d);  gm.plants.schema()
```
### Saving inputs (setpoints) 🔧
```python
plant.set_inputs({"heat_pump.temperature_setpoint": "100 degC"})   # + key "inputs" in the dict
```

## 1.4 Values

### Parameters ✅
```python
plant.set_params({...}, valid_from=...);  plant.params_at(path);  plant.param_history(path)
plant.missing_parameters();  plant.get(path)
```
### Plant description ✅
```python
plant.describe();  plant.help();  plant.named_modules()
```
### Fluid and brine 🆕
Density, viscosity, GLR and gas composition from the brief, stored in the plant dictionary (need to check how much of it exists now).

---

# 2. Modules (equipment)

## 2.1 Subsurface

### Reservoir and well ✅
```
ProductionReservoir, InjectionReservoir, ProductionWell, InjectionWell, ThermalDecline
```
### Shallow geothermal ✅
```
BoreholeField, DownholeHeatExchanger, AquiferStorage
```

## 2.2 Pumps

### Well and injection pumps ✅
```
ESP, LineShaftPump, InjectionPump, CentrifugalPump, GasCompressor
```
### Circulation pump ✅
```
CirculationPump   # new in the redesign
```

## 2.3 Heating

### Heat production ✅
```
HeatPump, Boiler, ElectricBoiler, CHP
```
### Exchangers ✅
```
HeatExchanger, Cooler
```

## 2.4 Cooling

### Chillers ✅
```
AbsorptionUnit, AdsorptionChiller   # compression chiller = HeatPump in cooling mode
```
### Dispatching chillers by role 🔧
The compression chiller and the adsorption chiller are also dispatched, with `cooling_order`.

## 2.5 Storage

### Thermal storage ✅
```
ThermalStorage, IceStorage, AquiferStorage
```

## 2.6 Brine and gas operations

### Treatment ✅
```
Degasser, Filter, Desander, Blowdown, InhibitorDosing, Flare, Separator
```
### Power generation ⚪
```
ORC, FlashTurbine
```

## 2.7 Piping and control

### Piping ✅
```
Pipe, Valve, Mixer, Splitter, PressurizationTank, GasMakeup
```
### Control ✅
```
PIDController
```

## 2.8 Networks and boundaries

### Demand networks ✅
```
HeatingGrid, CoolingGrid   # outputs: unmet_demand; surplus 🔧
```
### Supply and environment networks ✅
```
ElectricityGrid, GasGrid, WasteGrid, ChemicalGrid, Atmosphere, Formation
```

## 2.9 Writing a new module (challenge 1)

### Module catalogue ✅
```python
gm.modules.names(category=...);  gm.modules.get(name);  gm.modules.categories()
```
### Registering and loading ✅
```python
class X(gm.Module): def forward(self, inlets): ...
gm.modules.register(X);  gm.modules.load_file(path)
```
### Module test ✅
```python
gm.testing.check_module(X);  gm.evaluate(X, params, inlets, controls)   # volume flow: "flow"
```
### Docker sandbox 🔧
`docker/sandbox.Dockerfile`, with `make sandbox-image`.

---

# 3. Input data

## 3.1 Profiles

### Ready-made profiles ✅
```python
gm.profiles.names();  gm.profiles.get(name)   # attrs: units, quantities, source
```
### User profile 🆕
```python
gm.profiles.from_values(...);  gm.profiles.from_csv(...)   # with validation, shorter than a year
```

## 3.2 Requirements and rules

### schedule rules ✅ (a dictionary for now)
```
order, doublet_flow, max_brine_cooling, operating_days
```
### Competition preset 🔧
Competition rules in one general place (50 to 300 m3/h, 40 K, 330 days).
### Requirements as data 🆕
```python
gm.Requirements(...);  gm.Requirements.preset("hackathon_2027")
```

---

# 4. Running

## 4.1 Daily schedule

### schedule ✅
```python
plan = gm.schedule(plant, demand, rules)
```
### Operating days ✅
`operating_days`: a number (the lowest-demand days, spread across doublets) or a list of dates.

## 4.2 Simulation

### simulate ✅
```python
results = gm.simulate(plant, plan)
```
### Evaluating one module ✅
```python
gm.evaluate(module, params, inlets, controls)
```

## 4.3 Results

### Reading ✅
```python
results["path.to.field"];  results.to_frame();  results.to_bytes();  gm.Results.from_bytes(b)
```

## 4.4 Operational run ⚪
```python
gm.replay(...);  gm.live(...);  gm.resume(...);  gm.Engine;  gm.Clock;  gm.Dataset
```

---

# 5. Result analysis

## 5.1 KPI

### Totals and KPIs ✅
```python
gm.kpi.totals(plant, results);  gm.kpi.compute(plant, results);  gm.kpi.names()
```
### Useful and surplus heat 🔧
Useful heat (at most equal to the demand) next to delivered heat and `surplus`.
### Capacity of each unit 🆕
```python
gm.kpi.capacities(plant, results)   # peak heat pump, chiller, boiler, doublet
```

## 5.2 Checks

### Balance ✅
```python
gm.checks.energy_balance;  gm.checks.mass_balance;  gm.checks.plant_balance;  gm.checks.bounds
gm.checks.run_all(plant, results)
```
### Limits ✅
```python
gm.checks.Limits().add("d*.flow", min="50 m3/h", max="300 m3/h");  gm.checks.limits(...)
```
### Operating days ✅
```python
gm.checks.operating_days(plant, results, days)
```
### Competition requirements 🔧
`volume_imbalance` for each doublet, `Limits` on parameters (pump efficiency), and the result `passed: null` for a run without the column.
### One check for all requirements 🆕
```python
gm.checks.requirements(plant, results, requirements)   # failed days, grids, gas burned, limits
```

## 5.3 Economics

### Cost ✅
```python
gm.economics.Assumptions(...);  gm.economics.capex(...);  gm.economics.opex(...)
```
### Levelized cost ✅
```python
gm.economics.lcoh;  gm.economics.lcoc;  gm.economics.lcts;  gm.economics.annualised_cost
```
### Cash flow and carbon ✅
```python
gm.economics.npv;  gm.economics.payback;  gm.economics.co2
```

## 5.4 Summary for comparison 🆕
One call that gives KPI, cost and checks together for comparing options.

---

# 6. Design and optimization

## 6.1 Initial size guess 🆕
```python
gm.design.doublet_capacity(depth, flow, brine_cooling);  gm.design.doublets_for(peak)
```

## 6.2 Optimization ✅
```python
gm.optim.minimize(plant, profile, variables, objective, constraints, evaluations, assumptions)
```
### Defaults and speed 🔧
`profile=None` means the hackathon year, schedule in each trial, and a target of under 1 second per trial.

## 6.3 Uncertainty ✅
```python
gm.optim.sample(plant, profile, distributions, metrics, count, seed, assumptions)
```

## 6.4 List of capabilities 🆕
`gemini` itself says what it can run and what it cannot (instead of writing it in the agent prompt).

---

# 7. Operational analysis (digital twin) ⚪

## 7.1 Well and pump

### nodal ✅ (production) / 🔧 (injection)
```python
gm.analysis.nodal;  gm.analysis.injectivity;  gm.analysis.pump_curve
```
### Calibration ⚪
```python
gm.analysis.calibrate_pump;  gm.analysis.fit_head_coefficients;  gm.analysis.fit_head_correction
gm.optim.calibrate
```

## 7.2 Integrity ⚪
```python
gm.analysis.calibrate_corrosion;  gm.analysis.corrosion_forecast;  gm.analysis.erosion
```

## 7.3 Reservoir ⚪
```python
gm.analysis.estimate_reservoir_pressure;  gm.analysis.estimate_conductance
```

---

# 8. Infrastructure

## 8.1 Units ✅
```python
gm.units.convert(value, unit, target)   # unit strings everywhere: "3000 m", "150 m3/h"
```

## 8.2 Errors ✅
```
GeminiError, ValidationError, DefinitionError, PhysicsError, RunError, Cancelled, NotImplementedYet
gm.errors.CODES, ROW_CODES
```

## 8.3 Base types ⚪
```
Stream, Ports, Fluid, BRINE, WATER, Quantity, Profile, streams, runtime, no_outputs,
ModuleList, ModuleDict
```

## 8.4 Backends ✅
python and numpy with the same result; graph trace for speed.
