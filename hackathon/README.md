# Agentic geothermal heating and cooling design (GEMINI hackathon)

Work for the GEMINI agentic geothermal design hackathon, on top of the
`development` branch of the GEMINI geothermal suite. Everything added lives in
this `hackathon/` folder; GEMINI's own `src/` is not modified.

## Architecture

```
fact sheet + demand CSVs (config/, data/)
        |
[A] resource assessment    models/subsurface.py   T, P vs depth; PI from k,h,mu; wellhead T
[B] doublet                models/subsurface.py   GEMINI IPR + DPDT + injector solver (design mode)
                           models/gemini_project.py  native GEMINI project .json, ESP tuned (project mode)
[C] surface + demand       models/surface.py      sorption/electric chiller, direct HX, CHP, heat pump, boiler
                           models/dispatch.py     365-day dispatch, KPIs, constraint checks
        |
agent (agent/)             agent.py: plan -> tool -> observe -> revise -> compare -> finish
                           tools.py: 8 tools; non-GEMINI models must be loaded before use
                           llm_client.py: one client for Ollama (local) and Gemini (API), JSONL token log
```

## Agent

```bash
# 1. hackathon/.env  (ignored by git)
GEMINI_API_KEY=<your key>
# 2. set exact model ids in hackathon/agent/llm_config.yaml
# 3. run
PYTHONPATH=. python -m hackathon.agent.agent --scripted          # offline check, 0 tokens
PYTHONPATH=. python -m hackathon.agent.agent --routing local_only
PYTHONPATH=. python -m hackathon.agent.agent                     # hybrid (from config)
```

Each run folder `runs/<timestamp>/` holds `transcript.md`, `llm_log.jsonl`
(every prompt, answer, token count and cost), `token_totals.json`, the GEMINI
project files the agent generated, daily tables per design and
`final_design.json`.

## Setup

```bash
conda activate gemini
pip install pyyaml          # the only package beyond GEMINI's numpy/scipy/pandas
```

## Run (from the repo root)

```bash
PYTHONPATH=. pytest hackathon/tests -q                     # 11 tests
PYTHONPATH=. python hackathon/validation/validate_doublet.py  # GEMINI vs design mode vs hand estimate
PYTHONPATH=. python hackathon/run_design.py                # one design over 365 days
```

## What to review

* `config/fixed_inputs.yaml`, section `assumptions`: every value has status
  `default` until the owner confirms it.
* `models/surface.py`, `SurfaceParams`: technology parameters marked DEFAULT
  (sorption COP and drive temperatures, CHP efficiencies, heat pump limits).
* `notes/gemini_gaps.md`: the GEMINI gaps found and how each is handled.
