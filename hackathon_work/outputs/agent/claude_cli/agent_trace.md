# Design agent trace (claude_cli backend)

Generated 2026-11-03 00:22 UTC from `decision_log.jsonl` (39 logged steps). Rerun: `$env:PYTHONPATH="src"; py -3.11 -m poetry run python hackathon_work/design_agent.py --backend claude_cli`.

## Judges' agent-reasoning tests

| Test | Result | Evidence |
|---|---|---|
| (i) missing physical quantity -> stop and ask | PASS | step 4: I cannot size the plant without: heating return temperature. 'heating return temperature' is needed because it sets district water flow = Q / (cp * (100 - T_return)) and the HEX/heat-pump lift. It is not in the organizers' inputs and I will not invent it. Please provide a value (previously approved: 60 C). |
| (ii) >= 350 m3/h per doublet -> rejected with reason, revised | FAIL | not triggered |
| (iii) 87 C reservoir vs 100 C supply -> shortfall stated, deeper well vs surface upgrade decided | PASS | step 8 (assessment); candidates evaluated at reservoir temperatures [87.0, 94.5, 102.0, 109.5, 117.0] C; step 39 (decision) |
| (iv) recovery after a failed / ranked-out candidate | FAIL | not triggered |

## Evaluations (scenario B)

| # | Candidate | T_res (C) | Feasible | External gas (GWh) | Emissions (t) | Grid import (GWh) | Drilled (m) | Wall (s) | Final verdict |
|---|---|---|---|---|---|---|---|---|---|
| 1 | n2_q300_s1.8_ua1000_z2500 | 87 | yes | 0.004 | 9011 | 12.39 | 10000 | 0.1 (cached) | REJECTED (rank 4) |
| 2 | n2_q300_s1.8_ua1000_z2750 | 94 | yes | 0.002 | 7342 | 8.15 | 11000 | 0.2 (cached) | REJECTED (rank 3) |
| 3 | n2_q300_s1.8_ua1000_z3000 | 102 | yes | 0.003 | 6165 | 5.12 | 12000 | 0.2 (cached) | REJECTED (rank 2) |
| 4 | n2_q300_s1.8_ua1000_z3250 | 110 | yes | 0.005 | 5376 | 2.58 | 13000 | 0.1 (cached) | ACCEPTED (rank 1) |
| 5 | n2_q300_s1.8_ua1000_z3500 | 117 | yes | 0.016 | 5226 | 1.92 | 14000 | 0.1 (cached) | REJECTED (rank 5) |

## Final pick

Depth ladder: 2500->2750 m: -18.5%, 1.669 t/yr/m (kept); 2750->3000 m: -16.0%, 1.178 t/yr/m (kept); 3000->3250 m: -12.8%, 0.788 t/yr/m (kept); 3250->3500 m: -2.8%, 0.150 t/yr/m (rejected). Selected n2_q300_s1.8_ua1000_z3250 (110 C reservoir): selected: feasible; external gas 0.0049 GWh, emissions 5376 t, grid import 2.58 GWh, 2 doublets, 13000 m drilled. Versus the conventional reference (gas boiler eta 0.90 + electric chiller COP 5.0, 26706 t): 79.9% lower emissions, external gas 0.005 vs 124.1 GWh, grid import 2.58 vs 4.75 GWh. Well checks at the pick: 300 m3/h: wellhead 107.4 C exceeds PVTConstantSTP temperature_max (100 C) - constant brine properties extrapolated; 300 m3/h: tubing velocity 4.7 m/s > 4 m/s in the 0.15 m ID (all depths). Drilling cost is not modeled; deeper steps are limited by the 5% parsimony rule.

## Runtime

- Annual evaluations: 5 (0 computed, 5 from cache); computed wall time mean 0.0 s, max 0.0 s
- Scenario B runtime: 61.6 s; scenario A runtime: 0.0 s
- Backend calls: 6 (60.8 s)

