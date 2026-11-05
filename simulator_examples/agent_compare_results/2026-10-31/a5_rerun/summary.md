# Agent backend comparison

| backend | runs | gated answers | behaviour ok | A1 design match | gate rejections (fixed) | invalid tool calls | prompt tok | completion tok | wall s | cost USD |
|---|---|---|---|---|---|---|---|---|---|---|
| gpt-6-luna | 3 | 3 | 2 | 0/0 | 0 (0) | 0 | 794526 | 18769 | 232 | 0.000 |
| qwen3-235b | 3 | 3 | 2 | 0/0 | 0 (0) | 4 | 148565 | 8335 | 367 | 0.018 |

Per case (mean over repeats):

| backend | case | behaviour ok | prompt tok | completion tok | tool calls | wall s |
|---|---|---|---|---|---|---|
| gpt-6-luna | A5 | 2/3 | 264842 | 6256 | 1.7 | 77 |
| qwen3-235b | A5 | 2/3 | 49522 | 2778 | 6.3 | 122 |

## Physics gate on the agents' simulation runs

Gate passed = integrity verdict (energy balance and sanity). A design that fails a hard rule (for example cooling demand not met) is still a valid run, but it cannot be recommended.

| backend | runs in ledger | gate passed | gate failed | meets all hard rules | solver re-run agrees | steps not passed |
|---|---|---|---|---|---|---|
| gpt-6-luna | 0 | 0 | 0 | 0 | 0 | none |
| qwen3-235b | 11 | 11 | 0 | 10 | 10 | none |

## A1 design found (reference: 2D-3100m-boiler-electric-chp, 33.49 EUR/MWh)

| backend | repeat | final reply | asked first | design | LCOE EUR/MWh | matches reference | tool calls | wall s |
|---|---|---|---|---|---|---|---|---|

## Failed behaviour checks

| backend | case | repeat | failure |
|---|---|---|---|
| gpt-6-luna | A5 | 3 | no model passed its tests and was registered |
| qwen3-235b | A5 | 3 | no model passed its tests and was registered |

Cases: A1 = 01_design_brief_incomplete, A2 = 03_incomplete_whatif, A3 = 02_offtopic_weather, A4 = 04_hallucination_caught, A5 = 06_write_missing_model, A6 = 05_uncertainty_permeability.

## A5 rerun: notes

- Rerun of case A5 (write a missing dry cooler model), 3 repeats per backend, on PR #4 (commit e7cca1d). PR #4 gives the correct import path in the `write_model` tool text (`from gemini_model.model_abstract import StaticModel`) and adds harness acceptance tests (interface, energy balance, second law, limits) that a model must pass before it is registered.
- Same backends and settings as the first run: `codex:gpt-6-luna` and `openrouter:qwen/qwen3-235b-a22b-2507`, `OPENBLAS_NUM_THREADS=1`, 2 screen workers.
- The workspace was an absolute path. With a relative workspace (the runner's default), the harness acceptance check cannot find the model file (`FileNotFoundError`, harness level "import"), because it runs in the `generated_models` folder with a relative file path. A scripted A5 run shows this: it passes with an absolute `--out` and fails with a relative one. A first rerun with relative paths was discarded for this reason. The bug was reported for a fix.
- Result: A5 went from 0/6 to 4/6 (2/3 per backend). Every registered model passed its own tests and the harness acceptance tests.
  - Qwen3 235B failed the acceptance tests on its first attempt in 2 runs (results not stored in `output`, wrong behaviour when the air is warmer than the water), then fixed the model and passed.
  - gpt-6-luna r3: the model replied that `write_model` was not available in the session and did not call it. The tool was in the prompt, so this is a model error in the Codex text tool-call mode.
  - qwen3-235b r3: after 12 tool calls the model answered a design question instead of the model request (it ran designs and recommended R0011), so no model was registered.
