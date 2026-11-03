# Design agent trace (rules backend, interactive)

Generated 2026-11-03 06:13 UTC from `decision_log.jsonl` (66 logged steps). Rerun: `$env:PYTHONPATH="src"; py -3.11 -m poetry run python hackathon_work/design_agent.py --backend rules`.

## Judges' agent-reasoning tests

| Test | Result | Evidence |
|---|---|---|
| (i) missing physical quantity -> stop and ask | PASS | step 4 AGENT ASKED: I cannot size the plant without the heating return temperature. It is needed because it sets district water flow = Q / (cp * (100 - T_return)) and the HEX/heat-pump lift. It is not in the organizers' inputs and I will not invent it. Please type a value in C (plausible range 40-80 C), or 'q' to stop. -> step 9 USER ANSWERED '60': accepted, 60 C. |
| (ii) >= 350 m3/h per doublet -> rejected with reason, revised | PASS | step 13: 650.00 m3/h exceeds the 300 m3/h hard cap -> step 14: Revised to n1_q300_s1.8_ua1000_z2500 |
| (iii) 87 C reservoir vs 100 C supply -> shortfall stated, deeper well vs surface upgrade decided | PASS | step 11 (assessment); candidates evaluated at reservoir temperatures [87.0, 94.5, 102.0, 109.5, 117.0] C; step 66 (decision) |
| (iv) recovery after a failed / ranked-out candidate | PASS | step 17: Annual model + constraint check: n1_q300_s1.8_ua1000_z2500 infeasible (never_all_off) -> step 24: Annual model + constraint check: n2_q300_s1.8_ua1000_z2500 feasible; ranked-out recoveries at steps [31, 36, 60] |

## Evaluations (scenario A)

| # | Candidate | T_res (C) | ESP set (m) / intake (bar) | Feasible | External gas (GWh) | Emissions (t) | Grid import (GWh) | Drilled (m) | Wall (s) | Final verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | n1_q300_s1.8_ua1000_z2500 | 87 | 660 / 30.3 | no (never_all_off) | 28.597 | 12968 | 11.91 | 5000 | 0.8 | REJECTED (rank 9) |
| 2 | n2_q300_s1.8_ua1000_z2500 | 87 | 660 / 30.3 | yes | 0.002 | 8908 | 12.01 | 10000 | 0.8 | REJECTED (rank 5) |
| 3 | n2_q300_s1.8_ua500_z2500 | 87 | 660 / 30.3 | yes | 0.008 | 9036 | 12.50 | 10000 | 0.8 | REJECTED (rank 7) |
| 4 | n2_q300_s1.0_ua1000_z2500 | 87 | 530 / 30.7 | yes | 8.090 | 9429 | 11.49 | 10000 | 0.8 | REJECTED (rank 8) |
| 5 | n2_q300_s1.8_ua1000_z2750 | 94 | 670 / 30.1 | yes | 0.006 | 7267 | 7.83 | 11000 | 0.9 | REJECTED (rank 4) |
| 6 | n2_q300_s1.8_ua1000_z3000 | 102 | 690 / 31.0 | yes | 0.004 | 6038 | 4.66 | 12000 | 0.8 | REJECTED (rank 3) |
| 7 | n2_q300_s1.8_ua1000_z3250 | 110 | 700 / 30.9 | yes | 0.004 | 5148 | 1.84 | 13000 | 4.0 | ACCEPTED (rank 1) |
| 8 | n2_q300_s1.8_ua1000_z3500 | 117 | 710 / 30.7 | yes | 0.016 | 4891 | 0.80 | 14000 | 1.4 | REJECTED (rank 6) |
| 9 | n3_q300_s1.8_ua1000_z3250 | 110 | 700 / 30.9 | yes | 0.004 | 5148 | 1.84 | 19500 | 3.9 | REJECTED (rank 2) |

## Final pick

