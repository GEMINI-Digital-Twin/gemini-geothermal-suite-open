# Design options explored by the agent

| # | Option | Run | vs baseline | LCOE (EUR/MWh) | CO2 (t/yr) | Verdict | Reason |
|---|---|---|---|---|---|---|---|
| 1 | wet cooling tower + free cooling (baseline) (2D-3000m-boiler-electric-chp-tower-fc) | R0038 | R0022 | 39.84 (-0.86) | 4789.0 (-515) | **accept** | Centrifugal wet tower with free cooling cuts LCOE from 40.70 to 39.84 EUR/MWh and CO2 from 5304 to 4789 t/yr versus the legacy chiller, at the cost of 42120 m3/yr of tower water. |
| 2 | screw dry cooler + free cooling (water-free) (2D-3000m-boiler-electric-chp-screw-fc) | R0044 | R0038 | 39.76 (-0.08) | 4925.0 (+136) | **alternative** | LCOE 39.76 vs 39.84 EUR/MWh (0.2 % cheaper) but 4925 vs 4789 t CO2/yr and no cooling water; worth reporting as the water-free variant. |
| 3 | 3500 m wells (2D-3500m-boiler-electric-chp-tower-fc) | R0040 | R0038 | 40.6 (+0.76) | 4197.0 (-592) | **reject** | Deeper wells cut CO2 to 4197 t/yr but raise LCOE to 40.60 EUR/MWh versus 39.84 at 3000 m. |
| 4 | 3 doublets (3D-3000m-boiler-electric-chp-tower-fc) | R0041 | R0038 | 51.94 (+12.1) | 4618.0 (-171) | **reject** | Third doublet cuts CO2 to 4618 t/yr but LCOE rises to 51.94 EUR/MWh versus 39.84 with two doublets. |
| 5 | heat pump upgrade (2D-3000m-heat_pump-electric-chp-tower-fc) | R0042 | R0038 | 44.79 (+4.95) | 4941.0 (+152) | **reject** | Heat pump upgrade gives LCOE 44.79 EUR/MWh and 4941 t CO2/yr, worse than the boiler design on both. |
| 6 | outage scheduled on the coldest day (stress test) (2D-3000m-boiler-electric-chp-tower-fc) | R0043 | R0038 | 43.43 (+3.59) | 5967.0 (+1178) | **alternative** | Forcing the 35-day outage to start on the 28 Jan peak day still meets all demand with LCOE 43.43 EUR/MWh and 5967 t CO2/yr, so the backup boiler covers the trip. |
