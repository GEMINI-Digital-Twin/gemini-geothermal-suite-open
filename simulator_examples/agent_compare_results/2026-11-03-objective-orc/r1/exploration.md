# Design options explored by the agent

| # | Option | Run | vs baseline | LCOE (EUR/MWh) | CO2 (t/yr) | Verdict | Reason |
|---|---|---|---|---|---|---|---|
| 1 | CHP on co-produced gas (1D-3000m-boiler-electric-chp-screw) | R0084 | R0038 | 47.82 (-1.1) | 11930.0 (-90) | **accept** | CHP cuts LCOE from 48.92 to 47.82 EUR/MWh and CO2 from 12020 to 11930 t/yr by using the associated gas instead of flaring it. |
| 2 | free cooling ahead of chiller (1D-3000m-boiler-electric-chp-screw-fc) | R0110 | R0084 | 47.88 (+0.06) | 11790.0 (-140) | **accept** | Free cooling is cost-neutral (47.88 vs 47.82 EUR/MWh) but lowers CO2 from 11930 to 11790 t/yr. |
| 3 | 250,000 m3 pit store (1D-3000m-boiler-electric-chp-screw-fc-pit250k) | R0111 | R0110 | 49.15 (+1.27) | 9701.0 (-2089) | **alternative** | Pit store raises LCOE from 47.88 to 49.15 EUR/MWh but cuts CO2 from 11790 to 9701 t/yr. |
| 4 | 2 doublets 3500 m (2D-3500m-boiler-electric-chp-screw) | R0105 | R0110 | 51.5 (+3.62) | 8150.0 (-3640) | **reject** | Second deep doublet costs 51.50 vs 47.88 EUR/MWh for a CO2 cut to 8150 t/yr, worse value than the pit store. |
