# Design agent trace (rules backend, interactive)

Generated 2026-11-05 06:30 UTC from `decision_log.jsonl` (95 logged steps). Rerun: `$env:PYTHONPATH="src"; py -3.11 -m poetry run python hackathon_work/design_agent.py --backend rules`.

## Judges' agent-reasoning tests

| Test | Result | Evidence |
|---|---|---|
| (i) missing physical quantity -> stop and ask | PASS | removed: heating_return_T; step 8 AGENT ASKED: I cannot size the plant without the heating return temperature (heating_return_T, ASSUMED). It is needed because it sets district water flow = Q / (cp * (100 - T_return)) and the HEX/heat-pump lift. It is not in the organizers' inputs and I will not invent it. Please type a value in C (plausible range 40-80 C), or 'q' to stop. -> step 9 USER ANSWERED '60': accepted, 60 C. |
| (ii) >= 350 m3/h per doublet -> rejected with reason, revised | PASS | step 21: 350.00 m3/h exceeds the 300 m3/h hard cap -> step 22: Revised to n2_q300_s1.8_ua1000_z2500; also step 14: 650.00 m3/h exceeds the 300 m3/h hard cap -> step 15: Revised to n1_q300_s1.8_ua1000_z2500 |
| (iii) 87 C reservoir vs 100 C supply -> shortfall stated, deeper well vs surface upgrade decided | PASS | step 12 (assessment); candidates evaluated at reservoir temperatures [87.0, 94.5, 102.0, 109.5, 117.0, 124.5] C; step 95 (decision) |
| (iv) recovery after a failed / ranked-out candidate | PASS | step 14: 650.00 m3/h exceeds the 300 m3/h hard cap (hard limit) -> step 15: Revised to n1_q300_s1.8_ua1000_z2500 -> step 18: n1_q300_s1.8_ua1000_z2500 feasible; also n1_q300_s1.8_ua1000_z2500 feasible but ranked out (rank 13): superseded by n2_q300_s1.8_ua1000_z2500: ranks better than n1_q300_s1.8_ua1000_z2500 (decided by external_gas_fuel_GWh: 0.001987 vs 28.6, beyond its tie tolerance); extra doublet: external gas +100.0%, emissions +31.3% (needs >= 5% on either, beyond the tie tolerance); also n1_q300_s1.8_ua1000_z3500_co2ri feasible but ranked out (rank 14): parsimony rule not met: ranks not better than n1_q300_s1.8_ua1000_z2500 (decided by external_gas_fuel_GWh: 36.46 vs 28.6, beyond its tie tolerance); deeper 2500 -> 3500 m: emissions +16.853% (needs >= 5% beyond the tie tolerance), marginal abatement 1.093 t CO2/yr per extra metre drilled; also 11 more feasible candidate(s) ranked out: n2_q300_s1.8_ua1000_z3750_co2ri, n3_q300_s1.8_ua1000_z3500_co2ri, n2_q300_s1.8_ua1000_z3250_co2ri, n2_q300_s1.8_ua1000_z3500, n2_q300_s1.8_ua1000_z3250, n2_q300_s1.8_ua1000_z3000, n2_q300_s1.8_ua1000_z2750, n2_q300_s1.8_ua1000_z2500, n2_q300_s1.8_ua500_z2500, n2_q300_s1.8_ua1000_z3500_allri, n2_q300_s1.0_ua1000_z2500 |

## Evaluations (scenario A)

| # | Candidate | T_res (C) | ESP set (m) / intake (bar) | Feasible | External gas (GWh) | Emissions (t) | Grid import (GWh) | Drilled (m) | Wall (s) | Final verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | n1_q300_s1.8_ua1000_z2500 | 87 | 660 / 30.3 | yes | 28.597 | 12968 | 11.91 | 5000 | 0.8 | REJECTED (rank 13) |
| 2 | n2_q300_s1.8_ua1000_z2500 | 87 | 660 / 30.3 | yes | 0.002 | 8908 | 12.01 | 10000 | 0.9 | REJECTED (rank 9) |
| 3 | n2_q300_s1.8_ua500_z2500 | 87 | 660 / 30.3 | yes | 0.008 | 9036 | 12.50 | 10000 | 0.8 | REJECTED (rank 10) |
| 4 | n2_q300_s1.0_ua1000_z2500 | 87 | 530 / 30.7 | yes | 8.090 | 9429 | 11.49 | 10000 | 0.8 | REJECTED (rank 12) |
| 5 | n2_q300_s1.8_ua1000_z2750 | 94 | 670 / 30.1 | yes | 0.006 | 7267 | 7.83 | 11000 | 0.9 | REJECTED (rank 8) |
| 6 | n2_q300_s1.8_ua1000_z3000 | 102 | 690 / 31.0 | yes | 0.004 | 6038 | 4.66 | 12000 | 0.9 | REJECTED (rank 7) |
| 7 | n2_q300_s1.8_ua1000_z3250 | 110 | 700 / 30.9 | yes | 0.004 | 5148 | 1.84 | 13000 | 1.5 | REJECTED (rank 6) |
| 8 | n2_q300_s1.8_ua1000_z3500 | 117 | 710 / 30.7 | yes | 0.016 | 4891 | 0.80 | 14000 | 0.6 | REJECTED (rank 5) |
| 9 | n2_q300_s1.8_ua1000_z3250_co2ri | 110 | 700 / 30.9 | yes | 0.004 | 4252 | 1.91 | 13000 | 1.5 | REJECTED (rank 4) |
| 10 | n2_q300_s1.8_ua1000_z3500_co2ri | 117 | 710 / 30.7 | yes | 0.016 | 3983 | 0.87 | 14000 | 0.6 | ACCEPTED (rank 1) |
| 11 | n2_q300_s1.8_ua1000_z3750_co2ri | 124 | 720 / 30.6 | yes | 0.020 | 3950 | 0.73 | 15000 | 0.6 | REJECTED (rank 2) |
| 12 | n2_q300_s1.8_ua1000_z3500_allri | 117 | 710 / 30.7 | yes | 0.271 | 2023 | 6.56 | 14000 | 0.6 | REJECTED (rank 11) |
| 13 | n3_q300_s1.8_ua1000_z3500_co2ri | 117 | 710 / 30.7 | yes | 0.004 | 3979 | 0.87 | 21000 | 0.6 | REJECTED (rank 3) |
| 14 | n1_q300_s1.8_ua1000_z3500_co2ri | 117 | 710 / 30.7 | yes | 36.457 | 10783 | 1.75 | 7000 | 0.5 | REJECTED (rank 14) |

## Final pick

Depth ladder: 2500->2750 m: -18.4%, 1.641 t/yr/m (kept); 2750->3000 m: -16.9%, 1.229 t/yr/m (kept); 3000->3250 m: -14.7%, 0.890 t/yr/m (kept); 3250->3500 m: -5.0%, 0.257 t/yr/m (rejected, marginal); 3250->3500 m: -6.3%, 0.268 t/yr/m (kept); 3500->3750 m: -0.8%, 0.033 t/yr/m (rejected). Selected n2_q300_s1.8_ua1000_z3500_co2ri (117 C reservoir): selected: feasible; external gas 0.0157 GWh, emissions 3983 t, grid import 0.87 GWh, 2 doublets, 14000 m drilled. Versus the conventional reference (gas boiler eta 0.90 + electric chiller COP 5.0, 26706 t): 85.1% lower emissions, external gas 0.016 vs 124.1 GWh, grid import 0.87 vs 4.75 GWh. Well checks at the pick: 300 m3/h: wellhead 114.1 C exceeds PVTConstantSTP temperature_max (100 C) - constant brine properties extrapolated. Drilling cost is not modeled; deeper steps are limited by the 5% parsimony rule. Gas handling: options compared at n2_q300_s1.8_ua1000_z3500: chp external gas 0.016 GWh, 4891 t, grid 0.80 GWh; co2_reinject external gas 0.016 GWh, 3983 t, grid 0.87 GWh; reinject_all external gas 0.271 GWh, 2023 t, grid 6.56 GWh. The ranking keeps co2_reinject at that design (external gas first, then emissions); reinject_all has the lowest emissions but needs more external gas (0.271 vs 0.016 GWh (without CHP heat the heat pump cannot cover the whole lift on the coldest days)), and external gas ranks first. Final pick uses co2_reinject. Dissolution check (co2_reinject): CO2 0.16 Nm3/m3: dissolves at the wellhead (margin 7.27); reservoir margin 147.5 (conservative salinity 2.29 mol/kg). Dissolution check (reinject_all): CO2+CH4 0.80 Nm3/m3: wellhead margin 0.11 < 1: co-inject through a dip tube reaching >= 558 m (bubble point 61.5 bar(g)); reservoir margin 4.8 (conservative salinity 2.29 mol/kg). N-1 (unplanned outage of one doublet, ASSUMED): peak heating day 2027-01-28: boiler 15.1 MWth, electric chiller 0.0 MWcool; peak cooling day 2027-07-19: boiler 2.1 MWth, electric chiller 0.0 MWcool; installed backup 15.1 MWth boiler + 0.0 MWcool electric chiller covers it. One-doublet alternative n1_q300_s1.8_ua1000_z2500 (valid per the organizer clarification of 2026-11-01, backup covers the source outage): feasible with 35 day(s) without geothermal supply, installed backup 30.0 MWth boiler + 10.0 MWcool chiller, but 28.6 GWh external gas and 12968 t, so it is ranked out. One-doublet alternative n1_q300_s1.8_ua1000_z3500_co2ri (valid per the organizer clarification of 2026-11-01, backup covers the source outage): feasible with 35 day(s) without geothermal supply, installed backup 30.0 MWth boiler + 10.0 MWcool chiller, but 36.5 GWh external gas and 10783 t, so it is ranked out.

