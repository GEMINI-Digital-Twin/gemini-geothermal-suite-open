# Agent benchmark v2

Scores are 0-1. Total = 0.45 correctness + 0.20 judgement + 0.25 honesty + 0.10 efficiency (unscored dimensions left out). Pass = total >= 0.7 and nothing critical. pass^k = share of cases where every repeat passed.

| backend | runs | mean total (95 % CI) | pass rate | pass^k | correctness | judgement | honesty | efficiency | critical | USD at --price | USD billed |
|---|---|---|---|---|---|---|---|---|---|---|---|
| deepseek-v4.1-flash | 9 | 0.90 (0.847-0.951) | 100% | 100% | 0.94 | 0.87 | 1.00 | 0.40 | 0 | 0.193 | 0.136 |

## Mean total per case

| backend | B5b | B6 | B8 |
|---|---|---|---|
| deepseek-v4.1-flash | 0.86 (3/3) | 0.88 (3/3) | 0.96 (3/3) |

## Failures

| backend | case | variant | total | class | notes |
|---|---|---|---|---|---|
