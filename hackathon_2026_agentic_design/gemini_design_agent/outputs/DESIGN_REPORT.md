# GEMINI Agentic Geothermal Design - Final Design Report

Orchestration mode: **rulebased**. Subsurface / well engineering evaluated with the GEMINI digital-twin models (`gemini_model`: radial Darcy inflow, IPR, DPDT wellbore pressure-temperature, ESP curve, CO2 corrosion, API erosional velocity). Heating and cooling plant evaluated with the complementary component models in `gemini_design_agent/components.py`.

## 1. Selected design

| Item | Value | Note |
|---|---|---|
| Number of doublets | 3 | challenge range 1-3 |
| Reservoir midpoint depth | 3500 m TVD | reservoir T 117.0 C, P 351 bar(g) |
| Well measured depth | 3780 m MD | deviated, MD = 1.08 x TVD |
| Production / injection casing ID | 217 / 217 mm |  |
| ESP setting depth | 1000 m | intake 70 bar at 300 m3/h vs bubble point 29 bar |
| ESP | 32 stages, BEP 220 m3/h, VSD 30-65 Hz | 538 kW at 300 m3/h |
| High-temperature heat pump | 2.0 MWth | brine-source, 100 C supply |
| Absorption chiller | 10.0 MWcool | single-effect LiBr, brine-driven |
| Electric chiller | 0.0 MWcool | backup / peak |
| District heating return | 60 C | assumption |
| Corrosion mitigation | inhibitor+GRE-lined tubing | un-mitigated rate 8.2 mm/yr (GEMINI DLM, 20 mol% CO2) |
| Maintenance windows (35 d per doublet) | 2027-05-06 to 2027-06-09; 2027-08-03 to 2027-09-06; 2027-09-07 to 2027-10-11 | staggered, lowest-load period |

### Why this design

- Brine ~114 C allows direct 100 C supply; heat pump kept small (7.5 MW) for top-up.
- Single-effect absorption chiller (10.0 MW) driven by 114 C brine covers the cooling peak.
- Heating unmet on 12 days while every available doublet runs at the 300 m3/h cap and the 40 C brine-cooling cap binds; an additional doublet raises extractable heat.
- Capacities trimmed to 110 % of the peak actually used in the annual simulation.

## 2. Demand interpretation

| Load | Peak | Annual energy | Note |
|---|---|---|---|
| Heating | 30.0 MW on 2027-01-28 | 111.7 GWh/yr | min 2.7 MW |
| Cooling | 10.0 MW on 2027-07-19 | 23.7 GWh/yr | 219 days with cooling |

Heating duration: 25.0 MW exceeded 30 days, 20.1 MW exceeded 90 days, 11.9 MW exceeded 180 days. Daily energy = power x 24 h.

## 3. Annual power and energy balance (330 operating days per doublet)

| Quantity | Value | Detail |
|---|---|---|
| Heat delivered | 111.67 GWh | direct 105.13 + heat pump 6.54 |
| Cooling delivered | 23.74 GWh | absorption 23.74 + electric 0.00 |
| Unmet demand | heat 0.000 / cool 0.000 GWh | must be 0 for feasibility |
| Geothermal heat extracted | 143.26 GWh | peak 29.6 MW |
| Electricity | 7.81 GWh | ESP 3.60, injection 0.94, heat pump 1.38, chillers 1.89 |
| System COP | 17.3 | (heat + cool) / electricity |
| Geothermal (non-electric) share | 94 % | (delivered - electricity) / delivered |
| Flow per doublet | peak 221, mean 136 m3/h | 0 d at cap, 0 d at 50 m3/h minimum |
| Produced = injected volume | 3.24 Mm3/yr | equal liquid volumes, same reservoir |
| Max brine cooling | 40.0 C | cap 40 C; min injection T 64.3 C |
| Associated gas | 2.59 MNm3/yr | GLR 0.8; CO2 1026 t/yr to treatment, CH4 to flare/engine |

## 4. Constraint check (final design)

