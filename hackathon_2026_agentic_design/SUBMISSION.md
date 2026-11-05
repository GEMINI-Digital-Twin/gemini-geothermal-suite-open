# GEMINI Agentic Geothermal Design Hackathon - Submission

**Participant:** Ramdhan Ari Wibawa (ramdhan@zanskar.us)
**Submission date:** 3 November 2026
**Deliverables (per the kick-off instructions):** technical report `GEMINI_Hackathon_Report_Ramdhan_Wibawa.pptx` (10 slides); 5-minute video pitch with `GEMINI_Hackathon_Pitch_Ramdhan_Wibawa.pptx`; code pushed to the GEMINI repository and attached as a zip; agent-interaction evidence in `gemini_design_agent/outputs_claude/INTERACTION_EVIDENCE.md`. This document is the long-form companion to the deck.

## 1. What we built

An agentic AI orchestration workflow that selects, sizes and validates a deep-geothermal heating
and cooling system for the supplied 2027 demand profiles. The agent uses the GEMINI digital-twin
physics models for every subsurface and well-engineering evaluation and our own component models
for the surface heating and cooling plant, exactly as the scope note requires (GEMINI does not
contain an end-to-end heating-and-cooling optimiser; the system-level design agent is ours).

The workflow is a closed loop:

```
propose design -> evaluate with the twin (365-day power/energy balance)
   -> detect violations -> diagnose -> repair -> re-evaluate
   -> explore alternatives -> right-size -> rank -> report
   -> closed-loop geothermal management over the 25-year project life
```

Two orchestration modes drive the same toolbox:

| Mode | Where | Purpose |
|---|---|---|
| Claude-orchestrated | `gemini_design_agent/outputs_claude/` | Claude chose each design move and wrote the rationale (transcript in `orchestration_log.md`, decisions in section 6 of the report) |
| Rule-based | `gemini_design_agent/outputs/` | Deterministic engineering heuristics; fully offline and reproducible, explores 16 structural alternatives and repairs each |

Both converge on the same design.

## 2. Selected design

| Item | Value |
|---|---|
| Doublets | 3 (one in a 35-day maintenance window at a time, staggered into the low-load season, so each runs 330 days and supply never drops) |
| Reservoir depth | 3,500 m TVD (117 C reservoir, ~114 C wellhead), 3,780 m MD deviated wells |
| Casing | 9-5/8" (217 mm ID) producer and injector |
| ESP | 1,000 m setting depth, 32 stages, BEP 170 m3/h, VSD 30-65 Hz; intake 70 bar vs 29 bar bubble point |
| Heating | Direct plate heat exchange at 100 C (105 of 112 GWh); 2.5 MW high-temperature heat pump for cold-spell top-up |
| Cooling | 10 MW single-effect absorption chiller driven by the brine (all 23.7 GWh); no electric chiller |
| Corrosion | Inhibitor + GRE-lined tubing (GEMINI de Waard-Milliams: 8 mm/yr un-mitigated at 20 mol% CO2) |

| KPI (year 1) | Value |
|---|---|
| Heat / cooling delivered | 111.7 GWh / 23.7 GWh, zero unmet |
| Electricity | 7.8 GWh/yr (ESP 3.6, injection 0.9, heat pump 1.4, chillers 1.9) |
| System COP | 17.3 |
| Geothermal (non-electric) share | 94 % |
| Flow per doublet | peak 221 m3/h, mean 136 m3/h (never at the 300 or 50 m3/h caps) |
| Max brine cooling | 40.0 C (at the cap on the peak days) |
| Indicative cost | capex 67 MEUR, 8.6 MEUR/yr, 63.8 EUR/MWh |

Every challenge constraint passes: 1-3 doublets, 50-300 m3/h per doublet, 40 C brine cooling,
70 % pump efficiency, equal produced and injected volume, 330 operating days per doublet, 100 C
heating supply, 20 C cooling supply. Additional engineering guards also pass: ESP intake above the
gas bubble point, tubing velocity below the API RP14E erosional velocity, injection wellhead
pressure within limit.

## 3. Why this design (major decisions)

1. **One doublet is infeasible.** The 330-day rule leaves 35 days without supply; two or more
   doublets allow staggered maintenance.
2. **The 40 C brine-cooling cap, not temperature, sets heat per doublet** (~13.4 MW at
   300 m3/h). The 30 MW peak therefore needs three doublets with direct heating. Two doublets at
   3,500 m fail on 16 peak days even with a 15 MW heat pump, because once the brine is at the
   40 C floor the heat pump has no source left.
