# Full design screen on KNMI Schiphol 2025 weather (1 Nov 2026)

Author: Sa'eed Telvari

`simulator_examples/run_full_screen.py --knmi simulator_examples/weather/knmi_etmgeg_240_1991_2025.txt --year 2025` (the KNMI file comes with the weather rerun, PR #17). Same basis as the report's final pick: measured KNMI Schiphol daily weather for 2025, whole geothermal source down 35 days in the lowest-load window, corrosion mitigation priced, ledger prices. The ATES option now has a 9 MW backup chiller, as in the pick (6 MW misses cooling in 13 of 35 KNMI years). 600 year runs, about 15 minutes on 4 cores.

- 540 of 600 meet every hard rule. All 60 absorption designs fail on cooling: the absorption chiller is driven by brine, and the whole source is off in summer.
- The pick, 2D-3100m-boiler-electric-chp-aircooled-fc-ates3, reproduces PR #17 (36.57 EUR/MWh, 4,790 t). No design is both cheaper and lower in CO2.
- What changed against the IWEC screen (`../full_screen/`): ATES is no longer the cheapest cooling. KNMI 2025 has fewer cold days, so free cooling and the winter ATES charge do less and the chiller does more. Same wells (2D, 3.1 km, CHP): screw chiller + dry cooler 36.25 EUR/MWh and 5,353 t; air-cooled + free cooling 36.50 and 5,307 t; + 3 ATES pairs 36.57 and 4,790 t. The pick is the lowest-CO2 two-doublet design at 3.1 km, at 0.32 EUR/MWh (about 43 kEUR/yr) more than the cheapest, for 563 t less CO2 (about 77 EUR/t).
- CHP saves 2.6 EUR/MWh (the pick's layout without CHP: 39.15).
- One doublet: cheapest 34.39 EUR/MWh at 9,796 t (screw + dry cooler); with the pick's cooling 34.71 and 9,331 t. Three doublets: 48.84 EUR/MWh or more.