| Constraint | Value | Status |
|---|---|---|
| Doublets 1-3 | 3 | PASS |
| Max 300 m3/h per doublet | 221.3 | PASS |
| Min 50 m3/h while active | enforced by dispatcher (bypass at minimum) | PASS |
| Max 40 C brine cooling | 40.0 | PASS |
| Pump efficiency 70 % | applied to ESP and injection pump | PASS |
| Production / injection balance | equal volumes | PASS |
| 330 operating days per doublet | 35-day staggered outages | PASS |
| 100 C heating supply | direct HX (if brine >= 103 C) / heat pump | PASS |
| 20 C cooling supply | absorption / electric chillers | PASS |
| ESP intake above bubble point | 70 bar vs 29 bar | PASS |
| Tubing velocity < API erosional | 2.26 < 4.75 m/s | PASS |
| Injection WHP limit | 33.3 bar < 60 | PASS |

Remaining (soft) notices:
- `esp_outside_operating_window` (soft, 8 days, worst 0.40): ESP operating outside 40-135 % of BEP (below 40 % a recirculation line keeps the pump in its window)

## 5. Subsurface / well engineering (GEMINI models)

| Flow m3/h | Prod BHP bar | ESP intake bar | ESP head bar | Hz | ESP kW | WH T C | Inj WHP bar | Inj pump kW | v m/s |
|---|---|---|---|---|---|---|---|---|---|
| 50.00 | 346.92 | 94.16 | 19.11 | 30.00 | 37.91 | 95.99 | 2.55 | 0.00 | 0.38 |
| 100.00 | 342.83 | 89.69 | 23.54 | 33.74 | 93.40 | 105.73 | 8.08 | 8.39 | 0.75 |
| 150.00 | 338.73 | 84.98 | 28.48 | 36.94 | 169.55 | 109.31 | 13.92 | 47.36 | 1.13 |
| 200.00 | 334.64 | 80.06 | 33.74 | 39.69 | 267.77 | 111.16 | 20.07 | 111.97 | 1.50 |
| 250.00 | 330.55 | 74.92 | 39.30 | 42.83 | 389.90 | 112.29 | 26.53 | 204.03 | 1.88 |
| 300.00 | 326.46 | 69.56 | 45.17 | 47.60 | 537.72 | 113.06 | 33.29 | 325.35 | 2.26 |

Productivity index 12.2 m3/h/bar, injectivity index 10.0 m3/h/bar (radial Darcy, k = 200 mD, h = 100 m, re = 1000 m, injector skin 2.0).

## 6. Agent trajectory - how the design was reached

