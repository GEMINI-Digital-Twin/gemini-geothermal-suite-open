# Agentic geothermal heating and cooling design (GEMINI hackathon)

Contribution to the SPE Europe Energy GeoHackathon (GEMINI), on top of the
`development` branch of the GEMINI geothermal suite. Everything added lives in
this `hackathon/` folder; GEMINI's own `src/` is not modified. GEMINI issues
found on the way are described in `notes/gemini_gaps.md` and in the pull request.

## Result

| | Agent's final design (run 5, D10) | Recommended design |
|---|---|---|
| Wells | 3 doublets x 3500 m, 1800 m spacing, 120 m3/h each | 2 doublets x 3300 m, 1600 m spacing, up to 300 m3/h each |
| Surface | absorption (DH type) 10 MW, electric chiller 5 MW, gas boiler 25 MW | heat pump 4 MW, absorption (DH type) 10 MW, electric chiller 4 MW (backup), gas boiler 15 MW (backup) |
| LCOH P10 / P50 / P90 (EUR/MWh) | 60.9 / 62.6 / 64.4 | 57.5 / 57.9 / 58.2 |
| Feasible in uncertainty samples | 100% | 100% (100 samples) |
| CO2 (kt/yr) | 7.3 | 5.1 |
| Heat from gas boiler in a normal year | 15.5 GWh | 0 |

The recommended design was found with the same tools the agent uses
(`run_design.py`, `figures/make_figures.py`); it meets the heating (111.7 GWh,
100 C) and cooling (23.7 GWh, 20 C) demand on all 365 days, also on the peak day
with one doublet out (15 MW backup boiler). Full calculation (KPIs, CAPEX/OPEX
breakdown, P10/P50/P90, return-temperature sensitivity, all 365 days):
`results/recommended_design.json` and `results/recommended_daily.csv`. LCOH uses TNO ThermoGIS cost defaults
and compares designs; it is not a cost forecast. CO2 is reported, not priced.

## Architecture

```
fact sheet + demand CSVs (config/, data/)
        |
[A] resource assessment   models/subsurface.py   T, P vs depth; PI via GEMINI bottomhole_skin_dp (r_e = spacing);
                                                 wellhead T via GEMINI DPDT; breakthrough time
[B] doublet               models/subsurface.py   GEMINI DPDT + injector solver (friction sign corrected)
                          models/gemini_project.py  native GEMINI project .json, ESP tuned to a target flow
[C] surface + demand      models/surface.py      absorption chiller, electric chiller, direct HX,
                                                 CHP on associated gas, heat pump, boiler
                          models/dispatch.py     365-day dispatch, KPIs, CO2, constraint checks
                          models/economics.py    LCOH with the TNO ThermoGIS cost model
                          models/robustness.py   Monte Carlo, P10/P50/P90 (P90 = conservative)
        |
agent (agent/)            agent.py       goal-only prompt; tool loop; loop guard; JSONL log
                          tools.py       10 tools; non-GEMINI models must be loaded first;
                                         finish checks F1-F3 before accepting a design
                          llm_client.py  one client for Ollama (local) and Gemini (API)
```

Every input value has a source: `config/fixed_inputs.yaml` and `notes/decisions.md`.

## Libraries and models

GEMINI (`gemini_model`, `gemini_simulator`), Python 3.11, NumPy, pandas, SciPy,
PyYAML, requests, matplotlib. LLM: qwen3.5 4B through Ollama's OpenAI-compatible
endpoint, run locally (no API cost, no data leaves the machine). The client also
supports the Gemini API free tier and a hybrid local/API routing (not used in
the recorded runs).

## Setup

```bash
conda activate gemini
pip install pyyaml requests matplotlib
# Ollama: the default 4096-token context truncates the prompt; create a 32k variant
printf 'FROM qwen3.5:4b\nPARAMETER num_ctx 32768\n' > Modelfile && ollama create qwen3.5-4b-32k -f Modelfile
```

## Run (from the repo root)

```bash
PYTHONPATH=. pytest hackathon/tests -q                        # 21 tests
PYTHONPATH=. python hackathon/validation/validate_doublet.py  # GEMINI project vs design model vs hand formulas
PYTHONPATH=. python hackathon/run_design.py --robust          # recommended design + P10/P50/P90 -> results/
PYTHONPATH=. python -m hackathon.figures.make_figures         # slide figures -> figures/out/

PYTHONPATH=. python -m hackathon.agent.agent --scripted       # offline replay, no LLM, 0 tokens
PYTHONPATH=. python -m hackathon.agent.agent --routing local_only --local-model qwen3.5-4b-32k --max-steps 50
```

## Agent runs (prompts, answers, token usage)

Each run folder `runs/<timestamp>/` holds `transcript.md` (readable record of
every step), `llm_log.jsonl` (every prompt, answer and token count),
`token_totals.json`, daily tables per evaluated design and `final_design.json`.

| Run | Folder | Calls | Model time | Tokens in / out | Result |
|---|---|---|---|---|---|
| 2 | `runs/20261104_192033` | 20 | 28 min | 115k / 4k | D4, P50 90.5 EUR/MWh |
| 3 | `runs/20261105_083545` | 35 | 37 min | 282k / 8k | step limit, no design |
| 4 | `runs/20261105_092244` | 31 | 74 min | 273k / 9k | D5, P50 86.3 EUR/MWh |
| 5 (final) | `runs/20261105_112007` | 30 | 57 min | 263k / 8k | D10, P50 62.6 EUR/MWh |
| 6 | `runs/20261105_123809` | 15 | stopped | - | same code as run 5; host slowed down |

All runs: qwen3.5 4B, local, cost EUR 0. Between runs, tools and checks were
added where the model failed (loop guard, clearer tool messages, the F3 coverage
check, units and ranges on every input); the commit history shows each change.

## Authorship

AI-assisted code by Claude (Anthropic), designed, reviewed, tested and run by
the repository owner.
