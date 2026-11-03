# Design agent trace (rules backend)

Generated 2026-11-03 21:48 UTC from `decision_log.jsonl` (63 logged steps). Rerun: `$env:PYTHONPATH="src"; py -3.11 -m poetry run python hackathon_work/design_agent.py --backend rules`.

## Judges' agent-reasoning tests

| Test | Result | Evidence |
|---|---|---|
| (i) missing physical quantity -> stop and ask | PASS | removed: heating_return_T; step 4: I cannot size the plant without 1 input(s): heating_return_T. 'heating_return_T' (heating return temperature, C, ASSUMED) is needed because it sets district water flow = Q / (cp * (100 - T_return)) and the HEX/heat-pump lift; plausible range 40-80 C. It is not in the organizers' inputs and I will not invent it. Please provide a value (or rerun with --interactive to answer in the terminal). |
| (ii) >= 350 m3/h per doublet -> rejected with reason, revised | PASS | step 17: 350.00 m3/h exceeds the 300 m3/h hard cap -> step 18: Revised to n2_q300_s1.8_ua1000_z2500; also step 10: 650.00 m3/h exceeds the 300 m3/h hard cap -> step 11: Revised to n1_q300_s1.8_ua1000_z2500 |
| (iii) 87 C reservoir vs 100 C supply -> shortfall stated, deeper well vs surface upgrade decided | PASS | step 8 (assessment); candidates evaluated at reservoir temperatures [87.0, 94.5, 102.0, 109.5, 117.0] C; step 63 (decision) |
| (iv) recovery after a failed / ranked-out candidate | PASS | step 14: Annual model + constraint check: n1_q300_s1.8_ua1000_z2500 infeasible (never_all_off) -> step 21: Annual model + constraint check: n2_q300_s1.8_ua1000_z2500 feasible; ranked-out recoveries at steps [28, 33, 57] |

## Evaluations (scenario B)

| # | Candidate | T_res (C) | ESP set (m) / intake (bar) | Feasible | External gas (GWh) | Emissions (t) | Grid import (GWh) | Drilled (m) | Wall (s) | Final verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | n1_q300_s1.8_ua1000_z2500 | 87 | 660 / 30.3 | no (never_all_off) | 28.597 | 12968 | 11.91 | 5000 | 0.8 | REJECTED (rank 9) |
| 2 | n2_q300_s1.8_ua1000_z2500 | 87 | 660 / 30.3 | yes | 0.002 | 8908 | 12.01 | 10000 | 0.8 | REJECTED (rank 5) |
| 3 | n2_q300_s1.8_ua500_z2500 | 87 | 660 / 30.3 | yes | 0.008 | 9036 | 12.50 | 10000 | 1.9 | REJECTED (rank 7) |
| 4 | n2_q300_s1.0_ua1000_z2500 | 87 | 530 / 30.7 | yes | 8.090 | 9429 | 11.49 | 10000 | 1.5 | REJECTED (rank 8) |
| 5 | n2_q300_s1.8_ua1000_z2750 | 94 | 670 / 30.1 | yes | 0.006 | 7267 | 7.83 | 11000 | 0.9 | REJECTED (rank 4) |
| 6 | n2_q300_s1.8_ua1000_z3000 | 102 | 690 / 31.0 | yes | 0.004 | 6038 | 4.66 | 12000 | 0.9 | REJECTED (rank 3) |
| 7 | n2_q300_s1.8_ua1000_z3250 | 110 | 700 / 30.9 | yes | 0.004 | 5148 | 1.84 | 13000 | 1.4 | ACCEPTED (rank 1) |
| 8 | n2_q300_s1.8_ua1000_z3500 | 117 | 710 / 30.7 | yes | 0.016 | 4891 | 0.80 | 14000 | 0.6 | REJECTED (rank 6) |
| 9 | n3_q300_s1.8_ua1000_z3250 | 110 | 700 / 30.9 | yes | 0.004 | 5148 | 1.84 | 19500 | 1.4 | REJECTED (rank 2) |

## Final pick

