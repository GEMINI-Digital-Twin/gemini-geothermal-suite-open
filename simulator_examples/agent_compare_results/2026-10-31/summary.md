# Agent backend comparison

| backend | runs | gated answers | behaviour ok | A1 design match | gate rejections (fixed) | invalid tool calls | prompt tok | completion tok | wall s | cost USD |
|---|---|---|---|---|---|---|---|---|---|---|
| gpt-6-luna | 18 | 17 | 9 | 2/3 | 1 (1) | 10 | 3509567 | 49692 | 3733 | 0.000 |
| qwen3-235b | 18 | 16 | 9 | 1/3 | 2 (2) | 19 | 467640 | 21839 | 3701 | 0.054 |

Per case (mean over repeats):

| backend | case | behaviour ok | prompt tok | completion tok | tool calls | wall s |
|---|---|---|---|---|---|---|
| gpt-6-luna | A1 | 0/3 | 181259 | 1210 | 5.7 | 341 |
| gpt-6-luna | A2 | 1/3 | 168258 | 1240 | 3.3 | 35 |
| gpt-6-luna | A3 | 3/3 | 22047 | 46 | 0.0 | 5 |
| gpt-6-luna | A4 | 2/3 | 216928 | 2197 | 3.3 | 47 |
| gpt-6-luna | A5 | 0/3 | 289190 | 10071 | 2.0 | 609 |
| gpt-6-luna | A6 | 3/3 | 292173 | 1800 | 5.3 | 209 |
| qwen3-235b | A1 | 0/3 | 26647 | 416 | 5.0 | 792 |
| qwen3-235b | A2 | 0/3 | 13947 | 714 | 2.7 | 124 |
| qwen3-235b | A3 | 3/3 | 2948 | 47 | 0.0 | 3 |
| qwen3-235b | A4 | 3/3 | 38555 | 2082 | 5.7 | 123 |
| qwen3-235b | A5 | 0/3 | 55478 | 3543 | 8.3 | 142 |
| qwen3-235b | A6 | 3/3 | 18306 | 478 | 3.0 | 50 |

## Physics gate on the agents' simulation runs

Gate passed = integrity verdict (energy balance and sanity). A design that fails a hard rule (for example cooling demand not met) is still a valid run, but it cannot be recommended.

| backend | runs in ledger | gate passed | gate failed | meets all hard rules | solver re-run agrees | steps not passed |
|---|---|---|---|---|---|---|
| gpt-6-luna | 152 | 152 | 0 | 125 | 145 | 2_hard_rules x20 |
| qwen3-235b | 152 | 152 | 0 | 128 | 148 | 2_hard_rules x20 |

## A1 design found (reference: 2D-3100m-boiler-electric-chp, 33.49 EUR/MWh)

| backend | repeat | final reply | asked first | design | LCOE EUR/MWh | matches reference | tool calls | wall s |
|---|---|---|---|---|---|---|---|---|
| gpt-6-luna | 1 | answer | no | 1D-3100m-boiler-electric | 36.04 | no | 2 | 238.1 |
| gpt-6-luna | 2 | answer | no | 2D-3100m-boiler-electric-chp | 33.49 | yes | 10 | 459.0 |
| gpt-6-luna | 3 | answer | no | 2D-3100m-boiler-electric-chp | 33.49 | yes | 5 | 324.6 |
| qwen3-235b | 1 | answer | no | 1D-3100m-boiler-electric | 36.04 | no | 6 | 205.5 |
| qwen3-235b | 2 | failed | no | - | - | no | 3 | 1860.0 |
| qwen3-235b | 3 | answer | no | 2D-3100m-boiler-electric-chp | 33.49 | yes | 6 | 309.8 |

## Failed behaviour checks

