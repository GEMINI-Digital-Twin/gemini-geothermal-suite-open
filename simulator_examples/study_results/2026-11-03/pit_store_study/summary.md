# One doublet + a realistic pit heat store, against the current pick

Author: Sa'eed Telvari

Simulator runs, no LLM (`run_pit_store_study.py`), weather knmi_etmgeg_240_1991_2025.txt (2025). Store model: `gemini_design.pit_storage` (built in). Basis: staggered 35-day doublet stops in the lowest-load window, CO2 80 EUR/t, lined casing.

## reference

| case | lcoe_eur_per_mwh | co2_t_per_year | store_capex_meur | pits | land_ha | store_in_mwh | store_out_mwh | boiler_topup_mwh | store_loss_mwh | store_efficiency | max_top_c | meets_all_hard_rules | physics_gate |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| current pick (2D, ATES, 33 MW boiler) | 35.71 | 4345 | 0.0 | 0 | 0.0 | 0 | 0 | 0 | 0 | 0.0 | 0.0 | True | pass |
| 1D, Sol's plant, no store | 34.4 | 9796 | 0.0 | 0 | 0.0 | 0 | 0 | 0 | 0 | 0.0 | 0.0 | True | pass |
| 1D, pick's cooling, no store | 34.92 | 9331 | 0.0 | 0 | 0.0 | 0 | 0 | 0 | 0 | 0.0 | 0.0 | True | pass |

## 1D + pit, Sol's plant

| case | lcoe_eur_per_mwh | co2_t_per_year | store_capex_meur | pits | land_ha | store_in_mwh | store_out_mwh | boiler_topup_mwh | store_loss_mwh | store_efficiency | max_top_c | meets_all_hard_rules | physics_gate |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1D + 100k m3 @ 10 MW | 36.01 | 8698 | 5.89 | 1 | 1.8 | 7459 | 6124 | 4612 | 1335 | 0.82 | 89.2 | True | pass |
| 1D + 100k m3 @ 15 MW | 36.32 | 8684 | 6.39 | 1 | 1.8 | 7538 | 6201 | 4585 | 1337 | 0.82 | 89.5 | True | pass |
| 1D + 100k m3 @ 25 MW | 36.99 | 8676 | 7.39 | 1 | 1.8 | 7581 | 6242 | 4567 | 1339 | 0.82 | 89.7 | True | pass |
| 1D + 200k m3 @ 10 MW | 35.92 | 7876 | 8.42 | 1 | 3.0 | 12886 | 10456 | 8311 | 2433 | 0.81 | 88.8 | True | pass |
| 1D + 200k m3 @ 15 MW | 36.18 | 7836 | 8.92 | 1 | 3.0 | 13167 | 10731 | 8287 | 2436 | 0.81 | 89.1 | True | pass |
| 1D + 200k m3 @ 25 MW | 36.82 | 7813 | 9.92 | 1 | 3.0 | 13303 | 10861 | 8239 | 2442 | 0.82 | 89.5 | True | pass |
| 1D + 250k m3 @ 10 MW | 35.66 | 7428 | 9.5 | 1 | 3.6 | 15846 | 12790 | 9599 | 3070 | 0.81 | 88.5 | True | pass |
| 1D + 250k m3 @ 15 MW | 35.97 | 7405 | 10.0 | 1 | 3.6 | 16069 | 13036 | 9774 | 3033 | 0.81 | 89.0 | True | pass |
| 1D + 250k m3 @ 25 MW | 36.59 | 7375 | 11.0 | 1 | 3.6 | 16247 | 13205 | 9700 | 3043 | 0.81 | 89.4 | True | pass |
| 1D + 350k m3 @ 10 MW | 38.36 | 7064 | 14.69 | 2 | 5.5 | 19875 | 14853 | 9662 | 5115 | 0.75 | 87.6 | True | pass |
| 1D + 350k m3 @ 15 MW | 38.27 | 6858 | 15.19 | 2 | 5.5 | 21390 | 16182 | 9317 | 5201 | 0.76 | 88.5 | True | pass |
| 1D + 350k m3 @ 25 MW | 38.82 | 6797 | 16.19 | 2 | 5.5 | 21808 | 16540 | 8959 | 5250 | 0.76 | 89.1 | True | pass |
| 1D + 500k m3 @ 10 MW | 41.48 | 7470 | 18.01 | 2 | 7.3 | 19352 | 13094 | 11421 | 6256 | 0.68 | 85.4 | True | pass |
| 1D + 500k m3 @ 15 MW | 41.53 | 7330 | 18.51 | 2 | 7.3 | 20461 | 13990 | 11509 | 6321 | 0.68 | 86.1 | True | pass |
| 1D + 500k m3 @ 25 MW | 42.21 | 7330 | 19.51 | 2 | 7.3 | 20461 | 13990 | 11509 | 6321 | 0.68 | 86.1 | True | pass |
| 1D + 750k m3 @ 10 MW | 48.59 | 8099 | 26.51 | 3 | 10.9 | 19146 | 10299 | 14216 | 8404 | 0.54 | 80.1 | True | pass |
| 1D + 750k m3 @ 15 MW | 48.71 | 7988 | 27.01 | 3 | 10.9 | 19841 | 10998 | 14501 | 8475 | 0.55 | 80.9 | True | pass |
| 1D + 750k m3 @ 25 MW | 49.39 | 7988 | 28.01 | 3 | 10.9 | 19841 | 10998 | 14501 | 8475 | 0.55 | 80.9 | True | pass |

