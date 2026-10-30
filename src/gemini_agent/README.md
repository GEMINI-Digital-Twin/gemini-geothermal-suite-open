# gemini_agent: physics-gated design agent

The agent answers design questions about the GeoHackathon heating + cooling plant.
The language model plans and talks. Every number it reports comes from a GEMINI run
that passed a six-step physics gate. Numbers it cannot trace to a run are rejected
before the user sees them.

```
user question
   │
   ▼
LLM (any OpenAI-compatible endpoint; default: Qwen 2.5 7B on local Ollama)
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

```powershell
# Windows, local open-weight model
winget install Ollama.Ollama
ollama pull qwen2.5:7b-instruct
$env:PYTHONPATH="src"
python -m gemini_agent                                  # chat
python -m gemini_agent --ask "Which design meets demand at the lowest cost?"
python simulator_examples/run_agent_transcripts.py --backend live   # appendix transcripts
```

Other endpoints: `--provider llamacpp|vllm|openrouter`, or `--base-url` / `--model`.
The API key in the code is the placeholder `YOUR_API_KEY_HERE`. For a hosted endpoint,
put the real key in the environment (`GEMINI_AGENT_API_KEY`), not in a file. If a model
handles native tool calls poorly, use `--no-native-tools`. Tools are then described in
the prompt, and `<tool_call>{...}</tool_call>` JSON in the reply is parsed instead.

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
