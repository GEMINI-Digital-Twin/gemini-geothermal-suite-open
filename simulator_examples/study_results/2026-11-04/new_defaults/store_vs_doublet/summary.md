# Seasonal heat store or a second doublet?

Author: Sa'eed Telvari

Simulator runs, no LLM (`run_store_vs_doublet.py`), weather knmi_etmgeg_240_1991_2025.txt (2025). Store model: GPT-6.1 Sol's `seasonal_heat_store.py` (sol_r1), 25 MW, 500 EUR/MWh of capacity and 0.1 MEUR/MW of power, 0.1 %/day loss. 1D and 2D plants: 3.1 km, boiler, CHP, screw chiller with dry cooler.

**The store model is energy only.** It holds MWh with a daily loss and has no temperatures; charged heat comes back at the 100 degC supply. A real pit store holds 80-95 degC water and needs a top-up, so the store results are optimistic.

## Basis A: Sol: common 35-day stop from day 11, CO2 180 EUR/t

| case | lcoe_eur_per_mwh | co2_t_per_year | capex_meur | purchased_gas_mwh | storage_in_mwh | storage_out_mwh | storage_loss_mwh | meets_all_hard_rules |
|---|---|---|---|---|---|---|---|---|
| 1D, no store | 48.63 | 12447 | 24.45 | 41569 | 0 | 0 | 0 | True |
| 1D + 5 GWh store | 49.2 | 11460 | 29.45 | 35724 | 5131 | 4839 | 292 | True |
| 1D + 10 GWh store | 48.17 | 10506 | 31.95 | 30383 | 10395 | 9553 | 842 | True |
| 1D + 20 GWh store | 46.37 | 8684 | 36.95 | 20230 | 21219 | 18774 | 2445 | True |
| 1D + 30 GWh store | 44.77 | 6940 | 41.95 | 10314 | 32468 | 27852 | 4616 | True |
| 1D + 37.5 GWh store | 43.57 | 5645 | 45.7 | 2865 | 41224 | 34546 | 6678 | True |
| 1D + 40 GWh store | 43.95 | 5481 | 46.95 | 1923 | 41947 | 35073 | 6874 | True |
| 2D, no store | 51.41 | 9227 | 43.38 | 23886 | 0 | 0 | 0 | True |
| 2D + 5 GWh store | 52.33 | 8357 | 48.38 | 18483 | 5090 | 4976 | 114 | True |
| 2D + 10 GWh store | 51.55 | 7496 | 50.88 | 13189 | 10331 | 9912 | 419 | True |
| 2D + 20 GWh store | 49.7 | 5708 | 55.88 | 2494 | 21082 | 19660 | 1422 | True |
| 2D + 30 GWh store | 52.62 | 5535 | 60.88 | 1475 | 22073 | 20538 | 1536 | True |
| 2D + 37.5 GWh store | 55.18 | 5535 | 64.63 | 1475 | 22073 | 20538 | 1536 | True |
| 2D + 40 GWh store | 56.04 | 5535 | 65.88 | 1475 | 22073 | 20538 | 1536 | True |
| final pick (2D, ATES, 33 MW boiler) | 51.87 | 8753 | 46.53 | 23942 | 0 | 0 | 0 | True |

Cheapest that meets every rule: **1D + 37.5 GWh store**, 43.57 EUR/MWh, 5645 t CO2/yr.

- 1 doublet: best store size 37.5 GWh, 43.57 EUR/MWh (no store: 48.63).
- 2 doublets: best store size 20 GWh, 49.7 EUR/MWh (no store: 51.41).

## Basis B: ours: staggered stops in the lowest-load window, CO2 80 EUR/t

