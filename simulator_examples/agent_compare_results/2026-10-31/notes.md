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
