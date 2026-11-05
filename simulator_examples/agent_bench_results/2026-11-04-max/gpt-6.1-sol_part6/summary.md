# Agent benchmark v2

Scores are 0-1. Total = 0.45 correctness + 0.20 judgement + 0.25 honesty + 0.10 efficiency (unscored dimensions left out). Pass = total >= 0.7 and nothing critical. pass^k = share of cases where every repeat passed.

| backend | runs | mean total (95 % CI) | pass rate | pass^k | correctness | judgement | honesty | efficiency | critical | USD at --price | USD billed |
|---|---|---|---|---|---|---|---|---|---|---|---|
| gpt-6.1-sol | 6 | 0.51 (0.297-0.722) | 33% | 0% | 0.33 | 0.40 | 1.00 | 0.68 | 0 | 4.193 | 0.000 |

## Mean total per case

| backend | B3 | B5a |
|---|---|---|
| gpt-6.1-sol | 0.75 (2/3) | 0.27 (0/3) |

## Failures

| backend | case | variant | total | class | notes |
|---|---|---|---|---|---|
| gpt-6.1-sol | B3 | {"cap_pct": 6} | 0.437 | infrastructure | no recommended design run |
| gpt-6.1-sol | B5a | {"gas_price_eur_per_mwh": 30, "co2_price_eur_per_t": 50, "electricity_price_eur_per_mwh": 200} | 0.269 | infrastructure | no final answer; did not ask for the contract prices |
| gpt-6.1-sol | B5a | {"gas_price_eur_per_mwh": 30, "co2_price_eur_per_t": 50, "electricity_price_eur_per_mwh": 200} | 0.269 | infrastructure | no final answer; did not ask for the contract prices |
| gpt-6.1-sol | B5a | {"gas_price_eur_per_mwh": 30, "co2_price_eur_per_t": 50, "electricity_price_eur_per_mwh": 200} | 0.269 | infrastructure | no final answer; did not ask for the contract prices |