Depth ladder: 2500->2750 m: -18.4%, 1.641 t/yr/m (kept); 2750->3000 m: -16.9%, 1.229 t/yr/m (kept); 3000->3250 m: -14.7%, 0.890 t/yr/m (kept); 3250->3500 m: -5.0%, 0.257 t/yr/m (rejected, marginal). Selected n2_q300_s1.8_ua1000_z3250 (110 C reservoir): selected: feasible; external gas 0.0038 GWh, emissions 5148 t, grid import 1.84 GWh, 2 doublets, 13000 m drilled. Versus the conventional reference (gas boiler eta 0.90 + electric chiller COP 5.0, 26706 t): 80.7% lower emissions, external gas 0.004 vs 124.1 GWh, grid import 1.84 vs 4.75 GWh. Well checks at the pick: 300 m3/h: wellhead 107.0 C exceeds PVTConstantSTP temperature_max (100 C) - constant brine properties extrapolated. Drilling cost is not modeled; deeper steps are limited by the 5% parsimony rule. Marginal sensitivity case: n2_q300_s1.8_ua1000_z3500 (3500 m) changes emissions -4.994% vs 3250 m (0.26 t CO2/yr per extra metre), within the tie tolerance of the 5% threshold, so it is not taken (drilling cost and risk not modelled); its wellhead reaches 114.1 C vs 107.0 C at 3250 m, further above the 100 C brine-property (PVTConstantSTP) range.

## Marginal sensitivity cases

Rejected only because the step improvement is within the tie tolerance of the 5% threshold, which counts as not met (conservative: drilling cost and risk are not modelled).

| Candidate | Step | Emissions change | Abatement (t/yr per m) | Wellhead T max (C) |
|---|---|---|---|---|
| n2_q300_s1.8_ua1000_z3500 | 3250 -> 3500 m | -4.994% | 0.26 | 114.1 (vs 107.0; PVT range <= 100) |

## Runtime

- Annual evaluations: 9 (9 computed, 0 from cache); computed wall time mean 1.1 s, max 1.9 s
- Scenario B runtime: 10.2 s; scenario A runtime: 0.0 s
- Backend calls: 0 (0.0 s)

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

**9. [propose] Proposal n1_q650_s1.8_ua1000_z2500**
> Start with the fewest doublets (1): the ranking prefers fewer doublets, so the smallest plant that passes the hard constraints is the target. Flow sizing heuristic: peak 30.0 MW / 1 doublet(s) at the 40 K brine cap -> 639.4 m3/h per doublet, rounded up to 650 m3/h. Largest ESP (s = 1.8), HEX 1000 kW/K, official 2500 m reservoir.

**10. [validate] Rejected before simulation: n1_q650_s1.8_ua1000_z2500**
> 650.00 m3/h exceeds the 300 m3/h hard cap

**11. [revise] Revised to n1_q300_s1.8_ua1000_z2500**
> Clip to the nearest admissible value: flow_cap_m3h 650 -> 300 (650.00 m3/h exceeds the 300 m3/h hard cap). The proposal's intent (largest admissible flow) is kept; the shortfall is left to the heat pump / CHP and to more doublets if needed.

**12. [build_json] GEMINI JSON for n1_q300_s1.8_ua1000_z2500**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**13. [well_check] Well / ESP sanity check at 2500 m**
> No flags. Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 30.0 | 7.24 / 78.1 | 0.44 | 59.7 / 74.0 | 0.029 | 245.9 | 0.6 |
| 300 | 53.4 | 4.61 / 85.5 | 0.59 | 30.3 / 74.5 | 0.526 | 225.2 | 3.3 |

**14. [evaluate] Annual model + constraint check: n1_q300_s1.8_ua1000_z2500**
> INFEASIBLE: external gas 28.597 GWh, emissions 12968 t, grid import 11.91 GWh, drilled 5000 m; fails never_all_off (0.8 s)

**15. [rank] Ranking after evaluation**
> No feasible candidate yet.

| Candidate | Rank | Verdict | Reason |
|---|---|---|---|
| n1_q300_s1.8_ua1000_z2500 | 1 | REJECTED | fails hard constraints: annual checks |

**16. [propose] Proposal n2_q350_s1.8_ua1000_z2500**
> Recovery: n1_q300_s1.8_ua1000_z2500 failed (never_all_off). With 1 doublet(s) the 35-day maintenance window leaves the plant without geothermal supply, which the 'never all off' interpretation forbids; add a doublet so maintenance can be staggered. Flow sizing heuristic: peak 30.0 MW / 2 doublet(s) at the 40 K brine cap -> 319.7 m3/h per doublet, rounded up to 350 m3/h. Largest ESP (s = 1.8), HEX 1000 kW/K, official 2500 m reservoir.

