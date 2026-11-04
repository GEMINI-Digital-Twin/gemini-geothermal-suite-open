# hackathon_work — GEMINI Agentic Geothermal Hackathon

Workspace for designing a 1–3 doublet geothermal heating + cooling system for the
2027 demand profiles, using GEMINI's physics models and simulator.

## Folder rules
- NEVER modify `../src/`, `../simulator_examples/`, `../unit_test/`. Read them; import from them.
- `inputs/` is read-only (official data + PDFs). Never edit or overwrite.
- `outputs/` is generated; anything there must be reproducible from code + inputs.
  Per-run logs go in `outputs/runs/`.
- Plant JSONs live in `projects/` (copies of `../simulator_examples/projects/*.json`, edited there).
  Every non-official value is tagged in the project's `_provenance` section.
- Extending GEMINI without touching src: call models directly, register extra types at
  runtime (`registry.COMPONENT_REGISTRY["heatpump"] = HeatpumpBasic`), or patch module
  globals from our code (e.g. the well PVT override in `run_doublet_challenge.py`).
- Do NOT use `gemini_simulator/kpi.py` (hard-coded names, rho 1050 / cp 4200). Write our
  own KPIs using the project's brine properties (cp = 4100).
- Run from repo root:
  `$env:PYTHONPATH="src"; py -3.11 -m poetry run python hackathon_work/<script>.py`

