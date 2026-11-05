# New design levers on the pick, KNMI 2025 (run_pick_levers.py)

Author: Sa'eed Telvari

| case | gate | rules | LCOE | CO₂ t | CAPEX M€ |
|---|---|---|---|---|---|
| pick | pass | yes | 35.98 | 4,617 | 46.53 |
| pick, cooling return 30 °C | pass | yes | **35.53** | **4,394** | 46.99 |
| pick, heating return 45 °C, cooling 28 °C | pass | yes | 35.69 | 4,509 | 46.63 |
| pick, ESP sized 250 m³/h, VSD | pass | yes | 35.98 | 4,687 | 46.29 |
| pick, ESP 250, fixed speed | pass | yes | 37.27 | 4,998 | 46.18 |
| pick, ESP 300, VSD | pass | yes | 36.18 | 4,650 | 46.59 |
| pick, 2 boiler units | pass | yes | 36.50 | 4,617 | 47.29 |
| pick, 3 boiler units | pass | yes | 36.89 | 4,590 | 47.82 |
| pick, ESP 250 VSD, 2 units, returns 45/30 | pass | yes | 36.04 | 4,449 | 47.42 |
| 2D screw (cheapest in the screen) | pass | yes | 35.19 | 5,143 | 43.38 |
| 2D screw, ESP 250 VSD, 2 units, returns 45/30 | pass | yes | 35.56 | 5,102 | 43.95 |
| DeepSeek B1: 1D-3040 screw, 2 units, returns 45/28 | pass | yes | 35.52 | 10,260 | 24.87 |
| GLM B1: 2D-3050 screw, ESP 250, cooling return 30 | pass | yes | 36.60 | 6,177 | 42.95 |