Depth ladder: 2500->2750 m: -18.4%, 1.641 t/yr/m (kept); 2750->3000 m: -16.9%, 1.229 t/yr/m (kept); 3000->3250 m: -14.7%, 0.890 t/yr/m (kept); 3250->3500 m: -5.0%, 0.257 t/yr/m (rejected, marginal). Selected n2_q300_s1.8_ua1000_z3250 (110 C reservoir): selected: feasible; external gas 0.0038 GWh, emissions 5148 t, grid import 1.84 GWh, 2 doublets, 13000 m drilled. Versus the conventional reference (gas boiler eta 0.90 + electric chiller COP 5.0, 26706 t): 80.7% lower emissions, external gas 0.004 vs 124.1 GWh, grid import 1.84 vs 4.75 GWh. Well checks at the pick: 300 m3/h: wellhead 107.0 C exceeds PVTConstantSTP temperature_max (100 C) - constant brine properties extrapolated. Drilling cost is not modeled; deeper steps are limited by the 5% parsimony rule. Marginal sensitivity case: n2_q300_s1.8_ua1000_z3500 (3500 m) changes emissions -4.994% vs 3250 m (0.26 t CO2/yr per extra metre), within the tie tolerance of the 5% threshold, so it is not taken (drilling cost and risk not modelled); its wellhead reaches 114.1 C vs 107.0 C at 3250 m, further above the 100 C brine-property (PVTConstantSTP) range.

## Marginal sensitivity cases

Rejected only because the step improvement is within the tie tolerance of the 5% threshold, which counts as not met (conservative: drilling cost and risk are not modelled).

| Candidate | Step | Emissions change | Abatement (t/yr per m) | Wellhead T max (C) |
|---|---|---|---|---|
| n2_q300_s1.8_ua1000_z3500 | 3250 -> 3500 m | -4.994% | 0.26 | 114.1 (vs 107.0; PVT range <= 100) |

## Runtime

- Annual evaluations: 9 (9 computed, 0 from cache); computed wall time mean 1.6 s, max 4.0 s
- Scenario B runtime: 14.3 s; scenario A runtime: 14.3 s
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

**4. AGENT ASKED** (2026-11-03 06:12:56 UTC)
> I cannot size the plant without the heating return temperature. It is needed because it sets district water flow = Q / (cp * (100 - T_return)) and the HEX/heat-pump lift. It is not in the organizers' inputs and I will not invent it. Please type a value in C (plausible range 40-80 C), or 'q' to stop.

**5. USER ANSWERED** (2026-11-03 06:12:56 UTC)
> 'abc': rejected - it is not a number (expected e.g. 60 for 60 C)

**6. AGENT ASKED** (2026-11-03 06:12:56 UTC)
> I cannot size the plant without the heating return temperature. It is needed because it sets district water flow = Q / (cp * (100 - T_return)) and the HEX/heat-pump lift. It is not in the organizers' inputs and I will not invent it. Please type a value in C (plausible range 40-80 C), or 'q' to stop.

**7. USER ANSWERED** (2026-11-03 06:12:56 UTC)
> '95': rejected - 95 C is outside the plausible 40-80 C range (a district heating return for a 100 C supply is typically 40-80 C: below 40 C is atypical for a 100 C network, above 80 C leaves less than 20 K for the district water and the HEX/heat-pump lift)

**8. AGENT ASKED** (2026-11-03 06:12:56 UTC)
> I cannot size the plant without the heating return temperature. It is needed because it sets district water flow = Q / (cp * (100 - T_return)) and the HEX/heat-pump lift. It is not in the organizers' inputs and I will not invent it. Please type a value in C (plausible range 40-80 C), or 'q' to stop.

**9. USER ANSWERED** (2026-11-03 06:12:56 UTC)
> '60': accepted, 60 C.

**10. [required_inputs] Check required inputs**
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

**11. [temperature_assessment] Source temperature vs 100 C supply**
> Reservoir at 2500 m is 87.0 C, 13.0 K below the fixed 100 C supply before any losses, so a HEX alone cannot supply 100 C. Options: (a) deeper well - T_res = 100 C needs 2933 m, and direct HEX supply (T_res >= 107.4 C incl. 5 K approach, 0.4 K surface drops, ~2 K wellbore loss) needs ~3180 m; (b) surface upgrade - heat pump on the brine leaving the HEX plus CHP on the produced gas. Decision: start with (b) at the official 2500 m (no extrapolated reservoir data, least drilling), then climb a 250 m depth ladder (max 4000 m) and keep each step only if emissions fall >= 5%; the ranking decides with numbers.

