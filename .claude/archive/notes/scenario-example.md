# A complete scenario (proposal, 2026-11-01 20:40)

The competition sample written in the proposed shape. Nothing is implemented yet. Names (`Scenario` or `Basis`) still open.

Rule: the scenario holds only what nobody changes by designing the plant: time, site, demand, market, requirements. Uncertainty sits next to the value it belongs to. Each section may be written inline or given as a path to a file of the same shape.

Tags in the source list below: [O] organiser brief, [V] verified source (cost-sources), [S] secondary source, [A] our assumption, no source.

## scenario.json

```json
{
  "name": "competition base",

  "time": {
    "start": "2027-01-01",
    "end": "2028-01-01",
    "step": {"value": 1, "unit": "d"}
  },

  "site": {
    "ground": {
      "surface_temperature": {"value": 12, "unit": "degC"},
      "gradient": {"value": 30, "unit": "K/km"}
    },
    "reservoir": {
      "reference_depth": {"value": 2500, "unit": "m"},
      "thickness": {"value": 100, "unit": "m"},
      "permeability": {"value": 200, "unit": "mD",
        "uncertainty": {"kind": "triangular", "min": 100, "max": 300}},
      "pressure": {"value": 250, "unit": "barg"},
      "pressure_at_other_depth": "hydrostatic"
    },
    "fluid": {
      "density": {"value": 1030, "unit": "kg/m3"},
      "viscosity": {"value": 0.4, "unit": "mPa.s"},
      "gas_liquid_ratio": {"value": 0.8, "unit": "Nm3/m3"},
      "gas": {"CH4": 0.8, "CO2": 0.2}
    },
    "air": {
      "temperature": {"value": 10, "unit": "degC"}
    }
  },

  "demand": {
    "file": "data/demand.csv",
    "time_column": "date",
    "heating": {
      "column": "heating_demand_MWth",
      "unit": "MW",
      "supply_temperature": {"value": 100, "unit": "degC"},
      "return_temperature": {"value": 60, "unit": "degC"}
    },
    "cooling": {
      "column": "cooling_demand_MWcool",
      "unit": "MW",
      "supply_temperature": {"value": 20, "unit": "degC"},
      "return_temperature": {"value": 25, "unit": "degC"}
    }
  },

  "market": {
    "currency": "EUR",
    "price_year": 2015,
    "discount_rate": {"value": 0.04,
      "uncertainty": {"kind": "uniform", "min": 0.03, "max": 0.06}},
    "lifetime": {"value": 25, "unit": "yr"},
    "capex": {
      "drilling": {"value": 1845, "unit": "EUR/m"},
      "heat_pump": {"value": 0.67, "unit": "EUR/W"},
      "absorption_chiller": {"value": 0.234, "unit": "EUR/W"},
      "compression_chiller": {"value": 0.159, "unit": "EUR/W"},
      "dry_cooler": {"value": 0.07, "unit": "EUR/W"},
      "pipe": {"value": 1149, "unit": "EUR/m"},
      "production_pump": {"value": 0.5, "unit": "EUR/W"},
      "degasser": {"value": 1000000, "unit": "EUR"}
    },
    "opex": {
      "fixed": {
        "heat_pump": {"value": 2, "unit": "%/yr"}
      },
      "electricity": {"value": 100, "unit": "EUR/MWh",
        "uncertainty": {"kind": "triangular", "min": 70, "max": 160}},
      "gas": {"value": 40, "unit": "EUR/MWh"},
      "co2": {"value": 80, "unit": "EUR/t"}
    },
    "revenue": {
      "heat": {"value": 90, "unit": "EUR/MWh"},
      "cold": {"value": 90, "unit": "EUR/MWh"}
    },
    "allocation": {"heat_cost_share": 0.8},
    "emissions": {
      "CO2": {"electricity": {"value": 209.2, "unit": "g/kWh"}},
      "CH4": {"gwp": 29.8}
    }
  },

  "requirements": [
    {"on": "doublet", "quantity": "count", "min": 1, "max": 3},
    {"on": "doublet", "quantity": "production_flow", "over": "each", "when": "running",
     "min": {"value": 50, "unit": "m3/h"}, "max": {"value": 300, "unit": "m3/h"}},
    {"on": "doublet", "quantity": "brine_cooling", "over": "each", "when": "running",
     "max": {"value": 40, "unit": "K"}},
    {"on": "doublet", "quantity": "running_time", "over": "sum",
     "max": {"value": 330, "unit": "d"}},
    {"on": "doublet", "quantity": "pump_efficiency", "equals": 0.7},
    {"on": "heating_supply", "quantity": "unmet", "over": "max",
     "max": {"value": 0, "unit": "W"}},
    {"on": "cooling_supply", "quantity": "unmet", "over": "max",
     "max": {"value": 0, "unit": "W"}}
  ]
}
```

## Where each value comes from

| section | values | tag |
| --- | --- | --- |
| time | 2027, daily | [O] |
| site.ground, reservoir, fluid | all | [O]; permeability range [A] |
| site.air | 10 degC | [A] |
| demand | CSV, supply temps | [O]; return temps [A] |
| market.discount_rate | 4 % real financial (EU Reg. 480/2014 art. 19(3)) | [V]; range [A] |
| market.capex.drilling | 1,845 EUR2015/m at 3000 m (2013 NL SDE+) | [V], depth dependent in reality |
| market.capex.chillers | 0.234 / 0.159 EUR2015/W | [S] |
| market.capex.dry_cooler | 0.049-0.107 EUR/W, middle taken | [V] |
| market.capex.pipe | 1,149 EUR2015/m | [V] |
| market.capex heat_pump, production_pump, degasser | | [A] |
| market.opex electricity, gas, co2 price | | [A] |
| market.revenue.heat | 85-98 EUR/MWh consumer price | [V] |
| market.revenue.cold | 81-105 EUR/MWh | [S] |
| market.emissions CO2 electricity | 209.2 g/kWh EU 2025 (Ember) | [V] |
| market.emissions CH4 gwp | 29.8 (IPCC AR6, fossil) | [V] |
| requirements | doublets 1-3, flow, 40 K, 330 d, pump 70 % | [O] |
| requirements unmet = 0 | the plant must meet demand | [A], implied by the brief |

## What is no longer here (moved out)

- `choices` -> study variables / cases
- ESP intake pressure and free-gas limits -> parameters of the ESP in the plant (they depend on the pump type)
- `volume_imbalance` -> numeric check of the simulation
- pump efficiency: the plant sets it; the requirement only checks it equals 0.7, because the organiser demands it for every plant

## Open points

- name: `Scenario` or `Basis`
- `time` here or in the study (kept here, the demand profile depends on it)
- drilling cost as a depth-dependent curve instead of one EUR/m
- capex keys name equipment kinds; a plant with a kind missing from `capex` should fail with a clear missing-value error