**17. [validate] Rejected before simulation: n2_q350_s1.8_ua1000_z2500**
> 350.00 m3/h exceeds the 300 m3/h hard cap

**18. [revise] Revised to n2_q300_s1.8_ua1000_z2500**
> Clip to the nearest admissible value: flow_cap_m3h 350 -> 300 (350.00 m3/h exceeds the 300 m3/h hard cap). The proposal's intent (largest admissible flow) is kept; the shortfall is left to the heat pump / CHP and to more doublets if needed.

**19. [build_json] GEMINI JSON for n2_q300_s1.8_ua1000_z2500**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**20. [well_check] Well / ESP sanity check at 2500 m**
> No flags. Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 30.0 | 7.24 / 78.1 | 0.44 | 59.7 / 74.0 | 0.029 | 245.9 | 0.6 |
| 300 | 53.4 | 4.61 / 85.5 | 0.59 | 30.3 / 74.5 | 0.526 | 225.2 | 3.3 |

**21. [evaluate] Annual model + constraint check: n2_q300_s1.8_ua1000_z2500**
> FEASIBLE: external gas 0.002 GWh, emissions 8908 t, grid import 12.01 GWh, drilled 10000 m (0.8 s)

**22. [rank] Ranking after evaluation**
> Incumbent: n2_q300_s1.8_ua1000_z2500

| Candidate | Rank | Verdict | Reason |
|---|---|---|---|
| n2_q300_s1.8_ua1000_z2500 | 1 | ACCEPTED | selected: feasible; external gas 0.0020 GWh, emissions 8908 t, grid import 12.01 GWh, 2 doublets, 10000 m drilled |
| n1_q300_s1.8_ua1000_z2500 | 2 | REJECTED | fails hard constraints: annual checks |

**23. [propose] Proposal n2_q300_s1.8_ua500_z2500**
> Variant of incumbent n2_q300_s1.8_ua1000_z2500: Smaller HEX (500 kW/K, lower cost): check whether the heat pump can absorb the lost HEX duty without external gas.

**24. [build_json] GEMINI JSON for n2_q300_s1.8_ua500_z2500**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**25. [well_check] Well / ESP sanity check at 2500 m**
> No flags. Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 30.0 | 7.24 / 78.1 | 0.44 | 59.7 / 74.0 | 0.029 | 245.9 | 0.6 |
| 300 | 53.4 | 4.61 / 85.5 | 0.59 | 30.3 / 74.5 | 0.526 | 225.2 | 3.3 |

**26. [evaluate] Annual model + constraint check: n2_q300_s1.8_ua500_z2500**
> FEASIBLE: external gas 0.008 GWh, emissions 9036 t, grid import 12.50 GWh, drilled 10000 m (1.9 s)

**27. [rank] Ranking after evaluation**
> Incumbent: n2_q300_s1.8_ua1000_z2500

| Candidate | Rank | Verdict | Reason |
|---|---|---|---|
| n2_q300_s1.8_ua1000_z2500 | 1 | ACCEPTED | selected: feasible; external gas 0.0020 GWh, emissions 8908 t, grid import 12.01 GWh, 2 doublets, 10000 m drilled |
| n2_q300_s1.8_ua500_z2500 | 2 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on emissions_t (tied within tolerance on external_gas_fuel_GWh): external gas 0.0079 vs 0.0020 GWh, emissions 9036 vs 8908 t, grid import 12.50 vs 12.01 GWh, drilled 10000 vs 10000 m |
| n1_q300_s1.8_ua1000_z2500 | 3 | REJECTED | fails hard constraints: annual checks |

**28. [propose] Proposal n2_q300_s1.0_ua1000_z2500**
> Previous candidate n2_q300_s1.8_ua500_z2500 was ranked out (same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on emissions_t (tied within tolerance on external_gas_fuel_GWh): external gas 0.0079 vs 0.0020 GWh, emissions 9036 vs 8908 t, grid import 12.50 vs 12.01 GWh, drilled 10000 vs 10000 m); keep incumbent n2_q300_s1.8_ua1000_z2500. Variant of incumbent n2_q300_s1.8_ua1000_z2500: Smaller ESP (s = 1.0, the GEMINI example pump): cheaper, but capped at ~176 m3/h; check the effect on external gas.