**12. [propose] Proposal n1_q650_s1.8_ua1000_z2500**
> Start with the fewest doublets (1): the ranking prefers fewer doublets, so the smallest plant that passes the hard constraints is the target. Flow sizing heuristic: peak 30.0 MW / 1 doublet(s) at the 40 K brine cap -> 639.4 m3/h per doublet, rounded up to 650 m3/h. Largest ESP (s = 1.8), HEX 1000 kW/K, official 2500 m reservoir.

**13. [validate] Rejected before simulation: n1_q650_s1.8_ua1000_z2500**
> 650.00 m3/h exceeds the 300 m3/h hard cap

**14. [revise] Revised to n1_q300_s1.8_ua1000_z2500**
> Clip to the nearest admissible value: flow_cap_m3h 650 -> 300 (650.00 m3/h exceeds the 300 m3/h hard cap). The proposal's intent (largest admissible flow) is kept; the shortfall is left to the heat pump / CHP and to more doublets if needed.

**15. [build_json] GEMINI JSON for n1_q300_s1.8_ua1000_z2500**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**16. [well_check] Well / ESP sanity check at 2500 m**
> No flags. Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 30.0 | 7.24 / 78.1 | 0.44 | 59.7 / 74.0 | 0.029 | 245.9 | 0.6 |
| 300 | 53.4 | 4.61 / 85.5 | 0.59 | 30.3 / 74.5 | 0.526 | 225.2 | 3.3 |

**17. [evaluate] Annual model + constraint check: n1_q300_s1.8_ua1000_z2500**
> INFEASIBLE: external gas 28.597 GWh, emissions 12968 t, grid import 11.91 GWh, drilled 5000 m; fails never_all_off (0.8 s)

**18. [rank] Ranking after evaluation**
> No feasible candidate yet.

| Candidate | Rank | Verdict | Reason |
|---|---|---|---|
| n1_q300_s1.8_ua1000_z2500 | 1 | REJECTED | fails hard constraints: annual checks |

**19. [propose] Proposal n2_q350_s1.8_ua1000_z2500**
> Recovery: n1_q300_s1.8_ua1000_z2500 failed (never_all_off). With 1 doublet(s) the 35-day maintenance window leaves the plant without geothermal supply, which the 'never all off' interpretation forbids; add a doublet so maintenance can be staggered. Flow sizing heuristic: peak 30.0 MW / 2 doublet(s) at the 40 K brine cap -> 319.7 m3/h per doublet, rounded up to 350 m3/h. Largest ESP (s = 1.8), HEX 1000 kW/K, official 2500 m reservoir.

**20. [validate] Rejected before simulation: n2_q350_s1.8_ua1000_z2500**
> 350.00 m3/h exceeds the 300 m3/h hard cap

**21. [revise] Revised to n2_q300_s1.8_ua1000_z2500**
> Clip to the nearest admissible value: flow_cap_m3h 350 -> 300 (350.00 m3/h exceeds the 300 m3/h hard cap). The proposal's intent (largest admissible flow) is kept; the shortfall is left to the heat pump / CHP and to more doublets if needed.

**22. [build_json] GEMINI JSON for n2_q300_s1.8_ua1000_z2500**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**23. [well_check] Well / ESP sanity check at 2500 m**
> No flags. Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 30.0 | 7.24 / 78.1 | 0.44 | 59.7 / 74.0 | 0.029 | 245.9 | 0.6 |
| 300 | 53.4 | 4.61 / 85.5 | 0.59 | 30.3 / 74.5 | 0.526 | 225.2 | 3.3 |

**24. [evaluate] Annual model + constraint check: n2_q300_s1.8_ua1000_z2500**
> FEASIBLE: external gas 0.002 GWh, emissions 8908 t, grid import 12.01 GWh, drilled 10000 m (0.8 s)

**25. [rank] Ranking after evaluation**
> Incumbent: n2_q300_s1.8_ua1000_z2500

| Candidate | Rank | Verdict | Reason |
|---|---|---|---|
| n2_q300_s1.8_ua1000_z2500 | 1 | ACCEPTED | selected: feasible; external gas 0.0020 GWh, emissions 8908 t, grid import 12.01 GWh, 2 doublets, 10000 m drilled |
| n1_q300_s1.8_ua1000_z2500 | 2 | REJECTED | fails hard constraints: annual checks |

