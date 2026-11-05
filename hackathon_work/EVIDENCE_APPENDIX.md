# Evidence appendix

GEMINI agentic geothermal hackathon, 2027 design. All paths are relative to `hackathon_work/`.
Every number below comes from a committed output file, named next to it. Figures are the
300 dpi panel exports in `outputs/figures/`.

**Final pick (rules backend):** `n2_q300_s1.8_ua1000_z3500_co2ri`. That is 2 doublets at a
300 m³/h cap, an s1.8 ESP, a 1 MW/K HEX and 3 500 m wells (117 °C reservoir). The CO₂ is
separated and reinjected, and the CH₄ goes to the CHP.

| KPI | Pick | Reference (gas boiler η 0.90 + electric chiller COP 5.0) |
|---|---|---|
| Emissions | **3 983 t CO₂/yr** | 26 706 t CO₂/yr (−85.1%) |
| External gas | 0.016 GWh | 124.1 GWh |
| Grid import | 0.87 GWh | 4.75 GWh |
| Hard constraints | all pass, all 365 days | – |

Sources: `outputs/agent/run_summary.json`, `outputs/agent/final_design/summary.json`, `outputs/reference/summary.json`.
Figures: `outputs/figures/p1_kpis.png`, `p6_emissions.png`, `p12_energy_sankey.png`, `p15_why_this_design.png`.

Contents:

1. Judges' agent-reasoning tests
2. Constraint checker tests
3. Missing-input handling
4. Sensitivity
5. N-1 backup
6. Gas solubility margins
7. Provenance summary
8. Token use and runtime
9. Known limitations
10. GEMINI issues found
11. Reproduce

---

## 1. Judges' agent-reasoning tests (4/4 PASS)

Source: `outputs/agent/agent_trace.md` (section "Judges' agent-reasoning tests"), with the full step log in
`outputs/agent/decision_log.jsonl` (91 steps). Figure: `outputs/figures/p9_judges_tests.png`.

**(i) Missing physical quantity: stop and ask.** In scenario A, `heating_return_T` is removed and the agent halts at step 4:

> I cannot size the plant without 1 input(s): heating_return_T. 'heating_return_T' (heating return
> temperature, C, ASSUMED) is needed because it sets district water flow = Q / (cp * (100 - T_return))
> and the HEX/heat-pump lift; plausible range 40-80 C. It is not in the organizers' inputs and I will
> not invent it. Please provide a value (or rerun with --interactive to answer in the terminal).

**(ii) ≥ 350 m³/h per doublet: rejected with a reason, then revised.**

> step 17: 350.00 m3/h exceeds the 300 m3/h hard cap -> step 18: Revised to n2_q300_s1.8_ua1000_z2500

Step 10 is a second instance: 650 m³/h is rejected and revised to `n1_q300_s1.8_ua1000_z2500` at step 11.

**(iii) 87 °C reservoir against the fixed 100 °C supply: the shortfall is stated, and a deeper well is weighed against a surface upgrade.**
The step 8 assessment states the 13 K shortfall at 2 500 m. Candidates are then evaluated at reservoir temperatures of
87.0, 94.5, 102.0, 109.5, 117.0 and 124.5 °C. Step 91 records the decision: go deeper on a 250 m ladder, keeping each
step only if it cuts emissions by ≥ 5% beyond the tie tolerance, with the heat-pump cascade as the surface upgrade.

> Depth ladder: 2500->2750 m: -18.4%, 1.641 t/yr/m (kept); 2750->3000 m: -16.9%, 1.229 t/yr/m (kept); 3000->3250 m:
> -14.7%, 0.890 t/yr/m (kept); 3250->3500 m: -5.0%, 0.257 t/yr/m (rejected, marginal); 3250->3500 m: -6.3%, 0.268 t/yr/m
> (kept); 3500->3750 m: -0.8%, 0.033 t/yr/m (rejected).

The first 3 250 → 3 500 m step is with CHP and falls within the tie tolerance of 5%, so it does not count. The second
is with CO₂ reinjection, accepted at 3 250 m, which re-opens the ladder.