| case | lcoe_eur_per_mwh | co2_t_per_year | capex_meur | purchased_gas_mwh | storage_in_mwh | storage_out_mwh | storage_loss_mwh | meets_all_hard_rules |
|---|---|---|---|---|---|---|---|---|
| 1D, no store | 35.33 | 10476 | 24.45 | 30742 | 0 | 0 | 0 | True |
| 1D + 5 GWh store | 35.49 | 8944 | 29.45 | 21901 | 7538 | 7193 | 345 | True |
| 1D + 10 GWh store | 35.16 | 7990 | 31.95 | 16559 | 12802 | 11908 | 895 | True |
| 1D + 20 GWh store | 34.59 | 6123 | 36.95 | 6073 | 23941 | 21068 | 2873 | True |
| 1D + 30 GWh store | 36.02 | 5199 | 41.95 | 805 | 29787 | 25499 | 4288 | True |
| 1D + 37.5 GWh store | 38.58 | 5199 | 45.7 | 805 | 29787 | 25499 | 4288 | True |
| 1D + 40 GWh store | 39.44 | 5199 | 46.95 | 805 | 29787 | 25499 | 4288 | True |
| 2D, no store | 35.19 | 5143 | 43.38 | 0 | 0 | 0 | 0 | True |
| 2D + 5 GWh store | 38.61 | 5143 | 48.38 | 0 | 0 | 0 | 0 | True |
| 2D + 10 GWh store | 40.32 | 5143 | 50.88 | 0 | 0 | 0 | 0 | True |
| 2D + 20 GWh store | 43.74 | 5143 | 55.88 | 0 | 0 | 0 | 0 | True |
| 2D + 30 GWh store | 47.16 | 5143 | 60.88 | 0 | 0 | 0 | 0 | True |
| 2D + 37.5 GWh store | 49.73 | 5143 | 64.63 | 0 | 0 | 0 | 0 | True |
| 2D + 40 GWh store | 50.58 | 5143 | 65.88 | 0 | 0 | 0 | 0 | True |
| final pick (2D, ATES, 33 MW boiler) | 35.98 | 4617 | 46.53 | 0 | 0 | 0 | 0 | True |

Cheapest that meets every rule: **1D + 20 GWh store**, 34.59 EUR/MWh, 6123 t CO2/yr.

- 1 doublet: best store size 20 GWh, 34.59 EUR/MWh (no store: 35.33).
- 2 doublets: best store size 0 GWh, 35.19 EUR/MWh (no store: 35.19).

## Basis C: the client's CO2 weight without the yearly winter stop (DeepSeek's basis): staggered stops, CO2 180 EUR/t

| case | lcoe_eur_per_mwh | co2_t_per_year | capex_meur | purchased_gas_mwh | storage_in_mwh | storage_out_mwh | storage_loss_mwh | meets_all_hard_rules |
|---|---|---|---|---|---|---|---|---|
| 1D, no store | 43.07 | 10476 | 24.45 | 30742 | 0 | 0 | 0 | True |
| 1D + 5 GWh store | 42.09 | 8944 | 29.45 | 21901 | 7538 | 7193 | 345 | True |
| 1D + 10 GWh store | 41.06 | 7990 | 31.95 | 16559 | 12802 | 11908 | 895 | True |
| 1D + 20 GWh store | 39.11 | 6123 | 36.95 | 6073 | 23941 | 21068 | 2873 | True |
| 1D + 30 GWh store | 39.86 | 5199 | 41.95 | 816 | 29787 | 25499 | 4288 | True |
| 1D + 37.5 GWh store | 42.42 | 5199 | 45.7 | 816 | 29787 | 25499 | 4288 | True |
| 1D + 40 GWh store | 43.28 | 5199 | 46.95 | 816 | 29787 | 25499 | 4288 | True |
| 2D, no store | 38.95 | 5063 | 43.38 | 0 | 0 | 0 | 0 | True |
| 2D + 5 GWh store | 42.37 | 5063 | 48.38 | 0 | 0 | 0 | 0 | True |
| 2D + 10 GWh store | 44.08 | 5063 | 50.88 | 0 | 0 | 0 | 0 | True |
| 2D + 20 GWh store | 47.5 | 5063 | 55.88 | 0 | 0 | 0 | 0 | True |
| 2D + 30 GWh store | 50.92 | 5063 | 60.88 | 0 | 0 | 0 | 0 | True |
| 2D + 37.5 GWh store | 53.48 | 5063 | 64.63 | 0 | 0 | 0 | 0 | True |
| 2D + 40 GWh store | 54.34 | 5063 | 65.88 | 0 | 0 | 0 | 0 | True |
| final pick (2D, ATES, 33 MW boiler) | 39.37 | 4576 | 46.53 | 0 | 0 | 0 | 0 | True |

Cheapest that meets every rule: **2D, no store**, 38.95 EUR/MWh, 5063 t CO2/yr.

- 1 doublet: best store size 20 GWh, 39.11 EUR/MWh (no store: 43.07).
- 2 doublets: best store size 0 GWh, 38.95 EUR/MWh (no store: 38.95).