## Backup equipment sizing (feasible candidates)

Peak daily duties the backup must be built for, in planned operation and in the N-1 case (UNPLANNED outage of one doublet on the peak heating and peak cooling days, ASSUMED). Installed backup = max of the two, so a 1-doublet design (backup covers its maintenance window) and a staggered multi-doublet design are compared on equal terms. Organizer clarification (Discord, 2026-11-01): the 330-day rule limits the geothermal source; the full system must meet demand on all 365 days.

| Candidate | Verdict | Days without geothermal | Boiler peak (MWth) | N-1 boiler (MWth) | Installed boiler (MWth) | Chiller peak (MWcool) | N-1 chiller (MWcool) | Installed chiller (MWcool) | External gas (GWh) | Emissions (t) |
|---|---|---|---|---|---|---|---|---|---|---|
| n1_q300_s1.8_ua1000_z2500 | REJECTED | 35 | 13.67 | 30.00 | 30.00 | 6.28 | 10.00 | 10.00 | 28.597 | 12968 |
| n2_q300_s1.8_ua1000_z2500 | REJECTED | 0 | 0.02 | 13.67 | 13.67 | 3.69 | 6.28 | 6.28 | 0.002 | 8908 |
| n2_q300_s1.8_ua500_z2500 | REJECTED | 0 | 0.03 | 13.53 | 13.53 | 3.69 | 6.28 | 6.28 | 0.008 | 9036 |
| n2_q300_s1.0_ua1000_z2500 | REJECTED | 0 | 8.63 | 19.47 | 19.47 | 5.42 | 7.71 | 7.71 | 8.090 | 9429 |
| n2_q300_s1.8_ua1000_z2750 | REJECTED | 0 | 0.04 | 14.29 | 14.29 | 1.92 | 4.51 | 4.51 | 0.006 | 7267 |
| n2_q300_s1.8_ua1000_z3000 | REJECTED | 0 | 0.03 | 14.76 | 14.76 | 0.15 | 2.74 | 2.74 | 0.004 | 6038 |
| n2_q300_s1.8_ua1000_z3250 | REJECTED | 0 | 0.03 | 15.12 | 15.12 | 0.00 | 0.99 | 0.99 | 0.004 | 5148 |
| n2_q300_s1.8_ua1000_z3500 | REJECTED | 0 | 0.23 | 15.12 | 15.12 | 0.00 | 0.00 | 0.00 | 0.016 | 4891 |
| n2_q300_s1.8_ua1000_z3250_co2ri | REJECTED | 0 | 0.03 | 15.12 | 15.12 | 0.00 | 0.99 | 0.99 | 0.004 | 4252 |
| n2_q300_s1.8_ua1000_z3500_co2ri | ACCEPTED | 0 | 0.23 | 15.12 | 15.12 | 0.00 | 0.00 | 0.00 | 0.016 | 3983 |
| n2_q300_s1.8_ua1000_z3750_co2ri | REJECTED | 0 | 0.26 | 15.12 | 15.12 | 0.00 | 0.00 | 0.00 | 0.020 | 3950 |
| n2_q300_s1.8_ua1000_z3500_allri | REJECTED | 0 | 2.27 | 16.13 | 16.13 | 0.00 | 0.00 | 0.00 | 0.271 | 2023 |
| n3_q300_s1.8_ua1000_z3500_co2ri | REJECTED | 0 | 0.03 | 0.23 | 0.23 | 0.00 | 0.00 | 0.00 | 0.004 | 3979 |
| n1_q300_s1.8_ua1000_z3500_co2ri | REJECTED | 35 | 15.12 | 30.00 | 30.00 | 5.89 | 10.00 | 10.00 | 36.457 | 10783 |

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
| n2_q300_s1.8_ua1000_z3500 | chp | 0.016 | 4891 | 4647 | 0.80 | 0.000 | 9.1 | n/a (burned) | REJECTED (5) |
| n2_q300_s1.8_ua1000_z3500_co2ri | co2_reinject | 0.016 | 3983 | 3718 | 0.87 | 0.093 | 9.1 | 7.27 / 147.5 (PASS) | ACCEPTED (1) |
| n2_q300_s1.8_ua1000_z3500_allri | reinject_all | 0.271 | 2023 | 0 | 6.56 | 0.481 | 0.0 | 0.11 / 4.8 (PASS) | REJECTED (11) |

Dissolution margin = brine's gas capacity / gas to reinject per m3 (bubble point at the available pressure; IAPWS G7-04 Henry constants, Weisenberger-Schumpe salting-out, Peng-Robinson; `gas_solubility.py`). Wellhead: lowest injector wellhead pressure of the year at the hottest injection temperature; reservoir: reservoir P and T; conservative salinity (1030 kg/m3 read at reservoir temperature).


## Runtime

- Annual evaluations: 14 (14 computed, 0 from cache); computed wall time mean 0.8 s, max 1.5 s
- Scenario B runtime: 26.0 s; scenario A runtime: 26.0 s
- Backend calls: 0 (0.0 s)

## Scenario A: heating_return_T removed from the inputs (interactive: the agent asks, the user answers, the design loop continues)

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

**4. AGENT ASKED** (2026-11-05 06:30:01 UTC)
> I cannot size the plant without the heating return temperature (heating_return_T, ASSUMED). It is needed because it sets district water flow = Q / (cp * (100 - T_return)) and the HEX/heat-pump lift. It is not in the organizers' inputs and I will not invent it. Please type a value in C (plausible range 40-80 C), or 'q' to stop.

**5. USER ANSWERED** (2026-11-05 06:30:06 UTC)
> 'abc': rejected - it is not a number in C (expected e.g. 60 C)

**6. AGENT ASKED** (2026-11-05 06:30:06 UTC)
> I cannot size the plant without the heating return temperature (heating_return_T, ASSUMED). It is needed because it sets district water flow = Q / (cp * (100 - T_return)) and the HEX/heat-pump lift. It is not in the organizers' inputs and I will not invent it. Please type a value in C (plausible range 40-80 C), or 'q' to stop.

**7. USER ANSWERED** (2026-11-05 06:30:11 UTC)
> '95': rejected - 95 C is outside the plausible 40-80 C range (a district heating return for a 100 C supply is typically 40-80 C: below 40 C is atypical for a 100 C network, above 80 C leaves less than 20 K for the district water and the HEX/heat-pump lift)

**8. AGENT ASKED** (2026-11-05 06:30:11 UTC)
> I cannot size the plant without the heating return temperature (heating_return_T, ASSUMED). It is needed because it sets district water flow = Q / (cp * (100 - T_return)) and the HEX/heat-pump lift. It is not in the organizers' inputs and I will not invent it. Please type a value in C (plausible range 40-80 C), or 'q' to stop.

**9. USER ANSWERED** (2026-11-05 06:30:16 UTC)
> '60': accepted, 60 C.

**10. [interpret] Interpret demand profiles and fixed inputs**
> 365-day heating (111.67 GWh, peak 30.0 MW on 2027-01-28) and cooling (23.74 GWh, peak 10.0 MW) must be served every day.

**11. [required_inputs] Check required inputs**
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

**12. [temperature_assessment] Source temperature vs 100 C supply**
> Reservoir at 2500 m is 87.0 C, 13.0 K below the fixed 100 C supply before any losses, so a HEX alone cannot supply 100 C. Options: (a) deeper well - T_res = 100 C needs 2933 m, and direct HEX supply (T_res >= 107.4 C incl. 5 K approach, 0.4 K surface drops, ~2 K wellbore loss) needs ~3180 m; (b) surface upgrade - heat pump on the brine leaving the HEX plus CHP on the produced gas. Decision: start with (b) at the official 2500 m (no extrapolated reservoir data, least drilling), then climb a 250 m depth ladder (max 4000 m) and keep each step only if emissions fall >= 5%; the ranking decides with numbers.

**13. [propose] Proposal n1_q650_s1.8_ua1000_z2500**
> Start with the fewest doublets (1): the ranking prefers fewer doublets, so the smallest plant that passes the hard constraints is the target. Flow sizing heuristic: peak 30.0 MW / 1 doublet(s) at the 40 K brine cap -> 639.4 m3/h per doublet, rounded up to 650 m3/h. Largest ESP (s = 1.8), HEX 1000 kW/K, official 2500 m reservoir.

**14. [validate] Rejected before simulation: n1_q650_s1.8_ua1000_z2500**
> 650.00 m3/h exceeds the 300 m3/h hard cap

**15. [revise] Revised to n1_q300_s1.8_ua1000_z2500**
> Clip to the nearest admissible value: flow_cap_m3h 650 -> 300 (650.00 m3/h exceeds the 300 m3/h hard cap). The proposal's intent (largest admissible flow) is kept; the shortfall is left to the heat pump / CHP and to more doublets if needed.

