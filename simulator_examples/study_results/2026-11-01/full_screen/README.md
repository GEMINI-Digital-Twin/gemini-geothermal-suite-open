# Full design screen (1 Nov 2026)

Author: Sa'eed Telvari

`simulator_examples/run_full_screen.py --epw NLD_Amsterdam.062400_IWEC.epw` on the final pick's basis: Amsterdam IWEC weather, whole geothermal source down 35 days in the lowest-load window, corrosion mitigation priced, ledger prices. 600 year runs (1-3 doublets x 2.5/2.8/3.1/3.4/4.0 km x boiler or heat pump x CHP or not x 10 cooling options), about 6 minutes on 4 cores.

- 540 of 600 meet every hard rule. All 60 absorption designs fail on cooling: the absorption chiller is driven by brine, and the whole source is off in summer.
- The pick, 2D-3100m-boiler-electric-chp-aircooled-fc-ates3, reproduces the report (35.05 EUR/MWh, 4,429 t). It is the cheapest two-doublet design, and no design is both cheaper and lower in CO2.
- Same wells (2D, 3.1 km, CHP): legacy chiller 36.89, air-cooled + free cooling 35.64, + 3 ATES pairs 35.05 EUR/MWh. Without CHP the pick's layout costs 37.63.
- One doublet with the same cooling: 33.19 EUR/MWh, 9,072 t. Three doublets: 47.42 EUR/MWh or more.

The weather file is not in the repository (ASHRAE IWEC licence); it is the public EnergyPlus file `NLD_Amsterdam.062400_IWEC`.

Superseded by `../full_screen_knmi2025/`, which uses the report's final basis (KNMI Schiphol 2025 weather and a 9 MW backup chiller on the ATES option; this run used 6 MW).
