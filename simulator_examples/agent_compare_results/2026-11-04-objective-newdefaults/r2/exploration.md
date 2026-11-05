# Design options explored by the agent

| # | Option | Run | vs baseline | LCOE (EUR/MWh) | CO2 (t/yr) | Verdict | Reason |
|---|---|---|---|---|---|---|---|
| 1 | free cooling (dry-cooler economiser) (2D-2825m-boiler-electric-screw-fc-2xB-retref/30) | R0362 | R0333 | 39.7 (-0.37) | 5235.0 (-267) | **accept** | Free cooling cuts LCOE from 40.07 to 39.70 EUR/MWh and CO2 from 5502 to 5235 t/yr by covering 8230 MWh of cooling with the measured outdoor air. |
| 2 | ATES cold store (2 well pairs) (2D-2825m-boiler-electric-screw-fc-ates2-2xB-retref/30) | R0388 | R0362 | 40.11 (+0.41) | 4985.0 (-250) | **alternative** | ATES lowers CO2 from 5235 to 4985 t/yr but raises LCOE from 39.70 to 40.11 EUR/MWh, so it is a trade-off not a win. |
| 3 | heat pump instead of gas boiler (2D-3000m-heat_pump-electric-screw) | R0077 | R0368 | 47.57 (+7.86) | 5846.0 (+672) | **reject** | Heat pump upgrade costs 47.57 vs 39.71 EUR/MWh and emits 5846 vs 5174 t CO2/yr because it adds electric load. |
| 4 | 3 doublets (3D-2825m-boiler-electric-screw-fc-2xB-retref/30) | R0436 | R0362 | 50.53 (+10.83) | 5046.0 (-189) | **reject** | A third doublet raises LCOE from 39.70 to 50.53 EUR/MWh for only 5235 to 5046 t CO2/yr. |
| 5 | single 2500 m doublet (1D-2500m-boiler-electric-screw) | R0003 | R0368 | 48.69 (+8.98) | 12600.0 (+7426) | **reject** | One shallow doublet costs 48.69 vs 39.71 EUR/MWh and emits 12600 vs 5174 t CO2/yr. |
| 6 | cooling return 30 degC instead of 26 (2D-3000m-boiler-electric-screw-2xB-retref/30) | R0294 | R0292 | 40.68 (-0.02) | 5321.0 (-85) | **accept** | A 30 degC cooling return lowers LCOE from 40.70 to 40.68 EUR/MWh and CO2 from 5406 to 5321 t/yr. |