**26. [propose] Proposal n2_q300_s1.8_ua500_z2500**
> Variant of incumbent n2_q300_s1.8_ua1000_z2500: Smaller HEX (500 kW/K, lower cost): check whether the heat pump can absorb the lost HEX duty without external gas.

**27. [build_json] GEMINI JSON for n2_q300_s1.8_ua500_z2500**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**28. [well_check] Well / ESP sanity check at 2500 m**
> No flags. Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 30.0 | 7.24 / 78.1 | 0.44 | 59.7 / 74.0 | 0.029 | 245.9 | 0.6 |
| 300 | 53.4 | 4.61 / 85.5 | 0.59 | 30.3 / 74.5 | 0.526 | 225.2 | 3.3 |

**29. [evaluate] Annual model + constraint check: n2_q300_s1.8_ua500_z2500**
> FEASIBLE: external gas 0.008 GWh, emissions 9036 t, grid import 12.50 GWh, drilled 10000 m (0.8 s)

**30. [rank] Ranking after evaluation**
> Incumbent: n2_q300_s1.8_ua1000_z2500

| Candidate | Rank | Verdict | Reason |
|---|---|---|---|
| n2_q300_s1.8_ua1000_z2500 | 1 | ACCEPTED | selected: feasible; external gas 0.0020 GWh, emissions 8908 t, grid import 12.01 GWh, 2 doublets, 10000 m drilled |
| n2_q300_s1.8_ua500_z2500 | 2 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on emissions_t (tied within tolerance on external_gas_fuel_GWh): external gas 0.0079 vs 0.0020 GWh, emissions 9036 vs 8908 t, grid import 12.50 vs 12.01 GWh, drilled 10000 vs 10000 m |
| n1_q300_s1.8_ua1000_z2500 | 3 | REJECTED | fails hard constraints: annual checks |

**31. [propose] Proposal n2_q300_s1.0_ua1000_z2500**
> Previous candidate n2_q300_s1.8_ua500_z2500 was ranked out (same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on emissions_t (tied within tolerance on external_gas_fuel_GWh): external gas 0.0079 vs 0.0020 GWh, emissions 9036 vs 8908 t, grid import 12.50 vs 12.01 GWh, drilled 10000 vs 10000 m); keep incumbent n2_q300_s1.8_ua1000_z2500. Variant of incumbent n2_q300_s1.8_ua1000_z2500: Smaller ESP (s = 1.0, the GEMINI example pump): cheaper, but capped at ~176 m3/h; check the effect on external gas.

**32. [build_json] GEMINI JSON for n2_q300_s1.0_ua1000_z2500**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**33. [well_check] Well / ESP sanity check at 2500 m**
> Flags: 195 m3/h: ESP at 69.7 Hz, within 2 Hz of the drive limit; ESP reaches only 195 of the 300 m3/h cap at this depth. Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 39.5 | 3.00 / 78.1 | 0.44 | 46.5 / 56.6 | 0.020 | 245.9 | 0.6 |
| 195 | 69.7 | 3.34 / 84.7 | 0.57 | 30.7 / 58.0 | 0.211 | 233.9 | 2.2 |

**34. [evaluate] Annual model + constraint check: n2_q300_s1.0_ua1000_z2500**
> FEASIBLE: external gas 8.090 GWh, emissions 9429 t, grid import 11.49 GWh, drilled 10000 m (0.8 s)

**35. [rank] Ranking after evaluation**
> Incumbent: n2_q300_s1.8_ua1000_z2500

| Candidate | Rank | Verdict | Reason |
|---|---|---|---|
| n2_q300_s1.8_ua1000_z2500 | 1 | ACCEPTED | selected: feasible; external gas 0.0020 GWh, emissions 8908 t, grid import 12.01 GWh, 2 doublets, 10000 m drilled |
| n2_q300_s1.8_ua500_z2500 | 2 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on emissions_t (tied within tolerance on external_gas_fuel_GWh): external gas 0.0079 vs 0.0020 GWh, emissions 9036 vs 8908 t, grid import 12.50 vs 12.01 GWh, drilled 10000 vs 10000 m |
| n2_q300_s1.0_ua1000_z2500 | 3 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on external_gas_fuel_GWh: external gas 8.0904 vs 0.0020 GWh, emissions 9429 vs 8908 t, grid import 11.49 vs 12.01 GWh, drilled 10000 vs 10000 m |
| n1_q300_s1.8_ua1000_z2500 | 4 | REJECTED | fails hard constraints: annual checks |

