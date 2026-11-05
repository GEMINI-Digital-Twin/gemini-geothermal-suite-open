# GEMINI GeoHackathon 2026 — Agentic geothermal design

**Author:** Mahdi Izadi

An agentic AI workflow that designs a deep-geothermal district heating **and**
cooling plant for the official 2027 demand profiles. An LLM agent (Ollama, local)
proposes designs. GEMINI and complementary component models simulate all
365 days. A deterministic validator checks every challenge constraint and sends
the violations back to the agent, which repairs and improves the design.

```
 demand CSVs ─► agent (LLM) ─► design JSON ─► schema check ─► GEMINI wells/ESP/separator/injector
                  ▲                                            + HEX + heat pump + chillers
                  │                                            365-day lowest-CO2 dispatch
                  └──── violations + KPIs + history ◄──── deterministic validator (18 checks)
```

The LLM never decides PASS/FAIL. Only the validator does, from the simulated
numbers. No check reads a typed-in value: supply temperatures are computed from
the heat actually delivered, and every heat-pump day is re-solved with GEMINI's
own `HeatpumpBasic`.

## Result — designed by the LLM agent (Ollama qwen2.5:7b, run 3)

| | Agent's design (`agent_best_design.json`) |
|---|---|
| Doublets | **3**, wells 3,300 m TVD (111 °C reservoir, 104 °C at the wellhead) |
| Heat exchanger | 2,000 kW/K per doublet. The brine is hot enough to heat the water to 100 °C directly, so the heat pump is not needed |
| ESP | 45 stages at 1,000 m, variable speed → 55–202 m³/h per doublet |
| Backup gas boiler | 35 MW installed, **peak use 3.5 MW** |
| Chillers (20 °C) | 15 MW electric (COP 6.45, peak use 10 MW) + 8 MW absorption (peak use 3.7 MW) |
| **CO₂** | **6,626 t/year**, against **26,386 t** for the same demand without geothermal (**−74.9 %**) |
| Heat from geothermal | 87.1 % (produced gas 10.5 %, backup boiler 2.4 %) |
| Constraint checks | **18/18 PASS** (reproduced with `python run_full_year.py`) |

How the agent got there (`agent_log.md`, 20 iterations):
1. It started with 1 doublet at 2,000 m. The validator reported FAIL, with a heating supply of only 92.8 °C, cooling at 23 °C, and shortfalls of 3.6 MW heating and 5 MW cooling.
2. It added doublets and chiller capacity and got its first PASS at iteration 2 (11,223 t). 3 doublets brought it to 8,396 t.
3. It deepened the wells step by step (2,800 → 3,000 → 3,100 → 3,200 → 3,300 m) and added ESP stages, reaching 6,626 t.
4. It tested 3,400 m, saw CO₂ rise (6,693 t), and kept 3,300 m.
5. It tried to stop four times too early. The workflow refused each time because directions were still untried, and each refusal led to a better design.
6. Two exact repeats were rejected without a simulation.

**Engineering review of the agent's design.** The plant is valid and its CO₂ is the
lowest found. However, the LLM **oversized the backup units**: the boiler is used at most
3.5 MW of its 35 MW, the electric chiller 10 of 15 MW, and the absorption chiller 3.7 of 8 MW.
Oversizing does not change CO₂; a right-sized plant would install about 4 MW boiler, 10.5 MW
electric chiller and 4 MW absorption chiller. The LLM's written reasoning is not always exact
either (iteration 20 says it enlarges the HEX, but the HEX was already at its maximum and the
actual change was a smaller boiler). This is why the design is judged only by the deterministic
validator, never by the LLM's text.

