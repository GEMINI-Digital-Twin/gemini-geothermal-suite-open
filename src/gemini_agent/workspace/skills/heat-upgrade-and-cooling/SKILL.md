---
name: heat-upgrade-and-cooling
description: Heat pumps, boilers, absorption and electric chillers - when each makes sense, how they are sized, and backup/N-1 rules. Read before sizing surface equipment or choosing a cooling technology.
---
# Heat upgrade and cooling technologies

Heating chain (district water): return T_r -> heat exchanger (geothermal) -> heat pump condenser -> boiler -> 100 C.
- Heat exchanger: cheap, heats DH water to ~3 K below brine temperature.
- Heat pump (GEMINI HeatpumpBasic, Lorenz COP): uses the remaining brine (down to the 40 K limit) as source and lifts DH water to 100 C. COP ~4-7 for this lift. Uses electricity.
- Boiler: peak/backup only (gas or electric). Size so the plant survives one doublet trip on the peak day (N-1); `search_designs` right-sizes it automatically.
- Lower DH return temperature -> more direct geothermal heat, but the customer side must accept it (45-55 C typical).

Cooling (network 20 C supply / ~26 C return):
- Electric chiller: COP ~7-8 at 20 C chilled water (high-temperature cooling is easy).
- Absorption chiller (LiBr, single effect): driven by hot brine (needs ~70-90 C), thermal COP ~0.7, plus cooling-tower power. It uses summer geothermal heat that is otherwise idle, but it needs a lot of brine flow (pumping) and capital.
- Do NOT assume absorption is better: compare designs with and without it using tools. It tends to pay off with hotter brine (deeper wells) and low electricity prices.
- Give cooling some capacity margin: demand growth or a hot year can exceed the 10 MW peak (`stress_test_design` demand_plus_10/20, `add_capacity_margin`).
