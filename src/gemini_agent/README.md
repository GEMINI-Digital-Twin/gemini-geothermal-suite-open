# gemini_agent: physics-gated design agent

The agent answers design questions about the GeoHackathon heating + cooling plant.
The language model plans and talks. The numbers it reports must trace to a GEMINI run
that went through the physics gate (see `HACKATHON.md`, "Physics gate", for what each
of the six checks catches and does not). Answers with numbers it cannot trace to a tool
result, the brief or the user, or with a bare number above 12 and no unit, go back to
the model before the user sees them.

```
user question
   │
   ▼
LLM (any OpenAI-compatible endpoint; default: Qwen3 8B on local Ollama)
   │  tool call (JSON)
   ▼
gate 1: arguments vs schema + ranges ──fail──► error back to the LLM
   │
   ▼
tools ──► gemini_design (365-day dispatch on GEMINI models) / gemini_simulator.Solver
   │
   ▼
gates 2-5 on every year run: hard rules · daily energy balances · Solver re-run of
the peak day · Carnot / temperature-order / pump bounds ──fail──► run marked invalid
   │
   ▼
LLM writes the answer ──► gate 6: every number must match a tool result or a cited run
   │                          (or the brief / the user's message) ──fail──► back to the LLM
   ▼
answer to the user, with run ids  ·  or ask_user for a missing input
```

## What it knows, decides and remembers

| | |
|---|---|
| **Knows** | the brief (`gemini_design.challenge.CHALLENGE`), an assumptions ledger with source + confidence for every assumed value (`knowledge.py`), the list of inputs the brief does not give, and the GEMINI model registry (the system prompt carries no hackathon or grading text) |
| **Decides** | number of doublets, depth, boiler vs heat pump, electric vs absorption cooling, CHP on co-produced gas, equipment sizes, which assumptions to vary, when to ask the user, when a model is missing |
| **Tools** | `describe_inputs`, `list_models`, `run_design`, `screen`, `sensitivity`, `cross_check`, `get_run`, `compare_runs` (a run vs a baseline: deltas and a cost/CO2 Pareto label), `log_option` (verdict + reason on an explored option, reason gated), `reservoir_simulation` (analytic now, Fimbul when `gemini_design.fimbul` exists), `write_model` (sandboxed; its own tests and the harness acceptance tests must pass before registering), `ask_user`, `memory_read`, `memory_write` |
| **Memory** | *scratchpad* (one question, then cleared) · *run ledger* (`run_ledger.jsonl` plus `runs/Rxxxx/summary.json` and `daily.csv`: every run, its gate verdict, reused when identical) · *project notes* (`project_notes.json` / `.md`: decisions, agreed assumptions, lessons, written models; loaded into the system prompt of every new session) |

Tool results are short summaries (about 100 to 400 tokens), never 365-row tables.
Identical runs are reused from the ledger, so repeating a question costs neither
simulation time nor tokens.

## Run it

Default model: **Qwen3 8B** (`qwen3:8b` in Ollama, Q4_K_M, about 5.2 GB). It is
open-weight (Apache 2.0), has native tool calling and a thinking mode, and fits an
8 GB GPU such as an RTX 5060 with a 16k context. Ollama's default context is too
short for the agent, which needs about 3-12k tokens per call, so set
`OLLAMA_CONTEXT_LENGTH` before starting the server.

```powershell
# Windows, local open-weight model
winget install Ollama.Ollama
setx OLLAMA_CONTEXT_LENGTH 16384     # then quit Ollama from the tray and start it again
ollama pull qwen3:8b
pip install numpy scipy pandas requests pytest
$env:PYTHONPATH="src"
python -m gemini_agent                                  # chat
python -m gemini_agent --ask "Which design meets demand at the lowest cost?"
python simulator_examples/run_agent_transcripts.py --backend live   # appendix transcripts
```

Compare backends on the same cases (A1-A6, three repeats each) with
`simulator_examples/compare_agent_models.py`. It writes `results.csv`, `results.json`
and `summary.md` to `simulator_examples/outputs/agent_compare/`:

```powershell
$env:OPENAI_API_KEY="sk-..."     # only needed for the OpenAI backend
python simulator_examples/compare_agent_models.py `
    --backend qwen3-8b=ollama:qwen3:8b `
    --backend gpt-6-luna=openai:gpt-6-luna --price gpt-6-luna=<usd_in>,<usd_out> `
    --repeats 3