**16. [build_json] GEMINI JSON for n1_q300_s1.8_ua1000_z2500**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**17. [well_check] Well / ESP sanity check at 2500 m**
> No flags. Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 30.0 | 7.24 / 78.1 | 0.44 | 59.7 / 74.0 | 0.029 | 245.9 | 0.6 |
| 300 | 53.4 | 4.61 / 85.5 | 0.59 | 30.3 / 74.5 | 0.526 | 225.2 | 3.3 |

**18. [evaluate] Annual model + constraint check: n1_q300_s1.8_ua1000_z2500**
> FEASIBLE: external gas 28.597 GWh, emissions 12968 t, grid import 11.91 GWh, drilled 5000 m; 35 day(s) without geothermal supply, covered by backup (boiler 13.7 MWth, electric chiller 6.3 MWcool peak) (0.8 s)

**19. [rank] Ranking after evaluation**
> Incumbent: n1_q300_s1.8_ua1000_z2500

| Candidate | Rank | Verdict | Reason |
|---|---|---|---|
| n1_q300_s1.8_ua1000_z2500 | 1 | ACCEPTED | selected: feasible; external gas 28.5966 GWh, emissions 12968 t, grid import 11.91 GWh, 1 doublets, 5000 m drilled |

**20. [propose] Proposal n2_q350_s1.8_ua1000_z2500**
> n1_q300_s1.8_ua1000_z2500 is feasible (the 330-day rule limits the geothermal source; backup may cover the outage - organizer clarification 2026-11-01), but it has 35 day(s) without geothermal supply and needs 28.6 GWh of external gas with a 13.7 MWth backup boiler and a 6.3 MWcool electric chiller. External gas ranks first, so compare 2 doublets with staggered maintenance before refining the 1-doublet design. Flow sizing heuristic: peak 30.0 MW / 2 doublet(s) at the 40 K brine cap -> 319.7 m3/h per doublet, rounded up to 350 m3/h. Largest ESP (s = 1.8), HEX 1000 kW/K, official 2500 m reservoir.

**21. [validate] Rejected before simulation: n2_q350_s1.8_ua1000_z2500**
> 350.00 m3/h exceeds the 300 m3/h hard cap

**22. [revise] Revised to n2_q300_s1.8_ua1000_z2500**
> Clip to the nearest admissible value: flow_cap_m3h 350 -> 300 (350.00 m3/h exceeds the 300 m3/h hard cap). The proposal's intent (largest admissible flow) is kept; the shortfall is left to the heat pump / CHP and to more doublets if needed.

**23. [build_json] GEMINI JSON for n2_q300_s1.8_ua1000_z2500**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**24. [well_check] Well / ESP sanity check at 2500 m**
> No flags. Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 30.0 | 7.24 / 78.1 | 0.44 | 59.7 / 74.0 | 0.029 | 245.9 | 0.6 |
| 300 | 53.4 | 4.61 / 85.5 | 0.59 | 30.3 / 74.5 | 0.526 | 225.2 | 3.3 |

**25. [evaluate] Annual model + constraint check: n2_q300_s1.8_ua1000_z2500**
> FEASIBLE: external gas 0.002 GWh, emissions 8908 t, grid import 12.01 GWh, drilled 10000 m (0.9 s)

**26. [rank] Ranking after evaluation**
> Incumbent: n2_q300_s1.8_ua1000_z2500 (was n1_q300_s1.8_ua1000_z2500)

| Candidate | Rank | Verdict | Reason |
|---|---|---|---|
| n2_q300_s1.8_ua1000_z2500 | 1 | ACCEPTED | selected: feasible; external gas 0.0020 GWh, emissions 8908 t, grid import 12.01 GWh, 2 doublets, 10000 m drilled |
| n1_q300_s1.8_ua1000_z2500 | 2 | REJECTED | superseded by n2_q300_s1.8_ua1000_z2500: ranks better than n1_q300_s1.8_ua1000_z2500 (decided by external_gas_fuel_GWh: 0.001987 vs 28.6, beyond its tie tolerance); extra doublet: external gas +100.0%, emissions +31.3% (needs >= 5% on either, beyond the tie tolerance) |

**27. [propose] Proposal n2_q300_s1.8_ua500_z2500**
> Variant of incumbent n2_q300_s1.8_ua1000_z2500: Smaller HEX (500 kW/K, lower cost): check whether the heat pump can absorb the lost HEX duty without external gas.

**28. [build_json] GEMINI JSON for n2_q300_s1.8_ua500_z2500**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**29. [well_check] Well / ESP sanity check at 2500 m**
> No flags. Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 30.0 | 7.24 / 78.1 | 0.44 | 59.7 / 74.0 | 0.029 | 245.9 | 0.6 |
| 300 | 53.4 | 4.61 / 85.5 | 0.59 | 30.3 / 74.5 | 0.526 | 225.2 | 3.3 |

**30. [evaluate] Annual model + constraint check: n2_q300_s1.8_ua500_z2500**
> FEASIBLE: external gas 0.008 GWh, emissions 9036 t, grid import 12.50 GWh, drilled 10000 m (0.8 s)

**31. [rank] Ranking after evaluation**
> Incumbent: n2_q300_s1.8_ua1000_z2500

| Candidate | Rank | Verdict | Reason |
|---|---|---|---|
| n2_q300_s1.8_ua1000_z2500 | 1 | ACCEPTED | selected: feasible; external gas 0.0020 GWh, emissions 8908 t, grid import 12.01 GWh, 2 doublets, 10000 m drilled |
| n2_q300_s1.8_ua500_z2500 | 2 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on emissions_t (tied within tolerance on external_gas_fuel_GWh): external gas 0.0079 vs 0.0020 GWh, emissions 9036 vs 8908 t, grid import 12.50 vs 12.01 GWh, drilled 10000 vs 10000 m |
| n1_q300_s1.8_ua1000_z2500 | 3 | REJECTED | superseded by n2_q300_s1.8_ua1000_z2500: ranks better than n1_q300_s1.8_ua1000_z2500 (decided by external_gas_fuel_GWh: 0.001987 vs 28.6, beyond its tie tolerance); extra doublet: external gas +100.0%, emissions +31.3% (needs >= 5% on either, beyond the tie tolerance) |

**32. [propose] Proposal n2_q300_s1.0_ua1000_z2500**
> Previous candidate n2_q300_s1.8_ua500_z2500 was ranked out (same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on emissions_t (tied within tolerance on external_gas_fuel_GWh): external gas 0.0079 vs 0.0020 GWh, emissions 9036 vs 8908 t, grid import 12.50 vs 12.01 GWh, drilled 10000 vs 10000 m); keep incumbent n2_q300_s1.8_ua1000_z2500. Variant of incumbent n2_q300_s1.8_ua1000_z2500: Smaller ESP (s = 1.0, the GEMINI example pump): cheaper, but capped at ~176 m3/h; check the effect on external gas.

**33. [build_json] GEMINI JSON for n2_q300_s1.0_ua1000_z2500**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**34. [well_check] Well / ESP sanity check at 2500 m**
> Flags: 195 m3/h: ESP at 69.7 Hz, within 2 Hz of the drive limit; ESP reaches only 195 of the 300 m3/h cap at this depth. Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 39.5 | 3.00 / 78.1 | 0.44 | 46.5 / 56.6 | 0.020 | 245.9 | 0.6 |
| 195 | 69.7 | 3.34 / 84.7 | 0.57 | 30.7 / 58.0 | 0.211 | 233.9 | 2.2 |

**35. [evaluate] Annual model + constraint check: n2_q300_s1.0_ua1000_z2500**
> FEASIBLE: external gas 8.090 GWh, emissions 9429 t, grid import 11.49 GWh, drilled 10000 m (0.8 s)

**36. [rank] Ranking after evaluation**
> Incumbent: n2_q300_s1.8_ua1000_z2500

| Candidate | Rank | Verdict | Reason |
|---|---|---|---|
| n2_q300_s1.8_ua1000_z2500 | 1 | ACCEPTED | selected: feasible; external gas 0.0020 GWh, emissions 8908 t, grid import 12.01 GWh, 2 doublets, 10000 m drilled |
| n2_q300_s1.8_ua500_z2500 | 2 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on emissions_t (tied within tolerance on external_gas_fuel_GWh): external gas 0.0079 vs 0.0020 GWh, emissions 9036 vs 8908 t, grid import 12.50 vs 12.01 GWh, drilled 10000 vs 10000 m |
| n2_q300_s1.0_ua1000_z2500 | 3 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on external_gas_fuel_GWh: external gas 8.0904 vs 0.0020 GWh, emissions 9429 vs 8908 t, grid import 11.49 vs 12.01 GWh, drilled 10000 vs 10000 m |
| n1_q300_s1.8_ua1000_z2500 | 4 | REJECTED | superseded by n2_q300_s1.8_ua1000_z2500: ranks better than n1_q300_s1.8_ua1000_z2500 (decided by external_gas_fuel_GWh: 0.001987 vs 28.6, beyond its tie tolerance); extra doublet: external gas +100.0%, emissions +31.3% (needs >= 5% on either, beyond the tie tolerance) |