## one pit above the built range (upper bound)

| case | lcoe_eur_per_mwh | co2_t_per_year | store_capex_meur | pits | land_ha | store_in_mwh | store_out_mwh | boiler_topup_mwh | store_loss_mwh | store_efficiency | max_top_c | meets_all_hard_rules | physics_gate |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1D + one 300k m3 pit @ 15 MW | 35.68 | 6965 | 11.01 | 1 | 4.2 | 19162 | 15402 | 10095 | 3759 | 0.8 | 88.9 | True | pass |
| 1D + one 350k m3 pit @ 15 MW | 35.84 | 6753 | 11.95 | 1 | 4.8 | 21127 | 16617 | 8882 | 4505 | 0.79 | 88.7 | True | pass |
| 1D + one 400k m3 pit @ 15 MW | 36.73 | 6884 | 12.84 | 1 | 5.4 | 21025 | 16042 | 9457 | 4904 | 0.76 | 88.1 | True | pass |

## 1D + pit, pick's cooling

| case | lcoe_eur_per_mwh | co2_t_per_year | store_capex_meur | pits | land_ha | store_in_mwh | store_out_mwh | boiler_topup_mwh | store_loss_mwh | store_efficiency | max_top_c | meets_all_hard_rules | physics_gate |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1D pick-cooling + 200k m3 @ 25 MW | 37.33 | 7346 | 9.92 | 1 | 3.0 | 13303 | 10861 | 8239 | 2442 | 0.82 | 89.5 | True | pass |
| 1D pick-cooling + 350k m3 @ 25 MW | 39.34 | 6329 | 16.19 | 2 | 5.5 | 21808 | 16540 | 8959 | 5250 | 0.76 | 89.1 | True | pass |
| 1D pick-cooling + 500k m3 @ 25 MW | 42.73 | 6862 | 19.51 | 2 | 7.3 | 20461 | 13990 | 11509 | 6321 | 0.68 | 86.1 | True | pass |

## 2D + pit

| case | lcoe_eur_per_mwh | co2_t_per_year | store_capex_meur | pits | land_ha | store_in_mwh | store_out_mwh | boiler_topup_mwh | store_loss_mwh | store_efficiency | max_top_c | meets_all_hard_rules | physics_gate |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| pick + 100k m3 @ 15 MW | 40.11 | 4366 | 6.39 | 1 | 1.8 | 943 | 0 | 0 | 943 | 0.0 | 45.8 | True | pass |
| pick + 250k m3 @ 15 MW | 42.62 | 4398 | 10.0 | 1 | 3.6 | 1885 | 0 | 0 | 1885 | 0.0 | 46.1 | True | pass |

## kinder store assumptions

| case | lcoe_eur_per_mwh | co2_t_per_year | store_capex_meur | pits | land_ha | store_in_mwh | store_out_mwh | boiler_topup_mwh | store_loss_mwh | store_efficiency | max_top_c | meets_all_hard_rules | physics_gate |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1D + 250k m3 @ 10 MW, cheaper pits (-30 %) | 34.14 | 7428 | 7.28 | 1 | 3.6 | 15846 | 12790 | 9599 | 3070 | 0.81 | 88.5 | True | pass |
| 1D + 250k m3 @ 10 MW, half the losses | 35.3 | 7239 | 9.5 | 1 | 3.6 | 15043 | 13512 | 9456 | 1555 | 0.9 | 89.2 | True | pass |
| 1D + 250k m3 @ 10 MW, 95 degC liner | 35.03 | 7139 | 9.5 | 1 | 3.6 | 17498 | 14256 | 8509 | 3260 | 0.81 | 93.2 | True | pass |
| 1D + 250k m3 @ 10 MW, no land cost, no price index | 33.6 | 7428 | 6.49 | 1 | 3.6 | 15846 | 12790 | 9599 | 3070 | 0.81 | 88.5 | True | pass |
| 1D + 250k m3 @ 10 MW, all four together | 31.45 | 6935 | 4.84 | 1 | 3.6 | 16686 | 15065 | 8222 | 1651 | 0.9 | 94.1 | True | pass |

## basis: winter stop (both doublets down 35 days from day 11)

| case | lcoe_eur_per_mwh | co2_t_per_year | store_capex_meur | pits | land_ha | store_in_mwh | store_out_mwh | boiler_topup_mwh | store_loss_mwh | store_efficiency | max_top_c | meets_all_hard_rules | physics_gate |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| current pick, winter stop (both doublets down 35 days from day 11) | 45.1 | 8662 | 0.0 | 0 | 0.0 | 0 | 0 | 0 | 0 | 0.0 | 0.0 | True | pass |
| 1D + 250k m3 @ 10 MW, winter stop (both doublets down 35 days from day 11) | 40.56 | 9690 | 9.5 | 1 | 3.6 | 14553 | 11633 | 8554 | 2928 | 0.8 | 88.5 | True | pass |
| 1D, Sol's plant, no store, winter stop (both doublets down 35 days from day 11) | 38.84 | 11855 | 0.0 | 0 | 0.0 | 0 | 0 | 0 | 0 | 0.0 | 0.0 | True | pass |

