## Run conditions and notes

- Date: 2026-10-31, 15:05-17:34 local time, on one Windows 11 PC (32 GB RAM). Code: commit `18f5d40` on `development` (after PRs #4-#7). Same agent, tools, prompt and physics gate for all three backends. Cases A1-A6, 3 repeats each, fresh workspace per repeat.
- DeepSeek V4.1 Flash: `openrouter:deepseek/deepseek-v4.1-flash-1017` with native tool calls. Cost uses the OpenRouter list price on 2026-10-31: USD 0.0141 per M input and USD 0.158 per M output tokens.
- GLM 5.3: `openrouter:z-ai/glm-5.3` with native tool calls. Cost uses the OpenRouter list price on 2026-10-31: USD 0.0699 per M input and USD 1.40 per M output tokens.
- GPT-6.1 Sol: `codex:gpt-6.1-sol` through the Codex CLI 0.166.0 with a ChatGPT plan (no API key). Tools go in as text and come back as `<tool_call>` JSON. Prompt tokens include the Codex system prompt on every step. Cost is covered by the plan, so the cost column shows 0. The plan usage limit did not stop any case.
- Total OpenRouter cost: USD 0.15 for 36 cases (DeepSeek USD 0.034, GLM USD 0.118), plus USD 0.0035 for the A1 rerun.
- Screen settings: `OPENBLAS_NUM_THREADS=1` and 2 screen workers, because free RAM was low. Wall times include simulation time, so they depend on the PC load.
- Raw workspaces (120 MB) are in `simulator_examples/outputs/agent_compare_more_models/` (not tracked). This folder holds the collected rows, tables and transcripts (`collect_agent_compare.py`).
- One of 54 cases ended with an infrastructure failure, not a model decision:
  - deepseek-v4.1-flash A1 r1: the OpenRouter read timed out. The case ran for 54 minutes in total. I ran this case again once in a fresh workspace (`a1_rerun/`, 547 s, USD 0.0035). The rerun had no infrastructure failure, but DeepSeek stopped at the 14-step limit after 27 tool calls without a gated answer. The main tables keep the timeout row.

### Comparison with the earlier run

- The GPT-6 Luna and Qwen3 235B run (`../2026-10-31/`) used older code, before PRs #4-#7. Only case A5 was run again after the import fix (`../2026-10-31/a5_rerun/`). A5 here is comparable only to `a5_rerun`, and the other cases are comparable only with care.
- The A1 reference is a fixed design (`REFERENCE` in `compare_agent_models.py`): 2D-3100m-boiler-electric-chp. On this code it costs 36.88 EUR/MWh (33.49 EUR/MWh on the old code). It is no longer the cheapest valid design. The new chiller menu and the doublet operating rules changed the ranking. In these runs, the cheapest base-case design that met all hard rules and passed the gate was 1D-3100m-boiler-electric-chp-screw at 34.36 EUR/MWh. Thus the "A1 design match" column counts a match with an old optimum, not the best design. Update the reference before the next comparison.

### Behaviour findings

- Missing inputs (A1, A2): no backend asked for the missing return temperatures before it ran the screen (0/9 each for A1 and A2 over all backends). All used the brief defaults and said so. This is the same as the earlier run.
- A1 designs found (base case, 36.88 EUR/MWh reference):
  - DeepSeek: r2 found 1D-3100m-boiler-electric-chp-screw at 34.36 EUR/MWh, the cheapest valid design of all runs. r3 and the r1 rerun stopped at the 14-step limit: DeepSeek runs many screen and sensitivity steps and does not finish in time.
  - GLM: r1 matched the reference (36.88), r2 picked 1D-2500m (38.92), r3 picked 1D-3100m-boiler-electric-chp (36.10).
  - Sol: all 3 repeats picked 1D-3100m-boiler-electric-chp at 36.10 EUR/MWh. This design meets all hard rules, passes the gate and costs less than the reference, but Sol did not try the chiller options.
- Off-topic question (A3): all backends declined without tools (9/9).
- Hallucination check (A4): DeepSeek 3/3, Sol 3/3, GLM 1/3. Both GLM failures stopped at the 14-step limit before a gated answer.
- Uncertainty (A6): all backends ran a permeability sensitivity (9/9).
- Write a dry cooler model (A5): DeepSeek 1/3, GLM 2/3, Sol 0/3.
  - Sol (3/3) and GLM r1 said that a dry cooler already exists and wrote no model. They read the `dry_cooler` contract in `list_models` -> `model_contracts` as a registered model. The chiller menu also has a `screw_dry_cooler` option. Thus the case text "GEMINI has no dry cooler model" now conflicts with what the tools show. `model_slots` gives a "registered / EMPTY" status only for thermal storage, not for the dry cooler. This is a gap in the tool output and the case, not only a model error.
  - DeepSeek r1 and r2 stopped at the 14-step limit with 6 and 12 invalid calls. Its `write_model` calls arrived with no arguments or with arguments that could not be parsed (`_unparsed`): the long code argument did not come through as valid JSON.
- Tool use and the physics gate:
  - Invalid tool calls: DeepSeek 36, Sol 21, GLM 4.
  - Gate 6 rejected final answers with untraced numbers: DeepSeek 13 (12 fixed), GLM 11 (10 fixed), Sol 0. Sol cites run ids in every answer.
  - The physics gate passed all but one simulation run of the three backends. One GLM run failed the second-solver check (4_second_solver), and the gate stopped it as designed.
- Token use and speed: Sol used the most prompt tokens (2.39 M, mostly the Codex system prompt) but the fewest output tokens (18 k). GLM used the fewest prompt tokens (0.56 M) and was the fastest (1765 s for 18 cases). DeepSeek was the cheapest per token but used 1.35 M prompt tokens and many steps.
