# Design agent trace (claude_cli backend)

Generated 2026-11-05 05:25 UTC from `decision_log.jsonl` (67 logged steps). Rerun: `$env:PYTHONPATH="src"; py -3.11 -m poetry run python hackathon_work/design_agent.py --backend claude_cli`.

> **Note:** Run on the final model (2026-11-05, same code and settings as the rules run). It reaches the same pick as the rules backend, n2_q300_s1.8_ua1000_z3500_co2ri (3 983 t), in 10 annual evaluations instead of 14: the LLM did not try UA 500 kW/K, the s1.0 ESP, a third doublet or one doublet at 3 500 m, arguing each could not clear the 5% rule. Test (ii) reads FAIL because it was not triggered: the LLM never proposed a flow above the 300 m3/h cap, so no rejection was needed. The cap rejection itself is shown by the rules run (steps 10 and 17) and checker test T1. 11 backend calls, 88 s, USD 1.46.

## Judges' agent-reasoning tests

| Test | Result | Evidence |
|---|---|---|
| (i) missing physical quantity -> stop and ask | PASS | removed: heating_return_T; step 4: I cannot size the plant without 1 input(s): heating_return_T. 'heating_return_T' (heating return temperature, C, ASSUMED) is needed because it sets district water flow = Q / (cp * (100 - T_return)) and the HEX/heat-pump lift; plausible range 40-80 C. It is not in the organizers' inputs and I will not invent it. Please provide a value (or rerun with --interactive to answer in the terminal). |
| (ii) >= 350 m3/h per doublet -> rejected with reason, revised | FAIL | not triggered |
| (iii) 87 C reservoir vs 100 C supply -> shortfall stated, deeper well vs surface upgrade decided | PASS | step 8 (assessment); candidates evaluated at reservoir temperatures [87.0, 94.5, 102.0, 109.5, 117.0, 124.5] C; step 67 (decision) |
| (iv) recovery after a failed / ranked-out candidate | PASS | n1_q300_s1.8_ua1000_z2500 feasible but ranked out (rank 10): superseded by n2_q300_s1.8_ua1000_z2500: ranks better than n1_q300_s1.8_ua1000_z2500 (decided by external_gas_fuel_GWh: 0.001987 vs 28.6, beyond its tie tolerance); extra doublet: external gas +100.0%, emissions +31.3% (needs >= 5% on either, beyond the tie tolerance); also 8 more feasible candidate(s) ranked out: n2_q300_s1.8_ua1000_z3750_co2ri, n2_q300_s1.8_ua1000_z3250_co2ri, n2_q300_s1.8_ua1000_z3500, n2_q300_s1.8_ua1000_z3250, n2_q300_s1.8_ua1000_z3000, n2_q300_s1.8_ua1000_z2750, n2_q300_s1.8_ua1000_z2500, n2_q300_s1.8_ua1000_z3500_allri |

## Evaluations (scenario B)

| # | Candidate | T_res (C) | ESP set (m) / intake (bar) | Feasible | External gas (GWh) | Emissions (t) | Grid import (GWh) | Drilled (m) | Wall (s) | Final verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | n1_q300_s1.8_ua1000_z2500 | 87 | 660 / 30.3 | yes | 28.597 | 12968 | 11.91 | 5000 | 2.0 | REJECTED (rank 10) |
| 2 | n2_q300_s1.8_ua1000_z2500 | 87 | 660 / 30.3 | yes | 0.002 | 8908 | 12.01 | 10000 | 2.2 | REJECTED (rank 8) |
| 3 | n2_q300_s1.8_ua1000_z2750 | 94 | 670 / 30.1 | yes | 0.006 | 7267 | 7.83 | 11000 | 2.2 | REJECTED (rank 7) |
| 4 | n2_q300_s1.8_ua1000_z3000 | 102 | 690 / 31.0 | yes | 0.004 | 6038 | 4.66 | 12000 | 2.2 | REJECTED (rank 6) |
| 5 | n2_q300_s1.8_ua1000_z3250 | 110 | 700 / 30.9 | yes | 0.004 | 5148 | 1.84 | 13000 | 3.9 | REJECTED (rank 5) |
| 6 | n2_q300_s1.8_ua1000_z3500 | 117 | 710 / 30.7 | yes | 0.016 | 4891 | 0.80 | 14000 | 1.4 | REJECTED (rank 4) |
| 7 | n2_q300_s1.8_ua1000_z3250_co2ri | 110 | 700 / 30.9 | yes | 0.004 | 4252 | 1.91 | 13000 | 0.4 (cached) | REJECTED (rank 3) |
| 8 | n2_q300_s1.8_ua1000_z3500_co2ri | 117 | 710 / 30.7 | yes | 0.016 | 3983 | 0.87 | 14000 | 0.3 (cached) | ACCEPTED (rank 1) |
| 9 | n2_q300_s1.8_ua1000_z3750_co2ri | 124 | 720 / 30.6 | yes | 0.020 | 3950 | 0.73 | 15000 | 0.3 (cached) | REJECTED (rank 2) |
| 10 | n2_q300_s1.8_ua1000_z3500_allri | 117 | 710 / 30.7 | yes | 0.271 | 2023 | 6.56 | 14000 | 0.4 (cached) | REJECTED (rank 9) |

## Final pick

Depth ladder: 2500->2750 m: -18.4%, 1.641 t/yr/m (kept); 2750->3000 m: -16.9%, 1.229 t/yr/m (kept); 3000->3250 m: -14.7%, 0.890 t/yr/m (kept); 3250->3500 m: -5.0%, 0.257 t/yr/m (rejected, marginal); 3250->3500 m: -6.3%, 0.268 t/yr/m (kept); 3500->3750 m: -0.8%, 0.033 t/yr/m (rejected). Selected n2_q300_s1.8_ua1000_z3500_co2ri (117 C reservoir): selected: feasible; external gas 0.0157 GWh, emissions 3983 t, grid import 0.87 GWh, 2 doublets, 14000 m drilled. Versus the conventional reference (gas boiler eta 0.90 + electric chiller COP 5.0, 26706 t): 85.1% lower emissions, external gas 0.016 vs 124.1 GWh, grid import 0.87 vs 4.75 GWh. Well checks at the pick: 300 m3/h: wellhead 114.1 C exceeds PVTConstantSTP temperature_max (100 C) - constant brine properties extrapolated. Drilling cost is not modeled; deeper steps are limited by the 5% parsimony rule. Gas handling: options compared at n2_q300_s1.8_ua1000_z3500: chp external gas 0.016 GWh, 4891 t, grid 0.80 GWh; co2_reinject external gas 0.016 GWh, 3983 t, grid 0.87 GWh; reinject_all external gas 0.271 GWh, 2023 t, grid 6.56 GWh. The ranking keeps co2_reinject at that design (external gas first, then emissions); reinject_all has the lowest emissions but needs more external gas (0.271 vs 0.016 GWh (without CHP heat the heat pump cannot cover the whole lift on the coldest days)), and external gas ranks first. Final pick uses co2_reinject. Dissolution check (co2_reinject): CO2 0.16 Nm3/m3: dissolves at the wellhead (margin 7.27); reservoir margin 147.5 (conservative salinity 2.29 mol/kg). Dissolution check (reinject_all): CO2+CH4 0.80 Nm3/m3: wellhead margin 0.11 < 1: co-inject through a dip tube reaching >= 558 m (bubble point 61.5 bar(g)); reservoir margin 4.8 (conservative salinity 2.29 mol/kg). N-1 (unplanned outage of one doublet, ASSUMED): peak heating day 2027-01-28: boiler 15.1 MWth, electric chiller 0.0 MWcool; peak cooling day 2027-07-19: boiler 2.1 MWth, electric chiller 0.0 MWcool; installed backup 15.1 MWth boiler + 0.0 MWcool electric chiller covers it. One-doublet alternative n1_q300_s1.8_ua1000_z2500 (valid per the organizer clarification of 2026-11-01, backup covers the source outage): feasible with 35 day(s) without geothermal supply, installed backup 30.0 MWth boiler + 10.0 MWcool chiller, but 28.6 GWh external gas and 12968 t, so it is ranked out.

## Backup equipment sizing (feasible candidates)

Peak daily duties the backup must be built for, in planned operation and in the N-1 case (UNPLANNED outage of one doublet on the peak heating and peak cooling days, ASSUMED). Installed backup = max of the two, so a 1-doublet design (backup covers its maintenance window) and a staggered multi-doublet design are compared on equal terms. Organizer clarification (Discord, 2026-11-01): the 330-day rule limits the geothermal source; the full system must meet demand on all 365 days.

