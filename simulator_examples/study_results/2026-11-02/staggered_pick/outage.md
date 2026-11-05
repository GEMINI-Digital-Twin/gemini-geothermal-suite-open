# Geothermal source outage study

Weather: knmi_etmgeg_240_1991_2025.txt. Pick: {'n_doublets': 2, 'depth_m': 3100, 'upgrade': 'boiler', 'cooling': 'electric', 'chp': True, 'chiller_capacity_mw': 9.0, 'chiller_type': 'air_cooled_screw', 'free_cooling': True, 'ates_doublets': 3, 'boiler_capacity_mw': 33.0}.

S6: whole-source 35-day outage started on each of 331 days: demand fully met in 331 of 331; LCOE 36.78-45.24 EUR/MWh.

| case | doublet_outages | days_without_geothermal | boiler_mw | unmet_heating_mwh | unmet_cooling_mwh | purchased_gas_mwh | peak_boiler_mw | boiler_headroom_mw | co2_t_per_year | lcoe_eur_per_mwh | all_hard_rules |
|---|---|---|---|---|---|---|---|---|---|---|---|
| S1 headline: staggered planned stops, 33 MW boiler | 05-26..06-29 (1 on); 07-09..08-12 (1 on) | 0 | 33.0 | 0.0 | 0.0 | 27 | 0.41 | 32.59 | 4345 | 35.71 | True |
| S1b staggered, best summer pair (doublet 1 from day 176) | 06-26..09-03 (1 on) | 0 | 33.0 | 0.0 | 0.0 | 27 | 0.41 | 32.59 | 4308 | 35.71 | True |
| S1c staggered, 30 MW boiler (= peak) | 05-26..06-29 (1 on); 07-09..08-12 (1 on) | 0 | 30.0 | 0.0 | 0.0 | 27 | 0.41 | 29.59 | 4345 | 35.51 | True |
| S2 whole source planned in the lowest-load window | 07-09..08-12 (0 on) | 35 | 33.0 | 0.0 | 0.0 | 2643 | 3.47 | 29.53 | 4790 | 36.78 | True |
| S3 one doublet fails at the winter peak | 01-01..02-04 (1 on); 07-09..08-12 (1 on) | 0 | 33.0 | 0.0 | 0.0 | 10004 | 14.75 | 18.25 | 6157 | 39.74 | True |
| S4 both doublets fail at the winter peak | 01-01..02-04 (0 on) | 35 | 33.0 | 0.0 | 0.0 | 24241 | 30.0 | 3.0 | 8729 | 45.24 | True |
| S5 both fail at the winter peak, heating +6 % | 01-01..02-04 (0 on) | 35 | 33.0 | 0.0 | 0.0 | 25696 | 31.8 | 1.2 | 9186 | 43.86 | True |
| S5b same with a 30 MW boiler | 01-01..02-04 (0 on) | 35 | 30.0 | 97.6 | 0.0 | 25587 | 30.0 | 0.0 | 9164 | 43.66 | False |
| S6 whole-source sweep: costliest start day | 01-01..02-04 (0 on) | 35 | 33.0 | 0.0 | 0.0 | 24241 | 30.0 | 3.0 | 8729 | 45.24 | True |
| S6 whole-source sweep: least boiler headroom | 01-01..02-04 (0 on) | 35 | 33.0 | 0.0 | 0.0 | 24241 | 30.0 | 3.0 | 8729 | 45.24 | True |