Figure: `outputs/figures/p5_agent_path.png`.

**(iv) Recovery after a failed or ranked-out candidate.** The 650 m³/h proposal fails a hard limit (step 10), is
revised at step 11, and the revised design is feasible at step 14. It is then ranked out:

> superseded by n2_q300_s1.8_ua1000_z2500: ranks better than n1_q300_s1.8_ua1000_z2500 (decided by
> external_gas_fuel_GWh: 0.001987 vs 28.6, beyond its tie tolerance)

Thirteen of the 14 evaluated candidates are ranked out, each with a logged reason. The replay of all 14 steps is
`outputs/figures/p14_agent_replay.png`, which is interactive in `dashboard/index.html`.

## 2. Constraint checker tests (10/10 expectations met)

Source: `test_constraint_checker.py` → `outputs/evidence/constraint_checker_tests.txt` (readable) and
`constraint_checker_tests.json` (each case with its full report). The cases are synthetic, not simulator results. Each
variant breaks one limit and must be rejected by that check. Figure: `outputs/figures/p8_constraints.png`.

| Test | Case | Expected | Checker reason | Result |
|---|---|---|---|---|
| T0 | compliant reference: 200 m³/h, ΔT 35 K, η 0.70, 100 °C / 20 °C | feasible | all PASS | OK |
| T1 | 350 m³/h per doublet | `flow_range` FAIL | 350.00 m3/h exceeds the 300 m3/h hard cap | OK |
| T2 | 30 m³/h on an active doublet | `flow_range` FAIL | 30.00 m3/h is below the 50 m3/h minimum stable flow while active | OK |
| T3 | brine cooled 85 → 40 °C (45 K) | `brine_dT` FAIL | 45.00 K brine cooling exceeds the 40 K cap | OK |
| T4 | 4 doublets | `doublet_count` FAIL | 4 doublets is outside the allowed 1-3 | OK |
| T5 | heating supply 77.75 °C (task 1) | `heating_supply_T` FAIL | 77.75 C is -22.25 K from the fixed 100 C supply | OK |
| T6 | ESP power from the curve at η 0.65 | `pump_efficiency` FAIL | 236.8 kW implies eta 0.650, required 0.7 -> expected 219.8 kW | OK |
| T7 | 200 m³/h produced, 190 m³/h injected | `volume_balance` FAIL | imbalance +10.00 m3/h | OK |
| T8 | cooling supply not modelled | `cooling_supply_T` MISSING | not modeled yet; cannot be shown compliant | OK |
| **T9** | **reinjected CO₂ at 200× the OFFICIAL load (GLR 160 Nm³/m³ → 32 Nm³ CO₂/m³), at the pick's reservoir (351 bar(g), 117 °C) and worst injector wellhead (5.1 bar(g), 74.7 °C)** | **`gas_dissolution` FAIL** | **wellhead margin 0.04 < 1 and no bubble point below 2000 bar: the gas cannot all dissolve; reservoir margin 0.7** | **OK** |

