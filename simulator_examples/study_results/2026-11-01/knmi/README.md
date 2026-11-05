# The pick on measured KNMI Schiphol weather (1 Nov 2026)

Author: Sa'eed Telvari

Weather: KNMI daily data for Amsterdam Schiphol, station 240
(`simulator_examples/weather/knmi_etmgeg_240_1991_2025.txt`, open data). The demand profiles are
for 2027, so measured years are aligned by day of year. Headline year: 2025, the latest full
year, which sits at the median of 2016-2025 (LCOE 36.44-37.45 EUR/MWh over that decade).
Basis otherwise as the IWEC report runs: GRE-lined casing priced, whole geothermal source down
35 days in the lowest-load window, no doublet operating rules unless stated.

## What changed

The IWEC typical year has a cool summer. On 35 measured years (1991-2025) the pick with the
6 MW backup chiller misses cooling in 13 years (worst 2020: 822 MWh, 2.7 MW short on 19 July).
After a warm winter the dry cooler charges less cold, the permit heat balance throttles the
ATES to about 1.3 MW, and on hot days there is no free cooling. 8.5 MW still misses 2020;
**9 MW meets all heating and cooling in all 35 years**, so the pick's backup chiller is now 9 MW.

| Basis | LCOE, EUR/MWh | CO2, t/yr | Demand met |
|---|---|---|---|
| IWEC, 6 MW chiller (old headline) | 35.05 | 4,429 | yes (IWEC only) |
| IWEC, 9 MW chiller | 35.67 | 4,430 | yes |
| **KNMI 2025, 9 MW chiller (new headline)** | **36.57** | **4,790** | yes |
| KNMI 1991-2025, 9 MW: range (median) | 35.64-37.45 (36.44) | 4,393-5,084 (4,749) | 35/35 years |
| KNMI 1991-2025, 6 MW | 35.02-36.88 | | 22/35 years |

Commands (PYTHONPATH=src, OPENBLAS_NUM_THREADS=1), W = the KNMI file above:

    python simulator_examples/run_weather_years.py --knmi W --epw NLD_Amsterdam.062400_IWEC.epw
    python simulator_examples/run_outage_study.py --knmi W --year 2025
    python simulator_examples/run_final_pick.py --knmi W --year 2025 --mc 400

## KNMI 2025 results

Gated runs (`final_pick/runs.md`, all pass the physics gate and every hard rule):

| Case | LCOE | CO2 |
|---|---|---|
| Final pick (9 MW chiller) | 36.57 | 4,790 |
| With operating rules | 36.50 | 4,703 |
| Earlier pick (12 MW legacy chiller) | 37.43 | 5,593 |
| Air-cooled 12 MW + free cooling, no ATES | 36.94 | 5,314 |
| ATES pair cost x2 / x0.5 | 37.80 / 35.96 | 4,790 |
| ATES losses x2 | 37.18 | 5,007 |
| Corrosion mitigation free | 33.18 | 4,790 |
| One doublet | 34.71 | 9,331 |

The ATES now beats the no-ATES air-cooled design by only EUR 0.37/MWh (and 524 t CO2); with
ATES well pairs at twice the assumed cost it is EUR 0.86/MWh dearer.

Outage (`outage.md`): outage started on each of 331 days, demand met in 331/331, LCOE
36.57-45.04. Winter-peak outage: 30 MW boiler at zero headroom; with heating +6 % it misses
98 MWh, a 33 MW boiler fixes it.

Monte Carlo (400 samples, sourced prices): pick meets all demand in 400/400 (was 399/400 on
IWEC), LCOE P10/P50/P90 32.1 / 37.6 / 43.6, CO2 P50 4.7 kt. Cheaper than the earlier pick in
400/400 (median EUR 0.90/MWh) and lower CO2 in 400/400 (median 0.50 kt). Sourced base case
EUR 32.6/MWh, 4.5 kt, CAPEX EUR 43.0 M.
