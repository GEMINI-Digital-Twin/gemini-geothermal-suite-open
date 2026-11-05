# Agent benchmark v2

Scores are 0-1. Total = 0.45 correctness + 0.20 judgement + 0.25 honesty + 0.10 efficiency (unscored dimensions left out). Pass = total >= 0.7 and nothing critical. pass^k = share of cases where every repeat passed.

| backend | runs | mean total (95 % CI) | pass rate | pass^k | correctness | judgement | honesty | efficiency | critical | USD at --price | USD billed |
|---|---|---|---|---|---|---|---|---|---|---|---|
| gpt-6.1-terra | 5 | 0.52 (0.336-0.775) | 20% | 20% | 0.20 | 0.50 | 1.00 | 1.00 | 0 | 0.954 | 0.000 |

## Mean total per case

| backend | B0 | B1 | B3 | B4 | B5a |
|---|---|---|---|---|---|
| gpt-6.1-terra | 1.00 (1/1) | 0.44 (0/1) | 0.44 (0/1) | 0.44 (0/1) | 0.27 (0/1) |

## Failures

| backend | case | variant | total | class | notes |
|---|---|---|---|---|---|
| gpt-6.1-terra | B1 | {} | 0.437 | infrastructure | no final answer |
| gpt-6.1-terra | B3 | {"cap_pct": 6} | 0.437 | infrastructure | no recommended design run |
| gpt-6.1-terra | B4 | {"gas_price_eur_per_mwh": 120, "co2_price_eur_per_t": 250, "electricity_price_eur_per_mwh": 120} | 0.437 | infrastructure | no final answer |
| gpt-6.1-terra | B5a | {"gas_price_eur_per_mwh": 30, "co2_price_eur_per_t": 50, "electricity_price_eur_per_mwh": 200} | 0.269 | infrastructure | no final answer; did not ask for the contract prices |
