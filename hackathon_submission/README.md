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
                  └──── violations + KPIs + history ◄──── deterministic validator (16 checks)
```

The LLM never decides PASS/FAIL. Only the validator does, from the simulated
numbers.

## Result

| | Agent's design (`agent_best_design.json`) |
|---|---|
| Doublets | **3**, wells 3,500 m TVD (117 °C reservoir) |
| Heat exchanger | 2,000 kW/K per doublet. At this depth the brine heats the water to 100 °C directly, so the heat pump is not needed |
| ESP | 50 stages at 1,000 m, variable speed → 58–196 m³/h per doublet |
| Backup gas boiler | 4.5 MW (peak use 3.9 MW) |
| Chillers (20 °C) | 10.5 MW electric + 9 MW absorption (geothermal heat) |
| **CO₂** | **7,192 t/year** |
| Heat from geothermal | 88.3 % (produced gas 9.7 %, backup boiler 2.0 %) |
| Constraint checks | **16/16 PASS** |

Benchmarks from the exhaustive search over 72 designs (`optimize_design.py`):

| Best design with … | CO₂ t/yr |
|---|---|
| 1 doublet | 15,724 |
| 2 doublets | 9,486 |
| 3 doublets | 7,221 |
| 3 doublets, depth fixed at the 2,500 m reservoir midpoint | 9,075 |
| **Agent (offline rule-based run)** | **7,192** (−0.4 % vs. the grid, because it found a combination outside the grid) |

## How to run

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows   (Linux/Mac: source .venv/bin/activate)
pip install numpy scipy pandas matplotlib
cd hackathon_submission

# 1. agentic design loop  (needs Ollama:  ollama pull qwen2.5:7b)
python agent.py --model qwen2.5:7b --iterations 12
#    no LLM available? deterministic rule-based agent:
python agent.py --offline --iterations 30

# 2. full-year report of the agent's design (16 checks, CSVs, plots)
python run_full_year.py

# 3. optional benchmark + sensitivity study (~1 min)
python optimize_design.py
```

## Official requirements → where they are met

| Requirement (challenge PDF, 28 Oct 2026) | Implementation |
|---|---|
| Agentic AI: interpret demand, generate configurations, run checks, detect violations, iterate | `agent.py`: the LLM gets a demand summary, rules, history, violations and KPIs; proposes JSON; schema check; simulation; validator; repeat. Every step and reason is in `agent_log.md` |
| Use GEMINI for subsurface/well engineering; complementary models for heating/cooling | GEMINI: producer well + ESP (nodal), separator, filters, injector well + pump, produced-gas boiler/CHP, `HeatExchanger`. Complementary: Lorenz heat pump, chillers, dispatch |
| Demand: 365 daily MW; MWh = MW × 24 | 111.67 GWh heat / 23.74 GWh cooling reproduced |
| Reservoir 2,500 m, 100 m, 30 °C/km, 12 °C, 250 bar, 200 mD | T = 12 + 30·z/1000; p hydrostatic (250 bar at 2,500 m); PI from Darcy with k = 200 mD, h = 100 m, μ = 0.40 mPa·s → 11.2 m³/h/bar |
| Other well depths via hydrostatic pressure and gradient | Depth is a design variable (2,000–3,500 m) |
| Brine 1,030 kg/m³, 0.40 mPa·s | Used in GEMINI well hydraulics (new optional `pvt` input), HEX and heat pump |
| GLR 0.8 Nm³/m³, 80 % CH₄ / 20 % CO₂, Nm³ at 0 °C, 1.01325 bar | Gas density 0.969 kg/Nm³; heat from CH₄ only (35.88 MJ/Nm³); CO₂ = combustion + native CO₂ (checked within 1 %) |
| 1–3 doublets | Design variable |
| 50–300 m³/h per active doublet | ESP speed chosen daily within the range; checked |
| Brine cooling ≤ 40 °C, producer → injector | Heat pump and HEX can never cool the brine below T_producer − 40 °C; checked |
| Pump hydraulic efficiency 70 % | ESP and injector power = Δp·Q/0.70; checked |
| Production = injection volume | GEMINI injector receives the producer flow; checked |
| 330 daily steps, daily power and energy balance | One 35-day maintenance block placed at least CO₂ cost; heat, electricity and gas balances checked every day |
| 100 °C heating supply | HEX/heat-pump outlet solved at 100 °C (HEX bypass when the brine is hotter) |
| 20 °C cooling supply | Absorption (COP 0.7, 100 °C drive) and electric (COP 4) chillers at 20 °C; demand met every day |
| Explain every major engineering decision | Agent reasoning per iteration (`agent_log.md`), assumptions and sensitivities below |

## Validator — 16 checks (from `validation_report.txt`)

Doublets in [1,3] · active ≤ installed · flow 50–300 m³/h · no flow when off ·
produced = injected · brine cooling ≤ 40 °C · pump efficiency 0.70 ·
heating supply 100 °C · heating met every day · cooling met every day at 20 °C ·
330 geothermal days · HEX + heat-pump energy balance · whole-plant heat balance ·
electricity balance · gas mass balance · produced-gas CO₂ = CH₄ burned + native CO₂.

