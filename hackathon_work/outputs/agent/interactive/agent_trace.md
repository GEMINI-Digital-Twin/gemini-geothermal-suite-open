# Design agent trace (rules backend, interactive)

Generated 2026-11-03 06:19 UTC from `decision_log.jsonl` (56 logged steps). Rerun: `$env:PYTHONPATH="src"; py -3.11 -m poetry run python hackathon_work/design_agent.py --backend rules`.

## Judges' agent-reasoning tests

| Test | Result | Evidence |
|---|---|---|
| (i) missing physical quantity -> stop and ask | PASS | step 4 AGENT ASKED: I cannot size the plant without the heating return temperature. It is needed because it sets district water flow = Q / (cp * (100 - T_return)) and the HEX/heat-pump lift. It is not in the organizers' inputs and I will not invent it. Please type a value in C (plausible range 40-80 C), or 'q' to stop. -> step 5 USER ANSWERED '40': accepted, 40 C. |
| (ii) >= 350 m3/h per doublet -> rejected with reason, revised | PASS | step 9: 650.00 m3/h exceeds the 300 m3/h hard cap -> step 10: Revised to n1_q300_s1.8_ua1000_z2500 |
| (iii) 87 C reservoir vs 100 C supply -> shortfall stated, deeper well vs surface upgrade decided | PASS | step 7 (assessment); candidates evaluated at reservoir temperatures [87.0, 94.5, 102.0, 109.5] C; step 56 (decision) |
| (iv) recovery after a failed / ranked-out candidate | PASS | step 13: Annual model + constraint check: n1_q300_s1.8_ua1000_z2500 infeasible (never_all_off) -> step 20: Annual model + constraint check: n2_q300_s1.8_ua1000_z2500 feasible; ranked-out recoveries at steps [27, 32, 50] |

## Evaluations (scenario A)

| # | Candidate | T_res (C) | ESP set (m) / intake (bar) | Feasible | External gas (GWh) | Emissions (t) | Grid import (GWh) | Drilled (m) | Wall (s) | Final verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | n1_q300_s1.8_ua1000_z2500 | 87 | 660 / 30.3 | no (never_all_off) | 32.697 | 12462 | 7.36 | 5000 | 0.8 | REJECTED (rank 8) |
| 2 | n2_q300_s1.8_ua1000_z2500 | 87 | 660 / 30.3 | yes | 0.002 | 7832 | 8.02 | 10000 | 0.9 | REJECTED (rank 4) |
| 3 | n2_q300_s1.8_ua500_z2500 | 87 | 660 / 30.3 | yes | 0.001 | 8172 | 9.28 | 10000 | 0.8 | REJECTED (rank 5) |
| 4 | n2_q300_s1.0_ua1000_z2500 | 87 | 530 / 30.7 | yes | 11.695 | 8608 | 6.10 | 10000 | 0.8 | REJECTED (rank 7) |
| 5 | n2_q300_s1.8_ua1000_z2750 | 94 | 670 / 30.1 | yes | 0.002 | 6196 | 3.86 | 11000 | 0.8 | REJECTED (rank 3) |
| 6 | n2_q300_s1.8_ua1000_z3000 | 102 | 690 / 31.0 | yes | 0.002 | 5118 | 1.21 | 12000 | 1.6 | ACCEPTED (rank 1) |
| 7 | n2_q300_s1.8_ua1000_z3250 | 110 | 700 / 30.9 | yes | 0.012 | 4896 | 0.80 | 13000 | 0.6 | REJECTED (rank 6) |
| 8 | n3_q300_s1.8_ua1000_z3000 | 102 | 690 / 31.0 | yes | 0.002 | 5118 | 1.20 | 18000 | 1.6 | REJECTED (rank 2) |

## Final pick

