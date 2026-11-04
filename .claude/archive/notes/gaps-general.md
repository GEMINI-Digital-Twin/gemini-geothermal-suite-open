# Capabilities gemini lacks for geomind (general view)

Review on `refactor` at `33c7f52`, 2026-10-31. Basis: what a geothermal designer does for **any** heating and cooling problem, not just the competition. The generalization prompt (`prompts/gemini-general-not-competition.md`) solves a few items; those are marked ⏳.

Priorities:
- 🔴 without it geomind gets stuck on an arbitrary problem
- 🟠 lowers the quality or credibility of the answer
- 🟢 bonus

---

# 1. Problem definition

## 1.1 One problem object 🔴
### `Problem`
Demand, site (reservoir, fluid), constraints and economic assumptions in one dictionary with `to_dict`, `from_dict` and a schema. The Brief in geomind becomes this. Now each one is passed separately and without a rule.

## 1.2 General constraint 🔴
### `Constraint`
One shape for every requirement: path, aggregation (`each`, `count`, `sum`, `max`, `mean`), `min` / `max` / `equals`, and a condition (`when="running"`). Both schedule and the checks should read this. Now the schedule rules are a dictionary with fixed fields, and `Limits` is separate.

## 1.3 Schema for all inputs 🟠
### Agent tool input
Only `gm.plants.schema()` and `profile_schema()` exist. `Problem`, `Constraint`, rules and `Assumptions` also need a schema, so geomind can get its tool inputs from gemini.

---

# 2. Input data

## 2.1 Profile from a file or values ⏳
`from_csv`, `from_values`, with any time step.

## 2.2 Building a profile from little information 🔴
### When the user only gives the peak or annual consumption
For example "peak 20 MW, 80 GWh per year". Build the profile from a standard shape (degree-days or a dimensionless sample profile) with a source. Without this, for any problem that lacks a full profile the agent must ask or make up numbers (which it is not allowed to do).

## 2.3 Ambient temperature 🟠
### Weather profile
Air temperature affects the compression chiller, the cooling tower and network losses. Now there is no ambient temperature input in schedule or the profiles.

---

# 3. Design

## 3.1 Initial sizing 🔴
### `size(plant, problem)`
Capacity of each doublet at a given depth and flow rate, the number of doublets for the peak, and the capacity of the heat pump, boiler and chiller from the demand. Now the sizes are manual and fixed in the sample files, and geomind is not allowed to compute physics.

## 3.2 List of capabilities 🟠
### `capabilities()`
Which families and combinations can be scheduled and run, and what limits they have, from the code itself. Now this information is written by hand in the geomind prompt and goes stale fast.

## 3.3 Several units of one type 🟠
### The "at most one" limit
`gm.schedule` accepts only one of each type and role (`schedule.py:129`). Two cascaded heat pumps or two boilers in series are not possible.

## 3.4 Storage in the daily schedule 🟠
### Thermal storage, ice and ATES
Their modules exist, but `gm.schedule` does not dispatch them (ATES is explicitly not supported). Seasonal storage for heating and cooling is a main design option.

## 3.5 Arbitrary time step ⏳
schedule on any time step.

---

# 4. Running

## 4.1 Multi-year run 🟠
### Project lifetime
Only one year is run, and the economics multiply that over the project lifetime. Reservoir temperature decline over 20 to 30 years (`ThermalDecline` exists) affects LCOH and the number of doublets.

## 4.2 Speed of plants with loops 🟠
### 6 to 9 seconds per year
Plants with a bypass run row by row. This is slow for optimization and for comparing several options. Fix: move the loops inside the graph.

---

# 5. Evaluation

## 5.1 Incomplete capital cost 🔴
### Only 9 of about 70 modules have `capex`
Have it: absorption, exchanger, boiler, CHP, heat pump, gas makeup, doublet, degasser, flare. Do not have it: adsorption chiller, pumps (ESP, injection, circulation), pipes and network, storage, wells on their own, ORC and the rest. So the LCTS of any design that has these is incomplete or empty, and comparing options is not fair.

## 5.2 Capacity of each unit 🔴
### `capacities(plant, results)`
Peak power of each unit in the run. Needed for the design report (any problem).

## 5.3 Single report 🟠
### `report(plant, results, problem)`
KPI, costs, capacities and all constraints in one dictionary.

## 5.4 Comparing options 🟠
### `compare(reports)`
Ranking several designs by criteria, and the Pareto front (cost and carbon). Now geomind must put the numbers side by side itself.

## 5.5 Why a day failed 🟠
### Diagnosis
Summary of the failed steps: which module, which error code, how many times. The agent needs this to fix the design.

## 5.6 Sensitivity 🟢
### tornado
Effect of each parameter on one metric (one at a time). Now there is only random sampling.

---

# 6. Optimization

## 6.1 Discrete variables 🟠
### Number of doublets, design family
`minimize` only accepts continuous parameters. The number of doublets and the choice of family are main design decisions.

## 6.2 Multi-objective 🟢
### Cost and carbon
One objective only.

---

# 7. Summary

Suggested order after the generalization prompt:
1. `Problem` and `Constraint` (and the schema for all inputs)
2. `capex` for all modules
3. `size`, `capacities`, `report`
4. Profile from little information
5. Several units of one type, and storage in schedule
6. Multi-year run, failure diagnosis, comparison
7. Loop speed, discrete variables, sensitivity