3. **The specified 2,500 m is too cold for a 100 C supply.** Wellhead brine is 85 C, so all heat
   must be lifted by a 31 MW heat pump: 36 GWh/yr electricity, COP 3.8, 86 EUR/MWh. The
   challenge allows other depths with hydrostatic pressure and the 30 C/km gradient.
4. **3,000 m is the worst of both worlds** (wellhead ~99 C, still below the 103 C needed for a
   3 C approach): deep wells plus a large heat pump, 92 EUR/MWh.
5. **3,500 m unlocks direct supply and full-COP absorption cooling**: electricity falls to
   7.8 GWh/yr, COP 17.3, 63.8 EUR/MWh.
6. **4,000 m does not pay**: hotter brine does not raise the cap-limited heat per doublet, so
   well capex rises for little gain (70.7 EUR/MWh).
7. **Absorption cooling beats electric chillers** at this temperature: 4.3 GWh/yr and
   0.65 MEUR/yr saved; the brine is split in parallel between the heating and cooling trains
   and the split is optimised daily.
8. **ESP placement is governed by gas.** At GLR 0.8 Nm3/m3 (80 % CH4) the bubble point is
   ~29 bar; the ESP sits at 1,000 m so the intake stays 40 bar above it.
9. **Right-sizing**: the heat pump is trimmed from 7.5 to 2.5 MW (max used 1.8 MW) and the ESP
   frame re-selected to the actual peak flow.

## 4. How GEMINI is used

| GEMINI model (`gemini_model`) | Role |
|---|---|
| `reservoir.reservoir_pressuredrop.bottomhole_skin_dp` | productivity / injectivity index (radial Darcy with skin) |
| `reservoir.inflow_performance.IPR` | production and injection bottom-hole pressure vs flow |
| `well.pressure_drop.DPDT` + `fluid.pvt_water_stp.PVTConstantSTP` | wellbore pressure and temperature, marched in 100 m segments with the geothermal gradient as ambient, producer and injector |
| `pump.esp.ESP` | stage head curve; stage count and VSD frequency solved from the required head |
| `corrosion.co2_corrosion.CO2Corrosion` | CO2 corrosion rate -> material decision |
| `erosion.erosion_model.ErosionModel` | API erosional velocity -> casing ID check |

The models are called directly from the open-source package; no Docker services or databases
are needed, so the whole workflow runs from the command line in about five minutes.

## 5. Closed-loop geothermal management (beyond the brief)

The design is also run through a 25-year management loop in which the twin is re-evaluated each
year with reservoir cooling (Gringarten-Sauty breakthrough), injector skin growth and ESP wear.
The controller schedules acid stimulation and ESP workovers (every ~5 years), would retrofit
heat-pump or chiller capacity if the produced temperature fell, and recommends the
producer-injector spacing (breakthrough after 20 years at 600 m, 36 years at 800 m, beyond the
project life at the assumed 1,500 m).

## 5b. External optimiser study (petlab / py-trsqp / StoSAG)

The continuous design variables of the 3-doublet system (depth, heat-pump, absorption and electric
chiller capacities, ESP depth and frame) were handed to black-box optimisers through petlab's
backend interface: **DFTR-Filter** (py-trsqp, derivative-free trust region with output
constraints), **COBYLA** (scipy baseline) and **StoSAG** (ensemble-gradient robust optimisation
over permeability 140-220 mD, gradient 29-32 C/km and injector skin). Every candidate was re-run
at full daily fidelity and repaired by the rule-based diagnoser where the fast screening had
missed a peak day. Details: `gemini_design_agent/outputs_opt/OPTIMIZATION_REPORT.md`.

| Candidate | Depth m | HP MW | Abs MW | Annual MEUR | EUR/MWh | Expected (ensemble) | Worst (ensemble) |
|---|---|---|---|---|---|---|---|
| Agent design (Claude / rule-based) | 3,500 | 2.5 | 10.0 | 8.63 | 63.8 | 8.70 | 8.86 |
| DFTR-Filter from the agent design | 3,344 | 0.0 | 10.0 | **8.17** | **60.3** | **8.31** | **8.65** |
| StoSAG robust (ensemble mean) | 3,335 | 1.9 | 10.0 | 8.42 | 62.2 | 8.54 | 8.88 |
| COBYLA | 3,250 | 0.0 | 11.5 | 8.28 | 61.1 | 8.80 | 10.63 |
| DFTR-Filter from 2,500 m start | 3,938 | 0.0 | 0.0 (electric 10.2) | 8.86 | 65.4 | 8.91 | 9.02 |

