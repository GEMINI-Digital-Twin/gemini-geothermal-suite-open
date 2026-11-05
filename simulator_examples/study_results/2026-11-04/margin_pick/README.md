# Design margin after the external review (4 Nov 2026)

Author: Sa'eed Telvari

An external review (4 Nov) reproduced the 2–4 Nov headline exactly (2 doublets at 3.1 km, 9 MW
backup chiller: €35.98/MWh, 4,617 t) but found it was sized in-sample with almost no margin: the
zero-boiler year rested on a ~0.5 K wellhead margin above 100 °C, and the 9 MW backup chiller
missed cooling in warm years made 1–2 K warmer or with 10 % more cooling. Sa'eed approved buying
margin: **wells 3.1 → 3.2 km and backup chiller 9 → 10 MW**. Everything else is unchanged
(KNMI Schiphol 2025, staggered 35-day doublet stops, 33 MW boiler, lined casing, ledger prices,
daily power prices and boiler part load on).

Commands (`PYTHONPATH=src:simulator_examples`, `OPENBLAS_NUM_THREADS=1`,
W = `simulator_examples/weather/knmi_etmgeg_240_1991_2025.txt`), run in a 4-core container:

    python simulator_examples/run_full_screen.py --knmi W --year 2025 --workers 4
    python simulator_examples/run_stress_margin.py --knmi W
    python simulator_examples/run_final_pick.py --knmi W --year 2025 --mc 400 --mc-weather
    python simulator_examples/run_outage_study.py --knmi W --year 2025
    python simulator_examples/run_weather_years.py --knmi W --chillers 9 10
    python docs/figures/make_compliance_figure.py

## Answer

| | 2–4 Nov pick | **New pick (4 Nov)** |
|---|---|---|
| Design | 2 doublets 3.1 km, CHP, 33 MW boiler, air-cooled chiller 9 MW + free cooling + 3 ATES pairs | **same, wells at 3.2 km (108 °C, 320.7 bar), 10 MW backup chiller** |
| LCOE (KNMI 2025) | €35.98/MWh | **€36.35/MWh** |
| CO₂ | 4,617 t/yr | **4,269 t/yr** |
| CAPEX | €46.5 M | **€47.6 M** |
| Bought gas / boiler heat | 0 MWh | 0 MWh |
| Wellhead temperature, lowest running day | 100.6 °C | **100.8 °C**; 105.2 °C max |
| Stress tests met (13, `stress_margin/`) | 10 | **13** |
| KNMI years 1991–2025 met | 35/35 (median €35.79) | **35/35** (€35.45–37.02, median €36.15; CO₂ 3.9–4.6 kt) |
| Monte Carlo, 400 samples, weather year sampled too | met in 96.0 % (95 % CI 93.6–97.5 %) | **met in 99.0 % (95 % CI 97.5–99.6 %)**; P50 €37.4 (P10–P90 31.6–44.7), CO₂ P50 4.27 kt |
| Gas boiler + chiller reference (now on daily prices) | €60.7 → €60.43/MWh, 27.1 kt | €60.43/MWh, 27.1 kt |
| Against the reference | | **40 % cheaper, 84 % less CO₂ (22.8 kt/yr avoided), payback 6.7 yr, NPV €44.9 M** |

The MC failures of the new pick are 4 of 400 samples, all cooling: KNMI 2014 or 2020 weather with
cooling demand scaled ×1.15–1.25 (0.3–84 MWh short). "Meets every day" is therefore stated as
"every day of the official year, every measured year 1991–2025, and 99 % of sampled futures".

## Stress tests (stress_margin/stress.md)

LCOE €/MWh (CO₂ t), X = demand missed. The designs are sized on the official 2025 basis and then
run on conditions they did not see.

| test | 3.1 km, 9 MW (old) | 3.15 km, 10 MW | **3.2 km, 10 MW** |
|---|---|---|---|
| base | 35.98 (4,617) | 36.18 (4,355) | **36.35 (4,269)** |
| producer 1.5 K cooler | 38.21 | 36.55 | 36.46 |
| gradient 29 °C/km | 39.60 | 39.01 | 36.91 |
| low reservoir (28.1 °C/km, 100 mD) | 44.57 | 44.24 | 43.72 |
| whole source down 35 days (summer) | 37.23 | 37.48 | 37.67 |
| whole source down from the heating peak | 44.59 | 44.79 | 44.95 |
| KNMI 2020, air +2 K | **X 77 MWh** | 37.70 | 37.85 |
| KNMI 2020, cooling +10 % | **X 32 MWh** | 36.51 | 36.67 |
| KNMI 2014, air +1 K | **X 13.5 MWh** | 37.19 | 37.34 |
| heating and cooling +10 % | 33.56 | 33.74 | 33.90 |
| smaller HEX (1.45 MW/K, ~3 K approach) | 36.72 | 36.21 | 36.35 |
| smaller HEX + producer 1.5 K cooler | 39.47 | 37.37 | 36.50 |

3.15 km is €0.17 cheaper in the base case but loses most of its margin to a 1 °C/km lower gradient
(+€2.8/MWh against +€0.6 at 3.2 km), so 3.2 km was chosen.

## Why not the cheapest design? (baselines)

