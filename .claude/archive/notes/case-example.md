# `gm.Case` example: JSON, Python and quickstart

Proposal, 2026-10-31. Nothing is implemented yet. The example problem is the competition inputs; prices and cost factors are placeholders.

Rules:
- Every dimensional value is `{"value", "unit"}` and the unit comes from `gm.units.Unit` (enum)
- A raw number only for a dimensionless quantity (efficiency, fraction, discount rate)
- An unknown key is an error; there is no default in the package
- Profiles come only from CSV, and all are checked against `time`
- Order of sections: `time`, `environment`, `demand`, `choices`, `constraints`, `assumptions`
- Assumptions in two groups: `finance` (anything that is money) and `emissions` (per substance, with the same names as `fluid.gas`)
- `opex.fixed` is an annual percent of capex, separate for each equipment type; the keys of `capex` and `opex.fixed` are the same closed list of equipment types in section 5 of the prompt
- `optim` is named `study`
- Inside `Case` everything is stored in SI; `Quantity` only at the input and output boundary
- Only `gm.Case` at the top level; the rest under `gm.case`
- Run prompt: `prompts/gemini-case.md` (where it differs from this file, the prompt is right)
- `end` is not included in the range (half-open): `2027-01-01` to `2028-01-01` means 365 days

---

## 1. `case.json`

```json
{
  "time": {
    "start": "2027-01-01",
    "end": "2028-01-01",
    "step": {"value": 1, "unit": "d"}
  },

  "environment": {
    "ground": {
      "surface_temperature": {"value": 12, "unit": "degC"},
      "gradient": {"value": 30, "unit": "K/km"}
    },
    "reservoir": {
      "reference_depth": {"value": 2500, "unit": "m"},
      "thickness": {"value": 100, "unit": "m"},
      "permeability": {"value": 200, "unit": "mD"},
      "pressure": {"value": 250, "unit": "barg"}
    },
    "fluid": {
      "density": {"value": 1030, "unit": "kg/m3"},
      "viscosity": {"value": 0.4, "unit": "mPa.s"},
      "gas_liquid_ratio": {"value": 0.8, "unit": "Nm3/m3"},
      "gas": {"CH4": 0.8, "CO2": 0.2}
    },
    "air": {"temperature": {"value": 10, "unit": "degC"}}
  },

  "demand": {
    "file": "demand.csv",
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

  "choices": {
    "doublets": {"min": 1, "max": 3},
    "depth": {
      "min": {"value": 2000, "unit": "m"},
      "max": {"value": 3500, "unit": "m"}
    }
  },

  "constraints": [
    {"on": "doublet", "quantity": "production_flow", "over": "each", "when": "running",
     "min": {"value": 50, "unit": "m3/h"}, "max": {"value": 300, "unit": "m3/h"}},
    {"on": "doublet", "quantity": "brine_cooling", "over": "each", "when": "running",
     "max": {"value": 40, "unit": "K"}},
    {"on": "doublet", "quantity": "production_flow", "over": "duration", "when": "running",
     "max": {"value": 330, "unit": "d"}},
    {"on": "doublet", "quantity": "pump_efficiency", "equals": 0.7},
    {"on": "doublet", "quantity": "volume_imbalance", "over": "each", "when": "running",
     "min": {"value": -1e-6, "unit": "m3/s"}, "max": {"value": 1e-6, "unit": "m3/s"}}
  ],

  "assumptions": {
    "finance": {
      "currency": "EUR",
      "discount_rate": 0.05,
      "lifetime": {"value": 25, "unit": "yr"},
      "price_year": 2015,
      "capex": {
        "drilling":   {"value": 1239,    "unit": "EUR/m"},
        "production_pump":    {"value": 0.5,  "unit": "EUR/W"},
        "injection_pump":     {"value": 0.5,  "unit": "EUR/W"},
        "heat_pump":  {"value": 0.67,    "unit": "EUR/W"},
        "boiler":     {"value": 0.06,    "unit": "EUR/W"},
        "chp":        {"value": 0.95,    "unit": "EUR/W"},
        "absorption_chiller":  {"value": 0.3, "unit": "EUR/W"},
        "compression_chiller": {"value": 0.3, "unit": "EUR/W"},
        "heat_exchanger":      {"value": 0.5, "unit": "EUR/(W/K)"},
        "degasser":   {"value": 1000000, "unit": "EUR"},
        "flare":      {"value": 100000,  "unit": "EUR"},
        "gas_makeup": {"value": 50000,   "unit": "EUR"}
      },
      "opex": {
        "fixed": {
          "heat_pump": {"value": 2, "unit": "%/yr"},
          "boiler":    {"value": 1.5, "unit": "%/yr"}
        },
        "electricity":    {"value": 100, "unit": "EUR/MWh"},
        "gas":            {"value": 40,  "unit": "EUR/MWh"},
        "chemical":       {"value": 3,   "unit": "EUR/kg"},
        "waste_disposal": {"value": 0.2, "unit": "EUR/kg"},
        "co2":            {"value": 80,  "unit": "EUR/t"}
      },
      "revenue": {
        "heat": {"value": 60, "unit": "EUR/MWh"},
        "cold": {"value": 60, "unit": "EUR/MWh"}
      },
      "allocation": {"heat_cost_share": 0.8}
    },
    "emissions": {
      "CO2": {"electricity": {"value": 300, "unit": "g/kWh"}},
      "CH4": {"gwp": 29.8}
    }
  }
}
```

