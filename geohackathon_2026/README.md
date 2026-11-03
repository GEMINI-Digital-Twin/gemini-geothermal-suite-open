# SPE Europe GeoHackathon 2026: geothermal heating and cooling agent

An agent that selects, sizes and checks a deep geothermal direct-use system for one district with GEMINI. It must meet the 2027 daily heating demand (30 MWth peak) and cooling demand (10 MW peak).

The agent chooses the number of doublets, the depth and the layout: gas boiler or heat pump to reach 100 C, and absorption or electric chillers. It then checks the chosen design for return temperature, an unplanned failure over the peak, subsurface, demand and grid uncertainty, and every operating day in GEMINI plant files.

The agent runs on an open-weight model (qwen3:8b) through Ollama. The model plans, chooses tools and explains the result. Every number comes from Python tools built on GEMINI's models, and every challenge limit is checked in code.

## Layout

| Folder | Contents |
|---|---|
| `agent/` | Agent loop (`run_agent.py`), tools, plant JSON generator and GEMINI year run (`plant_json.py`, `plant_year.py`), uncertainty sampling, cost model, answer reviewer, sensitivity study, tests |
| `cases/` | Baseline case, pipe size study, 365-day heating and cooling models with layouts |
| `results/` | Yearly results, sensitivity tables, generated GEMINI plant files, evidence summary |
| `logs/` | One file per agent session, with every tool call and token counts |

The two demand files are the challenge inputs.

## Run

Python 3.11 with numpy, scipy and pandas. Run from this folder:

```bash
PYTHONPATH=../src:cases:agent python -m pytest agent cases -q
```

```bash
PYTHONPATH=../src python cases/yearly_energy.py
```

```bash
ollama pull qwen3:8b
PYTHONPATH=../src:cases:agent python agent/run_agent.py "Design the heating and cooling system for the district."
```

## Changes to GEMINI

- `src/gemini_simulator/nodal_solver.py`: `_well_bottomhole_pressure_injection` now passes the injection flow as negative, so pipe friction lowers the injector's bottomhole pressure, as in the rest of GEMINI's injection code. Test added in `unit_test/gemini_simulator/test_nodal_solver.py`.
- `src/gemini_model/heatpump/heatpump_basic.py`: Carnot mode is solved directly, COP = eta * Th_out / (Th_out - Ts_in), with a bracketed root search when the source limit applies. Nelder-Mead could stop away from the solution (COP 3.25 instead of 4.60 for 100 C sink and 59.4 C source). One expected value in the existing Carnot test changes by 0.21 W, to the exact value. Two tests added.
- `src/gemini_model/absorption_chiller/`: new hot-water absorption chiller model, demand driven or flow driven, with tests.
- `src/gemini_simulator/registry.py`: `heat_pump` and `absorption_chiller` can be used in plant JSON files.