| Design (KNMI 2025, all meet every rule) | LCOE €/MWh | CO₂ t/yr | note |
|---|---|---|---|
| Cheapest in the screen: 2D-3100 screw + dry cooler, 30 MW boiler, 10 MW chiller | 35.19 | 5,143 | no margin: same 3.1 km knife edge |
| 2D-3200 screw + dry cooler, 33 MW boiler, chiller at the 10 MW peak | 35.46 | 4,746 | misses cooling with +10 % cooling (93 MWh); MC: met in 49.8 % |
| 2D-3200 screw + dry cooler, 33 MW boiler, 12 MW chiller | 35.82 | 4,751 | passes all 13 stress tests |
| **Pick: 2D-3200, free cooling + 3 ATES pairs + 10 MW air-cooled chiller** | **36.35** | **4,269** | passes all 13; MC 99 % |
| Previous pick (3.1 km, 9 MW) | 35.98 | 4,617 | fails 3 of 13 |
| Gas boiler 30 MW + 12 MW air-cooled chiller (reference) | 60.43 | 27,106 | |
| Best design at the reference depth 2.5 km (1D screw, CHP) | 39.22 | 12,781 | |

Abatement on top of the €80/t already inside the LCOE: pick against the 12 MW screw design with the
same margin, +€0.53/MWh for 482 t less, **about €149/t**; against the cheapest (no-margin) design,
+€1.16/MWh for 874 t, about €180/t. Against gas the pick saves money and CO₂ together.
Paired MC (same 400 samples): the pick is cheaper than the peak-sized 3.2 km screw design in 13 %
of samples (median +€0.58/MWh) and lower in CO₂ in 100 %.

## How we read the brief

| Point | Brief / organiser text | Our reading | Literal reading, result |
|---|---|---|---|
| Well depth | Brief §3.1 (28 Oct): "For selecting different geothermal well depth, you can use hydrostatic pressure for reservoir pressure and estimate reservoir temperature based on the provided geothermal gradient." Organisers, 1 Nov (as relayed by Sa'eed): changing well depth is allowed. | Depth is a design variable; 3.2 km = 108 °C, 320.7 bar | Reservoir fixed at 2,500 m: best compliant design €39.22, 12.8 kt; the pick's plant at 2.5 km €46.7 |
| 330 days | Brief: "Annual operation of geothermal doublet: 330 daily steps". Organisers, 1 Nov: the 330 days are the availability of the geothermal source (35 days planned or unplanned shutdown); the full system must meet demand on all 365 days. Second answer, 1 Nov: the outage schedule is a design choice; several doublets may take staggered maintenance. | Each doublet runs 330 days, stops staggered in summer; geothermal heat on all 365 days | Whole source down 35 days together: €37.67, 4,815 t, demand met; started on any of 331 days: all met, €37.67–45.90 |
| Return temperatures | Not in the brief. Organisers, 1 Nov: our choice if the constraints hold. | 40 °C heating, 26 °C cooling | Any heating return 30–62 °C / cooling 23–30 °C keeps the 40 K brine cap |
| Supply temperatures | Brief: 100 °C heating, 20 °C cooling, fixed | Met every day | – |

The organiser answers are not on file verbatim; the wording above is Sa'eed's record of them.

## Other fixes in this rerun

- **Absorption chiller COP** (`absorption_chiller.py`): cooling water at the 20 °C floor equal to
  the chilled-water target returned COP 0, so every absorption design failed. It now returns
  `cop_max`; a boundary test is added. 48 of 72 absorption designs now meet every rule (the 24
  failures are single-doublet designs during their outage); the best is 2D-3200 CHP €38.53/MWh,
  6,339 t, so brine-driven cooling is feasible but €2.2/MWh dearer than the pick.
- **Gas reference** priced on the same daily power prices as the pick: €60.72 → €60.43/MWh.
- **Operating rules vs wellbore**: the rules variant also switched to the aged-wellbore heat loss
  (multiplier 0.45 of GEMINI's steady model). Separately: aged wellbore only €36.27, 4,070 t
  (−€0.08); rules with it €36.43, 4,097 t; so the start/stop rules alone cost about +€0.16/MWh.
  New assumption `wellbore_heat_loss_multiplier` (default 1 = GEMINI as is).
- **Price floor**: daily import price is floored at max(export price, 0); it never binds at the
  default €120/MWh mean.
- **HEX UA**: the 4 MW/K default is a ~0.1 K approach by ε-NTU, not ~3 K as its comment said. The
  value is kept (changing it moves every 3.1 km number and the scripted demos) and the comment is
  corrected. A 1.45 MW/K HEX (~3 K approach) leaves the 3.2 km pick unchanged (€36.35) and is in
  the stress table.
- **Monte Carlo**: `--mc-weather` samples one of the 35 KNMI years per sample (stratified), the
  paired comparison now includes the screw design, and P(met) carries a 95 % Wilson interval.
- **Full screen**: adds 3.2 km (720 designs, 696 meet every rule); the pick (30 MW boiler in the
  screen) ranks 32nd of 696 on cost and no design is both cheaper and lower in CO₂.

Not rerun: the Fimbul reservoir sweep (Julia; was run for 3.1 km, no breakthrough at 1,200 m),
the ThermoGIS cross-check (Sa'eed's PC) and the LLM benchmark (4 Nov results stand, on the code
of that day).