**29. [build_json] GEMINI JSON for n2_q300_s1.0_ua1000_z2500**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**30. [well_check] Well / ESP sanity check at 2500 m**
> Flags: 195 m3/h: ESP at 69.7 Hz, within 2 Hz of the drive limit; ESP reaches only 195 of the 300 m3/h cap at this depth. Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 39.5 | 3.00 / 78.1 | 0.44 | 46.5 / 56.6 | 0.020 | 245.9 | 0.6 |
| 195 | 69.7 | 3.34 / 84.7 | 0.57 | 30.7 / 58.0 | 0.211 | 233.9 | 2.2 |

**31. [evaluate] Annual model + constraint check: n2_q300_s1.0_ua1000_z2500**
> FEASIBLE: external gas 8.090 GWh, emissions 9429 t, grid import 11.49 GWh, drilled 10000 m (1.5 s)

**32. [rank] Ranking after evaluation**
> Incumbent: n2_q300_s1.8_ua1000_z2500

| Candidate | Rank | Verdict | Reason |
|---|---|---|---|
| n2_q300_s1.8_ua1000_z2500 | 1 | ACCEPTED | selected: feasible; external gas 0.0020 GWh, emissions 8908 t, grid import 12.01 GWh, 2 doublets, 10000 m drilled |
| n2_q300_s1.8_ua500_z2500 | 2 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on emissions_t (tied within tolerance on external_gas_fuel_GWh): external gas 0.0079 vs 0.0020 GWh, emissions 9036 vs 8908 t, grid import 12.50 vs 12.01 GWh, drilled 10000 vs 10000 m |
| n2_q300_s1.0_ua1000_z2500 | 3 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on external_gas_fuel_GWh: external gas 8.0904 vs 0.0020 GWh, emissions 9429 vs 8908 t, grid import 11.49 vs 12.01 GWh, drilled 10000 vs 10000 m |
| n1_q300_s1.8_ua1000_z2500 | 4 | REJECTED | fails hard constraints: annual checks |

**33. [propose] Proposal n2_q300_s1.8_ua1000_z2750**
> Previous candidate n2_q300_s1.0_ua1000_z2500 was ranked out (same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on external_gas_fuel_GWh: external gas 8.0904 vs 0.0020 GWh, emissions 9429 vs 8908 t, grid import 11.49 vs 12.01 GWh, drilled 10000 vs 10000 m); keep incumbent n2_q300_s1.8_ua1000_z2500. Depth ladder from incumbent n2_q300_s1.8_ua1000_z2500: 2500 -> 2750 m (reservoir 94.5 C) to cut the heat-pump lift; accepted only if emissions improve >= 5% vs the 2500 m design.

**34. [build_json] GEMINI JSON for n2_q300_s1.8_ua1000_z2750**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**35. [well_check] Well / ESP sanity check at 2750 m**
> No flags. Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 30.0 | 7.20 / 83.7 | 0.55 | 60.6 / 75.0 | 0.029 | 271.1 | 0.6 |
| 300 | 54.1 | 4.61 / 92.7 | 0.78 | 30.1 / 75.6 | 0.541 | 250.5 | 3.3 |

**36. [evaluate] Annual model + constraint check: n2_q300_s1.8_ua1000_z2750**
> FEASIBLE: external gas 0.006 GWh, emissions 7267 t, grid import 7.83 GWh, drilled 11000 m (0.9 s)

**37. [rank] Ranking after evaluation**
> Incumbent: n2_q300_s1.8_ua1000_z2750 (was n2_q300_s1.8_ua1000_z2500)

| Candidate | Rank | Verdict | Reason |
|---|---|---|---|
| n2_q300_s1.8_ua1000_z2750 | 1 | ACCEPTED | selected: feasible; external gas 0.0061 GWh, emissions 7267 t, grid import 7.83 GWh, 2 doublets, 11000 m drilled |
| n2_q300_s1.8_ua1000_z2500 | 2 | REJECTED | superseded by n2_q300_s1.8_ua1000_z2750: ranks better than n2_q300_s1.8_ua1000_z2500; deeper 2500 -> 2750 m: emissions +18.422% (needs >= 5% beyond the tie tolerance), marginal abatement 1.641 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua500_z2500 | 3 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on emissions_t (tied within tolerance on external_gas_fuel_GWh): external gas 0.0079 vs 0.0020 GWh, emissions 9036 vs 8908 t, grid import 12.50 vs 12.01 GWh, drilled 10000 vs 10000 m |
| n2_q300_s1.0_ua1000_z2500 | 4 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on external_gas_fuel_GWh: external gas 8.0904 vs 0.0020 GWh, emissions 9429 vs 8908 t, grid import 11.49 vs 12.01 GWh, drilled 10000 vs 10000 m |
| n1_q300_s1.8_ua1000_z2500 | 5 | REJECTED | fails hard constraints: annual checks |

