# District return temperatures against the constraints

Weather: knmi_etmgeg_240_1991_2025.txt. Pick: {'n_doublets': 2, 'depth_m': 3100, 'upgrade': 'boiler', 'cooling': 'electric', 'chp': True, 'chiller_capacity_mw': 9.0, 'chiller_type': 'air_cooled_screw', 'free_cooling': True, 'ates_doublets': 3, 'boiler_capacity_mw': 33.0}.

| parameter | value_c | pick_value | lcoe_eur_per_mwh | co2_t_per_year | unmet_heating_mwh | unmet_cooling_mwh | max_brine_cooling_k | geothermal_share_of_heat | all_hard_rules |
|---|---|---|---|---|---|---|---|---|---|
| heating_return_c | 30.0 | False | 35.69 | 4343 | 0.0 | 0.0 | 40.0 | 0.932 | True |
| heating_return_c | 35.0 | False | 35.7 | 4345 | 0.0 | 0.0 | 40.0 | 0.932 | True |
| heating_return_c | 40.0 | True | 35.71 | 4345 | 0.0 | 0.0 | 40.0 | 0.931 | True |
| heating_return_c | 45.0 | False | 35.73 | 4345 | 0.0 | 0.0 | 40.0 | 0.931 | True |
| heating_return_c | 50.0 | False | 35.75 | 4356 | 0.0 | 0.0 | 40.0 | 0.931 | True |
| heating_return_c | 55.0 | False | 35.97 | 4508 | 0.0 | 0.0 | 38.99 | 0.928 | True |
| heating_return_c | 60.0 | False | 36.57 | 4955 | 0.0 | 0.0 | 38.44 | 0.922 | True |
| heating_return_c | 62.0 | False | 36.92 | 5149 | 0.0 | 0.0 | 37.92 | 0.92 | True |
| cooling_return_c | 23.0 | False | 36.05 | 4487 | 0.0 | 0.0 | 40.0 | 0.931 | True |
| cooling_return_c | 24.0 | False | 35.95 | 4447 | 0.0 | 0.0 | 40.0 | 0.931 | True |
| cooling_return_c | 26.0 | True | 35.71 | 4345 | 0.0 | 0.0 | 40.0 | 0.931 | True |
| cooling_return_c | 28.0 | False | 35.53 | 4240 | 0.0 | 0.0 | 40.0 | 0.932 | True |
| cooling_return_c | 30.0 | False | 35.33 | 4133 | 0.0 | 0.0 | 40.0 | 0.933 | True |