**37. [propose] Proposal n2_q300_s1.8_ua1000_z2750**
> Previous candidate n2_q300_s1.0_ua1000_z2500 was ranked out (same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on external_gas_fuel_GWh: external gas 8.0904 vs 0.0020 GWh, emissions 9429 vs 8908 t, grid import 11.49 vs 12.01 GWh, drilled 10000 vs 10000 m); keep incumbent n2_q300_s1.8_ua1000_z2500. Depth ladder from incumbent n2_q300_s1.8_ua1000_z2500: 2500 -> 2750 m (reservoir 94.5 C) to cut the heat-pump lift; accepted only if emissions improve >= 5% vs the 2500 m design.

**38. [build_json] GEMINI JSON for n2_q300_s1.8_ua1000_z2750**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**39. [well_check] Well / ESP sanity check at 2750 m**
> No flags. Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 30.0 | 7.20 / 83.7 | 0.55 | 60.6 / 75.0 | 0.029 | 271.1 | 0.6 |
| 300 | 54.1 | 4.61 / 92.7 | 0.78 | 30.1 / 75.6 | 0.541 | 250.5 | 3.3 |

**40. [evaluate] Annual model + constraint check: n2_q300_s1.8_ua1000_z2750**
> FEASIBLE: external gas 0.006 GWh, emissions 7267 t, grid import 7.83 GWh, drilled 11000 m (0.9 s)

**41. [rank] Ranking after evaluation**
> Incumbent: n2_q300_s1.8_ua1000_z2750 (was n2_q300_s1.8_ua1000_z2500)

| Candidate | Rank | Verdict | Reason |
|---|---|---|---|
| n2_q300_s1.8_ua1000_z2750 | 1 | ACCEPTED | selected: feasible; external gas 0.0061 GWh, emissions 7267 t, grid import 7.83 GWh, 2 doublets, 11000 m drilled |
| n2_q300_s1.8_ua1000_z2500 | 2 | REJECTED | superseded by n2_q300_s1.8_ua1000_z2750: ranks better than n2_q300_s1.8_ua1000_z2500 (decided by emissions_t: 7267 vs 8908); deeper 2500 -> 2750 m: emissions +18.422% (needs >= 5% beyond the tie tolerance), marginal abatement 1.641 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua500_z2500 | 3 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on emissions_t (tied within tolerance on external_gas_fuel_GWh): external gas 0.0079 vs 0.0020 GWh, emissions 9036 vs 8908 t, grid import 12.50 vs 12.01 GWh, drilled 10000 vs 10000 m |
| n2_q300_s1.0_ua1000_z2500 | 4 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on external_gas_fuel_GWh: external gas 8.0904 vs 0.0020 GWh, emissions 9429 vs 8908 t, grid import 11.49 vs 12.01 GWh, drilled 10000 vs 10000 m |
| n1_q300_s1.8_ua1000_z2500 | 5 | REJECTED | superseded by n2_q300_s1.8_ua1000_z2500: ranks better than n1_q300_s1.8_ua1000_z2500 (decided by external_gas_fuel_GWh: 0.001987 vs 28.6, beyond its tie tolerance); extra doublet: external gas +100.0%, emissions +31.3% (needs >= 5% on either, beyond the tie tolerance) |

**42. [depth_step] Depth step 2500 -> 2750 m**
> Emissions 8908 -> 7267 t (-18.4%) for +1000 m drilled: 1.641 t CO2/yr per extra metre. ACCEPTED (>= 5% beyond the tie tolerance).

**43. [propose] Proposal n2_q300_s1.8_ua1000_z3000**
>  Depth ladder from incumbent n2_q300_s1.8_ua1000_z2750: 2750 -> 3000 m (reservoir 102.0 C) to cut the heat-pump lift; accepted only if emissions improve >= 5% vs the 2750 m design.

**44. [build_json] GEMINI JSON for n2_q300_s1.8_ua1000_z3000**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**45. [well_check] Well / ESP sanity check at 3000 m**
> No flags. Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 30.0 | 7.17 / 89.1 | 0.68 | 62.6 / 77.0 | 0.029 | 296.4 | 0.6 |
| 300 | 54.8 | 4.61 / 99.9 | 1.01 | 31.0 / 77.7 | 0.555 | 275.7 | 3.3 |

**46. [evaluate] Annual model + constraint check: n2_q300_s1.8_ua1000_z3000**
> FEASIBLE: external gas 0.004 GWh, emissions 6038 t, grid import 4.66 GWh, drilled 12000 m (0.9 s)

**47. [rank] Ranking after evaluation**
> Incumbent: n2_q300_s1.8_ua1000_z3000 (was n2_q300_s1.8_ua1000_z2750)

| Candidate | Rank | Verdict | Reason |
|---|---|---|---|
| n2_q300_s1.8_ua1000_z3000 | 1 | ACCEPTED | selected: feasible; external gas 0.0044 GWh, emissions 6038 t, grid import 4.66 GWh, 2 doublets, 12000 m drilled |
| n2_q300_s1.8_ua1000_z2750 | 2 | REJECTED | superseded by n2_q300_s1.8_ua1000_z3000: ranks better than n2_q300_s1.8_ua1000_z2750 (decided by emissions_t: 6038 vs 7267); deeper 2750 -> 3000 m: emissions +16.910% (needs >= 5% beyond the tie tolerance), marginal abatement 1.229 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua1000_z2500 | 3 | REJECTED | superseded by n2_q300_s1.8_ua1000_z2750: ranks better than n2_q300_s1.8_ua1000_z2500 (decided by emissions_t: 7267 vs 8908); deeper 2500 -> 2750 m: emissions +18.422% (needs >= 5% beyond the tie tolerance), marginal abatement 1.641 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua500_z2500 | 4 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on emissions_t (tied within tolerance on external_gas_fuel_GWh): external gas 0.0079 vs 0.0020 GWh, emissions 9036 vs 8908 t, grid import 12.50 vs 12.01 GWh, drilled 10000 vs 10000 m |
| n2_q300_s1.0_ua1000_z2500 | 5 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on external_gas_fuel_GWh: external gas 8.0904 vs 0.0020 GWh, emissions 9429 vs 8908 t, grid import 11.49 vs 12.01 GWh, drilled 10000 vs 10000 m |
| n1_q300_s1.8_ua1000_z2500 | 6 | REJECTED | superseded by n2_q300_s1.8_ua1000_z2500: ranks better than n1_q300_s1.8_ua1000_z2500 (decided by external_gas_fuel_GWh: 0.001987 vs 28.6, beyond its tie tolerance); extra doublet: external gas +100.0%, emissions +31.3% (needs >= 5% on either, beyond the tie tolerance) |

**48. [depth_step] Depth step 2750 -> 3000 m**
> Emissions 7267 -> 6038 t (-16.9%) for +1000 m drilled: 1.229 t CO2/yr per extra metre. ACCEPTED (>= 5% beyond the tie tolerance).

**49. [propose] Proposal n2_q300_s1.8_ua1000_z3250**
>  Depth ladder from incumbent n2_q300_s1.8_ua1000_z3000: 3000 -> 3250 m (reservoir 109.5 C) to cut the heat-pump lift; accepted only if emissions improve >= 5% vs the 3000 m design.

**50. [build_json] GEMINI JSON for n2_q300_s1.8_ua1000_z3250**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**51. [well_check] Well / ESP sanity check at 3250 m**
> Flags: 300 m3/h: wellhead 107.0 C exceeds PVTConstantSTP temperature_max (100 C) - constant brine properties extrapolated. Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 30.0 | 7.13 / 94.4 | 0.83 | 63.6 / 78.0 | 0.029 | 321.7 | 0.6 |
| 300 | 55.5 | 4.61 / 107.0 | 1.30 | 30.9 / 78.8 | 0.570 | 301.0 | 3.3 |

**52. [evaluate] Annual model + constraint check: n2_q300_s1.8_ua1000_z3250**
> FEASIBLE: external gas 0.004 GWh, emissions 5148 t, grid import 1.84 GWh, drilled 13000 m (1.5 s)

**53. [rank] Ranking after evaluation**
> Incumbent: n2_q300_s1.8_ua1000_z3250 (was n2_q300_s1.8_ua1000_z3000)

| Candidate | Rank | Verdict | Reason |
|---|---|---|---|
| n2_q300_s1.8_ua1000_z3250 | 1 | ACCEPTED | selected: feasible; external gas 0.0038 GWh, emissions 5148 t, grid import 1.84 GWh, 2 doublets, 13000 m drilled |
| n2_q300_s1.8_ua1000_z3000 | 2 | REJECTED | superseded by n2_q300_s1.8_ua1000_z3250: ranks better than n2_q300_s1.8_ua1000_z3000 (decided by emissions_t: 5148 vs 6038); deeper 3000 -> 3250 m: emissions +14.744% (needs >= 5% beyond the tie tolerance), marginal abatement 0.890 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua1000_z2750 | 3 | REJECTED | superseded by n2_q300_s1.8_ua1000_z3000: ranks better than n2_q300_s1.8_ua1000_z2750 (decided by emissions_t: 6038 vs 7267); deeper 2750 -> 3000 m: emissions +16.910% (needs >= 5% beyond the tie tolerance), marginal abatement 1.229 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua1000_z2500 | 4 | REJECTED | superseded by n2_q300_s1.8_ua1000_z2750: ranks better than n2_q300_s1.8_ua1000_z2500 (decided by emissions_t: 7267 vs 8908); deeper 2500 -> 2750 m: emissions +18.422% (needs >= 5% beyond the tie tolerance), marginal abatement 1.641 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua500_z2500 | 5 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on emissions_t (tied within tolerance on external_gas_fuel_GWh): external gas 0.0079 vs 0.0020 GWh, emissions 9036 vs 8908 t, grid import 12.50 vs 12.01 GWh, drilled 10000 vs 10000 m |
| n2_q300_s1.0_ua1000_z2500 | 6 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on external_gas_fuel_GWh: external gas 8.0904 vs 0.0020 GWh, emissions 9429 vs 8908 t, grid import 11.49 vs 12.01 GWh, drilled 10000 vs 10000 m |
| n1_q300_s1.8_ua1000_z2500 | 7 | REJECTED | superseded by n2_q300_s1.8_ua1000_z2500: ranks better than n1_q300_s1.8_ua1000_z2500 (decided by external_gas_fuel_GWh: 0.001987 vs 28.6, beyond its tie tolerance); extra doublet: external gas +100.0%, emissions +31.3% (needs >= 5% on either, beyond the tie tolerance) |