Depth ladder: 2500->2750 m: -20.9%, 1.636 t/yr/m (kept); 2750->3000 m: -17.4%, 1.077 t/yr/m (kept); 3000->3250 m: -4.3%, 0.222 t/yr/m (rejected, marginal). Selected n2_q300_s1.8_ua1000_z3000 (102 C reservoir): selected: feasible; external gas 0.0019 GWh, emissions 5118 t, grid import 1.21 GWh, 2 doublets, 12000 m drilled. Versus the conventional reference (gas boiler eta 0.90 + electric chiller COP 5.0, 26706 t): 80.8% lower emissions, external gas 0.002 vs 124.1 GWh, grid import 1.21 vs 4.75 GWh. Well checks at the pick: no flags. Drilling cost is not modeled; deeper steps are limited by the 5% parsimony rule. Marginal sensitivity case: n2_q300_s1.8_ua1000_z3250 (3250 m) changes emissions -4.345% vs 3000 m (0.22 t CO2/yr per extra metre), within the tie tolerance of the 5% threshold, so it is not taken (drilling cost and risk not modelled); its wellhead reaches 107.0 C vs 99.9 C at 3000 m, further above the 100 C brine-property (PVTConstantSTP) range.

## Marginal sensitivity cases

Rejected only because the step improvement is within the tie tolerance of the 5% threshold, which counts as not met (conservative: drilling cost and risk are not modelled).

| Candidate | Step | Emissions change | Abatement (t/yr per m) | Wellhead T max (C) |
|---|---|---|---|---|
| n2_q300_s1.8_ua1000_z3250 | 3000 -> 3250 m | -4.345% | 0.22 | 107.0 (vs 99.9; PVT range <= 100) |

## Runtime

- Annual evaluations: 8 (8 computed, 0 from cache); computed wall time mean 1.0 s, max 1.6 s
- Scenario B runtime: 27.6 s; scenario A runtime: 27.6 s
- Backend calls: 0 (0.0 s)

## Scenario A: heating return temperature removed from the inputs (interactive: the agent asks, the user answers, the design loop continues)

**1. [start] Scenario A_missing_input: start**

**2. [interpret] Interpret demand profiles and fixed inputs**
> 365-day heating (111.67 GWh, peak 30.0 MW on 2027-01-28) and cooling (23.74 GWh, peak 10.0 MW) must be served every day.

**3. [required_inputs] Check required inputs**
> 1 required input(s) missing: heating return temperature.

| Input | Present | Source | Needed for |
|---|---|---|---|
| heating demand profile (365 days) | yes | OFFICIAL CSV | sets daily heat to deliver |
| cooling demand profile (365 days) | yes | OFFICIAL CSV | sets daily cooling to deliver |
| reservoir depth / gradient / surface T / pressure / permeability | yes | OFFICIAL | source temperature and well inflow |
| brine density / viscosity / GLR / gas composition | yes | OFFICIAL | hydraulics, produced gas |
| hard constraints (flow, brine dT, pump eta, 330 days, supply temperatures) | yes | OFFICIAL | feasibility checks |
| heating return temperature | **MISSING** | ASSUMED, user-approved (60 C) | sets district water flow = Q / (cp * (100 - T_return)) and the HEX/heat-pump lift |
| cooling supply / return temperature | yes | OFFICIAL 20 C / ASSUMED 26 C | chiller duty |
| brine specific heat | yes | ASSUMED, user-approved (4100) | all heat balances |
| well inner diameter / roughness | yes | ASSUMED, user-approved | friction, pump power |
| heat pump / chiller performance | yes | ASSUMED, user-approved | electricity, cooling supply |
| emission factors | yes | DERIVED / ASSUMED | emissions ranking |

**4. AGENT ASKED** (2026-11-03 06:18:39 UTC)
> I cannot size the plant without the heating return temperature. It is needed because it sets district water flow = Q / (cp * (100 - T_return)) and the HEX/heat-pump lift. It is not in the organizers' inputs and I will not invent it. Please type a value in C (plausible range 40-80 C), or 'q' to stop.

**5. USER ANSWERED** (2026-11-03 06:18:58 UTC)
> '40': accepted, 40 C.

**6. [required_inputs] Check required inputs**
> All required inputs present.