Findings: the optimisers confirm the agent's structure (3 doublets, direct heating, absorption
cooling) and shave 5.4 % off the annual cost by stopping just deep enough for direct 100 C supply
(3,344 m) and dropping the heat pump. The design space has a cliff at ~3,250 m: COBYLA sat on it
and its worst case over the geological ensemble jumps to 10.6 MEUR, while the DFTR solution keeps
100 m of margin and stays cheapest in every realisation. Starting DFTR from the as-specified
2,500 m lands in a worse local optimum (deep wells with electric cooling), which shows why the
agent's engineering reasoning matters as the optimiser's starting point. Recommended design:
the DFTR-polished configuration if the 30 C/km gradient is confirmed by a temperature log,
otherwise the StoSAG design with its heat-pump hedge.

## 5d. Real-time ESP smart monitoring (beyond the brief)

Between the live well and the yearly controller sits an hourly ESP monitor
(`gemini_design_agent/esp_monitoring.py`). Every sample of flow, VSD frequency, intake and
discharge pressure, motor temperature, current, power and vibration is compared with the
GEMINI-based twin (affinity-scaled stage curve, inflow performance). Three detectors work on the
residuals: a robust Mahalanobis distance (minimum covariance determinant), an Isolation Forest,
and a CUSUM on the hydraulic-efficiency estimate for slow drift. A signature classifier names the
fault (gas interference, stage wear/scale, motor thermal, trip), a health index and a
remaining-useful-life estimate are updated hourly, and the health index replaces the assumed
ESP wear rate in the 25-year loop. On synthetic telemetry with four injected faults the monitor
reached 91 % recall on fault hours, 0.7 % false alarms and 100 % correct fault labels. Details and
figure: `gemini_design_agent/outputs_monitoring/ESP_MONITORING_REPORT.md`.

## 5c. Interactive dashboard

A dashboard with the selected design, constraint scorecard, daily dispatch, the agent's decision
log, alternatives, GEMINI well table, the 25-year closed loop with an equipment-health panel
(ESP efficiency, injector skin, tubing wall loss, interventions), the curves of the component
models built for this challenge, the real-time ESP monitoring panel (telemetry with detected
fault episodes, health index and RUL, alerts), and the optimiser study:
https://claude.ai/artifact/NsWjVJL11z7fZCAK5Fe4my (shared on request).

## 5e. Agent interaction evidence and LLM disclosure

An intake gate (`gemini_design_agent/intake.py`) runs before any simulation in both modes. It
lists missing inputs and asks whether to proceed, declines out-of-scope requests (power
generation, unrelated questions), and flags inputs that contradict the physics (a stated
reservoir temperature inconsistent with the gradient) without sizing the plant until resolved.
Six reproducible exchanges are in `outputs_claude/INTERACTION_EVIDENCE.md` (`python
demo_interactions.py`). LLM used: Claude (Anthropic, commercial) for the orchestrated run, with
the API key as a placeholder in the committed code; the rule-based mode reproduces the same
design with zero LLM tokens. Number of used tokens: the orchestrated run took 8 decision turns
and 7 twin evaluations, about 33k tokens in total (770 output tokens of stated hypotheses and
the final explanation, 4.5k tokens of twin answers, 32k tokens of context re-read across the
turns). This is an estimate at 4 characters per token over the logged text, because the run was
driven from a Claude Code session that does not expose API usage; the per-turn table is in
`outputs_claude/INTERACTION_EVIDENCE.md` section 8 and the totals in `outputs_claude/llm_usage.json`.
When the agent is run through the API (`--mode claude`), `response.usage` is metered on every
turn and the exact totals are written to `<out>/llm_usage.json`; the rule-based run writes zero.

Realized capacities of the selected design: heating 30.0 MW delivered on the peak day
(28.2 MW direct heat exchange + 1.8 MW heat pump; installed 3 x 13.7 MW plate HX + 2.5 MW heat
pump), cooling 10.0 MW delivered (10 MW absorption chiller installed), 111.7 GWh heat and
23.7 GWh cooling over the year with nothing unmet. Thermal storage was considered and not added:
the heat-pump top-up runs through 144- and 110-day cold stretches that a daily buffer cannot
shift, and at 94 % geothermal share seasonal storage has nothing to displace.

Libraries: Python 3.12; `gemini_model` from the GEMINI suite (imported directly, no Docker or
database); numpy, pandas, scipy, matplotlib; scikit-learn (ESP monitoring); py-trsqp, petlab and
stosag (optimiser study, vendored as sibling folders); anthropic SDK (API mode only).

## 5f. Organiser clarifications (Discord technical Q&A, 1-3 November) and how the design meets them

- **330 days means the geothermal source, not the system; the full system must supply all 365
  days.** The selected design schedules the three doublets' 35-day windows one after another in the
  low-load season (May-October), so two doublets are always available and the demand is met every
  day without a backup boiler or chiller. The dispatch figure on slide 6 shows the availability
  steps; unmet heat and cooling are zero. A single-doublet design would need backup equipment
  sized for the full peak, which is why the agent rejects it.
