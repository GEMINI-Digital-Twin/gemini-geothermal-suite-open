# Full design screen, weather: NLD_Amsterdam.062400_IWEC.epw

Basis: whole geothermal source down 35 days in the lowest-load window, corrosion mitigation priced, ledger prices (CO2 at the ledger price is inside the LCOE).

600 designs run, 540 meet every hard rule.

## Failures by cooling option

| cooling option | run | fail |
|---|---|---|
| absorption | 60 | 60 |
| legacy electric | 60 | 0 |
| screw + dry cooler | 60 | 0 |
| centrifugal + tower | 60 | 0 |
| air-cooled screw | 60 | 0 |
| legacy + free cooling | 60 | 0 |
| screw + free cooling | 60 | 0 |
| tower + free cooling | 60 | 0 |
| air-cooled + free cooling | 60 | 0 |
| air-cooled + free cooling + ATES x3 | 60 | 0 |

## 15 cheapest that meet every rule

| design | lcoe_eur_per_mwh | co2_t_per_year | capex_meur |
|---|---|---|---|
| 1D-3100m-boiler-electric-chp-aircooled-fc-ates3 | 33.19 | 9072 | 26.39 |
| 1D-3100m-boiler-electric-chp-aircooled-fc | 33.73 | 9515 | 24.94 |
| 1D-2800m-boiler-electric-chp-aircooled-fc-ates3 | 33.76 | 9488 | 25.19 |
| 1D-3100m-boiler-electric-chp-screw-fc | 33.87 | 9456 | 25.44 |
| 1D-3400m-boiler-electric-chp-aircooled-fc-ates3 | 33.95 | 8953 | 27.59 |
| 1D-3100m-boiler-electric-chp-tower-fc | 34.06 | 9361 | 25.73 |
| 1D-3100m-boiler-electric-chp-fc | 34.29 | 9575 | 25.44 |
| 1D-3100m-boiler-electric-chp-aircooled | 34.3 | 9868 | 23.94 |
| 1D-2800m-boiler-electric-aircooled-fc-ates3 | 34.3 | 9507 | 24.65 |
| 1D-2800m-boiler-electric-chp-aircooled-fc | 34.33 | 9928 | 23.74 |
| 1D-3100m-boiler-electric-chp-screw | 34.37 | 9791 | 24.44 |
| 1D-2800m-boiler-electric-chp-screw-fc | 34.47 | 9869 | 24.24 |
| 1D-3400m-boiler-electric-chp-aircooled-fc | 34.48 | 9376 | 26.14 |
| 1D-3100m-boiler-electric-chp-tower | 34.58 | 9633 | 24.73 |
| 1D-3400m-boiler-electric-chp-screw-fc | 34.62 | 9317 | 26.64 |

## Cheapest per cooling option and doublet count (rules met)

| cooling option | doublets | design | lcoe_eur_per_mwh | co2_t_per_year |
|---|---|---|---|---|
| air-cooled + free cooling + ATES x3 | 1 | 1D-3100m-boiler-electric-chp-aircooled-fc-ates3 | 33.19 | 9072 |
| air-cooled + free cooling | 1 | 1D-3100m-boiler-electric-chp-aircooled-fc | 33.73 | 9515 |
| screw + free cooling | 1 | 1D-3100m-boiler-electric-chp-screw-fc | 33.87 | 9456 |
| tower + free cooling | 1 | 1D-3100m-boiler-electric-chp-tower-fc | 34.06 | 9361 |
| legacy + free cooling | 1 | 1D-3100m-boiler-electric-chp-fc | 34.29 | 9575 |
| air-cooled screw | 1 | 1D-3100m-boiler-electric-chp-aircooled | 34.3 | 9868 |
| screw + dry cooler | 1 | 1D-3100m-boiler-electric-chp-screw | 34.37 | 9791 |
| centrifugal + tower | 1 | 1D-3100m-boiler-electric-chp-tower | 34.58 | 9633 |
| legacy electric | 1 | 1D-3100m-boiler-electric-chp | 35.04 | 9979 |
| air-cooled + free cooling + ATES x3 | 2 | 2D-3100m-boiler-electric-chp-aircooled-fc-ates3 | 35.05 | 4429 |
| air-cooled + free cooling | 2 | 2D-3100m-boiler-electric-chp-aircooled-fc | 35.64 | 5053 |
| screw + free cooling | 2 | 2D-3100m-boiler-electric-chp-screw-fc | 35.77 | 4995 |
| tower + free cooling | 2 | 2D-3100m-boiler-electric-chp-tower-fc | 35.96 | 4899 |
| air-cooled screw | 2 | 2D-3100m-boiler-electric-chp-aircooled | 36.16 | 5423 |
| legacy + free cooling | 2 | 2D-3100m-boiler-electric-chp-fc | 36.19 | 5116 |
| screw + dry cooler | 2 | 2D-3100m-boiler-electric-chp-screw | 36.23 | 5348 |
| centrifugal + tower | 2 | 2D-3100m-boiler-electric-chp-tower | 36.44 | 5189 |
| legacy electric | 2 | 2D-3100m-boiler-electric-chp | 36.89 | 5537 |
| air-cooled + free cooling + ATES x3 | 3 | 3D-3100m-boiler-electric-chp-aircooled-fc-ates3 | 47.42 | 4365 |
| air-cooled + free cooling | 3 | 3D-3100m-boiler-electric-chp-aircooled-fc | 48.23 | 5261 |
| screw + free cooling | 3 | 3D-3100m-boiler-electric-chp-screw-fc | 48.37 | 5204 |
| tower + free cooling | 3 | 3D-3100m-boiler-electric-chp-tower-fc | 48.55 | 5108 |
| air-cooled screw | 3 | 3D-3100m-boiler-electric-chp-aircooled | 48.76 | 5672 |
| legacy + free cooling | 3 | 3D-3100m-boiler-electric-chp-fc | 48.79 | 5325 |
| screw + dry cooler | 3 | 3D-3100m-boiler-electric-chp-screw | 48.82 | 5596 |
| centrifugal + tower | 3 | 3D-3100m-boiler-electric-chp-tower | 49.04 | 5438 |
| legacy electric | 3 | 3D-3100m-boiler-electric-chp | 49.48 | 5786 |

## 10 lowest CO2 that meet every rule

| design | lcoe_eur_per_mwh | co2_t_per_year | capex_meur |
|---|---|---|---|
| 3D-4000m-boiler-electric-chp-aircooled-fc-ates3 | 54.37 | 4152 | 75.07 |
| 3D-4000m-heat_pump-electric-chp-aircooled-fc-ates3 | 59.16 | 4152 | 82.07 |
| 3D-3400m-boiler-electric-chp-aircooled-fc-ates3 | 49.44 | 4153 | 67.87 |
| 3D-3400m-heat_pump-electric-chp-aircooled-fc-ates3 | 54.23 | 4155 | 74.87 |
| 2D-3400m-boiler-electric-chp-aircooled-fc-ates3 | 36.49 | 4293 | 47.73 |
| 2D-3400m-heat_pump-electric-chp-aircooled-fc-ates3 | 41.28 | 4295 | 54.73 |
| 2D-4000m-boiler-electric-chp-aircooled-fc-ates3 | 39.84 | 4303 | 52.53 |
| 2D-4000m-heat_pump-electric-chp-aircooled-fc-ates3 | 44.63 | 4303 | 59.53 |
| 3D-3100m-boiler-electric-chp-aircooled-fc-ates3 | 47.42 | 4365 | 64.27 |
| 2D-3100m-boiler-electric-chp-aircooled-fc-ates3 | 35.05 | 4429 | 45.33 |
