# Full design screen, weather: knmi_etmgeg_240_1991_2025.txt (2025)

Basis: each doublet down 35 days at its own time (staggered, lowest-load windows), corrosion mitigation priced, ledger prices (CO2 at the ledger price is inside the LCOE).

720 designs run, 696 meet every hard rule.

## Failures by cooling option

| cooling option | run | fail |
|---|---|---|
| absorption | 72 | 24 |
| legacy electric | 72 | 0 |
| screw + dry cooler | 72 | 0 |
| centrifugal + tower | 72 | 0 |
| air-cooled screw | 72 | 0 |
| legacy + free cooling | 72 | 0 |
| screw + free cooling | 72 | 0 |
| tower + free cooling | 72 | 0 |
| air-cooled + free cooling | 72 | 0 |
| air-cooled + free cooling + ATES x3 | 72 | 0 |

## 15 cheapest that meet every rule

| design | lcoe_eur_per_mwh | co2_t_per_year | capex_meur |
|---|---|---|---|
| 2D-3100m-boiler-electric-chp-screw | 35.19 | 5143 | 43.38 |
| 2D-3100m-boiler-electric-chp-aircooled | 35.25 | 5255 | 42.88 |
| 2D-3200m-boiler-electric-chp-screw | 35.26 | 4746 | 44.18 |
| 2D-3200m-boiler-electric-chp-aircooled | 35.32 | 4867 | 43.68 |
| 1D-3100m-boiler-electric-chp-screw | 35.33 | 10476 | 24.44 |
| 1D-3100m-boiler-electric-chp-aircooled | 35.38 | 10594 | 23.94 |
| 1D-3200m-boiler-electric-chp-screw | 35.42 | 10220 | 24.84 |
| 2D-3100m-boiler-electric-chp-tower | 35.42 | 4972 | 43.67 |
| 2D-3100m-boiler-electric-chp-screw-fc | 35.45 | 4982 | 44.38 |
| 1D-3200m-boiler-electric-chp-aircooled | 35.47 | 10338 | 24.34 |
| 2D-3100m-boiler-electric-chp-aircooled-fc | 35.48 | 5087 | 43.88 |
| 2D-3200m-boiler-electric-chp-tower | 35.5 | 4589 | 44.47 |
| 1D-3100m-boiler-electric-chp-screw-fc | 35.55 | 10333 | 25.44 |
| 2D-3200m-boiler-electric-chp-screw-fc | 35.56 | 4623 | 45.18 |
| 1D-3100m-boiler-electric-chp-tower | 35.56 | 10313 | 24.73 |

## Cheapest per cooling option and doublet count (rules met)