## basis: CO2 at 180 EUR/t

| case | lcoe_eur_per_mwh | co2_t_per_year | store_capex_meur | pits | land_ha | store_in_mwh | store_out_mwh | boiler_topup_mwh | store_loss_mwh | store_efficiency | max_top_c | meets_all_hard_rules | physics_gate |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| current pick, CO2 at 180 EUR/t | 38.84 | 4207 | 0.0 | 0 | 0.0 | 0 | 0 | 0 | 0 | 0.0 | 0.0 | True | pass |
| 1D + 250k m3 @ 10 MW, CO2 at 180 EUR/t | 41.14 | 7411 | 9.5 | 1 | 3.6 | 15846 | 12790 | 9599 | 3070 | 0.81 | 88.5 | True | pass |
| 1D, Sol's plant, no store, CO2 at 180 EUR/t | 41.62 | 9758 | 0.0 | 0 | 0.0 | 0 | 0 | 0 | 0 | 0.0 | 0.0 | True | pass |


## Findings (written by hand from the tables above)

1. **With a realistic store, 1 doublet + store no longer beats the pick.** The best
   store case is 1 doublet + one 250,000 m3 pit at 10 MW (the largest pit the model
   allows; the largest built pit, Vojens, is about 200,000 m3): 35.66 EUR/MWh and
   7,428 t CO2/yr, against the pick's 35.71 EUR/MWh and 4,345 t. Cost is a tie
   (0.05 EUR/MWh), and the store design emits 3.1 kt/yr more.
2. **It never beats 1 doublet without a store on cost** (34.40 EUR/MWh, 9,796 t). The
   store buys about 2.4 kt/yr of CO2 cuts for 1.26 EUR/MWh, about 72 EUR/t. The second
   doublet (the pick) buys 5.5 kt/yr for 1.31 EUR/MWh, about 33 EUR/t.
3. **Why Sol's store looked better (34.29 EUR/MWh with 20 GWh):** its energy-only model
   gave heat back at 100 degC with about 12 % loss and no size limit. The realistic pit
   loses 19 % of the heat put in (3.1 GWh of 15.8 GWh), gives water at 50-89 degC, so the
   boiler tops up 9.6 GWh to reach 100 degC (gas and CO2 priced), and 20 GWh of capacity
   needs about 345,000 m3, which is two pits. Pit cost here: 29.7 EUR/m3 at 250,000 m3
   (2027 prices) plus 3.6 ha of land.
4. **Bigger is worse beyond one pit.** Above 250,000 m3 the cost climbs fast (38.3 EUR/MWh
   at 350,000 m3, 41.5 at 500,000 m3): the free summer heat of one doublet is only about
   20-22 GWh, so extra water is never heated fully and loses more through its surface. Even
   one 300,000-350,000 m3 pit, larger than any built, is 35.7-35.8 EUR/MWh.
5. **A store does nothing for 2 doublets** (pick + 100,000 m3: 40.11 EUR/MWh, CO2 flat):
   with staggered stops there is little winter deficit to fill.
6. **Kinder assumptions can flip the cost, not the CO2.** Cheaper pits (-30 %) give
   34.14 EUR/MWh; dropping land and the 2015-to-2027 price index gives 33.60; all four
   kinder changes together give 31.45 EUR/MWh, 6,935 t. That beats the pick on cost but
   still emits 2.6 kt/yr more. The store's case rests on cost data, not physics.
7. **Other bases.** With CO2 at 180 EUR/t the pick stays cheapest (38.84 against 41.14
   for the store). With both doublets down for 35 days from 11 January, 1 doublet without a
   store is cheapest at 80 EUR/t CO2 (38.84), then the store (40.56), then the pick (45.10).

## Limits of the model

- Daily steps with 12 layers; upwind advection adds some numerical mixing (pessimistic).
- Stores above 250,000 m3 are split into equal pits run in parallel. Running them one
  after the other would do better; the single-pit rows above are the upper bound.
- Lid and ground U-values (0.15 W/m2K) are team estimates, not calibrated on measured
  plant data; a 60,000 m3 pit cycled once a year loses about 1.3 GWh (31 % of the heat put
  in), a 250,000 m3 pit 19 %. The "half the losses" row shows the effect (35.30 EUR/MWh).
- Charging assumes the HEX still works against a 40 degC return; a warmer store bottom
  would lower the HEX duty a little.
- Costs: about 40 EUR/m3 at 60,000 m3 (2015), falling with size to the power 0.42
  (Dronninglund, Marstal, Gram, Vojens), times 1.35 to 2027, plus land at 30 EUR/m2 over
  1.5 x the top area and 0.1 MEUR/MW for the charge/discharge HEX and pumps. Low confidence.