## Hard constraints (OFFICIAL — inputs/requirements.pdf p.2; never relax)
- Doublets: 1–3 (integer). Flow per active doublet: 50 ≤ Q ≤ 300 m³/h.
- Brine cooling producer→injector: 0 ≤ ΔT ≤ 40 K.
- Pump hydraulic efficiency: 70%. ESP and injector pump power = Q·Δp / 0.70
  (do not use the ESP curve's own power/efficiency for reported power).
- Production = injection liquid volume, same reservoir.
- Geothermal doublet operation: 330 daily steps; demand covered on all 365 days.
  **Organizer clarification (Discord, 2026-11-01):** the 330-day rule is the availability of the
  geothermal SOURCE; the full system must meet demand on all 365 days. Staggered maintenance OR
  one doublet with backup are both valid design choices. "Never all doublets off" is therefore
  NOT a constraint: days without geothermal supply are a reported design attribute
  (`days_without_geothermal`), and the hard check is `demand_met_365` (no unmet heat/cooling).
- Supply temperature: heating 100 °C, cooling 20 °C.
- Reservoir (OFFICIAL): 2500 m TVD midpoint, 100 m thick, 30 °C/km, 12 °C surface,
  250 bar(g), 200 mD → T_res = 87 °C (DERIVED). Other depths: hydrostatic P, gradient T.
- Brine (OFFICIAL): 1030 kg/m³, 0.40 mPa·s, GLR 0.8 Nm³/m³ (0 °C, 1.01325 bar a), gas 80% CH₄ / 20% CO₂.
- Demand: 365 daily-average MW values; MWh = MW × 24.

## Value provenance — tag every number
Every parameter in code/JSON/reports is OFFICIAL, DERIVED (show formula), or ASSUMED
(state rationale). Never present an ASSUMED value as a requirement. If a physical
quantity is missing, ask the user rather than invent it.

| Value | Setting | Tag / rationale |
|---|---|---|
| Brine cp | 4100 J/(kg·K) | ASSUMED (technical guide illustrative value) |
| Well fluid props in DPDT | 1030 kg/m³, 0.4 mPa·s, cp 4100 | OFFICIAL/ASSUMED; applied at runtime by patching `gemini_simulator.well_flow.PVTConstantSTP` |
| HEX/boiler/CHP fluid props | `fluid_density` 1030, `specific_heat` 4100 | same props used on both HEX sides (ASSUMED simplification) |
| Well trajectory | vertical to 2500 m TVD (deeper in the depth ladder), production/injection tubing ID 0.178 m (7-inch casing) | ASSUMED |
| ESP setting depth | design variable: shallowest depth (10 m steps, ≥ 100 m above the reservoir) with intake ≥ 30 bar at the flow cap → 660–710 m for s1.8 at 300 m³/h | ASSUMED 30 bar gas-handling limit (GLR 0.8; free gas not modelled); hard engineering check |
| Tubing velocity | ≤ 4 m/s at the maximum flow (0.178 m ID: 3.35 m/s at 300 m³/h) | ASSUMED guideline; hard engineering check |
| Roughness | 4.5e-5 m | ASSUMED (commercial steel) |
| Productivity / injectivity index | 12.1 m³/h/bar (both wells) | DERIVED: 2πkh/(μ ln(re/rw)), k=200 mD, h=100 m, μ=0.4 mPa·s; ASSUMED re/rw=1e4, skin 0 |
| Injector reservoir pressure | 250 bar | OFFICIAL ("same reservoir") |
| Producer wellhead temperature | 85 °C nominal | DERIVED: T_wh = T_res − U·π·ID·L·(T_res − T_form,mean)/(ṁ·cp), U = 10 W/m²K (code's value), T_form,mean = 49.5 °C → ~0.44 MW loss; recomputed per solved flow by the run script |
| Separator `gas_water_ratio` | 0.8 Nm³/m³ | OFFICIAL (GLR) |
| Gas density | 0.9653 kg/Nm³ | DERIVED: (0.8·16.043 + 0.2·44.01)/22.414 |
| Gas `caloric_value` (LHV) | 29.67 MJ/kg (28.64 MJ/Nm³) | DERIVED from 0.8 × CH₄ LHV 35.8 MJ/Nm³ (standard value) |
| Gas emission factor | 68.6 kg CO₂/GJ | DERIVED: 1.0 Nm³ CO₂ per Nm³ gas (0.8 combustion + 0.2 pass-through) × 1.9635 kg/Nm³ ÷ 28.64 MJ/Nm³ |
| Electricity emission factor | 0.3 kg CO₂/kWh | ASSUMED (GEMINI example) |
| Heating return temperature | 60 °C (sensitivity 50 / 70 °C) | ASSUMED |
| Cooling | absorption chiller, COP_th 0.7, driven by geothermal heat; electric chiller backup COP 5.0 | ASSUMED |
| Cooling supply / return | 20 °C (OFFICIAL) / 26 °C (ASSUMED) | |
| 330-day schedule | per doublet: 35 maintenance days each, staggered (non-overlapping) in the summer low-demand window; with 1 doublet the backup covers its 35 days | ASSUMED schedule; rule confirmed by the organizers (Discord, 2026-11-01): source availability, demand met all 365 days |
| Separator / filter temperature drops | 0.2 K each | ASSUMED (short insulated surface equipment) |
| Brine flow Q per doublet | design/control variable, 50–300 m³/h | solved via `esp_freq_hz` in 30–70 Hz (ASSUMED VSD range); else wellhead pressure in [surface floor, 30 bar] |
| Wellhead pressure | 3 bar nominal, never below the floor | floor = 1.0 bar min surface pressure (ASSUMED) + surface Δp(Q) |
| District secondary flow | heating demand per doublet / (ρ·cp·(100 − 60 °C)) | DERIVED per day |
| HEX UA | design parameter; 250 kW/K is one option | ASSUMED (GEMINI example) |
| Checker tolerances | supply T ± 0.5 K, implied pump η ± 0.001, volume balance 1e-6 rel., flow ± 0.01 m³/h, brine ΔT + 0.001 K (numerical) | ASSUMED; brine ΔT = producer wellhead → injector wellhead |
| ESP size | flow-scale s (flow ×s, power ×s, same η shape): s1.0 = 10 stages (max ~176 m³/h), s1.8 = 24 stages (300 m³/h at ~63 Hz) | ASSUMED (`projects/candidates_2027.json`) |
| Heat pump | Lorenz η 0.45, COP cap 6.0, sink out 100 °C (sensitivity: η 0.5, no cap) | ASSUMED |
| Absorption chiller | hot end of the brine (after filter_a, before HEX), COP_th 0.7, drive inlet ≥ 75 °C, drive outlet ≥ 70 °C | ASSUMED (single-effect LiBr; 70 °C outlet added by Claude) |
| Produced gas | GEMINI CHP first (η 0.8, 1/3 el, 2/3 heat) into the 100 °C top-up; heat pump covers only the lift CHP cannot; then boiler; flared only if heat unusable | ASSUMED dispatch |
| Gas handling (agent design variable) | a) `chp`: all produced gas to CHP; b) `co2_reinject`: CO₂ (20 mol%, OFFICIAL) separated and reinjected with the brine, CH₄ to CHP, EF 68.6 × 0.8 = 54.9 kg CO₂/GJ (DERIVED), 0.1 kWh/kg CO₂ separation + compression (ASSUMED); c) `reinject_all`: no combustion, 0.1 kWh/kg gas compression (ASSUMED) | dissolution checked (`gas_solubility.py`, DERIVED): IAPWS G7-04 Henry + Poynting, Weisenberger–Schumpe salting-out (salinity from 1030 kg/m³, conservative reading at reservoir T ≈ 2.1–2.3 mol/kg NaCl), Peng–Robinson gas phase; hard check `gas_dissolution`: margin ≥ 1 at reservoir P/T and dip-tube depth < well depth; wellhead margin reported |
| N-1 resilience | unplanned outage of one doublet on the peak heating (28 Jan) and peak cooling (19 Jul) days; installed backup = max(planned peak, N-1) | ASSUMED case |
| CHP electricity | offsets ESP / injector / HP / chiller; no export credit | ASSUMED |
| External gas | 56.6 kg CO₂/GJ, 35.8 MJ/Nm³ | ASSUMED (pipeline natural gas) |
| Produced gas CO₂ | emitted whether burned or flared | ASSUMED |
| Dispatch | 5 m³/h grid; maintenance windows in May–Sep at lowest H + C/0.7 | ASSUMED |
| Other well depths | T = 12 + 30·z/1000; P = 250 + ρ·g·(z − 2500) (hydrostatic from the official point); vertical wells, drilled m = 2·n·z | DERIVED |
| Conventional reference | gas boiler η 0.90 (56.6 kg/GJ) + electric chiller COP 5.0, grid 0.3 kg/kWh → 26 706 t CO₂/yr | ASSUMED (user decision) |
| Example carry-overs | ESP 10 stages (HC27000 curve; 650 m only as the placement start), separator & filter resistances, splits 0.8/0.2, boiler/CHP η 0.8 | ASSUMED (GEMINI doublet_plant.json values) |