T9 includes a control run under the same conditions at the OFFICIAL load (GLR 0.8 Nm³/m³), which must PASS:
"CO2 0.16 Nm3/m3: dissolves at the wellhead (margin 7.27); reservoir margin 147.5". This shows that T9 fails because
of the gas load alone. Writing T9 exposed a bug: `gas_solubility.bubble_point_bar` overflowed when no bubble point
exists. It now returns `inf` above 2 000 bar, and the check reports FAIL. The fix has no effect on any evaluated
design, whose highest bubble point is 61.5 bar(g) (see DECISIONS_LOG #24).

The 365-day model applies the same checks per doublet and per day (`daily_model.py`, `constraints.py`). The annual
checks it adds are the 330-day rule, demand met on all 365 days, ESP intake, tubing velocity and `gas_dissolution`.

## 3. Missing-input handling

Source: `design_agent.py` (`REQUIRED_INPUTS`), `outputs/agent/agent_trace.md` (scenario A) and
`outputs/agent/interactive/agent_trace.md`. Figure: `outputs/figures/p9_judges_tests.png`.

Twelve inputs the agent needs are not in the organizers' data. Each has a unit, a reason it is needed, a plausible
range with justification, and a provenance tag. All twelve are checked at startup:

| Input | Value used | Plausible range | Provenance |
|---|---|---|---|
| heating_return_T | 60 °C | 40–80 °C | ASSUMED |
| cooling_return_T | 26 °C | 21–35 °C | ASSUMED |
| brine_cp | 4 100 J/(kg K) | 3 500–4 300 | ASSUMED |
| absorption_COP | 0.7 | 0.5–1.4 | ASSUMED |
| absorption_drive_inlet_T | 75 °C | 65–100 °C | ASSUMED |
| absorption_drive_outlet_T | 70 °C | 55–95 °C | ASSUMED |
| electric_chiller_COP | 5.0 | 2.5–8 | ASSUMED |
| hp_eta_lorenz | 0.45 | 0.3–0.7 | ASSUMED |
| hp_cop_cap | 6 | 3–10 | ASSUMED |
| produced_gas_EF | 68.6 kg CO₂/GJ | 50–100 | DERIVED (80/20 CH₄/CO₂ combustion + CO₂ pass-through) |
| external_gas_EF | 56.6 kg CO₂/GJ | 50–60 | ASSUMED |
| electricity_EF | 0.3 kg CO₂/kWh | 0–1 | ASSUMED |

The agent responds to a missing input in one of three ways:
- **Default run:** it stops and lists every missing input with its unit, range and reason. It never substitutes a
  value (judges' test i). `--remove NAME[,NAME]` or `--remove all` removes inputs for the demo.
- **`--interactive`:** it asks for each value in the terminal, validates the answer against the range and asks
  again if the answer is out of range. It then continues with the answers logged and timestamped. The recorded run
  is `outputs/agent/interactive/` (re-run 2026-11-05 on the final model, `--remove heating_return_T`). The agent
  refused `abc` (not a number) and `95` (outside 40–80 °C) and accepted `60`. It then reached the same pick as the
  rules run, n2_q300_s1.8_ua1000_z3500_co2ri, in 14 evaluations with all four judges' tests passing.
- **Out-of-range value:** it refuses the value and gives the plausible range.

## 4. Sensitivity (one input at a time, 10 cases)

Source: `sensitivity.py` → `outputs/sensitivity/sensitivity.md`, `summary.json`, and one decision log per case under
`runs/`. Figure: `outputs/figures/p10_sensitivity_tornado.png`. All spreads are ASSUMED (gradient: ±10% of the
OFFICIAL 30 °C/km). Two runs were made per case:
- **Final design:** the base pick re-simulated with the changed input.
- **Agent pick:** a fresh rules-agent run with the changed input.

| Input | Value | Final design emissions (t) | Delta (t) | Delta (%) | Hard constraints | Agent pick | Pick changed |
|---|---|---|---|---|---|---|---|
| Heating return temperature (C) | 50 (base 60) | 3958 | -25 | -0.6% | PASS | `n2_q300_s1.8_ua1000_z3250_co2ri` (4024 t) | **yes** |
| Heating return temperature (C) | 70 (base 60) | 4172 | +189 | +4.7% | PASS | `n2_q300_s1.8_ua1000_z3500_co2ri` (4172 t) | no |
| Heat pump Lorenz efficiency (-) | 0.4 (base 0.45) | 3983 | +0 | +0.0% | PASS | `n2_q300_s1.8_ua1000_z3500_co2ri` (3983 t) | no |
| Heat pump Lorenz efficiency (-) | 0.5 (base 0.45) | 3983 | +0 | +0.0% | PASS | `n2_q300_s1.8_ua1000_z3500_co2ri` (3983 t) | no |
| Absorption chiller COP (-) | 0.6 (base 0.7) | 4137 | +153 | +3.8% | PASS | `n3_q300_s1.8_ua1000_z3500_co2ri` (4099 t) | **yes** |
| Absorption chiller COP (-) | 0.8 (base 0.7) | 3874 | -109 | -2.7% | PASS | `n2_q300_s1.8_ua1000_z3500_co2ri` (3874 t) | no |
| Geothermal gradient (C/km) | 27 (base 30) | 4618 | +635 | +15.9% | PASS | `n2_q300_s1.8_ua1000_z3750_co2ri` (4018 t) | **yes** |
| Geothermal gradient (C/km) | 33 (base 30) | 3971 | -12 | -0.3% | PASS | `n2_q300_s1.8_ua1000_z3000_co2ri` (4104 t) | **yes** |
| Brine specific heat (J/(kg K)) | 4000 (base 4100) | 4085 | +102 | +2.6% | PASS | `n2_q300_s1.8_ua1000_z3250_co2ri` (4344 t) | **yes** |
| Brine specific heat (J/(kg K)) | 4200 (base 4100) | 3904 | -80 | -2.0% | PASS | `n2_q300_s1.8_ua1000_z3500_co2ri` (3904 t) | no |

Why the base pick loses where the pick changes (the agent's own verdict on the base pick, from each case's log):

- Heating return temperature = 50: parsimony rule not met: ranks better than n2_q300_s1.8_ua1000_z3250_co2ri (decided by emissions_t: 3958 vs 4024); deeper 3250 -> 3500 m: emissions +1.634% (needs >= 5% beyond the tie tolerance), marginal abatement 0.066 t CO2/yr per extra metre drilled
- Absorption chiller COP = 0.6: superseded by n3_q300_s1.8_ua1000_z3500_co2ri: ranks better than n2_q300_s1.8_ua1000_z3500_co2ri (decided by external_gas_fuel_GWh: 0.00468 vs 0.1577, beyond its tie tolerance); extra doublet: external gas +97.0%, emissions +0.9% (needs >= 5% on either, beyond the tie tolerance)
- Geothermal gradient = 27: not evaluated: the depth ladder stopped elsewhere (each step must cut emissions >= 5%)
- Geothermal gradient = 33: not evaluated: the depth ladder stopped elsewhere (each step must cut emissions >= 5%)
- Brine specific heat = 4000: parsimony rule not met: ranks better than n2_q300_s1.8_ua1000_z3250_co2ri (decided by emissions_t: 4085 vs 4344); deeper 3250 -> 3500 m: emissions +5.962% (needs >= 5% beyond the tie tolerance), marginal abatement 0.259 t CO2/yr per extra metre drilled - within the tie tolerance of the threshold, counts as NOT met (marginal sensitivity case)

The final design passes every hard constraint in all 10 cases, with emissions of 3 874–4 618 t. The geothermal
gradient dominates. Heat-pump η has no effect because at 3 500 m the heat pump runs at its COP 6 cap on all 145 days
it operates. The pick changes in 5 of 10 cases, but the architecture (s1.8 ESP, UA 1 MW/K, CO₂ reinjection) holds in
all 10. Depth moves with the gradient, return temperature and cp because those cases sit near the 5% step threshold.
At absorption COP 0.6, a third doublet removes the external gas.

## 5. N-1 backup (unplanned outage of one doublet, ASSUMED resilience case)

Source: `outputs/agent/agent_trace.md` ("N-1 resilience at the final pick", "Backup equipment sizing").
Figure: `outputs/figures/p11_resilience_gas.png`.

| Case | Date | Doublet out | Doublets on | Boiler (MWth): normal → N-1 | of which external gas | Electric chiller (MWcool) | Unmet heat / cool |
|---|---|---|---|---|---|---|---|
| Peak heating day | 2027-01-28 | doublet_1 | 2 → 1 | 0.23 → 15.12 | 15.12 | 0.00 → 0.00 | 0 / 0 MW |
| Peak cooling day | 2027-07-19 | doublet_1 | 2 → 1 | 0.00 → 2.07 | 2.07 | 0.00 → 0.00 | 0 / 0 MW |

The installed backup at the pick is 15.12 MWth of boiler and no electric chiller. Installed backup is the larger of
the planned peak and the N-1 peak, which puts 1-doublet designs on equal terms: they are sized at 30 MWth + 10 MWcool.
A single doublet is feasible with backup (organizer clarification, 2026-11-01: the 330-day rule limits the source,
and the system must meet demand on all 365 days). It is ranked out because it needs 28.6 GWh of external gas at
2 500 m and 36.5 GWh at 3 500 m.

## 6. Gas solubility margins (reinjected gas must dissolve)

Source: `gas_solubility.py`, with results in `outputs/agent/final_design/summary.json` (`gas_dissolution`) and the
agent trace ("Gas handling"). Figure: `outputs/figures/p11_resilience_gas.png`.

Method (DERIVED, each part cited in the module):
- Henry constants for CO₂ and CH₄ from IAPWS G7-04 (Fernández-Prini et al. 2003), with a Poynting correction. The
  partial molar volumes are ASSUMED: 35 cm³/mol for CO₂ and 37 cm³/mol for CH₄.
- Water vapour pressure from Wagner & Pruß (2002).
- Weisenberger & Schumpe (1996) salting-out.
- Peng–Robinson gas phase with k_ij 0.09 (ASSUMED).
- Salinity read from the OFFICIAL density of 1 030 kg/m³:
  - at 20 °C, 0.80 mol/kg (DERIVED);
  - at reservoir temperature, 2.29 mol/kg. This is the conservative bound and is the one used for the check.

The margin is the factor by which the gas load could grow before the bubble point reaches the available pressure.
The check is a hard annual check: the reservoir margin must be ≥ 1, and the dip tube must be shallower than the well.

| Option at n2 / 3 500 m | Gas reinjected | Wellhead (5.1 bar(g), 74.7 °C) | Reservoir (351 bar(g), 117 °C) | Dip tube | Compression |
|---|---|---|---|---|---|
| (b) co2_reinject (**pick**) | 0.16 Nm³ CO₂/m³ | margin **7.27** (bubble point 0.14 bar(g)) | margin **147.5** | none | DERIVED minimum 0.042 kWh/kg; ASSUMED 0.1 kWh/kg used |
| (c) reinject_all | 0.80 Nm³ CO₂+CH₄/m³ | margin **0.11** (bubble point 61.5 bar(g)) | margin **4.8** | ≥ 558 m | DERIVED 0.197 kWh/kg, used |
| T9 negative test | 32 Nm³ CO₂/m³ | 0.04 (no bubble point) | **0.7 → FAIL** | none possible | – |

With the surface salinity (0.80 mol/kg), the margins for option (b) are 9.46 at the wellhead and 176.7 at the
reservoir.

## 7. Provenance summary

Source: the `_provenance` blocks in `projects/doublet_challenge.json` (GEMINI chain) and
`projects/candidates_2027.json` (design settings), plus `REQUIRED_INPUTS`. The counts are of entries by the tags each
entry carries. "Other" entries are not new physical values: they are GEMINI defaults, control variables, design
variables, user decisions or organizer clarifications.

| File | Entries | OFFICIAL | DERIVED | ASSUMED | OFFICIAL + ASSUMED | DERIVED + ASSUMED | Other |
|---|---|---|---|---|---|---|---|
| `projects/doublet_challenge.json` | 26 | 4 | 6 | 10 | 2 | 1 | 3 (2 control, 1 design variable) |
| `projects/candidates_2027.json` | 32 | 1 | 1 | 19 | 2 | 3 | 6 (2 GEMINI defaults, 2 user decisions, 1 organizer clarification, 1 CHP configuration) |
| **Total** | **58** | **5** | **7** | **29** | **4** | **4** | **9** |
| `REQUIRED_INPUTS` (agent) | 12 | – | 1 | 11 | – | – | – |

The OFFICIAL inputs (demand profiles, reservoir, brine, hard limits and supply temperatures) are transcribed in
`inputs/challenge_inputs.json` and `CLAUDE.md`. Every DERIVED value states its derivation, and every ASSUMED value
states its basis and range.

## 8. Token use and runtime

| Run | Backend | Annual evaluations | Backend calls | Input tokens (uncached / cache write / cache read) | Output tokens | Cost (USD) | Backend wall time | Total runtime |
|---|---|---|---|---|---|---|---|---|
| Final, rules (`outputs/agent/`) | deterministic rules | 14 (all computed, cold cache) | 0 | 0 | 0 | 0 | 0 s | 25.3 s scenario B |
| Final, claude_cli (`outputs/agent/claude_cli/`) | Claude Code `claude -p` (Opus 5.5; Haiku 5.5 for $0.005 of CLI housekeeping) | 10 (6 computed, 4 from the rules run's cache) | 11 | 22 / 164 272 / 21 789 (186 083 total) | 6 821 | **1.46** | 88.4 s | 105 s |
| Previous claude_cli run (superseded, earlier model) | same | 5 | 6 | – | 4 468 | 0.60 | 60.8 s | 62 s |

Per-call detail (wall time, tokens and cost) is in the token table at the end of
`outputs/agent/claude_cli/agent_trace.md`. Each call costs about $0.12. Almost all of that is the 13–17 k cache-write
tokens: every `claude -p --no-session-persistence` call starts a fresh session and re-sends the Claude Code system
prompt together with the agent state. Output is 350–1 600 tokens per call. This run had 11 calls, against 6 in the
earlier one, which is why it cost $1.46 rather than the ~$0.60 that run suggested. Calling the Messages API directly
with a cached system prompt would cut this (not done).

**The two backends compared.** The claude_cli run on the final model reaches the **same pick** as the rules backend,
`n2_q300_s1.8_ua1000_z3500_co2ri` (3 983 t). It follows the same path: the doublet step (1 → 2), the CHP depth ladder
to 3 250 m (3 500 m marginal at −4.994%), CO₂ reinjection at 3 250 m, the ladder re-opened (3 500 m −6.3% kept,
3 750 m −0.8% rejected), and reinject_all ranked out. It skipped UA 500 kW/K, the s1.0 ESP, a third doublet and
one doublet at 3 500 m. Its rationale (step 43): "3 doublets are unlikely to clear the 5% bar on external gas
(already ~0) or emissions". Its stop rationale is logged at step 65. Judges' tests (i), (iii) and (iv) pass in that
run. Test (ii) is not triggered, because the LLM never proposed a flow above the 300 m³/h cap. The rules run
demonstrates that rejection (steps 10 and 17), and so does checker test T1. Every LLM proposal still passes through
the same validation, GEMINI JSON build, 365-day model and ranking as the rules backend.

Token use while developing the submission (the Claude Code sessions that wrote this code) is not recorded in the
repository and is not included above.

## 9. Known limitations

- **Wellhead 114 °C against a 100 °C brine-property range.** From 3 000 m, the wellhead temperature (114.1 °C at the
  pick) exceeds `PVTConstantSTP`'s `temperature_max` of 100 °C. The constant brine properties (1 030 kg/m³,
  0.4 mPa·s, cp 4 100) are extrapolated. This is flagged in the trace for every affected candidate. The cp
  sensitivity (±100 J/(kg K)) bounds the heat-balance effect at −2.0% to +2.6% emissions.
- **Fixed-COP chillers.** The absorption chiller (COP 0.7) and the electric chiller (COP 5.0) use constant COPs with
  no dependence on drive, condenser or ambient temperature. Only the absorption drive limits (75 °C in, 70 °C out)
  are enforced per day. The absorption COP sensitivity (0.6 / 0.8) is +3.8% / −2.7% on emissions.
- **No cost model.** Drilling, equipment and gas-handling costs are not modelled. Depth and doublet count are
  limited by the 5% parsimony rule instead. That rule is conservative: a step within the tie tolerance of 5% counts
  as not meeting it.
- **Daily resolution.** Peaks are daily averages, not hourly. Backup capacity is unlimited by construction, so unmet
  demand is 0, and installed backup is reported from the planned and N-1 peaks.
- **Free gas at the ESP intake is not modelled.** The well model has a gas mass fraction of 0 at GLR 0.8.
- **Gas solubility.** The salting-out fit (273–363 K) is extrapolated to 117 °C, and the partial molar volumes and
  k_ij are ASSUMED. The pick's margins (7.3 and 148) leave a wide buffer for this uncertainty.

## 10. GEMINI issues found

None of these required changes to `src/`. Each has a workaround in `hackathon_work/`.

| # | Component | Issue | Impact / workaround | Evidence |
|---|---|---|---|---|
| 1 | `gemini_model/heatpump/heatpump_basic.py` | (a) The Nelder-Mead solve diverges at low lift or small sink flow: COP 0.014, Th_out 409 °C, where the same equations give COP 17.7 and 100 °C. (b) The `Ts_in_minimum` fallback returns Th_out 835.7 °C at COP 1.00. (c) `get_output()` returns the internal dict, so a stored result is overwritten by the next call. | It agreed within 1% on only 238–272 of 344–365 heat-pump days. `daily_model.py` solves the same two equations (Lorenz COP and energy balance) with a bracketing root finder and logs HeatpumpBasic as a cross-check. The issue note includes a proposed upstream fix. | `outputs/evidence/heatpumpbasic_issue.md`, `repro_heatpumpbasic.py` |
| 2 | ESP model (`gemini_simulator.well_flow`, HC27000 curve) | ESP efficiency is not a parameter; it emerges from the curve: 58% in GEMINI's example run and 62–65% at the challenge flows. The challenge requires η 0.70. Frequency does not extend the flow range (head = stages·(f/60)²·poly(Q), zero head above 280 m³/h at any frequency), so the challenge doublet reaches only ~176 m³/h at 70 Hz. | ESP power is reported as Q·Δp/0.70 and checked (T6). A scaled ESP (`ScaledESP`, stage options s1.0 / s1.8) is installed at runtime to reach 300 m³/h. | `CLAUDE.md` (Known code facts), `doublet_model.py` (`install_scaled_esp`), `run_doublet_challenge.py` |
| 3 | Fluid properties | `PVTConstantSTP` has no T/P dependence and a stated 100 °C maximum. `kpi.py`, `HeatExchanger` and `Boiler` hard-code 1 050 kg/m³ and 4 200 J/(kg K), against the challenge brine's 1 030 and 4 100. The separator's gas composition is unused, and wells carry gas mass fraction 0. | The challenge brine is installed at runtime (`doublet_model.install_brine_pvt` replaces `well_flow.PVTConstantSTP` and verifies the override). The surface models get 1 030 / 4 100 through their parameters. KPIs are computed in `hackathon_work`. | `src/gemini_simulator/kpi.py:35-36`, `src/gemini_model/heat_exchanger/heat_exchanger.py:16-17`, `src/gemini_model/boiler/boiler.py:16-17`, `src/gemini_model/fluid/pvt_water_stp.py:16` |
| 4 | Other model facts | The reservoir temperature is unused (the wellhead temperature is a boundary input). The boiler and CHP have no temperature setpoint, and the CHP split is fixed at 1/3 electric and 2/3 heat. `HeatpumpBasic` is not in the registry, and there is no cooling model. The solver is single pass, so a daily loop must be driven externally. | All handled in `daily_model.py`. | `CLAUDE.md` (Known code facts) |

## 11. Reproduce

Run these from the GEMINI repository root on the `development` branch with this folder added:

```powershell
$env:PYTHONPATH="src"
py -3.11 -m poetry run python hackathon_work/reference_case.py                      # reference (26 706 t)
py -3.11 -m poetry run python hackathon_work/test_constraint_checker.py             # 10/10 checker tests
py -3.11 -m poetry run python hackathon_work/design_agent.py --clear-cache          # rules agent, ~30 s
py -3.11 -m poetry run python hackathon_work/design_agent.py --backend claude_cli   # LLM backend (needs Claude Code)
py -3.11 -m poetry run python hackathon_work/sensitivity.py                         # 10 agent runs, ~5 min
py -3.11 -m poetry run python hackathon_work/make_dashboard.py                      # dashboard + outputs/figures/*.png
```
