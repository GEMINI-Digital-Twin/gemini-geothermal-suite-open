# solution/

The hackathon deliverable: an agentic design tool for the GeoHackathon 2026 brief, built on GEMINI.
The brief: 30 MW heat and 10 MW cold, supply 100 C and 20 C, 1 to 3 doublets at 2 500 m [D].

Tags on numbers: [C] computed by our code, [D] data from the brief, [L] literature, [A] our assumption, [TBC] to be confirmed.

## What is here

| path | what it is |
|---|---|
| `geo/` | the physics on GEMINI's components: well, plant, demand, year (heating), cooling, checks, cost, outage, gas, lifetime, storage, optimise, rule, GEMINI replay |
| `ai/` | the agent: tools (`AI02_tools.py` registry, `AI02_tools_<topic>.py` site, year, economics, gemini, schema, common), plan, repair moves, checker, eval, RAG, MCP server, prompts, run files |
| `explore/` | the design scripts `01`-`10`, `scenarios/`, their `figures/` and `tables/` |
| `NOTES_findings.md` | the findings log, F1-F31: what we saw, the numbers, a beginner version; all history lives here |
| `GEMINI_MODELS.md` | our five GEMINI models: file, inputs, tests, sources |
| `PATCH.md` | the diff against TNO's `development` (the injector sign fix, registry, new files) |
| `SOURCES.md` | full references behind the short source names in code comments |

The five models live only in the fork's `src/`, not here.
`geo/gemini_path.py` finds them at `~/src/gemini-geothermallica/src` (or `GEMINI_DEV_SRC`).

## Commands

Run from this folder with the repo venv. No environment variable is needed.

```
PY=../../.venv/bin/python
$PY -m pytest geo ai -q                      # tests
$PY geo/cost.py                              # economics of 1-3 doublets at 60 C
$PY ai/AI02_tools.py                         # every tool once, with its result
$PY -c "import sys; sys.path.insert(0, 'ai'); import AI03_agent as a, AI03_plan as p; print(p.plan_message(a.BRIEF, p.plan(a.BRIEF)))"   # the plan, no model
$PY ai/AI03_agent.py                         # the agent, interactive (needs Ollama)
$PY ai/AI03_agent.py "<brief>"               # the agent on one brief (needs Ollama)
$PY ai/AI04_check.py                         # re-check the newest run file
$PY ai/AI05_eval.py --plan                   # six briefs, plan mode (needs Ollama)
$PY ai/AI10_mcp_check.py                     # MCP server round trip, no model
$PY ai/AI07_rag_eval.py                      # eight GEMINI questions for the RAG (needs Ollama)
$PY explore/08_checks.py                     # the checks table, explore/tables/08_checks.md
```

What you should see:
- Tests: `45 passed` [C]. A few `RuntimeWarning` lines from `heatpump_basic.py` are normal.
- The plan: `Plan choice: 2 doublets at a 56.5 C return`, then the iteration, gas, outage, replay lines and seven rejected alternatives. About 25 s on a laptop [C].
- The plan writes `ai/runs/gemini_project_2d_56.5C.json`, the GEMINI project file of the replay.
- The agent: the recommendation, `checker problems: ...`, and `wrote ai/runs/<date>_plan_<brief>.md`.
- The MCP check: `17 tools match AI02.FUNCS`, a deliberate error for `q_m3h=400`, two resources (one on the fork, where the findings note is absent), one prompt.
- The other design scripts in `explore/` write figures to `explore/figures/` as `.pdf` and `.png`.

Ollama runs one job at a time. Pull the model once: `ollama pull qwen3:4b-instruct-2507-q4_K_M`.
`AGENT_MODEL=<name>` swaps the model. `ai/MCP.md` shows how to connect Claude Code or the Inspector.

## The design answer

2 doublets, 56.5 C network return, ESP at 1 100 m, reservoir at 2 500 m, associated gas reinjected. All from the tools.

| quantity | value |
|---|---|
| LCoH | 61.93 EUR/MWh [C] |
| CO2 | 5.49 kt/yr, all from grid electricity at 0.3 kg/kWh [C, D] |
| gas handling | reinjected: the gas rule takes it when it adds under 1 % to the LCoH (+0.13 EUR/MWh, +0.2 %), compression 0.08 GWh/yr, permit assumed [C, A] |
| same design with a gas engine (rejected) | LCoH 61.8 EUR/MWh, CO2 9.43 kt/yr, electricity 18.23 GWh/yr [C] |
| electricity | 18.31 GWh/yr [C] |
| geothermal share of heat | 91.25 % [C] |
| cooling | 76.7 % free, 6.3 % absorption, 17.1 % electric [C] |
| checks | 17/17 pass (13 computed + 4 declared) [C] |
| outages | staggered, days 177-211 and 212-246 [C] |
| one doublet out on the coldest day | 31.0 MW available against 30 MW [C] |
| unplanned 7-day outage in January | +2.23 GWh boiler, 0.17 MEUR, 0.34 kt CO2 [C, A] |

Why this design:
- One doublet needs a boiler for 21.74 % of the heat [C]. A third adds 9.0 EUR/MWh [C].
- 56.5 C is the optimiser's lowest LCoH [C]. At 55 C the boiler must supply 3.06 GWh [C].
- The boiler-lift layout costs 76.1 EUR/MWh and emits 11.97 kt CO2, both with the gas reinjected [C]. So the heat pump stays.
- Reinjecting the gas cuts CO2 from 9.43 to 5.49 kt for +0.13 EUR/MWh (+0.2 %), under the 1 % gas rule [C, A]. So the engine goes.