Notes:
- The reservoir temperature is not given, so it is computed from the surface temperature and gradient (87 degrees at 2500 meters). If `reservoir.temperature` is given, it is the basis and the gradient is used only for another depth.
- Pressure at another depth is always: `p(z) = p_ref + rho_brine * g * (z - z_ref)`.
- Air temperature can also be a profile: `"air": {"temperature": {"file": "air.csv", "column": "t_air", "unit": "degC"}}`. The same shape for the `opex` and `revenue` prices and for `emissions.CO2.electricity`.
- There is no supply temperature constraint; `demand` has it itself and gemini checks it.
- Moved out of `plant.json`: consumer return temperature and pressure, fluid, air temperature, and all ground and reservoir values.

---

## 2. The same case in Python

```python
import gemini as gm
from gemini.units import Quantity as Q, Unit as U

case = gm.Case(
    time=gm.case.Time(
        start="2027-01-01",
        end="2028-01-01",
        step=Q(1, U.D),
    ),
    environment=gm.case.Environment(
        ground=gm.case.Ground(
            surface_temperature=Q(12, U.DEG_C),
            gradient=Q(30, U.K_PER_KM),
        ),
        reservoir=gm.case.Reservoir(
            reference_depth=Q(2500, U.M),
            thickness=Q(100, U.M),
            permeability=Q(200, U.MD),
            pressure=Q(250, U.BARG),
        ),
        fluid=gm.case.Fluid(
            density=Q(1030, U.KG_PER_M3),
            viscosity=Q(0.4, U.MPA_S),
            gas_liquid_ratio=Q(0.8, U.NM3_PER_M3),
            gas={"CH4": 0.8, "CO2": 0.2},
        ),
        air=gm.case.Air(temperature=Q(10, U.DEG_C)),
    ),
    demand=gm.case.Demand(
        file="demand.csv",
        time_column="date",
        heating=gm.case.Service(
            column="heating_demand_MWth",
            unit=U.MW,
            supply_temperature=Q(100, U.DEG_C),
            return_temperature=Q(60, U.DEG_C),
        ),
        cooling=gm.case.Service(
            column="cooling_demand_MWcool",
            unit=U.MW,
            supply_temperature=Q(20, U.DEG_C),
            return_temperature=Q(25, U.DEG_C),
        ),
    ),
    choices=gm.case.Choices(
        doublets=gm.case.Range(1, 3),
        depth=gm.case.Range(Q(2000, U.M), Q(3500, U.M)),
    ),
    constraints=[
        gm.case.Constraint(on="doublet", quantity="production_flow", over="each",
                      when="running", min=Q(50, U.M3_PER_H), max=Q(300, U.M3_PER_H)),
        gm.case.Constraint(on="doublet", quantity="brine_cooling", over="each",
                      when="running", max=Q(40, U.K)),
        gm.case.Constraint(on="doublet", quantity="production_flow", over="duration",
                      when="running", max=Q(330, U.D)),
        gm.case.Constraint(on="doublet", quantity="pump_efficiency", equals=0.7),
        gm.case.Constraint(on="doublet", quantity="volume_imbalance", over="each",
                      when="running", min=Q(-1e-6, U.M3_PER_S), max=Q(1e-6, U.M3_PER_S)),
    ],
    assumptions=gm.case.Assumptions(
        finance=gm.case.Finance(
            currency="EUR",
            discount_rate=0.05,
            lifetime=Q(25, U.YR),
            price_year=2015,
            capex=gm.case.Capex(
                drilling=Q(1239, U.EUR_PER_M),
                heat_pump=Q(0.67, U.EUR_PER_W),
                boiler=Q(0.06, U.EUR_PER_W),
                degasser=Q(1_000_000, U.EUR),
            ),
            opex=gm.case.Opex(
                fixed={"heat_pump": Q(2, U.PERCENT_PER_YR), "boiler": Q(1.5, U.PERCENT_PER_YR)},
                electricity=Q(100, U.EUR_PER_MWH),
                gas=Q(40, U.EUR_PER_MWH),
                co2=Q(80, U.EUR_PER_T),
            ),
            revenue=gm.case.Revenue(
                heat=Q(60, U.EUR_PER_MWH),
                cold=Q(60, U.EUR_PER_MWH),
            ),
            allocation=gm.case.Allocation(heat_cost_share=0.8),
        ),
        emissions=gm.case.Emissions(
            CO2=gm.case.CO2(electricity=Q(300, U.G_PER_KWH)),
            CH4=gm.case.CH4(gwp=29.8),
        ),
    ),
)

case.to_json("case.json")
assert gm.Case.from_json("case.json") == case
```

