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
| 2D-3100m-boiler-electric-chp-screw | 35.18 | 4875 | 43.38 |
| 1D-2800m-boiler-electric-chp-tower | 35.18 | 10048 | 23.53 |
| 1D-2800m-boiler-electric-chp-aircooled-fc | 35.21 | 10175 | 23.74 |
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
| screw + dry cooler | 2 | 2D-3100m-boiler-electric-chp-screw | 35.18 | 4875 |
| legacy electric | 1 | 1D-3100m-boiler-electric-chp | 35.22 | 10031 |
| air-cooled screw | 2 | 2D-3100m-boiler-electric-chp-aircooled | 35.26 | 4992 |
| legacy + free cooling | 1 | 1D-3100m-boiler-electric-chp-fc | 35.3 | 9859 |
| centrifugal + tower | 2 | 2D-3100m-boiler-electric-chp-tower | 35.38 | 4712 |
| screw + free cooling | 2 | 2D-3100m-boiler-electric-chp-screw-fc | 35.4 | 4722 |
| air-cooled + free cooling | 2 | 2D-3100m-boiler-electric-chp-aircooled-fc | 35.44 | 4830 |
| air-cooled + free cooling + ATES x3 | 2 | 2D-3100m-boiler-electric-chp-aircooled-fc-ates3 | 35.51 | 4345 |
| tower + free cooling | 2 | 2D-3100m-boiler-electric-chp-tower-fc | 35.59 | 4587 |
| legacy electric | 2 | 2D-3100m-boiler-electric-chp | 36.01 | 5112 |
| legacy + free cooling | 2 | 2D-3100m-boiler-electric-chp-fc | 36.13 | 4928 |
| screw + dry cooler | 3 | 3D-3100m-boiler-electric-chp-screw | 47.78 | 5138 |
| air-cooled screw | 3 | 3D-3100m-boiler-electric-chp-aircooled | 47.86 | 5255 |
| air-cooled + free cooling + ATES x3 | 3 | 3D-3100m-boiler-electric-chp-aircooled-fc-ates3 | 47.88 | 4450 |
| centrifugal + tower | 3 | 3D-3100m-boiler-electric-chp-tower | 47.98 | 4974 |
| screw + free cooling | 3 | 3D-3100m-boiler-electric-chp-screw-fc | 48.0 | 4984 |
| air-cooled + free cooling | 3 | 3D-3100m-boiler-electric-chp-aircooled-fc | 48.04 | 5085 |
| tower + free cooling | 3 | 3D-3100m-boiler-electric-chp-tower-fc | 48.18 | 4843 |
| legacy electric | 3 | 3D-3100m-boiler-electric-chp | 48.61 | 5374 |
| legacy + free cooling | 3 | 3D-3100m-boiler-electric-chp-fc | 48.72 | 5191 |

## 10 lowest CO2 that meet every rule

| design | lcoe_eur_per_mwh | co2_t_per_year | capex_meur |
|---|---|---|---|
| 3D-4000m-boiler-electric-chp-aircooled-fc-ates3 | 54.78 | 4041 | 75.97 |
| 3D-4000m-heat_pump-electric-chp-aircooled-fc-ates3 | 59.57 | 4041 | 82.97 |
| 3D-3400m-boiler-electric-chp-aircooled-fc-ates3 | 49.84 | 4080 | 68.77 |
| 3D-3400m-heat_pump-electric-chp-aircooled-fc-ates3 | 54.63 | 4082 | 75.77 |
| 2D-4000m-boiler-electric-chp-aircooled-fc-ates3 | 40.26 | 4094 | 53.43 |
| 2D-4000m-heat_pump-electric-chp-aircooled-fc-ates3 | 45.05 | 4094 | 60.43 |
| 2D-3400m-boiler-electric-chp-aircooled-fc-ates3 | 36.91 | 4102 | 48.63 |
| 2D-3400m-heat_pump-electric-chp-aircooled-fc-ates3 | 41.7 | 4104 | 55.63 |
| 2D-4000m-heat_pump-electric-chp-tower-fc | 45.08 | 4275 | 58.87 |
| 2D-4000m-boiler-electric-chp-tower-fc | 40.29 | 4275 | 51.87 |
