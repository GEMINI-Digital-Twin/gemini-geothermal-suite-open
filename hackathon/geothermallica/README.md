# Geothermallica: GEMINI models and an agentic design tool

Team Geothermallica, SPE Europe Energy GeoHackathon 2026, Express Edition.

Tags on numbers: [C] computed by our code, [D] data from the brief, [L] literature, [A] our assumption, [TBC] to be confirmed.

## 1. What this branch is

This branch is a pull request to TNO's GEMINI `development` branch.
It adds five new GEMINI models, one fix to GEMINI's solver, and unit tests for all six.
It also holds our hackathon solution, which uses those models.
The solution is an agentic design tool for the challenge brief.
The brief asks for a district with 30 MW of heat and 10 MW of cold [D].
Heat is supplied at 100 C and cold at 20 C [D].
The source is 1 to 3 geothermal doublets in a reservoir at 2 500 m [D].
Nothing outside `src/`, `unit_test/` and `hackathon/geothermallica/` is changed.

## 2. What changed in GEMINI's source

| Model (registry name) | File in `src/` | What it does | Tests |
|---|---|---|---|
| `ESPAffinity` (`esp_affinity`) | `gemini_model/pump/esp_affinity.py` | ESP that reads the 60 Hz curve at q x 60/f (pump similarity laws) | 4 |
| `HeatPumpLift` (`heatpump_lift`) | `gemini_model/heatpump/heatpump_lift.py` | `HeatpumpBasic` with a brine floor per call, COP capped at 8 | 8 |
| `HenryGasBubblePoint` (`henry_gas`) | `gemini_model/fluid/henry_gas.py` | Bubble point of dissolved CH4 and CO2 by Henry's law, with salt | 6 |
| `DoubletThermalBreakthrough` (`thermal_breakthrough`) | `gemini_model/reservoir/thermal_breakthrough.py` | Thermal breakthrough time and pressure interference of doublets | 8 |
| `AbsorptionChiller` (`absorption_chiller`) | `gemini_model/chiller/absorption_chiller.py` | Brine heat above a drive floor turned into cold at COP 0.75 | 7 |
| Injector friction sign (fix) | `gemini_simulator/nodal_solver.py` | Injection flow passed to DPDT as negative, so friction opposes it | 5 |