## Engineering findings

1. **The number of doublets matters most.** Going from 1 to 3 doublets cuts CO₂ by 54 %, because one doublet cannot carry the 30 MW winter peak.
2. **Depth pays off through temperature.** At 3,500 m (117 °C, 110 °C at the wellhead) the brine heats the district water to 100 °C on its own, and the heat pump's electricity disappears. With the brine-cooling cap of 40 °C, the heat per m³ stays the same, so depth does not add capacity. There is no cost data, so the extra 6 × 1,000 m of drilling is not priced in. The best design at the fixed 2,500 m reservoir depth (9,075 t) is reported too.
3. **Produced gas is now the largest CO₂ source** (≈ 4,250 t/yr): 1.58 kg CO₂ per m³ of brine, unavoidable once brine is produced.
4. **Summer geothermal heat makes cooling.** The absorption chiller turns spare brine heat into cooling. The 35-day maintenance block sits in July–August, when the plant is needed least.
5. **Equipment right-sizing:** the backup boiler is needed only at 3.9 MW (not 30 MW) and the electric chiller at 10 MW. The electric chiller carries the full cooling peak during the maintenance block.

## Sensitivity (benchmark design, `sensitivity.csv`)

| Parameter | Values → CO₂ t/yr |
|---|---|
| Specific heat 3,900 / 4,186 J/kg/K | 7,803 / 7,221 |
| Well skin 0 / 2 / 5 / 10 (PI 14.0 / 11.2 / 8.6 / 6.2 m³/h/bar) | 7,130 / 7,221 / 7,334 / 7,545 |
| Grid factor 0.1 / 0.3 / 0.5 kg/kWh | 5,297 / 7,221 / 8,724 |
| Electric chiller COP 3 / 4 / 5 | 7,426 / 7,221 / 7,052 |
| Return temperature 35–50 °C, heat-pump η 0.4–0.6, wellbore loss 4–10 °C | no change: the heat pump is unused at 3,500 m and the 40 °C cooling cap binds |

All cases stay feasible.

## Assumptions (not given in the challenge)

| Item | Value |
|---|---|
| Specific heat brine/water | 4,186 J/kg/K (sensitivity above) |
| Well skin / drainage radius / well radius (PI) | 2 / 600 m / 0.1 m |
| Wellbore heat loss reservoir → wellhead | 7 °C (87 → 80 °C, as in the GEMINI example) |
| District heating return | 40 °C |
| Heat pump | Lorenz, η = 0.50 (same equations as GEMINI `HeatpumpBasic`) |
| Chillers | absorption COP 0.7, electric COP 4.0 |
| Grid emission factor | 0.3 kg CO₂/kWh (GEMINI example) |
| Purchased natural gas | 56.6 kg CO₂/GJ, backup boiler η 0.90 |
| ESP depth | 1,000 m; intake kept > 10 bar |
| Costs | not modelled: no data given, none invented |

## Changes to GEMINI and issues found

* `src/gemini_simulator/registry.py`: `HeatpumpBasic` was not registered; now added.
* `src/gemini_simulator/well_flow.py`: wells always used plain water (1,000 kg/m³,
  1.0 mPa·s). There is now an optional `pvt` entry in a well's parameters
  (e.g. `{"RHOL": 1030, "VISL": 0.0004}`). Default behaviour is unchanged, and all 91
  GEMINI unit tests pass.
* `HeatpumpBasic`'s fallback branch, used when the source-outlet minimum is
  active, returns non-physical results (hot outlet > 700 °C, COP ≈ 1). Its
  Nelder-Mead solve has no bounds and no convergence check. We solve the same
  Lorenz equations by bisection and match `HeatpumpBasic` exactly in its valid
  range (COP 6.129 = 6.129).
* Example JSON values that contradict the challenge (240 bar injector, 2,400/3,100 m wells,
  0.8 pump efficiency, GLR 0.5, gas density 0.7) are replaced.

## Files

| File | Purpose |
|---|---|
| `agent.py` | agentic loop (Ollama / OpenAI-compatible / `--offline` rule agent) |
| `plant_model.py` | GEMINI well/gas layer, reservoir from depth, HEX, heat pump |
| `dispatch.py` | daily lowest-CO₂ dispatch, maintenance block, KPIs, 16-check validator |
| `run_full_year.py` | full-year report of the chosen design + plots |
| `optimize_design.py` | exhaustive benchmark (72 designs) + sensitivity |
| `challenge_plant.json` | GEMINI project with challenge inputs |
| `GEMINI_*_Demand_Daily_2027.csv` | official demand profiles |
| `agent_log.md`, `agent_history.csv`, `agent_best_design.json` | agent run: reasoning, designs, verdicts |
| `results_daily.csv`, `results_summary.csv`, `validation_report.txt`, `plots/` | full-year results |
| `design_comparison.csv`, `sensitivity.csv`, `best_design.json` | benchmark outputs |
