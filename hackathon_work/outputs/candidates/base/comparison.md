| Metric | C1_2dbl_s1.8_UA1000 | C2_3dbl_s1.8_UA1000 | C3_2dbl_s1.0_UA250 |
|---|---|---|---|
| Doublets / ESP / UA | 2 / s=1.8 (24 st) / 1000 kW/K | 3 / s=1.8 (24 st) / 1000 kW/K | 2 / s=1.0 (10 st) / 250 kW/K |
| Heat pump (eta, COP cap) | 0.45, 6.0 | 0.45, 6.0 | 0.45, 6.0 |
| Unmet heat / cooling (GWh) | 0.000 / 0.000 | 0.000 / 0.000 | 0.000 / 0.000 |
| Heat: HEX / HP / CHP / boiler-ext (GWh) | 45.0 / 55.2 / 11.4 / 0.00 | 45.1 / 54.5 / 12.1 / 0.00 | 29.2 / 67.2 / 9.3 / 6.00 |
| Cooling: absorption / electric (GWh) | 21.06 / 2.68 | 23.31 / 0.44 | 14.27 / 9.47 |
| External gas (GWh fuel / Mm3) | 0.0020 / 0.0002 | 0.0020 / 0.0002 | 7.4981 / 0.7540 |
| Produced gas: CHP / boiler / flared (GWh fuel) | 21.44 / 0.00 / 0.03 | 22.68 / 0.00 / 0.21 | 17.49 / 0.00 / 0.00 |
| Electricity load (GWh): ESP / inj / HP / chiller | 4.87 / 1.107 / 11.22 / 0.54 | 4.83 / 1.152 / 11.11 / 0.09 | 2.75 / 0.716 / 11.68 / 1.89 |
| CHP electricity (GWh) | 5.72 | 6.05 | 4.66 |
| Net grid import / export (GWh) | 12.01 / 0.00 | 11.14 / 0.01 | 12.37 / 0.00 |
| HP seasonal COP (days at cap) | 4.92 (113) | 4.91 (111) | 5.75 (142) |
| Emissions (t CO2/yr): total | 8908 | 8994 | 9559 |
|   produced gas / external gas / grid el. | 5303 / 0 / 3604 | 5652 / 0 / 3342 | 4320 / 1528 / 3712 |
| Peak HP (MWth) | 15.32 | 15.32 | 14.43 |
| Peak absorption / electric chiller (MWcool) | 7.44 / 3.69 | 10.00 / 2.47 | 4.58 / 5.42 |
| Peak CHP (MWth / MWel) / boiler (MWth) | 2.04 / 1.02 / 0.02 | 2.44 / 1.22 / 0.02 | 1.32 / 0.66 / 8.33 |
| Peak external gas (MW fuel) | 0.02 | 0.02 | 10.41 |
| Max brine dT (K) | 40.000 | 40.000 | 40.000 |
| Flow when on (m3/h) | 150-300 | 150-300 | 100-195 |
| Days geothermal + CHP meet need | 274/365 | 346/365 | 134/365 |
| Hard constraints (daily + annual) | PASS | PASS | PASS |
| Rank | 1 | 2 | 3 |
| Verdict | ACCEPTED | REJECTED | REJECTED |

Ranking verdicts:
- **C1_2dbl_s1.8_UA1000**: ACCEPTED - selected: feasible; external gas 0.0020 GWh, emissions 8908 t, grid import 12.01 GWh, 2 doublets, 10000 m drilled
- **C2_3dbl_s1.8_UA1000**: REJECTED - parsimony rule not met: ranks better than C1_2dbl_s1.8_UA1000; extra doublet: external gas +0.0%, emissions -1.0% (needs >= 5% on either, beyond the tie tolerance)
- **C3_2dbl_s1.0_UA250**: REJECTED - same doublet count and depth as C1_2dbl_s1.8_UA1000 but ranks lower on external_gas_fuel_GWh: external gas 7.4981 vs 0.0020 GWh, emissions 9559 vs 8908 t, grid import 12.37 vs 12.01 GWh, drilled 10000 vs 10000 m
