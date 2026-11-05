# Files of a complete gemini project (proposal, 2026-11-01 21:45)

Not implemented yet. Values are the competition sample where known; anything marked "illustration" is made up to show the shape.

## Folder

```
my_project/
  scenario.json            the world: time, site, demand, market, requirements
  market_high_price.json   optional: one section shared or swapped by another scenario
  scenario_high_price.json optional: second scenario reusing site/demand, other market
  data/
    demand.csv             profiles (demand, air temperature, time-varying prices)
    measurements.csv       optional: measured data of a real plant (operation loop)
  plants/
    heat_cool.json         one file per plant; parameters with value, and optional range/options
    heat_pump.json
  study.json               what to run: scenarios x plants, method, objective, budget, seed
  results/                 written by result.to_folder(); never edited by hand
```

Runtime settings (processes, tolerances) are not a file: they do not change results.

## 1. scenario.json

Each of `site`, `demand`, `market`, `requirements` is either inline or a path to a file of the same shape. Uncertainty sits next to the value it belongs to.

```json
{
  "name": "base",
  "time": {"start": "2027-01-01", "end": "2028-01-01", "step": {"value": 1, "unit": "d"}},
  "site": {
    "ground": {"surface_temperature": {"value": 12, "unit": "degC"},
               "gradient": {"value": 30, "unit": "K/km"}},
    "reservoir": {"reference_depth": {"value": 2500, "unit": "m"},
                  "thickness": {"value": 100, "unit": "m"},
                  "permeability": {"value": 200, "unit": "mD",
                                   "uncertainty": {"kind": "triangular", "min": 100, "max": 300}},
                  "pressure": {"value": 250, "unit": "barg"},
                  "pressure_at_other_depth": "hydrostatic"},
    "fluid": {"density": {"value": 1030, "unit": "kg/m3"},
              "viscosity": {"value": 0.4, "unit": "mPa.s"},
              "gas_liquid_ratio": {"value": 0.8, "unit": "Nm3/m3"},
              "gas": {"CH4": 0.8, "CO2": 0.2}},
    "air": {"temperature": {"value": 10, "unit": "degC"}}
  },
  "demand": {
    "file": "data/demand.csv", "time_column": "date",
    "heating": {"column": "heating_demand_MWth", "unit": "MW",
                "supply_temperature": {"value": 100, "unit": "degC"},
                "return_temperature": {"value": 60, "unit": "degC"}},
    "cooling": {"column": "cooling_demand_MWcool", "unit": "MW",
                "supply_temperature": {"value": 20, "unit": "degC"},
                "return_temperature": {"value": 25, "unit": "degC"}}
  },
  "market": "market_base.json",
  "requirements": [
    {"name": "doublets", "on": "doublet", "quantity": "count", "min": 1, "max": 3},
    {"name": "flow", "on": "doublet", "quantity": "production_flow", "over": "each", "when": "running",
     "min": {"value": 50, "unit": "m3/h"}, "max": {"value": 300, "unit": "m3/h"}},
    {"name": "brine cooling", "on": "doublet", "quantity": "brine_cooling", "over": "each", "when": "running",
     "max": {"value": 40, "unit": "K"}},
    {"name": "running days", "on": "doublet", "quantity": "running_time", "over": "sum",
     "max": {"value": 330, "unit": "d"}},
    {"name": "heat met", "on": "heating_supply", "quantity": "unmet", "over": "max",
     "max": {"value": 0, "unit": "W"}},
    {"name": "cold met", "on": "cooling_supply", "quantity": "unmet", "over": "max",
     "max": {"value": 0, "unit": "W"}}
  ]
}
```

## 2. market_base.json (a section in its own file)

Values should cite rows of `docs/cost-sources/sources.csv` in the example README.

```json
{
  "currency": "EUR",
  "price_year": 2015,
  "discount_rate": {"value": 0.04, "uncertainty": {"kind": "uniform", "min": 0.03, "max": 0.06}},
  "lifetime": {"value": 25, "unit": "yr"},
  "capex": {
    "drilling": {"value": 1845, "unit": "EUR/m"},
    "heat_pump": {"value": 0.738, "unit": "EUR/W"},
    "compression_chiller": {"value": 0.159, "unit": "EUR/W"},
    "absorption_chiller": {"value": 0.234, "unit": "EUR/W"},
    "heat_exchanger": {"value": 0.5, "unit": "EUR/(W/K)"},
    "production_pump": {"value": 0.5, "unit": "EUR/W"},
    "injection_pump": {"value": 0.5, "unit": "EUR/W"},
    "pipe": {"value": 1149, "unit": "EUR/m"}
  },
  "opex": {
    "fixed": {"heat_pump": {"value": 2, "unit": "%/yr"}, "drilling": {"value": 1, "unit": "%/yr"}},
    "electricity": {"value": 105.75, "unit": "EUR/MWh",
                    "uncertainty": {"kind": "triangular", "min": 70, "max": 160}},
    "gas": {"value": 39.92, "unit": "EUR/MWh"},
    "co2": {"value": 57.03, "unit": "EUR/t"}
  },
  "revenue": {"heat": {"value": 81.11, "unit": "EUR/MWh"}, "cold": {"value": 81.15, "unit": "EUR/MWh"}},
  "emissions": {"CO2": {"electricity": {"value": 209.2, "unit": "g/kWh"}}, "CH4": {"gwp": 29.8}}
}
```