**38. [depth_step] Depth step 2500 -> 2750 m**
> Emissions 8908 -> 7267 t (-18.4%) for +1000 m drilled: 1.641 t CO2/yr per extra metre. ACCEPTED (>= 5% beyond the tie tolerance).

**39. [propose] Proposal n2_q300_s1.8_ua1000_z3000**
>  Depth ladder from incumbent n2_q300_s1.8_ua1000_z2750: 2750 -> 3000 m (reservoir 102.0 C) to cut the heat-pump lift; accepted only if emissions improve >= 5% vs the 2750 m design.

**40. [build_json] GEMINI JSON for n2_q300_s1.8_ua1000_z3000**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**41. [well_check] Well / ESP sanity check at 3000 m**
> No flags. Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 30.0 | 7.17 / 89.1 | 0.68 | 62.6 / 77.0 | 0.029 | 296.4 | 0.6 |
| 300 | 54.8 | 4.61 / 99.9 | 1.01 | 31.0 / 77.7 | 0.555 | 275.7 | 3.3 |

**42. [evaluate] Annual model + constraint check: n2_q300_s1.8_ua1000_z3000**
> FEASIBLE: external gas 0.004 GWh, emissions 6038 t, grid import 4.66 GWh, drilled 12000 m (0.9 s)

**43. [rank] Ranking after evaluation**
> Incumbent: n2_q300_s1.8_ua1000_z3000 (was n2_q300_s1.8_ua1000_z2750)

| Candidate | Rank | Verdict | Reason |
|---|---|---|---|
| n2_q300_s1.8_ua1000_z3000 | 1 | ACCEPTED | selected: feasible; external gas 0.0044 GWh, emissions 6038 t, grid import 4.66 GWh, 2 doublets, 12000 m drilled |
| n2_q300_s1.8_ua1000_z2750 | 2 | REJECTED | superseded by n2_q300_s1.8_ua1000_z3000: ranks better than n2_q300_s1.8_ua1000_z2750; deeper 2750 -> 3000 m: emissions +16.910% (needs >= 5% beyond the tie tolerance), marginal abatement 1.229 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua1000_z2500 | 3 | REJECTED | superseded by n2_q300_s1.8_ua1000_z2750: ranks better than n2_q300_s1.8_ua1000_z2500; deeper 2500 -> 2750 m: emissions +18.422% (needs >= 5% beyond the tie tolerance), marginal abatement 1.641 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua500_z2500 | 4 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on emissions_t (tied within tolerance on external_gas_fuel_GWh): external gas 0.0079 vs 0.0020 GWh, emissions 9036 vs 8908 t, grid import 12.50 vs 12.01 GWh, drilled 10000 vs 10000 m |
| n2_q300_s1.0_ua1000_z2500 | 5 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on external_gas_fuel_GWh: external gas 8.0904 vs 0.0020 GWh, emissions 9429 vs 8908 t, grid import 11.49 vs 12.01 GWh, drilled 10000 vs 10000 m |
| n1_q300_s1.8_ua1000_z2500 | 6 | REJECTED | fails hard constraints: annual checks |

**44. [depth_step] Depth step 2750 -> 3000 m**
> Emissions 7267 -> 6038 t (-16.9%) for +1000 m drilled: 1.229 t CO2/yr per extra metre. ACCEPTED (>= 5% beyond the tie tolerance).

**45. [propose] Proposal n2_q300_s1.8_ua1000_z3250**
>  Depth ladder from incumbent n2_q300_s1.8_ua1000_z3000: 3000 -> 3250 m (reservoir 109.5 C) to cut the heat-pump lift; accepted only if emissions improve >= 5% vs the 3000 m design.

