# Design options explored by the agent

| # | Option | Run | vs baseline | LCOE (EUR/MWh) | CO2 (t/yr) | Verdict | Reason |
|---|---|---|---|---|---|---|---|
| 1 | ATES cold store (2 pairs) added (2D-3000m-boiler-electric-chp-screw-fc-ates2-3xB-retref/30) | R0419 | R0418 | 39.1 (+0.39) | 4623.0 (-249) | **alternative** | Costs 0.39 EUR/MWh more (39.10 vs 38.71) but cuts CO2 from 4872 to 4623 t/yr and also survives +10% demand. |
| 2 | 18 MW boiler + ATES (fully stress-proof) (2D-3000m-boiler-electric-chp-screw-fc-ates2-3xB-retref/30) | R0425 | R0418 | 39.92 (+1.21) | 4633.0 (-239) | **alternative** | 39.92 vs 38.71 EUR/MWh and 4633 vs 4872 t CO2/yr, but it is the only variant tested that also passes the combined low-reservoir/high-demand/trip case. |