| Call | Purpose | Wall (s) | Input tokens | Cache read | Output tokens | Cost (USD) |
|---|---|---|---|---|---|---|
| 1 | propose | 7.8 | 2 | 649 | 556 | 0.0959802 |
| 2 | propose | 8.6 | 2 | 2120 | 659 | 0.0898373 |
| 3 | propose | 6.3 | 2 | 2120 | 363 | 0.0873923 |
| 4 | propose | 11.3 | 2 | 2120 | 846 | 0.101005 |
| 5 | propose | 12.0 | 2 | 2120 | 791 | 0.1038577 |
| 6 | propose | 14.8 | 2 | 2120 | 1253 | 0.1218556 |

## Scenario A: heating return temperature removed from the inputs

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

**4. [halt] Stop and ask for the missing input**
> I cannot size the plant without: heating return temperature. 'heating return temperature' is needed because it sets district water flow = Q / (cp * (100 - T_return)) and the HEX/heat-pump lift. It is not in the organizers' inputs and I will not invent it. Please provide a value (previously approved: 60 C).


## Scenario B: complete inputs, design loop

**5. [start] Scenario B_design: start**

**6. [interpret] Interpret demand profiles and fixed inputs**
> 365-day heating (111.67 GWh, peak 30.0 MW on 2027-01-28) and cooling (23.74 GWh, peak 10.0 MW) must be served every day.

**7. [required_inputs] Check required inputs**
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

**8. [temperature_assessment] Source temperature vs 100 C supply**
> Reservoir at 2500 m is 87.0 C, 13.0 K below the fixed 100 C supply before any losses, so a HEX alone cannot supply 100 C. Options: (a) deeper well - T_res = 100 C needs 2933 m, and direct HEX supply (T_res >= 107.4 C incl. 5 K approach, 0.4 K surface drops, ~2 K wellbore loss) needs ~3180 m; (b) surface upgrade - heat pump on the brine leaving the HEX plus CHP on the produced gas. Decision: start with (b) at the official 2500 m (no extrapolated reservoir data, least drilling), then climb a 250 m depth ladder (max 4000 m) and keep each step only if emissions fall >= 5%; the ranking decides with numbers.

**9. [propose] Proposal n2_q300_s1.8_ua1000_z2500**
> No incumbent yet, so this run sets the baseline at the official 2500 m depth, which is the reference for the 5% deeper-well rule. Thermal capacity check: one doublet at 300 m³/h and 40 K delivers about 14.1 MW (300/3600 × 1030 × 4100 × 40). Two doublets give about 28 MW against the 30 MW heating peak plus the absorption drive, so two is the plausible minimum. ESP s1.8 is the only pump that reaches 300 m³/h (s1.0 tops out near 176 m³/h). UA 1000 kW/K gives the most HEX preheat and the least heat-pump lift. The 87 °C reservoir is 13 K short of the 100 °C supply. Next runs should test 1 doublet, for parsimony, and 3000 m depth (about 102 °C), since that is the depth step most likely to change the ranking.

**10. [build_json] GEMINI JSON for n2_q300_s1.8_ua1000_z2500**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**11. [well_check] Well / ESP sanity check at 2500 m**
> Flags: 300 m3/h: tubing velocity 4.7 m/s > 4 m/s in the 0.15 m ID (all depths). Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 30.0 | 6.72 / 79.5 | 0.46 | 58.3 / 72.6 | 0.029 | 245.9 | 0.8 |
| 300 | 62.9 | 4.61 / 85.7 | 0.59 | 16.5 / 77.9 | 0.732 | 225.2 | 4.7 |

**12. [evaluate] Annual model + constraint check: n2_q300_s1.8_ua1000_z2500**
> FEASIBLE: external gas 0.004 GWh, emissions 9011 t, grid import 12.39 GWh, drilled 10000 m (0.1 s, cached)