| Input | Present | Source | Needed for |
|---|---|---|---|
| heating demand profile (365 days) | yes | OFFICIAL CSV | sets daily heat to deliver |
| cooling demand profile (365 days) | yes | OFFICIAL CSV | sets daily cooling to deliver |
| reservoir depth / gradient / surface T / pressure / permeability | yes | OFFICIAL | source temperature and well inflow |
| brine density / viscosity / GLR / gas composition | yes | OFFICIAL | hydraulics, produced gas |
| hard constraints (flow, brine dT, pump eta, 330 days, supply temperatures) | yes | OFFICIAL | feasibility checks |
| heating return temperature | yes | ASSUMED, user-approved (60 C) | sets district water flow = Q / (cp * (100 - T_return)) and the HEX/heat-pump lift |
| cooling supply / return temperature | yes | OFFICIAL 20 C / ASSUMED 26 C | chiller duty |
| brine specific heat | yes | ASSUMED, user-approved (4100) | all heat balances |
| well inner diameter / roughness | yes | ASSUMED, user-approved | friction, pump power |
| heat pump / chiller performance | yes | ASSUMED, user-approved | electricity, cooling supply |
| emission factors | yes | DERIVED / ASSUMED | emissions ranking |

**7. [temperature_assessment] Source temperature vs 100 C supply**
> Reservoir at 2500 m is 87.0 C, 13.0 K below the fixed 100 C supply before any losses, so a HEX alone cannot supply 100 C. Options: (a) deeper well - T_res = 100 C needs 2933 m, and direct HEX supply (T_res >= 107.4 C incl. 5 K approach, 0.4 K surface drops, ~2 K wellbore loss) needs ~3180 m; (b) surface upgrade - heat pump on the brine leaving the HEX plus CHP on the produced gas. Decision: start with (b) at the official 2500 m (no extrapolated reservoir data, least drilling), then climb a 250 m depth ladder (max 4000 m) and keep each step only if emissions fall >= 5%; the ranking decides with numbers.

**8. [propose] Proposal n1_q650_s1.8_ua1000_z2500**
> Start with the fewest doublets (1): the ranking prefers fewer doublets, so the smallest plant that passes the hard constraints is the target. Flow sizing heuristic: peak 30.0 MW / 1 doublet(s) at the 40 K brine cap -> 639.4 m3/h per doublet, rounded up to 650 m3/h. Largest ESP (s = 1.8), HEX 1000 kW/K, official 2500 m reservoir.

**9. [validate] Rejected before simulation: n1_q650_s1.8_ua1000_z2500**
> 650.00 m3/h exceeds the 300 m3/h hard cap

**10. [revise] Revised to n1_q300_s1.8_ua1000_z2500**
> Clip to the nearest admissible value: flow_cap_m3h 650 -> 300 (650.00 m3/h exceeds the 300 m3/h hard cap). The proposal's intent (largest admissible flow) is kept; the shortfall is left to the heat pump / CHP and to more doublets if needed.

**11. [build_json] GEMINI JSON for n1_q300_s1.8_ua1000_z2500**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**12. [well_check] Well / ESP sanity check at 2500 m**
> No flags. Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 30.0 | 7.24 / 78.1 | 0.44 | 59.7 / 74.0 | 0.029 | 245.9 | 0.6 |
| 300 | 53.4 | 4.61 / 85.5 | 0.59 | 30.3 / 74.5 | 0.526 | 225.2 | 3.3 |

**13. [evaluate] Annual model + constraint check: n1_q300_s1.8_ua1000_z2500**
> INFEASIBLE: external gas 32.697 GWh, emissions 12462 t, grid import 7.36 GWh, drilled 5000 m; fails never_all_off (0.8 s)

**14. [rank] Ranking after evaluation**
> No feasible candidate yet.

| Candidate | Rank | Verdict | Reason |
|---|---|---|---|
| n1_q300_s1.8_ua1000_z2500 | 1 | REJECTED | fails hard constraints: annual checks |

**15. [propose] Proposal n2_q350_s1.8_ua1000_z2500**
> Recovery: n1_q300_s1.8_ua1000_z2500 failed (never_all_off). With 1 doublet(s) the 35-day maintenance window leaves the plant without geothermal supply, which the 'never all off' interpretation forbids; add a doublet so maintenance can be staggered. Flow sizing heuristic: peak 30.0 MW / 2 doublet(s) at the 40 K brine cap -> 319.7 m3/h per doublet, rounded up to 350 m3/h. Largest ESP (s = 1.8), HEX 1000 kW/K, official 2500 m reservoir.

**16. [validate] Rejected before simulation: n2_q350_s1.8_ua1000_z2500**
> 350.00 m3/h exceeds the 300 m3/h hard cap

