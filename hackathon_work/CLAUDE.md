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
| Well trajectory | vertical to 2500 m TVD, ID 0.15 m | ASSUMED |
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
| 330-day schedule | per doublet: 35 maintenance days each, staggered in the summer low-demand window, never all doublets off at once. Sensitivity: global 35-day outage | ASSUMED — interpretation pending organizer confirmation |
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
| CHP electricity | offsets ESP / injector / HP / chiller; no export credit | ASSUMED |
| External gas | 56.6 kg CO₂/GJ, 35.8 MJ/Nm³ | ASSUMED (pipeline natural gas) |
| Produced gas CO₂ | emitted whether burned or flared | ASSUMED |
| Dispatch | 5 m³/h grid; maintenance windows in May–Sep at lowest H + C/0.7 | ASSUMED |
| Other well depths | T = 12 + 30·z/1000; P = 250 + ρ·g·(z − 2500) (hydrostatic from the official point); vertical wells, drilled m = 2·n·z | DERIVED |
| Conventional reference | gas boiler η 0.90 (56.6 kg/GJ) + electric chiller COP 5.0, grid 0.3 kg/kWh → 26 706 t CO₂/yr | ASSUMED (user decision) |
| Example carry-overs | ESP 10 stages / 650 m (HC27000 curve), separator & filter resistances, splits 0.8/0.2, boiler/CHP η 0.8 | ASSUMED (GEMINI doublet_plant.json values) |

## Ranking rule (user decision, 2026-11-02)
1. Hard constraints: pass/fail (daily checker + annual 330-day / never-all-off checks).
2. Among feasible candidates minimize, in order: external gas → emissions → net grid
   electricity import → number of doublets → total drilled metres (final tie-break).
   Tie tolerance (approved 2026-11-03): values within max(1%, 0.01 GWh / 10 t) count as
   equal so the next metric decides (otherwise ~0.0003 GWh of external-gas noise decides).
3. Parsimony (candidates walked in order of doublets, then depth):
   - an extra doublet is accepted only if it improves external gas or emissions by ≥ 5%
     versus the incumbent (relative improvement from a zero base = 0%);
   - depth is explored in 250 m steps from 2500 m (max 4000 m, ASSUMED); each deeper step
     is accepted only if emissions improve by ≥ 5% vs the previous accepted depth. The
     agent climbs until a step fails and logs the marginal abatement (t CO₂/yr per extra m).
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
  brine ≥ T_wellhead − 40 K). With the ESP fixed at 650 m, ESP intake pressure at 300 m³/h falls
  with depth (16.5 bar at 2500 m → 7.6 bar at 3250 m → 4.7 bar at 3500 m, cavitation flag);
  a deeper pump setting would be needed in a real design. Wellhead T > 100 °C from 3000 m
  exceeds PVTConstantSTP's stated range (constant properties extrapolated). Free gas at the
  ESP intake (GLR 0.8) is not modelled. 0.15 m tubing at 300 m³/h = 4.7 m/s at every depth.
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
  in 250 m steps; budget 14; `--clear-cache` for honest timings (~0.9 s per annual evaluation).
  claude_cli backend: bundled VS Code `claude.exe` if not on PATH (or $CLAUDE_CLI); `-p --output-format
  json --tools "" --no-session-persistence`, neutral cwd; outputs in `outputs/agent/claude_cli/`.

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
6. [done] Design agent (rules backend, depth ladder): 9 annual evaluations, all four judges'
   tests PASS; final pick n2_q300_s1.8_ua1000_z3250 (2 doublets at 3250 m, 110 °C reservoir):
   5 376 t CO₂/yr, 79.9% below the conventional reference; 3500 m step rejected (−2.8% < 5%).
7. Report artifacts: comparison tables, plots, ≤5-page report or ≤10 slides, ≤5 min pitch.