Location of the classes: all under `gm.case` (the `gemini/case/` folder): `Case`, `Constraint`, `Assumptions` and all the sections. Only `gm.Case` is also at the top level, like `gm.Plant`.

Errors at construction time:

```python
Q(300, U.M)                    # as production_flow max
# ValidationError: constraints[0].max: unit 'm' is not a volume flow; expected one of m3/s, m3/h, m3/d

gm.case.Reservoir(depth=Q(2500, U.M))
# ValidationError: reservoir: unknown key 'depth'; did you mean 'reference_depth'?

gm.case.Constraint(on="doublet", quantity="cop", max=5)
# ValidationError: constraint: 'cop' is not a quantity of 'doublet'; expected one of production_flow, ...

gm.evaluate.lcts(plant, case_without_prices, results)
# ValidationError (missing_assumption): assumptions.finance.opex.electricity is needed for lcts
```

---

## 3. quickstart

```python
"""Quickstart: one case, one plant, one year."""

import gemini as gm

case = gm.Case.from_json("inputs/examples/shallow_district/case.json")
plant = gm.Plant.from_json("inputs/examples/shallow_district/plant.json")

results = gm.simulate(plant, case)

for check in gm.evaluate.constraints(plant, case, results):
    print(check["name"], "ok" if check["passed"] else "VIOLATED", check["value"])

report = gm.evaluate.report(plant, case, results)
print("heat delivered:", report["heat_delivered"].to("GWh"))
print("cold delivered:", report["cold_delivered"].to("GWh"))
print("LCTS:          ", report["lcts"].to("EUR/MWh"))
print("CO2:           ", report["co2"].to("t/yr"))
```

The outputs are `Quantity`, so we no longer subtract and add table columns by hand and no longer convert units by hand.

The `examples/hackathon.py` path (summary):

```python
from pathlib import Path

case = gm.Case.from_json("inputs/examples/hackathon_2027/case.json")
reports = []
for path in sorted(Path("inputs/examples/hackathon_2027/plants").glob("*.json")):
    plant = gm.study.size(gm.Plant.from_json(path), case)
    best = gm.study.minimize(plant, case, objective="lcts")
    results = gm.simulate(best.plant, case)
    reports.append(gm.evaluate.report(best.plant, case, results))

print(gm.evaluate.compare(reports, by=["lcts", "co2"]).to_frame())
```

`minimize` reads its variables from `case.choices` (`doublets`, `depth`).