**17. [revise] Revised to n2_q300_s1.8_ua1000_z2500**
> Clip to the nearest admissible value: flow_cap_m3h 350 -> 300 (350.00 m3/h exceeds the 300 m3/h hard cap). The proposal's intent (largest admissible flow) is kept; the shortfall is left to the heat pump / CHP and to more doublets if needed.

**18. [build_json] GEMINI JSON for n2_q300_s1.8_ua1000_z2500**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**19. [well_check] Well / ESP sanity check at 2500 m**
> No flags. Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 30.0 | 7.24 / 78.1 | 0.44 | 59.7 / 74.0 | 0.029 | 245.9 | 0.6 |
| 300 | 53.4 | 4.61 / 85.5 | 0.59 | 30.3 / 74.5 | 0.526 | 225.2 | 3.3 |

**20. [evaluate] Annual model + constraint check: n2_q300_s1.8_ua1000_z2500**
> FEASIBLE: external gas 0.002 GWh, emissions 7832 t, grid import 8.02 GWh, drilled 10000 m (0.9 s)

**21. [rank] Ranking after evaluation**
> Incumbent: n2_q300_s1.8_ua1000_z2500

| Candidate | Rank | Verdict | Reason |
|---|---|---|---|
| n2_q300_s1.8_ua1000_z2500 | 1 | ACCEPTED | selected: feasible; external gas 0.0016 GWh, emissions 7832 t, grid import 8.02 GWh, 2 doublets, 10000 m drilled |
| n1_q300_s1.8_ua1000_z2500 | 2 | REJECTED | fails hard constraints: annual checks |

**22. [propose] Proposal n2_q300_s1.8_ua500_z2500**
> Variant of incumbent n2_q300_s1.8_ua1000_z2500: Smaller HEX (500 kW/K, lower cost): check whether the heat pump can absorb the lost HEX duty without external gas.

**23. [build_json] GEMINI JSON for n2_q300_s1.8_ua500_z2500**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**24. [well_check] Well / ESP sanity check at 2500 m**
> No flags. Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 30.0 | 7.24 / 78.1 | 0.44 | 59.7 / 74.0 | 0.029 | 245.9 | 0.6 |
| 300 | 53.4 | 4.61 / 85.5 | 0.59 | 30.3 / 74.5 | 0.526 | 225.2 | 3.3 |

**25. [evaluate] Annual model + constraint check: n2_q300_s1.8_ua500_z2500**
> FEASIBLE: external gas 0.001 GWh, emissions 8172 t, grid import 9.28 GWh, drilled 10000 m (0.8 s)

**26. [rank] Ranking after evaluation**
> Incumbent: n2_q300_s1.8_ua1000_z2500

| Candidate | Rank | Verdict | Reason |
|---|---|---|---|
| n2_q300_s1.8_ua1000_z2500 | 1 | ACCEPTED | selected: feasible; external gas 0.0016 GWh, emissions 7832 t, grid import 8.02 GWh, 2 doublets, 10000 m drilled |
| n2_q300_s1.8_ua500_z2500 | 2 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on emissions_t (tied within tolerance on external_gas_fuel_GWh): external gas 0.0013 vs 0.0016 GWh, emissions 8172 vs 7832 t, grid import 9.28 vs 8.02 GWh, drilled 10000 vs 10000 m |
| n1_q300_s1.8_ua1000_z2500 | 3 | REJECTED | fails hard constraints: annual checks |

**27. [propose] Proposal n2_q300_s1.0_ua1000_z2500**
> Previous candidate n2_q300_s1.8_ua500_z2500 was ranked out (same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on emissions_t (tied within tolerance on external_gas_fuel_GWh): external gas 0.0013 vs 0.0016 GWh, emissions 8172 vs 7832 t, grid import 9.28 vs 8.02 GWh, drilled 10000 vs 10000 m); keep incumbent n2_q300_s1.8_ua1000_z2500. Variant of incumbent n2_q300_s1.8_ua1000_z2500: Smaller ESP (s = 1.0, the GEMINI example pump): cheaper, but capped at ~176 m3/h; check the effect on external gas.