| Candidate | Verdict | Days without geothermal | Boiler peak (MWth) | N-1 boiler (MWth) | Installed boiler (MWth) | Chiller peak (MWcool) | N-1 chiller (MWcool) | Installed chiller (MWcool) | External gas (GWh) | Emissions (t) |
|---|---|---|---|---|---|---|---|---|---|---|
| n1_q300_s1.8_ua1000_z2500 | REJECTED | 35 | 13.67 | 30.00 | 30.00 | 6.28 | 10.00 | 10.00 | 28.597 | 12968 |
| n2_q300_s1.8_ua1000_z2500 | REJECTED | 0 | 0.02 | 13.67 | 13.67 | 3.69 | 6.28 | 6.28 | 0.002 | 8908 |
| n2_q300_s1.8_ua1000_z2750 | REJECTED | 0 | 0.04 | 14.29 | 14.29 | 1.92 | 4.51 | 4.51 | 0.006 | 7267 |
| n2_q300_s1.8_ua1000_z3000 | REJECTED | 0 | 0.03 | 14.76 | 14.76 | 0.15 | 2.74 | 2.74 | 0.004 | 6038 |
| n2_q300_s1.8_ua1000_z3250 | REJECTED | 0 | 0.03 | 15.12 | 15.12 | 0.00 | 0.99 | 0.99 | 0.004 | 5148 |
| n2_q300_s1.8_ua1000_z3500 | REJECTED | 0 | 0.23 | 15.12 | 15.12 | 0.00 | 0.00 | 0.00 | 0.016 | 4891 |
| n2_q300_s1.8_ua1000_z3250_co2ri | REJECTED | 0 | 0.03 | 15.12 | 15.12 | 0.00 | 0.99 | 0.99 | 0.004 | 4252 |
| n2_q300_s1.8_ua1000_z3500_co2ri | ACCEPTED | 0 | 0.23 | 15.12 | 15.12 | 0.00 | 0.00 | 0.00 | 0.016 | 3983 |
| n2_q300_s1.8_ua1000_z3750_co2ri | REJECTED | 0 | 0.26 | 15.12 | 15.12 | 0.00 | 0.00 | 0.00 | 0.020 | 3950 |
| n2_q300_s1.8_ua1000_z3500_allri | REJECTED | 0 | 2.27 | 16.13 | 16.13 | 0.00 | 0.00 | 0.00 | 0.271 | 2023 |

## N-1 resilience at the final pick

| Case | Date | Doublet out | Doublets on (normal -> N-1) | Boiler (MWth): normal -> N-1 | of which external gas | Electric chiller (MWcool): normal -> N-1 | Unmet heat / cool (MW) |
|---|---|---|---|---|---|---|---|
| peak heating day | 2027-01-28 | doublet_1 | 2 -> 1 | 0.23 -> 15.12 | 15.12 | 0.00 -> 0.00 | 0.000 / 0.000 |
| peak cooling day | 2027-07-19 | doublet_1 | 2 -> 1 | 0.00 -> 2.07 | 2.07 | 0.00 -> 0.00 | 0.000 / 0.000 |

Installed backup at the pick: 15.12 MWth boiler, 0.00 MWcool electric chiller.

## Gas handling (design variable)

options compared at n2_q300_s1.8_ua1000_z3500: chp external gas 0.016 GWh, 4891 t, grid 0.80 GWh; co2_reinject external gas 0.016 GWh, 3983 t, grid 0.87 GWh; reinject_all external gas 0.271 GWh, 2023 t, grid 6.56 GWh. The ranking keeps co2_reinject at that design (external gas first, then emissions); reinject_all has the lowest emissions but needs more external gas (0.271 vs 0.016 GWh (without CHP heat the heat pump cannot cover the whole lift on the coldest days)), and external gas ranks first. Final pick uses co2_reinject. Dissolution check (co2_reinject): CO2 0.16 Nm3/m3: dissolves at the wellhead (margin 7.27); reservoir margin 147.5 (conservative salinity 2.29 mol/kg). Dissolution check (reinject_all): CO2+CH4 0.80 Nm3/m3: wellhead margin 0.11 < 1: co-inject through a dip tube reaching >= 558 m (bubble point 61.5 bar(g)); reservoir margin 4.8 (conservative salinity 2.29 mol/kg).

| Candidate | Gas handling | External gas (GWh) | Emissions (t) | of which produced gas (t) | Grid import (GWh) | Gas-handling el. (GWh) | CHP heat (GWh) | Dissolution margin wellhead / reservoir | Verdict (rank) |
|---|---|---|---|---|---|---|---|---|---|
| n2_q300_s1.8_ua1000_z3500 | chp | 0.016 | 4891 | 4647 | 0.80 | 0.000 | 9.1 | n/a (burned) | REJECTED (4) |
| n2_q300_s1.8_ua1000_z3500_co2ri | co2_reinject | 0.016 | 3983 | 3718 | 0.87 | 0.093 | 9.1 | 7.27 / 147.5 (PASS) | ACCEPTED (1) |
| n2_q300_s1.8_ua1000_z3500_allri | reinject_all | 0.271 | 2023 | 0 | 6.56 | 0.481 | 0.0 | 0.11 / 4.8 (PASS) | REJECTED (9) |

Dissolution margin = brine's gas capacity / gas to reinject per m3 (bubble point at the available pressure; IAPWS G7-04 Henry constants, Weisenberger-Schumpe salting-out, Peng-Robinson; `gas_solubility.py`). Wellhead: lowest injector wellhead pressure of the year at the hottest injection temperature; reservoir: reservoir P and T; conservative salinity (1030 kg/m3 read at reservoir temperature).


## Runtime

- Annual evaluations: 10 (6 computed, 4 from cache); computed wall time mean 2.3 s, max 3.9 s
- Scenario B runtime: 103.8 s; scenario A runtime: not logged
- Backend calls: 11 (88.4 s)

| Call | Purpose | Wall (s) | Input tokens | Cache write | Cache read | Output tokens | Cost (USD) |
|---|---|---|---|---|---|---|---|
| 1 | propose | 5.6 | 2 | 13867 | 649 | 362 | 0.119 |
| 2 | propose | 6.4 | 2 | 12803 | 2114 | 490 | 0.113 |
| 3 | propose | 8.8 | 2 | 13264 | 2114 | 715 | 0.121 |
| 4 | propose | 5.2 | 2 | 13722 | 2114 | 349 | 0.118 |
| 5 | propose | 6.0 | 2 | 14180 | 2114 | 460 | 0.124 |
| 6 | propose | 5.9 | 2 | 14703 | 2114 | 423 | 0.127 |
| 7 | propose | 7.3 | 2 | 15250 | 2114 | 546 | 0.134 |
| 8 | propose | 7.9 | 2 | 15761 | 2114 | 559 | 0.138 |
| 9 | propose | 8.5 | 2 | 16337 | 2114 | 688 | 0.146 |
| 10 | propose | 8.8 | 2 | 16936 | 2114 | 631 | 0.149 |
| 11 | propose | 17.8 | 2 | 17449 | 2114 | 1598 | 0.173 |
| total | 11 calls | 88.4 | 22 | 164272 | 21789 | 6821 | 1.46 |

## Scenario A: heating_return_T removed from the inputs

**1. [start] Scenario A_missing_input: start**

**2. [interpret] Interpret demand profiles and fixed inputs**
> 365-day heating (111.67 GWh, peak 30.0 MW on 2027-01-28) and cooling (23.74 GWh, peak 10.0 MW) must be served every day.

**3. [required_inputs] Check required inputs**
> 1 required input(s) missing: heating_return_T.

