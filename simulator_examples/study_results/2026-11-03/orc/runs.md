# ORC study, KNMI 2025 (Schiphol), staggered stops

| case | lcoe_eur_per_mwh | co2_t | all_rules_met | capex_meur | orc_mwh_el | orc_full_load_hours | orc_mean_efficiency_pct | pumping_mwh | purchased_gas_mwh | grid_export_mwh |
|---|---|---|---|---|---|---|---|---|---|---|
| A pick (no ORC) | 35.71 | 4345 | True | 46.53 | 0 | 0 | 0.0 | 3715 | 27 | 275 |
| A pick + ORC 0.5 MW | 35.78 | 5242 | True | 48.03 | 2725 | 5449 | 5.43 | 5450 | 7 | 1906 |
| A pick + ORC 1 MW | 36.85 | 5696 | True | 49.53 | 3513 | 3513 | 5.45 | 6232 | 12 | 2504 |
| A pick + ORC 2 MW | 39.04 | 5557 | True | 52.53 | 3024 | 1512 | 5.25 | 5911 | 23 | 2212 |
| A pick + ORC 3 MW | 41.44 | 5201 | True | 55.53 | 1946 | 649 | 5.3 | 4982 | 24 | 1828 |
| B 3500 m (no ORC) | 37.67 | 4080 | True | 49.73 | 0 | 0 | 0.0 | 3438 | 18 | 473 |
| B 3500 m + ORC 1 MW | 38.67 | 5929 | True | 52.73 | 5016 | 5016 | 6.78 | 7096 | 3 | 3297 |
| B 3500 m + ORC 2 MW | 40.85 | 5938 | True | 55.73 | 4773 | 2386 | 6.58 | 6969 | 14 | 3266 |
| B 3500 m + ORC 3 MW | 43.32 | 5540 | True | 58.73 | 3498 | 1166 | 6.51 | 5976 | 16 | 2886 |
| B 4000 m (no ORC) | 40.47 | 4094 | True | 53.73 | 0 | 0 | 0.0 | 3503 | 21 | 457 |
| B 4000 m + ORC 1 MW | 40.95 | 6098 | True | 56.73 | 6759 | 6759 | 8.33 | 8026 | 4 | 4185 |
| B 4000 m + ORC 2 MW | 43.08 | 6605 | True | 59.73 | 7887 | 3944 | 8.22 | 9019 | 13 | 5002 |
| B 4000 m + ORC 3 MW | 45.38 | 6455 | True | 62.73 | 7045 | 2348 | 7.92 | 8476 | 17 | 4663 |
| B 4500 m (no ORC) | 43.27 | 4091 | True | 57.73 | 0 | 0 | 0.0 | 3558 | 21 | 443 |
| B 4500 m + ORC 1 MW | 43.32 | 6016 | True | 60.73 | 7624 | 7624 | 9.63 | 8190 | 3 | 4741 |
| B 4500 m + ORC 2 MW | 45.29 | 6882 | True | 63.73 | 10224 | 5112 | 9.64 | 10249 | 9 | 6358 |
| B 4500 m + ORC 3 MW | 47.59 | 6897 | True | 66.73 | 9788 | 3263 | 9.4 | 10071 | 16 | 6257 |
| C 3500 m + ORC 1 MW, export at import price (120) | 37.05 | 6460 | True | 52.73 | 6404 | 6404 | 7.04 | 8560 | 2 | 3830 |
| C 3500 m no ORC, export at import price (120) | 37.46 | 4086 | True | 49.73 | 0 | 0 | 0.0 | 3440 | 18 | 478 |
| C 3500 m + ORC 1 MW, ORC cost 2,000 EUR/kW | 37.98 | 5929 | True | 51.73 | 5016 | 5016 | 6.78 | 7096 | 3 | 3297 |
| C 3500 m no ORC, ORC cost 2,000 EUR/kW | 37.67 | 4080 | True | 49.73 | 0 | 0 | 0.0 | 3438 | 18 | 473 |
| C 3500 m + ORC 1 MW, ORC second-law fraction 0.54 | 38.07 | 6170 | True | 52.73 | 7078 | 7078 | 8.4 | 8122 | 0 | 4438 |
| C 3500 m no ORC, ORC second-law fraction 0.54 | 37.67 | 4080 | True | 49.73 | 0 | 0 | 0.0 | 3438 | 18 | 473 |
| C 3500 m + ORC 1 MW, all three above | 35.36 | 6318 | True | 51.73 | 7519 | 7519 | 8.46 | 8569 | 0 | 4602 |
| C 3500 m no ORC, all three above | 37.46 | 4086 | True | 49.73 | 0 | 0 | 0.0 | 3440 | 18 | 478 |
| C pick + ORC 1 MW, export at import price (120) | 35.58 | 6306 | True | 49.53 | 4832 | 4832 | 5.74 | 7665 | 12 | 3088 |
| C pick + ORC 1 MW, ORC cost 2,000 EUR/kW | 36.17 | 5696 | True | 48.53 | 3513 | 3513 | 5.45 | 6232 | 12 | 2504 |
| C pick + ORC 1 MW, ORC second-law fraction 0.54 | 36.4 | 6031 | True | 49.53 | 5301 | 5301 | 6.8 | 7285 | 3 | 3464 |
| C pick + ORC 1 MW, all three above | 34.02 | 6524 | True | 48.53 | 6608 | 6608 | 7.05 | 8650 | 2 | 3971 |
| C pick, all three above (no ORC) | 35.58 | 4392 | True | 46.53 | 0 | 0 | 0.0 | 3733 | 27 | 315 |
| D 3 doublets at 4500 m + ORC 2 MW | 59.4 | 8756 | True | 88.27 | 17223 | 8611 | 10.05 | 11528 | 0 | 13911 |
| D 3 doublets at 4500 m + ORC 4 MW | 63.57 | 10680 | True | 94.27 | 23184 | 5796 | 9.91 | 17258 | 0 | 16350 |
| D 3 doublets at 4500 m (no ORC) | 59.11 | 4004 | True | 82.27 | 0 | 0 | 0.0 | 2515 | 4 | 871 |
