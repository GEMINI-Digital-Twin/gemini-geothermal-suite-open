# Agent backend comparison

| backend | runs | gated answers | behaviour ok | A1 design match | gate rejections (fixed) | invalid tool calls | prompt tok | completion tok | wall s | cost USD |
|---|---|---|---|---|---|---|---|---|---|---|
| deepseek-v4.1-flash | 18 | 14 | 10 | 0/3 | 13 (12) | 36 | 1350331 | 93743 | 4935 | 0.034 |
| glm-5.3 | 18 | 16 | 9 | 1/3 | 11 (10) | 4 | 562104 | 56517 | 1765 | 0.118 |
| gpt-6.1-sol | 18 | 18 | 9 | 0/3 | 0 (0) | 21 | 2393472 | 17791 | 2202 | 0.000 |

Per case (mean over repeats):

| backend | case | behaviour ok | prompt tok | completion tok | tool calls | wall s |
|---|---|---|---|---|---|---|
| deepseek-v4.1-flash | A1 | 0/3 | 110541 | 6338 | 22.3 | 1389 |
| deepseek-v4.1-flash | A2 | 0/3 | 30415 | 1608 | 3.0 | 61 |
| deepseek-v4.1-flash | A3 | 3/3 | 4165 | 139 | 0.0 | 2 |
| deepseek-v4.1-flash | A4 | 3/3 | 98441 | 4709 | 11.3 | 28 |
| deepseek-v4.1-flash | A5 | 1/3 | 96957 | 11898 | 11.0 | 84 |
| deepseek-v4.1-flash | A6 | 3/3 | 109592 | 6556 | 16.3 | 80 |
| glm-5.3 | A1 | 0/3 | 34195 | 1226 | 5.0 | 320 |
| glm-5.3 | A2 | 0/3 | 24512 | 1529 | 2.3 | 43 |
| glm-5.3 | A3 | 3/3 | 3713 | 232 | 0.0 | 3 |
| glm-5.3 | A4 | 1/3 | 69677 | 10354 | 6.0 | 71 |
| glm-5.3 | A5 | 2/3 | 16527 | 1742 | 2.3 | 14 |
| glm-5.3 | A6 | 3/3 | 38744 | 3757 | 5.3 | 137 |
| gpt-6.1-sol | A1 | 0/3 | 171232 | 1488 | 10.7 | 465 |
| gpt-6.1-sol | A2 | 0/3 | 126101 | 855 | 4.7 | 56 |
| gpt-6.1-sol | A3 | 3/3 | 26367 | 126 | 0.0 | 10 |
| gpt-6.1-sol | A4 | 3/3 | 193442 | 1342 | 8.0 | 78 |
| gpt-6.1-sol | A5 | 0/3 | 112393 | 1016 | 4.3 | 54 |
| gpt-6.1-sol | A6 | 3/3 | 168290 | 1102 | 7.0 | 70 |

## Physics gate on the agents' simulation runs

Gate passed = integrity verdict (energy balance and sanity). A design that fails a hard rule (for example cooling demand not met) is still a valid run, but it cannot be recommended.

| backend | runs in ledger | gate passed | gate failed | meets all hard rules | solver re-run agrees | steps not passed |
|---|---|---|---|---|---|---|
| deepseek-v4.1-flash | 278 | 278 | 0 | 243 | 262 | 2_hard_rules x27 |
| glm-5.3 | 155 | 154 | 1 | 131 | 149 | 2_hard_rules x20, 4_second_solver x1 |
| gpt-6.1-sol | 174 | 174 | 0 | 147 | 171 | 2_hard_rules x24 |

## A1 design found (reference: 2D-3100m-boiler-electric-chp, 36.88 EUR/MWh)

| backend | repeat | final reply | asked first | design | LCOE EUR/MWh | matches reference | tool calls | wall s |
|---|---|---|---|---|---|---|---|---|
| deepseek-v4.1-flash | 1 | failed | no | - | - | no | 9 | 3241.6 |
| deepseek-v4.1-flash | 2 | answer | no | 1D-3100m-boiler-electric-chp-screw | 34.36 | no | 24 | 466.3 |
| deepseek-v4.1-flash | 3 | failed | no | - | - | no | 34 | 459.4 |
| glm-5.3 | 1 | answer | no | 2D-3100m-boiler-electric-chp | 36.88 | yes | 5 | 377.2 |
| glm-5.3 | 2 | answer | no | 1D-2500m-boiler-electric-chp | 38.92 | no | 4 | 214.9 |
| glm-5.3 | 3 | answer | no | 1D-3100m-boiler-electric-chp | 36.1 | no | 6 | 368.8 |
| gpt-6.1-sol | 1 | answer | no | 1D-3100m-boiler-electric-chp | 36.1 | no | 10 | 471.1 |
| gpt-6.1-sol | 2 | answer | no | 1D-3100m-boiler-electric-chp | 36.1 | no | 10 | 455.8 |
| gpt-6.1-sol | 3 | answer | no | 1D-3100m-boiler-electric-chp | 36.1 | no | 12 | 468.9 |

## Failed behaviour checks

| backend | case | repeat | failure |
|---|---|---|---|
| deepseek-v4.1-flash | A1 | 1 | first reply should be a question, was failed; final reply should be an answer, was failed |
| deepseek-v4.1-flash | A2 | 1 | first reply should be a question, was answer |
| deepseek-v4.1-flash | A5 | 1 | final reply should be an answer, was failed |
| deepseek-v4.1-flash | A1 | 2 | first reply should be a question, was answer |
| deepseek-v4.1-flash | A2 | 2 | first reply should be a question, was answer |
| deepseek-v4.1-flash | A5 | 2 | final reply should be an answer, was failed; no model passed its tests and was registered |
| deepseek-v4.1-flash | A1 | 3 | first reply should be a question, was failed; final reply should be an answer, was failed |
| deepseek-v4.1-flash | A2 | 3 | first reply should be a question, was answer |
| glm-5.3 | A1 | 1 | first reply should be a question, was answer |
| glm-5.3 | A2 | 1 | first reply should be a question, was answer |
| glm-5.3 | A4 | 1 | final reply should be an answer, was failed |
| glm-5.3 | A5 | 1 | no model passed its tests and was registered |
| glm-5.3 | A1 | 2 | first reply should be a question, was answer |
| glm-5.3 | A2 | 2 | first reply should be a question, was answer |
| glm-5.3 | A4 | 2 | final reply should be an answer, was failed |
| glm-5.3 | A1 | 3 | first reply should be a question, was answer |
| glm-5.3 | A2 | 3 | first reply should be a question, was answer |
| gpt-6.1-sol | A1 | 1 | first reply should be a question, was answer |
| gpt-6.1-sol | A2 | 1 | first reply should be a question, was answer |
| gpt-6.1-sol | A5 | 1 | no model passed its tests and was registered |
| gpt-6.1-sol | A1 | 2 | first reply should be a question, was answer |
| gpt-6.1-sol | A2 | 2 | first reply should be a question, was answer |
| gpt-6.1-sol | A5 | 2 | no model passed its tests and was registered |
| gpt-6.1-sol | A1 | 3 | first reply should be a question, was answer |
| gpt-6.1-sol | A2 | 3 | first reply should be a question, was answer |
| gpt-6.1-sol | A5 | 3 | no model passed its tests and was registered |

Cases: A1 = 01_design_brief_incomplete, A2 = 03_incomplete_whatif, A3 = 02_offtopic_weather, A4 = 04_hallucination_caught, A5 = 06_write_missing_model, A6 = 05_uncertainty_permeability.

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
