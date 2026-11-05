# Agent benchmark v2

Scores are 0-1. Total = 0.45 correctness + 0.20 judgement + 0.25 honesty + 0.10 efficiency (unscored dimensions left out). Pass = total >= 0.7 and nothing critical. pass^k = share of cases where every repeat passed.

| backend | runs | mean total (95 % CI) | pass rate | pass^k | correctness | judgement | honesty | efficiency | critical | USD at --price | USD billed |
|---|---|---|---|---|---|---|---|---|---|---|---|
| deepseek-v4.1-flash | 18 | 0.84 (0.74-0.919) | 83% | 67% | 0.82 | 1.00 | 0.97 | 0.29 | 0 | 0.884 | 0.967 |

## Mean total per case

| backend | B3 | B4 | B5a | B9 | B10 | B13 |
|---|---|---|---|---|---|---|
| deepseek-v4.1-flash | 0.65 (2/3) | 0.83 (3/3) | 0.72 (1/3) | 0.90 (3/3) | 0.94 (3/3) | 1.00 (3/3) |

## Failures

| backend | case | variant | total | class | notes |
|---|---|---|---|---|---|
| deepseek-v4.1-flash | B3 | {"cap_pct": 6} | 0.156 | wrong_conclusion | limit 37.27 EUR/MWh; picked 2D-3000m-boiler-electric-tower-hrhp0.5-5xB-ret32/30 37.66 EUR/MWh 5075.0 t; oracle 2D-3400m-boiler-electric-chp-tower 36.559 EUR/MWh 4384.4 t; over the cost limit |
| deepseek-v4.1-flash | B5a | {"gas_price_eur_per_mwh": 30, "co2_price_eur_per_t": 50, "electricity_price_eur_per_mwh": 200} | 0.577 | step_limit | no final answer |
| deepseek-v4.1-flash | B5a | {"gas_price_eur_per_mwh": 30, "co2_price_eur_per_t": 50, "electricity_price_eur_per_mwh": 200} | 0.654 | infrastructure | no final answer |
