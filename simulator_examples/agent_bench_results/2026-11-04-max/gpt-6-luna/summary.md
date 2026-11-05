# Agent benchmark v2

Scores are 0-1. Total = 0.45 correctness + 0.20 judgement + 0.25 honesty + 0.10 efficiency (unscored dimensions left out). Pass = total >= 0.7 and nothing critical. pass^k = share of cases where every repeat passed.

| backend | runs | mean total (95 % CI) | pass rate | pass^k | correctness | judgement | honesty | efficiency | critical | USD at --price | USD billed |
|---|---|---|---|---|---|---|---|---|---|---|---|
| gpt-6-luna | 33 | 0.76 (0.678-0.841) | 64% | 36% | 0.59 | 0.83 | 0.95 | 0.97 | 0 | 0.340 | 0.000 |

## Mean total per case

| backend | B0 | B1 | B3 | B4 | B5a | B5b | B6 | B8 | B9 | B10 | B13 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| gpt-6-luna | 1.00 (3/3) | 0.71 (2/3) | 0.28 (0/3) | 0.54 (0/3) | 0.74 (1/3) | 0.71 (2/3) | 0.87 (3/3) | 0.80 (2/3) | 1.00 (3/3) | 0.90 (3/3) | 0.84 (2/3) |

## Failures

| backend | case | variant | total | class | notes |
|---|---|---|---|---|---|
| gpt-6-luna | B1 | {} | 0.437 | wrong_conclusion | answer recommends no design run |
| gpt-6-luna | B3 | {"cap_pct": 6} | 0.281 | wrong_conclusion | limit 37.27 EUR/MWh; picked 2D-3000m-boiler-electric 39.75 EUR/MWh 6431.0 t; oracle 2D-3400m-boiler-electric-chp-tower 36.559 EUR/MWh 4384.4 t; over the cost limit |
| gpt-6-luna | B3 | {"cap_pct": 6} | 0.281 | wrong_conclusion | limit 37.27 EUR/MWh; picked 1D-2500m-heat_pump-electric-chp 42.54 EUR/MWh 11640.0 t; oracle 2D-3400m-boiler-electric-chp-tower 36.559 EUR/MWh 4384.4 t; over the cost limit |
| gpt-6-luna | B3 | {"cap_pct": 6} | 0.281 | wrong_conclusion | limit 37.27 EUR/MWh; picked 1D-2500m-heat_pump-electric-chp 42.54 EUR/MWh 11640.0 t; oracle 2D-3400m-boiler-electric-chp-tower 36.559 EUR/MWh 4384.4 t; over the cost limit |
| gpt-6-luna | B4 | {"gas_price_eur_per_mwh": 120, "co2_price_eur_per_t": 250, "electricity_price_eur_per_mwh": 120} | 0.583 | wrong_conclusion | design: 2D-3500m-boiler-electric-chp 44.6 EUR/MWh vs oracle 2D-3100m-boiler-electric-chp-screw 41.519 (regret 7.4 %) |
| gpt-6-luna | B4 | {"gas_price_eur_per_mwh": 90, "co2_price_eur_per_t": 180, "electricity_price_eur_per_mwh": 70} | 0.437 | wrong_conclusion | design: 2D-2500m-heat_pump-electric-chp 46.01 EUR/MWh vs oracle 2D-3100m-boiler-electric-chp-screw 37.722 (regret 22.0 %) |
| gpt-6-luna | B4 | {"gas_price_eur_per_mwh": 90, "co2_price_eur_per_t": 180, "electricity_price_eur_per_mwh": 70} | 0.607 | wrong_conclusion | design: 2D-3500m-boiler-electric-chp 40.36 EUR/MWh vs oracle 2D-3100m-boiler-electric-chp-screw 37.722 (regret 7.0 %) |
| gpt-6-luna | B5a | {"gas_price_eur_per_mwh": 30, "co2_price_eur_per_t": 50, "electricity_price_eur_per_mwh": 200} | 0.654 | wrong_conclusion | design: 1D-3500m-boiler-electric-chp 36.52 EUR/MWh vs oracle 1D-3100m-boiler-electric-chp-tower 33.015 (regret 10.6 %) |
| gpt-6-luna | B5a | {"gas_price_eur_per_mwh": 30, "co2_price_eur_per_t": 50, "electricity_price_eur_per_mwh": 200} | 0.654 | wrong_conclusion | design: 1D-2500m-boiler-electric 40.09 EUR/MWh vs oracle 1D-3100m-boiler-electric-chp-tower 33.015 (regret 21.4 %) |
| gpt-6-luna | B5b | {} | 0.654 | wrong_conclusion | design: 1D-3000m-boiler-electric 38.7 EUR/MWh vs oracle 2D-3100m-boiler-electric-chp-screw 35.158 (regret 10.1 %) |
| gpt-6-luna | B8 | {} | 0.41 | wrong_conclusion | premise None; did not give the cost of the design asked about; gave no cheaper run as evidence |
| gpt-6-luna | B13 | {"fault": "dc_zero_flow_crash"} | 0.55 | wrong_conclusion | registered and passing harness: none |
