# Seasonal heat store or a second doublet?

Author: Sa'eed Telvari

Simulator runs, no LLM (`run_store_vs_doublet.py`), weather knmi_etmgeg_240_1991_2025.txt (2025). Store model: GPT-6.1 Sol's `seasonal_heat_store.py` (sol_r1), 25 MW, 500 EUR/MWh of capacity and 0.1 MEUR/MW of power, 0.1 %/day loss. 1D and 2D plants: 3.1 km, boiler, CHP, screw chiller with dry cooler.

**The store model is energy only.** It holds MWh with a daily loss and has no temperatures; charged heat comes back at the 100 degC supply. A real pit store holds 80-95 degC water and needs a top-up, so the store results are optimistic.

## Basis A: Sol: common 35-day stop from day 11, CO2 180 EUR/t

| case | lcoe_eur_per_mwh | co2_t_per_year | capex_meur | purchased_gas_mwh | storage_in_mwh | storage_out_mwh | storage_loss_mwh | meets_all_hard_rules |
|---|---|---|---|---|---|---|---|---|
| 1D, no store | 47.57 | 11800 | 24.45 | 39965 | 0 | 0 | 0 | True |
| 1D + 5 GWh store | 48.43 | 10920 | 29.45 | 34582 | 5131 | 4839 | 292 | True |
| 1D + 10 GWh store | 47.51 | 10030 | 31.95 | 29343 | 10395 | 9553 | 842 | True |
| 1D + 20 GWh store | 45.79 | 8283 | 36.95 | 19099 | 21219 | 18774 | 2445 | True |
| 1D + 30 GWh store | 44.21 | 6599 | 41.95 | 9011 | 32468 | 27852 | 4616 | True |
| 1D + 37.5 GWh store | 43.14 | 5378 | 45.7 | 1574 | 41224 | 34546 | 6678 | True |
| 1D + 40 GWh store | 43.73 | 5288 | 46.95 | 986 | 41947 | 35073 | 6874 | True |
| 2D, no store | 51.11 | 8825 | 43.38 | 23834 | 0 | 0 | 0 | True |
| 2D + 5 GWh store | 51.95 | 7930 | 48.38 | 18295 | 5090 | 4976 | 114 | True |
| 2D + 10 GWh store | 51.05 | 7032 | 50.88 | 12809 | 10331 | 9912 | 419 | True |
| 2D + 20 GWh store | 49.18 | 5234 | 55.88 | 1970 | 21082 | 19660 | 1422 | True |
| 2D + 30 GWh store | 52.13 | 5073 | 60.88 | 995 | 22073 | 20538 | 1536 | True |
| 2D + 37.5 GWh store | 54.7 | 5073 | 64.63 | 995 | 22073 | 20538 | 1536 | True |
| 2D + 40 GWh store | 55.55 | 5073 | 65.88 | 995 | 22073 | 20538 | 1536 | True |
| final pick (2D, ATES, 33 MW boiler) | 51.29 | 8356 | 46.53 | 23831 | 0 | 0 | 0 | True |

Cheapest that meets every rule: **1D + 37.5 GWh store**, 43.14 EUR/MWh, 5378 t CO2/yr.

- 1 doublet: best store size 37.5 GWh, 43.14 EUR/MWh (no store: 47.57).
- 2 doublets: best store size 20 GWh, 49.18 EUR/MWh (no store: 51.11).

## Basis B: ours: staggered stops in the lowest-load window, CO2 80 EUR/t

| case | lcoe_eur_per_mwh | co2_t_per_year | capex_meur | purchased_gas_mwh | storage_in_mwh | storage_out_mwh | storage_loss_mwh | meets_all_hard_rules |
|---|---|---|---|---|---|---|---|---|
| 1D, no store | 34.4 | 9796 | 24.45 | 28341 | 0 | 0 | 0 | True |
| 1D + 5 GWh store | 34.92 | 8463 | 29.45 | 20345 | 7538 | 7193 | 345 | True |
| 1D + 10 GWh store | 34.66 | 7565 | 31.95 | 15106 | 12802 | 11908 | 895 | True |
| 1D + 20 GWh store | 34.29 | 5839 | 36.95 | 4927 | 23941 | 21068 | 2873 | True |
| 1D + 30 GWh store | 35.9 | 5024 | 41.95 | 4 | 29787 | 25499 | 4288 | True |
| 1D + 37.5 GWh store | 38.47 | 5024 | 45.7 | 4 | 29787 | 25499 | 4288 | True |
| 1D + 40 GWh store | 39.33 | 5024 | 46.95 | 4 | 29787 | 25499 | 4288 | True |
| 2D, no store | 35.18 | 4875 | 43.38 | 26 | 0 | 0 | 0 | True |
| 2D + 5 GWh store | 38.6 | 4875 | 48.38 | 26 | 0 | 0 | 0 | True |
| 2D + 10 GWh store | 40.32 | 4875 | 50.88 | 26 | 0 | 0 | 0 | True |
| 2D + 20 GWh store | 43.74 | 4875 | 55.88 | 26 | 0 | 0 | 0 | True |
| 2D + 30 GWh store | 47.16 | 4875 | 60.88 | 26 | 0 | 0 | 0 | True |
| 2D + 37.5 GWh store | 49.72 | 4875 | 64.63 | 26 | 0 | 0 | 0 | True |
| 2D + 40 GWh store | 50.58 | 4875 | 65.88 | 26 | 0 | 0 | 0 | True |
| final pick (2D, ATES, 33 MW boiler) | 35.71 | 4345 | 46.53 | 27 | 0 | 0 | 0 | True |

