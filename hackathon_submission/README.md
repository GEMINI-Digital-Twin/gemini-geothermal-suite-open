# GEMINI GeoHackathon 2026 — Submission

**Author:** Mahdi Izadi

A full-year (2027, 365 days) design and dispatch study of a geothermal
district heating **and** cooling plant built on the GEMINI simulator, with an
automatic design search over 1–3 doublets and an independent validator that
recomputes every challenge constraint from the daily results.

## Result in one line

**3 doublets + 1.6 MW/K plate HEX per doublet + Lorenz heat pump to 100 °C,
absorption/electric chillers for 20 °C cooling → 8,708 t CO₂/year, 87 % of
100 °C heat from the geothermal chain, 12/12 constraint checks passed.**

| Design (best of each) | Annual CO₂ | Backup gas boiler share |
|---|---|---|
| 1 doublet  | 15,330 t | 33 % |
| 2 doublets |  9,721 t |  3 % |
| **3 doublets (selected)** | **8,708 t** | **2 %** |

## How to run

```bash
# from the repository root (development branch + this folder)
python -m venv .venv
.venv\Scripts\activate          # Windows   (Linux/Mac: source .venv/bin/activate)
pip install numpy scipy pandas matplotlib

cd hackathon_submission
python optimize_design.py       # ~30 s: 45 designs + sensitivity -> best_design.json
python run_full_year.py         # full year of the selected design + validation + plots
```

## Plant

```
reservoir 2500 m TVD, 250 bar, 87 C
  └─ producer well + ESP (1000 m, variable speed)       [GEMINI ProducerWell]
       └─ separator (GLR 0.8) ─ gas ─> boiler 80 % / CHP 20 %   [GEMINI]
       └─ filter A ─> plate HEX ─> heat-pump evaporator ─> filter B
                                                          └─ injector well [GEMINI InjectorWell, pump eta 0.70]
district return 40 C ─> HEX (secondary) ─> heat-pump condenser ─> 100 C supply
                                  100 C heat ─> absorption chiller ─> 20 C cooling
                                 electricity ─> electric chiller   ─> 20 C cooling
backup gas boiler (100 C) covers what geothermal cannot (maintenance block, peaks)
```

The brine always cools in two stages: first directly in the HEX, then in the
heat-pump evaporator, never below **40 °C injection** (80 °C wellhead − 40 °C
limit), so the 40 °C brine-cooling limit is a hard physical bound in the model.

## Method

1. **GEMINI physics layer** (`plant_model.build_well_table`). For each ESP
   frequency (15–70 Hz) the GEMINI project (`challenge_plant.json`) is solved:
   nodal producer well with ESP, separator gas, filters, injector well and
   pump, produced-gas boiler/CHP. Operating points outside 50–300 m³/h or with
   ESP intake < 10 bar are discarded.
2. **HEX** — GEMINI `HeatExchanger` class (counter-flow ε-NTU) with brine
   density 1030 kg/m³.
3. **Heat pump** — Lorenz model, η = 0.50, identical equations to GEMINI
   `HeatpumpBasic` (now registered in the component registry). Solved by
   bisection on the source outlet temperature; verified to match
   `HeatpumpBasic` exactly where its solver converges (COP 6.129 vs 6.129).
4. **Daily dispatch** (`dispatch.py`). Every day, all combinations of active
   doublets (1..N), ESP frequency and absorption-chiller share
   (0/25/50/75/100 %) are evaluated; the lowest-CO₂ option that meets demand
   is chosen.
5. **330 operating days** — geothermal is off for one contiguous 35-day
   maintenance block, placed where it costs the least CO₂
   (selected: 9 Jul – 12 Aug 2027). Backup boiler + electric chiller serve
   those days.
6. **Design search** (`optimize_design.py`) — 3 doublet counts × 5 HEX sizes
   × 3 ESP stage counts = 45 full-year simulations; infeasible candidates are
   rejected; the lowest-CO₂ feasible design is selected
   (`design_comparison.csv`).
7. **Sensitivity** on the selected design (`sensitivity.csv`).

## Constraint compliance (from `validation_report.txt`)