## Ranking rule (user decision, 2026-11-02)
1. Hard constraints: pass/fail (daily checker + annual 330-day, demand-met-365 and well checks).
   Backup peak duties (boiler, electric chiller) are reported per candidate so a 1-doublet
   design with backup and a staggered design are compared on equal terms.
2. Among feasible candidates minimize, in order: external gas → emissions → net grid
   electricity import → number of doublets → total drilled metres (final tie-break).
   Tie tolerance (approved 2026-11-03): values within max(1%, abs) count as equal so the next
   metric decides; abs = 0.1 GWh external gas, 10 t emissions, 0.01 GWh grid.
   External gas 0.1 GWh (user decision, 2026-11-03, DERIVED): < 0.1% of the reference's
   124.1 GWh gas; differences below this are below model resolution (daily averages, 0.05 K
   dispatch tolerance, ASSUMED brine properties). With 0.01 GWh the depth flipped on
   0.01–0.08 GWh/yr differences (≈ 2–15 t CO₂) in 8 of 10 sensitivity cases.
3. Parsimony (candidates walked in order of doublets, then depth):
   - an extra doublet is accepted only if it improves external gas or emissions by ≥ 5%
     versus the incumbent (relative improvement from a zero base = 0%);
   - depth is explored in 250 m steps from 2500 m (max 4000 m, ASSUMED); each deeper step
     is accepted only if emissions improve by ≥ 5% vs the previous accepted depth. The
     agent climbs until a step fails and logs the marginal abatement (t CO₂/yr per extra m).
   - (user decision, 2026-11-03) A depth or doublet step whose improvement is within the
     tie tolerance of the 5% threshold counts as NOT meeting it (conservative: drilling cost
     and risk are not modelled): the saving must exceed 5%·base by more than the metric's tie
     tolerance (`run_candidates.threshold_test`; for emissions max(10 t, 1%) → ≈ 6% in
     practice). Such candidates are flagged `marginal` and reported as marginal sensitivity
     cases (3500 m: −4.994%, 0.26 t/yr per m, wellhead 114 °C vs 107 °C at 3250 m).