`scenario_high_price.json` (illustration) reuses everything but the market:

```json
{"name": "high price", "time": "scenario.json#time", "site": "scenario.json#site",
 "demand": "scenario.json#demand", "market": "market_high_price.json",
 "requirements": "scenario.json#requirements"}
```

(Open: whether a path may point into another scenario with `#section`, or shared sections must be their own files.)

## 3. plants/heat_cool.json

A plant built from a class: `type` plus parameters. A parameter is `{"value", "unit"}`; it may add `range` (the designer frees it for search) or `options` (a discrete choice). `value` is always required: the starting point and the value used in a plain run. A range must lie inside the module's physical bounds.

```json
{
  "type": "HeatingCoolingPlant",
  "params": {
    "d0": {
      "count": {"value": 2, "range": {"min": 1, "max": 3}},
      "depth": {"value": 3000, "unit": "m",
                "range": {"min": {"value": 2000, "unit": "m"}, "max": {"value": 3500, "unit": "m"}}},
      "well_diameter": {"value": 0.2, "unit": "m"},
      "roughness": {"value": 0.05, "unit": "mm"},
      "pump_efficiency": 0.7,
      "esp": {
        "pump_type": {"value": "standard", "options": ["standard", "gas_handler"]},
        "minimum_intake_pressure": {"value": 5, "unit": "bar"},
        "maximum_gas_fraction": 0.1875
      }
    },
    "heat_pump": {
      "heat_capacity": {"value": 8, "unit": "MW",
                        "range": {"min": {"value": 3, "unit": "MW"}, "max": {"value": 30, "unit": "MW"}}},
      "carnot_fraction": 0.5
    },
    "chiller": {
      "cold_capacity": {"value": 10, "unit": "MW"}
    }
  }
}
```

(Illustration: `gas_handler` does not exist in gemini yet; capacities and ranges are made up.)

A plant built from scratch carries its structure instead of `type`: `modules` (name -> module type + params, same parameter form), `connections` (`"d0.out" -> "hx.hot_in"`), and optional `outputs`. Same reader, same `to_json`, same parameter form, so ranges and options work the same way.

## 4. study.json

The study only says what to run and how; free parameters come from the plants, uncertainty from the scenarios.

```json
{
  "name": "design",
  "scenarios": ["scenario.json"],
  "plants": ["plants/heat_cool.json", "plants/heat_pump.json"],
  "prepare": {"size": {"backup": "peak"}},
  "method": "minimize",
  "objective": "lcts",
  "evaluations": 20,
  "metrics": ["lcts", "co2", "capex"],
  "allocation": {"heat_cost_share": 0.8},
  "seed": 1
}
```

The same plants under uncertainty:

```json
{
  "name": "risk",
  "scenarios": ["scenario.json"],
  "plants": ["results/design/heat_cool/best.json"],
  "method": "sample",
  "samples": 200,
  "metrics": ["lcts", "co2"],
  "allocation": {"heat_cost_share": 0.8},
  "seed": 1
}
```

Operation loop (illustration, not designed yet):

```json
{"name": "calibrate 2028", "scenarios": ["scenario_2028.json"], "plants": ["plants/as_built.json"],
 "method": "calibrate", "measurements": "data/measurements.csv", "seed": 1}
```

## 5. Run

```python
import gemini as gm

study = gm.Study.from_json("study.json")
with gm.runtime.settings(processes=8):
    result = study.run()
result.compare().to_frame()
result.to_folder("results/design")
```

## 6. results/ (generated)

```
results/design/
  compare.json
  heat_cool/
    best.json            the plant with the best values (a runnable plant file)
    scenario.json        copy of the inputs used
    report.json
    verdict.json
    series.parquet
  heat_pump/
    ...
```

## Rules in one place

| file | holds | who changes it |
| --- | --- | --- |
| scenario (+ section files) | world; uncertainty next to values | nobody by design |
| data/*.csv | profiles, measurements | data owner |
| plants/*.json | design; ranges and options next to values | designer |
| study.json | what to run, method, budget, seed, cost allocation | analyst |
| runtime | processes, tolerances | whoever runs it |
| results/ | outputs | generated |