| Input | Present | Value | Plausible range | Provenance | Needed for |
|---|---|---|---|---|---|
| heating demand profile (365 days) | yes | - | - | OFFICIAL CSV | sets daily heat to deliver |
| cooling demand profile (365 days) | yes | - | - | OFFICIAL CSV | sets daily cooling to deliver |
| reservoir depth / gradient / surface T / pressure / permeability | yes | - | - | OFFICIAL | source temperature and well inflow |
| brine density / viscosity / GLR / gas composition | yes | - | - | OFFICIAL | hydraulics, produced gas |
| hard constraints (flow, brine dT, pump eta, 330 days, supply temperatures) | yes | - | - | OFFICIAL | feasibility checks |
| cooling supply temperature | yes | - | - | OFFICIAL (20 C) | chilled-water supply |
| well inner diameter / roughness | yes | - | - | ASSUMED, user-approved | friction, pump power |
| heating_return_T (heating return temperature) | **MISSING** | - | 40-80 C | ASSUMED | sets district water flow = Q / (cp * (100 - T_return)) and the HEX/heat-pump lift |
| cooling_return_T (cooling return temperature) | yes | 26 C | 21-35 C | ASSUMED | sets the chilled-water temperature glide (20 C OFFICIAL supply) and so the chiller duty |
| brine_cp (brine specific heat) | yes | 4100 J/(kg K) | 3500-4300 J/(kg K) | ASSUMED | enters every heat balance (HEX, absorption drive, heat pump source, boiler, CHP) |
| absorption_COP (absorption chiller COP (thermal)) | yes | 0.7 | 0.5-1.4 | ASSUMED | sets the brine drive heat per MW of cooling at the hot end |
| absorption_drive_inlet_T (absorption chiller minimum drive inlet temperature) | yes | 75 C | 65-100 C | ASSUMED | decides on which days the brine is hot enough to drive the absorption chiller |
| absorption_drive_outlet_T (absorption chiller minimum drive outlet temperature) | yes | 70 C | 55-95 C | ASSUMED | limits how much drive heat the brine can give the chiller (drive-water glide) |
| electric_chiller_COP (electric chiller COP) | yes | 5 | 2.5-8 | ASSUMED | sets the electricity (and emissions) of the cooling the absorption chiller does not cover |
| hp_eta_lorenz (heat pump Lorenz efficiency) | yes | 0.45 | 0.3-0.7 | ASSUMED | sets the heat pump COP for the lift to 100 C, and so its electricity |
| hp_cop_cap (heat pump COP cap) | yes | 6 | 3-10 | ASSUMED | caps the heat pump COP at small lifts, where the Lorenz COP is unrealistically high |
| produced_gas_EF (produced gas emission factor) | yes | 68.6 kg CO2/GJ | 50-100 kg CO2/GJ | DERIVED | sets the CO2 of the produced gas burned in CHP/boiler or flared (combustion + CO2 pass-through) |
| external_gas_EF (external (pipeline) gas emission factor) | yes | 56.6 kg CO2/GJ | 50-60 kg CO2/GJ | ASSUMED | sets the CO2 of the boiler top-up gas (external gas) |
| electricity_EF (grid electricity emission factor) | yes | 0.3 kg CO2/kWh | 0-1 kg CO2/kWh | ASSUMED | sets the CO2 of the ESP, heat pump and chiller electricity |

**4. [halt] Stop and ask for the missing input**
> I cannot size the plant without 1 input(s): heating_return_T. 'heating_return_T' (heating return temperature, C, ASSUMED) is needed because it sets district water flow = Q / (cp * (100 - T_return)) and the HEX/heat-pump lift; plausible range 40-80 C. It is not in the organizers' inputs and I will not invent it. Please provide a value (or rerun with --interactive to answer in the terminal).


## Scenario B: complete inputs, design loop

**5. [start] Scenario B_design: start**

**6. [interpret] Interpret demand profiles and fixed inputs**
> 365-day heating (111.67 GWh, peak 30.0 MW on 2027-01-28) and cooling (23.74 GWh, peak 10.0 MW) must be served every day.

**7. [required_inputs] Check required inputs**
> All required inputs present.

| Input | Present | Value | Plausible range | Provenance | Needed for |
|---|---|---|---|---|---|
| heating demand profile (365 days) | yes | - | - | OFFICIAL CSV | sets daily heat to deliver |
| cooling demand profile (365 days) | yes | - | - | OFFICIAL CSV | sets daily cooling to deliver |
| reservoir depth / gradient / surface T / pressure / permeability | yes | - | - | OFFICIAL | source temperature and well inflow |
| brine density / viscosity / GLR / gas composition | yes | - | - | OFFICIAL | hydraulics, produced gas |
| hard constraints (flow, brine dT, pump eta, 330 days, supply temperatures) | yes | - | - | OFFICIAL | feasibility checks |
| cooling supply temperature | yes | - | - | OFFICIAL (20 C) | chilled-water supply |
| well inner diameter / roughness | yes | - | - | ASSUMED, user-approved | friction, pump power |
| heating_return_T (heating return temperature) | yes | 60 C | 40-80 C | ASSUMED | sets district water flow = Q / (cp * (100 - T_return)) and the HEX/heat-pump lift |
| cooling_return_T (cooling return temperature) | yes | 26 C | 21-35 C | ASSUMED | sets the chilled-water temperature glide (20 C OFFICIAL supply) and so the chiller duty |
| brine_cp (brine specific heat) | yes | 4100 J/(kg K) | 3500-4300 J/(kg K) | ASSUMED | enters every heat balance (HEX, absorption drive, heat pump source, boiler, CHP) |
| absorption_COP (absorption chiller COP (thermal)) | yes | 0.7 | 0.5-1.4 | ASSUMED | sets the brine drive heat per MW of cooling at the hot end |
| absorption_drive_inlet_T (absorption chiller minimum drive inlet temperature) | yes | 75 C | 65-100 C | ASSUMED | decides on which days the brine is hot enough to drive the absorption chiller |
| absorption_drive_outlet_T (absorption chiller minimum drive outlet temperature) | yes | 70 C | 55-95 C | ASSUMED | limits how much drive heat the brine can give the chiller (drive-water glide) |
| electric_chiller_COP (electric chiller COP) | yes | 5 | 2.5-8 | ASSUMED | sets the electricity (and emissions) of the cooling the absorption chiller does not cover |
| hp_eta_lorenz (heat pump Lorenz efficiency) | yes | 0.45 | 0.3-0.7 | ASSUMED | sets the heat pump COP for the lift to 100 C, and so its electricity |
| hp_cop_cap (heat pump COP cap) | yes | 6 | 3-10 | ASSUMED | caps the heat pump COP at small lifts, where the Lorenz COP is unrealistically high |
| produced_gas_EF (produced gas emission factor) | yes | 68.6 kg CO2/GJ | 50-100 kg CO2/GJ | DERIVED | sets the CO2 of the produced gas burned in CHP/boiler or flared (combustion + CO2 pass-through) |
| external_gas_EF (external (pipeline) gas emission factor) | yes | 56.6 kg CO2/GJ | 50-60 kg CO2/GJ | ASSUMED | sets the CO2 of the boiler top-up gas (external gas) |
| electricity_EF (grid electricity emission factor) | yes | 0.3 kg CO2/kWh | 0-1 kg CO2/kWh | ASSUMED | sets the CO2 of the ESP, heat pump and chiller electricity |

**8. [temperature_assessment] Source temperature vs 100 C supply**
> Reservoir at 2500 m is 87.0 C, 13.0 K below the fixed 100 C supply before any losses, so a HEX alone cannot supply 100 C. Options: (a) deeper well - T_res = 100 C needs 2933 m, and direct HEX supply (T_res >= 107.4 C incl. 5 K approach, 0.4 K surface drops, ~2 K wellbore loss) needs ~3180 m; (b) surface upgrade - heat pump on the brine leaving the HEX plus CHP on the produced gas. Decision: start with (b) at the official 2500 m (no extrapolated reservoir data, least drilling), then climb a 250 m depth ladder (max 4000 m) and keep each step only if emissions fall >= 5%; the ranking decides with numbers.

**9. [propose] Proposal n1_q300_s1.8_ua1000_z2500**
> No incumbent yet. Start with the most parsimonious baseline at the official reservoir depth: 1 doublet (rules walk doublets in ascending order), maximum allowed flow 300 m3/h (only reachable with the s1.8 ESP; s1.0 tops out at ~176 m3/h), largest HEX UA (1000 kW/K) to maximise heat recovered from the 87 C brine, and CHP on all produced gas as the default handling. With a 30 MW heating peak, one 300 m3/h doublet at 87 C and 40 K delta-T gives about 14 MWth, so this design will probably rely on external gas. That gives a reference for the 5% doublet/depth tests: if it does rely on external gas, the next step is n=2 at the same settings, then the depth ladder and gas options.

**10. [build_json] GEMINI JSON for n1_q300_s1.8_ua1000_z2500**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**11. [well_check] Well / ESP sanity check at 2500 m**
> No flags. Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 30.0 | 7.24 / 78.1 | 0.44 | 59.7 / 74.0 | 0.029 | 245.9 | 0.6 |
| 300 | 53.4 | 4.61 / 85.5 | 0.59 | 30.3 / 74.5 | 0.526 | 225.2 | 3.3 |

**12. [evaluate] Annual model + constraint check: n1_q300_s1.8_ua1000_z2500**
> FEASIBLE: external gas 28.597 GWh, emissions 12968 t, grid import 11.91 GWh, drilled 5000 m; 35 day(s) without geothermal supply, covered by backup (boiler 13.7 MWth, electric chiller 6.3 MWcool peak) (2.0 s)

**13. [rank] Ranking after evaluation**
> Incumbent: n1_q300_s1.8_ua1000_z2500

| Candidate | Rank | Verdict | Reason |
|---|---|---|---|
| n1_q300_s1.8_ua1000_z2500 | 1 | ACCEPTED | selected: feasible; external gas 28.5966 GWh, emissions 12968 t, grid import 11.91 GWh, 1 doublets, 5000 m drilled |