- **Changing depth is acceptable**, using hydrostatic pressure and the 30 C/km gradient. That is
  exactly what the agent does (3,500 m, 351 bar, 117 C).
- **Return temperatures are the designer's choice** as long as the constraints hold. We use a 60 C
  heating return and a 3 C heat-exchanger approach; the brine is never cooled more than 40 C.
- **Associated gas is a CH4/CO2 mix; several handling options are possible; grid electricity
  emission factor 0.3 kg CO2/kWh.** The gas-handling model (`components.py`, GasHandling) uses
  80 % CH4 / 20 % CO2 at GLR 0.8. For the selected design, hand-calculated from the model constants:

  | Item | Value per year |
  |---|---|
  | Associated gas | 2.59 MNm3 (CH4 2.08, CO2 0.52) |
  | Formation CO2 separated | 1,026 t |
  | CH4 fuel value (LHV) | 20.6 GWh |
  | Electricity from a gas engine at 38 % | 7.8 GWh, equal to the plant's whole electricity use |
  | CO2 from burning the CH4 (engine or flare) | 4,090 t |
  | Grid electricity, 7.8 GWh at 0.3 kg/kWh | 2,340 t (shallow heat-pump design: 10,800 t) |
  | Option A: flare CH4, buy grid power | 7,460 t CO2 |
  | Option B: gas engine on CH4, no grid import | 5,120 t CO2, and about 0.9 MEUR/yr electricity saved |
  | Venting CH4 (not an option) | 41,700 t CO2-equivalent |

  Recommendation: option B, a 1 MW gas engine running on the separated CH4 makes the plant
  electrically self-sufficient on average and cuts the CO2 balance by a third relative to flaring.
  The engine's jacket heat can also drive the absorption chiller in summer. The formation CO2 can
  be re-dissolved into the injection brine rather than vented, since injection is at 33 bar; we
  have not modelled that. The engine is a sizing note, not yet in the daily dispatch model.
- **Submission:** a pull request to the GEMINI development branch is sufficient; deadline
  Thursday 5 November, 23:59 CET. We did not modify any GEMINI model, so there are no bug fixes
  to report; the package imports `gemini_model` unchanged.

## 6. How to run

```
cd gemini_design_agent
pip install -r requirements.txt
python -m gemini_design_agent run --heating ../GEMINI_Heating_Demand_Daily_2027.csv \
    --cooling ../GEMINI_Cooling_Demand_Daily_2027.csv --out outputs --mode rule
python -m pytest tests -q        # 13 tests
```

The GEMINI repository (`gemini-geothermal-suite-open`) must sit next to the package as
`../gemini-geothermal-suite-open-main` (or edit the path in `subsurface.py`). `--mode claude`
drives the same tools through the Anthropic API when an API key is set; `claude_session.py` is
the step-by-step driver used for the Claude-orchestrated run.

## 7. Files

```
SUBMISSION.md                       this document
gemini_design_agent/README.md       technical description and layout
gemini_design_agent/gemini_design_agent/   source (spec, demand, components, subsurface, system, agent, closed_loop, report, cli)
gemini_design_agent/tests/          unit tests
gemini_design_agent/outputs_claude/ Claude-orchestrated run: DESIGN_REPORT.md, orchestration_log.md, figures, JSON, CSV
gemini_design_agent/outputs/        rule-based run: DESIGN_REPORT.md, agent_log.txt, figures, JSON, CSV
gemini_design_agent/outputs_opt/    optimiser study: OPTIMIZATION_REPORT.md, convergence figure, per-run JSON
gemini_design_agent/outputs_monitoring/  ESP smart monitoring: ESP_MONITORING_REPORT.md, figure, hourly telemetry CSV, alerts JSON
gemini_design_agent/gemini_design_agent/esp_monitoring.py, run_monitoring.py, report_monitoring.py   monitoring module, demo, report
gemini_design_agent/gemini_design_agent/optimize_ext.py, run_optimizers.py, report_opt.py   optimiser integration
```

The optimiser study needs the three repositories next to the package: `py-trsqp-main`,
`stosag-master`, `petlab-master` (plus `pip install casadi`).

## 8. Assumptions and limitations

Permeability is assumed depth-independent (200 mD); reservoir pressure is hydrostatic anchored on
250 bar(g) at 2,500 m; district return 60 C; heat-pump COP = 0.5 x Carnot; absorption COP 0.72
at >= 95 C driving temperature; costs are indicative planning figures used only to rank
alternatives; the breakthrough model is lumped and would be refined with a reservoir simulation.
