# Full rerun on the new defaults (4 Nov 2026)

Author: Sa'eed Telvari

**What changed in the code.** From PR #30 (merge e0007ae), two options are on by default:
daily NL day-ahead electricity prices for 2025 (`electricity_daily_prices` = 1) and gas boiler
part-load losses (`boiler_part_load` = 1). PR #30 also adds an opt-in sized ESP, but that option
is off by default. Everything else is unchanged from the 2 Nov basis
(`../../2026-11-02/staggered_pick`): KNMI Schiphol 2025 weather, staggered 35-day doublet
stops, lined casing, a 33 MW boiler and the ledger prices.

All the runs below were made in a fresh workspace on e0007ae. Commands (with `PYTHONPATH=src`,
`OPENBLAS_NUM_THREADS=1` and W = `simulator_examples/weather/knmi_etmgeg_240_1991_2025.txt`):

    python simulator_examples/run_final_pick.py --knmi W --year 2025 --mc 400
    python simulator_examples/run_full_screen.py --knmi W --year 2025 --workers 4
    python simulator_examples/run_outage_study.py --knmi W --year 2025
    python simulator_examples/run_return_temperature_check.py --knmi W --year 2025
    python simulator_examples/run_weather_years.py --knmi W
    python simulator_examples/run_shallow_wells.py --knmi W
    python simulator_examples/run_pit_store_study.py --knmi W
    python simulator_examples/run_store_vs_doublet.py --knmi W
    python simulator_examples/run_orc_study.py              (writes into 2026-11-03/orc; copied here)
    PYTHONPATH=src:simulator_examples python simulator_examples/run_pick_levers.py <ws>
    PYTHONPATH=src:simulator_examples python docs/figures/make_compliance_figure.py
    python docs/figures/make_depth_figure.py

`run_thermogis_crosscheck.py` was not rerun, because it needs pyThermoGIS, which is only on
Sa'eed's PC. It checks the well model, which these defaults do not touch.

## Headline: the pick (final_pick/)

The pick is the same design: 2 doublets at 3.1 km, CHP, a 33 MW boiler, an air-cooled chiller
with free cooling, 3 ATES pairs and a 9 MW backup chiller.

| | 2 Nov | **4 Nov (new defaults)** |
|---|---|---|
| LCOE | €35.71/MWh | **€35.98/MWh** |
| CO₂ | 4,345 t/yr | **4,617 t/yr** |
| CAPEX | €46.5 M | €46.5 M |
| Purchased gas | 27 MWh | 0 MWh |
| With doublet operating rules | €35.62, 4,202 t | €35.70, 4,255 t |
| 1 doublet, same plant | €34.91, 9,331 t | **€36.24, 10,080 t: 1 doublet is now dearer than 2** |
| Gas boiler + chiller reference | €59.3/MWh, 26.4 kt | €60.7/MWh, 27.1 kt |
| Pick against the reference | 40% cheaper, 84% less CO₂, payback 6.6 yr, NPV €44.0 M | 41% cheaper, 83% less CO₂, payback 6.5 yr, NPV €46.1 M |
| Monte Carlo (400 samples, sourced prices) | P50 €36.5 (P10–P90 30.9–42.6), CO₂ P50 4.28 kt, 400/400 met | **P50 €37.6 (31.8–45.5), CO₂ P50 4.87 kt, 400/400 met** |
| Pick cheaper than the earlier pick (12 MW legacy chiller) | 96.5% of samples | 73% of samples (median −€0.24/MWh); lower CO₂ in 100% |
| Earlier pick meets cooling in the MC | | 97.75% of samples |
| Sourced base case | €31.55, 4.09 kt | €31.86, 4.45 kt |

Why CO₂ rises while purchased gas falls to zero: with the part-load losses on, the plant runs
more brine instead of the boiler at low load, and more brine brings more co-produced reservoir
gas, which is burnt in the CHP.

Tornado (LCOE swing, €/MWh): well cost 6.9, **temperature gradient 6.3 (was 3.1)**, discount
rate 6.1, permeability 5.0 (was 3.8), heating demand 3.2, surface CAPEX 2.8. The gradient
matters more now: a cooler reservoir means more boiler hours, and those now run at part load.

## Full screen (full_screen/)

600 designs, 540 meet every rule. All 60 absorption designs fail, as before.