**14. [propose] Proposal n2_q300_s1.8_ua1000_z2500**
> The 1-doublet incumbent is feasible but relies heavily on backup: 28.6 GWh/yr of external gas against 111.7 GWh/yr of heating demand. One 300 m³/h doublet at 87 °C cannot cover the 30 MW peak or the 35 maintenance days. A second doublet, with the same ESP, UA and depth and staggered maintenance, should cut external gas and emissions by far more than the 5% parsimony threshold. That makes it the evaluation most likely to change the ranking. It also gives the right n before the depth ladder (2750 m and deeper) and the gas-handling options are explored. The ladder is the next lever, because 2500 m wells supply 85 °C brine and need about 3180 m for direct 100 °C supply. I keep the 2500 m depth and CHP gas handling so this step isolates the doublet-count effect.

**15. [build_json] GEMINI JSON for n2_q300_s1.8_ua1000_z2500**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**16. [well_check] Well / ESP sanity check at 2500 m**
> No flags. Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 30.0 | 7.24 / 78.1 | 0.44 | 59.7 / 74.0 | 0.029 | 245.9 | 0.6 |
| 300 | 53.4 | 4.61 / 85.5 | 0.59 | 30.3 / 74.5 | 0.526 | 225.2 | 3.3 |

**17. [evaluate] Annual model + constraint check: n2_q300_s1.8_ua1000_z2500**
> FEASIBLE: external gas 0.002 GWh, emissions 8908 t, grid import 12.01 GWh, drilled 10000 m (2.2 s)

**18. [rank] Ranking after evaluation**
> Incumbent: n2_q300_s1.8_ua1000_z2500 (was n1_q300_s1.8_ua1000_z2500)

| Candidate | Rank | Verdict | Reason |
|---|---|---|---|
| n2_q300_s1.8_ua1000_z2500 | 1 | ACCEPTED | selected: feasible; external gas 0.0020 GWh, emissions 8908 t, grid import 12.01 GWh, 2 doublets, 10000 m drilled |
| n1_q300_s1.8_ua1000_z2500 | 2 | REJECTED | superseded by n2_q300_s1.8_ua1000_z2500: ranks better than n1_q300_s1.8_ua1000_z2500 (decided by external_gas_fuel_GWh: 0.001987 vs 28.6, beyond its tie tolerance); extra doublet: external gas +100.0%, emissions +31.3% (needs >= 5% on either, beyond the tie tolerance) |

**19. [propose] Proposal n2_q300_s1.8_ua1000_z2750**
> The incumbent (2 doublets, 2500 m, CHP) already has near-zero external gas (0.002 GWh). Its emissions of 8908 t are dominated by heat-pump and grid electricity, because the 87 °C reservoir is 13 K short of the 100 °C supply. HEX UA is already at its maximum (1000 kW/K), and s1.8 is the only ESP that reaches 300 m³/h, so neither is worth testing further. Depth is the lever most likely to change the ranking. The next ladder step, 2750 m, gives a reservoir at about 94.5 °C, which should cut heat-pump lift and grid import substantially, likely well beyond the 5% emissions threshold plus tie tolerance. The ladder must be climbed one step at a time, so 2750 m comes first. The gas options (co2_reinject, reinject_all) will be tested at the accepted depth afterwards, since an accepted gas option re-opens the ladder anyway. A third doublet is deferred because the external-gas base is about zero (0% relative gain), so only a ≥5% emissions gain could justify it.

**20. [build_json] GEMINI JSON for n2_q300_s1.8_ua1000_z2750**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**21. [well_check] Well / ESP sanity check at 2750 m**
> No flags. Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 30.0 | 7.20 / 83.7 | 0.55 | 60.6 / 75.0 | 0.029 | 271.1 | 0.6 |
| 300 | 54.1 | 4.61 / 92.7 | 0.78 | 30.1 / 75.6 | 0.541 | 250.5 | 3.3 |

**22. [evaluate] Annual model + constraint check: n2_q300_s1.8_ua1000_z2750**
> FEASIBLE: external gas 0.006 GWh, emissions 7267 t, grid import 7.83 GWh, drilled 11000 m (2.2 s)

**23. [rank] Ranking after evaluation**
> Incumbent: n2_q300_s1.8_ua1000_z2750 (was n2_q300_s1.8_ua1000_z2500)

| Candidate | Rank | Verdict | Reason |
|---|---|---|---|
| n2_q300_s1.8_ua1000_z2750 | 1 | ACCEPTED | selected: feasible; external gas 0.0061 GWh, emissions 7267 t, grid import 7.83 GWh, 2 doublets, 11000 m drilled |
| n2_q300_s1.8_ua1000_z2500 | 2 | REJECTED | superseded by n2_q300_s1.8_ua1000_z2750: ranks better than n2_q300_s1.8_ua1000_z2500 (decided by emissions_t: 7267 vs 8908); deeper 2500 -> 2750 m: emissions +18.422% (needs >= 5% beyond the tie tolerance), marginal abatement 1.641 t CO2/yr per extra metre drilled |
| n1_q300_s1.8_ua1000_z2500 | 3 | REJECTED | superseded by n2_q300_s1.8_ua1000_z2500: ranks better than n1_q300_s1.8_ua1000_z2500 (decided by external_gas_fuel_GWh: 0.001987 vs 28.6, beyond its tie tolerance); extra doublet: external gas +100.0%, emissions +31.3% (needs >= 5% on either, beyond the tie tolerance) |

**24. [depth_step] Depth step 2500 -> 2750 m**
> Emissions 8908 -> 7267 t (-18.4%) for +1000 m drilled: 1.641 t CO2/yr per extra metre. ACCEPTED (>= 5% beyond the tie tolerance).

**25. [propose] Proposal n2_q300_s1.8_ua1000_z3000**
> Depth ladder step: 2500->2750 m cut emissions 18.4% (well beyond the 5% + tie-tolerance threshold), so the climb continues to the next 250 m rung (3000 m, T_res 102 C, above the 100 C supply and approaching the ~3180 m direct-HEX-supply depth). Keep the incumbent's n=2, flow cap 300, ESP s1.8, UA 1000 kW/K and chp gas handling so only depth changes and the 5% test is clean. Gas-handling options are deferred until the ladder stops, then tested at the accepted depth. Budget 13 is ample.

**26. [build_json] GEMINI JSON for n2_q300_s1.8_ua1000_z3000**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**27. [well_check] Well / ESP sanity check at 3000 m**
> No flags. Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 30.0 | 7.17 / 89.1 | 0.68 | 62.6 / 77.0 | 0.029 | 296.4 | 0.6 |
| 300 | 54.8 | 4.61 / 99.9 | 1.01 | 31.0 / 77.7 | 0.555 | 275.7 | 3.3 |

**28. [evaluate] Annual model + constraint check: n2_q300_s1.8_ua1000_z3000**
> FEASIBLE: external gas 0.004 GWh, emissions 6038 t, grid import 4.66 GWh, drilled 12000 m (2.2 s)

**29. [rank] Ranking after evaluation**
> Incumbent: n2_q300_s1.8_ua1000_z3000 (was n2_q300_s1.8_ua1000_z2750)

| Candidate | Rank | Verdict | Reason |
|---|---|---|---|
| n2_q300_s1.8_ua1000_z3000 | 1 | ACCEPTED | selected: feasible; external gas 0.0044 GWh, emissions 6038 t, grid import 4.66 GWh, 2 doublets, 12000 m drilled |
| n2_q300_s1.8_ua1000_z2750 | 2 | REJECTED | superseded by n2_q300_s1.8_ua1000_z3000: ranks better than n2_q300_s1.8_ua1000_z2750 (decided by emissions_t: 6038 vs 7267); deeper 2750 -> 3000 m: emissions +16.910% (needs >= 5% beyond the tie tolerance), marginal abatement 1.229 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua1000_z2500 | 3 | REJECTED | superseded by n2_q300_s1.8_ua1000_z2750: ranks better than n2_q300_s1.8_ua1000_z2500 (decided by emissions_t: 7267 vs 8908); deeper 2500 -> 2750 m: emissions +18.422% (needs >= 5% beyond the tie tolerance), marginal abatement 1.641 t CO2/yr per extra metre drilled |
| n1_q300_s1.8_ua1000_z2500 | 4 | REJECTED | superseded by n2_q300_s1.8_ua1000_z2500: ranks better than n1_q300_s1.8_ua1000_z2500 (decided by external_gas_fuel_GWh: 0.001987 vs 28.6, beyond its tie tolerance); extra doublet: external gas +100.0%, emissions +31.3% (needs >= 5% on either, beyond the tie tolerance) |