| cooling option | doublets | design | lcoe_eur_per_mwh | co2_t_per_year |
|---|---|---|---|---|
| screw + dry cooler | 2 | 2D-3100m-boiler-electric-chp-screw | 35.19 | 5143 |
| air-cooled screw | 2 | 2D-3100m-boiler-electric-chp-aircooled | 35.25 | 5255 |
| screw + dry cooler | 1 | 1D-3100m-boiler-electric-chp-screw | 35.33 | 10476 |
| air-cooled screw | 1 | 1D-3100m-boiler-electric-chp-aircooled | 35.38 | 10594 |
| centrifugal + tower | 2 | 2D-3100m-boiler-electric-chp-tower | 35.42 | 4972 |
| screw + free cooling | 2 | 2D-3100m-boiler-electric-chp-screw-fc | 35.45 | 4982 |
| air-cooled + free cooling | 2 | 2D-3100m-boiler-electric-chp-aircooled-fc | 35.48 | 5087 |
| screw + free cooling | 1 | 1D-3100m-boiler-electric-chp-screw-fc | 35.55 | 10333 |
| centrifugal + tower | 1 | 1D-3100m-boiler-electric-chp-tower | 35.56 | 10313 |
| air-cooled + free cooling | 1 | 1D-3100m-boiler-electric-chp-aircooled-fc | 35.58 | 10441 |
| tower + free cooling | 2 | 2D-3100m-boiler-electric-chp-tower-fc | 35.67 | 4839 |
| tower + free cooling | 1 | 1D-3100m-boiler-electric-chp-tower-fc | 35.77 | 10197 |
| legacy electric | 2 | 2D-3100m-boiler-electric-chp | 35.96 | 5378 |
| air-cooled + free cooling + ATES x3 | 2 | 2D-3100m-boiler-electric-chp-aircooled-fc-ates3 | 35.99 | 4619 |
| legacy electric | 1 | 1D-3100m-boiler-electric-chp | 36.11 | 10711 |
| air-cooled + free cooling + ATES x3 | 1 | 1D-3100m-boiler-electric-chp-aircooled-fc-ates3 | 36.13 | 10023 |
| legacy + free cooling | 2 | 2D-3100m-boiler-electric-chp-fc | 36.14 | 5191 |
| legacy + free cooling | 1 | 1D-3100m-boiler-electric-chp-fc | 36.24 | 10539 |
| absorption | 2 | 2D-3200m-boiler-absorption-chp | 38.53 | 6339 |
| screw + dry cooler | 3 | 3D-3100m-boiler-electric-chp-screw | 47.74 | 5215 |
| air-cooled screw | 3 | 3D-3100m-boiler-electric-chp-aircooled | 47.8 | 5327 |
| centrifugal + tower | 3 | 3D-3100m-boiler-electric-chp-tower | 47.98 | 5044 |
| screw + free cooling | 3 | 3D-3100m-boiler-electric-chp-screw-fc | 48.01 | 5055 |
| air-cooled + free cooling | 3 | 3D-3100m-boiler-electric-chp-aircooled-fc | 48.03 | 5159 |
| tower + free cooling | 3 | 3D-3100m-boiler-electric-chp-tower-fc | 48.22 | 4912 |
| air-cooled + free cooling + ATES x3 | 3 | 3D-3100m-boiler-electric-chp-aircooled-fc-ates3 | 48.31 | 4597 |
| legacy electric | 3 | 3D-3100m-boiler-electric-chp | 48.52 | 5451 |
| legacy + free cooling | 3 | 3D-3100m-boiler-electric-chp-fc | 48.69 | 5264 |
| absorption | 3 | 3D-3100m-boiler-absorption-chp | 50.27 | 6679 |

## 10 lowest CO2 that meet every rule

| design | lcoe_eur_per_mwh | co2_t_per_year | capex_meur |
|---|---|---|---|
| 3D-4000m-boiler-electric-chp-aircooled-fc-ates3 | 54.96 | 4007 | 76.27 |
| 3D-4000m-heat_pump-electric-chp-aircooled-fc-ates3 | 59.74 | 4007 | 83.27 |
| 3D-3400m-boiler-electric-chp-aircooled-fc-ates3 | 50.02 | 4061 | 69.07 |
| 3D-3400m-heat_pump-electric-chp-aircooled-fc-ates3 | 54.8 | 4063 | 76.07 |
| 2D-4000m-heat_pump-electric-chp-aircooled-fc-ates3 | 45.35 | 4093 | 60.73 |
| 2D-4000m-boiler-electric-chp-aircooled-fc-ates3 | 40.56 | 4093 | 53.73 |
| 2D-3400m-boiler-electric-chp-aircooled-fc-ates3 | 37.2 | 4109 | 48.93 |
| 2D-3400m-heat_pump-electric-chp-aircooled-fc-ates3 | 41.99 | 4110 | 55.93 |
| 3D-3200m-heat_pump-electric-chp-aircooled-fc-ates3 | 53.25 | 4226 | 73.67 |
| 3D-3200m-boiler-electric-chp-aircooled-fc-ates3 | 48.47 | 4229 | 66.67 |