- **The cheapest design is now 2 doublets**: 2D screw + dry cooler, €35.19/MWh, 5,143 t
  (2 Nov: 1D screw + dry cooler at €34.39 was the cheapest). The best 1D is €35.33, 10,476 t.
- The ATES pick (with the screen's 30 MW boiler) costs €35.77 and emits 4,617 t. That is
  **€0.58/MWh more than 2D screw for 526 t less CO₂, about €149/t** on top of the €80/t already
  in the LCOE (2 Nov: €0.33/MWh for 530 t, about €84/t).

## Stress and outages (outage.md)

| Scenario | 2 Nov | 4 Nov |
|---|---|---|
| S1 staggered stops (headline) | 35.71 | 35.98 |
| S1c same with a 30 MW boiler | 35.51 | 35.77 |
| S2 whole source down in summer | 36.78 | 37.23 |
| S3 one doublet trips at the January peak | 39.74 | 40.19 |
| S4 both trip at the January peak | 45.24 | 45.54 (boiler 30.0 of 33 MW) |
| S5 S4 with heating +6% | 43.86 | 44.13 (31.8 of 33 MW) |
| S5b S5 with a 30 MW boiler | 98 MWh unmet | 97.6 MWh unmet |
| S6 whole-source outage on each of 331 start days | 331/331 met, 36.78–45.24 | 331/331 met, 37.23–45.54 |

The 33 MW boiler is still needed for S5.

## Weather years (years.md)

With the 9 MW backup chiller, all 35 KNMI years (1991–2025) still meet every rule:
€35.07–36.66, median €35.79 (was €34.78–36.59, median €35.58). A 6 MW backup chiller
still fails in 13 years.

## Return temperatures (return_temperatures.md)

Every value tested still meets every rule.

- **Heating return:** 40 °C costs €35.98/MWh. 45 °C costs €35.95 and 50 °C costs €35.97,
  so the curve is still flat from 40 to 50 °C.
- **Cooling return:** this is now worth more. A 30 °C cooling return costs €35.53/MWh and
  emits 4,394 t, compared with €35.98 and 4,617 t at our 26 °C (2 Nov: €35.33 against
  €36.05). 30 °C is the upper end the tool allows, 2 K below the 32 °C building return.

## New levers on the pick (levers.md)

Some of the B1 designs that agents found in the max-thinking benchmark were cheaper than the
benchmark's grid optimum on the official profiles. They used the new options (return
temperatures, a sized ESP, boiler units), so we checked those options here on KNMI 2025:

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

On KNMI 2025 none of the agents' B1 designs beats the plain 2D screw design. The only option
that helps the pick is a warmer cooling return. Extra boiler units do not pay for a plant that
hardly uses its boiler. A sized ESP gains nothing, and with a fixed-speed drive it costs
€1.3/MWh more.

## Other studies

- **Shallow wells + heat pump (shallow_wells/, docs/figures/fig_depth.png).** For the pick's
  plant (2D, CHP, ATES), the heat pump beats the boiler only at depths shallower than
  **about 2.7 km** (was about 2.6 km). At
  1.5 km with a heat pump it costs €53.5/MWh, against €35.8 at 3.1 km with a boiler.
- **Pit heat store (pit_store_study/).** 1D + 250,000 m³ at 10 MW costs €36.70 and emits
  8,091 t, against the pick's €35.98 and 4,617 t. On 2 Nov the two tied (€35.66 against
  €35.71). The store no longer ties the pick.
- **Store vs a 2nd doublet (store_vs_doublet/, Sol's energy-only store).** On our basis B,
  1D + 20 GWh costs €34.59 (was €34.29), 2D screw €35.19 and the pick €35.98. On Sol's basis A,
  1D + 37.5 GWh costs €43.57 (was €43.14).
- **ORC (orc/).** 0.5 MWe is close to break-even (+€0.04/MWh, +559 t). 1 MWe adds €1.04/MWh
  (2 Nov: €36.85 against €35.71, +€1.14). It still does not pay.

## Figures regenerated

`final_pick/fig_tornado_pick.png`, `full_screen/fig_full_screen.png`,
`docs/figures/fig_compliance.png`, `docs/figures/fig_depth.png`,
`docs/figures/system_workflow.svg/.png` (headline box: €36.0/MWh, 4,617 t). The year figure
(`deliverables/figures/make_pick_figures_staggered.py` on `final_pick/pick_daily.csv`) is in
the project folder as `fig_year_pick_newdefaults.png`.
