# Design options explored by the agent

| # | Option | Run | vs baseline | LCOE (EUR/MWh) | CO2 (t/yr) | Verdict | Reason |
|---|---|---|---|---|---|---|---|
| 1 | add 250,000 m3 seasonal pit store (1D-3000m-heat_pump-electric-tower-pit250k) | R0073 | R0071 | 49.18 (+0.87) | 7743.0 (-2190) | **alternative** | Pit store cuts CO2 from 9933 to 7743 t/yr but raises LCOE from 48.31 to 49.18 EUR/MWh, a trade-off worth reporting. |
| 2 | heat pump instead of boiler (1 doublet, 3000 m, wet-tower electric cooling) (1D-3000m-heat_pump-electric-tower) | R0071 | R0060 | 48.31 (-0.68) | 9933.0 (-1917) | **accept** | Heat pump cuts CO2 from 11850 to 9933 t/yr and LCOE from 48.99 to 48.31 EUR/MWh, so it dominates the boiler design. |