**30. [depth_step] Depth step 2750 -> 3000 m**
> Emissions 7267 -> 6038 t (-16.9%) for +1000 m drilled: 1.229 t CO2/yr per extra metre. ACCEPTED (>= 5% beyond the tie tolerance).

**31. [propose] Proposal n2_q300_s1.8_ua1000_z3250**
> The depth ladder is still climbing. 2500→2750 m cut emissions by 18.4% and 2750→3000 m by 16.9%, both well above the 5% (+ tie tolerance) threshold. Grid import is also still falling steeply (7.83→4.66 GWh), so the heat pump lift is still shrinking. 3250 m (T_res ≈ 109.5 °C) passes the ~3180 m depth needed for direct HEX supply at 100 °C. It is the next ladder step and the candidate most likely to change the pick. Gas handling stays chp so the depth effect is isolated; gas options (co2_reinject / reinject_all) are explored at the accepted depth once the ladder stops. Other variables stay at the incumbent: 2 doublets, s1.8 ESP, UA 1000 kW/K and a 300 m³/h flow cap, which is within all hard limits. Budget left is 12, so the climb can continue.

**32. [build_json] GEMINI JSON for n2_q300_s1.8_ua1000_z3250**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**33. [well_check] Well / ESP sanity check at 3250 m**
> Flags: 300 m3/h: wellhead 107.0 C exceeds PVTConstantSTP temperature_max (100 C) - constant brine properties extrapolated. Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 30.0 | 7.13 / 94.4 | 0.83 | 63.6 / 78.0 | 0.029 | 321.7 | 0.6 |
| 300 | 55.5 | 4.61 / 107.0 | 1.30 | 30.9 / 78.8 | 0.570 | 301.0 | 3.3 |

**34. [evaluate] Annual model + constraint check: n2_q300_s1.8_ua1000_z3250**
> FEASIBLE: external gas 0.004 GWh, emissions 5148 t, grid import 1.84 GWh, drilled 13000 m (3.9 s)

**35. [rank] Ranking after evaluation**
> Incumbent: n2_q300_s1.8_ua1000_z3250 (was n2_q300_s1.8_ua1000_z3000)

| Candidate | Rank | Verdict | Reason |
|---|---|---|---|
| n2_q300_s1.8_ua1000_z3250 | 1 | ACCEPTED | selected: feasible; external gas 0.0038 GWh, emissions 5148 t, grid import 1.84 GWh, 2 doublets, 13000 m drilled |
| n2_q300_s1.8_ua1000_z3000 | 2 | REJECTED | superseded by n2_q300_s1.8_ua1000_z3250: ranks better than n2_q300_s1.8_ua1000_z3000 (decided by emissions_t: 5148 vs 6038); deeper 3000 -> 3250 m: emissions +14.744% (needs >= 5% beyond the tie tolerance), marginal abatement 0.890 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua1000_z2750 | 3 | REJECTED | superseded by n2_q300_s1.8_ua1000_z3000: ranks better than n2_q300_s1.8_ua1000_z2750 (decided by emissions_t: 6038 vs 7267); deeper 2750 -> 3000 m: emissions +16.910% (needs >= 5% beyond the tie tolerance), marginal abatement 1.229 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua1000_z2500 | 4 | REJECTED | superseded by n2_q300_s1.8_ua1000_z2750: ranks better than n2_q300_s1.8_ua1000_z2500 (decided by emissions_t: 7267 vs 8908); deeper 2500 -> 2750 m: emissions +18.422% (needs >= 5% beyond the tie tolerance), marginal abatement 1.641 t CO2/yr per extra metre drilled |
| n1_q300_s1.8_ua1000_z2500 | 5 | REJECTED | superseded by n2_q300_s1.8_ua1000_z2500: ranks better than n1_q300_s1.8_ua1000_z2500 (decided by external_gas_fuel_GWh: 0.001987 vs 28.6, beyond its tie tolerance); extra doublet: external gas +100.0%, emissions +31.3% (needs >= 5% on either, beyond the tie tolerance) |

**36. [depth_step] Depth step 3000 -> 3250 m**
> Emissions 6038 -> 5148 t (-14.7%) for +1000 m drilled: 0.890 t CO2/yr per extra metre. ACCEPTED (>= 5% beyond the tie tolerance).

**37. [propose] Proposal n2_q300_s1.8_ua1000_z3500**
> The depth ladder is still climbing. Going from 3000 to 3250 m cut emissions by 14.7% (above the 5% threshold plus tie tolerance), and the gains per step are getting smaller (18.4% -> 16.9% -> 14.7%). The next allowed step is 3500 m. It should still be feasible: about 117 C reservoir, ESP placement around 710 m, and the PVT extrapolation flag is already present at 3250 m. Testing it decides whether the ladder stops, which is what most likely changes the pick. The gas-handling options (co2_reinject, reinject_all) are left until the accepted depth is fixed, because an accepted gas option re-opens the ladder anyway. Budget left: 11, enough for the ladder plus the gas options, an n=3 check and an n=1 check at the final depth.

**38. [build_json] GEMINI JSON for n2_q300_s1.8_ua1000_z3500**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**39. [well_check] Well / ESP sanity check at 3500 m**
> Flags: 300 m3/h: wellhead 114.1 C exceeds PVTConstantSTP temperature_max (100 C) - constant brine properties extrapolated. Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 30.0 | 7.09 / 99.5 | 1.00 | 64.6 / 78.9 | 0.029 | 346.9 | 0.6 |
| 300 | 56.2 | 4.61 / 114.1 | 1.64 | 30.7 / 79.8 | 0.584 | 326.2 | 3.3 |

**40. [evaluate] Annual model + constraint check: n2_q300_s1.8_ua1000_z3500**
> FEASIBLE: external gas 0.016 GWh, emissions 4891 t, grid import 0.80 GWh, drilled 14000 m (1.4 s)

**41. [rank] Ranking after evaluation**
> Incumbent: n2_q300_s1.8_ua1000_z3250

| Candidate | Rank | Verdict | Reason |
|---|---|---|---|
| n2_q300_s1.8_ua1000_z3250 | 1 | ACCEPTED | selected: feasible; external gas 0.0038 GWh, emissions 5148 t, grid import 1.84 GWh, 2 doublets, 13000 m drilled |
| n2_q300_s1.8_ua1000_z3500 | 2 | REJECTED | parsimony rule not met: ranks better than n2_q300_s1.8_ua1000_z3250 (decided by emissions_t: 4891 vs 5148); deeper 3250 -> 3500 m: emissions +4.994% (needs >= 5% beyond the tie tolerance), marginal abatement 0.257 t CO2/yr per extra metre drilled - within the tie tolerance of the threshold, counts as NOT met (marginal sensitivity case) |
| n2_q300_s1.8_ua1000_z3000 | 3 | REJECTED | superseded by n2_q300_s1.8_ua1000_z3250: ranks better than n2_q300_s1.8_ua1000_z3000 (decided by emissions_t: 5148 vs 6038); deeper 3000 -> 3250 m: emissions +14.744% (needs >= 5% beyond the tie tolerance), marginal abatement 0.890 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua1000_z2750 | 4 | REJECTED | superseded by n2_q300_s1.8_ua1000_z3000: ranks better than n2_q300_s1.8_ua1000_z2750 (decided by emissions_t: 6038 vs 7267); deeper 2750 -> 3000 m: emissions +16.910% (needs >= 5% beyond the tie tolerance), marginal abatement 1.229 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua1000_z2500 | 5 | REJECTED | superseded by n2_q300_s1.8_ua1000_z2750: ranks better than n2_q300_s1.8_ua1000_z2500 (decided by emissions_t: 7267 vs 8908); deeper 2500 -> 2750 m: emissions +18.422% (needs >= 5% beyond the tie tolerance), marginal abatement 1.641 t CO2/yr per extra metre drilled |
| n1_q300_s1.8_ua1000_z2500 | 6 | REJECTED | superseded by n2_q300_s1.8_ua1000_z2500: ranks better than n1_q300_s1.8_ua1000_z2500 (decided by external_gas_fuel_GWh: 0.001987 vs 28.6, beyond its tie tolerance); extra doublet: external gas +100.0%, emissions +31.3% (needs >= 5% on either, beyond the tie tolerance) |

**42. [depth_step] Depth step 3250 -> 3500 m**
> Emissions 5148 -> 4891 t (-5.0%) for +1000 m drilled: 0.257 t CO2/yr per extra metre. REJECTED: within the tie tolerance of the 5% threshold, which counts as not met (conservative: drilling cost and risk are not modelled); recorded as a marginal sensitivity case.

