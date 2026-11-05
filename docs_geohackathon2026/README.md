# GEMINI GeoDesign Agent (GeoHackathon 2026)

An AI assistant that designs a geothermal heating and cooling plant for a district, built on the
GEMINI digital twin. It runs a small open-source AI model on an ordinary computer (no paid AI service).

**How it works, in one line:** the AI model plans the work, the physics code calculates every number,
and an automatic checker approves the answer before you see it.

Team **DeepLayers** (Behnam Tavagh Mohammadi).

## Where to find what (for the jury)

| You want to see | Look here |
|---|---|
| Every conversation with the agent: questions, answers, rejected drafts, token counts | one file per session: `evidence/<session>/transcript.md`; overview of all sessions: `evidence/Appendix_A_Agent_Evidence.md` |
| The raw logs of each session | `evidence/<session>/`. You can replay any session in the app ("Replay a recorded run"). |
| How we chose the AI model | `evidence/bakeoff/`: 7 open-source models tested on the same 8 tasks |
| What the checker caught, and what the agent learned from it | the rejected drafts in each transcript; the lessons in `evidence/memory_AGENTS.md` |
| The agent noticing a missing model and building it | the S6 transcript, turn 2. The new model and its test are saved next to it (`agent_generated_*.py`). |
| Whether the physics is right | `GEMINI_MODEL_AUDIT.md` (problems we found in GEMINI), each design re-run in GEMINI's own simulator, and `evidence/independent_check.py` (a hand calculation without GEMINI) |
| A bigger AI model, same code | two `qwen3:8b` sessions in `evidence/`: same design for S1; it could not build the new model in S6 |
| Running it yourself | `pip install -r requirements-geohackathon2026.txt`, then `python -m gemini_agent.scenarios qwen3:4b-instruct-2507-q4_K_M S2 lean` |

## What the agent does

Given the challenge brief (daily heating and cooling demand for 2027, the reservoir, the brine and
the limits), the agent:

1. **Reads the brief and the demand.** It lists which GEMINI models exist and which are missing, and
   asks you for anything important that is not given (or, with no user, uses a documented default).
   Before the AI sees your message, simple rules also check it: an impossible request (say 500 m³/h
   per well pair) is flagged, a design you spell out is simulated exactly as you wrote it, and a
   topic with no model in GEMINI (say seasonal storage) is sent to the model builder.
2. **Checks how hot the rock is at different depths** with GEMINI's well models.
3. **Searches over about 135 plant designs**, each simulated day by day for a whole year: depth,
   number of well pairs, heat pump, type of cooling, what to do with the gas in the brine, and a
   backup boiler big enough to cover one failed well pair.
4. **Stress-tests the best design** (coldest day with a well pair down, 10 % more demand, uncertain
   inputs) and adds capacity where it falls short.
5. **Re-runs the design in GEMINI's own simulator** to confirm the numbers.
6. **Writes the answer.** Every number must point to a calculation it actually ran. An automatic
   checker rejects numbers it cannot trace, wrong units, claims that contradict the numbers, or a
   design other than the one you asked for, and sends the draft back once with the exact problem.
7. **Learns.** Each rejection is turned into a short lesson that every later session starts with.

## Quick start

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-geohackathon2026.txt   # exact versions used for every reported result
ollama pull qwen3:4b-instruct-2507-q4_K_M   # bake-off winner; any open-weight model with tool calling works
export PYTHONPATH=src

