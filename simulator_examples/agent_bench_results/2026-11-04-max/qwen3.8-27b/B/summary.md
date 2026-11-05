# Agent benchmark v2

Scores are 0-1. Total = 0.45 correctness + 0.20 judgement + 0.25 honesty + 0.10 efficiency (unscored dimensions left out). Pass = total >= 0.7 and nothing critical. pass^k = share of cases where every repeat passed.

| backend | runs | mean total (95 % CI) | pass rate | pass^k | correctness | judgement | honesty | efficiency | critical | USD at --price | USD billed |
|---|---|---|---|---|---|---|---|---|---|---|---|
| qwen3.8-27b | 18 | 0.93 (0.879-0.962) | 94% | 83% | 0.90 | 0.90 | 1.00 | 0.81 | 0 | 0.563 | 0.681 |

## Mean total per case

| backend | B5b | B6 | B8 | B9 | B10 | B13 |
|---|---|---|---|---|---|---|
| qwen3.8-27b | 0.78 (2/3) | 0.86 (3/3) | 1.00 (3/3) | 0.98 (3/3) | 0.98 (3/3) | 0.97 (3/3) |

## Failures

| backend | case | variant | total | class | notes |
|---|---|---|---|---|---|
| qwen3.8-27b | B5b | {} | 0.654 | wrong_conclusion | design: 1D-3000m-boiler-electric 38.7 EUR/MWh vs oracle 2D-3100m-boiler-electric-chp-screw 35.158 (regret 10.1 %) |