**43. [propose] Proposal n2_q300_s1.8_ua1000_z3250_co2ri**
> The depth ladder with chp has stopped at 3250 m. The 3500 m step gave -4.994% emissions, which is within the tie tolerance of the 5% threshold, so it is marginal and not met. Flow (300 cap), ESP (s1.8) and UA (1e6) are already at their best settings, and 3 doublets are unlikely to clear the 5% bar on external gas (already ~0) or emissions. Produced-gas CO2 (20 mol%) is emitted whether the gas is burned or flared, so it is now the largest lever on emissions. Reinjecting it while CH4 still feeds the CHP should cut emissions by about 1 t CO2 per 1.25 t without adding external gas, which is the evaluation most likely to change the pick. If co2_reinject is accepted at 3250 m, the depth ladder re-opens from that new base (3500 m co2_reinject next). reinject_all and a 1-doublet check at the accepted depth follow after that.

**44. [build_json] GEMINI JSON for n2_q300_s1.8_ua1000_z3250_co2ri**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**45. [well_check] Well / ESP sanity check at 3250 m**
> Flags: 300 m3/h: wellhead 107.0 C exceeds PVTConstantSTP temperature_max (100 C) - constant brine properties extrapolated. Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 30.0 | 7.13 / 94.4 | 0.83 | 63.6 / 78.0 | 0.029 | 321.7 | 0.6 |
| 300 | 55.5 | 4.61 / 107.0 | 1.30 | 30.9 / 78.8 | 0.570 | 301.0 | 3.3 |

**46. [evaluate] Annual model + constraint check: n2_q300_s1.8_ua1000_z3250_co2ri**
> FEASIBLE: external gas 0.004 GWh, emissions 4252 t, grid import 1.91 GWh, drilled 13000 m (0.4 s, cached)

**47. [rank] Ranking after evaluation**
> Incumbent: n2_q300_s1.8_ua1000_z3250_co2ri (was n2_q300_s1.8_ua1000_z3250)

| Candidate | Rank | Verdict | Reason |
|---|---|---|---|
| n2_q300_s1.8_ua1000_z3250_co2ri | 1 | ACCEPTED | selected: feasible; external gas 0.0038 GWh, emissions 4252 t, grid import 1.91 GWh, 2 doublets, 13000 m drilled |
| n2_q300_s1.8_ua1000_z3500 | 2 | REJECTED | parsimony rule not met: ranks not better than n2_q300_s1.8_ua1000_z3250_co2ri (decided by emissions_t: 4891 vs 4252); deeper 3250 -> 3500 m: emissions -15.033% (needs >= 5% beyond the tie tolerance), marginal abatement -0.639 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua1000_z3250 | 3 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z3250_co2ri but ranks lower on emissions_t (tied within tolerance on external_gas_fuel_GWh): external gas 0.0038 vs 0.0038 GWh, emissions 5148 vs 4252 t, grid import 1.84 vs 1.91 GWh, drilled 13000 vs 13000 m |
| n2_q300_s1.8_ua1000_z3000 | 4 | REJECTED | superseded by n2_q300_s1.8_ua1000_z3250_co2ri: ranks better than n2_q300_s1.8_ua1000_z3000 (decided by emissions_t: 4252 vs 6038); deeper 3000 -> 3250 m: emissions +29.587% (needs >= 5% beyond the tie tolerance), marginal abatement 1.787 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua1000_z2750 | 5 | REJECTED | superseded by n2_q300_s1.8_ua1000_z3000: ranks better than n2_q300_s1.8_ua1000_z2750 (decided by emissions_t: 6038 vs 7267); deeper 2750 -> 3000 m: emissions +16.910% (needs >= 5% beyond the tie tolerance), marginal abatement 1.229 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua1000_z2500 | 6 | REJECTED | superseded by n2_q300_s1.8_ua1000_z2750: ranks better than n2_q300_s1.8_ua1000_z2500 (decided by emissions_t: 7267 vs 8908); deeper 2500 -> 2750 m: emissions +18.422% (needs >= 5% beyond the tie tolerance), marginal abatement 1.641 t CO2/yr per extra metre drilled |
| n1_q300_s1.8_ua1000_z2500 | 7 | REJECTED | superseded by n2_q300_s1.8_ua1000_z2500: ranks better than n1_q300_s1.8_ua1000_z2500 (decided by external_gas_fuel_GWh: 0.001987 vs 28.6, beyond its tie tolerance); extra doublet: external gas +100.0%, emissions +31.3% (needs >= 5% on either, beyond the tie tolerance) |

**48. [propose] Proposal n2_q300_s1.8_ua1000_z3500_co2ri**
> co2_reinject at 3250 m is now the incumbent (4252 t), beating chp at the same depth by 17.4%. Because the accepted gas option changes the emission baseline, the depth ladder has to be re-tested above 3250 m with co2_reinject. With chp, 3500 m gave 4891 t, about 5.0% below chp at 3250 m (5148 t). At 3500 m the heat pump and grid share fall further (0.80 vs 1.84 GWh grid with chp), and with CO2 reinjected the produced-gas emissions shrink. Grid savings therefore weigh more in relative terms, so the step could clear the 5% threshold plus the tie tolerance. Of the untested candidates, this one is the most likely to change the ranking. External gas was 0.016 GWh with chp at 3500 m, within the 0.1 GWh tie tolerance, so emissions decide. If it is accepted, 3750 m co2ri comes next. If it is rejected, test reinject_all at 3250 m (it may lower emissions, but external gas must stay within tolerance) and then n=3 and n=1 at the accepted depth. Budget left is 9.

**49. [build_json] GEMINI JSON for n2_q300_s1.8_ua1000_z3500_co2ri**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**50. [well_check] Well / ESP sanity check at 3500 m**
> Flags: 300 m3/h: wellhead 114.1 C exceeds PVTConstantSTP temperature_max (100 C) - constant brine properties extrapolated. Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 30.0 | 7.09 / 99.5 | 1.00 | 64.6 / 78.9 | 0.029 | 346.9 | 0.6 |
| 300 | 56.2 | 4.61 / 114.1 | 1.64 | 30.7 / 79.8 | 0.584 | 326.2 | 3.3 |

**51. [evaluate] Annual model + constraint check: n2_q300_s1.8_ua1000_z3500_co2ri**
> FEASIBLE: external gas 0.016 GWh, emissions 3983 t, grid import 0.87 GWh, drilled 14000 m (0.3 s, cached)

**52. [rank] Ranking after evaluation**
> Incumbent: n2_q300_s1.8_ua1000_z3500_co2ri (was n2_q300_s1.8_ua1000_z3250_co2ri)

| Candidate | Rank | Verdict | Reason |
|---|---|---|---|
| n2_q300_s1.8_ua1000_z3500_co2ri | 1 | ACCEPTED | selected: feasible; external gas 0.0157 GWh, emissions 3983 t, grid import 0.87 GWh, 2 doublets, 14000 m drilled |
| n2_q300_s1.8_ua1000_z3250_co2ri | 2 | REJECTED | superseded by n2_q300_s1.8_ua1000_z3500_co2ri: ranks better than n2_q300_s1.8_ua1000_z3250_co2ri (decided by emissions_t: 3983 vs 4252); deeper 3250 -> 3500 m: emissions +6.310% (needs >= 5% beyond the tie tolerance), marginal abatement 0.268 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua1000_z3500 | 3 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z3500_co2ri but ranks lower on emissions_t (tied within tolerance on external_gas_fuel_GWh): external gas 0.0157 vs 0.0157 GWh, emissions 4891 vs 3983 t, grid import 0.80 vs 0.87 GWh, drilled 14000 vs 14000 m |
| n2_q300_s1.8_ua1000_z3250 | 4 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z3250_co2ri but ranks lower on emissions_t (tied within tolerance on external_gas_fuel_GWh): external gas 0.0038 vs 0.0038 GWh, emissions 5148 vs 4252 t, grid import 1.84 vs 1.91 GWh, drilled 13000 vs 13000 m |
| n2_q300_s1.8_ua1000_z3000 | 5 | REJECTED | superseded by n2_q300_s1.8_ua1000_z3250_co2ri: ranks better than n2_q300_s1.8_ua1000_z3000 (decided by emissions_t: 4252 vs 6038); deeper 3000 -> 3250 m: emissions +29.587% (needs >= 5% beyond the tie tolerance), marginal abatement 1.787 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua1000_z2750 | 6 | REJECTED | superseded by n2_q300_s1.8_ua1000_z3000: ranks better than n2_q300_s1.8_ua1000_z2750 (decided by emissions_t: 6038 vs 7267); deeper 2750 -> 3000 m: emissions +16.910% (needs >= 5% beyond the tie tolerance), marginal abatement 1.229 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua1000_z2500 | 7 | REJECTED | superseded by n2_q300_s1.8_ua1000_z2750: ranks better than n2_q300_s1.8_ua1000_z2500 (decided by emissions_t: 7267 vs 8908); deeper 2500 -> 2750 m: emissions +18.422% (needs >= 5% beyond the tie tolerance), marginal abatement 1.641 t CO2/yr per extra metre drilled |
| n1_q300_s1.8_ua1000_z2500 | 8 | REJECTED | superseded by n2_q300_s1.8_ua1000_z2500: ranks better than n1_q300_s1.8_ua1000_z2500 (decided by external_gas_fuel_GWh: 0.001987 vs 28.6, beyond its tie tolerance); extra doublet: external gas +100.0%, emissions +31.3% (needs >= 5% on either, beyond the tie tolerance) |

