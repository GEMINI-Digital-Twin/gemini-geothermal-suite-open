# Design options explored by the agent

| # | Option | Run | vs baseline | LCOE (EUR/MWh) | CO2 (t/yr) | Verdict | Reason |
|---|---|---|---|---|---|---|---|
| 1 | Refined depth and operating controls (1D-3062m-boiler-electric-chp-screw) | R0193 | R0158 | 47.29 (-0.29) | 11670.0 (-120) | **accept** | Lower LCOE and lower CO2 while meeting every hard rule with the geothermal outage covering the heating peak. |
| 2 | Centrifugal chiller with cooling tower (1D-3062m-boiler-electric-chp-tower) | R0205 | R0193 | 47.36 (+0.07) | 11500.0 (-170) | **alternative** | Lower CO2 but higher LCOE after including the requested carbon price. |
| 3 | Aquifer cold storage (1D-3062m-boiler-electric-chp-screw-ates1) | R0206 | R0193 | 47.36 (+0.07) | 11540.0 (-130) | **reject** | Reduced emissions do not offset its higher cost under the requested carbon valuation. |
| 4 | Seasonal pit heat storage (1D-3125m-boiler-electric-chp-screw-pit250k) | R0192 | R0193 | 48.67 (+1.38) | 9490.0 (-2180) | **alternative** | Lower CO2 and purchased gas consumption, but higher capital cost and LCOE. |