4. State ACCEPTED / REJECTED + reason for every candidate (`run_candidates.rank`).

## Heating architecture (implemented)
Cascade per active doublet:
0. Absorption chiller generator at the hot end of the brine (in the GEMINI chain as a
   zero-resistance filter whose temperature drop = drive heat); electric chiller (COP 5.0) for the rest.
1. HEX preheats district water 60 → ~80 °C from the brine.
2. Heat pump (HeatpumpBasic equations, root-solved) on the brine leaving the HEX lifts the
   share of district water CHP heat cannot cover to 100 °C; brine ≥ T_wellhead − 40 K.
3. 100 °C top-up: CHP on produced gas → boiler on remaining produced gas → external gas.
- Use the full 40 K brine ΔT where possible (producer wellhead → injector).

## Known code facts (verified 2026-11-02, development @ d86e8bb)
- Producer flow is an OUTPUT of the nodal solve (set via wellhead pressure / esp_freq_hz).
- ESP efficiency is not a parameter; it emerges from the curves (example run: 58%).
- Reservoir temperature is unused; wellhead temperature is a boundary input.
- Well PVT is constant (no T/P dependence), so the solved flow does not depend on temperature.
- Separator `gas_water_ratio` = GLR; gas composition is unused; wells have gas fraction 0.
- Boiler/CHP have no temperature setpoint; the CHP is always 1/3 electric, 2/3 heat.
- kpi.py only works with doublet_plant.json component names and fixed 1050/4200.
- `HeatpumpBasic` exists but isn't in the registry; there is no cooling model.
- Solver: single pass, fixed boundary inputs — a daily loop must be driven externally.
- Injector wellhead pressure floors at 0.001 bar when the hydrostatic column over-delivers.
- Example baseline output (unchanged doublet_plant.json): Q = 129.02 m³/h,
  T_s_out = 53.97 °C, power_plant = 5.825 MW, 4082.05 kg CO₂/day.
- ESP head = stages·(f/60)²·poly(actual flow): frequency does NOT extend the flow range.
  The HC27000 curve gives zero head above 280 m³/h at any frequency, and at 70 Hz the
  challenge doublet reaches only ~176 m³/h → 300 m³/h needs a different (bigger) pump curve.
- Surface Δp is linear in Q (filter_a dominates: ~3 bar at 300 m³/h).
- Deep wells: the HEX gets a primary-side bypass (duty capped so district water ≤ 100 °C and
  brine ≥ T_wellhead − 40 K). The ESP is placed per design (`Plant.place_esp`): intake rises
  ~1 bar per 10 m of setting depth, and the intake at a fixed setting falls only slowly with
  reservoir depth (extra tubing friction), so 660 m (2500 m well) → 710 m (3500 m well).
  `esp_intake_pressure` and `tubing_velocity` are annual hard checks (`Plant.engineering`).
  Wellhead T > 100 °C from 3000 m exceeds PVTConstantSTP's stated range (constant properties
  extrapolated). Free gas at the ESP intake (GLR 0.8) is not modelled.