**54. [depth_step] Depth step 3000 -> 3250 m**
> Emissions 6038 -> 5148 t (-14.7%) for +1000 m drilled: 0.890 t CO2/yr per extra metre. ACCEPTED (>= 5% beyond the tie tolerance).

**55. [propose] Proposal n2_q300_s1.8_ua1000_z3500**
>  Depth ladder from incumbent n2_q300_s1.8_ua1000_z3250: 3250 -> 3500 m (reservoir 117.0 C) to cut the heat-pump lift; accepted only if emissions improve >= 5% vs the 3250 m design.

**56. [build_json] GEMINI JSON for n2_q300_s1.8_ua1000_z3500**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**57. [well_check] Well / ESP sanity check at 3500 m**
> Flags: 300 m3/h: wellhead 114.1 C exceeds PVTConstantSTP temperature_max (100 C) - constant brine properties extrapolated. Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 30.0 | 7.09 / 99.5 | 1.00 | 64.6 / 78.9 | 0.029 | 346.9 | 0.6 |
| 300 | 56.2 | 4.61 / 114.1 | 1.64 | 30.7 / 79.8 | 0.584 | 326.2 | 3.3 |

**58. [evaluate] Annual model + constraint check: n2_q300_s1.8_ua1000_z3500**
> FEASIBLE: external gas 0.016 GWh, emissions 4891 t, grid import 0.80 GWh, drilled 14000 m (0.6 s)

**59. [rank] Ranking after evaluation**
> Incumbent: n2_q300_s1.8_ua1000_z3250

| Candidate | Rank | Verdict | Reason |
|---|---|---|---|
| n2_q300_s1.8_ua1000_z3250 | 1 | ACCEPTED | selected: feasible; external gas 0.0038 GWh, emissions 5148 t, grid import 1.84 GWh, 2 doublets, 13000 m drilled |
| n2_q300_s1.8_ua1000_z3500 | 2 | REJECTED | parsimony rule not met: ranks better than n2_q300_s1.8_ua1000_z3250 (decided by emissions_t: 4891 vs 5148); deeper 3250 -> 3500 m: emissions +4.994% (needs >= 5% beyond the tie tolerance), marginal abatement 0.257 t CO2/yr per extra metre drilled - within the tie tolerance of the threshold, counts as NOT met (marginal sensitivity case) |
| n2_q300_s1.8_ua1000_z3000 | 3 | REJECTED | superseded by n2_q300_s1.8_ua1000_z3250: ranks better than n2_q300_s1.8_ua1000_z3000 (decided by emissions_t: 5148 vs 6038); deeper 3000 -> 3250 m: emissions +14.744% (needs >= 5% beyond the tie tolerance), marginal abatement 0.890 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua1000_z2750 | 4 | REJECTED | superseded by n2_q300_s1.8_ua1000_z3000: ranks better than n2_q300_s1.8_ua1000_z2750 (decided by emissions_t: 6038 vs 7267); deeper 2750 -> 3000 m: emissions +16.910% (needs >= 5% beyond the tie tolerance), marginal abatement 1.229 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua1000_z2500 | 5 | REJECTED | superseded by n2_q300_s1.8_ua1000_z2750: ranks better than n2_q300_s1.8_ua1000_z2500 (decided by emissions_t: 7267 vs 8908); deeper 2500 -> 2750 m: emissions +18.422% (needs >= 5% beyond the tie tolerance), marginal abatement 1.641 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua500_z2500 | 6 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on emissions_t (tied within tolerance on external_gas_fuel_GWh): external gas 0.0079 vs 0.0020 GWh, emissions 9036 vs 8908 t, grid import 12.50 vs 12.01 GWh, drilled 10000 vs 10000 m |
| n2_q300_s1.0_ua1000_z2500 | 7 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on external_gas_fuel_GWh: external gas 8.0904 vs 0.0020 GWh, emissions 9429 vs 8908 t, grid import 11.49 vs 12.01 GWh, drilled 10000 vs 10000 m |
| n1_q300_s1.8_ua1000_z2500 | 8 | REJECTED | superseded by n2_q300_s1.8_ua1000_z2500: ranks better than n1_q300_s1.8_ua1000_z2500 (decided by external_gas_fuel_GWh: 0.001987 vs 28.6, beyond its tie tolerance); extra doublet: external gas +100.0%, emissions +31.3% (needs >= 5% on either, beyond the tie tolerance) |

**60. [depth_step] Depth step 3250 -> 3500 m**
> Emissions 5148 -> 4891 t (-5.0%) for +1000 m drilled: 0.257 t CO2/yr per extra metre. REJECTED: within the tie tolerance of the 5% threshold, which counts as not met (conservative: drilling cost and risk are not modelled); recorded as a marginal sensitivity case.

**61. [propose] Proposal n2_q300_s1.8_ua1000_z3250_co2ri**
> Previous candidate n2_q300_s1.8_ua1000_z3500 was ranked out (parsimony rule not met: ranks better than n2_q300_s1.8_ua1000_z3250 (decided by emissions_t: 4891 vs 5148); deeper 3250 -> 3500 m: emissions +4.994% (needs >= 5% beyond the tie tolerance), marginal abatement 0.257 t CO2/yr per extra metre drilled - within the tie tolerance of the threshold, counts as NOT met (marginal sensitivity case)); keep incumbent n2_q300_s1.8_ua1000_z3250. Depth step to 3500 m failed the parsimony rule; stop exploring deeper (accepted depth stays 3250 m). Variant of incumbent n2_q300_s1.8_ua1000_z3250: Gas handling (b): separate the 20 mol% CO2 and reinject it with the brine, CH4 to CHP. Only CH4 combustion CO2 counts (54.9 vs 68.6 kg/GJ, DERIVED); costs ~0.1 kWh/kg CO2 separation + compression (ASSUMED). If accepted, the depth ladder re-opens: the lower emissions baseline changes the 5% depth rule.

**62. [build_json] GEMINI JSON for n2_q300_s1.8_ua1000_z3250_co2ri**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**63. [well_check] Well / ESP sanity check at 3250 m**
> Flags: 300 m3/h: wellhead 107.0 C exceeds PVTConstantSTP temperature_max (100 C) - constant brine properties extrapolated. Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 30.0 | 7.13 / 94.4 | 0.83 | 63.6 / 78.0 | 0.029 | 321.7 | 0.6 |
| 300 | 55.5 | 4.61 / 107.0 | 1.30 | 30.9 / 78.8 | 0.570 | 301.0 | 3.3 |

**64. [evaluate] Annual model + constraint check: n2_q300_s1.8_ua1000_z3250_co2ri**
> FEASIBLE: external gas 0.004 GWh, emissions 4252 t, grid import 1.91 GWh, drilled 13000 m (1.5 s)

**65. [rank] Ranking after evaluation**
> Incumbent: n2_q300_s1.8_ua1000_z3250_co2ri (was n2_q300_s1.8_ua1000_z3250)