**13. [rank] Ranking after evaluation**
> Incumbent: n2_q300_s1.8_ua1000_z2500

| Candidate | Rank | Verdict | Reason |
|---|---|---|---|
| n2_q300_s1.8_ua1000_z2500 | 1 | ACCEPTED | selected: feasible; external gas 0.0043 GWh, emissions 9011 t, grid import 12.39 GWh, 2 doublets, 10000 m drilled |

**14. [propose] Proposal n2_q300_s1.8_ua1000_z2750**
> External gas is already essentially zero (0.0043 GWh), so emissions decide the ranking. Most of those emissions come from grid electricity for the heat pump, because the 87 °C reservoir is 13 K short of the 100 °C supply. Going deeper raises reservoir temperature by 7.5 K per 250 m step (2750 m gives 94.5 °C). That cuts heat-pump lift and grid import, which makes depth the lever most likely to change the pick. The depth-acceptance rule compares each depth with the previous accepted one, so I step one rung at a time: 2750 m, keeping the incumbent's n=2, 300 m3/h cap, s1.8 and UA 1000 kW/K so depth is the only change. Adding a third doublet or a bigger HEX is less promising: with gas already at zero, those changes are unlikely to reach the 5% emissions gain needed to be kept. Open flag: 300 m3/h gives 4.7 m/s tubing velocity, which applies at every depth.

**15. [build_json] GEMINI JSON for n2_q300_s1.8_ua1000_z2750**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**16. [well_check] Well / ESP sanity check at 2750 m**
> Flags: 300 m3/h: tubing velocity 4.7 m/s > 4 m/s in the 0.15 m ID (all depths). Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 30.0 | 6.63 / 85.4 | 0.59 | 58.2 / 72.5 | 0.029 | 271.1 | 0.8 |
| 300 | 64.4 | 4.61 / 93.0 | 0.78 | 13.5 / 77.9 | 0.767 | 250.5 | 4.7 |

**17. [evaluate] Annual model + constraint check: n2_q300_s1.8_ua1000_z2750**
> FEASIBLE: external gas 0.002 GWh, emissions 7342 t, grid import 8.15 GWh, drilled 11000 m (0.2 s, cached)

**18. [rank] Ranking after evaluation**
> Incumbent: n2_q300_s1.8_ua1000_z2750 (was n2_q300_s1.8_ua1000_z2500)

| Candidate | Rank | Verdict | Reason |
|---|---|---|---|
| n2_q300_s1.8_ua1000_z2750 | 1 | ACCEPTED | selected: feasible; external gas 0.0022 GWh, emissions 7342 t, grid import 8.15 GWh, 2 doublets, 11000 m drilled |
| n2_q300_s1.8_ua1000_z2500 | 2 | REJECTED | superseded by n2_q300_s1.8_ua1000_z2750: ranks better than n2_q300_s1.8_ua1000_z2500; deeper 2500 -> 2750 m: emissions +18.5% (needs >= 5%), marginal abatement 1.669 t CO2/yr per extra metre drilled |

**19. [depth_step] Depth step 2500 -> 2750 m**
> Emissions 9011 -> 7342 t (-18.5%) for +1000 m drilled: 1.669 t CO2/yr per extra metre. ACCEPTED (>= 5%).

**20. [propose] Proposal n2_q300_s1.8_ua1000_z3000**
> Going from 2500 to 2750 m cut emissions by 18.5% (9011 -> 7342 t) and grid import by 34%, far above the 5% depth threshold, and T_res is still 94.5 C, below 100 C. 3000 m (T_res 102 C, above the 2933 m depth where T_res reaches 100 C) should shrink the heat-pump lift sharply again, so it is the candidate most likely to change the pick. I keep the incumbent's n, flow, ESP and UA so the depth effect is isolated. External gas is already ~0 (a tie), so emissions decide; fewer-doublet or lower-UA variants come after the depth trend is settled. Budget 12 is ample.

