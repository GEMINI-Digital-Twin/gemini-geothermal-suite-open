# Guide

A tour of the package, from the repository root with Python 3.11, 3.12, 3.13 or 3.14.

## Quickstart

The short form, on a sample case of the repository:

```python
import gemini as gm

case = gm.Case.from_json("examples/shallow_district/case.json")
plant = gm.Plant.from_json("examples/shallow_district/plants/HeatingHeatPumpCoolingPlant.json")
results = gm.simulate(plant, case)
report = gm.evaluate.report(plant, case, results)
print(report["heat_delivered"].to("MWh").value, report["lcts"].to("EUR/MWh").value)
```

A `gm.Case` holds what a plant is asked to do and the world around it: the time, the site,
the demand, the utilities, the requirements of third parties and the economics (prices, cost
factors, emission factors) of a run, in a `case.json` with its CSV files. The plant file holds only
the plant. `gm.check(plant, case)` lists what a run still lacks, and a `gm.Study` (`study.json`) records
which plants, cases and method to run. Every value with a unit is a `{"value": 150, "unit": "m3/h"}` or a `gm.units.Quantity`, text
such as `"150 m3/h"` is refused, and nothing a user must decide has a default: a value that is
missing raises `missing_value` naming its path. For measured inputs, `gm.simulate(plant, plan=frame)`
runs a DataFrame or `gm.Dataset` of the plant's inputs.

`gm.simulate`, `gm.replay`, `gm.live` and `gm.resume` cover a run in one call; `gm.Engine` is the
level for complex tasks, such as a run held in memory or a callback that reads the engine.

[examples/README.md](../examples/README.md) lists the five examples, starting with
`python examples/quickstart.py`; `python examples/hackathon.py` sizes, searches, simulates, checks,
reports and compares six candidate plants on a case. The longer tour, from the repository root with Python 3.11, 3.12,
3.13 or 3.14:

```python
import pandas as pd

import gemini as gm

plant = gm.Plant.from_json("tests/fixtures/doublet_heat/plant.json")
design = {
    name: parameter.value
    if parameter.unit in (None, "-")
    else gm.units.Quantity(parameter.value, parameter.unit)
    for name, parameter in plant.doublet.esp.named_parameters()
}
esp = gm.modules.ESP().set_params("", design)
stream = gm.Stream(flow={"value": 100, "unit": "m3/h"}, T={"value": 80, "unit": "C"}, p={"value": 20, "unit": "bar"}, fluid=gm.BRINE)
out = esp(fluid_in=stream, frequency={"value": 50, "unit": "Hz"})
assert out.outputs.head == esp({"fluid_in": stream}, frequency={"value": 50, "unit": "Hz"}).outputs.head
assert out.outputs.head == esp(stream, frequency={"value": 50, "unit": "Hz"}).outputs.head
print(out.outputs.get("head", unit="bar"), out.outlets.fluid_out)
assert out.outlets.fluid_out is out.outlets["fluid_out"]

with gm.modules.no_outputs():
    fluid_only = esp(fluid_in=out.outlets.fluid_out, frequency={"value": 50, "unit": "Hz"})
assert dict(fluid_only.outputs) == {}

esp.frequency = 50.0
plant.doublet.esp.frequency = {"value": 50, "unit": "Hz"}

frame = pd.read_csv("tests/fixtures/doublet_heat/doublet_2024_15min.csv", parse_dates=["time"])
data = gm.Dataset.from_frame(frame, time_column="time")

results = gm.replay(plant, data, checkpoint="runs/replay.ckpt")
print(results.to_frame(table="energy"))
print(results["doublet.esp"].power)
assert len(gm.resume("runs/replay.ckpt")) == len(results)

fit = gm.study.calibrate(plant, data, params=[plant.get("heat_exchanger.thermal_conductance")])
print(fit)
```

