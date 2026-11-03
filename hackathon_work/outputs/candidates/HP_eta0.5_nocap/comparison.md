| Metric | C1_2dbl_s1.8_UA1000 | C2_3dbl_s1.8_UA1000 | C3_2dbl_s1.0_UA250 |
|---|---|---|---|
| Doublets / ESP / UA | 2 / s=1.8 (24 st) / 1000 kW/K | 3 / s=1.8 (24 st) / 1000 kW/K | 2 / s=1.0 (10 st) / 250 kW/K |
| Heat pump (eta, COP cap) | 0.5, none | 0.5, none | 0.5, none |
| Unmet heat / cooling (GWh) | 0.000 / 0.000 | 0.000 / 0.000 | 0.000 / 0.000 |
| Heat: HEX / HP / CHP / boiler-ext (GWh) | 46.0 / 54.2 / 11.5 / 0.00 | 46.0 / 53.6 / 12.1 / 0.00 | 29.2 / 62.3 / 8.8 / 11.35 |
| Cooling: absorption / electric (GWh) | 21.24 / 2.50 | 23.36 / 0.39 | 13.19 / 10.55 |
| External gas (GWh fuel / Mm3) | 0.0039 / 0.0004 | 0.0039 / 0.0004 | 14.1894 / 1.4269 |
| Produced gas: CHP / boiler / flared (GWh fuel) | 21.54 / 0.00 / 0.03 | 22.67 / 0.00 / 0.19 | 16.41 / 0.00 / 0.00 |
| Electricity load (GWh): ESP / inj / HP / chiller | 6.58 / 0.013 / 9.75 / 0.50 | 6.39 / 0.015 / 9.65 / 0.08 | 2.93 / 0.072 / 9.61 / 2.11 |
| CHP electricity (GWh) | 5.74 | 6.04 | 4.38 |
| Net grid import / export (GWh) | 11.10 / 0.00 | 10.09 / 0.01 | 10.35 / 0.00 |
| HP seasonal COP (days at cap) | 5.56 (0) | 5.55 (0) | 6.49 (0) |
| Emissions (t CO2/yr): total | 8655 | 8674 | 10047 |
|   produced gas / external gas / grid el. | 5326 / 1 / 3329 | 5645 / 1 / 3028 | 4052 / 2891 / 3104 |
| Peak HP (MWth) | 15.19 | 15.19 | 12.46 |
| Peak absorption / electric chiller (MWcool) | 7.56 / 3.63 | 10.00 / 2.36 | 4.18 / 5.82 |
| Peak CHP (MWth / MWel) / boiler (MWth) | 2.04 / 1.02 / 0.02 | 2.39 / 1.20 / 0.02 | 1.19 / 0.60 / 10.76 |
| Peak external gas (MW fuel) | 0.03 | 0.03 | 13.45 |
| Max brine dT (K) | 40.000 | 40.000 | 40.000 |
| Flow when on (m3/h) | 155-300 | 155-300 | 95-176 |
| Days geothermal + CHP meet need | 276/365 | 347/365 | 123/365 |
| Hard constraints (daily + annual) | PASS | PASS | PASS |
| Rank | 1 | 2 | 3 |
| Verdict | ACCEPTED | REJECTED | REJECTED |

Ranking verdicts:
- **C1_2dbl_s1.8_UA1000**: ACCEPTED - selected: feasible; external gas 0.0039 GWh, emissions 8655 t, grid import 11.10 GWh, 2 doublets, 10000 m drilled
- **C2_3dbl_s1.8_UA1000**: REJECTED - parsimony rule not met: ranks better than C1_2dbl_s1.8_UA1000; extra doublet: external gas +0.0%, emissions -0.2% (needs >= 5% on either)
- **C3_2dbl_s1.0_UA250**: REJECTED - same doublet count and depth as C1_2dbl_s1.8_UA1000 but ranks lower on external_gas_fuel_GWh: external gas 14.1894 vs 0.0039 GWh, emissions 10047 vs 8655 t, grid import 10.35 vs 11.10 GWh, drilled 10000 vs 10000 m
