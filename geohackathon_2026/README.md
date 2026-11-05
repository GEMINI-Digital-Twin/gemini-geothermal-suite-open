# SPE Europe GeoHackathon 2026: geothermal heating and cooling agent

An agent that selects, sizes and checks a deep geothermal direct-use system for one district with GEMINI. It must meet the 2027 daily heating demand (30 MWth peak) and cooling demand (10 MW peak).

The agent chooses the number of doublets, the depth and the layout: gas boiler, heat pump or CHP on the produced gas to reach 100 C, and absorption or electric chillers. It then checks the chosen design for return temperature, an unplanned failure over the peak, subsurface, demand and grid uncertainty, and every operating day in GEMINI plant files.

The agent runs on an open-weight model (qwen3:8b) through Ollama. The model plans, chooses tools and explains the result. Every number comes from Python tools built on GEMINI's models, and every challenge limit is checked in code.

## Layout

| Folder | Contents |
|---|---|
| `agent/` | Agent loop (`run_agent.py`), tools, plant JSON generator and GEMINI year run (`plant_json.py`, `plant_year.py`), uncertainty sampling, cost model, answer reviewer, sensitivity study, tests |
| `cases/` | Baseline case, pipe size study, 365-day heating and cooling models with layouts |
| `results/` | Yearly results, sensitivity tables, generated GEMINI plant files, evidence summary |
| `logs/` | One file per agent session, with every tool call and token counts |

The two demand files are the challenge inputs.

## Result

Recommended design: 2 doublets at 3,000 m, produced gas in a CHP, absorption chillers. 71.2 EUR/MWh, 5.97 kt CO2 a year (78% less than gas boilers and electric chillers), 0.3% of delivered energy bought; every operating day passes in GEMINI plant files. Details: `results/evidence/evidence_summary.md`, `results/sensitivity.md` and `results/figures/`.

## Setup

Needs Python 3.11 and, for the agent only, [Ollama](https://ollama.com). Tested on macOS.

```bash
git clone --branch geohackathon-2026 https://github.com/kimia1999/gemini-geothermal-suite-open.git
cd gemini-geothermal-suite-open/geohackathon_2026
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

On Windows, activate with `.venv\Scripts\activate` and set the path with `set PYTHONPATH=..\src;cases;agent` instead of the `PYTHONPATH=...` prefix below.

For the agent, install Ollama, then:

```bash
ollama pull qwen3:8b
```

## Run

All commands run from this folder.

| What | Command | Time | Expected |
|---|---|---|---|
| Tests (ours) | `python -m pytest agent cases -q` | 1 min | 33 passed |
| Tests (GEMINI models and simulator) | `cd .. && PYTHONPATH=src python -m pytest unit_test/gemini_model unit_test/gemini_simulator -q` | 10 s | 103 passed |
| Agent | `PYTHONPATH=../src:cases:agent python agent/run_agent.py "Design the heating and cooling system for the district. Compare designs and recommend one."` | 3-5 min | `RECOMMENDATION: doublets=2, depth_m=3000, layout=chp+absorption`, then `REVIEWER: accepted.` |
| Price sensitivity and failure study | `PYTHONPATH=../src:cases:agent python agent/sensitivity_study.py` | 2 min | writes `results/sensitivity.md` |
| Figures | `PYTHONPATH=../src:cases:agent python cases/figures.py` | 10 s | writes `results/figures/*.svg` |
| Conventional reference | `PYTHONPATH=../src:cases:agent python cases/reference_case.py` | 5 s | gas boilers + electric chillers: 26.71 kt CO2 at 65.3 EUR/MWh; the design saves 78% |
| GEMINI baseline case | `PYTHONPATH=../src python cases/run_baseline.py` | 5 s | the challenge's reference case (one doublet at 2,500 m) and its checks. It fails the 100 C supply check on purpose: brine at 2,500 m is too cold, which is why the design goes deeper |

The agent needs Ollama running (`ollama serve`, or the Ollama app). Each agent session is logged in `logs/` with every tool call and its token count. Tool results are cached in `agent/memory.json`; delete it to recompute everything (the first design question then takes a few minutes longer).

## Changes to GEMINI

- `src/gemini_simulator/nodal_solver.py`: `_well_bottomhole_pressure_injection` now passes the injection flow as negative, so pipe friction lowers the injector's bottomhole pressure, as in the rest of GEMINI's injection code. Test added in `unit_test/gemini_simulator/test_nodal_solver.py`.
- `src/gemini_model/heatpump/heatpump_basic.py`: Carnot mode is solved directly, COP = eta * Th_out / (Th_out - Ts_in), with a bracketed root search when the source limit applies. Nelder-Mead could stop away from the solution (COP 3.25 instead of 4.60 for 100 C sink and 59.4 C source). One expected value in the existing Carnot test changes by 0.21 W, to the exact value. Two tests added.
- `src/gemini_model/absorption_chiller/`: new hot-water absorption chiller model, demand driven or flow driven, with tests.
- `src/gemini_simulator/registry.py`: `heat_pump` and `absorption_chiller` can be used in plant JSON files.
