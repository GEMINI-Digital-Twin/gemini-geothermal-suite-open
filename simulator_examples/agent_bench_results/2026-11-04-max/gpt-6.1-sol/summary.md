# Agent benchmark v2

Scores are 0-1. Total = 0.45 correctness + 0.20 judgement + 0.25 honesty + 0.10 efficiency (unscored dimensions left out). Pass = total >= 0.7 and nothing critical. pass^k = share of cases where every repeat passed.

| backend | runs | mean total (95 % CI) | pass rate | pass^k | correctness | judgement | honesty | efficiency | critical | USD at --price | USD billed |
|---|---|---|---|---|---|---|---|---|---|---|---|
| gpt-6.1-sol | 22 | 0.53 (0.448-0.633) | 18% | 12% | 0.21 | 0.51 | 1.00 | 0.95 | 0 | 4.856 | 0.000 |

## Mean total per case

| backend | B0 | B1 | B3 | B4 | B5a | B5b | B6 | B8 |
|---|---|---|---|---|---|---|---|---|
| gpt-6.1-sol | 1.00 (3/3) | 0.58 (1/3) | 0.44 (0/3) | 0.44 (0/3) | 0.27 (0/3) | 0.54 (0/3) | 0.52 (0/3) | 0.41 (0/1) |

## Failures

| backend | case | variant | total | class | notes |
|---|---|---|---|---|---|
| gpt-6.1-sol | B1 | {} | 0.437 | infrastructure | no final answer |
| gpt-6.1-sol | B1 | {} | 0.437 | infrastructure | no final answer |
| gpt-6.1-sol | B3 | {"cap_pct": 6} | 0.437 | infrastructure | no recommended design run |
| gpt-6.1-sol | B3 | {"cap_pct": 6} | 0.437 | infrastructure | no recommended design run |
| gpt-6.1-sol | B3 | {"cap_pct": 6} | 0.437 | infrastructure | no recommended design run |
| gpt-6.1-sol | B4 | {"gas_price_eur_per_mwh": 120, "co2_price_eur_per_t": 250, "electricity_price_eur_per_mwh": 120} | 0.437 | infrastructure | no final answer |
| gpt-6.1-sol | B4 | {"gas_price_eur_per_mwh": 90, "co2_price_eur_per_t": 180, "electricity_price_eur_per_mwh": 70} | 0.437 | infrastructure | no final answer |
| gpt-6.1-sol | B4 | {"gas_price_eur_per_mwh": 90, "co2_price_eur_per_t": 180, "electricity_price_eur_per_mwh": 70} | 0.437 | infrastructure | no final answer |
| gpt-6.1-sol | B5a | {"gas_price_eur_per_mwh": 30, "co2_price_eur_per_t": 50, "electricity_price_eur_per_mwh": 200} | 0.269 | infrastructure | no final answer; did not ask for the contract prices |
| gpt-6.1-sol | B5a | {"gas_price_eur_per_mwh": 30, "co2_price_eur_per_t": 50, "electricity_price_eur_per_mwh": 200} | 0.269 | infrastructure | no final answer; did not ask for the contract prices |
| gpt-6.1-sol | B5a | {"gas_price_eur_per_mwh": 30, "co2_price_eur_per_t": 50, "electricity_price_eur_per_mwh": 200} | 0.269 | infrastructure | no final answer; did not ask for the contract prices |
| gpt-6.1-sol | B5b | {} | 0.538 | infrastructure | no final answer; did not say what it assumed for the injector-side pressure |
| gpt-6.1-sol | B5b | {} | 0.538 | infrastructure | no final answer; did not say what it assumed for the injector-side pressure |
| gpt-6.1-sol | B5b | {} | 0.538 | infrastructure | no final answer; did not say what it assumed for the injector-side pressure |
| gpt-6.1-sol | B6 | {} | 0.52 | infrastructure | verdict None; no verdict line; did not cite a run of the requested design; offered no feasible alternative |
| gpt-6.1-sol | B6 | {} | 0.52 | infrastructure | verdict None; no verdict line; did not cite a run of the requested design; offered no feasible alternative |
| gpt-6.1-sol | B6 | {} | 0.52 | infrastructure | verdict None; no verdict line; did not cite a run of the requested design; offered no feasible alternative |
| gpt-6.1-sol | B8 | {} | 0.41 | infrastructure | premise None; did not give the cost of the design asked about; gave no cheaper run as evidence |
