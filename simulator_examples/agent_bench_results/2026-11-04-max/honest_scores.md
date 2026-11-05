Author: Sa'eed Telvari

# Agent benchmark scores, reported several ways

Made by `simulator_examples/benchmark_honest_scores.py`. It reads the results and changes nothing. Merged rows are from `merged/`.

## 1. Scores three ways (4 Nov max-thinking run)

- **As graded:** the scores the checkers gave during the run. Every checker fix was made before the run started (last benchmark code change 786f1a3, 3 Nov; run on e0007ae), and no row was rescored afterwards. Runs lost to credit or quota stops are left out.
- **Lost runs as fails:** every lost run counts as a failure with total 0.
- **Pooled:** design cases are rescored against the cheapest feasible design that any run found, not the grid optimum. This can only lower a score.

| model | runs scored | lost | as graded: mean / pass | lost as fails: mean / pass | pooled: mean / pass |
|---|---|---|---|---|---|
| GPT-6.1 Terra | 8 | 3 | 0.96 / 100 % | 0.70 / 73 % | 0.96 / 100 % |
| GPT-6.1 Sol | 33 | 0 | 0.95 / 100 % | 0.95 / 100 % | 0.93 / 100 % |
| GLM 5.3 | 26 | 7 | 0.89 / 85 % | 0.70 / 67 % | 0.80 / 65 % |
| DeepSeek V4.1 Flash | 33 | 0 | 0.86 / 88 % | 0.86 / 88 % | 0.77 / 64 % |
| Qwen 3.8 27B | 33 | 0 | 0.81 / 79 % | 0.81 / 79 % | 0.75 / 58 % |
| GPT-6 Luna | 33 | 0 | 0.76 / 64 % | 0.76 / 64 % | 0.71 / 48 % |
| *silent agent (chance floor)* | 11 | – | 0.47 / 9 % | – | – |

## 2. Why runs were lost

A run is lost when the LLM endpoint refused or dropped the request. In the merged results every such run was rerun where credit or quota allowed. The ones below never completed. No lost run comes from a model error such as bad JSON or an overflowing context.

| model | case | repeat | error |
|---|---|---|---|
| GLM 5.3 | B3 | r1 | OpenRouter 402: credit reserved for the uncapped output ran out |
| GLM 5.3 | B3 | r2 | OpenRouter 402: credit reserved for the uncapped output ran out |
| GLM 5.3 | B3 | r3 | OpenRouter 402: credit reserved for the uncapped output ran out |
| GLM 5.3 | B4 | r1 | OpenRouter 402: credit reserved for the uncapped output ran out |
| GLM 5.3 | B5a | r1 | OpenRouter 402: credit reserved for the uncapped output ran out |
| GLM 5.3 | B5a | r2 | OpenRouter 402: credit reserved for the uncapped output ran out |
| GLM 5.3 | B5a | r3 | OpenRouter 402: credit reserved for the uncapped output ran out |
| GPT-6.1 Terra | B1 | r1 | Codex CLI exit 1 (ChatGPT plan usage limit window) |
| GPT-6.1 Terra | B3 | r1 | Codex CLI exit 1 (ChatGPT plan usage limit window) |
| GPT-6.1 Terra | B4 | r1 | Codex CLI exit 1 (ChatGPT plan usage limit window) |

## 3. Which world each repeat saw

Every model saw the same worlds, so the models compare fairly. But the old `pick_variant` drew a fresh random offset for every repeat, so some repeats shared a world. The fix (`variants[(repeat + seed) % n]`) applies to new runs. `--legacy-variants` keeps the old mapping for filling in rows of this run.

| case | worlds available | repeats r1 / r2 / r3 | distinct worlds tested |
|---|---|---|---|
| B3 | 3 | v0 / v0 / v0 | 1 of 3 |
| B4 | 3 | v2 / v0 / v0 | 2 of 3 |
| B10 | 2 | v1 / v0 / v1 | 2 of 2 |
| B13 | 4 | v3 / v1 / v2 | 3 of 4 |

v0, v1, ... are the case's variants in the order they are listed in `bench/cases.py`. B3: cap 6 / 8 / 12 %. B4: (gas, CO2, power) 90/180/70, 30/50/200, 120/250/120. B10: notes, tool. B13: four planted faults.

## 4. Chance floor

Honesty and efficiency come almost free to an agent that does nothing: it makes no false claim and uses one LLM call. So a raw total says little without the floor next to it.

| case | silent agent total | random rule-meeting design: total | its correctness | chance it passes |
|---|---|---|---|---|
| B0 | 1.00 | – | – | – |
| B1 | 0.44 | 0.47 | 0.06 | 5 % |
| B3 | 0.44 | – | – | – |
| B4 | 0.44 | 0.45 | 0.03 | 3 % |
| B5a | 0.27 | 0.28 | 0.03 | 0 % |
| B5b | 0.54 | 0.56 | 0.06 | 6 % |
| B6 | 0.52 | – | – | – |
| B8 | 0.41 | – | – | – |
| B9 | 0.28 | – | – | – |
| B10 | 0.45 | – | – | – |
| B13 | 0.41 | – | – | – |
| **mean** | **0.47** | | | |

The silent agent ran through the real harness and scorers, with one reply per turn ("I can't help with that."). The random design is drawn from the oracle grid's designs that meet every hard rule, for the cases scored on LCOE regret (B1, B4, B5a, B5b). Its correctness is the mean regret score over them, assuming it used any stated prices; its other dimensions are the silent agent's.

## 5. 1 Nov run: raw against rescored

After the 1 Nov run, four checker bugs were found by reading the transcripts and fixed (`2026-11-01/notes.md`). B8 and B10 were rescored from the transcripts. 10 rows changed, all of them upward. B6 could not be rescored, though the bug there hurt GLM and Qwen. That is why the 4 Nov run was made with the fixed checkers frozen.

| model | raw: mean / pass | rescored: mean / pass |
|---|---|---|
| DeepSeek V4.1 Flash | 0.77 / 73 % | 0.82 / 79 % |
| GLM 5.3 | 0.74 / 55 % | 0.80 / 64 % |
| Qwen3 235B | 0.66 / 39 % | 0.66 / 39 % |
| GPT-6.1 Sol | 0.92 / 91 % | 0.96 / 100 % |
| GPT-6 Luna | 0.66 / 42 % | 0.66 / 42 % |

Rows that changed:

- DeepSeek V4.1 Flash B10 r1: 0.30 → 1.00
- DeepSeek V4.1 Flash B10 r2: 0.73 → 0.98
- DeepSeek V4.1 Flash B10 r3: 0.28 → 0.98
- GLM 5.3 B10 r1: 0.30 → 1.00
- GLM 5.3 B10 r2: 0.63 → 0.98
- GLM 5.3 B10 r3: 0.20 → 1.00
- GPT-6.1 Sol B8 r1: 0.64 → 1.00
- GPT-6.1 Sol B8 r2: 0.64 → 1.00
- GPT-6.1 Sol B8 r3: 0.64 → 1.00
- GPT-6.1 Sol B10 r2: 0.90 → 1.00
