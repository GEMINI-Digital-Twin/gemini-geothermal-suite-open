# One doublet + a realistic pit heat store, against the current pick

Author: Sa'eed Telvari

Simulator runs, no LLM (`run_pit_store_study.py`), weather knmi_etmgeg_240_1991_2025.txt (2025). Store model: `gemini_design.pit_storage` (built in). Basis: staggered 35-day doublet stops in the lowest-load window, CO2 80 EUR/t, lined casing.

## reference

| case | lcoe_eur_per_mwh | co2_t_per_year | store_capex_meur | pits | land_ha | store_in_mwh | store_out_mwh | boiler_topup_mwh | store_loss_mwh | store_efficiency | max_top_c | meets_all_hard_rules | physics_gate |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| current pick (2D, ATES, 33 MW boiler) | 35.98 | 4617 | 0.0 | 0 | 0.0 | 0 | 0 | 0 | 0 | 0.0 | 0.0 | True | pass |
| 1D, Sol's plant, no store | 35.33 | 10476 | 0.0 | 0 | 0.0 | 0 | 0 | 0 | 0 | 0.0 | 0.0 | True | pass |
| 1D, pick's cooling, no store | 36.25 | 10081 | 0.0 | 0 | 0.0 | 0 | 0 | 0 | 0 | 0.0 | 0.0 | True | pass |

## 1D + pit, Sol's plant

| case | lcoe_eur_per_mwh | co2_t_per_year | store_capex_meur | pits | land_ha | store_in_mwh | store_out_mwh | boiler_topup_mwh | store_loss_mwh | store_efficiency | max_top_c | meets_all_hard_rules | physics_gate |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1D + 100k m3 @ 10 MW | 37.08 | 9428 | 5.89 | 1 | 1.8 | 7459 | 6124 | 4612 | 1335 | 0.82 | 89.2 | True | pass |
| 1D + 100k m3 @ 15 MW | 37.36 | 9394 | 6.39 | 1 | 1.8 | 7538 | 6201 | 4585 | 1337 | 0.82 | 89.5 | True | pass |
| 1D + 100k m3 @ 25 MW | 38.05 | 9400 | 7.39 | 1 | 1.8 | 7581 | 6242 | 4567 | 1339 | 0.82 | 89.7 | True | pass |
| 1D + 200k m3 @ 10 MW | 36.96 | 8560 | 8.42 | 1 | 3.0 | 12886 | 10456 | 8311 | 2433 | 0.81 | 88.8 | True | pass |
| 1D + 200k m3 @ 15 MW | 37.28 | 8550 | 8.92 | 1 | 3.0 | 13167 | 10731 | 8287 | 2436 | 0.81 | 89.1 | True | pass |
| 1D + 200k m3 @ 25 MW | 37.91 | 8524 | 9.92 | 1 | 3.0 | 13303 | 10861 | 8239 | 2442 | 0.82 | 89.5 | True | pass |
| 1D + 250k m3 @ 10 MW | 36.7 | 8091 | 9.5 | 1 | 3.6 | 15846 | 12790 | 9599 | 3070 | 0.81 | 88.5 | True | pass |
| 1D + 250k m3 @ 15 MW | 37.05 | 8100 | 10.0 | 1 | 3.6 | 16069 | 13036 | 9774 | 3033 | 0.81 | 89.0 | True | pass |
| 1D + 250k m3 @ 25 MW | 37.69 | 8080 | 11.0 | 1 | 3.6 | 16247 | 13205 | 9700 | 3043 | 0.81 | 89.4 | True | pass |
| 1D + 350k m3 @ 10 MW | 39.4 | 7706 | 14.69 | 2 | 5.5 | 19875 | 14853 | 9662 | 5115 | 0.75 | 87.6 | True | pass |
| 1D + 350k m3 @ 15 MW | 39.33 | 7521 | 15.19 | 2 | 5.5 | 21390 | 16182 | 9317 | 5201 | 0.76 | 88.5 | True | pass |
| 1D + 350k m3 @ 25 MW | 39.9 | 7470 | 16.19 | 2 | 5.5 | 21808 | 16540 | 8959 | 5250 | 0.76 | 89.1 | True | pass |
| 1D + 500k m3 @ 10 MW | 42.56 | 8139 | 18.01 | 2 | 7.3 | 19352 | 13094 | 11421 | 6256 | 0.68 | 85.4 | True | pass |
| 1D + 500k m3 @ 15 MW | 42.62 | 8012 | 18.51 | 2 | 7.3 | 20461 | 13990 | 11509 | 6321 | 0.68 | 86.1 | True | pass |
| 1D + 500k m3 @ 25 MW | 43.3 | 8008 | 19.51 | 2 | 7.3 | 20461 | 13990 | 11509 | 6321 | 0.68 | 86.1 | True | pass |
| 1D + 750k m3 @ 10 MW | 49.69 | 8781 | 26.51 | 3 | 10.9 | 19146 | 10299 | 14216 | 8404 | 0.54 | 80.1 | True | pass |
| 1D + 750k m3 @ 15 MW | 49.84 | 8697 | 27.01 | 3 | 10.9 | 19841 | 10998 | 14501 | 8475 | 0.55 | 80.9 | True | pass |
| 1D + 750k m3 @ 25 MW | 50.51 | 8690 | 28.01 | 3 | 10.9 | 19841 | 10998 | 14501 | 8475 | 0.55 | 80.9 | True | pass |

## one pit above the built range (upper bound)