**36. [propose] Proposal n2_q300_s1.8_ua1000_z2750**
> Previous candidate n2_q300_s1.0_ua1000_z2500 was ranked out (same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on external_gas_fuel_GWh: external gas 8.0904 vs 0.0020 GWh, emissions 9429 vs 8908 t, grid import 11.49 vs 12.01 GWh, drilled 10000 vs 10000 m); keep incumbent n2_q300_s1.8_ua1000_z2500. Depth ladder from incumbent n2_q300_s1.8_ua1000_z2500: 2500 -> 2750 m (reservoir 94.5 C) to cut the heat-pump lift; accepted only if emissions improve >= 5% vs the 2500 m design.

**37. [build_json] GEMINI JSON for n2_q300_s1.8_ua1000_z2750**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**38. [well_check] Well / ESP sanity check at 2750 m**
> No flags. Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 30.0 | 7.20 / 83.7 | 0.55 | 60.6 / 75.0 | 0.029 | 271.1 | 0.6 |
| 300 | 54.1 | 4.61 / 92.7 | 0.78 | 30.1 / 75.6 | 0.541 | 250.5 | 3.3 |

**39. [evaluate] Annual model + constraint check: n2_q300_s1.8_ua1000_z2750**
> FEASIBLE: external gas 0.006 GWh, emissions 7267 t, grid import 7.83 GWh, drilled 11000 m (0.9 s)

**40. [rank] Ranking after evaluation**
> Incumbent: n2_q300_s1.8_ua1000_z2750 (was n2_q300_s1.8_ua1000_z2500)

| Candidate | Rank | Verdict | Reason |
|---|---|---|---|
| n2_q300_s1.8_ua1000_z2750 | 1 | ACCEPTED | selected: feasible; external gas 0.0061 GWh, emissions 7267 t, grid import 7.83 GWh, 2 doublets, 11000 m drilled |
| n2_q300_s1.8_ua1000_z2500 | 2 | REJECTED | superseded by n2_q300_s1.8_ua1000_z2750: ranks better than n2_q300_s1.8_ua1000_z2500; deeper 2500 -> 2750 m: emissions +18.422% (needs >= 5% beyond the tie tolerance), marginal abatement 1.641 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua500_z2500 | 3 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on emissions_t (tied within tolerance on external_gas_fuel_GWh): external gas 0.0079 vs 0.0020 GWh, emissions 9036 vs 8908 t, grid import 12.50 vs 12.01 GWh, drilled 10000 vs 10000 m |
| n2_q300_s1.0_ua1000_z2500 | 4 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on external_gas_fuel_GWh: external gas 8.0904 vs 0.0020 GWh, emissions 9429 vs 8908 t, grid import 11.49 vs 12.01 GWh, drilled 10000 vs 10000 m |
| n1_q300_s1.8_ua1000_z2500 | 5 | REJECTED | fails hard constraints: annual checks |

**41. [depth_step] Depth step 2500 -> 2750 m**
> Emissions 8908 -> 7267 t (-18.4%) for +1000 m drilled: 1.641 t CO2/yr per extra metre. ACCEPTED (>= 5% beyond the tie tolerance).

**42. [propose] Proposal n2_q300_s1.8_ua1000_z3000**
>  Depth ladder from incumbent n2_q300_s1.8_ua1000_z2750: 2750 -> 3000 m (reservoir 102.0 C) to cut the heat-pump lift; accepted only if emissions improve >= 5% vs the 2750 m design.

**43. [build_json] GEMINI JSON for n2_q300_s1.8_ua1000_z3000**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**44. [well_check] Well / ESP sanity check at 3000 m**
> No flags. Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 30.0 | 7.17 / 89.1 | 0.68 | 62.6 / 77.0 | 0.029 | 296.4 | 0.6 |
| 300 | 54.8 | 4.61 / 99.9 | 1.01 | 31.0 / 77.7 | 0.555 | 275.7 | 3.3 |

**45. [evaluate] Annual model + constraint check: n2_q300_s1.8_ua1000_z3000**
> FEASIBLE: external gas 0.004 GWh, emissions 6038 t, grid import 4.66 GWh, drilled 12000 m (0.8 s)

