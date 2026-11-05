# Geothermallica: GEMINI models and an agentic design tool

Team Geothermallica, SPE Europe Energy GeoHackathon 2026, Express Edition.

## 1. What this branch is

This branch is a pull request to TNO's GEMINI `development` branch.
It adds five GEMINI models, one fix to GEMINI's solver and unit tests for all six; `GEMINI_MODELS.md` describes them.
It also holds our hackathon solution under `hackathon/geothermallica/solution/`, which imports those models from `src/`.
The solution is an agentic design tool for the challenge brief: a district with 30 MW of heat and 10 MW of cold,
supplied at 100 C and 20 C, from 1 to 3 geothermal doublets in a reservoir at 2 500 m.
Nothing outside `src/`, `unit_test/` and `hackathon/geothermallica/` is changed.

## 2. Run the tests

From the root of this repository, after TNO's normal install:

```
pip install -e .
pytest unit_test/gemini_model unit_test/gemini_simulator hackathon -q
```

You should see `176 passed`: 91 of TNO's tests, 38 for our models and the fix, 47 for the solution.
A few `RuntimeWarning` lines from `heatpump_basic.py` are normal.
A bare `pytest` from the root runs `unit_test/` only, as TNO's CI does.
`flake8 src unit_test --max-line-length=100` gives the same 31 findings as `development`; `black --check src unit_test` is clean.
The `hackathon/` folder is not linted by TNO's CI.
The MCP server alone needs `pip install "mcp>=2"`.

## 3. The overall workflow

The chain runs from the brief to a checked answer in these steps.

1. **Brief.** The code reads the peaks, the supply temperatures and the reservoir depth from the brief text and scales
   the daily heat and cold demand files to them.
2. **Physics** (`solution/geo/`). One year of plant operation is built on GEMINI's own components (IPR, DPDT, ESP, PVT,
   HeatpumpBasic and the five new models). `well.py` is the producer and the injector, `plant.py` one doublet's heat,
   electricity and lift against flow, `year.py` the day-by-day heat dispatch of 2027, `cooling.py` the cold, `checks.py`
   the 17 constraint checks, `outage.py` the 35-day outage of each doublet placed in the quietest weeks, `cost.py` the
   CAPEX, operation, electricity, gas, CO2, LCoH and LCoC, `gas.py` the dissolved gas and its handling, `lifetime.py`
   the thermal breakthrough, `storage.py` a heat tank against the backup boiler.
3. **Plan** (`solution/ai/AI03_plan.py`). The code sweeps 1 to 3 doublets by six return temperatures through the physics,
   18 candidates with a verdict each, and applies the one rule in `geo/rule.py`: the fewest doublets that meet the heat
   with the boiler at most 5 % of the heat and the peak covered. `geo/optimise.py` then searches return temperature and
   ESP depth for the front of LCoH against CO2, and the plan prices the alternatives: the next doublet, a boiler-lift
   layout without heat pump, a storage tank, a lower return, burning the associated gas instead of reinjecting it.
4. **GEMINI replay** (`geo/gemini_project.py`, `geo/gemini_compare.py`). The chosen design is written as a native GEMINI
   project file and GEMINI's own solver re-runs it on three days of the year; the replay compares ESP head, injection
   wellhead pressure, heat-pump COP, bubble point and breakthrough time with the plan's numbers.
5. **Answer.** The plan, the tool results and the replay verdict go to a local language model that writes the answer
   as a fixed JSON; a checker verifies it; the run file holds the answer, the checks and the transcript.

`geo/gemini_path.py` puts this branch's `src/` first on the Python path, so the solution keeps no copies of the models.
`solution/SOURCES.md` lists the source of every constant in the code.

## 4. The agentic workflow

**Tools.** `ai/AI02_tools.py` is a registry of 17 typed tools; the tools live in `AI02_tools_site.py`, `AI02_tools_year.py`,
`AI02_tools_economics.py` and `AI02_tools_gemini.py`. Every tool returns numbers with the GEMINI classes that ran and
the GEMINI commit. `ai/AI10_mcp.py` serves the same 17 tools to any MCP client.

**Who does what.**
- The code builds the design plan, calls the tools, runs the checks and the GEMINI replay.
- The model (qwen3 4b instruct on Ollama, local, zero cost) reads the plan and writes the answer in a fixed JSON with a
  provenance tag on every number. It picks one design from the LCoH-CO2 front, saying what it gives up, and when a check
  fails it picks one repair move from a short menu (`AI03_moves.py`, for example: free gas at the pump intake moves the
  ESP deeper). The model never computes a number.
- The checker (`AI04_check.py`, rules a to k) verifies every number in the answer against the tool results of that run
  and rejects untagged or untraceable numbers, conclusions that disagree with the sweeps, brief values that never reached
  a tool, a missing iteration trace and an answer that drops what the replay said. A bad answer gets one re-prompt with
  the list of problems.

**Around it.** `AI03_agent.py` runs the chain and writes a run file. `AI05_eval.py` runs six briefs end to end.
`AI06_rag.py` answers questions about GEMINI's modules from their docstrings, with the module cited.
Every prompt is a plain file in `ai/prompts/`.

## 5. Run it yourself

Run these from `hackathon/geothermallica/solution`.

**(a) The design plan, no model needed** (about 25 s):

```
python -c "import sys; sys.path.insert(0, 'ai'); import AI03_agent as a, AI03_plan as p; print(p.plan_message(a.BRIEF, p.plan(a.BRIEF)))"
```

You should see `Plan choice: 2 doublets at a 56.5 C return`, the 18 design iterations, the gas, outage and GEMINI
replay lines, and seven rejected alternatives. It writes the GEMINI project file `ai/runs/gemini_project_2d_56.5C.json`.

**(b) The agent, with a local model:**

```
ollama pull qwen3:4b-instruct-2507-q4_K_M
python ai/AI03_agent.py "District with 30 MW peak heating and 10 MW peak cooling, supply 100 C and 20 C, reservoir at 2500 m. Recommend the number of doublets and the network return temperature, and tell me whether the design needs a boiler. Check the constraints."
```

You should see the recommendation in plain text, then `checker problems: ...`, then `wrote ai/runs/<date>_plan_<brief>.md`.
With no brief, `python ai/AI03_agent.py` is interactive: Enter runs the challenge brief, `q` quits.
`AGENT_MODEL=<name>` swaps the model.

**(c) The MCP server:**

```
python ai/AI10_mcp_check.py
```

You should see `17 tools match AI02.FUNCS`, two tool calls, one deliberate error (`q_m3h=400.0 outside 50.0-300.0`),
one resource and one prompt. To use it from an MCP client, point the client at `python <absolute path>/ai/AI10_mcp.py`
over stdio; with Claude Code, `claude mcp add geohack -- python <absolute path>/ai/AI10_mcp.py`.

## 6. The answer for the brief

Two doublets at a 56.5 C network return, ESP at 1 100 m, associated gas reinjected: LCoH 61.93 EUR/MWh, 5.49 kt CO2 a
year, no boiler energy with a 16 MW backup boiler installed, 17 of 17 checks pass.
One doublet needs a boiler for 22 % of the heat and is 48 % short at the peak; a third doublet adds 8.98 EUR/MWh when
two already meet the heat. A boiler lift instead of the heat pump costs 76.1 EUR/MWh and 11.97 kt CO2.
The gas engine alternative gives 61.8 EUR/MWh and 9.43 kt CO2. GEMINI's own solver agrees with the design within 0.2 bar
on the ESP head and 0.1 bar on the injection wellhead.
