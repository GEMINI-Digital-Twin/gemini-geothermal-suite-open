# gemini_agent: physics-gated design agent

The agent answers design questions about the GeoHackathon heating + cooling plant.
The language model plans and talks. Every number it reports comes from a GEMINI run
that passed a six-step physics gate. Numbers it cannot trace to a run are rejected
before the user sees them.

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
| **Knows** | the brief (`gemini_design.challenge.CHALLENGE`), an assumptions ledger with source + confidence for every assumed value (`knowledge.py`), the list of inputs the brief does not give, the GEMINI model registry, and the grading rubric |
| **Decides** | number of doublets, depth, boiler vs heat pump, electric vs absorption cooling, CHP on co-produced gas, equipment sizes, which assumptions to vary, when to ask the user, when a model is missing |
| **Tools** | `describe_inputs`, `list_models`, `run_design`, `screen`, `sensitivity`, `cross_check`, `get_run`, `reservoir_simulation` (analytic now, Fimbul when `gemini_design.fimbul` exists), `write_model` (sandboxed, tested before registering), `ask_user`, `memory_read`, `memory_write` |
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
put the real key in the environment (`GEMINI_AGENT_API_KEY` or `OPENAI_API_KEY`), not in
a file. If a model handles native tool calls poorly, use `--no-native-tools`. Tools are
then described in the prompt, and `<tool_call>{...}</tool_call>` JSON in the reply is
parsed instead.

`--backend scripted` replays a fixed policy (`scenarios.py`) without any model server.
It exists so that the tools, gate, memory and logging can be tested and shown offline.
Its transcripts are labelled *scripted* and are not LLM output.

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
- Small models (7B) sometimes produce malformed tool calls. Gate 1 returns the error and
  the model retries, but a 14B+ model is noticeably more reliable.
- `write_model` runs generated tests in a separate process with a time limit and an
  import allowlist. This is a guard against mistakes, not a security boundary for
  untrusted users.