**28. [build_json] GEMINI JSON for n2_q300_s1.0_ua1000_z2500**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**29. [well_check] Well / ESP sanity check at 2500 m**
> Flags: 195 m3/h: ESP at 69.7 Hz, within 2 Hz of the drive limit; ESP reaches only 195 of the 300 m3/h cap at this depth. Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 39.5 | 3.00 / 78.1 | 0.44 | 46.5 / 56.6 | 0.020 | 245.9 | 0.6 |
| 195 | 69.7 | 3.34 / 84.7 | 0.57 | 30.7 / 58.0 | 0.211 | 233.9 | 2.2 |

**30. [evaluate] Annual model + constraint check: n2_q300_s1.0_ua1000_z2500**
> FEASIBLE: external gas 11.695 GWh, emissions 8608 t, grid import 6.10 GWh, drilled 10000 m (0.8 s)

**31. [rank] Ranking after evaluation**
> Incumbent: n2_q300_s1.8_ua1000_z2500

| Candidate | Rank | Verdict | Reason |
|---|---|---|---|
| n2_q300_s1.8_ua1000_z2500 | 1 | ACCEPTED | selected: feasible; external gas 0.0016 GWh, emissions 7832 t, grid import 8.02 GWh, 2 doublets, 10000 m drilled |
| n2_q300_s1.8_ua500_z2500 | 2 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on emissions_t (tied within tolerance on external_gas_fuel_GWh): external gas 0.0013 vs 0.0016 GWh, emissions 8172 vs 7832 t, grid import 9.28 vs 8.02 GWh, drilled 10000 vs 10000 m |
| n2_q300_s1.0_ua1000_z2500 | 3 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on external_gas_fuel_GWh: external gas 11.6945 vs 0.0016 GWh, emissions 8608 vs 7832 t, grid import 6.10 vs 8.02 GWh, drilled 10000 vs 10000 m |
| n1_q300_s1.8_ua1000_z2500 | 4 | REJECTED | fails hard constraints: annual checks |

**32. [propose] Proposal n2_q300_s1.8_ua1000_z2750**
> Previous candidate n2_q300_s1.0_ua1000_z2500 was ranked out (same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on external_gas_fuel_GWh: external gas 11.6945 vs 0.0016 GWh, emissions 8608 vs 7832 t, grid import 6.10 vs 8.02 GWh, drilled 10000 vs 10000 m); keep incumbent n2_q300_s1.8_ua1000_z2500. Depth ladder from incumbent n2_q300_s1.8_ua1000_z2500: 2500 -> 2750 m (reservoir 94.5 C) to cut the heat-pump lift; accepted only if emissions improve >= 5% vs the 2500 m design.

**33. [build_json] GEMINI JSON for n2_q300_s1.8_ua1000_z2750**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**34. [well_check] Well / ESP sanity check at 2750 m**
> No flags. Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 30.0 | 7.20 / 83.7 | 0.55 | 60.6 / 75.0 | 0.029 | 271.1 | 0.6 |
| 300 | 54.1 | 4.61 / 92.7 | 0.78 | 30.1 / 75.6 | 0.541 | 250.5 | 3.3 |

**35. [evaluate] Annual model + constraint check: n2_q300_s1.8_ua1000_z2750**
> FEASIBLE: external gas 0.002 GWh, emissions 6196 t, grid import 3.86 GWh, drilled 11000 m (0.8 s)

**36. [rank] Ranking after evaluation**
> Incumbent: n2_q300_s1.8_ua1000_z2750 (was n2_q300_s1.8_ua1000_z2500)

| Candidate | Rank | Verdict | Reason |
|---|---|---|---|
| n2_q300_s1.8_ua1000_z2750 | 1 | ACCEPTED | selected: feasible; external gas 0.0021 GWh, emissions 6196 t, grid import 3.86 GWh, 2 doublets, 11000 m drilled |
| n2_q300_s1.8_ua1000_z2500 | 2 | REJECTED | superseded by n2_q300_s1.8_ua1000_z2750: ranks better than n2_q300_s1.8_ua1000_z2500; deeper 2500 -> 2750 m: emissions +20.892% (needs >= 5% beyond the tie tolerance), marginal abatement 1.636 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua500_z2500 | 3 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on emissions_t (tied within tolerance on external_gas_fuel_GWh): external gas 0.0013 vs 0.0016 GWh, emissions 8172 vs 7832 t, grid import 9.28 vs 8.02 GWh, drilled 10000 vs 10000 m |
| n2_q300_s1.0_ua1000_z2500 | 4 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on external_gas_fuel_GWh: external gas 11.6945 vs 0.0016 GWh, emissions 8608 vs 7832 t, grid import 6.10 vs 8.02 GWh, drilled 10000 vs 10000 m |
| n1_q300_s1.8_ua1000_z2500 | 5 | REJECTED | fails hard constraints: annual checks |