**46. [rank] Ranking after evaluation**
> Incumbent: n2_q300_s1.8_ua1000_z3000 (was n2_q300_s1.8_ua1000_z2750)

| Candidate | Rank | Verdict | Reason |
|---|---|---|---|
| n2_q300_s1.8_ua1000_z3000 | 1 | ACCEPTED | selected: feasible; external gas 0.0044 GWh, emissions 6038 t, grid import 4.66 GWh, 2 doublets, 12000 m drilled |
| n2_q300_s1.8_ua1000_z2750 | 2 | REJECTED | superseded by n2_q300_s1.8_ua1000_z3000: ranks better than n2_q300_s1.8_ua1000_z2750; deeper 2750 -> 3000 m: emissions +16.910% (needs >= 5% beyond the tie tolerance), marginal abatement 1.229 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua1000_z2500 | 3 | REJECTED | superseded by n2_q300_s1.8_ua1000_z2750: ranks better than n2_q300_s1.8_ua1000_z2500; deeper 2500 -> 2750 m: emissions +18.422% (needs >= 5% beyond the tie tolerance), marginal abatement 1.641 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua500_z2500 | 4 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on emissions_t (tied within tolerance on external_gas_fuel_GWh): external gas 0.0079 vs 0.0020 GWh, emissions 9036 vs 8908 t, grid import 12.50 vs 12.01 GWh, drilled 10000 vs 10000 m |
| n2_q300_s1.0_ua1000_z2500 | 5 | REJECTED | same doublet count and depth as n2_q300_s1.8_ua1000_z2500 but ranks lower on external_gas_fuel_GWh: external gas 8.0904 vs 0.0020 GWh, emissions 9429 vs 8908 t, grid import 11.49 vs 12.01 GWh, drilled 10000 vs 10000 m |
| n1_q300_s1.8_ua1000_z2500 | 6 | REJECTED | fails hard constraints: annual checks |

**47. [depth_step] Depth step 2750 -> 3000 m**
> Emissions 7267 -> 6038 t (-16.9%) for +1000 m drilled: 1.229 t CO2/yr per extra metre. ACCEPTED (>= 5% beyond the tie tolerance).

**48. [propose] Proposal n2_q300_s1.8_ua1000_z3250**
>  Depth ladder from incumbent n2_q300_s1.8_ua1000_z3000: 3000 -> 3250 m (reservoir 109.5 C) to cut the heat-pump lift; accepted only if emissions improve >= 5% vs the 3000 m design.

**49. [build_json] GEMINI JSON for n2_q300_s1.8_ua1000_z3250**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**50. [well_check] Well / ESP sanity check at 3250 m**
> Flags: 300 m3/h: wellhead 107.0 C exceeds PVTConstantSTP temperature_max (100 C) - constant brine properties extrapolated. Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 30.0 | 7.13 / 94.4 | 0.83 | 63.6 / 78.0 | 0.029 | 321.7 | 0.6 |
| 300 | 55.5 | 4.61 / 107.0 | 1.30 | 30.9 / 78.8 | 0.570 | 301.0 | 3.3 |

**51. [evaluate] Annual model + constraint check: n2_q300_s1.8_ua1000_z3250**
> FEASIBLE: external gas 0.004 GWh, emissions 5148 t, grid import 1.84 GWh, drilled 13000 m (4.0 s)

**52. [rank] Ranking after evaluation**
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

**53. [depth_step] Depth step 3000 -> 3250 m**
> Emissions 6038 -> 5148 t (-14.7%) for +1000 m drilled: 0.890 t CO2/yr per extra metre. ACCEPTED (>= 5% beyond the tie tolerance).

**54. [propose] Proposal n2_q300_s1.8_ua1000_z3500**
>  Depth ladder from incumbent n2_q300_s1.8_ua1000_z3250: 3250 -> 3500 m (reservoir 117.0 C) to cut the heat-pump lift; accepted only if emissions improve >= 5% vs the 3250 m design.

**55. [build_json] GEMINI JSON for n2_q300_s1.8_ua1000_z3500**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**56. [well_check] Well / ESP sanity check at 3500 m**
> Flags: 300 m3/h: wellhead 114.1 C exceeds PVTConstantSTP temperature_max (100 C) - constant brine properties extrapolated. Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 30.0 | 7.09 / 99.5 | 1.00 | 64.6 / 78.9 | 0.029 | 346.9 | 0.6 |
| 300 | 56.2 | 4.61 / 114.1 | 1.64 | 30.7 / 79.8 | 0.584 | 326.2 | 3.3 |