```

**Benchmark v2** (`gemini_agent/bench/`, `simulator_examples/run_agent_bench.py`) is the
harder suite: answers are scored against an exhaustive oracle grid on the current code,
claims are checked against the run ledger, and each case is proven to fail a scripted bad
agent (sycophant, injection-follower, rubber-stamper, ...). See `bench/README.md`.

**GPT-6 Luna without an API key (Codex CLI).** With a ChatGPT plan, install the Codex CLI
(`npm install -g @openai/codex`), run `codex login` once, and use the `codex` provider:
`--backend gpt-6-luna=codex:gpt-6-luna` in the comparison, or `--provider codex` in the
CLI. Use the model name `default` to keep Codex's configured model. Each agent step runs
one ephemeral, read-only `codex exec` in an empty temporary folder. The conversation and
tools go in as text, and tool requests come back as `<tool_call>` JSON, so the same tools
and gate apply. Token counts come from Codex's `--json` events and include Codex's own
system prompt, so they overstate what a bare API call would use. Cost is covered by the
plan (leave `--price` out).

Other endpoints: `--provider llamacpp|vllm|openrouter|openai`, or `--base-url` / `--model`.
The `openai` preset treats the model as a reasoning model: it sends no temperature and
uses `max_completion_tokens`. Any endpoint that rejects `max_tokens` is switched to
these parameters automatically. Hidden reasoning (`<think>` blocks, `reasoning_content`)
is logged as "model thinking" and kept out of the answer, and reasoning tokens are
counted separately when the endpoint reports them.
The API key in the code is the placeholder `YOUR_API_KEY_HERE`. For a hosted endpoint,
put the real key in the environment (`OPENROUTER_API_KEY` for OpenRouter, `OPENAI_API_KEY`
for OpenAI, or `GEMINI_AGENT_API_KEY` for any endpoint), not in a file. If a model handles native tool calls poorly, use `--no-native-tools`. Tools are
then described in the prompt, and `<tool_call>{...}</tool_call>` JSON in the reply is
parsed instead.

`--backend scripted` replays a fixed policy (`scenarios.py`) without any model server.
It exists so that the tools, gate, memory and logging can be tested and shown offline.
Its transcripts are labelled *scripted* and are not LLM output.

## Exploring more ambitious designs

`compare_runs` puts any run next to a baseline (usually the current pick) and labels it:
*dominates* (cheaper and lower CO2), *dominated*, a *trade-off*, or *infeasible*.
`log_option` records the agent's verdict on an option (`accept`, `alternative` or
`reject`) with a one-sentence reason. The reason goes through gate 6 against the two
runs, so it cannot quote a number the runs do not contain, and an option that is
dominated or infeasible cannot be accepted. Verdicts are written to `exploration.jsonl`
and an `exploration.md` table in the workspace, and `memory_read` returns them, so a
later question ("would something more ambitious score better?") is answered from the
log without re-running.

Seasonal heat storage is an option GEMINI has no model for. A design with
`storage_mwh > 0` looks up the `thermal_storage` slot in the component registry; when it
is empty the run stops with an error that names the interface the model needs. The agent
writes the model with `write_model`, it is registered only if its own tests and the
harness acceptance tests pass (below), and `gemini_design.storage.check_model` checks it
again for an energy balance and its limits before every year run. Gate 3 checks the store's daily state-of-charge balance.

### Harness acceptance tests for agent-written models

The agent writes a model *and* its tests, so a passing test only shows that the model
does what its author believed. `write_model` therefore runs a second test set that the
harness owns and the agent can not see or change (`gemini_agent.acceptance`, in its own
process with a time limit):

- every model: a GEMINI `Model` subclass that builds with no arguments, stores results in
  `self.output`, returns finite numbers, is deterministic and does not change its inputs;
- model slots with a contract (`dry_cooler`, `thermal_storage`, listed with units and
  checks by `list_models` under `model_contracts`): probed over a grid of inputs including
  edge cases (zero flow, air hotter than the water, a full or empty store), they must
  conserve energy, respect the second law and their limits (effectiveness 0-1, fan power,
  power rating, capacity) and respond in the physically right direction.

A rejected model comes back to the agent with the problems and the contract, so it can
fix it. `simulator_examples/run_model_red_team.py` measures what this adds: it plants 22
known bugs in the two demo models (energy created, kJ/J and m3/h/m3/s unit slips,
effectiveness above 1, a crash at zero flow, hidden state, a hard-coded power rating, ...).
The agent's own tests catch 13/22; with the harness tests 21/22 are caught (all 21 the
harness is designed for), with no false alarm on the clean models. The one miss is a dry
cooler half as effective as it should be: still physical, so only vendor data would
catch it.

Scenario `09_explore_ambitious` shows the whole loop (scripted offline; run it live with
`run_agent_transcripts.py --backend live --only 09_explore_ambitious`). The batch study
`simulator_examples/run_ambitious_study.py` runs about 175 options the same way (every
run gated, compared with the pick) and writes `results.md` with the Pareto front, any
design that beats the pick, and the storage price at which each store design breaks even.

## Logs for the report

Each session writes `agent_workspace/transcripts/<name>.jsonl`, with every LLM call
(reasoning text, tool calls, prompt and completion tokens, latency), tool call (arguments,
result preview, size in tokens, seconds), gate rejection and reply. It also writes a
Markdown rendering with a token table per question. `run_agent_transcripts.py` adds
`index.md` with totals across the demo scenarios. These include an off-topic question,
incomplete questions where the agent asks for the missing input, an invented number
caught by gate 6, an out-of-range request caught by gate 1, and the agent writing a
missing model.

Token counts come from the endpoint's `usage` field. When an endpoint does not report
usage, they are estimated at about 4 characters per token and marked as estimated.

## Limits

- Gate 6 matches numbers, not claims. A sentence can still misstate which run a number
  came from. Runs are cited so a reader can check.
- Gate 3 (energy balances) is mostly the dispatcher's own bookkeeping, so it catches broken
  or edited results rather than wrong physics. Gate 4 re-solves one day (the heating peak)
  and compares two temperatures; it is skipped for designs with doublets at mixed depths.
- The run ledger reuses a run only for the same design, overrides, demand and weather
  profile, physics code and data files and default assumptions
  (`gemini_agent.fingerprint`), so a workspace can be reused across input sets.
- Small models (7B) sometimes produce malformed tool calls. Gate 1 returns the error and
  the model retries, but a 14B+ model is noticeably more reliable.
- The harness acceptance tests check physics laws and limits, not calibration: a model
  that is physical but wrong in size (half the effectiveness) passes. A slot without a
  contract only gets the interface checks, and no design run uses such a model.
- `write_model` runs generated tests in a separate process with a time limit and an
  import allowlist, and blocks `open`, `eval`/`exec` and numpy/scipy file I/O. This is a guard against mistakes, not a security boundary for
  untrusted users.
