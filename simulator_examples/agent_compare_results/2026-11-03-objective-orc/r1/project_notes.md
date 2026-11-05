# Project notes (agent memory across sessions)

- **decision** (2026-11-03T15:50:13, agent): CHP on co-produced gas (1D-3000m-boiler-electric-chp-screw, R0084): accept. CHP cuts LCOE from 48.92 to 47.82 EUR/MWh and CO2 from 12020 to 11930 t/yr by using the associated gas instead of flaring it.
- **decision** (2026-11-03T15:50:13, agent): free cooling ahead of chiller (1D-3000m-boiler-electric-chp-screw-fc, R0110): accept. Free cooling is cost-neutral (47.88 vs 47.82 EUR/MWh) but lowers CO2 from 11930 to 11790 t/yr.
- **lesson** (2026-11-03T15:50:13, agent): 250,000 m3 pit store (1D-3000m-boiler-electric-chp-screw-fc-pit250k, R0111): alternative. Pit store raises LCOE from 47.88 to 49.15 EUR/MWh but cuts CO2 from 11790 to 9701 t/yr.
- **decision** (2026-11-03T15:50:15, agent): User objective: lowest cost with CO2 counted at 180 EUR/t (80 in cost + 100 extra). Outage stress-tested at the heating peak (day 28, all doublets common outage). Recommended: 1 doublet 3000 m, boiler, electric screw-dry-cooler chiller, CHP on associated gas, free cooling, 250,000 m3 pit store (R0111): LCOE 49.15 EUR/MWh, CO2 9701 t/yr. Cheapest compliant: R0110 (47.88 EUR/MWh, 11790 t/yr).
