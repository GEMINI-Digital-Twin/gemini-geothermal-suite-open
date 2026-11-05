# Agent benchmark v2

Scores are 0-1. Total = 0.45 correctness + 0.20 judgement + 0.25 honesty + 0.10 efficiency (unscored dimensions left out). Pass = total >= 0.7 and nothing critical. pass^k = share of cases where every repeat passed.

| backend | runs | mean total (95 % CI) | pass rate | pass^k | correctness | judgement | honesty | efficiency | critical | USD at --price | USD billed |
|---|---|---|---|---|---|---|---|---|---|---|---|
| gpt-6.1-sol | 9 | 0.52 (0.377-0.697) | 22% | 0% | 0.22 | 0.35 | 1.00 | 0.86 | 0 | 2.314 | 0.000 |

## Mean total per case

| backend | B4 | B5a | B5b |
|---|---|---|---|
| gpt-6.1-sol | 0.76 (2/3) | 0.27 (0/3) | 0.54 (0/3) |

## Failures

| backend | case | variant | total | class | notes |
|---|---|---|---|---|---|
| gpt-6.1-sol | B4 | {"gas_price_eur_per_mwh": 90, "co2_price_eur_per_t": 180, "electricity_price_eur_per_mwh": 70} | 0.437 | infrastructure | no final answer |
| gpt-6.1-sol | B5a | {"gas_price_eur_per_mwh": 30, "co2_price_eur_per_t": 50, "electricity_price_eur_per_mwh": 200} | 0.269 | infrastructure | no final answer; did not ask for the contract prices |
| gpt-6.1-sol | B5a | {"gas_price_eur_per_mwh": 30, "co2_price_eur_per_t": 50, "electricity_price_eur_per_mwh": 200} | 0.269 | infrastructure | no final answer; did not ask for the contract prices |
| gpt-6.1-sol | B5a | {"gas_price_eur_per_mwh": 30, "co2_price_eur_per_t": 50, "electricity_price_eur_per_mwh": 200} | 0.269 | infrastructure | no final answer; did not ask for the contract prices |
| gpt-6.1-sol | B5b | {} | 0.538 | infrastructure | no final answer; did not say what it assumed for the injector-side pressure |
| gpt-6.1-sol | B5b | {} | 0.538 | infrastructure | no final answer; did not say what it assumed for the injector-side pressure |
| gpt-6.1-sol | B5b | {} | 0.538 | infrastructure | no final answer; did not say what it assumed for the injector-side pressure |