| Candidate | Rank | Verdict | Reason |
|---|---|---|---|
| n2_q300_s1.8_ua1000_z3250_co2ri | 1 | ACCEPTED | selected: feasible; external gas 0.0038 GWh, emissions 4252 t, grid import 1.91 GWh, 2 doublets, 13000 m drilled |
| n2_q300_s1.8_ua1000_z3500 | 2 | REJECTED | parsimony rule not met: ranks not better than n2_q300_s1.8_ua1000_z3250_co2ri (decided by emissions_t: 4891 vs 4252); deeper 3250 -> 3500 m: emissions -15.033% (needs >= 5% beyond the tie tolerance), marginal abatement -0.639 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua1000_z3250 | 3 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z3250_co2ri but ranks lower on emissions_t (tied within tolerance on external_gas_fuel_GWh): external gas 0.0038 vs 0.0038 GWh, emissions 5148 vs 4252 t, grid import 1.84 vs 1.91 GWh, drilled 13000 vs 13000 m |
| n2_q300_s1.8_ua1000_z3000 | 4 | REJECTED | superseded by n2_q300_s1.8_ua1000_z3250_co2ri: ranks better than n2_q300_s1.8_ua1000_z3000 (decided by emissions_t: 4252 vs 6038); deeper 3000 -> 3250 m: emissions +29.587% (needs >= 5% beyond the tie tolerance), marginal abatement 1.787 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua1000_z2750 | 5 | REJECTED | superseded by n2_q300_s1.8_ua1000_z3000: ranks better than n2_q300_s1.8_ua1000_z2750 (decided by emissions_t: 6038 vs 7267); deeper 2750 -> 3000 m: emissions +16.910% (needs >= 5% beyond the tie tolerance), marginal abatement 1.229 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua1000_z2500 | 6 | REJECTED | superseded by n2_q300_s1.8_ua1000_z2750: ranks better than n2_q300_s1.8_ua1000_z2500 (decided by emissions_t: 7267 vs 8908); deeper 2500 -> 2750 m: emissions +18.422% (needs >= 5% beyond the tie tolerance), marginal abatement 1.641 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua500_z2500 | 7 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on emissions_t (tied within tolerance on external_gas_fuel_GWh): external gas 0.0079 vs 0.0020 GWh, emissions 9036 vs 8908 t, grid import 12.50 vs 12.01 GWh, drilled 10000 vs 10000 m |
| n2_q300_s1.0_ua1000_z2500 | 8 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on external_gas_fuel_GWh: external gas 8.0904 vs 0.0020 GWh, emissions 9429 vs 8908 t, grid import 11.49 vs 12.01 GWh, drilled 10000 vs 10000 m |
| n1_q300_s1.8_ua1000_z2500 | 9 | REJECTED | superseded by n2_q300_s1.8_ua1000_z2500: ranks better than n1_q300_s1.8_ua1000_z2500 (decided by external_gas_fuel_GWh: 0.001987 vs 28.6, beyond its tie tolerance); extra doublet: external gas +100.0%, emissions +31.3% (needs >= 5% on either, beyond the tie tolerance) |

**66. [propose] Proposal n2_q300_s1.8_ua1000_z3500_co2ri**
>  Depth ladder from incumbent n2_q300_s1.8_ua1000_z3250_co2ri: 3250 -> 3500 m (reservoir 117.0 C) to cut the heat-pump lift; accepted only if emissions improve >= 5% vs the 3250 m design.

**67. [build_json] GEMINI JSON for n2_q300_s1.8_ua1000_z3500_co2ri**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**68. [well_check] Well / ESP sanity check at 3500 m**
> Flags: 300 m3/h: wellhead 114.1 C exceeds PVTConstantSTP temperature_max (100 C) - constant brine properties extrapolated. Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 30.0 | 7.09 / 99.5 | 1.00 | 64.6 / 78.9 | 0.029 | 346.9 | 0.6 |
| 300 | 56.2 | 4.61 / 114.1 | 1.64 | 30.7 / 79.8 | 0.584 | 326.2 | 3.3 |

**69. [evaluate] Annual model + constraint check: n2_q300_s1.8_ua1000_z3500_co2ri**
> FEASIBLE: external gas 0.016 GWh, emissions 3983 t, grid import 0.87 GWh, drilled 14000 m (0.6 s)

**70. [rank] Ranking after evaluation**
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
| n2_q300_s1.8_ua500_z2500 | 8 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on emissions_t (tied within tolerance on external_gas_fuel_GWh): external gas 0.0079 vs 0.0020 GWh, emissions 9036 vs 8908 t, grid import 12.50 vs 12.01 GWh, drilled 10000 vs 10000 m |
| n2_q300_s1.0_ua1000_z2500 | 9 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on external_gas_fuel_GWh: external gas 8.0904 vs 0.0020 GWh, emissions 9429 vs 8908 t, grid import 11.49 vs 12.01 GWh, drilled 10000 vs 10000 m |
| n1_q300_s1.8_ua1000_z2500 | 10 | REJECTED | superseded by n2_q300_s1.8_ua1000_z2500: ranks better than n1_q300_s1.8_ua1000_z2500 (decided by external_gas_fuel_GWh: 0.001987 vs 28.6, beyond its tie tolerance); extra doublet: external gas +100.0%, emissions +31.3% (needs >= 5% on either, beyond the tie tolerance) |

**71. [depth_step] Depth step 3250 -> 3500 m**
> Emissions 4252 -> 3983 t (-6.3%) for +1000 m drilled: 0.268 t CO2/yr per extra metre. ACCEPTED (>= 5% beyond the tie tolerance).

**72. [propose] Proposal n2_q300_s1.8_ua1000_z3750_co2ri**
>  Depth ladder from incumbent n2_q300_s1.8_ua1000_z3500_co2ri: 3500 -> 3750 m (reservoir 124.5 C) to cut the heat-pump lift; accepted only if emissions improve >= 5% vs the 3500 m design.

**73. [build_json] GEMINI JSON for n2_q300_s1.8_ua1000_z3750_co2ri**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**74. [well_check] Well / ESP sanity check at 3750 m**
> Flags: 50 m3/h: wellhead 104.4 C exceeds PVTConstantSTP temperature_max (100 C) - constant brine properties extrapolated; 300 m3/h: wellhead 121.1 C exceeds PVTConstantSTP temperature_max (100 C) - constant brine properties extrapolated. Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 30.0 | 7.05 / 104.4 | 1.19 | 65.5 / 79.9 | 0.029 | 372.2 | 0.6 |
| 300 | 56.9 | 4.61 / 121.1 | 2.05 | 30.6 / 80.9 | 0.599 | 351.5 | 3.3 |

**75. [evaluate] Annual model + constraint check: n2_q300_s1.8_ua1000_z3750_co2ri**
> FEASIBLE: external gas 0.020 GWh, emissions 3950 t, grid import 0.73 GWh, drilled 15000 m (0.6 s)

**76. [rank] Ranking after evaluation**
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
| n2_q300_s1.8_ua500_z2500 | 9 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on emissions_t (tied within tolerance on external_gas_fuel_GWh): external gas 0.0079 vs 0.0020 GWh, emissions 9036 vs 8908 t, grid import 12.50 vs 12.01 GWh, drilled 10000 vs 10000 m |
| n2_q300_s1.0_ua1000_z2500 | 10 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on external_gas_fuel_GWh: external gas 8.0904 vs 0.0020 GWh, emissions 9429 vs 8908 t, grid import 11.49 vs 12.01 GWh, drilled 10000 vs 10000 m |
| n1_q300_s1.8_ua1000_z2500 | 11 | REJECTED | superseded by n2_q300_s1.8_ua1000_z2500: ranks better than n1_q300_s1.8_ua1000_z2500 (decided by external_gas_fuel_GWh: 0.001987 vs 28.6, beyond its tie tolerance); extra doublet: external gas +100.0%, emissions +31.3% (needs >= 5% on either, beyond the tie tolerance) |

**77. [depth_step] Depth step 3500 -> 3750 m**
> Emissions 3983 -> 3950 t (-0.8%) for +1000 m drilled: 0.033 t CO2/yr per extra metre. REJECTED by the depth parsimony rule (< 5%).

**78. [propose] Proposal n2_q300_s1.8_ua1000_z3500_allri**
> Previous candidate n2_q300_s1.8_ua1000_z3750_co2ri was ranked out (parsimony rule not met: ranks better than n2_q300_s1.8_ua1000_z3500_co2ri (decided by grid_import_GWh: 0.7317 vs 0.8744); deeper 3500 -> 3750 m: emissions +0.829% (needs >= 5% beyond the tie tolerance), marginal abatement 0.033 t CO2/yr per extra metre drilled); keep incumbent n2_q300_s1.8_ua1000_z3500_co2ri. Depth step to 3750 m failed the parsimony rule; stop exploring deeper (accepted depth stays 3500 m). Variant of incumbent n2_q300_s1.8_ua1000_z3500_co2ri: Gas handling (c): reinject all produced gas, no combustion: no produced-gas CO2, but no CHP heat or electricity, so the heat pump must cover the whole lift (external gas if it cannot).

**79. [build_json] GEMINI JSON for n2_q300_s1.8_ua1000_z3500_allri**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**80. [well_check] Well / ESP sanity check at 3500 m**
> Flags: 300 m3/h: wellhead 114.1 C exceeds PVTConstantSTP temperature_max (100 C) - constant brine properties extrapolated. Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 30.0 | 7.09 / 99.5 | 1.00 | 64.6 / 78.9 | 0.029 | 346.9 | 0.6 |
| 300 | 56.2 | 4.61 / 114.1 | 1.64 | 30.7 / 79.8 | 0.584 | 326.2 | 3.3 |

**81. [evaluate] Annual model + constraint check: n2_q300_s1.8_ua1000_z3500_allri**
> FEASIBLE: external gas 0.271 GWh, emissions 2023 t, grid import 6.56 GWh, drilled 14000 m (0.6 s)