The tests live in `unit_test/gemini_model/{pump,heatpump,fluid,reservoir,chiller}/` and `unit_test/gemini_simulator/test_injector_sign.py`.
`HeatpumpBasic` (TNO's own) is also added to the registry as `heatpump`.
`PATCH.md` shows the solver fix line by line.
`GEMINI_MODELS.md` lists the inputs, the sources and the cross-checks of each model.

## 3. Run the tests

From the root of this repository, after TNO's normal install:

```
pip install -e .
pip install "mcp>=2"
pytest unit_test/gemini_model unit_test/gemini_simulator hackathon -q
```

You should see `174 passed` [C].
That is 91 of TNO's tests, 38 for our models and the fix, and 45 for the solution [C].
A few `RuntimeWarning` lines from `heatpump_basic.py` are normal.
A bare `pytest` from the root runs `unit_test/` only (`testpaths` in `pyproject.toml`), as TNO's CI does.
Lint: `flake8 src unit_test --max-line-length=100` gives the same 31 findings as TNO's `development` and `black --check src unit_test` is clean.
The `hackathon/` folder is not linted by TNO's CI and does not keep the 100-character limit.

## 4. How the solution works

**`solution/geo/`: the physics.**
It builds one year of plant operation on GEMINI's own components (IPR, DPDT, ESP, PVT, HeatpumpBasic).
`well.py` is the producer and the injector.
`plant.py` gives one doublet's heat, electricity and lift against flow.
`year.py` dispatches the plant day by day over 2027 and runs the constraint checks.
`cost.py` prices it: CAPEX, operation, electricity, gas, CO2, LCoH and LCoC.
`outage.py` places the 35-day outage of each doublet in the quietest weeks.
`gas.py` handles the dissolved gas, `lifetime.py` the breakthrough, `storage.py` a heat tank.
`optimise.py` searches doublets, return temperature and ESP depth for the best cost and CO2.
`rule.py` holds the one rule that picks a design.
`gemini_project.py` writes our design as a native GEMINI project file and runs GEMINI's own solver on it.
`gemini_compare.py` compares that replay with our numbers.
`gemini_path.py` puts this branch's `src/` first on the Python path, so the solution keeps no copies of the models.

**`solution/ai/`: the agent.**
`AI02_tools.py` turns the physics into 17 typed tools.
`AI03_plan.py` is the code plan.
It reads the brief, sweeps 18 candidate designs, picks one, prices the alternatives and calls the GEMINI replay.
`AI03_moves.py` is the repair loop: when a check fails, the model picks one move from a short menu.
`AI03_agent.py` runs the whole chain and writes a run file.
`AI04_check.py` checks the model's answer with rules (a) to (k).
`AI05_eval.py` runs six briefs end to end.
`AI06_rag.py` answers questions about GEMINI's modules from their docstrings, with the module cited.
`AI10_mcp.py` serves the same 17 tools over MCP.
Every prompt is a plain file in `ai/prompts/`.

**Who does what.**
The code builds the design plan, calls the tools and runs the checks.
The local model (qwen3 4b instruct on Ollama) reads the plan and writes the answer in a fixed JSON.
It also picks one design from the cost and CO2 front, and picks repair moves from a menu.
The model never computes a number.
The checker rules verify every number in the answer against the tool results of that run.
A bad answer gets one re-prompt with the list of problems.

## 5. Run it yourself

Run these from `hackathon/geothermallica/solution`.

**(a) The design plan, no model needed.**

```
python -c "import sys; sys.path.insert(0, 'ai'); import AI03_agent as a, AI03_plan as p; print(p.plan_message(a.BRIEF, p.plan(a.BRIEF)))"
```

You should see `Plan choice: 2 doublets at a 56.5 C return`, the 18 design iterations, the gas, outage and GEMINI replay lines, and seven rejected alternatives.
It takes about 25 s on a laptop [C].
It writes the GEMINI project file `ai/runs/gemini_project_2d_56.5C.json`.

**(b) The agent, with a local model.**

```
ollama pull qwen3:4b-instruct-2507-q4_K_M
python ai/AI03_agent.py "District with 30 MW peak heating and 10 MW peak cooling, supply 100 C and 20 C, reservoir at 2500 m. Recommend the number of doublets and the network return temperature, and tell me whether the design needs a boiler. Check the constraints."
```

You should see the recommendation in plain text, then `checker problems: ...`, then `wrote ai/runs/<date>_plan_<brief>.md`.
The run file holds the answer JSON, the checks (17/17), the full transcript and the token count.
With no brief, `python ai/AI03_agent.py` is interactive: Enter runs the challenge brief, `q` quits.
`AGENT_MODEL=<name>` swaps the model.

**(c) The MCP server.**

```
python ai/AI10_mcp_check.py
```

You should see `17 tools match AI02.FUNCS`, two tool calls, one deliberate error (`q_m3h=400.0 outside 50.0-300.0`), one resource (`notes://readme`, this file; the findings note is not on this branch) and one prompt.
No model is needed.
To use it from an MCP client, point the client at `python <absolute path>/ai/AI10_mcp.py` over stdio.
Claude Code: `claude mcp add geohack -- python <absolute path>/ai/AI10_mcp.py`. Inspector: `npx @modelcontextprotocol/inspector python <absolute path>/ai/AI10_mcp.py`.

## 6. The design answer for the brief

All numbers below are [C] from the tools, for 2 doublets at a 56.5 C network return, ESP at 1 100 m, reservoir at 2 500 m.

| quantity | value |
|---|---|
| LCoH | 61.8 EUR/MWh [C] |
| CO2 | 9.43 kt/yr [C] |
| electricity | 18.23 GWh/yr [C] |
| geothermal share of heat | 91.25 % [C] |
| boiler energy | 0 GWh; 16 MW backup boiler installed [C] |
| cooling | 76.7 % free, 6.3 % absorption, 17.1 % electric [C] |
| checks | 17/17 pass (13 computed + 4 declared) [C] |
| outages | staggered, days 177-211 and 212-246 [C] |
| one doublet out on the coldest day | 31.0 MW available against 30 MW [C] |
| unplanned 7-day outage in January | +2.23 GWh boiler, 0.17 MEUR, 0.34 kt CO2 [C, A] |

**Why 2 doublets and not 1 or 3.**
One doublet needs a boiler for 21.74 % of the heat and is 48 % short at the peak [C].
A third doublet adds 9.0 EUR/MWh and 9.86 MEUR of CAPEX when two already meet the heat [C].

**Why a 56.5 C return.**
The optimiser finds it as the lowest LCoH [C].
A 55 C return needs 3.06 GWh of boiler energy [C], and the 60 C of our first sweeps costs 66.4 EUR/MWh [C].

**Why a heat pump and not a boiler.**
The exchanger alone gives water below 100 C, so something must lift it.
The boiler-lift layout costs 75.97 against 61.8 EUR/MWh [C].
It burns 51.64 GWh of gas and emits 15.95 kt CO2 against 9.43 kt [C].

**GEMINI checks our design.**
GEMINI's own solver re-runs the design on 3 days of 2027.
ESP head agrees within 0.2 bar, the injection wellhead within 0.1 bar [C].
Heat-pump COP, bubble point and breakthrough time agree [C].
On TNO's unpatched tree the injection wellhead is 7 to 25 bar off, which is how the replay finds the sign bug [C].

## 7. What we are not sure about

- Doublet CAPEX: the LCoH rests on the ThermoGIS well-cost curve, 9.33 MEUR per doublet [L]; other sources say 23.6-37.2 MEUR [L, TBC].
  At 23.6 MEUR per doublet the LCoH is 91.6 EUR/MWh instead of 61.8, at 37.2 MEUR 120.0 (`geo.cost.economics(2, 56.5, 30, 10, doublet_MEUR=23.6)`) [C].
- Peak margin: 2 doublets give 30.04 MW against the 30 MW peak, a margin of 0.14 % [C]; a small loss of flow or temperature puts the backup boiler on at the peak.
- ESP frequency: GEMINI's own ESP needs up to 8.4 Hz less for the same flow, because it reads the 60 Hz curve at the actual flow [C].
- Heat-pump COP is capped at 8 at small lifts [A].
- The salted bubble point is 45.6 or 62.5 bar, depending on a log base the source does not state [TBC]; the check uses the worse.
- The agent and most commands were run by Claude, not yet by a team member by hand.

## 8. Where the numbers come from

`GEMINI_MODELS.md` (models and sources), `PATCH.md` (the solver fix), and the run files the agent writes in `solution/ai/runs/`.
Each tool result carries its tag, the GEMINI classes that ran and the GEMINI commit.
