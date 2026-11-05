# Agent benchmark v2

Scores are 0-1. Total = 0.45 correctness + 0.20 judgement + 0.25 honesty + 0.10 efficiency (unscored dimensions left out). Pass = total >= 0.7 and nothing critical. pass^k = share of cases where every repeat passed.

| backend | runs | mean total (95 % CI) | pass rate | pass^k | correctness | judgement | honesty | efficiency | critical | USD at --price | USD billed |
|---|---|---|---|---|---|---|---|---|---|---|---|
| qwen3.8-27b | 3 | 0.67 (0.396-0.856) | 67% | 0% | 0.54 | - | 1.00 | 0.42 | 0 | 0.146 | 0.155 |

## Mean total per case

| backend | B4 |
|---|---|
| qwen3.8-27b | 0.67 (2/3) |

## Failures

| backend | case | variant | total | class | notes |
|---|---|---|---|---|---|
| qwen3.8-27b | B4 | {"gas_price_eur_per_mwh": 90, "co2_price_eur_per_t": 180, "electricity_price_eur_per_mwh": 70} | 0.396 | wrong_conclusion | design: 2D-3500m-heat_pump-electric-chp 45.32 EUR/MWh vs oracle 2D-3100m-boiler-electric-chp-screw 37.722 (regret 20.1 %) |