**21. [build_json] GEMINI JSON for n2_q300_s1.8_ua1000_z3000**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**22. [well_check] Well / ESP sanity check at 3000 m**
> Flags: 300 m3/h: wellhead 100.2 C exceeds PVTConstantSTP temperature_max (100 C) - constant brine properties extrapolated; 300 m3/h: tubing velocity 4.7 m/s > 4 m/s in the 0.15 m ID (all depths). Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 30.0 | 6.54 / 91.2 | 0.73 | 58.1 / 72.5 | 0.029 | 296.4 | 0.8 |
| 300 | 65.9 | 4.61 / 100.2 | 1.03 | 10.6 / 77.9 | 0.802 | 275.7 | 4.7 |

**23. [evaluate] Annual model + constraint check: n2_q300_s1.8_ua1000_z3000**
> FEASIBLE: external gas 0.003 GWh, emissions 6165 t, grid import 5.12 GWh, drilled 12000 m (0.2 s, cached)

**24. [rank] Ranking after evaluation**
> Incumbent: n2_q300_s1.8_ua1000_z3000 (was n2_q300_s1.8_ua1000_z2750)

| Candidate | Rank | Verdict | Reason |
|---|---|---|---|
| n2_q300_s1.8_ua1000_z3000 | 1 | ACCEPTED | selected: feasible; external gas 0.0029 GWh, emissions 6165 t, grid import 5.12 GWh, 2 doublets, 12000 m drilled |
| n2_q300_s1.8_ua1000_z2750 | 2 | REJECTED | superseded by n2_q300_s1.8_ua1000_z3000: ranks better than n2_q300_s1.8_ua1000_z2750; deeper 2750 -> 3000 m: emissions +16.0% (needs >= 5%), marginal abatement 1.178 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua1000_z2500 | 3 | REJECTED | superseded by n2_q300_s1.8_ua1000_z2750: ranks better than n2_q300_s1.8_ua1000_z2500; deeper 2500 -> 2750 m: emissions +18.5% (needs >= 5%), marginal abatement 1.669 t CO2/yr per extra metre drilled |

**25. [depth_step] Depth step 2750 -> 3000 m**
> Emissions 7342 -> 6165 t (-16.0%) for +1000 m drilled: 1.178 t CO2/yr per extra metre. ACCEPTED (>= 5%).

**26. [propose] Proposal n2_q300_s1.8_ua1000_z3250**
> Going deeper has improved emissions by 18.5% (2500 to 2750 m) and then 16.0% (2750 to 3000 m), both well above the 5% threshold. External gas is already about zero (ties within 0.01 GWh), so emissions now decide the ranking. At 3000 m the remaining 5.12 GWh of grid import (about 1 540 t CO2) comes mostly from the heat pump making up the lift to 100 C. At 3250 m the reservoir is 109.5 C, above the 107.4 C needed for direct HEX supply (the threshold depth is 3180 m). That should remove most of the heat-pump electricity and leave mainly pump power. The likely emissions saving is about 1 000 t (roughly 15-20%), so this is the candidate most likely to change the pick. The produced-gas CO2 floor of about 4 600 t is emitted whatever the depth, so the steps after this one should give diminishing returns. Doublet count, ESP and UA stay at the incumbent's values: a third doublet previously gave only about -0.2% emissions, and the s1.0 ESP cannot deliver 300 m3/h. Caveats: the wellhead temperature will rise further above the PVTConstantSTP range (100 C max), so brine properties are extrapolated. The 4.7 m/s tubing-velocity flag also remains; a lower flow cap should be considered later if it becomes binding.

**27. [build_json] GEMINI JSON for n2_q300_s1.8_ua1000_z3250**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**28. [well_check] Well / ESP sanity check at 3250 m**
> Flags: 300 m3/h: wellhead 107.4 C exceeds PVTConstantSTP temperature_max (100 C) - constant brine properties extrapolated; 300 m3/h: tubing velocity 4.7 m/s > 4 m/s in the 0.15 m ID (all depths). Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 30.0 | 6.45 / 96.8 | 0.90 | 58.0 / 72.4 | 0.029 | 321.7 | 0.8 |
| 300 | 67.3 | 4.61 / 107.4 | 1.31 | 7.6 / 77.9 | 0.837 | 301.0 | 4.7 |

