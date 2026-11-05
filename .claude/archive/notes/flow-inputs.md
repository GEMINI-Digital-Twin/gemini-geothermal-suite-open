# Every input of the competition flow in gemini dev (2026-11-01 20:30)

Read-only inventory of `inputs/examples/hackathon_2026/*` and `examples/hackathon.py`. Tags: [O] organiser brief, [A] our assumption, [D] design decision.

## 1. case.json
- time: 2027 start/end [O], step 1 d
- environment.ground: surface 12 degC, gradient 30 K/km [O]
- environment.reservoir: depth 2500 m, thickness 100 m, 200 mD, 250 barg [O]
- environment.fluid: density, viscosity, GLR, gas composition [O]
- environment.air: 10 degC [A]
- demand: heat/cool CSVs and supply temps [O], return temps [A]
- choices: 1-3 doublets [O], depth 2000-3500 m [A]
- constraints: flow 50-300 m3/h, brine cooling 40 K, 330 days, pump efficiency 0.7, volume balance [O]; ESP intake pressure and gas fraction [A]
- assumptions.finance: discount rate, lifetime, price year, capex 14 items, fixed opex 14 items, electricity, gas, CO2, chemicals, waste, heat/cold revenue, heat_cost_share [A]
- assumptions.emissions: grid CO2, CH4 GWP [A]
- uncertainty: distributions on 6 values [A]

## 2. plants/*.json (per candidate; HeatingPlant ~93 parameters)
- plant kind, doublet count
- depth and geometry: well diameter, roughness, pipe lengths and diameters
- equipment size: HX conductance, ESP rated flow, capacities
- equipment properties: motor efficiency, carnot_fraction, separator and flare efficiency
- model coefficients: friction correlation, correction_factors, fouling thresholds
- operating point: temperature_setpoint, pressure_setpoint

## 3. Only inside examples/hackathon.py (no input file)
- candidate list
- search variables and capacity range (0.1-1 x peak)
- objective lcts, compare metrics lcts and co2
- backup policy peak
- budget: 20 evaluations, 5 samples, seed 1, 8 processes

## Misplaced or double
- pump efficiency is both a constraint and a plant parameter; depth and doublet count are in both choices and plant
- flow range is read from constraints and turned into a search variable (one input, two roles)
- gas_grid.composition and heating_consumer.return_pressure are outside the plant but live in plant.json
- capex keys name equipment kinds, so the scenario knows what the plant contains
- reservoir fixed at 2500 m while depth is searched 2000-3500 m: meaning of the search unclear
- study settings live in example code, so the full run is not reproducible from files

## Proposed boundaries (rule: who changes this value?)
1. Site: nature and location (ground, reservoir, fluid, air). Nobody.
2. Demand: what the customer asks (profiles, supply/return temps). Customer.
3. Market: prices, finance, emissions factors. Market/policy.
4. Requirements: contract and permit rules valid for every plant. Regulator/client.
5. Plant: structure, sizes, equipment properties, operating points, model coefficients. Designer.
6. Study: cases, search variables, objective, method, sample count, seed, budget. Analyst.
7. Runtime: processes, numeric tolerances. No effect on results.
Scenario = 1-4 (+ time, + uncertainty on its own values). Cases = 5 varied by 6. Runtime separate.