**Depth.** The challenge allows other depths ("use hydrostatic pressure … and the geothermal
gradient"). Going to 3,300 m assumes the official reservoir properties (200 mD, 100 m) also hold
there, and drilling cost is not counted. If the depth must stay at the 2,500 m reservoir midpoint,
the best design is **8,324 t** (3 doublets; grid search).

## Plant and engineering decisions

```
reservoir (depth z: T = 12 + 30·z/1000 °C, p hydrostatic, k = 200 mD, h = 100 m)
  └─ producer well + ESP (GEMINI ProducerWell, nodal; ESP at 1,000 m, variable speed)
       └─ separator (GEMINI) ── gas 0.8 Nm³/m³ (80 % CH₄ / 20 % CO₂) ─► boiler 80 % / CHP 20 % (GEMINI)
       └─ filter A ─► plate HEX (GEMINI HeatExchanger) ─► heat-pump evaporator ─► filter B
                                                                └─► injector well + pump (GEMINI InjectorWell)
district return 40 °C ─► HEX ─► heat-pump condenser ─► 100 °C supply ─► absorption chiller ─► 20 °C cooling
electricity ─► ESP, injector pump, heat pump, electric chiller (20 °C cooling)
backup gas boiler (100 °C) ─► maintenance block and peaks
```

| Decision | Choice | Why |
|---|---|---|
| Number of doublets | 3 (chosen by the agent) | 1 doublet leaves the 30 MW January peak to gas (14,924 t); 3 doublets cover 87 % of the heat |
| Well depth | 3,300 m (agent; allowed by the PDF) | hotter brine (104 °C at the wellhead) heats the water to 100 °C directly, so no heat-pump electricity is needed; 3,400 m was tested and was worse |
| Heat cascade | HEX first, heat pump second | the hottest brine is used directly; the heat pump only lifts the rest, so its COP stays high |
| Brine-cooling limit | heat pump may not cool the brine below T_producer − 40 °C | enforces the 40 °C cap physically, so it can never be exceeded |
| Flow control | variable-speed ESP, 50–300 m³/h per doublet, chosen daily | follows the seasonal demand; low flow in summer saves pump power and produced-gas CO₂ |
| ESP setting depth | 1,000 m | keeps the pump intake above 10 bar at high flow (limits gas break-out) |
| Produced gas | burned on site (boiler 80 %, CHP 20 %) | uses the methane's energy instead of venting it; its CO₂ is counted |
| Cooling | absorption chiller on 100 °C geothermal heat + electric chiller | spare summer geothermal heat makes cooling; the electric chiller covers the maintenance block and the rest |
| 330 operating days | one contiguous 35-day maintenance block, July–August | placed by the dispatcher where switching off costs the least CO₂ (lowest heating demand) |
| Backup boiler | sized by the agent (peak use 3.5 MW) | covers the maintenance block and peaks geothermal cannot |
| Pump power | Δp·Q / 0.70 for ESP and injector | the challenge's simplified 70 % hydraulic efficiency |

## Benchmarks

| Reference | CO₂ t/yr |
|---|---|
| No geothermal (gas boiler + electric chiller for the whole demand) | 26,386 |
| Best 1-doublet design (grid search, `optimize_design.py`) | 14,924 |
| Best 2-doublet design | 8,760 |
| Best 3-doublet design (3,500 m) | 6,725 |
| Best design with depth fixed at the 2,500 m reservoir midpoint | 8,324 |
| **LLM agent, run 3** (14 simulations) | **6,626** (−1.5 % vs. the grid: found 3,300 m with 45 stages, which is outside the grid) |
| Offline rule-based agent (22 simulations) | 6,721 (−0.1 %) |

## Agent runs (`agent_runs/`)

| Run | Agent / model version | Best CO₂ | What happened |
|---|---|---|---|
| 1 | qwen2.5:7b, 12 it., earlier model | 10,596 t | Loop worked and the validator caught shortfalls, but the model repeated a failing design 5× and believed fewer doublets lower CO₂ |
| 2 | qwen2.5:7b, after workflow fix, earlier model | 8,080 t (7,502 t re-simulated now) | Repaired violations, improved monotonically, stopped itself too early at 3,200 m |
| **3** | **qwen2.5:7b, current model and workflow** | **6,626 t** | Finish refused 4× while directions were untried; explored depth to 3,400 m and back; beat the grid |
| — | offline rule agent, current model | 6,721 t | deterministic reference policy |

Workflow fixes between runs: exact repeats are rejected without simulation (after run 1);
the feedback shows the effect of the last change versus the best design and lists untried
directions (after run 1); "finish" is refused while untried directions remain (after run 2);
the prompt states key engineering facts, each **computed from the model** (226 kg CO₂ per MWh
of backup gas heat, 1.58 kg CO₂ per m³ of brine, ≈ 3,233 m depth beyond which the brine alone
reaches 100 °C, 10 MW peak cooling).

## How to run

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows   (Linux/Mac: source .venv/bin/activate)
python -m pip install -r hackathon_submission/requirements.txt
cd hackathon_submission

# 1. agentic design loop  (needs Ollama:  ollama pull qwen2.5:7b)
python agent.py --model qwen2.5:7b --iterations 20
#    no LLM available? deterministic rule-based agent:
python agent.py --offline --iterations 30

# 2. full-year report of the agent's design (18 checks, CSVs, plots)
python run_full_year.py

# 3. optional benchmark + sensitivity study (~2 min)
python optimize_design.py
```

## Official requirements → where they are met

| Requirement (challenge PDF, 28 Oct 2026) | Implementation |
|---|---|
| Agentic AI: interpret demand, generate configurations, run checks, detect violations, iterate | `agent.py`: the LLM gets a demand summary, rules, history, violations and KPIs; proposes JSON; schema check; simulation; validator; repeat. Every step and reason is in `agent_log.md` |
| Use GEMINI for subsurface/well engineering; complementary models for heating/cooling | GEMINI: producer well + ESP (nodal), separator, filters, injector well + pump, produced-gas boiler/CHP, `HeatExchanger`, `HeatpumpBasic` (cross-check). Complementary: fast Lorenz heat-pump solver, chillers, dispatch |
| Demand: 365 daily MW; MWh = MW × 24 | 111.67 GWh heat / 23.74 GWh cooling reproduced |
| Reservoir 2,500 m, 100 m, 30 °C/km, 12 °C, 250 bar, 200 mD | T = 12 + 30·z/1000; p hydrostatic (250 bar at 2,500 m); PI from Darcy with k = 200 mD, h = 100 m, μ = 0.40 mPa·s → 11.2 m³/h/bar |
| Other well depths via hydrostatic pressure and gradient | Depth is a design variable (2,000–3,500 m) |
| Brine 1,030 kg/m³, 0.40 mPa·s | Used in GEMINI well hydraulics (new optional `pvt` input), HEX and heat pump |
| GLR 0.8 Nm³/m³, 80 % CH₄ / 20 % CO₂, Nm³ at 0 °C, 1.01325 bar | Gas density 0.969 kg/Nm³; heat from CH₄ only (35.88 MJ/Nm³); CO₂ = combustion + native CO₂ (checked within 1 %) |
| 1–3 doublets | Design variable |
| 50–300 m³/h per active doublet | ESP speed chosen daily within the range; checked |
| Brine cooling ≤ 40 °C, producer → injector | HEX and heat pump can never cool the brine below T_producer − 40 °C; checked |
| Pump hydraulic efficiency 70 % | ESP and injector power = Δp·Q/0.70, set from the official constant; both checked |
| Production = injection volume | GEMINI injector receives the producer flow; checked |
| 330 daily steps, daily power and energy balance | One 35-day maintenance block placed at least CO₂ cost; heat, electricity and gas balances checked every day |
| 100 °C heating supply | Supply temperature **computed** from delivered heat and district flow; checked ≥ 100 °C; GEMINI `HeatpumpBasic` confirms the heat-pump outlet |
| 20 °C cooling supply | Chilled-water supply **computed** from delivered cooling (return 26 °C); electric-chiller COP follows from the 20 °C supply (Carnot fraction); checked ≤ 20 °C |
| Explain every major engineering decision | Agent reasoning per iteration (`agent_log.md`), assumptions and sensitivities below |

## Validator — 18 checks (from `validation_report.txt`)

Doublets in [1,3] · active ≤ installed · flow 50–300 m³/h · no flow when off ·
produced = injected · brine cooling ≤ 40 °C · pump efficiency 0.70 (ESP and injector) ·
heating supply ≥ 100 °C (computed) · heat pump re-solved by GEMINI agrees ·
cooling supply ≤ 20 °C (computed) · heating met every day · cooling met every day ·
330 geothermal days · HEX + heat-pump energy balance · whole-plant heat balance ·
electricity balance · gas mass balance · produced-gas CO₂ = CH₄ burned + native CO₂.

The checks do fail when they should. An undersized plant (1 doublet, 5 MW boiler,
4 MW chiller) gets FAIL with a heating supply of 72.6 °C, a cooling supply of
23.6 °C and a 13.7 MW heating shortfall.

## Engineering findings

1. **The number of doublets matters most.** Going from 1 to 3 doublets cuts CO₂ by 55 %, because one doublet cannot carry the 30 MW winter peak.
2. **Depth pays off through temperature.** Below ≈ 3,233 m the brine reaches the heat exchanger above 100 °C and the heat pump is no longer needed. The heat per m³ is capped by the 40 °C brine-cooling limit, so depth does not add capacity. There is no cost data, so the extra drilling is not priced in. The best design at the fixed 2,500 m reservoir depth (8,324 t) is reported too.
3. **Produced gas is now the largest CO₂ source:** 1.58 kg CO₂ per m³ of brine (≈ 3,600 t/yr for the agent's design, more than half of its total). It is unavoidable once brine is produced.
4. **The maintenance block sits in July–August**, when heating demand is lowest. On those 35 days the electric chiller carries the full 10 MW cooling peak alone.
5. **Equipment right-sizing:** with 3 doublets at 3,300 m the backup boiler is needed only at 3.5 MW (not 30 MW); the electric chiller needs 10 MW, because it carries the cooling alone during maintenance.

## Sensitivity (benchmark design, `sensitivity.csv`)

| Parameter | Values → CO₂ t/yr |
|---|---|
| Specific heat 3,900 / 4,186 J/kg/K | 7,222 / 6,725 |
| Well skin 0 / 2 / 5 / 10 (PI 14.0 / 11.2 / 8.6 / 6.2 m³/h/bar) | 6,656 / 6,725 / 6,824 / 7,015 |
| Grid factor 0.1 / 0.3 / 0.5 kg/kWh | 5,021 / 6,725 / 8,199 |
| Electric chiller Carnot fraction 0.3 / 0.4 / 0.5 | 6,991 / 6,725 / 6,515 |
| Chiller condensing 30 / 35 / 40 °C | 6,432 / 6,725 / 6,956 |
| Return temperature 35–50 °C, heat-pump η 0.4–0.6, wellbore loss 4–10 °C | no change: the heat pump is unused at 3,500 m and the 40 °C cooling cap binds |

All cases stay feasible.

## Assumptions (not given in the challenge)

All of them are fields of `Assumptions` in `plant_model.py`, and every report lists
them (`validation_report.txt`). Nothing else is typed into the physics. GEMINI
component parameters are read from `challenge_plant.json`; the fields the code sets
are listed there under `_set_by_code`.

| Item | Value |
|---|---|
| Specific heat brine/water | 4,186 J/kg/K |
| District heating return / chilled-water return | 40 °C / 26 °C |
| Heat pump | Lorenz, η = 0.50 (GEMINI default), COP cap 15 |
| Electric chiller | 0.40 × Carnot, evaporator 17 °C, condenser 35 °C → COP 6.45 |
| Absorption chiller | COP 0.7 at 100 °C drive |
| Grid emission factor | 0.3 kg CO₂/kWh (GEMINI example) |
| Purchased natural gas | 56.6 kg CO₂/GJ; boilers η 0.90, CHP 0.80; produced gas 80 % boiler / 20 % CHP |
| Productivity index | Darcy: skin 2, drainage radius 600 m, well radius 0.1 m |
| Wells | tubing ID 0.15 m, survey stations 300/500/1,000 m (GEMINI example) |
| Wellbore heat loss reservoir → wellhead | 7 °C (87 → 80 °C, as in the GEMINI example) |
| Wellhead pressure | 3 bar (GEMINI example) |
| ESP | depth 1,000 m, 15–70 Hz in 2.5 Hz steps, intake kept > 10 bar |
| Costs | not modelled: no data given, none invented |

## Changes to GEMINI (`git diff` against the development branch)

1. `src/gemini_simulator/registry.py` (+2 lines): `HeatpumpBasic` was not registered; now added.
2. `src/gemini_simulator/well_flow.py` (+12/−5): wells always used plain water
   (1,000 kg/m³, 1.0 mPa·s). There is now an optional `pvt` entry in a well's parameters
   (e.g. `{"RHOL": 1030, "VISL": 0.0004}`); the default behaviour is unchanged.
3. `src/gemini_model/heatpump/heatpump_basic.py`: **bug fixed.** When the source-outlet
   minimum was active, the fallback ran an unbounded Nelder-Mead with no convergence
   check and returned non-physical results (hot outlet 749 °C, COP ≈ 1). The Nelder-Mead result is
   now accepted only if it satisfies the equations; otherwise bracketed root searches
   (`brentq`) solve them, and the hot outlet can never exceed its target.
4. `unit_test/gemini_model/heatpump/test_heatpump_basic.py`: 2 regression tests. The first
   **fails on the original code** and passes on the fixed one. All 93 GEMINI unit tests pass.

## Model versions

* **Earlier model (runs 1–2):** electric chiller with a flat COP 4.0; supply temperatures
  written as constants.
* **Current model:** chiller COP from the 20 °C supply (6.45); computed supply
  temperatures; GEMINI heat-pump cross-check; injector efficiency check; all
  assumptions in one place. A copy of the earlier version is kept on the branch
  `backup-v1-working`.

## Files

| File | Purpose |
|---|---|
| `agent.py` | agentic loop (Ollama / OpenAI-compatible / `--offline` rule agent) |
| `plant_model.py` | official constants, `Assumptions`, GEMINI well/gas layer, HEX, heat pump, GEMINI heat-pump check |
| `dispatch.py` | daily lowest-CO₂ dispatch, maintenance block, no-geothermal reference, KPIs, 18-check validator |
| `run_full_year.py` | full-year report of the chosen design + plots |
| `optimize_design.py` | exhaustive benchmark (72 designs) + sensitivity |
| `challenge_plant.json` | GEMINI project at the 2,500 m baseline (fields set by code listed inside) |
| `GEMINI_*_Demand_Daily_2027.csv` | official demand profiles |
| `agent_log.md`, `agent_history.csv`, `agent_best_design.json` | LLM agent run 3 (submitted design) |
| `agent_runs/` | archived agent runs |
| `results_daily.csv`, `results_summary.csv`, `validation_report.txt`, `plots/` | full-year results |
| `design_comparison.csv`, `sensitivity.csv`, `best_design.json` | benchmark outputs |