**29. [evaluate] Annual model + constraint check: n2_q300_s1.8_ua1000_z3250**
> FEASIBLE: external gas 0.005 GWh, emissions 5376 t, grid import 2.58 GWh, drilled 13000 m (0.1 s, cached)

**30. [rank] Ranking after evaluation**
> Incumbent: n2_q300_s1.8_ua1000_z3250 (was n2_q300_s1.8_ua1000_z3000)

| Candidate | Rank | Verdict | Reason |
|---|---|---|---|
| n2_q300_s1.8_ua1000_z3250 | 1 | ACCEPTED | selected: feasible; external gas 0.0049 GWh, emissions 5376 t, grid import 2.58 GWh, 2 doublets, 13000 m drilled |
| n2_q300_s1.8_ua1000_z3000 | 2 | REJECTED | superseded by n2_q300_s1.8_ua1000_z3250: ranks better than n2_q300_s1.8_ua1000_z3000; deeper 3000 -> 3250 m: emissions +12.8% (needs >= 5%), marginal abatement 0.788 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua1000_z2750 | 3 | REJECTED | superseded by n2_q300_s1.8_ua1000_z3000: ranks better than n2_q300_s1.8_ua1000_z2750; deeper 2750 -> 3000 m: emissions +16.0% (needs >= 5%), marginal abatement 1.178 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua1000_z2500 | 4 | REJECTED | superseded by n2_q300_s1.8_ua1000_z2750: ranks better than n2_q300_s1.8_ua1000_z2500; deeper 2500 -> 2750 m: emissions +18.5% (needs >= 5%), marginal abatement 1.669 t CO2/yr per extra metre drilled |

**31. [depth_step] Depth step 3000 -> 3250 m**
> Emissions 6165 -> 5376 t (-12.8%) for +1000 m drilled: 0.788 t CO2/yr per extra metre. ACCEPTED (>= 5%).

**32. [propose] Proposal n2_q300_s1.8_ua1000_z3500**
> The depth ladder is still paying off: each 250 m step has cut emissions by more than the 5% threshold (18.5%, 16.0%, then 12.8% for 3000->3250 m). The gains are shrinking, because 3250 m (109.5 C) already passes the ~3180 m depth where the HEX alone can supply 100 C. The remaining improvement mostly comes from cutting heat-pump and electric-chiller electricity (2.58 GWh grid import, about 774 t at 0.3 kg/kWh, which is about 14% of 5376 t). Produced-gas CO2 is emitted whatever the design. So 3500 m (117 C) could still clear the 5% bar, mainly through more heat for the absorption chiller and less heat-pump duty, and it is the candidate most likely to change the pick. One doublet would raise external gas against the 30 MW peak, and changing UA or ESP is unlikely to beat depth. If 3500 m falls short of 5%, stop and keep 3250 m.

**33. [build_json] GEMINI JSON for n2_q300_s1.8_ua1000_z3500**
> GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components.

**34. [well_check] Well / ESP sanity check at 3500 m**
> Flags: 50 m3/h: wellhead 102.2 C exceeds PVTConstantSTP temperature_max (100 C) - constant brine properties extrapolated; 300 m3/h: wellhead 114.5 C exceeds PVTConstantSTP temperature_max (100 C) - constant brine properties extrapolated; 300 m3/h: ESP intake 4.7 bar < vapour pressure + 5 bar - cavitation risk; 300 m3/h: tubing velocity 4.7 m/s > 4 m/s in the 0.15 m ID (all depths); 300 m3/h: ESP at 68.7 Hz, within 2 Hz of the drive limit. Not modelled: free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model).

| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |
|---|---|---|---|---|---|---|---|
| 50 | 30.0 | 6.36 / 102.2 | 1.10 | 57.9 / 72.3 | 0.029 | 346.9 | 0.8 |
| 300 | 68.7 | 4.61 / 114.5 | 1.66 | 4.7 / 77.9 | 0.872 | 326.2 | 4.7 |

**35. [evaluate] Annual model + constraint check: n2_q300_s1.8_ua1000_z3500**
> FEASIBLE: external gas 0.016 GWh, emissions 5226 t, grid import 1.92 GWh, drilled 14000 m (0.1 s, cached)

**36. [rank] Ranking after evaluation**
> Incumbent: n2_q300_s1.8_ua1000_z3250

| Candidate | Rank | Verdict | Reason |
|---|---|---|---|
| n2_q300_s1.8_ua1000_z3250 | 1 | ACCEPTED | selected: feasible; external gas 0.0049 GWh, emissions 5376 t, grid import 2.58 GWh, 2 doublets, 13000 m drilled |
| n2_q300_s1.8_ua1000_z3000 | 2 | REJECTED | superseded by n2_q300_s1.8_ua1000_z3250: ranks better than n2_q300_s1.8_ua1000_z3000; deeper 3000 -> 3250 m: emissions +12.8% (needs >= 5%), marginal abatement 0.788 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua1000_z2750 | 3 | REJECTED | superseded by n2_q300_s1.8_ua1000_z3000: ranks better than n2_q300_s1.8_ua1000_z2750; deeper 2750 -> 3000 m: emissions +16.0% (needs >= 5%), marginal abatement 1.178 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua1000_z2500 | 4 | REJECTED | superseded by n2_q300_s1.8_ua1000_z2750: ranks better than n2_q300_s1.8_ua1000_z2500; deeper 2500 -> 2750 m: emissions +18.5% (needs >= 5%), marginal abatement 1.669 t CO2/yr per extra metre drilled |
| n2_q300_s1.8_ua1000_z3500 | 5 | REJECTED | parsimony rule not met: ranks not better than n2_q300_s1.8_ua1000_z3250; deeper 3250 -> 3500 m: emissions +2.8% (needs >= 5%), marginal abatement 0.150 t CO2/yr per extra metre drilled |

**37. [depth_step] Depth step 3250 -> 3500 m**
> Emissions 5376 -> 5226 t (-2.8%) for +1000 m drilled: 0.150 t CO2/yr per extra metre. REJECTED by the depth parsimony rule (< 5%).

**38. [stop] Backend stops proposing**
> No untried variant can change the pick within the design space and the parsimony rules.

**39. [final] Final pick: n2_q300_s1.8_ua1000_z3250**
> Depth ladder: 2500->2750 m: -18.5%, 1.669 t/yr/m (kept); 2750->3000 m: -16.0%, 1.178 t/yr/m (kept); 3000->3250 m: -12.8%, 0.788 t/yr/m (kept); 3250->3500 m: -2.8%, 0.150 t/yr/m (rejected). Selected n2_q300_s1.8_ua1000_z3250 (110 C reservoir): selected: feasible; external gas 0.0049 GWh, emissions 5376 t, grid import 2.58 GWh, 2 doublets, 13000 m drilled. Versus the conventional reference (gas boiler eta 0.90 + electric chiller COP 5.0, 26706 t): 79.9% lower emissions, external gas 0.005 vs 124.1 GWh, grid import 2.58 vs 4.75 GWh. Well checks at the pick: 300 m3/h: wellhead 107.4 C exceeds PVTConstantSTP temperature_max (100 C) - constant brine properties extrapolated; 300 m3/h: tubing velocity 4.7 m/s > 4 m/s in the 0.15 m ID (all depths). Drilling cost is not modeled; deeper steps are limited by the 5% parsimony rule.

