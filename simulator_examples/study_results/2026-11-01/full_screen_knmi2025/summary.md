# Full design screen, weather: KNMI Schiphol etmgeg 240, 1991-2025 file (year 2025)

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
| 1D-3100m-boiler-electric-chp-screw | 34.39 | 9796 | 24.44 |
| 1D-3100m-boiler-electric-chp-aircooled | 34.47 | 9914 | 23.94 |
| 1D-3100m-boiler-electric-chp-screw-fc | 34.57 | 9653 | 25.44 |
| 1D-3100m-boiler-electric-chp-tower | 34.58 | 9633 | 24.73 |
| 1D-3100m-boiler-electric-chp-aircooled-fc | 34.61 | 9761 | 24.94 |
| 1D-3100m-boiler-electric-chp-aircooled-fc-ates3 | 34.71 | 9331 | 27.29 |
| 1D-3100m-boiler-electric-chp-tower-fc | 34.75 | 9517 | 25.73 |
| 1D-2800m-boiler-electric-chp-screw | 34.99 | 10210 | 23.24 |
| 1D-2800m-boiler-electric-chp-aircooled | 35.07 | 10329 | 22.74 |
| 1D-3400m-boiler-electric-chp-screw | 35.14 | 9656 | 25.64 |
| 1D-2800m-boiler-electric-chp-screw-fc | 35.17 | 10066 | 24.24 |
| 1D-2800m-boiler-electric-chp-tower | 35.18 | 10048 | 23.53 |
| 1D-2800m-boiler-electric-chp-aircooled-fc | 35.21 | 10175 | 23.74 |
| 1D-3400m-boiler-electric-chp-aircooled | 35.22 | 9775 | 25.14 |
| 1D-3100m-boiler-electric-chp | 35.22 | 10031 | 24.44 |

## Cheapest per cooling option and doublet count (rules met)

| cooling option | doublets | design | lcoe_eur_per_mwh | co2_t_per_year |
|---|---|---|---|---|
| screw + dry cooler | 1 | 1D-3100m-boiler-electric-chp-screw | 34.39 | 9796 |
| air-cooled screw | 1 | 1D-3100m-boiler-electric-chp-aircooled | 34.47 | 9914 |
| screw + free cooling | 1 | 1D-3100m-boiler-electric-chp-screw-fc | 34.57 | 9653 |
| centrifugal + tower | 1 | 1D-3100m-boiler-electric-chp-tower | 34.58 | 9633 |
| air-cooled + free cooling | 1 | 1D-3100m-boiler-electric-chp-aircooled-fc | 34.61 | 9761 |
| air-cooled + free cooling + ATES x3 | 1 | 1D-3100m-boiler-electric-chp-aircooled-fc-ates3 | 34.71 | 9331 |
| tower + free cooling | 1 | 1D-3100m-boiler-electric-chp-tower-fc | 34.75 | 9517 |
| legacy electric | 1 | 1D-3100m-boiler-electric-chp | 35.22 | 10031 |
| legacy + free cooling | 1 | 1D-3100m-boiler-electric-chp-fc | 35.3 | 9859 |
| screw + dry cooler | 2 | 2D-3100m-boiler-electric-chp-screw | 36.25 | 5353 |
| air-cooled screw | 2 | 2D-3100m-boiler-electric-chp-aircooled | 36.33 | 5469 |
| centrifugal + tower | 2 | 2D-3100m-boiler-electric-chp-tower | 36.44 | 5189 |
| screw + free cooling | 2 | 2D-3100m-boiler-electric-chp-screw-fc | 36.46 | 5199 |
| air-cooled + free cooling | 2 | 2D-3100m-boiler-electric-chp-aircooled-fc | 36.5 | 5307 |
| air-cooled + free cooling + ATES x3 | 2 | 2D-3100m-boiler-electric-chp-aircooled-fc-ates3 | 36.57 | 4790 |
| tower + free cooling | 2 | 2D-3100m-boiler-electric-chp-tower-fc | 36.65 | 5064 |
| legacy electric | 2 | 2D-3100m-boiler-electric-chp | 37.07 | 5589 |
| legacy + free cooling | 2 | 2D-3100m-boiler-electric-chp-fc | 37.19 | 5406 |
| screw + dry cooler | 3 | 3D-3100m-boiler-electric-chp-screw | 48.84 | 5601 |
| air-cooled screw | 3 | 3D-3100m-boiler-electric-chp-aircooled | 48.92 | 5718 |
| air-cooled + free cooling + ATES x3 | 3 | 3D-3100m-boiler-electric-chp-aircooled-fc-ates3 | 48.94 | 4851 |
| centrifugal + tower | 3 | 3D-3100m-boiler-electric-chp-tower | 49.04 | 5438 |
| screw + free cooling | 3 | 3D-3100m-boiler-electric-chp-screw-fc | 49.06 | 5445 |
| air-cooled + free cooling | 3 | 3D-3100m-boiler-electric-chp-aircooled-fc | 49.1 | 5539 |
| tower + free cooling | 3 | 3D-3100m-boiler-electric-chp-tower-fc | 49.24 | 5297 |
| legacy electric | 3 | 3D-3100m-boiler-electric-chp | 49.67 | 5838 |
| legacy + free cooling | 3 | 3D-3100m-boiler-electric-chp-fc | 49.78 | 5651 |

## 10 lowest CO2 that meet every rule

| design | lcoe_eur_per_mwh | co2_t_per_year | capex_meur |
|---|---|---|---|
| 3D-4000m-heat_pump-electric-chp-aircooled-fc-ates3 | 60.66 | 4536 | 82.97 |
| 3D-4000m-boiler-electric-chp-aircooled-fc-ates3 | 55.88 | 4536 | 75.97 |
| 3D-3400m-boiler-electric-chp-aircooled-fc-ates3 | 50.94 | 4566 | 68.77 |
| 3D-3400m-heat_pump-electric-chp-aircooled-fc-ates3 | 55.73 | 4569 | 75.77 |
| 2D-4000m-heat_pump-electric-chp-aircooled-fc-ates3 | 46.14 | 4595 | 60.43 |
| 2D-4000m-boiler-electric-chp-aircooled-fc-ates3 | 41.35 | 4595 | 53.43 |
| 2D-3400m-boiler-electric-chp-aircooled-fc-ates3 | 38.0 | 4602 | 48.63 |
| 2D-3400m-heat_pump-electric-chp-aircooled-fc-ates3 | 42.79 | 4604 | 55.63 |
| 3D-3100m-heat_pump-electric-chp-aircooled-fc-ates3 | 53.75 | 4756 | 72.17 |
| 2D-3100m-heat_pump-electric-chp-aircooled-fc-ates3 | 41.36 | 4783 | 53.23 |