| # | Phase | Design | Action | Feasible | Hard violations | COP | Annual MEUR | EUR/MWh |
|---|---|---|---|---|---|---|---|---|
| 1 | repair | baseline-1dbl-2500m | evaluate | no | unmet_heating (330 d, worst 30.00); unmet_cooling (184 d, worst 10.00); no_doublet_available (35 d, worst 0.00) | 0.0 | 2.73 | inf |
| 2 | repair | baseline-1dbl-2500m-r1 | add doublet | no | unmet_heating (365 d, worst 30.00); unmet_cooling (219 d, worst 10.00) | 0.0 | 5.20 | inf |
| 3 | repair | baseline-1dbl-2500m-r2 | size heat pump | no | unmet_cooling (219 d, worst 10.00) | 3.1 | 10.74 | 96.2 |
| 4 | repair | baseline-1dbl-2500m-r3 | electric chiller | yes | - | 3.8 | 11.03 | 81.4 |
| 5 | repair | baseline-1dbl-2500m-r4 | re-select ESP frame | yes | - | 3.8 | 11.03 | 81.4 |
| 6 | explore | alt-2dbl-2500m-absorption | evaluate | yes | - | 3.8 | 11.64 | 86.0 |
| 7 | explore | alt-2dbl-2500m-absorption-r1 | re-select ESP frame | yes | - | 3.8 | 11.64 | 86.0 |
| 8 | explore | alt-3dbl-2500m-absorption | evaluate | yes | - | 3.7 | 13.35 | 98.6 |
| 9 | explore | alt-3dbl-2500m-absorption-r1 | re-select ESP frame | yes | - | 3.7 | 13.35 | 98.6 |
| 10 | explore | alt-3dbl-2500m-electric | evaluate | yes | - | 3.7 | 12.75 | 94.1 |
| 11 | explore | alt-3dbl-2500m-electric-r1 | re-select ESP frame | yes | - | 3.7 | 12.75 | 94.1 |
| 12 | explore | alt-2dbl-3000m-absorption | evaluate | no | unmet_cooling (28 d, worst 2.28); unmet_heating (12 d, worst 0.16) | 5.0 | 10.63 | 78.9 |
| 13 | explore | alt-2dbl-3000m-absorption-r1 | add doublet | yes | - | 5.1 | 12.47 | 92.1 |
| 14 | explore | alt-2dbl-3000m-absorption-r2 | re-select ESP frame | yes | - | 5.1 | 12.47 | 92.1 |
| 15 | explore | alt-2dbl-3000m-electric | evaluate | yes | - | 4.7 | 10.57 | 78.1 |
| 16 | explore | alt-3dbl-3000m-electric | evaluate | yes | - | 4.7 | 12.50 | 92.3 |
| 17 | explore | alt-3dbl-3000m-electric-r1 | re-select ESP frame | yes | - | 4.7 | 12.50 | 92.3 |
| 18 | explore | alt-2dbl-3500m-absorption | evaluate | no | unmet_heating (12 d, worst 2.91); unmet_cooling (8 d, worst 1.10) | 13.7 | 7.14 | 52.9 |
| 19 | explore | alt-2dbl-3500m-absorption-r1 | add doublet | yes | - | 17.3 | 9.02 | 66.6 |
| 20 | explore | alt-2dbl-3500m-absorption-r2 | re-select ESP frame | yes | - | 17.3 | 9.02 | 66.6 |
| 21 | explore | alt-2dbl-3500m-electric | evaluate | no | unmet_heating (7 d, worst 2.91) | 10.6 | 7.24 | 53.6 |
| 22 | explore | alt-2dbl-3500m-electric-r1 | add doublet | yes | - | 11.2 | 9.28 | 68.5 |
| 23 | explore | alt-2dbl-3500m-electric-r2 | re-select ESP frame | yes | - | 11.2 | 9.28 | 68.5 |
| 24 | explore | alt-2dbl-4000m-absorption | evaluate | no | unmet_heating (12 d, worst 3.03); unmet_cooling (8 d, worst 1.10) | 14.2 | 7.51 | 55.6 |
| 25 | explore | alt-2dbl-4000m-absorption-r1 | add doublet | yes | - | 18.4 | 9.57 | 70.7 |
| 26 | explore | alt-2dbl-4000m-absorption-r2 | re-select ESP frame | yes | - | 18.4 | 9.57 | 70.7 |
| 27 | explore | alt-2dbl-4000m-electric | evaluate | no | unmet_heating (7 d, worst 3.03) | 12.4 | 7.41 | 54.8 |
| 28 | explore | alt-2dbl-4000m-electric-r1 | add doublet | yes | - | 14.3 | 9.57 | 70.7 |
| 29 | explore | alt-2dbl-4000m-electric-r2 | re-select ESP frame | yes | - | 14.3 | 9.57 | 70.6 |
| 30 | refine | alt-2dbl-3500m-absorption-r1~trim | trim capacities | yes | - | 17.3 | 8.60 | 63.5 |
| 31 | refine | alt-2dbl-3500m-absorption-r2~trim | trim capacities | yes | - | 17.3 | 8.60 | 63.5 |

Decision log:

1. **evaluate** (baseline-1dbl-2500m): Deliberately minimal starting point: one doublet at the specified 2,500 m reservoir, no heat pump and no chiller, so every added component is justified by a detected violation.
2. **add doublet** (baseline-1dbl-2500m-r1): Each doublet may only operate 330 days/year; a single doublet leaves 35 days with no supply. A second doublet allows staggered maintenance with continuous supply.
3. **size heat pump** (baseline-1dbl-2500m-r2): Wellhead brine is 85 C, below the 100 C supply; heat pump capacity raised to cover the 30 MW heating peak (+5 % margin).
4. **electric chiller** (baseline-1dbl-2500m-r3): Cooling unmet on 219 days; electric chiller sized for the 10 MW cooling peak.
5. **re-select ESP frame** (baseline-1dbl-2500m-r4): ESP ran outside 40-135 % of BEP on 166 days; pump frame re-selected with BEP 196 m3/h (peak flow / 1.3) so the peak sits inside the window and the VSD plus a recirculation line cover the low-flow days.
6. **evaluate** (alt-2dbl-2500m-absorption): Brine ~84 C is below the 100 C supply: all heat is lifted by a 31.5 MW high-temperature heat pump. Absorption chiller COP is poor at 84 C driving temperature; electric chiller backup sized for the full peak.
7. **re-select ESP frame** (alt-2dbl-2500m-absorption-r1): ESP ran outside 40-135 % of BEP on 166 days; pump frame re-selected with BEP 196 m3/h (peak flow / 1.3) so the peak sits inside the window and the VSD plus a recirculation line cover the low-flow days.
8. **evaluate** (alt-3dbl-2500m-absorption): Brine ~84 C is below the 100 C supply: all heat is lifted by a 31.5 MW high-temperature heat pump. Absorption chiller COP is poor at 84 C driving temperature; electric chiller backup sized for the full peak.
9. **re-select ESP frame** (alt-3dbl-2500m-absorption-r1): ESP ran outside 40-135 % of BEP on 220 days; pump frame re-selected with BEP 130 m3/h (peak flow / 1.3) so the peak sits inside the window and the VSD plus a recirculation line cover the low-flow days.
10. **evaluate** (alt-3dbl-2500m-electric): Brine ~84 C is below the 100 C supply: all heat is lifted by a 31.5 MW high-temperature heat pump. Electric chiller (10.0 MW) covers cooling; geothermal brine serves heating only.
11. **re-select ESP frame** (alt-3dbl-2500m-electric-r1): ESP ran outside 40-135 % of BEP on 220 days; pump frame re-selected with BEP 130 m3/h (peak flow / 1.3) so the peak sits inside the window and the VSD plus a recirculation line cover the low-flow days.
12. **evaluate** (alt-2dbl-3000m-absorption): Brine ~100 C is below the 100 C supply: all heat is lifted by a 31.5 MW high-temperature heat pump. Single-effect absorption chiller (10.0 MW) driven by 100 C brine covers the cooling peak.
13. **add doublet** (alt-2dbl-3000m-absorption-r1): Heating unmet on 12 days while every available doublet runs at the 300 m3/h cap and the 40 C brine-cooling cap binds; an additional doublet raises extractable heat.
14. **re-select ESP frame** (alt-2dbl-3000m-absorption-r2): ESP ran outside 40-135 % of BEP on 28 days; pump frame re-selected with BEP 158 m3/h (peak flow / 1.3) so the peak sits inside the window and the VSD plus a recirculation line cover the low-flow days.
15. **evaluate** (alt-2dbl-3000m-electric): Brine ~100 C is below the 100 C supply: all heat is lifted by a 31.5 MW high-temperature heat pump. Electric chiller (10.0 MW) covers cooling; geothermal brine serves heating only.
16. **evaluate** (alt-3dbl-3000m-electric): Brine ~100 C is below the 100 C supply: all heat is lifted by a 31.5 MW high-temperature heat pump. Electric chiller (10.0 MW) covers cooling; geothermal brine serves heating only.
17. **re-select ESP frame** (alt-3dbl-3000m-electric-r1): ESP ran outside 40-135 % of BEP on 204 days; pump frame re-selected with BEP 143 m3/h (peak flow / 1.3) so the peak sits inside the window and the VSD plus a recirculation line cover the low-flow days.
18. **evaluate** (alt-2dbl-3500m-absorption): Brine ~114 C allows direct 100 C supply; heat pump kept small (7.5 MW) for top-up. Single-effect absorption chiller (10.0 MW) driven by 114 C brine covers the cooling peak.
19. **add doublet** (alt-2dbl-3500m-absorption-r1): Heating unmet on 12 days while every available doublet runs at the 300 m3/h cap and the 40 C brine-cooling cap binds; an additional doublet raises extractable heat.
20. **re-select ESP frame** (alt-2dbl-3500m-absorption-r2): ESP ran outside 40-135 % of BEP on 8 days; pump frame re-selected with BEP 170 m3/h (peak flow / 1.3) so the peak sits inside the window and the VSD plus a recirculation line cover the low-flow days.
21. **evaluate** (alt-2dbl-3500m-electric): Brine ~114 C allows direct 100 C supply; heat pump kept small (7.5 MW) for top-up. Electric chiller (10.0 MW) covers cooling; geothermal brine serves heating only.
22. **add doublet** (alt-2dbl-3500m-electric-r1): Heating unmet on 7 days while every available doublet runs at the 300 m3/h cap and the 40 C brine-cooling cap binds; an additional doublet raises extractable heat.
23. **re-select ESP frame** (alt-2dbl-3500m-electric-r2): ESP ran outside 40-135 % of BEP on 170 days; pump frame re-selected with BEP 170 m3/h (peak flow / 1.3) so the peak sits inside the window and the VSD plus a recirculation line cover the low-flow days.
24. **evaluate** (alt-2dbl-4000m-absorption): Brine ~130 C allows direct 100 C supply; heat pump kept small (7.5 MW) for top-up. Single-effect absorption chiller (10.0 MW) driven by 130 C brine covers the cooling peak.
25. **add doublet** (alt-2dbl-4000m-absorption-r1): Heating unmet on 12 days while every available doublet runs at the 300 m3/h cap and the 40 C brine-cooling cap binds; an additional doublet raises extractable heat.
26. **re-select ESP frame** (alt-2dbl-4000m-absorption-r2): ESP ran outside 40-135 % of BEP on 10 days; pump frame re-selected with BEP 171 m3/h (peak flow / 1.3) so the peak sits inside the window and the VSD plus a recirculation line cover the low-flow days.
27. **evaluate** (alt-2dbl-4000m-electric): Brine ~130 C allows direct 100 C supply; heat pump kept small (7.5 MW) for top-up. Electric chiller (10.0 MW) covers cooling; geothermal brine serves heating only.
28. **add doublet** (alt-2dbl-4000m-electric-r1): Heating unmet on 7 days while every available doublet runs at the 300 m3/h cap and the 40 C brine-cooling cap binds; an additional doublet raises extractable heat.
29. **re-select ESP frame** (alt-2dbl-4000m-electric-r2): ESP ran outside 40-135 % of BEP on 170 days; pump frame re-selected with BEP 171 m3/h (peak flow / 1.3) so the peak sits inside the window and the VSD plus a recirculation line cover the low-flow days.
30. **trim capacities** (alt-2dbl-3500m-absorption-r1~trim): Capacities trimmed to 110 % of the peak actually used in the annual simulation.
31. **trim capacities** (alt-2dbl-3500m-absorption-r2~trim): Capacities trimmed to 110 % of the peak actually used in the annual simulation.