python -m gemini_agent.cli search          # physics-only optimisation, no LLM
python -m gemini_agent.cli run             # batch agent run (documented defaults)
python -m gemini_agent.cli chat            # terminal conversation
python -m gemini_agent.cli ui              # web cockpit on http://127.0.0.1:7860
python -m gemini_agent.bakeoff qwen3:4b-instruct-2507-q4_K_M qwen2.5:7b llama3.2:3b   # model bake-off
pytest unit_test/gemini_agent unit_test/gemini_model unit_test/gemini_simulator
```

LLM endpoint: Ollama by default (`OLLAMA_HOST`, `GEODESIGN_MODEL`). Any OpenAI-compatible server
hosting open weights (vLLM, llama.cpp) also works: `GEODESIGN_PROVIDER=openai`, `OPENAI_BASE_URL`,
`OPENAI_API_KEY` (placeholder; no commercial API is used).

## Code map

| Path | Content |
|---|---|
| `src/gemini_model/chiller/` | **New** GEMINI models: `AbsorptionChiller` (characteristic equation), `ElectricChiller` |
| `src/gemini_simulator/registry.py` | registers `heat_pump`, `absorption_chiller`, `electric_chiller` |
| `src/gemini_agent/physics/` | brief/site (PI from permeability, gas), wells (GEMINI DPDT/IPR), plant dispatch + annual driver, economics, constraint verifier, GEMINI project compiler/verifier |
| `src/gemini_agent/tools.py` | 22 typed, token-lean agent tools (fact IDs) |
| `src/gemini_agent/agents.py` | deep agent (orchestrator + requirements-analyst, design-engineer, risk-verifier), skills, memory, token-lean harness |
| `src/gemini_agent/workspace/skills/` | domain skills (SKILL.md, progressive disclosure) |
| `src/gemini_agent/ledger.py`, `tracing.py` | fact ledger + provenance check; LLM/tool trace with tokens and latency |
| `src/gemini_agent/optimize.py` | staged design search, Pareto front, stress tests, Monte Carlo |
| `src/gemini_agent/ui/` | Gradio cockpit: one-page agent chat with steps, verifier verdict, inline design results and session replay |
| `src/gemini_agent/bakeoff.py` | open-weight model bake-off (8 deterministic micro-tasks) |
| `docs_geohackathon2026/GEMINI_MODEL_AUDIT.md` | bugs found in GEMINI and what was fixed |

## Assumptions

Inputs the brief does not give are kept in `src/gemini_agent/data/brief_geohackathon2026.yaml`
(`assumptions:`) and `economics_assumptions.yaml`, each with a one-line justification and, where
relevant, a range used by the Monte Carlo analysis.

## Optional calibrated router (off by default)

A Jev/SemIf-style triage step: before the agent runs, the same open-weight model answers *"what kind
of turn is this?"* with one letter (design / follow-up / off-topic / vague / infeasible). The option
probabilities are read from Ollama's token log-probabilities and softened by a temperature fitted on
40 labelled turns (`data/router_labels.yaml`, 2-fold cross-validation). The router answers a turn
itself only when it is confident and the class is off-topic (or vague, before any design exists);
everything else goes to the full agent unchanged.

```bash
GEODESIGN_ROUTER=1 python -m gemini_agent.cli chat     # or: --router / --no-router; cockpit: "Router" switch
python -m gemini_agent.router_eval --write             # re-calibrate for another model
```

Held-out result for qwen3:4b-instruct (`docs_geohackathon2026/evidence/router/router_eval.json`):
design, follow-up and off-topic turns 26/26; vague requests 0/8 (the model calls them designs, so
they stay with the agent, which asks); calibration error 0.30 → 0.14. Uncalibrated, two vague
requests were labelled off-topic at 99–100 % confidence; after calibration they fall below the
0.8 threshold. At 0.8 the router answers all 8 off-topic turns with no wrong answer: 351 tokens and
1.3 s per turn instead of 3,903 tokens and 201 s.

Method and sources: the router implements the SemIf/OpenJev method
([github.com/TheoLeeCJ/SemIf-OpenJev](https://github.com/TheoLeeCJ/SemIf-OpenJev), MIT) -- option
probabilities from next-token logits, as in EleutherAI's lm-evaluation-harness multiple-choice
scoring -- on Ollama's logprobs API, with temperature scaling (Guo et al., ICML 2017) and a
selective-prediction threshold (Geifman & El-Yaniv, NeurIPS 2017). SemIf, Kev and NeoHorse-Jev-4B
(Apache-2.0) were evaluated as drop-in tools; all expect GPU/BF16 weights and a second model, so on
this CPU-only setup the method runs on the model already serving the agent. With a GPU, a trained
decision model such as NeoHorse-Jev-4B or Kev is the natural next step, especially for vague
requests, which the 4B instruct model does not recognise.

To remove it: delete `router.py`, `router_eval.py`, `data/router_*` and the `router` lines in
`runner.py`, `cli.py`, `ui/app.py`, `scenarios.py` and `tracing.py`.
