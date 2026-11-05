Author: Sa'eed Telvari

# Agent benchmark v2: max-thinking run (4 Nov 2026)

## Setup

- **Code:** e0007ae on development (neutral prompt #27, design options #28, max-reasoning agent #29, new defaults #30). Merge and fill-in tools: PR #32. `src/` did not change during the run.
- **Oracle:** hash 8995b04caaf9, a 300-design grid per price world, cached in `simulator_examples/agent_bench_oracle/`.
  - Base best: 2D-3100m boiler + screw chiller + CHP, 35.158 EUR/MWh, on the official demand profiles. The KNMI headline is not used here.
- **Limits:** no `max_tokens` cap. 200 steps per question and 10 gate retries act as loop guards only.
- **Repeats:** 11 cases × 3 repeats per model. Variants are seeded on the repeat number, so every model sees the same worlds.
  - Caveat (found by an external review, 4 Nov): the old `pick_variant` let repeats share a world. B3 used cap 6 % in all 3 repeats; B4 used 120/250/120 once and 90/180/70 twice, never 30/50/200; B10 and B13 were fine. The models still compare fairly. New runs cover every world (`variants[(repeat + seed) % n]`); `--legacy-variants` keeps the old mapping for fill-ins of this run.
- **Scores reported several ways:** `honest_scores.md` (made by `simulator_examples/benchmark_honest_scores.py`) gives each model as graded, with lost runs counted as failures, and against the pooled best, plus a chance floor (a silent agent scores 0.47) and the 1 Nov raw against rescored scores.
- **Hardware:** Sa'eed's PC with 16 cores, using 2–3 screen workers per process.

| label | model id | effort | price per M (in / out / cached) |
|---|---|---|---|
| gpt-6.1-sol | codex:gpt-6.1-sol | max | 2.00 / 10.00 / 0.10 (API-equivalent) |
| gpt-6.1-terra | codex:gpt-6.1-terra | max | 1.00 / 5.00 / 0.10 (API-equivalent) |
| gpt-6-luna | codex:gpt-6-luna | max | 0.10 / 0.50 / 0.01 (API-equivalent) |
| deepseek-v4.1-flash | openrouter:deepseek/deepseek-v4.1-flash-1017 | max | 0.15 / 0.60 / 0.003 |
| glm-5.3 | openrouter:z-ai/glm-5.3 | max | 0.08 / 3.60 / 0.076 |
| qwen3.8-27b | openrouter:qwen/qwen3.8-27b | xhigh (its highest) | 0.15 / 1.875 / 0.0375 |

- OpenRouter costs are the billed `usage.cost`. ChatGPT-plan models (Sol, Terra, Luna) show the API-equivalent at OpenAI list prices.
- Qwen3 235B thinking was dropped on 4 Nov, at Sa'eed's call.

## What happened during the run

- **Terra overnight:** a Windows scheduled task started Sol's last row and Terra's 10 missing cases at the 01:55 UK reset (5 Nov). It ended at 05:05, when the limit hit for the 5th time. A second task at 08:47 UK retried Terra's 4 design cases: B5b finished, and B1, B3 and B4 hit the limit a 6th time. Terra stops at 8 of 11.
- **The run was split and restarted.** Each backend ran as 2–3 parallel processes using `--cases`, and gaps were filled with `--first-repeat`. `merge_agent_bench.py` keeps the first valid row per (backend, case, repeat). Runs lost to stops are left out of the scores and listed in `missing.md`.
- **OpenRouter credit ran out twice** (402 `in_flight_budget_exhausted`). With no output cap, OpenRouter reserves credit for each request's maximum output:
  - about $3.40 per request for GLM
  - about $0.44 for Qwen 3.8
  - about $0.24 for DeepSeek

  That is far more than the real spend. GLM stopped at 26 of 33 runs, at Sa'eed's call: B3 ×3, B4 r1 and B5a ×3 are missing.
- **The ChatGPT plan usage limit hit 4 times**, at 03:44, ~09:00, 12:42 and 17:2x local. Each reset took about 5 h. Sol's heavy design cases take 40–110 min each at max effort, mostly in simulation (screens and cross-checks).
- **One OpenRouter connection drop** hit DeepSeek B5a r3, which was rerun.

## Final results (`merged/`)

Grid-scored (`summary.md`). `merged_pre_terra/` keeps the earlier snapshot.

| model | runs | mean (95 % CI) | pass | USD per run | LLM calls / run | tools / run | reasoning tokens / run |
|---|---|---|---|---|---|---|---|
| GPT-6.1 Sol | 33 | 0.95 (0.94–0.97) | 100 % | 0.83 (API-eq.) | 9.4 | 34.5 | 15k |
| GPT-6.1 Terra † | 8 | 0.96 (0.93–0.99) | 100 % | 0.33 (API-eq.) | 8.0 | 35.6 | 15k |
| GLM 5.3 ‡ | 26 | 0.89 (0.84–0.93) | 85 % | 0.072 | 9.2 | 15.0 | 16k |
| DeepSeek V4.1 Flash | 33 | 0.86 (0.80–0.92) | 88 % | 0.043 | 34.2 | 52.4 | 21k |
| Qwen 3.8 27B | 33 | 0.81 (0.73–0.89) | 79 % | 0.079 | 17.4 | 22.3 | 16k |
| GPT-6 Luna | 33 | 0.76 (0.68–0.84) | 64 % | 0.010 (API-eq.) | 4.4 | 3.8 | 3k |

- † **Terra is partial and not comparable.** It ran 1 repeat only, because at max effort its design cases take 2–3 h each and kept running into the 5-hour ChatGPT window. 8 of 11 cases finished: B0, B5a, B5b and the five short cases B6–B13. B1, B3 and B4 were cut off by the limit on every try (three overnight and morning attempts, about 2 h and USD 0.9–2.1 API-equivalent each before the cut-off). Its mean and cost per run therefore come mostly from easy cases. Its two design cases: B5a 0.93 at 30.83 EUR/MWh, next to Sol's pooled best of 30.82, and B5b 0.92 at 32.32 EUR/MWh, a new pooled best.
- ‡ GLM is missing B3 ×3, B4 r1 and B5a ×3, all hard cases, so its mean is flattering. `honest_scores.md` counts lost runs as fails.
- 1 Nov run (high effort for Sol and Luna; OpenRouter default with a 1,200-token cap; rescored): Sol 0.96, DeepSeek 0.82, GLM 0.79, Luna 0.66.
- Max thinking with no caps helped Luna (+0.10), GLM (+0.09) and DeepSeek (+0.04). Sol was already at its ceiling (0.96 → 0.95).
- No model gave a critical answer: no rule-breaking design and no injected number reached the user.
- Luna still fails B3 (cost-capped CO2 pick) and B4 (stated prices). It does the least work, at 3.8 tool calls per run.
- Pooled means (`summary_pooled.md`): Sol 0.93, Terra 0.96 (8 runs), GLM 0.80, DeepSeek 0.77, Qwen 3.8 0.75, Luna 0.71.

## The agents beat the oracle grid

In every design world, the cheapest feasible design an agent found is 4–10 % below the 300-design grid optimum. The agents vary options the grid does not search: return temperatures, ORC, ESP size, boiler size and units (`pooled_best.md`; Sol found four pooled bests and Terra the B5b one (2D-3100 screw + CHP + ORC 0.4 + ESP 250 + returns 45/28, 32.32)).

- B1, base world: grid 35.158, against Sol's 2D-3010 screw + CHP + ORC 0.35 + ESP 220 + returns 45/29 at 31.78.
- **Where the saving comes from:** mostly the backup boiler. Sol's B1 picks set `boiler_capacity_mw` to 0.5–0.8 MW instead of the default 33 MW.
  - That meets every day of the nominal year, which is exactly what B1 asks.
  - It keeps no reserve for doublet trips or the peak-day stress cases, which is why the report's pick keeps 33 MW.
  - Return temperatures and ORC add a smaller part. On KNMI 2025 with the full pick basis, a 30 °C cooling return is worth about 0.45 EUR/MWh (thread "Rerun all analysis on new defaults", `run_pick_levers.py`).
- **The grid score is clamped,** so it can't reward a design below the grid optimum: regret is clamped at 0. `summary_pooled.md` rescores the design cases against the pooled best (the cheapest feasible design any run found). That view is strict: the grid optimum itself is more than 10 % above the pooled best in B1, so it scores 0 on correctness. Pooled means are listed above.

## Checker notes

- **GLM B10 r3 (0.65):** the final answer was correct (36.75 EUR/MWh [R0001], no 25), but earlier drafts that quoted "25 EUR/MWh" were rejected by gate 6 and counted as "tried to report". This is a likely partial false positive, not rescored.

- **`honest_scores.md`** is rerun on `merged/` with the functions of `benchmark_honest_scores.py`. The silent-agent and random-design floors are carried over from its pre-Terra run, because they do not depend on any model row. A full rerun has to rebuild the oracle grids after the cache-key change in development.

## Figure

`docs/figures/fig_agent_benchmark.png`, made by `simulator_examples/plot_agent_bench.py`. It shows the score per model with its CI, the pooled-best score, and the 1 Nov tick, plus score against cost. Hatched bars and starred labels are partial models (runs lost to credit or quota stops).
