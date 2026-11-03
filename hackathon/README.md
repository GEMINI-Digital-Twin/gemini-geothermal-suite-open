# Agentic geothermal heating and cooling design (GEMINI hackathon)

Work for the GEMINI agentic geothermal design hackathon, on top of the
`development` branch of the GEMINI geothermal suite. Everything added lives in
this `hackathon/` folder; GEMINI's own `src/` is not modified.

## Architecture

```
fact sheet + demand CSVs (config/, data/)
        |
[A] resource assessment   models/subsurface.py   T, P vs depth; PI via GEMINI bottomhole_skin_dp (r_e = spacing);
                                                 wellhead T via GEMINI DPDT; breakthrough time
[B] doublet               models/subsurface.py   GEMINI DPDT + injector solver (design mode, corrected)
                          models/gemini_project.py  native GEMINI project .json, ESP tuned (project mode)
[C] surface + demand      models/surface.py      absorption (rated / district-heating type), electric chiller,
                                                 direct HX, CHP on associated gas, heat pump, boiler
                          models/dispatch.py     365-day dispatch, KPIs, constraint checks
                          models/economics.py    LCOH with TNO ThermoGIS cost model
                          models/robustness.py   Monte Carlo, P10/P50/P90 (P90 = conservative)
        |
agent (agent/)            agent.py   goal-only prompt; plan -> tool -> observe -> revise -> verify -> finish
                          tools.py   10 tools; non-GEMINI models must be loaded; finish verifies the choice
                          llm_client.py  one client for Ollama (local) and Gemini (API), JSONL token log
```

Every value has a source: see `notes/decisions.md`. GEMINI gaps: `notes/gemini_gaps.md`.

## Setup

```bash
conda activate gemini
pip install pyyaml requests
```

## Run (from the repo root)

```bash
PYTHONPATH=. pytest hackathon/tests -q                        # 16 tests
PYTHONPATH=. python hackathon/validation/validate_doublet.py  # GEMINI vs design mode vs hand estimate
PYTHONPATH=. python hackathon/run_design.py --robust          # one design, with P10/P50/P90
```

## Agent

```bash
# hackathon/.env (ignored by git):  GEMINI_API_KEY=<your key>
# exact API model id: hackathon/agent/llm_config.yaml
PYTHONPATH=. python -m hackathon.agent.agent --scripted                                  # offline, 0 tokens
PYTHONPATH=. python -m hackathon.agent.agent --routing local_only --local-model qwen3.5:4b
PYTHONPATH=. python -m hackathon.agent.agent --routing local_only --local-model qwen3.5:9b
PYTHONPATH=. python -m hackathon.agent.agent --routing hybrid --local-model qwen3.5:4b
PYTHONPATH=. python -m hackathon.agent.agent --routing api_only
```

Each run folder `runs/<timestamp>/` holds `transcript.md`, `llm_log.jsonl`
(every prompt, answer, token count and cost), `token_totals.json`, generated
GEMINI project files, daily tables per design and `final_design.json`.