## 7. Feasible alternatives compared

| Design | Dbl | Depth m | HP MW | Abs MW | El.ch MW | El GWh | COP | Geo % | Capex MEUR | Annual MEUR | EUR/MWh |
|---|---|---|---|---|---|---|---|---|---|---|---|
| alt-2dbl-3500m-absorption-r1~trim | 3 | 3500 | 2.0 | 10.0 | 0.0 | 7.8 | 17.3 | 94 | 66.9 | 8.60 | 63.5 |
| alt-2dbl-3500m-absorption-r2~trim | 3 | 3500 | 2.0 | 10.0 | 0.0 | 7.8 | 17.3 | 94 | 66.9 | 8.60 | 63.5 |
| alt-2dbl-3500m-absorption-r1 | 3 | 3500 | 7.5 | 10.0 | 0.0 | 7.8 | 17.3 | 94 | 71.0 | 9.02 | 66.6 |
| alt-2dbl-3500m-absorption-r2 | 3 | 3500 | 7.5 | 10.0 | 0.0 | 7.8 | 17.3 | 94 | 71.0 | 9.02 | 66.6 |
| alt-2dbl-3500m-electric-r2 | 3 | 3500 | 7.5 | 0.0 | 10.0 | 12.1 | 11.2 | 91 | 68.6 | 9.28 | 68.5 |
| alt-2dbl-3500m-electric-r1 | 3 | 3500 | 7.5 | 0.0 | 10.0 | 12.1 | 11.2 | 91 | 68.6 | 9.28 | 68.5 |
| alt-2dbl-4000m-electric-r2 | 3 | 4000 | 7.5 | 0.0 | 10.0 | 9.5 | 14.3 | 93 | 74.4 | 9.57 | 70.6 |
| alt-2dbl-4000m-electric-r1 | 3 | 4000 | 7.5 | 0.0 | 10.0 | 9.5 | 14.3 | 93 | 74.4 | 9.57 | 70.7 |
| alt-2dbl-4000m-absorption-r2 | 3 | 4000 | 7.5 | 10.0 | 0.0 | 7.4 | 18.4 | 95 | 76.9 | 9.57 | 70.7 |
| alt-2dbl-4000m-absorption-r1 | 3 | 4000 | 7.5 | 10.0 | 0.0 | 7.4 | 18.4 | 95 | 76.9 | 9.57 | 70.7 |
| alt-2dbl-3000m-electric | 2 | 3000 | 31.5 | 0.0 | 10.0 | 28.6 | 4.7 | 79 | 64.3 | 10.57 | 78.1 |
| baseline-1dbl-2500m-r4 | 2 | 2500 | 31.5 | 0.0 | 10.0 | 36.0 | 3.8 | 73 | 60.1 | 11.03 | 81.4 |