**82. [rank] Ranking after evaluation**
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
| n2_q300_s1.8_ua500_z2500 | 9 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on emissions_t (tied within tolerance on external_gas_fuel_GWh): external gas 0.0079 vs 0.0020 GWh, emissions 9036 vs 8908 t, grid import 12.50 vs 12.01 GWh, drilled 10000 vs 10000 m |
| n2_q300_s1.8_ua1000_z3500_allri | 10 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z3500_co2ri but ranks lower on external_gas_fuel_GWh: external gas 0.2710 vs 0.0157 GWh, emissions 2023 vs 3983 t, grid import 6.56 vs 0.87 GWh, drilled 14000 vs 14000 m |
| n2_q300_s1.0_ua1000_z2500 | 11 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on external_gas_fuel_GWh: external gas 8.0904 vs 0.0020 GWh, emissions 9429 vs 8908 t, grid import 11.49 vs 12.01 GWh, drilled 10000 vs 10000 m |
| n1_q300_s1.8_ua1000_z2500 | 12 | REJECTED | superseded by n2_q300_s1.8_ua1000_z2500: ranks better than n1_q300_s1.8_ua1000_z2500 (decided by external_gas_fuel_GWh: 0.001987 vs 28.6, beyond its tie tolerance); extra doublet: external gas +100.0%, emissions +31.3% (needs >= 5% on either, beyond the tie tolerance) |

**83. [propose] Proposal n3_q300_s1.8_ua1000_z3500_co2ri**
> Previous candidate n2_q300_s1.8_ua1000_z3500_allri was ranked out (same doublet count and depth as n2_q300_s1.8_ua1000_z3500_co2ri but ranks lower on external_gas_fuel_GWh: external gas 0.2710 vs 0.0157 GWh, emissions 2023 vs 3983 t, grid import 6.56 vs 0.87 GWh, drilled 14000 vs 14000 m); keep incumbent n2_q300_s1.8_ua1000_z3500_co2ri. Variant of incumbent n2_q300_s1.8_ua1000_z3500_co2ri: More doublets: accepted only if external gas or emissions improve by >= 5%.

**84. [build_json] GEMINI JSON for n3_q300_s1.8_ua1000_z3500_co2ri**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**85. [well_check] Well / ESP sanity check at 3500 m**
> Flags: 300 m3/h: wellhead 114.1 C exceeds PVTConstantSTP temperature_max (100 C) - constant brine properties extrapolated. Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 30.0 | 7.09 / 99.5 | 1.00 | 64.6 / 78.9 | 0.029 | 346.9 | 0.6 |
| 300 | 56.2 | 4.61 / 114.1 | 1.64 | 30.7 / 79.8 | 0.584 | 326.2 | 3.3 |

**86. [evaluate] Annual model + constraint check: n3_q300_s1.8_ua1000_z3500_co2ri**
> FEASIBLE: external gas 0.004 GWh, emissions 3979 t, grid import 0.87 GWh, drilled 21000 m (0.6 s)

**87. [rank] Ranking after evaluation**
> Incumbent: n2_q300_s1.8_ua1000_z3500_co2ri

| Candidate | Rank | Verdict | Reason |
|---|---|---|---|
| n2_q300_s1.8_ua1000_z3500_co2ri | 1 | ACCEPTED | selected: feasible; external gas 0.0157 GWh, emissions 3983 t, grid import 0.87 GWh, 2 doublets, 14000 m drilled |
| n2_q300_s1.8_ua1000_z3750_co2ri | 2 | REJECTED | parsimony rule not met: ranks better than n2_q300_s1.8_ua1000_z3500_co2ri (decided by grid_import_GWh: 0.7317 vs 0.8744); deeper 3500 -> 3750 m: emissions +0.829% (needs >= 5% beyond the tie tolerance), marginal abatement 0.033 t CO2/yr per extra metre drilled |
| n3_q300_s1.8_ua1000_z3500_co2ri | 3 | REJECTED | parsimony rule not met: ranks not better than n2_q300_s1.8_ua1000_z3500_co2ri (decided by n_doublets: 3 vs 2); extra doublet: external gas +73.8%, emissions +0.1% (needs >= 5% on either, beyond the tie tolerance) |
| n2_q300_s1.8_ua1000_z3250_co2ri | 4 | REJECTED | superseded by n2_q300_s1.8_ua1000_z3500_co2ri: ranks better than n2_q300_s1.8_ua1000_z3250_co2ri (decided by emissions_t: 3983 vs 4252); deeper 3250 -> 3500 m: emissions +6.310% (needs >= 5% beyond the tie tolerance), marginal abatement 0.268 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua1000_z3500 | 5 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z3500_co2ri but ranks lower on emissions_t (tied within tolerance on external_gas_fuel_GWh): external gas 0.0157 vs 0.0157 GWh, emissions 4891 vs 3983 t, grid import 0.80 vs 0.87 GWh, drilled 14000 vs 14000 m |
| n2_q300_s1.8_ua1000_z3250 | 6 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z3250_co2ri but ranks lower on emissions_t (tied within tolerance on external_gas_fuel_GWh): external gas 0.0038 vs 0.0038 GWh, emissions 5148 vs 4252 t, grid import 1.84 vs 1.91 GWh, drilled 13000 vs 13000 m |
| n2_q300_s1.8_ua1000_z3000 | 7 | REJECTED | superseded by n2_q300_s1.8_ua1000_z3250_co2ri: ranks better than n2_q300_s1.8_ua1000_z3000 (decided by emissions_t: 4252 vs 6038); deeper 3000 -> 3250 m: emissions +29.587% (needs >= 5% beyond the tie tolerance), marginal abatement 1.787 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua1000_z2750 | 8 | REJECTED | superseded by n2_q300_s1.8_ua1000_z3000: ranks better than n2_q300_s1.8_ua1000_z2750 (decided by emissions_t: 6038 vs 7267); deeper 2750 -> 3000 m: emissions +16.910% (needs >= 5% beyond the tie tolerance), marginal abatement 1.229 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua1000_z2500 | 9 | REJECTED | superseded by n2_q300_s1.8_ua1000_z2750: ranks better than n2_q300_s1.8_ua1000_z2500 (decided by emissions_t: 7267 vs 8908); deeper 2500 -> 2750 m: emissions +18.422% (needs >= 5% beyond the tie tolerance), marginal abatement 1.641 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua500_z2500 | 10 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on emissions_t (tied within tolerance on external_gas_fuel_GWh): external gas 0.0079 vs 0.0020 GWh, emissions 9036 vs 8908 t, grid import 12.50 vs 12.01 GWh, drilled 10000 vs 10000 m |
| n2_q300_s1.8_ua1000_z3500_allri | 11 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z3500_co2ri but ranks lower on external_gas_fuel_GWh: external gas 0.2710 vs 0.0157 GWh, emissions 2023 vs 3983 t, grid import 6.56 vs 0.87 GWh, drilled 14000 vs 14000 m |
| n2_q300_s1.0_ua1000_z2500 | 12 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on external_gas_fuel_GWh: external gas 8.0904 vs 0.0020 GWh, emissions 9429 vs 8908 t, grid import 11.49 vs 12.01 GWh, drilled 10000 vs 10000 m |
| n1_q300_s1.8_ua1000_z2500 | 13 | REJECTED | superseded by n2_q300_s1.8_ua1000_z2500: ranks better than n1_q300_s1.8_ua1000_z2500 (decided by external_gas_fuel_GWh: 0.001987 vs 28.6, beyond its tie tolerance); extra doublet: external gas +100.0%, emissions +31.3% (needs >= 5% on either, beyond the tie tolerance) |

**88. [propose] Proposal n1_q300_s1.8_ua1000_z3500_co2ri**
> Previous candidate n3_q300_s1.8_ua1000_z3500_co2ri was ranked out (parsimony rule not met: ranks not better than n2_q300_s1.8_ua1000_z3500_co2ri (decided by n_doublets: 3 vs 2); extra doublet: external gas +73.8%, emissions +0.1% (needs >= 5% on either, beyond the tie tolerance)); keep incumbent n2_q300_s1.8_ua1000_z3500_co2ri. Variant of incumbent n2_q300_s1.8_ua1000_z3500_co2ri: Single doublet at the accepted depth and settings: check whether depth rescues one doublet; it still needs backup on its 35 maintenance days, so the ranking decides on external gas.

**89. [build_json] GEMINI JSON for n1_q300_s1.8_ua1000_z3500_co2ri**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**90. [well_check] Well / ESP sanity check at 3500 m**
> Flags: 300 m3/h: wellhead 114.1 C exceeds PVTConstantSTP temperature_max (100 C) - constant brine properties extrapolated. Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 30.0 | 7.09 / 99.5 | 1.00 | 64.6 / 78.9 | 0.029 | 346.9 | 0.6 |
| 300 | 56.2 | 4.61 / 114.1 | 1.64 | 30.7 / 79.8 | 0.584 | 326.2 | 3.3 |

**91. [evaluate] Annual model + constraint check: n1_q300_s1.8_ua1000_z3500_co2ri**
> FEASIBLE: external gas 36.457 GWh, emissions 10783 t, grid import 1.75 GWh, drilled 7000 m; 35 day(s) without geothermal supply, covered by backup (boiler 15.1 MWth, electric chiller 5.9 MWcool peak) (0.5 s)

**92. [rank] Ranking after evaluation**
> Incumbent: n2_q300_s1.8_ua1000_z3500_co2ri