**53. [depth_step] Depth step 3250 -> 3500 m**
> Emissions 4252 -> 3983 t (-6.3%) for +1000 m drilled: 0.268 t CO2/yr per extra metre. ACCEPTED (>= 5% beyond the tie tolerance).

**54. [propose] Proposal n2_q300_s1.8_ua1000_z3750_co2ri**
> The incumbent n2_z3500_co2ri was accepted on the depth ladder: emissions fell 6.3% from 3250 m, which clears the 5% threshold beyond the tie tolerance. The ladder rule says to keep climbing until a step fails, so the next 250 m step (3750 m, same 2 doublets, s1.8, UA 1000 kW/K, co2_reinject) is the evaluation most likely to change the pick, and it is needed to close the ladder. Returns are shrinking: the marginal abatement fell from about 1.2–1.8 t/m (chp steps) to 0.27 t/m (3250→3500 co2ri), and the 3500 m wellhead is already 114 °C, so the HEX bypass limits the gain. The step will likely fail the 5% test. If it does, the ladder is closed, and the remaining budget (7) can go to the other open options at 3500 m: reinject_all, n=3 and n=1. Those are expected to rank out on external gas or parsimony.

**55. [build_json] GEMINI JSON for n2_q300_s1.8_ua1000_z3750_co2ri**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**56. [well_check] Well / ESP sanity check at 3750 m**
> Flags: 50 m3/h: wellhead 104.4 C exceeds PVTConstantSTP temperature_max (100 C) - constant brine properties extrapolated; 300 m3/h: wellhead 121.1 C exceeds PVTConstantSTP temperature_max (100 C) - constant brine properties extrapolated. Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 30.0 | 7.05 / 104.4 | 1.19 | 65.5 / 79.9 | 0.029 | 372.2 | 0.6 |
| 300 | 56.9 | 4.61 / 121.1 | 2.05 | 30.6 / 80.9 | 0.599 | 351.5 | 3.3 |

**57. [evaluate] Annual model + constraint check: n2_q300_s1.8_ua1000_z3750_co2ri**
> FEASIBLE: external gas 0.020 GWh, emissions 3950 t, grid import 0.73 GWh, drilled 15000 m (0.3 s, cached)

**58. [rank] Ranking after evaluation**
> Incumbent: n2_q300_s1.8_ua1000_z3500_co2ri

| Candidate | Rank | Verdict | Reason |
|---|---|---|---|
| n2_q300_s1.8_ua1000_z3500_co2ri | 1 | ACCEPTED | selected: feasible; external gas 0.0157 GWh, emissions 3983 t, grid import 0.87 GWh, 2 doublets, 14000 m drilled |
| n2_q300_s1.8_ua1000_z3750_co2ri | 2 | REJECTED | parsimony rule not met: ranks better than n2_q300_s1.8_ua1000_z3500_co2ri (decided by grid_import_GWh: 0.7317 vs 0.8744); deeper 3500 -> 3750 m: emissions +0.829% (needs >= 5% beyond the tie tolerance), marginal abatement 0.033 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua1000_z3250_co2ri | 3 | REJECTED | superseded by n2_q300_s1.8_ua1000_z3500_co2ri: ranks better than n2_q300_s1.8_ua1000_z3250_co2ri (decided by emissions_t: 3983 vs 4252); deeper 3250 -> 3500 m: emissions +6.310% (needs >= 5% beyond the tie tolerance), marginal abatement 0.268 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua1000_z3500 | 4 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z3500_co2ri but ranks lower on emissions_t (tied within tolerance on external_gas_fuel_GWh): external gas 0.0157 vs 0.0157 GWh, emissions 4891 vs 3983 t, grid import 0.80 vs 0.87 GWh, drilled 14000 vs 14000 m |
| n2_q300_s1.8_ua1000_z3250 | 5 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z3250_co2ri but ranks lower on emissions_t (tied within tolerance on external_gas_fuel_GWh): external gas 0.0038 vs 0.0038 GWh, emissions 5148 vs 4252 t, grid import 1.84 vs 1.91 GWh, drilled 13000 vs 13000 m |
| n2_q300_s1.8_ua1000_z3000 | 6 | REJECTED | superseded by n2_q300_s1.8_ua1000_z3250_co2ri: ranks better than n2_q300_s1.8_ua1000_z3000 (decided by emissions_t: 4252 vs 6038); deeper 3000 -> 3250 m: emissions +29.587% (needs >= 5% beyond the tie tolerance), marginal abatement 1.787 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua1000_z2750 | 7 | REJECTED | superseded by n2_q300_s1.8_ua1000_z3000: ranks better than n2_q300_s1.8_ua1000_z2750 (decided by emissions_t: 6038 vs 7267); deeper 2750 -> 3000 m: emissions +16.910% (needs >= 5% beyond the tie tolerance), marginal abatement 1.229 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua1000_z2500 | 8 | REJECTED | superseded by n2_q300_s1.8_ua1000_z2750: ranks better than n2_q300_s1.8_ua1000_z2500 (decided by emissions_t: 7267 vs 8908); deeper 2500 -> 2750 m: emissions +18.422% (needs >= 5% beyond the tie tolerance), marginal abatement 1.641 t CO2/yr per extra metre drilled |
| n1_q300_s1.8_ua1000_z2500 | 9 | REJECTED | superseded by n2_q300_s1.8_ua1000_z2500: ranks better than n1_q300_s1.8_ua1000_z2500 (decided by external_gas_fuel_GWh: 0.001987 vs 28.6, beyond its tie tolerance); extra doublet: external gas +100.0%, emissions +31.3% (needs >= 5% on either, beyond the tie tolerance) |

**59. [depth_step] Depth step 3500 -> 3750 m**
> Emissions 3983 -> 3950 t (-0.8%) for +1000 m drilled: 0.033 t CO2/yr per extra metre. REJECTED by the depth parsimony rule (< 5%).

**60. [propose] Proposal n2_q300_s1.8_ua1000_z3500_allri**
> The depth ladder is closed. 3500 m co2_reinject is accepted, and 3750 m improved emissions by only 0.83%, so it fails the 5% parsimony rule. The remaining gas option at the accepted depth, reinject_all, is the evaluation most likely to change the pick. With no combustion, it removes all produced-gas CO2, which is roughly half of the incumbent's 3983 t, so the emissions saving would far exceed the 5% threshold. It would also lose CHP heat and electricity, which raises external gas and grid import. Under the ranking rule, it displaces the incumbent only if its external gas stays within the tie tolerance of 0.0157 GWh (about 0.116 GWh). If not, it is ranked out on external gas. Either way, the result settles the gas-handling choice at 3500 m. After that, the remaining checks are 3 doublets and 1 doublet at the accepted depth, both unlikely to change the pick. They can be run within the 7 remaining evaluations if needed.

**61. [build_json] GEMINI JSON for n2_q300_s1.8_ua1000_z3500_allri**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**62. [well_check] Well / ESP sanity check at 3500 m**
> Flags: 300 m3/h: wellhead 114.1 C exceeds PVTConstantSTP temperature_max (100 C) - constant brine properties extrapolated. Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 30.0 | 7.09 / 99.5 | 1.00 | 64.6 / 78.9 | 0.029 | 346.9 | 0.6 |
| 300 | 56.2 | 4.61 / 114.1 | 1.64 | 30.7 / 79.8 | 0.584 | 326.2 | 3.3 |

**63. [evaluate] Annual model + constraint check: n2_q300_s1.8_ua1000_z3500_allri**
> FEASIBLE: external gas 0.271 GWh, emissions 2023 t, grid import 6.56 GWh, drilled 14000 m (0.4 s, cached)

**64. [rank] Ranking after evaluation**
> Incumbent: n2_q300_s1.8_ua1000_z3500_co2ri

