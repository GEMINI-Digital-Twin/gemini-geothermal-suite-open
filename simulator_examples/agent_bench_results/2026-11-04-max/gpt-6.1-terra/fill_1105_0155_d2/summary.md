# Agent benchmark v2

Scores are 0-1. Total = 0.45 correctness + 0.20 judgement + 0.25 honesty + 0.10 efficiency (unscored dimensions left out). Pass = total >= 0.7 and nothing critical. pass^k = share of cases where every repeat passed.

| backend | runs | mean total (95 % CI) | pass rate | pass^k | correctness | judgement | honesty | efficiency | critical | USD at --price | USD billed |
|---|---|---|---|---|---|---|---|---|---|---|---|
| gpt-6.1-terra | 2 | 0.73 (0.538-0.929) | 50% | 50% | 0.50 | 0.85 | 1.00 | 0.54 | 0 | 2.978 | 0.000 |

## Mean total per case

| backend | B5a | B5b |
|---|---|---|
| gpt-6.1-terra | 0.93 (1/1) | 0.54 (0/1) |

## Failures

| backend | case | variant | total | class | notes |
|---|---|---|---|---|---|
| gpt-6.1-terra | B5b | {} | 0.538 | infrastructure | no final answer; did not say what it assumed for the injector-side pressure |