- `HeatpumpBasic` is NOT robust: its Nelder-Mead solve diverges at low lift / small sink flow
  (COP ~0, Th_out of hundreds of °C), its `Ts_in_minimum` fallback returns nonsense
  (e.g. 830 °C at COP 1.00), and `get_output()` returns its internal dict (copy it).
  daily_model.py solves the SAME two equations (Lorenz COP + energy balance) with a
  bracketing root finder and logs HeatpumpBasic's COP as a cross-check.
  Repro + proposed upstream fix: `outputs/evidence/heatpumpbasic_issue.md`
  (`repro_heatpumpbasic.py`).

## Code map (hackathon_work)
- `doublet_model.py`: `run_case(Q_target, UA, demand_W, n_doublets)`, control solver, KPIs, checker case.
- `constraints.py`: `check_constraints(case, limits)` → PASS / FAIL / MISSING per constraint.
- `run_doublet_challenge.py`: CLI (`--flow`, `--ua`, `--date`, `--n-doublets`), logs to `outputs/runs/`.
- `test_constraint_checker.py`: negative tests → `outputs/evidence/constraint_checker_tests.{txt,json}`.
- `daily_model.py`: `Plant(candidate, settings).simulate_year(H, C)`; GEMINI brine chain per day +
  setpoint surface model (HEX → heat pump → boiler; absorption → electric chiller), dispatch, 330-day schedule.
- `run_candidates.py`: runs `projects/candidates_2027.json` (base + sensitivities) →
  `outputs/candidates/<case>/` (per candidate daily.csv, summary.json, daily_supply.png;
  comparison.csv/.md, ranking.json). `_previous_run_v1/` = first run (before the 2026-11-02 changes).