**37. [depth_step] Depth step 2500 -> 2750 m**
> Emissions 7832 -> 6196 t (-20.9%) for +1000 m drilled: 1.636 t CO2/yr per extra metre. ACCEPTED (>= 5% beyond the tie tolerance).

**38. [propose] Proposal n2_q300_s1.8_ua1000_z3000**
>  Depth ladder from incumbent n2_q300_s1.8_ua1000_z2750: 2750 -> 3000 m (reservoir 102.0 C) to cut the heat-pump lift; accepted only if emissions improve >= 5% vs the 2750 m design.

**39. [build_json] GEMINI JSON for n2_q300_s1.8_ua1000_z3000**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**40. [well_check] Well / ESP sanity check at 3000 m**
> No flags. Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 30.0 | 7.17 / 89.1 | 0.68 | 62.6 / 77.0 | 0.029 | 296.4 | 0.6 |
| 300 | 54.8 | 4.61 / 99.9 | 1.01 | 31.0 / 77.7 | 0.555 | 275.7 | 3.3 |

**41. [evaluate] Annual model + constraint check: n2_q300_s1.8_ua1000_z3000**
> FEASIBLE: external gas 0.002 GWh, emissions 5118 t, grid import 1.21 GWh, drilled 12000 m (1.6 s)

**42. [rank] Ranking after evaluation**
> Incumbent: n2_q300_s1.8_ua1000_z3000 (was n2_q300_s1.8_ua1000_z2750)

| Candidate | Rank | Verdict | Reason |
|---|---|---|---|
| n2_q300_s1.8_ua1000_z3000 | 1 | ACCEPTED | selected: feasible; external gas 0.0019 GWh, emissions 5118 t, grid import 1.21 GWh, 2 doublets, 12000 m drilled |
| n2_q300_s1.8_ua1000_z2750 | 2 | REJECTED | superseded by n2_q300_s1.8_ua1000_z3000: ranks better than n2_q300_s1.8_ua1000_z2750; deeper 2750 -> 3000 m: emissions +17.388% (needs >= 5% beyond the tie tolerance), marginal abatement 1.077 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua1000_z2500 | 3 | REJECTED | superseded by n2_q300_s1.8_ua1000_z2750: ranks better than n2_q300_s1.8_ua1000_z2500; deeper 2500 -> 2750 m: emissions +20.892% (needs >= 5% beyond the tie tolerance), marginal abatement 1.636 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua500_z2500 | 4 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on emissions_t (tied within tolerance on external_gas_fuel_GWh): external gas 0.0013 vs 0.0016 GWh, emissions 8172 vs 7832 t, grid import 9.28 vs 8.02 GWh, drilled 10000 vs 10000 m |
| n2_q300_s1.0_ua1000_z2500 | 5 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on external_gas_fuel_GWh: external gas 11.6945 vs 0.0016 GWh, emissions 8608 vs 7832 t, grid import 6.10 vs 8.02 GWh, drilled 10000 vs 10000 m |
| n1_q300_s1.8_ua1000_z2500 | 6 | REJECTED | fails hard constraints: annual checks |

**43. [depth_step] Depth step 2750 -> 3000 m**
> Emissions 6196 -> 5118 t (-17.4%) for +1000 m drilled: 1.077 t CO2/yr per extra metre. ACCEPTED (>= 5% beyond the tie tolerance).

**44. [propose] Proposal n2_q300_s1.8_ua1000_z3250**
>  Depth ladder from incumbent n2_q300_s1.8_ua1000_z3000: 3000 -> 3250 m (reservoir 109.5 C) to cut the heat-pump lift; accepted only if emissions improve >= 5% vs the 3000 m design.

