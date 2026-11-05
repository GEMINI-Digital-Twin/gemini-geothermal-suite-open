# Final pick with staggered maintenance and a 33 MW boiler (2 Nov 2026)

Author: Sa'eed Telvari

**Why this changed.** The organisers' first answer (1 Nov) said the 330 days are the
availability of the geothermal source, and that the full system must meet demand on all 365
days. Their second answer (1 Nov, late) said the schedule is ours to choose: several doublets
may take their maintenance at different times, or a single doublet can rely on backup. Sa'eed
chose the following (2 Nov):

- **Staggered planned stops.** Each doublet is down 35 days at a different time in summer
  (26 May–29 Jun and 9 Jul–12 Aug), so geothermal heat is available every day.
- **A 33 MW boiler.** This is 10% above the 30 MW heating peak, so that the plant still meets
  demand if both doublets trip, unplanned, on the coldest days.

Weather: KNMI Schiphol 2025. Lined casing is priced, and the ledger prices are used.
Commands are in `HACKATHON.md`. Scripts: `run_final_pick.py`, `run_outage_study.py`,
`run_full_screen.py`, `run_weather_years.py`, `run_return_temperature_check.py`.

## Headline (final_pick/)

| | Before (whole source down, 30 MW boiler) | **Now (staggered stops, 33 MW boiler)** |
|---|---|---|
| LCOE | €36.57/MWh | **€35.71/MWh** |
| CO₂ | 4,790 t/yr | **4,345 t/yr** |
| CAPEX | €46.2 M | **€46.5 M** |
| Purchased gas | 2.6 GWh | **27 MWh** |
| With doublet operating rules | | €35.62/MWh, 4,202 t, 2 starts |
| Gas boiler + chiller reference | €59.3/MWh, 26.4 kt | €59.3/MWh, 26.4 kt: the pick is **40% cheaper with 84% less CO₂**, payback 6.6 yr, NPV €44.0 M |
| Monte Carlo (400 samples, sourced prices) | P50 €37.6 | **P50 €36.5 (P10–P90 30.9–42.6)**, CO₂ P50 4.28 kt, **400/400 meet all demand** |
| 1 doublet, same plant | €34.71, 9,331 t | €34.91, 9,331 t (the single-doublet design gets the 33 MW boiler too) |

## Resilience scenarios (outage.md)

| Scenario | LCOE €/MWh | CO₂ t | Demand met |
|---|---|---|---|
| S1 staggered planned stops (headline) | 35.71 | 4,345 | yes |
| S1c same, with a 30 MW boiler | 35.51 | 4,345 | yes |
| S2 whole source down together in summer | 36.78 | 4,790 | yes |
| S3 one doublet fails at the January peak | 39.74 | 6,157 | yes (boiler peaks at 14.8 MW) |
| S4 both doublets fail at the January peak | 45.24 | 8,729 | yes (boiler at 30.0 of 33 MW) |
| S5 S4 with heating demand +6% | 43.86 | 9,186 | yes (31.8 of 33 MW) |
| S5b S5 with a 30 MW boiler | 43.66 | 9,164 | **no, 98 MWh unmet** |
| S6 whole-source outage started on each of 331 days | 36.78–45.24 | | yes, all 331 |

Each scenario is a full year with that outage in it. Cooling never depends on the wells.
Where the summer windows fall barely matters: the best pair changes LCOE by less than a cent
and CO₂ by 37 t (S1b).

## Weather years (years.md)

With the 9 MW backup chiller, the pick meets all demand in all 35 KNMI years 1991–2025.
LCOE ranges from €34.78 to €36.59/MWh, median €35.58. A 6 MW backup chiller still fails in
13 of the 35 years.

## Full screen (full_screen/)

All 600 designs were rerun with staggered stops, each with the standard boiler (30 MW, equal
to the peak). 540 meet every rule, and all 60 absorption designs fail. The ordering is the same
as before:
- The cheapest design is still a single doublet: 1D screw + dry cooler, €34.39/MWh, 9,796 t.
- The best two-doublet design is screw + dry cooler at €35.18/MWh and 4,875 t.
- The ATES pick (with the 30 MW boiler) costs €35.51/MWh and emits 4,345 t. That is €0.33/MWh
  more for 530 t less CO₂, about €84/t on top of the €80/t already in the LCOE.

## Return temperatures (return_temperatures.md)

The brief fixes the supply temperatures but not the returns. The organisers said the returns
are ours to choose, as long as no constraint is broken. The binding constraint is the 40 K cap
on brine cooling.

- **Heating return:** every value from 30 to 62 °C meets every rule. Brine cooling reaches the
  40 K cap up to 50 °C, and stays below it above that. LCOE moves only €0.06 between 30 and
  50 °C, then rises to €36.92 at 62 °C, because a warmer return leaves less room to cool the
  brine.
- **Cooling return:** every value from 23 to 30 °C meets every rule, at €36.05 to
  €35.33/MWh.
- **Our choice:** 40 °C heating return (a modern Dutch district-heating return) and 26 °C
  cooling return (the usual 6 K district-cooling ΔT). Both sit in the flat part of the curve.