Cost assumptions: well_fixed_eur = 1.5e+06, well_per_m_md_eur = 1800, esp_eur_per_doublet = 900000, injection_pump_eur_per_doublet = 300000, surface_base_eur = 2.5e+06, surface_eur_per_mw_th = 120000, heat_pump_eur_per_mw = 750000, absorption_eur_per_mw = 400000, electric_chiller_eur_per_mw = 250000, cooling_tower_eur_per_mw_rejected = 80000, electricity_eur_per_mwh = 120, om_fraction_of_capex = 0.025, discount_rate = 0.06, lifetime_years = 25, esp_workover_eur_per_year_per_doublet = 250000.

## 8. Closed-loop geothermal management (25-year twin feedback)

Thermal breakthrough (Gringarten-Sauty) at the assumed well spacing: **125.8 years**; recommended producer-injector spacing at reservoir level: **732 m**.

- Breakthrough sensitivity to spacing: 600 m -> 20 yr, 800 m -> 36 yr, 1000 m -> 56 yr, 1200 m -> 81 yr, 1500 m -> 126 yr, 2000 m -> 224 yr.
- Lifetime electricity: 210 GWh (25.2 MEUR); interventions 19.2 MEUR.
- Years with hard violations before intervention: none.

| Year | Tprod C | Skin+ | ESP eff | Inj WHP | El GWh | COP | HP MW | Controller actions |
|---|---|---|---|---|---|---|---|---|
| 1 | 117.0 | 0.0 | 1.00 | 33 | 7.9 | 17.2 | 2.0 | - |
| 2 | 117.0 | 0.6 | 0.98 | 35 | 8.1 | 16.8 | 2.0 | - |
| 3 | 117.0 | 1.2 | 0.96 | 37 | 8.3 | 16.4 | 2.0 | - |
| 4 | 117.0 | 1.8 | 0.94 | 38 | 8.4 | 16.0 | 2.0 | - |
| 5 | 117.0 | 2.4 | 0.92 | 40 | 8.6 | 15.7 | 2.0 | - |
| 6 | 117.0 | 3.0 | 0.90 | 41 | 8.8 | 15.3 | 2.0 | acid stimulation of injectors (skin +3.0 -> 0; WHP 41 bar); ESP workover / replacement (efficiency factor 0.90 -> 1.00) |
| 7 | 117.0 | 0.6 | 0.98 | 35 | 8.1 | 16.8 | 2.0 | - |
| 8 | 117.0 | 1.2 | 0.96 | 37 | 8.3 | 16.4 | 2.0 | - |
| 9 | 117.0 | 1.8 | 0.94 | 38 | 8.4 | 16.0 | 2.0 | - |
| 10 | 117.0 | 2.4 | 0.92 | 40 | 8.6 | 15.7 | 2.0 | - |
| 11 | 117.0 | 3.0 | 0.90 | 41 | 8.8 | 15.3 | 2.0 | acid stimulation of injectors (skin +3.0 -> 0; WHP 41 bar); ESP workover / replacement (efficiency factor 0.90 -> 1.00) |
| 12 | 117.0 | 0.6 | 0.98 | 35 | 8.1 | 16.8 | 2.0 | - |
| 13 | 117.0 | 1.2 | 0.96 | 37 | 8.3 | 16.4 | 2.0 | - |
| 14 | 117.0 | 1.8 | 0.94 | 38 | 8.4 | 16.0 | 2.0 | - |
| 15 | 117.0 | 2.4 | 0.92 | 40 | 8.6 | 15.7 | 2.0 | - |
| 16 | 117.0 | 3.0 | 0.90 | 41 | 8.8 | 15.3 | 2.0 | acid stimulation of injectors (skin +3.0 -> 0; WHP 41 bar); ESP workover / replacement (efficiency factor 0.90 -> 1.00) |
| 17 | 117.0 | 0.6 | 0.98 | 35 | 8.1 | 16.8 | 2.0 | - |
| 18 | 117.0 | 1.2 | 0.96 | 37 | 8.3 | 16.4 | 2.0 | - |
| 19 | 117.0 | 1.8 | 0.94 | 38 | 8.4 | 16.0 | 2.0 | - |
| 20 | 117.0 | 2.4 | 0.92 | 40 | 8.6 | 15.7 | 2.0 | - |
| 21 | 117.0 | 3.0 | 0.90 | 41 | 8.8 | 15.3 | 2.0 | acid stimulation of injectors (skin +3.0 -> 0; WHP 41 bar); ESP workover / replacement (efficiency factor 0.90 -> 1.00) |
| 22 | 117.0 | 0.6 | 0.98 | 35 | 8.1 | 16.8 | 2.0 | - |
| 23 | 117.0 | 1.2 | 0.96 | 37 | 8.3 | 16.4 | 2.0 | - |
| 24 | 117.0 | 1.8 | 0.94 | 38 | 8.4 | 16.0 | 2.0 | - |
| 25 | 117.0 | 2.4 | 0.92 | 40 | 8.6 | 15.7 | 2.0 | - |