**46. [build_json] GEMINI JSON for n2_q300_s1.8_ua1000_z3250**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**47. [well_check] Well / ESP sanity check at 3250 m**
> Flags: 300 m3/h: wellhead 107.0 C exceeds PVTConstantSTP temperature_max (100 C) - constant brine properties extrapolated. Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 30.0 | 7.13 / 94.4 | 0.83 | 63.6 / 78.0 | 0.029 | 321.7 | 0.6 |
| 300 | 55.5 | 4.61 / 107.0 | 1.30 | 30.9 / 78.8 | 0.570 | 301.0 | 3.3 |

**48. [evaluate] Annual model + constraint check: n2_q300_s1.8_ua1000_z3250**
> FEASIBLE: external gas 0.004 GWh, emissions 5148 t, grid import 1.84 GWh, drilled 13000 m (1.4 s)

**49. [rank] Ranking after evaluation**
> Incumbent: n2_q300_s1.8_ua1000_z3250 (was n2_q300_s1.8_ua1000_z3000)

| Candidate | Rank | Verdict | Reason |
|---|---|---|---|
| n2_q300_s1.8_ua1000_z3250 | 1 | ACCEPTED | selected: feasible; external gas 0.0038 GWh, emissions 5148 t, grid import 1.84 GWh, 2 doublets, 13000 m drilled |
| n2_q300_s1.8_ua1000_z3000 | 2 | REJECTED | superseded by n2_q300_s1.8_ua1000_z3250: ranks better than n2_q300_s1.8_ua1000_z3000; deeper 3000 -> 3250 m: emissions +14.744% (needs >= 5% beyond the tie tolerance), marginal abatement 0.890 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua1000_z2750 | 3 | REJECTED | superseded by n2_q300_s1.8_ua1000_z3000: ranks better than n2_q300_s1.8_ua1000_z2750; deeper 2750 -> 3000 m: emissions +16.910% (needs >= 5% beyond the tie tolerance), marginal abatement 1.229 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua1000_z2500 | 4 | REJECTED | superseded by n2_q300_s1.8_ua1000_z2750: ranks better than n2_q300_s1.8_ua1000_z2500; deeper 2500 -> 2750 m: emissions +18.422% (needs >= 5% beyond the tie tolerance), marginal abatement 1.641 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua500_z2500 | 5 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on emissions_t (tied within tolerance on external_gas_fuel_GWh): external gas 0.0079 vs 0.0020 GWh, emissions 9036 vs 8908 t, grid import 12.50 vs 12.01 GWh, drilled 10000 vs 10000 m |
| n2_q300_s1.0_ua1000_z2500 | 6 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on external_gas_fuel_GWh: external gas 8.0904 vs 0.0020 GWh, emissions 9429 vs 8908 t, grid import 11.49 vs 12.01 GWh, drilled 10000 vs 10000 m |
| n1_q300_s1.8_ua1000_z2500 | 7 | REJECTED | fails hard constraints: annual checks |

**50. [depth_step] Depth step 3000 -> 3250 m**
> Emissions 6038 -> 5148 t (-14.7%) for +1000 m drilled: 0.890 t CO2/yr per extra metre. ACCEPTED (>= 5% beyond the tie tolerance).

**51. [propose] Proposal n2_q300_s1.8_ua1000_z3500**
>  Depth ladder from incumbent n2_q300_s1.8_ua1000_z3250: 3250 -> 3500 m (reservoir 117.0 C) to cut the heat-pump lift; accepted only if emissions improve >= 5% vs the 3250 m design.

**52. [build_json] GEMINI JSON for n2_q300_s1.8_ua1000_z3500**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**53. [well_check] Well / ESP sanity check at 3500 m**
> Flags: 300 m3/h: wellhead 114.1 C exceeds PVTConstantSTP temperature_max (100 C) - constant brine properties extrapolated. Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 30.0 | 7.09 / 99.5 | 1.00 | 64.6 / 78.9 | 0.029 | 346.9 | 0.6 |
| 300 | 56.2 | 4.61 / 114.1 | 1.64 | 30.7 / 79.8 | 0.584 | 326.2 | 3.3 |

**54. [evaluate] Annual model + constraint check: n2_q300_s1.8_ua1000_z3500**
> FEASIBLE: external gas 0.016 GWh, emissions 4891 t, grid import 0.80 GWh, drilled 14000 m (0.6 s)

**55. [rank] Ranking after evaluation**
> Incumbent: n2_q300_s1.8_ua1000_z3250