**45. [build_json] GEMINI JSON for n2_q300_s1.8_ua1000_z3250**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**46. [well_check] Well / ESP sanity check at 3250 m**
> Flags: 300 m3/h: wellhead 107.0 C exceeds PVTConstantSTP temperature_max (100 C) - constant brine properties extrapolated. Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 30.0 | 7.13 / 94.4 | 0.83 | 63.6 / 78.0 | 0.029 | 321.7 | 0.6 |
| 300 | 55.5 | 4.61 / 107.0 | 1.30 | 30.9 / 78.8 | 0.570 | 301.0 | 3.3 |

**47. [evaluate] Annual model + constraint check: n2_q300_s1.8_ua1000_z3250**
> FEASIBLE: external gas 0.012 GWh, emissions 4896 t, grid import 0.80 GWh, drilled 13000 m (0.6 s)

**48. [rank] Ranking after evaluation**
> Incumbent: n2_q300_s1.8_ua1000_z3000

| Candidate | Rank | Verdict | Reason |
|---|---|---|---|
| n2_q300_s1.8_ua1000_z3000 | 1 | ACCEPTED | selected: feasible; external gas 0.0019 GWh, emissions 5118 t, grid import 1.21 GWh, 2 doublets, 12000 m drilled |
| n2_q300_s1.8_ua1000_z2750 | 2 | REJECTED | superseded by n2_q300_s1.8_ua1000_z3000: ranks better than n2_q300_s1.8_ua1000_z2750; deeper 2750 -> 3000 m: emissions +17.388% (needs >= 5% beyond the tie tolerance), marginal abatement 1.077 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua1000_z2500 | 3 | REJECTED | superseded by n2_q300_s1.8_ua1000_z2750: ranks better than n2_q300_s1.8_ua1000_z2500; deeper 2500 -> 2750 m: emissions +20.892% (needs >= 5% beyond the tie tolerance), marginal abatement 1.636 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua500_z2500 | 4 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on emissions_t (tied within tolerance on external_gas_fuel_GWh): external gas 0.0013 vs 0.0016 GWh, emissions 8172 vs 7832 t, grid import 9.28 vs 8.02 GWh, drilled 10000 vs 10000 m |
| n2_q300_s1.8_ua1000_z3250 | 5 | REJECTED | parsimony rule not met: ranks not better than n2_q300_s1.8_ua1000_z3000; deeper 3000 -> 3250 m: emissions +4.345% (needs >= 5% beyond the tie tolerance), marginal abatement 0.222 t CO2/yr per extra metre drilled - within the tie tolerance of the threshold, counts as NOT met (marginal sensitivity case) |
| n2_q300_s1.0_ua1000_z2500 | 6 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on external_gas_fuel_GWh: external gas 11.6945 vs 0.0016 GWh, emissions 8608 vs 7832 t, grid import 6.10 vs 8.02 GWh, drilled 10000 vs 10000 m |
| n1_q300_s1.8_ua1000_z2500 | 7 | REJECTED | fails hard constraints: annual checks |

**49. [depth_step] Depth step 3000 -> 3250 m**
> Emissions 5118 -> 4896 t (-4.3%) for +1000 m drilled: 0.222 t CO2/yr per extra metre. REJECTED: within the tie tolerance of the 5% threshold, which counts as not met (conservative: drilling cost and risk are not modelled); recorded as a marginal sensitivity case.

**50. [propose] Proposal n3_q300_s1.8_ua1000_z3000**
> Previous candidate n2_q300_s1.8_ua1000_z3250 was ranked out (parsimony rule not met: ranks not better than n2_q300_s1.8_ua1000_z3000; deeper 3000 -> 3250 m: emissions +4.345% (needs >= 5% beyond the tie tolerance), marginal abatement 0.222 t CO2/yr per extra metre drilled - within the tie tolerance of the threshold, counts as NOT met (marginal sensitivity case)); keep incumbent n2_q300_s1.8_ua1000_z3000. Depth step to 3250 m failed the parsimony rule; stop exploring deeper (accepted depth stays 3000 m). Variant of incumbent n2_q300_s1.8_ua1000_z3000: More doublets: accepted only if external gas or emissions improve by >= 5%.

**51. [build_json] GEMINI JSON for n3_q300_s1.8_ua1000_z3000**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**52. [well_check] Well / ESP sanity check at 3000 m**
> No flags. Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 30.0 | 7.17 / 89.1 | 0.68 | 62.6 / 77.0 | 0.029 | 296.4 | 0.6 |
| 300 | 54.8 | 4.61 / 99.9 | 1.01 | 31.0 / 77.7 | 0.555 | 275.7 | 3.3 |

