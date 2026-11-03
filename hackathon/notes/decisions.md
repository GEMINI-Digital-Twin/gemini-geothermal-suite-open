# Decision log

Every value in the model is one of: (1) fact sheet / organiser clarification,
(2) a GEMINI code default, (3) a cited publication, (4) an owner decision with
the owner's reference, (5) a physical constant with a citation, (6) derived by
formula from the above. Numerical settings (grids, tolerances, sample counts)
are method choices and listed separately. All decisions were made by the
owner; Claude proposed options and searched sources for the owner to validate.

## Input assumptions (config/fixed_inputs.yaml)

| Item | Value | Source |
|---|---|---|
| Brine cp | 4,217 J/kgK | GEMINI `PVTConstantSTP` CPL; salinity unknown (owner) |
| Brine cooling cap reading | 40 C drop, producer to injector | Fact sheet status column "hard challenge cap; producer to injector"; organiser: "how much you can cool down the brine" |
| Reservoir pressure vs depth | 250 bar at 2,500 m + hydrostatic gradient | Fact sheet; organisers' hydrostatic instruction (owner: 250 bar is hard data) |
| Injector reservoir pressure | same as producer | Fact sheet: same reservoir |
| Heating return | agent chooses 45-70 C; base 60 C; sensitivity reported | Organisers: participant's choice (owner) |
| Wellhead pressure | 3 bar | GEMINI `doublet_plant.json` boundary input |
| Surface loss to injection pump | 1.55 bar | Derived: GEMINI template run 3.00 -> 1.45 bar at 129 m3/h |
| Well inner diameter | 7 in (0.1778 m) | TNO (2012) R10719 p. 29, DoubletCalc input (owner: fixed, no sourced diameter-cost relation) |
| Pipe roughness | 0.05 mm | Neutrium: carbon steel (new) 0.02-0.05 mm, upper value |
| Skin | producer 1, injector 5; uncertainty 0-5 | TNO (2012) p. 29; DoubletCalc 1.4 manual (TNO 2014 R11396) p. 18 default 0 |
| Drainage radius | r_e = well spacing L | DoubletCalc 1.4 manual Eq. 7 p. 27 (dipole superposition) |
| Spacing | agent chooses 1,000-2,000 m; base 1,600 m | Willems (2017) TU Delft PhD: ~1-1.5 km; DoubletCalc 1.4 p. 37: 1,500-2,000 m; p. 21 example 1,600 m |
| Lifetime | 30 years (hard breakthrough constraint, annual mean flow) | Masterplan Aardwarmte in Nederland (owner) |
| Breakthrough formula | t = pi h L^2 (rho c)_res / (3 Q (rho c)_w) | Gringarten & Sauty (1975) via Wallmeier, Vardon & Daniilidis (2025) Eq. 9 p. 4 (owner to verify equation form) |
| Rock grain cp / density | 730 J/kgK / 2,650 kg/m3 | Quartz (owner) |
| Porosity | 15%; uncertainty 14.6-18.9% | Slochteren core and field studies (owner) |
| Gas liberation | 1.0 (fixed) | Fact sheet definition (owner: no source for a lower bound) |
| CH4 heating value | 50 MJ/kg | GEMINI `doublet_plant.json` caloric_value |
| CH4 density | 0.7168 kg/Nm3 | Engineering ToolBox, methane at 0 C, 1 atm (owner) |
| CO2 density | 1.976 kg/Nm3 | GEMINI `PVTConstantSTP` RHOG |
| Boiler efficiency | 0.8 | GEMINI `doublet_plant.json` |
| PI formula | steady radial Darcy + skin | pengtools wiki (owner); skin term as Whitson, Reservoir Well Performance, Eq. 3 p. A.8-5 |

## Technology (models/surface.py)

| Item | Value | Source |
|---|---|---|
| Heat exchanger approach | 3 C; uncertainty 3-5 C | Slihte, Krizmane & Dzelzitis (2016) CLIMA 2016 |
| Heat pump | Lorenz eta 0.5, no COP cap; uncertainty 0.42-0.61 | GEMINI HeatpumpBasic; Pieper et al. (2020) Energy 205, Table 5 p. 12, Sec. 2.6 p. 12, Sec. 3.3 p. 13 |
| Absorption, rated | COP 0.70, inlet >= 80 C, drop <= 10 K; COP uncertainty 0.65-0.84 | US DOE (2017) p. 4 Table 2; CIBSE Journal Module 91 (2016) |
| Absorption, district-heating type | inlet >= 70 C, outlet >= 50 C | CIBSE Journal Module 91 (2016) |
| Electric chiller | COP 8.6 | NRCan: min COP 6.286 (AHRI 550/590) x 1.37 (Thu et al. 2017) |
| CHP on associated gas | 38% el / 49% heat (LHV); uncertainty to 41/46% | US EPA (2015) Table 2-2 pp. 2-10/2-11, systems 2-3, x1.10 (p. 2-5 fn. 10) |
| Associated gas use | CHP whenever doublets produce; no flaring | GEMINI template (gas to boiler + CHP); measured: boiler route doubles net electricity |
| Removed (no source) | adsorption chiller, heat pump COP cap, heat rejection auxiliary | Owner: remove rather than invent |

## Economics (TNO ThermoGIS as-is)

| Item | Value | Source |
|---|---|---|
| Wells, plant, heat pump, O&M, electricity price, financing, lifetime | ThermoGIS NL defaults | TNO pythermogis "UTC Properties ThermoGIS NL"; "Cost Model" page formula |
| Discount rate | 6.9% | Derived: pre-tax WACC from ThermoGIS financing (80% debt at 5%, 20% equity at 14.5%) |
| Absorption chiller | 580 EUR/kW; O&M 0.66 EUR/MWh | US DOE (2017) p. 4 Table 3, ECB 2025 rate, no inflation |
| Electric chiller | = ThermoGIS heat pump CAPEX / OPEX | Owner (comparable machinery; low sensitivity ~1 EUR/MWh) |
| CHP | 1.25 M EUR/MW; 9.2 EUR/MWh | DEA/Energinet (2012) Technology Data for Energy Plants, p. 19 (sheet 06 p. 54) |
| Gas boiler | 0.10 M EUR/MW; 3,700 EUR/MW/yr | DEA/Energinet (2012) table 44, pp. 19/22/25 (O&M column ambiguous: owner to verify) |
| Natural gas | 42.46 EUR/MWh; uncertainty 26.56-58.36 | ACER CHEST, gas prices 2025 (midpoint of range) |
| LCOH definition | per MWh of heat + cooling delivered | Owner |
| Benchmark | 63-133 EUR/MWh | PBL Advies basisbedragen SDE++ 2026, Table 3.9 (sanity check only) |

## Uncertainty and decision rule

| Item | Decision | Source |
|---|---|---|
| Convention | P90 = conservative case for every KPI | SPE/WPC Petroleum Reserves Definitions (1997) |
| Objective | lowest P50 LCOH | Owner |
| Robustness | feasible in >= 90% of samples | Owner (P90 convention) |
| Agent | goal-only system prompt; usage guidance in tool documentation | Owner (option iii') |

## Method choices (not data)

Flow grid 50-300 m3/h in 25 m3/h steps; daily flow = lowest within 1% of
least backup; 25 well segments for wellhead temperature; uniform independent
sampling, seed 2027, 100 samples; heat pump log-mean lift floored at 1 K
(numerical guard); agent step cap 30; LLM temperature 0.2.
