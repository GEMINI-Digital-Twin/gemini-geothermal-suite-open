# SPE Europe GeoHackathon 2026: geothermal heating and cooling agent

An agent that selects, sizes and checks a deep geothermal direct-use system for one district with GEMINI. It must meet the 2027 daily heating demand (30 MWth peak) and cooling demand (10 MW peak).

The agent runs on an open-weight model (qwen3:8b) through Ollama. The model plans, chooses tools and explains the result. Every number comes from Python tools built on GEMINI's models, and every challenge limit is checked in code.

## Layout

| Folder | Contents |
|---|---|
| `agent/` | Agent loop (`run_agent.py`), tools, plant JSON generator, cost model, answer reviewer, sensitivity study, tests |
| `cases/` | Baseline case, pipe size study, 365-day heating and cooling models, absorption chiller model, tests |
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

## Change to GEMINI

`src/gemini_simulator/nodal_solver.py`: `_well_bottomhole_pressure_injection` now passes the injection flow as negative, so pipe friction lowers the injector's bottomhole pressure, as in the rest of GEMINI's injection code. A test is added in `unit_test/gemini_simulator/test_nodal_solver.py`.