| Candidate | Rank | Verdict | Reason |
|---|---|---|---|
| n2_q300_s1.8_ua1000_z3250 | 1 | ACCEPTED | selected: feasible; external gas 0.0038 GWh, emissions 5148 t, grid import 1.84 GWh, 2 doublets, 13000 m drilled |
| n2_q300_s1.8_ua1000_z3000 | 2 | REJECTED | superseded by n2_q300_s1.8_ua1000_z3250: ranks better than n2_q300_s1.8_ua1000_z3000; deeper 3000 -> 3250 m: emissions +14.744% (needs >= 5% beyond the tie tolerance), marginal abatement 0.890 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua1000_z2750 | 3 | REJECTED | superseded by n2_q300_s1.8_ua1000_z3000: ranks better than n2_q300_s1.8_ua1000_z2750; deeper 2750 -> 3000 m: emissions +16.910% (needs >= 5% beyond the tie tolerance), marginal abatement 1.229 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua1000_z2500 | 4 | REJECTED | superseded by n2_q300_s1.8_ua1000_z2750: ranks better than n2_q300_s1.8_ua1000_z2500; deeper 2500 -> 2750 m: emissions +18.422% (needs >= 5% beyond the tie tolerance), marginal abatement 1.641 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua1000_z3500 | 5 | REJECTED | parsimony rule not met: ranks not better than n2_q300_s1.8_ua1000_z3250; deeper 3250 -> 3500 m: emissions +4.994% (needs >= 5% beyond the tie tolerance), marginal abatement 0.257 t CO2/yr per extra metre drilled - within the tie tolerance of the threshold, counts as NOT met (marginal sensitivity case) |
| n2_q300_s1.8_ua500_z2500 | 6 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on emissions_t (tied within tolerance on external_gas_fuel_GWh): external gas 0.0079 vs 0.0020 GWh, emissions 9036 vs 8908 t, grid import 12.50 vs 12.01 GWh, drilled 10000 vs 10000 m |
| n2_q300_s1.0_ua1000_z2500 | 7 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on external_gas_fuel_GWh: external gas 8.0904 vs 0.0020 GWh, emissions 9429 vs 8908 t, grid import 11.49 vs 12.01 GWh, drilled 10000 vs 10000 m |
| n1_q300_s1.8_ua1000_z2500 | 8 | REJECTED | fails hard constraints: annual checks |

**56. [depth_step] Depth step 3250 -> 3500 m**
> Emissions 5148 -> 4891 t (-5.0%) for +1000 m drilled: 0.257 t CO2/yr per extra metre. REJECTED: within the tie tolerance of the 5% threshold, which counts as not met (conservative: drilling cost and risk are not modelled); recorded as a marginal sensitivity case.

**57. [propose] Proposal n3_q300_s1.8_ua1000_z3250**
> Previous candidate n2_q300_s1.8_ua1000_z3500 was ranked out (parsimony rule not met: ranks not better than n2_q300_s1.8_ua1000_z3250; deeper 3250 -> 3500 m: emissions +4.994% (needs >= 5% beyond the tie tolerance), marginal abatement 0.257 t CO2/yr per extra metre drilled - within the tie tolerance of the threshold, counts as NOT met (marginal sensitivity case)); keep incumbent n2_q300_s1.8_ua1000_z3250. Depth step to 3500 m failed the parsimony rule; stop exploring deeper (accepted depth stays 3250 m). Variant of incumbent n2_q300_s1.8_ua1000_z3250: More doublets: accepted only if external gas or emissions improve by >= 5%.

**58. [build_json] GEMINI JSON for n3_q300_s1.8_ua1000_z3250**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**59. [well_check] Well / ESP sanity check at 3250 m**
> Flags: 300 m3/h: wellhead 107.0 C exceeds PVTConstantSTP temperature_max (100 C) - constant brine properties extrapolated. Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 30.0 | 7.13 / 94.4 | 0.83 | 63.6 / 78.0 | 0.029 | 321.7 | 0.6 |
| 300 | 55.5 | 4.61 / 107.0 | 1.30 | 30.9 / 78.8 | 0.570 | 301.0 | 3.3 |

**60. [evaluate] Annual model + constraint check: n3_q300_s1.8_ua1000_z3250**
> FEASIBLE: external gas 0.004 GWh, emissions 5148 t, grid import 1.84 GWh, drilled 19500 m (1.4 s)