| backend | case | repeat | failure |
|---|---|---|---|
| gpt-6-luna | A1 | 1 | first reply should be a question, was answer |
| gpt-6-luna | A2 | 1 | first reply should be a question, was answer |
| gpt-6-luna | A5 | 1 | no model passed its tests and was registered |
| gpt-6-luna | A1 | 2 | first reply should be a question, was answer |
| gpt-6-luna | A2 | 2 | first reply should be a question, was answer |
| gpt-6-luna | A5 | 2 | no model passed its tests and was registered |
| gpt-6-luna | A1 | 3 | first reply should be a question, was answer |
| gpt-6-luna | A4 | 3 | should call one of ['run_design', 'screen'] |
| gpt-6-luna | A5 | 3 | final reply should be an answer, was failed; no model passed its tests and was registered |
| qwen3-235b | A1 | 1 | first reply should be a question, was answer |
| qwen3-235b | A2 | 1 | first reply should be a question, was answer |
| qwen3-235b | A5 | 1 | final reply should be an answer, was failed; no model passed its tests and was registered |
| qwen3-235b | A1 | 2 | first reply should be a question, was failed; final reply should be an answer, was failed |
| qwen3-235b | A2 | 2 | first reply should be a question, was answer |
| qwen3-235b | A5 | 2 | no model passed its tests and was registered |
| qwen3-235b | A1 | 3 | first reply should be a question, was answer |
| qwen3-235b | A2 | 3 | first reply should be a question, was answer |
| qwen3-235b | A5 | 3 | no model passed its tests and was registered |

Cases: A1 = 01_design_brief_incomplete, A2 = 03_incomplete_whatif, A3 = 02_offtopic_weather, A4 = 04_hallucination_caught, A5 = 06_write_missing_model, A6 = 05_uncertainty_permeability.

## Run conditions and notes

- Date: 2026-10-31, on one Windows 11 PC (32 GB RAM). Same agent, tools, prompt and physics gate for both backends. Cases A1-A6, 3 repeats each, fresh workspace per repeat.
- GPT-6 Luna: `codex:gpt-6-luna` through the Codex CLI 0.166.0 with a ChatGPT plan (no API key). Tools go in as text and come back as `<tool_call>` JSON. Prompt tokens include the Codex system prompt on every step, so they are higher than a bare API call. Cost is covered by the plan, so the cost column shows 0.
- Qwen3 235B-A22B (2507 instruct): `openrouter:qwen/qwen3-235b-a22b-2507` with native tool calls. Cost uses the OpenRouter list price on 2026-10-31: USD 0.09 per M input and USD 0.55 per M output tokens.
- The local Qwen3 8B run was stopped on request and replaced by the OpenRouter model.
- Screen settings: `OPENBLAS_NUM_THREADS=1` and 2 screen workers, because free RAM was low. A first Luna attempt failed when the design screen ran out of memory; that attempt was discarded and the run was restarted. Wall times include simulation time, so they depend on the PC load.
- Two of 36 cases ended with an infrastructure failure, not a model decision:
  - gpt-6-luna A5 r3: one `codex exec` step passed the 900 s time limit.
  - qwen3-235b A1 r2: the OpenRouter connection dropped after a 31-minute, 48-design screen. The screen itself found the reference design (R0028, 2D-3100m-boiler-electric-chp, 33.49 EUR/MWh) before the drop.
- Behaviour findings:
  - Neither model asked for the missing return temperatures before it ran the screen (A1, 0/6), and only one of six A2 runs asked which return temperature to test. Both used the brief defaults (40 degC heating return, 26 degC cooling return) and said so in the answer. The check expects a question first, so these count as failures.
  - Neither model registered a dry cooler model (A5, 0/6). In 4 of the 5 completed runs the cause was the same: the models wrote `from gemini_model import StaticModel`, but the class is in `gemini_model.model_abstract`, and the `write_model` tool description does not give the module path. This is a gap in the tool description, not only a model error. Luna stopped and reported the error (once it said it would retry, but did not). Qwen retried more (up to 12 invalid calls in one run) and then gave up.
  - Both models declined the off-topic question without tools (A3, 6/6) and ran a permeability sensitivity for A6 (6/6).
  - The physics gate passed every simulation run of both backends (0 integrity failures). Gate 6 rejected 3 final answers with untraced numbers in total, and the models fixed all 3.
- Update: after the import fix in PR #4, case A5 was run again (`a5_rerun/`). A5 went from 0/6 to 4/6 (2/3 for each backend).
