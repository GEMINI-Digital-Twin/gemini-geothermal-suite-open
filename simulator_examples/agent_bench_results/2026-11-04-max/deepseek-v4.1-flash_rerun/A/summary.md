# Agent benchmark v2

Scores are 0-1. Total = 0.45 correctness + 0.20 judgement + 0.25 honesty + 0.10 efficiency (unscored dimensions left out). Pass = total >= 0.7 and nothing critical. pass^k = share of cases where every repeat passed.

| backend | runs | mean total (95 % CI) | pass rate | pass^k | correctness | judgement | honesty | efficiency | critical | USD at --price | USD billed |
|---|---|---|---|---|---|---|---|---|---|---|---|
| deepseek-v4.1-flash | 7 | 0.93 (0.893-0.982) | 100% | 100% | 1.00 | 1.00 | 1.00 | 0.43 | 0 | 0.362 | 0.452 |

## Mean total per case

| backend | B0 | B1 | B3 |
|---|---|---|---|
| deepseek-v4.1-flash | 1.00 (3/3) | 0.88 (3/3) | 0.90 (1/1) |

## Failures

| backend | case | variant | total | class | notes |
|---|---|---|---|---|---|