## The 17 checks (`checks` tool, `geo/checks.py`)

| # | check | kind |
|---|---|---|
| 01 | doublets 1-3 | computed |
| 02 | flow per doublet 50-300 m3/h | computed |
| 03 | flow above the pump floor (160 m3/h) | computed |
| 04 | brine cooling at most 40 K | computed |
| 05 | pump efficiency 0.70 | declared |
| 06 | production equals injection volume | declared |
| 07 | 330 operating days per doublet | computed |
| 08 | heat supply 100 C every day | computed |
| 09 | cold supply 20 C | declared |
| 10 | SodM injection pressure | computed |
| 11 | ESP envelope (flow, 60 Hz) | computed |
| 12 | accounting: supply equals demand | declared |
| 13 | capacity covers the peak | computed |
| 14 | no free gas at the ESP intake | computed |
| 15 | thermal breakthrough after 30 yr or more | computed |
| 16 | doublet interference within the SodM margin | computed |
| 17 | one doublet out on the coldest day | computed |

## The 17 tools (`ai/AI02_tools.py`, also served by `ai/AI10_mcp.py`)

| tool | what it returns |
|---|---|
| `site_inputs` | reservoir temperature and pressure at the depth; whether the setpoints are supported |
| `demand_summary` | peaks, annual GWh and cooling season of the 2027 demand files, scaled to the brief |
| `doublet_point` | one doublet at a flow and return: heat by source, ESP power, heat-pump COP |
| `heating_year` | the 2027 dispatch: GWh by source, electricity, capacity, outage windows and costs |
| `cooling_year` | cold over 2027: free, absorption, electric, and their electricity |
| `injector_point` | injectivity, injection pressures, pump power, SodM margin |
| `gas_point` | dissolved gas, bubble point at the ESP intake, five gas-handling options |
| `lifetime_point` | thermal breakthrough time and doublet interference |
| `heat_pump_point` | GEMINI's `HeatpumpBasic` through `HeatPumpLift`: COP, heat, electricity |
| `checks` | the 17 checks above, each value against its limit |
| `economics` | CAPEX, annual cost, LCoH, LCoC, electricity, gas, CO2 |
| `layout_compare` | heat-pump lift against boiler lift: cost, gas, CO2, share |
| `storage_point` | a steel heat tank against the 16 MW backup boiler |
| `return_sweep` | returns 40-70 C compared for 1-3 doublets, with the best return |
| `optimise_point` | search over doublets, return and ESP depth; front of LCoH against CO2 |
| `gemini_replay` | the design as a GEMINI project file, re-run by GEMINI's own solver |
| `gemini_traps` | our GEMINI findings as short sentences the agent may cite |

`gemini_traps` lists the five GEMINI bugs we hit or reproduced (F31).

## How the agent and the code share the work

The code reads the brief, runs the sweeps of 18 candidates, picks the design and runs the checks (`ai/AI03_plan.py`).
The code also prices the alternatives and calls the GEMINI replay.
The local model (qwen3 4b instruct on Ollama) reads the plan and writes the answer in a fixed JSON.
It picks one design from the cost and CO2 front and states the trade-off.
When a check fails, it picks one repair move from a menu (`ai/AI03_moves.py`).
The model never computes a number.
The checker (`ai/AI04_check.py`, rules a to k) traces every number to a tool result of the same run.
A bad answer gets one re-prompt with the problem list.

Latest eval table (`ai/runs/eval_table_qwen3_4b_instruct_2507_q4_k_m.md`): six briefs, 6/6 right designs, 4/6 clean [C]
(briefs B and C: a chiller electricity that matches no tool result, rule (d) caught it). Mean 28.3 k prompt tokens and
125 s per brief, 0 EUR [C].
All runs so far: 773 model calls, 5.75 M tokens, 0 EUR on the laptop [C, `ai/runs/tokens.md`].
RAG eval (`ai/runs/rag_eval.md`): 8/8 retrieval, 8/8 keyword, 8/8 grounded [C].

## What is untested by a human

- Every command above was run by Claude, not yet by Bartek. Type each one once before quoting it.
- The agent, the eval and the RAG need Ollama; they were not run while writing this file.
- Claude Code, ollmcp and the Inspector have not been connected to the MCP server by hand.
- Doublet CAPEX: 9.33 MEUR per doublet on the ThermoGIS curve [L]; other sources say 23.6-37.2 MEUR [L, TBC]. At 23.6 MEUR the LCoH is 91.6 EUR/MWh, at 37.2 MEUR 120.0 [C].
- Peak margin: 30.04 MW against the 30 MW peak, 0.14 % [C].
- GEMINI's own ESP needs up to 8.4 Hz less for the same flow [C]; the replay states that gap.
- The heat-pump COP is capped at 8 [A].

## The fork and the PR

The public copy is the fork github.com/barteksarwa/gemini-geothermal-suite-open, branch `geothermallica`.
The solution sits there at `hackathon/geothermallica/solution/` (`geo/`, `ai/`), with its own `README.md`.
The PR text is `../PR_TEXT.md`. The PR to TNO's `development` is the submission.