**61. [rank] Ranking after evaluation**
> Incumbent: n2_q300_s1.8_ua1000_z3250

| Candidate | Rank | Verdict | Reason |
|---|---|---|---|
| n2_q300_s1.8_ua1000_z3250 | 1 | ACCEPTED | selected: feasible; external gas 0.0038 GWh, emissions 5148 t, grid import 1.84 GWh, 2 doublets, 13000 m drilled |
| n3_q300_s1.8_ua1000_z3250 | 2 | REJECTED | parsimony rule not met: ranks not better than n2_q300_s1.8_ua1000_z3250; extra doublet: external gas +0.0%, emissions +0.0% (needs >= 5% on either, beyond the tie tolerance) |
| n2_q300_s1.8_ua1000_z3000 | 3 | REJECTED | superseded by n2_q300_s1.8_ua1000_z3250: ranks better than n2_q300_s1.8_ua1000_z3000; deeper 3000 -> 3250 m: emissions +14.744% (needs >= 5% beyond the tie tolerance), marginal abatement 0.890 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua1000_z2750 | 4 | REJECTED | superseded by n2_q300_s1.8_ua1000_z3000: ranks better than n2_q300_s1.8_ua1000_z2750; deeper 2750 -> 3000 m: emissions +16.910% (needs >= 5% beyond the tie tolerance), marginal abatement 1.229 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua1000_z2500 | 5 | REJECTED | superseded by n2_q300_s1.8_ua1000_z2750: ranks better than n2_q300_s1.8_ua1000_z2500; deeper 2500 -> 2750 m: emissions +18.422% (needs >= 5% beyond the tie tolerance), marginal abatement 1.641 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua1000_z3500 | 6 | REJECTED | parsimony rule not met: ranks not better than n2_q300_s1.8_ua1000_z3250; deeper 3250 -> 3500 m: emissions +4.994% (needs >= 5% beyond the tie tolerance), marginal abatement 0.257 t CO2/yr per extra metre drilled - within the tie tolerance of the threshold, counts as NOT met (marginal sensitivity case) |
| n2_q300_s1.8_ua500_z2500 | 7 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on emissions_t (tied within tolerance on external_gas_fuel_GWh): external gas 0.0079 vs 0.0020 GWh, emissions 9036 vs 8908 t, grid import 12.50 vs 12.01 GWh, drilled 10000 vs 10000 m |
| n2_q300_s1.0_ua1000_z2500 | 8 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on external_gas_fuel_GWh: external gas 8.0904 vs 0.0020 GWh, emissions 9429 vs 8908 t, grid import 11.49 vs 12.01 GWh, drilled 10000 vs 10000 m |
| n1_q300_s1.8_ua1000_z2500 | 9 | REJECTED | fails hard constraints: annual checks |

**62. [stop] Backend stops proposing**
> No untried variant can change the pick within the design space and the parsimony rules.

**63. [final] Final pick: n2_q300_s1.8_ua1000_z3250**
> Depth ladder: 2500->2750 m: -18.4%, 1.641 t/yr/m (kept); 2750->3000 m: -16.9%, 1.229 t/yr/m (kept); 3000->3250 m: -14.7%, 0.890 t/yr/m (kept); 3250->3500 m: -5.0%, 0.257 t/yr/m (rejected, marginal). Selected n2_q300_s1.8_ua1000_z3250 (110 C reservoir): selected: feasible; external gas 0.0038 GWh, emissions 5148 t, grid import 1.84 GWh, 2 doublets, 13000 m drilled. Versus the conventional reference (gas boiler eta 0.90 + electric chiller COP 5.0, 26706 t): 80.7% lower emissions, external gas 0.004 vs 124.1 GWh, grid import 1.84 vs 4.75 GWh. Well checks at the pick: 300 m3/h: wellhead 107.0 C exceeds PVTConstantSTP temperature_max (100 C) - constant brine properties extrapolated. Drilling cost is not modeled; deeper steps are limited by the 5% parsimony rule. Marginal sensitivity case: n2_q300_s1.8_ua1000_z3500 (3500 m) changes emissions -4.994% vs 3250 m (0.26 t CO2/yr per extra metre), within the tie tolerance of the 5% threshold, so it is not taken (drilling cost and risk not modelled); its wellhead reaches 114.1 C vs 107.0 C at 3250 m, further above the 100 C brine-property (PVTConstantSTP) range.

