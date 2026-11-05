# Agent benchmark v2

Scores are 0-1. Total = 0.45 correctness + 0.20 judgement + 0.25 honesty + 0.10 efficiency (unscored dimensions left out). Pass = total >= 0.7 and nothing critical. pass^k = share of cases where every repeat passed.

| backend | runs | mean total (95 % CI) | pass rate | pass^k | correctness | judgement | honesty | efficiency | critical | USD at --price | USD billed |
|---|---|---|---|---|---|---|---|---|---|---|---|
| gpt-6.1-sol | 6 | 0.44 (0.437-0.437) | 0% | 0% | 0.00 | - | 1.00 | 1.00 | 0 | 1.270 | 0.000 |

## Mean total per case

| backend | B1 | B3 |
|---|---|---|
| gpt-6.1-sol | 0.44 (0/3) | 0.44 (0/3) |

## Failures

| backend | case | variant | total | class | notes |
|---|---|---|---|---|---|
| gpt-6.1-sol | B1 | {} | 0.437 | infrastructure | no final answer |
| gpt-6.1-sol | B1 | {} | 0.437 | infrastructure | no final answer |
| gpt-6.1-sol | B1 | {} | 0.437 | infrastructure | no final answer |
| gpt-6.1-sol | B3 | {"cap_pct": 6} | 0.437 | infrastructure | no recommended design run |
| gpt-6.1-sol | B3 | {"cap_pct": 6} | 0.437 | infrastructure | no recommended design run |
| gpt-6.1-sol | B3 | {"cap_pct": 6} | 0.437 | infrastructure | no recommended design run |