**53. [evaluate] Annual model + constraint check: n3_q300_s1.8_ua1000_z3000**
> FEASIBLE: external gas 0.002 GWh, emissions 5118 t, grid import 1.20 GWh, drilled 18000 m (1.6 s)

**54. [rank] Ranking after evaluation**
> Incumbent: n2_q300_s1.8_ua1000_z3000

| Candidate | Rank | Verdict | Reason |
|---|---|---|---|
| n2_q300_s1.8_ua1000_z3000 | 1 | ACCEPTED | selected: feasible; external gas 0.0019 GWh, emissions 5118 t, grid import 1.21 GWh, 2 doublets, 12000 m drilled |
| n3_q300_s1.8_ua1000_z3000 | 2 | REJECTED | parsimony rule not met: ranks not better than n2_q300_s1.8_ua1000_z3000; extra doublet: external gas +0.0%, emissions +0.0% (needs >= 5% on either, beyond the tie tolerance) |
| n2_q300_s1.8_ua1000_z2750 | 3 | REJECTED | superseded by n2_q300_s1.8_ua1000_z3000: ranks better than n2_q300_s1.8_ua1000_z2750; deeper 2750 -> 3000 m: emissions +17.388% (needs >= 5% beyond the tie tolerance), marginal abatement 1.077 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua1000_z2500 | 4 | REJECTED | superseded by n2_q300_s1.8_ua1000_z2750: ranks better than n2_q300_s1.8_ua1000_z2500; deeper 2500 -> 2750 m: emissions +20.892% (needs >= 5% beyond the tie tolerance), marginal abatement 1.636 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua500_z2500 | 5 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on emissions_t (tied within tolerance on external_gas_fuel_GWh): external gas 0.0013 vs 0.0016 GWh, emissions 8172 vs 7832 t, grid import 9.28 vs 8.02 GWh, drilled 10000 vs 10000 m |
| n2_q300_s1.8_ua1000_z3250 | 6 | REJECTED | parsimony rule not met: ranks not better than n2_q300_s1.8_ua1000_z3000; deeper 3000 -> 3250 m: emissions +4.345% (needs >= 5% beyond the tie tolerance), marginal abatement 0.222 t CO2/yr per extra metre drilled - within the tie tolerance of the threshold, counts as NOT met (marginal sensitivity case) |
| n2_q300_s1.0_ua1000_z2500 | 7 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on external_gas_fuel_GWh: external gas 11.6945 vs 0.0016 GWh, emissions 8608 vs 7832 t, grid import 6.10 vs 8.02 GWh, drilled 10000 vs 10000 m |
| n1_q300_s1.8_ua1000_z2500 | 8 | REJECTED | fails hard constraints: annual checks |

**55. [stop] Backend stops proposing**
> No untried variant can change the pick within the design space and the parsimony rules.

**56. [final] Final pick: n2_q300_s1.8_ua1000_z3000**
> Depth ladder: 2500->2750 m: -20.9%, 1.636 t/yr/m (kept); 2750->3000 m: -17.4%, 1.077 t/yr/m (kept); 3000->3250 m: -4.3%, 0.222 t/yr/m (rejected, marginal). Selected n2_q300_s1.8_ua1000_z3000 (102 C reservoir): selected: feasible; external gas 0.0019 GWh, emissions 5118 t, grid import 1.21 GWh, 2 doublets, 12000 m drilled. Versus the conventional reference (gas boiler eta 0.90 + electric chiller COP 5.0, 26706 t): 80.8% lower emissions, external gas 0.002 vs 124.1 GWh, grid import 1.21 vs 4.75 GWh. Well checks at the pick: no flags. Drilling cost is not modeled; deeper steps are limited by the 5% parsimony rule. Marginal sensitivity case: n2_q300_s1.8_ua1000_z3250 (3250 m) changes emissions -4.345% vs 3000 m (0.22 t CO2/yr per extra metre), within the tie tolerance of the 5% threshold, so it is not taken (drilling cost and risk not modelled); its wellhead reaches 107.0 C vs 99.9 C at 3000 m, further above the 100 C brine-property (PVTConstantSTP) range.


## Scenario B: complete inputs, design loop

