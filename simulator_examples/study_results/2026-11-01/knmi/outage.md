# Geothermal source outage study

Weather: knmi_etmgeg_240_1991_2025.txt. Pick: {'n_doublets': 2, 'depth_m': 3100, 'upgrade': 'boiler', 'cooling': 'electric', 'chp': True, 'chiller_type': 'air_cooled_screw', 'free_cooling': True, 'ates_doublets': 3, 'chiller_capacity_mw': 9.0}.

Whole-source 35-day outage started on each of 331 days: demand fully met in 331 of 331; LCOE 36.57-45.04 EUR/MWh.

| case | outage_start | days_without_geothermal | boiler_mw | unmet_heating_mwh | unmet_cooling_mwh | purchased_gas_mwh | peak_boiler_mw | boiler_headroom_mw | co2_t_per_year | lcoe_eur_per_mwh | all_hard_rules |
|---|---|---|---|---|---|---|---|---|---|---|---|
| base: whole source down, lowest-load window | 2027-07-09 | 35 | 30.0 | 0.0 | 0.0 | 2643 | 3.47 | 26.53 | 4790 | 36.57 | True |
| old: staggered per-doublet stops | staggered | 0 | 30.0 | 0.0 | 0.0 | 27 | 0.41 | 29.59 | 4345 | 35.51 | True |
| sweep: costliest start day | 2027-01-01 | 35 | 30.0 | 0.0 | 0.0 | 24241 | 30.0 | 0.0 | 8729 | 45.04 | True |
| sweep: least boiler headroom | 2027-01-01 | 35 | 30.0 | 0.0 | 0.0 | 24241 | 30.0 | 0.0 | 8729 | 45.04 | True |
| winter-peak outage, heating +6 %, 30 MW boiler | 2027-01-01 | 35 | 30.0 | 97.6 | 0.0 | 25587 | 30.0 | 0.0 | 9164 | 43.66 | False |
| winter-peak outage, heating +6 %, 33 MW boiler | 2027-01-01 | 35 | 33.0 | 0.0 | 0.0 | 25696 | 31.8 | 1.2 | 9186 | 43.86 | True |
