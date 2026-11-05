# Design options explored by the agent

| # | Option | Run | vs baseline | LCOE (EUR/MWh) | CO2 (t/yr) | Verdict | Reason |
|---|---|---|---|---|---|---|---|
| 1 | 3000 m doublets instead of 2900 m (2D-3000m-boiler-electric-screw-2xB-retref/28) | R0090 | R0118 | 42.06 (+0.38) | 5438.0 (-88) | **alternative** | 3000 m costs 42.06 EUR/MWh vs 41.68 and emits 5438 vs 5526 t CO2/yr: slightly lower CO2, slightly higher cost. |
| 2 | 11 MW chiller (N-1 on cooling) (2D-3000m-boiler-electric-screw-2xB-retref/28) | R0100 | R0118 | 42.25 (+0.57) | 5445.0 (-81) | **alternative** | One extra MW of chiller costs 42.25 vs 41.68 EUR/MWh but keeps cooling met in the +10 % demand stress case (R0110). |
| 3 | heat pump upgrade instead of boiler (2D-3000m-heat_pump-electric-screw-2xB-retref/28) | R0112 | R0118 | 47.07 (+5.39) | 5493.0 (-33) | **reject** | Heat pump raises LCOE to 47.07 EUR/MWh and CO2 to 5493 t/yr versus 41.68 and 5526: no CO2 gain for much higher cost. |
| 4 | 100,000 m3 pit heat store (2D-2900m-boiler-electric-screw-2xB-pit100k-retref/28) | R0134 | R0118 | 46.47 (+4.79) | 5561.0 (+35) | **reject** | Pit store lifts LCOE to 46.47 EUR/MWh and CO2 to 5561 t/yr: no benefit with a 330-day geothermal source. |
