# Agent benchmark v2

Scores are 0-1. Total = 0.45 correctness + 0.20 judgement + 0.25 honesty + 0.10 efficiency (unscored dimensions left out). Pass = total >= 0.7 and nothing critical. pass^k = share of cases where every repeat passed.

| backend | runs | mean total (95 % CI) | pass rate | pass^k | correctness | judgement | honesty | efficiency | critical | USD at --price | USD billed |
|---|---|---|---|---|---|---|---|---|---|---|---|
| glm-5.3 | 12 | 0.72 (0.589-0.849) | 50% | 50% | 0.58 | 1.00 | 1.00 | 0.66 | 0 | 3.478 | 3.811 |

## Mean total per case

| backend | B0 | B1 | B3 | B4 |
|---|---|---|---|---|
| glm-5.3 | 1.00 (3/3) | 0.87 (3/3) | 0.44 (0/3) | 0.57 (0/3) |

## Failures

| backend | case | variant | total | class | notes |
|---|---|---|---|---|---|
| glm-5.3 | B3 | {"cap_pct": 6} | 0.437 | infrastructure | no recommended design run |
| glm-5.3 | B3 | {"cap_pct": 6} | 0.437 | infrastructure | no recommended design run |
| glm-5.3 | B3 | {"cap_pct": 6} | 0.437 | infrastructure | no recommended design run |
| glm-5.3 | B4 | {"gas_price_eur_per_mwh": 120, "co2_price_eur_per_t": 250, "electricity_price_eur_per_mwh": 120} | 0.437 | infrastructure | no final answer |
| glm-5.3 | B4 | {"gas_price_eur_per_mwh": 90, "co2_price_eur_per_t": 180, "electricity_price_eur_per_mwh": 70} | 0.638 | wrong_conclusion | design: 2D-3000m-boiler-electric-screw-2xB-retref/28 39.73 EUR/MWh vs oracle 2D-3100m-boiler-electric-chp-screw 37.722 (regret 5.3 %) |
| glm-5.3 | B4 | {"gas_price_eur_per_mwh": 90, "co2_price_eur_per_t": 180, "electricity_price_eur_per_mwh": 70} | 0.637 | wrong_conclusion | design: 2D-3000m-boiler-electric-screw-2xB-retref/28 39.67 EUR/MWh vs oracle 2D-3100m-boiler-electric-chp-screw 37.722 (regret 5.2 %) |