**57. [evaluate] Annual model + constraint check: n2_q300_s1.8_ua1000_z3500**
> FEASIBLE: external gas 0.016 GWh, emissions 4891 t, grid import 0.80 GWh, drilled 14000 m (1.4 s)

**58. [rank] Ranking after evaluation**
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

**59. [depth_step] Depth step 3250 -> 3500 m**
> Emissions 5148 -> 4891 t (-5.0%) for +1000 m drilled: 0.257 t CO2/yr per extra metre. REJECTED: within the tie tolerance of the 5% threshold, which counts as not met (conservative: drilling cost and risk are not modelled); recorded as a marginal sensitivity case.

**60. [propose] Proposal n3_q300_s1.8_ua1000_z3250**
> Previous candidate n2_q300_s1.8_ua1000_z3500 was ranked out (parsimony rule not met: ranks not better than n2_q300_s1.8_ua1000_z3250; deeper 3250 -> 3500 m: emissions +4.994% (needs >= 5% beyond the tie tolerance), marginal abatement 0.257 t CO2/yr per extra metre drilled - within the tie tolerance of the threshold, counts as NOT met (marginal sensitivity case)); keep incumbent n2_q300_s1.8_ua1000_z3250. Depth step to 3500 m failed the parsimony rule; stop exploring deeper (accepted depth stays 3250 m). Variant of incumbent n2_q300_s1.8_ua1000_z3250: More doublets: accepted only if external gas or emissions improve by >= 5%.

**61. [build_json] GEMINI JSON for n3_q300_s1.8_ua1000_z3250**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**62. [well_check] Well / ESP sanity check at 3250 m**
> Flags: 300 m3/h: wellhead 107.0 C exceeds PVTConstantSTP temperature_max (100 C) - constant brine properties extrapolated. Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 30.0 | 7.13 / 94.4 | 0.83 | 63.6 / 78.0 | 0.029 | 321.7 | 0.6 |
| 300 | 55.5 | 4.61 / 107.0 | 1.30 | 30.9 / 78.8 | 0.570 | 301.0 | 3.3 |

**63. [evaluate] Annual model + constraint check: n3_q300_s1.8_ua1000_z3250**
> FEASIBLE: external gas 0.004 GWh, emissions 5148 t, grid import 1.84 GWh, drilled 19500 m (3.9 s)

**64. [rank] Ranking after evaluation**
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

**65. [stop] Backend stops proposing**
> No untried variant can change the pick within the design space and the parsimony rules.

**66. [final] Final pick: n2_q300_s1.8_ua1000_z3250**
> Depth ladder: 2500->2750 m: -18.4%, 1.641 t/yr/m (kept); 2750->3000 m: -16.9%, 1.229 t/yr/m (kept); 3000->3250 m: -14.7%, 0.890 t/yr/m (kept); 3250->3500 m: -5.0%, 0.257 t/yr/m (rejected, marginal). Selected n2_q300_s1.8_ua1000_z3250 (110 C reservoir): selected: feasible; external gas 0.0038 GWh, emissions 5148 t, grid import 1.84 GWh, 2 doublets, 13000 m drilled. Versus the conventional reference (gas boiler eta 0.90 + electric chiller COP 5.0, 26706 t): 80.7% lower emissions, external gas 0.004 vs 124.1 GWh, grid import 1.84 vs 4.75 GWh. Well checks at the pick: 300 m3/h: wellhead 107.0 C exceeds PVTConstantSTP temperature_max (100 C) - constant brine properties extrapolated. Drilling cost is not modeled; deeper steps are limited by the 5% parsimony rule. Marginal sensitivity case: n2_q300_s1.8_ua1000_z3500 (3500 m) changes emissions -4.994% vs 3250 m (0.26 t CO2/yr per extra metre), within the tie tolerance of the 5% threshold, so it is not taken (drilling cost and risk not modelled); its wellhead reaches 114.1 C vs 107.0 C at 3250 m, further above the 100 C brine-property (PVTConstantSTP) range.


## Scenario B: complete inputs, design loop