## 9. Figures

![fig_dispatch.png](fig_dispatch.png)

![fig_temps_power.png](fig_temps_power.png)

![fig_well_performance.png](fig_well_performance.png)

![fig_closed_loop.png](fig_closed_loop.png)

## 10. Modelling assumptions and limitations

- Reservoir temperature from the 30 C/km gradient and 12 C surface; pressure hydrostatic anchored on 250 bar(g) at 2,500 m; permeability assumed depth-independent (200 mD).
- Wellbore heat loss from the GEMINI DPDT model marched in 100 m segments with the geothermal gradient as ambient (U = 10 W/m2K in the model).
- ESP curve is the HC27000 stage curve in the GEMINI unit tests, affinity-scaled to the selected pump frame; power from hydraulic head at the specified 70 % efficiency.
- Heat pump COP = 0.5 x Carnot between evaporator (mean brine T - 5 C) and condenser (105 C); absorption chiller COP 0.72 at >= 95 C driving temperature, derated below, off below 72 C.
- Bubble point from a Henry-law estimate for the 0.8 Nm3/m3 CH4/CO2 GLR; ESP intake kept >= 5 bar above it.
- Costs are indicative planning figures (see section 7) for ranking alternatives, not a budget.
- The closed-loop module uses a lumped Gringarten-Sauty breakthrough model; a full reservoir simulation would refine the breakthrough timing.