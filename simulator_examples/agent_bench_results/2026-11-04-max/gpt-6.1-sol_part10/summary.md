# Agent benchmark v2

Scores are 0-1. Total = 0.45 correctness + 0.20 judgement + 0.25 honesty + 0.10 efficiency (unscored dimensions left out). Pass = total >= 0.7 and nothing critical. pass^k = share of cases where every repeat passed.

| backend | runs | mean total (95 % CI) | pass rate | pass^k | correctness | judgement | honesty | efficiency | critical | USD at --price | USD billed |
|---|---|---|---|---|---|---|---|---|---|---|---|
| gpt-6.1-sol | 2 | 0.66 (0.437-0.875) | 50% | 0% | 0.50 | - | 1.00 | 0.50 | 0 | 3.239 | 0.000 |

## Mean total per case

| backend | B1 |
|---|---|
| gpt-6.1-sol | 0.66 (1/2) |

## Failures

| backend | case | variant | total | class | notes |
|---|---|---|---|---|---|
| gpt-6.1-sol | B1 | {} | 0.437 | infrastructure | no final answer |