| Candidate | Rank | Verdict | Reason |
|---|---|---|---|
| n2_q300_s1.8_ua1000_z3500_co2ri | 1 | ACCEPTED | selected: feasible; external gas 0.0157 GWh, emissions 3983 t, grid import 0.87 GWh, 2 doublets, 14000 m drilled |
| n2_q300_s1.8_ua1000_z3750_co2ri | 2 | REJECTED | parsimony rule not met: ranks better than n2_q300_s1.8_ua1000_z3500_co2ri (decided by grid_import_GWh: 0.7317 vs 0.8744); deeper 3500 -> 3750 m: emissions +0.829% (needs >= 5% beyond the tie tolerance), marginal abatement 0.033 t CO2/yr per extra metre drilled |
| n3_q300_s1.8_ua1000_z3500_co2ri | 3 | REJECTED | parsimony rule not met: ranks not better than n2_q300_s1.8_ua1000_z3500_co2ri (decided by n_doublets: 3 vs 2); extra doublet: external gas +73.8%, emissions +0.1% (needs >= 5% on either, beyond the tie tolerance) |
| n2_q300_s1.8_ua1000_z3250_co2ri | 4 | REJECTED | superseded by n2_q300_s1.8_ua1000_z3500_co2ri: ranks better than n2_q300_s1.8_ua1000_z3250_co2ri (decided by emissions_t: 3983 vs 4252); deeper 3250 -> 3500 m: emissions +6.310% (needs >= 5% beyond the tie tolerance), marginal abatement 0.268 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua1000_z3500 | 5 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z3500_co2ri but ranks lower on emissions_t (tied within tolerance on external_gas_fuel_GWh): external gas 0.0157 vs 0.0157 GWh, emissions 4891 vs 3983 t, grid import 0.80 vs 0.87 GWh, drilled 14000 vs 14000 m |
| n2_q300_s1.8_ua1000_z3250 | 6 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z3250_co2ri but ranks lower on emissions_t (tied within tolerance on external_gas_fuel_GWh): external gas 0.0038 vs 0.0038 GWh, emissions 5148 vs 4252 t, grid import 1.84 vs 1.91 GWh, drilled 13000 vs 13000 m |
| n2_q300_s1.8_ua1000_z3000 | 7 | REJECTED | superseded by n2_q300_s1.8_ua1000_z3250_co2ri: ranks better than n2_q300_s1.8_ua1000_z3000 (decided by emissions_t: 4252 vs 6038); deeper 3000 -> 3250 m: emissions +29.587% (needs >= 5% beyond the tie tolerance), marginal abatement 1.787 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua1000_z2750 | 8 | REJECTED | superseded by n2_q300_s1.8_ua1000_z3000: ranks better than n2_q300_s1.8_ua1000_z2750 (decided by emissions_t: 6038 vs 7267); deeper 2750 -> 3000 m: emissions +16.910% (needs >= 5% beyond the tie tolerance), marginal abatement 1.229 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua1000_z2500 | 9 | REJECTED | superseded by n2_q300_s1.8_ua1000_z2750: ranks better than n2_q300_s1.8_ua1000_z2500 (decided by emissions_t: 7267 vs 8908); deeper 2500 -> 2750 m: emissions +18.422% (needs >= 5% beyond the tie tolerance), marginal abatement 1.641 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua500_z2500 | 10 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on emissions_t (tied within tolerance on external_gas_fuel_GWh): external gas 0.0079 vs 0.0020 GWh, emissions 9036 vs 8908 t, grid import 12.50 vs 12.01 GWh, drilled 10000 vs 10000 m |
| n2_q300_s1.8_ua1000_z3500_allri | 11 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z3500_co2ri but ranks lower on external_gas_fuel_GWh: external gas 0.2710 vs 0.0157 GWh, emissions 2023 vs 3983 t, grid import 6.56 vs 0.87 GWh, drilled 14000 vs 14000 m |
| n2_q300_s1.0_ua1000_z2500 | 12 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on external_gas_fuel_GWh: external gas 8.0904 vs 0.0020 GWh, emissions 9429 vs 8908 t, grid import 11.49 vs 12.01 GWh, drilled 10000 vs 10000 m |
| n1_q300_s1.8_ua1000_z2500 | 13 | REJECTED | superseded by n2_q300_s1.8_ua1000_z2500: ranks better than n1_q300_s1.8_ua1000_z2500 (decided by external_gas_fuel_GWh: 0.001987 vs 28.6, beyond its tie tolerance); extra doublet: external gas +100.0%, emissions +31.3% (needs >= 5% on either, beyond the tie tolerance) |
| n1_q300_s1.8_ua1000_z3500_co2ri | 14 | REJECTED | parsimony rule not met: ranks not better than n1_q300_s1.8_ua1000_z2500 (decided by external_gas_fuel_GWh: 36.46 vs 28.6, beyond its tie tolerance); deeper 2500 -> 3500 m: emissions +16.853% (needs >= 5% beyond the tie tolerance), marginal abatement 1.093 t CO2/yr per extra metre drilled |

**93. [stop] Backend stops proposing**
> No untried variant can change the pick within the design space and the parsimony rules.

**94. [gas_decision] Gas handling: co2_reinject**
> options compared at n2_q300_s1.8_ua1000_z3500: chp external gas 0.016 GWh, 4891 t, grid 0.80 GWh; co2_reinject external gas 0.016 GWh, 3983 t, grid 0.87 GWh; reinject_all external gas 0.271 GWh, 2023 t, grid 6.56 GWh. The ranking keeps co2_reinject at that design (external gas first, then emissions); reinject_all has the lowest emissions but needs more external gas (0.271 vs 0.016 GWh (without CHP heat the heat pump cannot cover the whole lift on the coldest days)), and external gas ranks first. Final pick uses co2_reinject. Dissolution check (co2_reinject): CO2 0.16 Nm3/m3: dissolves at the wellhead (margin 7.27); reservoir margin 147.5 (conservative salinity 2.29 mol/kg). Dissolution check (reinject_all): CO2+CH4 0.80 Nm3/m3: wellhead margin 0.11 < 1: co-inject through a dip tube reaching >= 558 m (bubble point 61.5 bar(g)); reservoir margin 4.8 (conservative salinity 2.29 mol/kg).

**95. [final] Final pick: n2_q300_s1.8_ua1000_z3500_co2ri**
> Depth ladder: 2500->2750 m: -18.4%, 1.641 t/yr/m (kept); 2750->3000 m: -16.9%, 1.229 t/yr/m (kept); 3000->3250 m: -14.7%, 0.890 t/yr/m (kept); 3250->3500 m: -5.0%, 0.257 t/yr/m (rejected, marginal); 3250->3500 m: -6.3%, 0.268 t/yr/m (kept); 3500->3750 m: -0.8%, 0.033 t/yr/m (rejected). Selected n2_q300_s1.8_ua1000_z3500_co2ri (117 C reservoir): selected: feasible; external gas 0.0157 GWh, emissions 3983 t, grid import 0.87 GWh, 2 doublets, 14000 m drilled. Versus the conventional reference (gas boiler eta 0.90 + electric chiller COP 5.0, 26706 t): 85.1% lower emissions, external gas 0.016 vs 124.1 GWh, grid import 0.87 vs 4.75 GWh. Well checks at the pick: 300 m3/h: wellhead 114.1 C exceeds PVTConstantSTP temperature_max (100 C) - constant brine properties extrapolated. Drilling cost is not modeled; deeper steps are limited by the 5% parsimony rule. Gas handling: options compared at n2_q300_s1.8_ua1000_z3500: chp external gas 0.016 GWh, 4891 t, grid 0.80 GWh; co2_reinject external gas 0.016 GWh, 3983 t, grid 0.87 GWh; reinject_all external gas 0.271 GWh, 2023 t, grid 6.56 GWh. The ranking keeps co2_reinject at that design (external gas first, then emissions); reinject_all has the lowest emissions but needs more external gas (0.271 vs 0.016 GWh (without CHP heat the heat pump cannot cover the whole lift on the coldest days)), and external gas ranks first. Final pick uses co2_reinject. Dissolution check (co2_reinject): CO2 0.16 Nm3/m3: dissolves at the wellhead (margin 7.27); reservoir margin 147.5 (conservative salinity 2.29 mol/kg). Dissolution check (reinject_all): CO2+CH4 0.80 Nm3/m3: wellhead margin 0.11 < 1: co-inject through a dip tube reaching >= 558 m (bubble point 61.5 bar(g)); reservoir margin 4.8 (conservative salinity 2.29 mol/kg). N-1 (unplanned outage of one doublet, ASSUMED): peak heating day 2027-01-28: boiler 15.1 MWth, electric chiller 0.0 MWcool; peak cooling day 2027-07-19: boiler 2.1 MWth, electric chiller 0.0 MWcool; installed backup 15.1 MWth boiler + 0.0 MWcool electric chiller covers it. One-doublet alternative n1_q300_s1.8_ua1000_z2500 (valid per the organizer clarification of 2026-11-01, backup covers the source outage): feasible with 35 day(s) without geothermal supply, installed backup 30.0 MWth boiler + 10.0 MWcool chiller, but 28.6 GWh external gas and 12968 t, so it is ranked out. One-doublet alternative n1_q300_s1.8_ua1000_z3500_co2ri (valid per the organizer clarification of 2026-11-01, backup covers the source outage): feasible with 35 day(s) without geothermal supply, installed backup 30.0 MWth boiler + 10.0 MWcool chiller, but 36.5 GWh external gas and 10783 t, so it is ranked out.


## Scenario B: complete inputs, design loop