A module is built without arguments and configured with `set_params`, which returns it. Calls
accept inlets by keyword, mapping or position; controls given at the call apply to that call only,
while assignment (`esp.frequency = 50.0`, a bare SI number, author-level) persists them. A value with
a dimension given to `set_params`, `gm.Stream`, `gm.Fluid` or `gm.call` is a quantity: a bare number for it
raises `invalid_value`.

A leaf module computes and a plant connects: every composite is a `Plant` class that declares its
children, ports and connections, and `gm.Plant(name)` builds one with `add` and `connect`.
`gm.plants.names()` lists the plant classes, `gm.plants.get(name)` returns one without values.
The plant dict is the JSON form agents read and write: `plant.to_dict()`, `gm.Plant.from_dict`, `gm.plants.schema()`, and
`plant.to_json(path)`, `gm.Plant.from_json(path)` for a file. `gm.case` reads your demand, from a CSV
file (`gm.case.from_csv`) or from values (`from_values`). Readers are `from_<format>` and writers
`to_<format>` everywhere.

gemini converts every unit; a caller only chooses. `plant.to_dict(units=...)` and
`plant.to_json(path, units=...)` write the values in the units asked for, as a view does: a map
from quantity to unit (`{"thermal_conductance": "MW/K"}` writes 1 500 000 W/K as 1.5 MW/K),
`"display"` or `"si"`; without it each value stays as stated (else SI). A difference converts by
scale only, and `gm.Plant.from_json` reads a file in any unit that fits each value. A temperature in
`degC` is absolute; in a compound unit a degree is a difference, so `degC/km` equals `K/km` and
`W/m/degC` equals `W/m/K`. `gm.units.names(quantity)` lists the units a quantity takes.

gemini holds no data file. A sample project is a folder of `examples/` (its case, plants and
demand), in a source checkout and not installed; read a stored plant with `gm.Plant.from_json(path)`:

```text
examples/               # repository only
  quickstart.py ...     # the scripts
  shallow_district/     # a sample project: case.json, economics.json, plants/, data/
  hackathon_2026/       # another one, with its study files
tests/fixtures/         # what the tests read
  plants/               # example values of plants
  doublet_heat/         # measured data and the plant dict that fits it
  legacy_project/       # an old project folder
```

A plant can be designed from its depth. A `Doublet` derives its reservoir, wells and pump from a few
design values; the ground, the reservoir and the brine belong to the case, so one design runs on
several cases. `gm.schedule` plans each step from the demand of the case with no bindings to write,
`gm.evaluate.requirements` judges the run against the `requirements` of the case, and `gm.study`
sizes a design and searches the ranges its plant file states:

```python
case = gm.Case.from_json("examples/shallow_district/case.json")
plant = gm.Plant.from_json("examples/shallow_district/plants/HeatingHeatPumpCoolingPlant.json")
sized = gm.study.size(plant, case)
results = gm.simulate(sized, case)
checks = gm.evaluate.requirements(sized, case, results)
print([check["name"] for check in checks if check["passed"] is False])
```

`examples/hackathon.py` runs that path on the sample case of `examples/hackathon_2026/`, and
`examples/quickstart.py` on `examples/shallow_district/`, an hourly demand on one shallow
doublet, each with its own requirements. A control of a stored design is a leaf of the plant file
(`params.peak_boiler.temperature_setpoint`), and a template plant takes its size, `gm.plants.HeatingCoolingPlant(doublets=2)`.

Everything in the energy flow is a module and everything that crosses between modules goes through
a port. A plant starts at its edge modules: `ElectricityGrid`, `GasGrid`, `HeatingGrid`,
`CoolingGrid`, `WasteGrid`, `ChemicalGrid`, `Atmosphere` and `Formation`. Totals are read from them
(`gm.evaluate.totals(plant, case, results)`) and `gm.evaluate.plant_balance(plant, case,
results)` closes mass and energy on them.

The application, not the package, reads CSV, databases, or APIs. `Dataset` accepts pandas, dicts,
records, NumPy, and profiles already in memory. A plant owns bindings and dated parameters, so
engine and optimizer calls never take a separate configuration.

Report bugs with the output of `python -m gemini._utils.collect_env`.
