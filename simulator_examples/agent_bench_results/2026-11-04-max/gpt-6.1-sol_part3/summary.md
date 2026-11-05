# Agent benchmark v2

Scores are 0-1. Total = 0.45 correctness + 0.20 judgement + 0.25 honesty + 0.10 efficiency (unscored dimensions left out). Pass = total >= 0.7 and nothing critical. pass^k = share of cases where every repeat passed.

| backend | runs | mean total (95 % CI) | pass rate | pass^k | correctness | judgement | honesty | efficiency | critical | USD at --price | USD billed |
|---|---|---|---|---|---|---|---|---|---|---|---|
| gpt-6.1-sol | 15 | 0.98 (0.952-1.0) | 100% | 100% | 1.00 | 0.88 | 1.00 | 1.00 | 0 | 2.454 | 0.000 |

## Mean total per case

| backend | B6 | B8 | B9 | B10 | B13 |
|---|---|---|---|---|---|
| gpt-6.1-sol | 0.88 (3/3) | 1.00 (3/3) | 1.00 (3/3) | 1.00 (3/3) | 1.00 (3/3) |

## Failures

| backend | case | variant | total | class | notes |
|---|---|---|---|---|---|