| Check | Result |
|---|---|
| Doublets in [1,3] | 3 |
| Flow per active doublet 50–300 m³/h | 51–186 m³/h |
| No flow when inactive | ✓ |
| Volume balance produced = injected | exact (GEMINI connection) |
| Brine cooling ≤ 40 °C | max 40.00 °C |
| Pump efficiency 0.70 | ESP and injector power = Δp·Q / 0.70 |
| Heating supply 100 °C | HP condenser outlet solved at 100 °C |
| Heating demand met every day | max shortfall 0 MW |
| Cooling demand met at 20 °C | max shortfall 0 MW |
| Geothermal operating days | 330 |
| Energy balance HEX + HP closes | residual < 1 kW |

## Annual results (selected design, official 2027 demand)

| KPI | Value |
|---|---|
| Heating delivered | 111,668 MWh |
| Cooling delivered | 23,743 MWh |
| Share of 100 °C heat from geothermal chain (HEX + HP) | 87.2 % |
| … from produced gas (boiler/CHP) | 10.7 % |
| … from backup gas boiler | 2.1 % |
| Net electricity use | 15,681 MWh |
| Mean heat-pump COP | 4.38 |
| CO₂ emissions | 8,708 t/year |

## Sensitivity (selected design)

| Parameter | Values → CO₂ (t/yr) |
|---|---|
| District return temperature 35 / 40 / 45 / 50 °C | 8,560 / 8,708 / 8,875 / 9,066 |
| Heat-pump Lorenz efficiency 0.40 / 0.50 / 0.60 | 9,240 / 8,708 / 8,324 |
| Electric chiller COP 3 / 4 / 5 | 8,959 / 8,708 / 8,365 |
| Grid emission factor 0.1 / 0.3 / 0.5 kg/kWh | 5,459 / 8,708 / 11,608 |

All sensitivity cases stay feasible (12/12 checks).

## Assumptions (not supplied by the challenge)

| Item | Value | Why |
|---|---|---|
| Brine/water specific heat | 4186 J/kg/K | water at ~80 °C |
| District return temperature | 40 °C | typical; see sensitivity |
| Wellhead temperature | 80 °C | GEMINI boundary (87 °C reservoir − well losses) |
| Productivity/injectivity index | 10 m³/h/bar | GEMINI example value |
| ESP depth | 1000 m | keeps intake > 10 bar at high flow |
| Heat pump | Lorenz, η = 0.50 | GEMINI default |
| Electric chiller COP (20 °C supply) | 4.0 | see sensitivity |
| Absorption chiller COP (100 °C drive) | 0.7 | single-effect |
| Grid emission factor | 0.3 kg CO₂/kWh | GEMINI example value |
| Natural gas | 56.6 kg CO₂/GJ, boiler η 0.90 | standard |
| Produced gas | burned on site (GEMINI boiler/CHP); its CO₂ is counted | no venting |
| Economics | not modelled | challenge gives no costs; we do not invent them. Without costs a bigger HEX is always slightly better, so a cost study would mainly decide HEX size and 2 vs 3 doublets. |

## Known GEMINI issues found

* `HeatpumpBasic` was not in the component registry → added (one line in
  `src/gemini_simulator/registry.py`).
* `HeatpumpBasic` fallback branch (used when the source-outlet minimum is
  active) returns non-physical results (e.g. hot outlet > 700 °C, COP ≈ 1).
  We therefore solve the same Lorenz equations directly and cross-check them
  against `HeatpumpBasic` in its valid range.
* Example JSON values contradicting the challenge (240 bar injector, 2400/3100 m
  wells, 0.8 pump efficiency, GLR 0.5) are corrected in `challenge_plant.json`.

## Files

| File | Purpose |
|---|---|
| `plant_model.py` | GEMINI well/gas layer, HEX, heat pump, per-doublet physics |
| `dispatch.py` | daily optimal dispatch, maintenance block, summary, validator |
| `optimize_design.py` | design search + sensitivity |
| `run_full_year.py` | full-year run of selected design, reports, plots |
| `challenge_plant.json` | GEMINI project with challenge inputs |
| `GEMINI_*_Demand_Daily_2027.csv` | official demand profiles |
| `best_design.json` | selected design + assumptions |
| `design_comparison.csv` | all 45 candidates |
| `sensitivity.csv` | sensitivity study |
| `results_daily.csv` | 365 days × all flows, temperatures, powers, CO₂ |
| `results_summary.csv` | annual KPIs |
| `validation_report.txt` | pass/fail of every constraint |
| `plots/` | heating & cooling dispatch, operating envelope, design comparison |
