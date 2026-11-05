---
name: associated-gas
description: Handling of the co-produced gas (GLR 0.8 Nm3/m3, 80 % CH4 / 20 % CO2) and its CO2 accounting. Read when deciding gas handling or explaining emissions.
---
# Associated gas

Per m3 of brine: 0.64 Nm3 CH4 + 0.16 Nm3 CO2 (~23 MJ fuel). At 300 m3/h that is ~1.9 MW of fuel per doublet.
Options (design field `gas_handling`):
1. `separate_and_burn`: degas at low pressure, burn CH4 in the boiler (free fuel); surplus is flared. ALL gas ends up as CO2 (combustion CO2 + the co-produced 20 % CO2): ~1.58 kg CO2 per m3 of brine. Venting CH4 is not allowed.
2. `keep_in_solution_reinject`: keep the surface loop above the bubble point (~30 bar, assumption) so no gas is liberated; everything is re-injected. Zero process CO2, slightly more ESP power, but the injection pump is often no longer needed (the loop is already at injection pressure).
Always compare both with tools: option 1 lowers fuel cost, option 2 typically halves total CO2.