| case | lcoe_eur_per_mwh | co2_t_per_year | store_capex_meur | pits | land_ha | store_in_mwh | store_out_mwh | boiler_topup_mwh | store_loss_mwh | store_efficiency | max_top_c | meets_all_hard_rules | physics_gate |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1D + one 300k m3 pit @ 15 MW | 36.77 | 7652 | 11.01 | 1 | 4.2 | 19162 | 15402 | 10095 | 3759 | 0.8 | 88.9 | True | pass |
| 1D + one 350k m3 pit @ 15 MW | 36.91 | 7423 | 11.95 | 1 | 4.8 | 21127 | 16617 | 8882 | 4505 | 0.79 | 88.7 | True | pass |
| 1D + one 400k m3 pit @ 15 MW | 37.85 | 7578 | 12.84 | 1 | 5.4 | 21025 | 16042 | 9457 | 4904 | 0.76 | 88.1 | True | pass |

## 1D + pit, pick's cooling

| case | lcoe_eur_per_mwh | co2_t_per_year | store_capex_meur | pits | land_ha | store_in_mwh | store_out_mwh | boiler_topup_mwh | store_loss_mwh | store_efficiency | max_top_c | meets_all_hard_rules | physics_gate |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1D pick-cooling + 200k m3 @ 25 MW | 38.83 | 8133 | 9.92 | 1 | 3.0 | 13303 | 10861 | 8239 | 2442 | 0.82 | 89.5 | True | pass |
| 1D pick-cooling + 350k m3 @ 25 MW | 40.82 | 7078 | 16.19 | 2 | 5.5 | 21808 | 16540 | 8959 | 5250 | 0.76 | 89.1 | True | pass |
| 1D pick-cooling + 500k m3 @ 25 MW | 44.22 | 7617 | 19.51 | 2 | 7.3 | 20461 | 13990 | 11509 | 6321 | 0.68 | 86.1 | True | pass |

## 2D + pit

| case | lcoe_eur_per_mwh | co2_t_per_year | store_capex_meur | pits | land_ha | store_in_mwh | store_out_mwh | boiler_topup_mwh | store_loss_mwh | store_efficiency | max_top_c | meets_all_hard_rules | physics_gate |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| pick + 100k m3 @ 15 MW | 40.38 | 4646 | 6.39 | 1 | 1.8 | 943 | 0 | 0 | 943 | 0.0 | 45.8 | True | pass |
| pick + 250k m3 @ 15 MW | 42.89 | 4678 | 10.0 | 1 | 3.6 | 1885 | 0 | 0 | 1885 | 0.0 | 46.1 | True | pass |

## kinder store assumptions

| case | lcoe_eur_per_mwh | co2_t_per_year | store_capex_meur | pits | land_ha | store_in_mwh | store_out_mwh | boiler_topup_mwh | store_loss_mwh | store_efficiency | max_top_c | meets_all_hard_rules | physics_gate |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1D + 250k m3 @ 10 MW, cheaper pits (-30 %) | 35.18 | 8091 | 7.28 | 1 | 3.6 | 15846 | 12790 | 9599 | 3070 | 0.81 | 88.5 | True | pass |
| 1D + 250k m3 @ 10 MW, half the losses | 36.37 | 7921 | 9.5 | 1 | 3.6 | 15043 | 13512 | 9456 | 1555 | 0.9 | 89.2 | True | pass |
| 1D + 250k m3 @ 10 MW, 95 degC liner | 36.07 | 7793 | 9.5 | 1 | 3.6 | 17498 | 14256 | 8509 | 3260 | 0.81 | 93.2 | True | pass |
| 1D + 250k m3 @ 10 MW, no land cost, no price index | 34.64 | 8091 | 6.49 | 1 | 3.6 | 15846 | 12790 | 9599 | 3070 | 0.81 | 88.5 | True | pass |
| 1D + 250k m3 @ 10 MW, all four together | 32.5 | 7602 | 4.84 | 1 | 3.6 | 16686 | 15065 | 8222 | 1651 | 0.9 | 94.1 | True | pass |

## basis: winter stop (both doublets down 35 days from day 11)

| case | lcoe_eur_per_mwh | co2_t_per_year | store_capex_meur | pits | land_ha | store_in_mwh | store_out_mwh | boiler_topup_mwh | store_loss_mwh | store_efficiency | max_top_c | meets_all_hard_rules | physics_gate |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| current pick, winter stop (both doublets down 35 days from day 11) | 45.39 | 8793 | 0.0 | 0 | 0.0 | 0 | 0 | 0 | 0 | 0.0 | 0.0 | True | pass |
| 1D + 250k m3 @ 10 MW, winter stop (both doublets down 35 days from day 11) | 41.23 | 10259 | 9.5 | 1 | 3.6 | 14553 | 11633 | 8554 | 2928 | 0.8 | 88.5 | True | pass |
| 1D, Sol's plant, no store, winter stop (both doublets down 35 days from day 11) | 39.44 | 12447 | 0.0 | 0 | 0.0 | 0 | 0 | 0 | 0 | 0.0 | 0.0 | True | pass |

## basis: CO2 at 180 EUR/t

| case | lcoe_eur_per_mwh | co2_t_per_year | store_capex_meur | pits | land_ha | store_in_mwh | store_out_mwh | boiler_topup_mwh | store_loss_mwh | store_efficiency | max_top_c | meets_all_hard_rules | physics_gate |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| current pick, CO2 at 180 EUR/t | 39.37 | 4576 | 0.0 | 0 | 0.0 | 0 | 0 | 0 | 0 | 0.0 | 0.0 | True | pass |
| 1D + 250k m3 @ 10 MW, CO2 at 180 EUR/t | 42.67 | 8091 | 9.5 | 1 | 3.6 | 15846 | 12790 | 9599 | 3070 | 0.81 | 88.5 | True | pass |
| 1D, Sol's plant, no store, CO2 at 180 EUR/t | 43.07 | 10476 | 0.0 | 0 | 0.0 | 0 | 0 | 0 | 0 | 0.0 | 0.0 | True | pass |

