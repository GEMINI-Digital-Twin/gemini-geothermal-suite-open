# Final pick: gated runs, Monte Carlo and tornado (1 Nov 2026)

Author: Sa'eed Telvari

Made by `python simulator_examples/run_final_pick.py --epw NLD_Amsterdam.062400_IWEC.epw --mc 400`
(PYTHONPATH=src). The IWEC weather file is not in the repository (licence); download it from the
EnergyPlus weather site. Basis: Amsterdam IWEC weather, GRE-lined casing priced, the whole
geothermal source down 35 days in the lowest-load window (organisers' answer of 1 Nov), no
doublet operating rules unless stated. This is the basis of the report headline.

Pick: 2 doublets at 3.1 km, HEX, CHP on the co-produced gas, 30 MW boiler, free cooling, 3 ATES
well pairs, 6 MW air-cooled screw chiller (`2D-3100m-boiler-electric-chp-aircooled-fc-ates3`).

## Gated runs (ledger prices, `runs.md`)

| Case | LCOE, EUR/MWh | CO2, t/yr |
|---|---|---|
| Final pick | 35.05 | 4,429 |
| Final pick with operating rules | 35.00 | 4,298 |
| Earlier pick (12 MW legacy chiller) | 37.25 | 5,541 |
| ATES well pair cost x2 / x0.5 | 36.28 / 34.43 | 4,429 |
| ATES cold losses x2 | 35.59 | 4,682 |
| Corrosion mitigation free | 31.66 | 4,429 |
| One doublet | 33.19 | 9,072 |

All ten runs pass the physics gate (incl. the GEMINI Solver cross-check) and meet every hard rule.

## Monte Carlo (sourced prices, 400 shared Latin-hypercube samples of 14 inputs, `mc_summary.csv`)

| Design | P(all demand met) | LCOE P10 / P50 / P90 | CO2 P50, kt/yr |
|---|---|---|---|
| Final pick | 99.75 % (399/400) | 30.5 / 36.1 / 42.1 | 4.5 |
| Earlier pick (12 MW chiller) | 97.75 % (391/400) | 32.9 / 38.1 / 44.4 | 5.2 |

The pick is cheaper in all 400 paired samples (median by EUR 2.2/MWh) and emits less CO2 in all
400 (median 0.63 kt). Its one miss is 14 MWh of cooling at +28 % cooling demand. Sourced base
case: EUR 31.2/MWh, 4.3 kt, CAPEX EUR 42.1 M. Largest LCOE swings (`tornado_pick.csv`,
`fig_tornado_pick.png`): well cost factor (29.8-36.6), discount rate (29.5-35.4), permeability,
heating demand, temperature gradient. The well-integrity CAPEX (lined casing) is included and
scales with the sampled well cost.

`pick.json` also holds a simulated gas-boiler + air-cooled-chiller reference on the same weather
(EUR 59.2/MWh, 26.4 kt CO2, CAPEX EUR 5.4 M): pick payback 6.5 years, NPV EUR 44.9 M at 6 % over
30 years, 21.9 kt CO2 avoided a year. The report's §5.2 uses this reference.
