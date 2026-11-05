# Full design screen, weather: knmi_etmgeg_240_1991_2025.txt (2025)

Basis: each doublet down 35 days at its own time (staggered, lowest-load windows), corrosion mitigation priced, ledger prices (CO2 at the ledger price is inside the LCOE).

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
| 2D-3100m-boiler-electric-chp-screw | 35.19 | 5143 | 43.38 |
| 2D-3100m-boiler-electric-chp-aircooled | 35.25 | 5255 | 42.88 |
| 1D-3100m-boiler-electric-chp-screw | 35.33 | 10476 | 24.44 |
| 1D-3100m-boiler-electric-chp-aircooled | 35.38 | 10594 | 23.94 |
| 2D-3100m-boiler-electric-chp-tower | 35.42 | 4972 | 43.67 |
| 2D-3100m-boiler-electric-chp-screw-fc | 35.45 | 4982 | 44.38 |
| 2D-3100m-boiler-electric-chp-aircooled-fc | 35.48 | 5087 | 43.88 |
| 1D-3100m-boiler-electric-chp-screw-fc | 35.55 | 10333 | 25.44 |
| 1D-3100m-boiler-electric-chp-tower | 35.56 | 10313 | 24.73 |
| 1D-3100m-boiler-electric-chp-aircooled-fc | 35.58 | 10441 | 24.94 |
| 2D-3100m-boiler-electric-chp-tower-fc | 35.67 | 4839 | 44.67 |
| 2D-3100m-boiler-electric-chp-aircooled-fc-ates3 | 35.77 | 4617 | 46.23 |
| 1D-3100m-boiler-electric-chp-tower-fc | 35.77 | 10197 | 25.73 |
| 1D-3100m-boiler-electric-chp-aircooled-fc-ates3 | 35.91 | 10021 | 27.29 |
| 2D-3100m-boiler-electric-chp | 35.96 | 5378 | 43.38 |

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
| air-cooled + free cooling + ATES x3 | 2 | 2D-3100m-boiler-electric-chp-aircooled-fc-ates3 | 35.77 | 4617 |
| tower + free cooling | 1 | 1D-3100m-boiler-electric-chp-tower-fc | 35.77 | 10197 |
| air-cooled + free cooling + ATES x3 | 1 | 1D-3100m-boiler-electric-chp-aircooled-fc-ates3 | 35.91 | 10021 |
| legacy electric | 2 | 2D-3100m-boiler-electric-chp | 35.96 | 5378 |
| legacy electric | 1 | 1D-3100m-boiler-electric-chp | 36.11 | 10711 |
| legacy + free cooling | 2 | 2D-3100m-boiler-electric-chp-fc | 36.14 | 5191 |
| legacy + free cooling | 1 | 1D-3100m-boiler-electric-chp-fc | 36.24 | 10539 |
| screw + dry cooler | 3 | 3D-3100m-boiler-electric-chp-screw | 47.74 | 5215 |
| air-cooled screw | 3 | 3D-3100m-boiler-electric-chp-aircooled | 47.8 | 5327 |
| centrifugal + tower | 3 | 3D-3100m-boiler-electric-chp-tower | 47.98 | 5044 |
| screw + free cooling | 3 | 3D-3100m-boiler-electric-chp-screw-fc | 48.01 | 5055 |
| air-cooled + free cooling | 3 | 3D-3100m-boiler-electric-chp-aircooled-fc | 48.03 | 5159 |
| air-cooled + free cooling + ATES x3 | 3 | 3D-3100m-boiler-electric-chp-aircooled-fc-ates3 | 48.1 | 4595 |
| tower + free cooling | 3 | 3D-3100m-boiler-electric-chp-tower-fc | 48.22 | 4912 |
| legacy electric | 3 | 3D-3100m-boiler-electric-chp | 48.52 | 5451 |
| legacy + free cooling | 3 | 3D-3100m-boiler-electric-chp-fc | 48.69 | 5264 |

## 10 lowest CO2 that meet every rule

| design | lcoe_eur_per_mwh | co2_t_per_year | capex_meur |
|---|---|---|---|
| 3D-4000m-boiler-electric-chp-aircooled-fc-ates3 | 54.74 | 4003 | 75.97 |
| 3D-4000m-heat_pump-electric-chp-aircooled-fc-ates3 | 59.53 | 4003 | 82.97 |
| 3D-3400m-boiler-electric-chp-aircooled-fc-ates3 | 49.8 | 4058 | 68.77 |
| 3D-3400m-heat_pump-electric-chp-aircooled-fc-ates3 | 54.59 | 4061 | 75.77 |
| 2D-4000m-boiler-electric-chp-aircooled-fc-ates3 | 40.35 | 4091 | 53.43 |
| 2D-4000m-heat_pump-electric-chp-aircooled-fc-ates3 | 45.14 | 4091 | 60.43 |
| 2D-3400m-boiler-electric-chp-aircooled-fc-ates3 | 36.99 | 4107 | 48.63 |
| 2D-3400m-heat_pump-electric-chp-aircooled-fc-ates3 | 41.78 | 4108 | 55.63 |
| 2D-4000m-heat_pump-electric-chp-tower-fc | 44.98 | 4266 | 58.87 |
| 2D-4000m-boiler-electric-chp-tower-fc | 40.19 | 4266 | 51.87 |