- `reference_case.py`: conventional boiler + electric chiller reference → `outputs/reference/summary.json`.
- `design_agent.py`: task 6 agent (`--backend rules|claude_cli`, `--budget`); scenario A (heating
  return removed → stops and asks) + scenario B (design loop) → `outputs/agent/decision_log.jsonl`,
  `agent_trace.md`, `designs/` (validated GEMINI brine-chain JSON per candidate), `cache/` (gitignored).
  Design space: n 1–3, flow cap 50–300, ESP s1.0/s1.8, UA 250/500/1000 kW/K, depth 2500–4000 m
  in 250 m steps, gas handling chp / co2_reinject / reinject_all; budget 16; `--clear-cache` for honest timings
  (~2 s per annual evaluation incl. ESP placement). Rules search: n → n+1 if gas-reliant, HEX, ESP, depth ladder,
  then gas options at the accepted depth (an accepted gas option re-opens the ladder), n+1, and 1 doublet at the
  accepted depth. Every summary carries N-1 duties and installed backup.
  claude_cli backend: bundled VS Code `claude.exe` if not on PATH (or $CLAUDE_CLI); `-p --output-format
  json --tools "" --no-session-persistence`, neutral cwd; outputs in `outputs/agent/claude_cli/`.
  `--retrace NOTE` rebuilds agent_trace.md from a saved decision_log.jsonl (no calls, no simulation).
  `REQUIRED_INPUTS`: the 12 inputs not in the organizers' data (heating/cooling return T, brine cp,
  absorption COP + drive inlet/outlet T, electric chiller COP, HP η / COP cap, produced-gas / external-gas /
  electricity emission factors), each with unit, why, ASSUMED plausible range, provenance and where it lives
  (project or settings). All are checked at startup; none is ever invented. `--remove NAME[,NAME]` (or `all`;
  default heating_return_T) removes them in scenario A: the default run halts with the full list (judges' test i).
  `--interactive`: the agent asks in the terminal for each (AGENT ASKED / USER ANSWERED, timestamped in
  decision_log.jsonl and agent_trace.md), accepts only a number in the plausible range, re-asks otherwise,
  'q' or no stdin halts; answers go to `project_with_user_answers.json` / `settings_with_user_answers.json`
  and the design loop continues. Outputs in `outputs/agent/interactive/`; the default run needs no input.
- `sensitivity.py`: one-at-a-time sensitivity of the final pick (heating return 50/70 °C, HP η 0.40/0.50,
  absorption COP 0.6/0.8, gradient 27/33 °C/km, brine cp 4000/4200) + a fresh agent run per case →
  `outputs/sensitivity/{summary.json, sensitivity.md}` (tornado in dashboard panel 10).
- `make_dashboard.py`: reads existing outputs only → `dashboard/index.html` (self-contained, ECharts 5.5.1
  vendored in `dashboard/vendor/`, Apache-2.0) + 300 dpi panel PNGs in `outputs/figures/` via headless Edge.

## Prioritized tasks
1. [done] `projects/doublet_challenge.json` + run script with logged inputs/outputs.
2. [done] Constraint checker + negative tests (350, 30 m³/h, 45 K, 4 doublets, 77.75 °C,
   curve-efficiency pump power, volume imbalance, missing cooling).
3–5. [done, one daily model] 365-day driver + 330-day schedule, 100 °C cascade
   (HEX → heat pump → boiler, no CHP), absorption + electric cooling; 3 candidates compared.
   v2 (absorber at hot end, CHP first, HP η 0.45 / cap 6, ranking): C1 (2 doublets, s1.8,
   UA 1000) ACCEPTED; C2 rejected (extra doublet −0.2% emissions); C3 rejected (13.5 GWh external gas).
   Open caveats: backups unlimited (unmet = 0 by construction); peaks are daily averages
   (no hourly peaks); no capex/opex yet.
6. [done] Design agent (rules backend, depth ladder, gas handling): 14 annual evaluations, all four
   judges' tests PASS; final pick n2_q300_s1.8_ua1000_z3500_co2ri (2 doublets at 3500 m, 117 °C
   reservoir, CO₂ reinjected, CH₄ to CHP): 3 983 t CO₂/yr, 85.1% below the conventional reference,
   external gas 0.016 GWh (CHP on all gas at the same design: 4 891 t). Re-run 2026-11-03 with the
   0.1 GWh external-gas tie tolerance: 3500 m co2ri (−6.3% vs 3250 m) is now taken; 3750 m (−0.8%)
   is not. reinject_all at 3500 m: 1 952 t but 0.271 GWh external gas → ranked out. 3 doublets:
   3 979 t (−0.1%) → ranked out. 1 doublet (2500 m: 28.6 GWh external gas; 3500 m: 36.5 GWh) is
   feasible with backup and ranked out. N-1 at the pick: 15.1 MWth boiler (28 Jan), 2.1 MWth boiler
   and no electric chiller (19 Jul). LIMITATION: wellhead 114 °C at 300 m³/h exceeds the
   PVTConstantSTP range (100 °C), so constant brine properties are extrapolated.
   Gas dissolution (gas_solubility.py): CO₂ (co2ri) margin 7.3 at the injector wellhead
   (5.1 bar(g), 75 °C) and 148 at the reservoir; reinject_all margin 0.11 at the wellhead (bubble
   point 61.5 bar(g): dip tube to ≥ 558 m) and 4.8 at the reservoir; its ASSUMED 0.1 kWh/kg
   compression is below the DERIVED minimum 0.197 kWh/kg.
   Sensitivity (10 cases, fresh agent runs): pick changes in 5 (gradient 27 → 3750 m, 33 → 3000 m;
   heating return 50 → 3250 m (3500 m step only −1.6%); brine cp 4000 → 3250 m (−5.96%, within
   the tie tolerance of the 5% threshold); absorption COP 0.6 → 3 doublets (external gas 0.158 vs
   0.005 GWh)). All cases pass the hard constraints.
7. Report artifacts: comparison tables, plots, ≤5-page report or ≤10 slides, ≤5 min pitch.