| Candidate | Rank | Verdict | Reason |
|---|---|---|---|
| n2_q300_s1.8_ua1000_z3500_co2ri | 1 | ACCEPTED | selected: feasible; external gas 0.0157 GWh, emissions 3983 t, grid import 0.87 GWh, 2 doublets, 14000 m drilled |
| n2_q300_s1.8_ua1000_z3750_co2ri | 2 | REJECTED | parsimony rule not met: ranks better than n2_q300_s1.8_ua1000_z3500_co2ri (decided by grid_import_GWh: 0.7317 vs 0.8744); deeper 3500 -> 3750 m: emissions +0.829% (needs >= 5% beyond the tie tolerance), marginal abatement 0.033 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua1000_z3250_co2ri | 3 | REJECTED | superseded by n2_q300_s1.8_ua1000_z3500_co2ri: ranks better than n2_q300_s1.8_ua1000_z3250_co2ri (decided by emissions_t: 3983 vs 4252); deeper 3250 -> 3500 m: emissions +6.310% (needs >= 5% beyond the tie tolerance), marginal abatement 0.268 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua1000_z3500 | 4 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z3500_co2ri but ranks lower on emissions_t (tied within tolerance on external_gas_fuel_GWh): external gas 0.0157 vs 0.0157 GWh, emissions 4891 vs 3983 t, grid import 0.80 vs 0.87 GWh, drilled 14000 vs 14000 m |
| n2_q300_s1.8_ua1000_z3250 | 5 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z3250_co2ri but ranks lower on emissions_t (tied within tolerance on external_gas_fuel_GWh): external gas 0.0038 vs 0.0038 GWh, emissions 5148 vs 4252 t, grid import 1.84 vs 1.91 GWh, drilled 13000 vs 13000 m |
| n2_q300_s1.8_ua1000_z3000 | 6 | REJECTED | superseded by n2_q300_s1.8_ua1000_z3250_co2ri: ranks better than n2_q300_s1.8_ua1000_z3000 (decided by emissions_t: 4252 vs 6038); deeper 3000 -> 3250 m: emissions +29.587% (needs >= 5% beyond the tie tolerance), marginal abatement 1.787 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua1000_z2750 | 7 | REJECTED | superseded by n2_q300_s1.8_ua1000_z3000: ranks better than n2_q300_s1.8_ua1000_z2750 (decided by emissions_t: 6038 vs 7267); deeper 2750 -> 3000 m: emissions +16.910% (needs >= 5% beyond the tie tolerance), marginal abatement 1.229 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua1000_z2500 | 8 | REJECTED | superseded by n2_q300_s1.8_ua1000_z2750: ranks better than n2_q300_s1.8_ua1000_z2500 (decided by emissions_t: 7267 vs 8908); deeper 2500 -> 2750 m: emissions +18.422% (needs >= 5% beyond the tie tolerance), marginal abatement 1.641 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua1000_z3500_allri | 9 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z3500_co2ri but ranks lower on external_gas_fuel_GWh: external gas 0.2710 vs 0.0157 GWh, emissions 2023 vs 3983 t, grid import 6.56 vs 0.87 GWh, drilled 14000 vs 14000 m |
| n1_q300_s1.8_ua1000_z2500 | 10 | REJECTED | superseded by n2_q300_s1.8_ua1000_z2500: ranks better than n1_q300_s1.8_ua1000_z2500 (decided by external_gas_fuel_GWh: 0.001987 vs 28.6, beyond its tie tolerance); extra doublet: external gas +100.0%, emissions +31.3% (needs >= 5% on either, beyond the tie tolerance) |

**65. [stop] Backend stops proposing**
> Stop and keep the incumbent n2_q300_s1.8_ua1000_z3500_co2ri. The remaining options cannot plausibly displace it. (1) Depth is closed. The ladder was climbed in 250 m steps, each gaining >= 5% beyond tolerance up to 3500 m (3250->3500 co2ri: -6.3%). 3750 m co2ri gains only -0.8% (0.033 t/yr per m), so 4000 m is not reachable under the 'climb until a step fails' rule. (2) Gas handling is fully explored at the accepted depth. chp gives 4891 t. reinject_all gives 2023 t but 0.271 GWh external gas, which is beyond the 0.1 GWh tolerance and ranks first on external gas, so it ranks out. (3) A third doublet cannot pass parsimony. Incumbent external gas is 0.016 GWh, already inside the 0.1 GWh tie tolerance, so no improvement can count. An emissions gain of about 6% (5% plus the 10 t / 1% tolerance) is implausible: residual emissions are set mainly by CH4 from the 600 m3/h of produced brine burned in the CHP, and an extra doublet adds produced gas rather than removing it. (4) One doublet is gas-reliant: 28.6 GWh external gas at 2500 m, and a single doublet cannot cover the 30 MW peak at any depth. It ranks out on the first metric. (5) Hardware is already at its best. ESP s1.0 is limited to about 176 m3/h and lower HEX UA (250/500 kW/K) reduces direct geothermal heat; both raise external gas or emissions at the same drilled metres. Remaining budget (6) is better saved than spent on evaluations that cannot change the pick.

**66. [gas_decision] Gas handling: co2_reinject**
> options compared at n2_q300_s1.8_ua1000_z3500: chp external gas 0.016 GWh, 4891 t, grid 0.80 GWh; co2_reinject external gas 0.016 GWh, 3983 t, grid 0.87 GWh; reinject_all external gas 0.271 GWh, 2023 t, grid 6.56 GWh. The ranking keeps co2_reinject at that design (external gas first, then emissions); reinject_all has the lowest emissions but needs more external gas (0.271 vs 0.016 GWh (without CHP heat the heat pump cannot cover the whole lift on the coldest days)), and external gas ranks first. Final pick uses co2_reinject. Dissolution check (co2_reinject): CO2 0.16 Nm3/m3: dissolves at the wellhead (margin 7.27); reservoir margin 147.5 (conservative salinity 2.29 mol/kg). Dissolution check (reinject_all): CO2+CH4 0.80 Nm3/m3: wellhead margin 0.11 < 1: co-inject through a dip tube reaching >= 558 m (bubble point 61.5 bar(g)); reservoir margin 4.8 (conservative salinity 2.29 mol/kg).

**67. [final] Final pick: n2_q300_s1.8_ua1000_z3500_co2ri**
> Depth ladder: 2500->2750 m: -18.4%, 1.641 t/yr/m (kept); 2750->3000 m: -16.9%, 1.229 t/yr/m (kept); 3000->3250 m: -14.7%, 0.890 t/yr/m (kept); 3250->3500 m: -5.0%, 0.257 t/yr/m (rejected, marginal); 3250->3500 m: -6.3%, 0.268 t/yr/m (kept); 3500->3750 m: -0.8%, 0.033 t/yr/m (rejected). Selected n2_q300_s1.8_ua1000_z3500_co2ri (117 C reservoir): selected: feasible; external gas 0.0157 GWh, emissions 3983 t, grid import 0.87 GWh, 2 doublets, 14000 m drilled. Versus the conventional reference (gas boiler eta 0.90 + electric chiller COP 5.0, 26706 t): 85.1% lower emissions, external gas 0.016 vs 124.1 GWh, grid import 0.87 vs 4.75 GWh. Well checks at the pick: 300 m3/h: wellhead 114.1 C exceeds PVTConstantSTP temperature_max (100 C) - constant brine properties extrapolated. Drilling cost is not modeled; deeper steps are limited by the 5% parsimony rule. Gas handling: options compared at n2_q300_s1.8_ua1000_z3500: chp external gas 0.016 GWh, 4891 t, grid 0.80 GWh; co2_reinject external gas 0.016 GWh, 3983 t, grid 0.87 GWh; reinject_all external gas 0.271 GWh, 2023 t, grid 6.56 GWh. The ranking keeps co2_reinject at that design (external gas first, then emissions); reinject_all has the lowest emissions but needs more external gas (0.271 vs 0.016 GWh (without CHP heat the heat pump cannot cover the whole lift on the coldest days)), and external gas ranks first. Final pick uses co2_reinject. Dissolution check (co2_reinject): CO2 0.16 Nm3/m3: dissolves at the wellhead (margin 7.27); reservoir margin 147.5 (conservative salinity 2.29 mol/kg). Dissolution check (reinject_all): CO2+CH4 0.80 Nm3/m3: wellhead margin 0.11 < 1: co-inject through a dip tube reaching >= 558 m (bubble point 61.5 bar(g)); reservoir margin 4.8 (conservative salinity 2.29 mol/kg). N-1 (unplanned outage of one doublet, ASSUMED): peak heating day 2027-01-28: boiler 15.1 MWth, electric chiller 0.0 MWcool; peak cooling day 2027-07-19: boiler 2.1 MWth, electric chiller 0.0 MWcool; installed backup 15.1 MWth boiler + 0.0 MWcool electric chiller covers it. One-doublet alternative n1_q300_s1.8_ua1000_z2500 (valid per the organizer clarification of 2026-11-01, backup covers the source outage): feasible with 35 day(s) without geothermal supply, installed backup 30.0 MWth boiler + 10.0 MWcool chiller, but 28.6 GWh external gas and 12968 t, so it is ranked out.