Cheapest that meets every rule: **1D + 20 GWh store**, 34.29 EUR/MWh, 5839 t CO2/yr.

- 1 doublet: best store size 20 GWh, 34.29 EUR/MWh (no store: 34.4).
- 2 doublets: best store size 0 GWh, 35.18 EUR/MWh (no store: 35.18).

## Basis C: the client's CO2 weight without the yearly winter stop (DeepSeek's basis): staggered stops, CO2 180 EUR/t

| case | lcoe_eur_per_mwh | co2_t_per_year | capex_meur | purchased_gas_mwh | storage_in_mwh | storage_out_mwh | storage_loss_mwh | meets_all_hard_rules |
|---|---|---|---|---|---|---|---|---|
| 1D, no store | 41.62 | 9758 | 24.45 | 28345 | 0 | 0 | 0 | True |
| 1D + 5 GWh store | 41.15 | 8431 | 29.45 | 20347 | 7538 | 7193 | 345 | True |
| 1D + 10 GWh store | 40.24 | 7541 | 31.95 | 15108 | 12802 | 11908 | 895 | True |
| 1D + 20 GWh store | 38.6 | 5829 | 36.95 | 4928 | 23941 | 21068 | 2873 | True |
| 1D + 30 GWh store | 39.61 | 5023 | 41.95 | 6 | 29787 | 25499 | 4288 | True |
| 1D + 37.5 GWh store | 42.18 | 5023 | 45.7 | 6 | 29787 | 25499 | 4288 | True |
| 1D + 40 GWh store | 43.03 | 5023 | 46.95 | 6 | 29787 | 25499 | 4288 | True |
| 2D, no store | 38.67 | 4676 | 43.38 | 38 | 0 | 0 | 0 | True |
| 2D + 5 GWh store | 42.09 | 4676 | 48.38 | 38 | 0 | 0 | 0 | True |
| 2D + 10 GWh store | 43.8 | 4676 | 50.88 | 38 | 0 | 0 | 0 | True |
| 2D + 20 GWh store | 47.22 | 4676 | 55.88 | 38 | 0 | 0 | 0 | True |
| 2D + 30 GWh store | 50.64 | 4676 | 60.88 | 38 | 0 | 0 | 0 | True |
| 2D + 37.5 GWh store | 53.21 | 4676 | 64.63 | 38 | 0 | 0 | 0 | True |
| 2D + 40 GWh store | 54.06 | 4676 | 65.88 | 38 | 0 | 0 | 0 | True |
| final pick (2D, ATES, 33 MW boiler) | 38.84 | 4207 | 46.53 | 35 | 0 | 0 | 0 | True |

Cheapest that meets every rule: **1D + 20 GWh store**, 38.6 EUR/MWh, 5829 t CO2/yr.

- 1 doublet: best store size 20 GWh, 38.6 EUR/MWh (no store: 41.62).
- 2 doublets: best store size 0 GWh, 38.67 EUR/MWh (no store: 38.67).


## Findings (written by hand from the tables above)

1. **The basis decides it, not the store alone.** On Sol's basis (A), with both wells
   down over the coldest day in every year, 1 doublet + 37.5 GWh is the cheapest of all
   (43.14 EUR/MWh) and beats the best 2-doublet case (2D + 20 GWh, 49.18) by 6 EUR/MWh.
   Without the yearly winter stop, the result changes:
   - B (CO2 80 EUR/t): 1D + 20 GWh 34.29, 1D no store 34.40, 2D no store 35.18, final
     pick 35.71. The store saves only 0.11 EUR/MWh but cuts 4.0 kt CO2/yr.
   - C (CO2 180 EUR/t): 1D + 20 GWh 38.60, 2D no store 38.67, final pick 38.84. The three
     are within 0.24 EUR/MWh of each other. CO2 is 5.83, 4.68 and 4.21 kt/yr.
2. **37.5 GWh is sized for the common winter stop.** Off Sol's basis, a 1-doublet store
   takes in at most 29.8 GWh per year (B, C). Above about 30 GWh, the extra capacity is
   never used and only adds cost. The best size there is 20 GWh.
3. **A store does nothing for 2 doublets with staggered stops.** On B and C, the
   2-doublet store never charges (0 MWh in), because the two doublets already cover the
   winter without a deficit to fill. Every GWh only adds cost. On A it helps (best
   20 GWh, 49.18 against 51.11) but never catches 1D + store.
4. **Under the client's CO2 weight (C), 1D + 20 GWh and 2 doublets tie on cost.** The
   2-doublet plants keep 1.2-1.6 kt/yr less CO2 and do not depend on an unproven 20 GWh
   pit store (about 300,000 m3 of water) or on an energy-only store model. That supports
   keeping 2 doublets with ATES as the pick, and naming 1D + store as the alternative.

## Notes on the method

- The store model is Sol's own file, loaded as is. The script wraps it only to clip a
  rounding error at the empty and full ends (about 3e-14 MWh): Sol's model raised on
  that, and the 2-doublet runs reach it. The wrapper changes nothing else.
- The store model is energy only: no temperatures, and heat comes back at the 100 degC
  supply. Results with a store are optimistic.
- 1-doublet plants use Sol's 0.55 MWe CHP; 2-doublet plants use the default CHP size.
  All plants keep the default 30 MW boiler and 10 MW chiller, except the final pick
  (33 MW boiler, 9 MW air-cooled chiller, free cooling, 3 ATES pairs).
- A rerun of the script writes the tables again, without this section.
