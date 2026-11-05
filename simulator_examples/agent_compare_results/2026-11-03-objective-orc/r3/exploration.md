# Design options explored by the agent

| # | Option | Run | vs baseline | LCOE (EUR/MWh) | CO2 (t/yr) | Verdict | Reason |
|---|---|---|---|---|---|---|---|
| 1 | free cooling (dry-cooler economizer) (2D-3000m-boiler-electric-chp-tower-fc) | R0083 | R0082 | 38.51 (+0.13) | 4378.0 (-101) | **alternative** | Cuts CO2 from 4479 to 4378 t/yr but LCOE rises from 38.38 to 38.51 EUR/MWh (+1.0 MEUR capex). |
| 2 | ATES cold store (4 well pairs) (2D-3000m-boiler-electric-chp-tower-ates4) | R0084 | R0082 | 38.77 (+0.39) | 4101.0 (-378) | **alternative** | Lowest CO2 of the options tried (4101 vs 4479 t/yr) at LCOE 38.77 vs 38.38 EUR/MWh. |
| 3 | heat pump upgrade instead of boiler (2D-3000m-heat_pump-electric-chp-tower) | R0085 | R0082 | 43.21 (+4.83) | 4504.0 (+25) | **reject** | LCOE 43.21 vs 38.38 EUR/MWh and CO2 4504 vs 4479 t/yr: more capex and more electricity for no gain. |
| 4 | screw dry-cooler chiller (2D-3000m-boiler-electric-chp-screw) | R0104 | R0082 | 38.3 (-0.08) | 4639.0 (+160) | **alternative** | LCOE 38.30 vs 38.38 EUR/MWh (capex 42.58 vs 42.87 MEUR) but CO2 4639 vs 4479 t/yr, so it is a trade-off, not a win. |
| 5 | ATES4 cold store + free cooling (2D-3000m-boiler-electric-chp-tower-fc-ates4) | R0100 | R0082 | 38.89 (+0.51) | 3988.0 (-491) | **alternative** | Lowest CO2 of all options (3988 vs 4479 t/yr) at LCOE 38.89 vs 38.38 EUR/MWh; worth 0.51 EUR/MWh if CO2 is valued at 180 EUR/t. |
| 6 | 3 doublets (3D-3000m-boiler-electric-chp-tower) | R0097 | R0082 | 50.82 (+12.44) | 4506.0 (+27) | **reject** | LCOE 50.82 vs 38.38 EUR/MWh and CO2 4506 vs 4479 t/yr: a third doublet adds capex without cutting emissions. |
