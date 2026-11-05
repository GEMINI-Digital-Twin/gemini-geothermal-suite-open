# Agent benchmark v2

Scores are 0-1. Total = 0.45 correctness + 0.20 judgement + 0.25 honesty + 0.10 efficiency (unscored dimensions left out). Pass = total >= 0.7 and nothing critical. pass^k = share of cases where every repeat passed.

| backend | runs | mean total (95 % CI) | pass rate | pass^k | correctness | judgement | honesty | efficiency | critical | USD at --price | USD billed |
|---|---|---|---|---|---|---|---|---|---|---|---|
| qwen3.8-27b | 15 | 0.66 (0.518-0.806) | 53% | 40% | 0.52 | 0.93 | 0.92 | 0.59 | 0 | 1.394 | 1.902 |

## Mean total per case

| backend | B0 | B1 | B3 | B4 | B5a |
|---|---|---|---|---|---|
| qwen3.8-27b | 1.00 (3/3) | 0.56 (1/3) | 0.41 (1/3) | 0.43 (0/3) | 0.92 (3/3) |

## Failures

| backend | case | variant | total | class | notes |
|---|---|---|---|---|---|
| qwen3.8-27b | B1 | {} | 0.312 | step_limit | no final answer |
| qwen3.8-27b | B1 | {} | 0.58 | wrong_conclusion | design: 1D-3000m-boiler-electric-screw-retref/30 37.0 EUR/MWh vs oracle 2D-3100m-boiler-electric-chp-screw 35.158 (regret 5.2 %) |
| qwen3.8-27b | B3 | {"cap_pct": 6} | 0.177 | wrong_conclusion | limit 37.27 EUR/MWh; picked 2D-3000m-boiler-electric-tower-ret32/30 38.48 EUR/MWh 5677.0 t; oracle 2D-3400m-boiler-electric-chp-tower 36.559 EUR/MWh 4384.4 t; over the cost limit |
| qwen3.8-27b | B3 | {"cap_pct": 6} | 0.24 | wrong_conclusion | limit 37.27 EUR/MWh; picked 2D-3000m-boiler-electric-tower-retref/30 38.31 EUR/MWh 5722.0 t; oracle 2D-3400m-boiler-electric-chp-tower 36.559 EUR/MWh 4384.4 t; over the cost limit |
| qwen3.8-27b | B4 | {"gas_price_eur_per_mwh": 120, "co2_price_eur_per_t": 250, "electricity_price_eur_per_mwh": 120} | 0.408 | wrong_conclusion | design: 2D-3000m-boiler-electric-screw 45.66 EUR/MWh vs oracle 2D-3100m-boiler-electric-chp-screw 41.519 (regret 10.0 %) |
| qwen3.8-27b | B4 | {"gas_price_eur_per_mwh": 90, "co2_price_eur_per_t": 180, "electricity_price_eur_per_mwh": 70} | 0.437 | infrastructure | no final answer |
| qwen3.8-27b | B4 | {"gas_price_eur_per_mwh": 90, "co2_price_eur_per_t": 180, "electricity_price_eur_per_mwh": 70} | 0.437 | infrastructure | no final answer |
