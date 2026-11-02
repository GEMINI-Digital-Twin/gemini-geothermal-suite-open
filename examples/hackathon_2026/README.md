# Hackathon 2026 sample case

Sample of the SPE Europe Energy GeoHackathon 2026; the demand profiles are for the year 2027.

One sample case of gemini: only `examples/` and `tests/` read this folder, and nothing under
`gemini/` knows it. The inputs of the GEMINI agentic geothermal design hackathon, as the organisers released them on
2026-10-29. The requirements document is dated 28 October 2026. These files are unchanged:
`GEMINI_Heating_Demand_Daily_2027.csv`, `GEMINI_Cooling_Demand_Daily_2027.csv` and
`GEMINI_Hackathon_Challenge_Requirements.pdf`.

The profiles are synthetic: 365 daily-average power values, 1 January to 31 December 2027.

| Profile | Peak | Peak date | Year |
| --- | --- | --- | --- |
| Heating | 30.0 MWth | 2027-01-28 | 111.67 GWh/yr |
| Cooling | 10.0 MWcool | 2027-07-19 | 23.74 GWh/yr |

## Reservoir

| Parameter | Value |
| --- | --- |
| Midpoint depth | 2,500 m TVD |
| Gross thickness | 100 m |
| Geothermal gradient | 30 °C/km |
| Reference surface temperature | 12 °C |
| Reservoir pressure | 250 bar(g) |
| Permeability | 200 mD |

For another well depth the organisers allow hydrostatic pressure for the reservoir pressure and the
gradient for the reservoir temperature.

## Brine and associated gas

| Parameter | Value |
| --- | --- |
| Brine density | 1,030 kg/m³, constant |
| Dynamic viscosity | 0.40 mPa·s, constant |
| Gas-liquid ratio | 0.8 Nm³ gas per m³ produced liquid |
| Methane in the produced gas | 80 mol% |
| Carbon dioxide in the produced gas | 20 mol% |
| Fluid composition | Fixed baseline; variable PVT optional |

A normal cubic metre is at 0 °C and 1.01325 bar(a). The ratio is the gas that can be liberated at
standard conditions.

## Limits

| Constraint | Value | Status |
| --- | --- | --- |
| Geothermal doublets | 1 to 3 | Design variable |
| Maximum production flow | 300 m³/h per doublet | Hard cap |
| Minimum stable flow while active | 50 m³/h per doublet | Hard cap |
| Maximum brine cooling | 40 °C, producer to injector | Hard cap |
| Pump hydraulic efficiency | 70% | Simplified |
| Free gas at the pump intake | At most 18.75 % of the volume while running | Sourced below, not an organiser limit |
| Pump intake pressure | At least 5 bar while running | Assumption, no verified source; not an organiser limit |
| Production and injection volume | Equal liquid volumes, same reservoir | Required |
| Annual operation of a doublet | 330 daily steps | Daily power and energy balance |
| Heating supply temperature | 100 °C | Fixed |
| Cooling supply temperature | 20 °C | Fixed |

## Requirements of the case

Each is an entry of `requirements` in `case.json`, on a role of the plant, so that one case judges any plant.

| Name | Rule | Where it comes from |
| --- | --- | --- |
| `doublet_count` | `count` of `doublet`, 1 to 3 | the brief (geothermal doublets 1 to 3) |
| `production_flow_range` | 50 to 300 m3/h in every step in which the doublet runs | the brief |
| `brine_cooling_limit` | at most 40 K, producer to injector, while running | the brief |
| `running_time_limit` | at most 330 d running | the brief (330 daily steps) |
| `pump_efficiency` | 0.7 (`min` = `max`) | the brief (simplified) |
| `full_reinjection` | `reinjection_ratio` 0.99999 to 1.00001 while running | the brief says only "equal liquid volumes" and gives no number; the band is an assumption carried from the earlier absolute limit of this sample (1e-6 m3/s), see below |
| `heat_delivered` | `unmet_share` of `heating_supply` at most 0.01 | assumption: the brief asks that the heat demand is met and gives no tolerance |
| `cold_delivered` | `unmet_share` of `cooling_supply` at most 0.01 | assumption: the brief asks that the cold demand is met and gives no tolerance |

`full_reinjection`. The band 0.99999 to 1.00001 is not the brief's. It is the relative band that keeps the
verdict of every candidate under the earlier absolute limit of 1e-6 m3/s (the first relative band tried, 0.999999 to
1.000001, rejected `HackathonPlant` sized with the backup policy `peak`). `HackathonPlant` has a real imbalance:
2.2e-3 m3/h at about 300 m3/h, a ratio of 0.9999925, which is inside the band and outside a band of 1e-6 in
the ratio. The sample applies this band as its reading of the brief's rule.

`heat_delivered` and `cold_delivered`. The brief asks that the heat and cold demands are met and gives no tolerance;
the sample applies 1 % of the demanded energy of the year as an assumption. The share of the demanded energy that is
unmet was measured in every trial of the search (20 evaluations, seed 0, serial) of the six plants, and in the
searched designs:

| Share unmet | Largest in a trial | In the searched design |
| --- | --- | --- |
| heat | 1.1e-16 | 1.0e-16 or less (the peak boiler covers the rest) |
| cold | 0.79 (`HackathonPlant`, `HeatingHeatPumpCoolingPlant`), 0.70 (`HeatingAbsorptionCoolingPlant`), 0.45 (`HeatingCoolingPlant`), 0.26 (`HeatingFullCoolingPlant`) | 8.5e-17 |

Trials with an undersized chiller meet only part of the cold, so they are infeasible in the search under this band; the
searched designs meet the cold fully, so the best design of every plant is the one found without the requirement
(checked with the search guard on the six plants). `HeatingPlant` has no cooling supply: it breaks the cold rule
structurally, its trials are not made infeasible by it, and its verdict reason stays `cold_delivered`.

## Heat pump performance

Every heat pump and compression chiller states `carnot_fraction` 0.5 in its plant dict, which the
cost dispatch and the run read: "close to 50 percent of the Carnot value", H. U. Frutschi, ABB
Review 5/1996, pp. 33-34. It is a general figure and no data of these machines.

## Files added for the examples

The organiser files stay as released. The others hold the requirements above, and the assumptions
they leave open, in the shapes of gemini.

| File | Holds | Read by |
| --- | --- | --- |
| `demand.csv` (in `data/`) | The two organiser demand files joined on `time`: `heating_demand_MWth` and `cooling_demand_MWcool`, values unchanged | `case.json` |
| `case.json` | The one case: time, site, brine, demand, the requirements (with the 330 day operating duration) and the assumptions | every example, `gm.Case.from_json` |
| `economics.json` | Every price, factor and finance value, with the uncertainty ranges | `case.json` |
| `plants/<Class>.json` | One plant dict per candidate: `HeatingPlant`, `HeatingAbsorptionCoolingPlant`, `HeatingHeatPumpCoolingPlant`, `HeatingFullCoolingPlant`, `HeatingCoolingPlant`, and `HackathonPlant` (structure form: desander, inhibitor dosing, one absorption chiller); design values and search ranges only, no site; each `esp` states the two pump intake limits below | `study.json`, `examples/costs.py`, tests |
| `plants_brief/<Class>.json` | The same six plants without those two limits, for the ranking by the brief's rules only (an absent leaf is no limit); written from `plants/` by a script that removes the two leaves | `study_brief.json` |
| `study.json` | Size and search every plant of `plants/` on LCTS: 20 evaluations, seed 0, metric `co2` too | `examples/hackathon.py` |
| `study_brief.json` | The same study on `plants_brief/` | `examples/hackathon.py` |
| `study_sensitivity.json` | One-at-a-time sensitivity of LCTS; run on the best design given in memory | `examples/hackathon.py` |
| `study_sample.json` | 5 draws of the uncertain values (seed 1), metrics LCTS and CO2; run on the best design given in memory | `examples/hackathon.py` |

`examples/hackathon.py` runs `study_brief.json` and `study.json` one after the other, so it takes about
twice as long as one ranking: about 4.5 minutes with 8 processes (one ranking took 2 min 14 s).

Sizes of equipment and the injection pressure are design values of the plants. The return
temperatures, the air temperature and every price are assumptions of the case.

## Given by the organisers, in `case.json`

| Section | Values |
| --- | --- |
| `site` | Gradient 30 K/km, surface 12 degC, 2500 m, 100 m, 200 mD, 250 barg; brine 1030 kg/m3, 0.4 mPa.s, GLR 0.8, 80 % CH4 and 20 % CO2 |
| `demand` | The two profiles; supply 100 degC heating and 20 degC cooling |
| `requirements` | 1 to 3 doublets, 50 to 300 m3/h while running, brine cooling at most 40 K, at most 330 d running, pump efficiency 0.7, equal liquid volumes (the band is stated below), heat and cold delivered (the band is an assumption, stated below) |
| plant `range` | 2000 to 3500 m of depth, capacities and flows: search ranges of the plant files, an assumption of the example |

## Assumptions of the example

Every value of this section is a placeholder of the example, from no source and none given by the organisers (the search settings, 20 evaluations, seed 0, and 5 draws with seed 1, the search ranges of the plant files, the backup policy `peak`, the bands of `heat_delivered` and `cold_delivered` (1 %) and the band of `full_reinjection` are assumptions of the example as well): return temperatures 60 degC (heating) and 25 degC (cooling), air
10 degC; prices chemical 3 EUR/kg, waste disposal 0.2 EUR/kg,
heat and cold revenue 60 EUR/MWh; discount rate 0.05, lifetime 25 yr, `heat_cost_share` 0.8;
electricity 300 g CO2/kWh; capex of the production and injection pump 0.5 EUR/W, absorption and
adsorption chiller and compression chiller 0.3 EUR/W, heat exchanger 0.5 EUR/(W/K), cooler
0.1 EUR/W, pipe 500 EUR/m, flare 100000 EUR, gas makeup 50000 EUR; fixed opex per kind of 0.5 to
2 %/yr of its capex (heat exchanger 1, drilling 1) except the three kinds cited below.

### Uncertainty of the example

Six values carry an `uncertainty` next to their value in `case.json`. The ranges are assumptions of
the example, not from a source, chosen wide around the cited or placeholder value; `gm.study.sample` draws
them and `gm.study.sensitivity` runs each at its ends. A normal run, `size` and `minimize` use only the value.

| Value | Value in the case | Distribution (assumption) |
| --- | --- | --- |
| `opex.electricity` | 105.75 EUR/MWh | uniform 80 to 140 EUR/MWh |
| `opex.gas` | 39.92 EUR/MWh | triangular 25 to 70 EUR/MWh, mode 39.92 |
| `opex.co2` | 57.03 EUR/t | triangular 30 to 110 EUR/t, mode 57.03 |
| `environment.reservoir.permeability` | 200 mD | triangular 100 to 400 mD, mode 200 |
| `environment.ground.gradient` | 30 K/km | normal, std 2 K/km, cut to 25 to 35 K/km |
| `finance.discount_rate` | 0.05 | normal, std 0.01, cut to 0.02 to 0.08 |

Cited, price year 2015, currency EUR. Conversions to 2015 use the euro-area HICP annual average
index, all items (Eurostat `prc_hicp_aind`, `INX_A_AVG`, EA, 2015 = 100: 2015 100.00, 2020 105.06,
2025 128.75, update of 2026-02-06). The catalogue below is Danish Energy Agency, Technology Data for
Generation of Electricity and District Heating, version 0019, August 2026, with the Excel data sheets
of the same version (https://ens.dk/media/8614/download and https://ens.dk/media/8615/download, opened
2026-11-01). The fixed opex is the sheet's fixed O&M [EUR/MW/yr] over its nominal investment.

| Key | Value | Source and figure as stated |
| --- | --- | --- |
| `capex.heat_pump` | 0.73786 EUR/W | DEA data sheet "40 Comp. hp, waste heat 10 MW" (heat pump, waste heat, electricity, large, district heating): nominal investment (total) 0.95 MEUR/MW_h in the 2025 column, cost data in 2025 EURO; 0.95 / 1.2875 = 0.73786 EUR2015/W. Replaces 0.67 |
| `opex.fixed.heat_pump` | 0.2239 %/yr | Same sheet, fixed O&M (total) 2126.745 EUR/MW_h/y over 0.95 MEUR/MW_h. Replaces 2 |
| `capex.boiler` | 0.06073 EUR/W | DEA data sheet "44 Natural Gas DH Only" (gas boiler, medium): nominal investment (total), 2020 column, 0.0638024 MEUR/MW_h, cost data in 2020 EURO (Intro sheet); 0.0638024 / 1.0506 = 0.06073 EUR2015/W. Replaces 0.06 |
| `opex.fixed.boiler` | 3.25 %/yr | Same sheet, 2020 column, fixed O&M 2073.58 EUR/MW_h/y over 0.0638024 MEUR/MW_h. Replaces 1.5 |
| `capex.chp` | 0.96155 EUR/W electric | DEA data sheet "06 Gas engines, natural gas" (engine, back pressure, natural gas, small; 1 to 10 MW_e): nominal investment (total), 2020 column, 1.01020 MEUR/MW_e, cost data in 2020 EURO; 1.01020 / 1.0506 = 0.96155 EUR2015/W. Replaces 0.95 |
| `opex.fixed.chp` | 1.0263 %/yr | Same sheet, 2020 column, fixed O&M 10367.88 EUR/MW_e/y over 1.01020 MEUR/MW_e. Replaces 2 |
| `emissions.CH4.gwp` | 29.8 | IPCC AR6 WG1 chapter 7 table 7.15 (Forster et al. 2021), fossil methane, 100 years. Seen as quoted in Munoz, Schmidt and Weidema (2024), "The indirect global warming potential of methane oxidation in the IPCC's sixth assessment report", Environmental Research Letters 19(12), 121002, https://doi.org/10.1088/1748-9326/ad8edd: "the GWP100 for fossil and biogenic methane became 29.8 and 27.0 kg CO2-eq kg-1 methane, respectively (table 7.15 in Forster et al 2021)". The IPCC chapter itself could not be opened (HTTP 403) |
| `lifetime` 25 yr | kept | DEA data sheets above state a technical lifetime of 25 years for the large heat pump and the gas boiler (and the geothermal sheet 45.3); that is a technology lifetime, not a project appraisal period, so the value stays an assumption that agrees with it |
| `opex.electricity` | 105.75 EUR/MWh | Eurostat `nrg_pc_205`, electricity prices for non-household consumers, EU average (`EU27_2020`), band IE (20 000 to 69 999 MWh/yr), excluding VAT and other recoverable taxes (`X_VAT`), 2025-S1 0.1381 and 2025-S2 0.1342 EUR/kWh, mean 0.13615 EUR/kWh = 136.15 EUR/MWh (EUR 2025); 136.15 / 1.2875 = 105.75 EUR2015/MWh. API data of 2026-10-19. Band IE is chosen for a heat pump load of tens of GWh/yr. Replaces 100. The case names no country, so the EU average is used |
| `opex.gas` | 39.92 EUR/MWh | Eurostat `nrg_pc_203`, natural gas prices for non-household consumers, EU average (`EU27_2020`), band I4 (100 000 to 999 999 GJ/yr), `X_VAT`, 2025-S1 0.0545 and 2025-S2 0.0483 EUR/kWh, mean 0.0514 = 51.4 EUR/MWh (EUR 2025); 51.4 / 1.2875 = 39.92 EUR2015/MWh. Eurostat states the price per kWh of gross calorific value; the case does not state which heating value its fuel energy uses, so the value is exact only for a gross-value convention. Replaces 40 |
| `opex.co2` | 57.03 EUR/t | Instrat Foundation (Wojciech Przedlacki), "EU ETS 2025 summary and the beginning of 2026 auctions", 8 January 2026, https://energy.instrat.pl/en/eu-ets-2025-summary/: "The average CO2 allowance price in 2025 amounted to EUR 73.43 per tCO2 (volume-weighted average)", the 213 primary-market auctions of 2025; 73.43 / 1.2875 = 57.03 EUR2015/t. A secondary source, not the Commission or the EEA (their pages could not be opened). Replaces 80 |
| `capex.drilling` | 1239.13 EUR/m | SDE+ 2013 reference case, 2300 m doublet, 5.7 MEUR net drilling (Mijnlieff et al. 2013, EGC, slide 26), over two wells of 2300 m, taken into 2015 without escalation. Not re-opened in this check: placeholder, no verified source |
| `capex.degasser` | 1.0 MEUR | Same note: reserve for separation of hydrocarbons per doublet. Not re-opened: placeholder, no verified source |

The previous values 0.06, 0.95 and 0.67 EUR/W were cited to the April 2020 catalogue in 2015 prices; that
version was not re-opened for this check, and version 0019 (2020 and 2025 prices) is the source now.

Placeholder, no verified source (value unchanged): `capex.compression_chiller`, `absorption_chiller`
and `adsorption_chiller` 0.3 EUR/W (the DEA el and DH catalogue has no chiller or district cooling sheet; two searches found no
catalogue or peer-reviewed figure that was opened and read); `capex.production_pump` and `injection_pump` 0.5 EUR/W; `capex.heat_exchanger`
0.5 EUR/(W/K); `capex.cooler` 0.1 EUR/W; `capex.pipe` 500 EUR/m; `capex.flare`; `capex.gas_makeup`;
`capex.drilling` and `degasser` (above; DEA sheets 45.1 to 45.3 give only the whole plant, e.g. 1.9 MEUR/MW_h for 2000 m
(sheet 45.1.b) and 1.75 MEUR/MW_h (sheet 45.3), cost data in 2025 EURO, per MW of heat of the plant including heat pump; the sheets do not split wells, degasser, pumps or
exchangers, so they do not match a price per m of well or per kind); fixed opex of drilling, degasser, chillers, pumps, heat
exchanger, flare, gas makeup, cooler and pipe; `opex.chemical`, `waste_disposal` (not searched);
`revenue.heat` and `cold`; `discount_rate` 0.05 (the DEA catalogue guideline discounts reinvestments
at 4 % real, a different quantity; the European Commission Better Regulation Toolbox tool 64 text could not be opened);
`allocation.heat_cost_share`; `emissions.CO2.electricity` 300 g/kWh
(the EEA indicator page is an interactive chart that could not be read; the Umweltbundesamt page "Entwicklung der spezifischen
Kohlendioxid-Emissionen des deutschen Strommix in den Jahren 1990-2017", Climate Change 11/2018, states 528 g/kWh for 2015,
direct emissions, without the trade balance, but that is the 2015 grid and not the 2027 one the case describes, so it is not used).

The previous 100, 40 and 80 were not sourced. The energy prices are the latest real prices (2025) deflated to the 2015 price year,
the same convention as the capex above.

The compression chiller factor is a 0.3 EUR/W placeholder, not the heat pump row. `capex.injection_pump`
prices the `InjectionPump` of a plant per W of shaft power at its `nominal_flow` and `nominal_head`
(or the power curve at `nominal_flow`). The five plant dicts with an injection pump state those two design
values: `nominal_flow` 600 m3/h, the two doublets of 300 m3/h that the one plant-level pump serves, and
`nominal_head` 15.74 bar. They are the rule of `gm.study.size` (the flow of the doublets the pump serves,
and the pressure that `solve_injection_pressure` finds for the injection well at that flow, less the 10 bar
of the production wellhead as best suction, floored at zero) applied to the stored doublets and this case,
rounded to four digits. They are data of the plants, not a default of the package; the size of a plant with
other doublets rates its pump again. On `HeatingHeatPumpCoolingPlant` the pump is 0.187 MEUR of the
33.0 MEUR capex (0.57 %).

## Catalogue ids (`docs/cost-sources`)

Values of `economics.json` that have rows in [the cost catalogue](../../../docs/cost-sources/README.md), by `id`. The values
of the sample are unchanged; where they differ from the catalogue it is said here and nowhere is the sample changed.

| Key of `economics.json` | Sample value | Catalogue id | Catalogue value |
| --- | --- | --- | --- |
| `capex.heat_pump` | 0.73786 EUR/W | `heat-pump-dea-2025-10mw` | 0.737864 EUR2015/W: equal |
| `opex.fixed.heat_pump` | 0.2239 %/yr | `opex-heat-pump-dea-2025-10mw` | 2127 EUR/MW/yr over 0.95 MEUR/MW: equal |
| `capex.drilling` | 1239.13 EUR/m | `drilling-nl-2013-2300m` | 1239.1 EUR/m in 2013 prices, 1246.83 in 2015: the sample takes it into 2015 without escalation; other rows (`-3000m` 1844.74, `-4000m` 2075.37 EUR/m in 2015) are for deeper wells, the sample uses one price for every depth |
| `capex.degasser` | 1.0 MEUR | `degasser-nl-2013` | 1 MEUR in 2013, 1.00624 MEUR in 2015: same note, secondary source |
| `capex.production_pump`, `capex.injection_pump` | 0.5 EUR/W | `esp-geophires-500kw`, `injection-pump-geophires-500kw`, `injection-pump-proxy-dh-station`, `esp-unit-2019` | 0.593 and 0.733 USD/W at 500 kW, 0.0990 EUR2015/W (a DH pump station), 800000 EUR per unit: differs |
| `capex.absorption_chiller` | 0.3 EUR/W | `absorption-chiller-ecos-2023`, `-kim-2008-low`, `-kim-2008-high`, `-bigee-105kw` | 0.234, 0.328, 0.438, 0.409 EUR2015/W: inside the range |
| `capex.compression_chiller` | 0.3 EUR/W | `compression-chiller-ecos-2023` | 0.159 EUR2015/W: differs |
| `capex.adsorption_chiller` | 0.3 EUR/W | `adsorption-chiller-edinburgh-2023`, `adsorption-chiller-bigee-100-150kw` | 0.827 and 0.859 EUR2015/W: differs, the catalogue is nearly three times higher |
| `capex.heat_exchanger` | 0.5 EUR/(W/K) | `heat-exchanger-dea-2025-station` | 0.1089 EUR2015/W of duty: a different unit, not comparable |
| `capex.cooler` | 0.1 EUR/W | `dry-cooler-iea-2014-low`, `-high`, `cooling-tower-iea-2014-low`, `-high` | 0.049 to 0.107 (dry), 0.022 to 0.027 (wet) EUR/W: inside the range of the dry cooler |
| `capex.pipe` | 500 EUR/m | `pipe-dea-2025-distribution-1-5mw`, `-5-25mw`, `-transmission-0-50mw` | 636 and 1148 EUR2015/m, 49 EUR2015/MW/m: differs |
| `capex.flare`, `capex.gas_makeup` | 100000, 50000 EUR | `flare-capex`, `gas-makeup-capex` | placeholders: no verified source |
| `opex.fixed.drilling`, `degasser`, `absorption_chiller`, `adsorption_chiller`, `injection_pump`, `heat_exchanger`, `cooler`, `flare`, `gas_makeup` | 1 to 2 %/yr | `opex-fixed-drilling`, `-degasser`, `-absorption-chiller`, `-adsorption-chiller`, `-injection-pump`, `-heat-exchanger`, `-dry-cooler`, `-cooling-tower`, `-flare`, `-gas-makeup` | placeholders |
| `opex.fixed.pipe` | 0.5 %/yr | `opex-pipe-dea-2025-distribution`, `opex-pipe-dea-2025-transmission` | 1000 EUR/MW/yr, 100 EUR/MW/km/yr: different units |
| `opex.variable.chemical` | 3 EUR/kg | `chemical-scale-inhibitor`, `chemical-corrosion-inhibitor` | placeholders |
| `opex.variable.waste_disposal` | 0.2 EUR/kg | `waste-disposal`, `waste-disposal-proxy-sewage-sludge` | placeholder; proxy 0.0497 EUR2015/kg: differs |
| `revenue.heat` | 60 EUR/MWh | `heat-price-se-2019`, `heat-price-nl-2019`, `heat-price-nl-cap-2026` | 81.1, 93.5, 114.6 EUR2015/MWh: the sample is below all three |
| `revenue.cold` | 60 EUR/MWh | `cold-price-no-2017`, `cold-price-eu27-alternative-2014`, `cold-price-eu27-new-investment-2014` | 103.5, 81.2, 110.2 EUR2015/MWh: below all three |
| `discount_rate` | 0.05 | `discount-rate-financial-eu`, `discount-rate-social-eu` | 0.04 and 0.03: differs |
| `emissions.CO2.electricity` (`utilities.electricity.co2_intensity`, 300 g/kWh) | 300 g/kWh | `co2-grid-eu-2025`, `co2-grid-eu-2024` | 209.21 and 211.52 g/kWh: differs |

No catalogue row exists for `capex.boiler`, `capex.chp`, their fixed opex, `opex.electricity`, `opex.gas`, `opex.co2`
and the methane GWP: their sources are the rows of the table above in this README, not the catalogue.
The Carnot fraction 0.5 cites Frutschi (ABB Review 1996); the catalogue row `heat-pump-lorenz-dea-2025` is a Lorenz
fraction of 0.5 (DEA), which is the `lorenz_fraction` the plants state.

## Pump intake limits

The brief states neither limit, so `plants_brief/` holds the same six plants without them and `examples/hackathon.py` prints a ranking for each folder: the brief's rules only, then the standard-stage limits. Each plant file of `plants/` states two operating limits on the `esp` of every doublet (`minimum_intake_pressure` and
`maximum_gas_fraction`), which the organisers did not state. They are properties of the pump chosen, so they sit in
the plant and not in the case; a run that breaches one still runs every step with the same numbers, and
`gm.evaluate.verdict` gives a reason of kind `bound` (`gm.study.minimize` treats such a trial as infeasible).

- Maximum free gas, 0.1875 of the volume at the intake. Source: Baker Hughes, Ace Plus gas handler pumps,
  <https://www.bakerhughes.com/production/artificial-lift/electrical-submersible-pump-systems/pumps/ace-plus-gas-handler-pumps>:
  "Performance tests indicate that Ace Plus gas handler pumps can process up to 75% free gas without locking"
  and "Standard pump stages can handle only one-fourth of this amount of free gas before locking." The limit is
  75 % / 4 = 18.75 %, the manufacturer's figure for standard stages; the page was opened on 2026-11-01. A stricter
  rule of thumb of 10 % for a standard pump (Takacs, Electrical Submersible Pumps Manual, 2009, as quoted by a design
  manual site, not opened at the book) is not used.
- Minimum intake pressure, 5 bar: assumption, no verified source. The published rule found (intake pressure above the
  bubble point of the produced fluid) needs the PVT of the fluid, which the case does not give.
- Intake values of the stored plants over the first 32 days of the case (one run, 300 m3/h per doublet): lowest pressure
  7.7 bar, largest gas share 12.1 %, so neither limit rejects a stored design. The 10 % rule of thumb would.
- The limits do reject searched designs. Without them `HeatingFullCoolingPlant` searches to 3 doublets at 3319 m with an
  intake of 2.0 bar and 35.7 % free gas, and `HeatingPlant` to 2 doublets at 3275 m with 3.0 bar and 27.2 %: both break
  both limits, so the sourced gas limit alone rejects them. With the limits they search to 1 doublet at 2456 m (5.4 bar,
  16.5 %, LCTS 55.59 EUR/MWh instead of 40.29) and 2 doublets at 3234 m (6.7 bar, 14.4 %, 29.83 instead of 29.45), and the
  lowest LCTS among the designs that deliver heat and cold is now `HeatingHeatPumpCoolingPlant`, 40.34 EUR/MWh.

## Values the plants state that a module no longer defaults

A module declares no design value: each plant dict of this folder states the values below, with the value the package used as a default before, so no result changed. Where no source is given the value is an assumption of this sample, not data of the organisers or of a machine. `dN` is `d0`, `d1`, ... one per doublet.

| Name | Value | Status |
| --- | --- | --- |
| `heating_supply_pipe.roughness`, `heating_return_pipe.roughness` (and the cooling pipes) | 4.5e-5 m | cited: new commercial steel, Moody (1944), Trans. ASME 66 |
| `dN.drainage_radius` | 1000 m | assumption (the lower end of 1 to 2 km Dutch doublet spacing, Willems 2016) |
| `dN.roughness` | 4.5e-5 m | cited: new commercial steel, Moody (1944), Trans. ASME 66 (wall of the vertical wells, was inside the derivation) |
| `dN.esp.correction_factors` | [1, 0] | assumption (no calibration) |
| `dN.reservoir.skin`, `dN.sink.skin` | 0 | assumption |
| `dN.well|riser|injector.friction_correlation` | darcy_weisbach | assumption (model choice) |
| `dN.well|riser|injector.two_phase_friction_correlation` | BeggsBrill | assumption (model choice) |
| `dN.well|riser|injector.correction_factors` | [1, 0] | assumption (no calibration) |
| `dN.well|riser|injector.heat_transfer_coefficient` | 10 W/m2/K | assumption (the value of the original GEMINI well model) |
| `degasser.nominal_pressure_drop` | 14900 Pa | assumption (0.149 bar of the original GEMINI example) |
| `filters.hot|cold.nominal_pressure_drop` | 1600 Pa | assumption (0.016 bar of the original GEMINI example) |
| `filters.hot|cold.nominal_mass_flow` | 44.2033 kg/s | assumption (149 m3/h of brine at 1068 kg/m3) |
| `filters.hot|cold.clogging_pressure_drop` | 50000 Pa | assumption (0.5 bar, the limit of an old project) |
| `heat_exchanger.arrangement` | counterflow | assumption |
| `heat_exchanger.fouling_threshold`, `dN.reservoir.decline_threshold`, `dN.sink.decline_threshold` | 0.15 | assumption (alarm threshold) |
| `gas_grid.composition` | CH4 0.82495, C2H6 0.03955, C3H8 0.01275, CO2 0.01191, N2 0.11084 (mole fractions) | assumption (a measured grid gas of the original GEMINI example) |
| `flare.combustion_efficiency` | 0.98 | cited: US EPA AP-42, section 13.5 |
| `heat_pump.cop_model`, `compression_chiller.cop_model` | carnot | assumption (model choice) |
| `heat_pump.carnot_fraction`, `compression_chiller.carnot_fraction` | 0.5 | cited: H. U. Frutschi, ABB Review 5/1996 |
| `heat_pump.lorenz_fraction`, `compression_chiller.lorenz_fraction` | 0.5 | assumption (no source for a Lorenz value of its own) |
| `heat_pump.minimum_temperature_lift`, `compression_chiller.minimum_temperature_lift` | 10 K | cited: lowest lift of the machines summarised by Arpagaus et al. (2018) |
| `absorption_chiller.thermal_cop`, `chiller.thermal_cop` | 0.7 | cited: Herold, Radermacher and Klein (2016), Absorption Chillers and Heat Pumps |
| `absorption_chiller.minimum_driving_temperature`, `chiller.minimum_driving_temperature` | 353.15 K | assumption (a GEMINI operating limit of a LiBr chiller) |
| `adsorption_chiller.thermal_cop` | 0.55 | cited: Wang and Oliveira (2006), Prog. Energy Combust. Sci. 32 |
| `adsorption_chiller.minimum_driving_temperature`, `adsorption_chiller.maximum_driving_temperature` | 328.15 K, 363.15 K | assumption (a GEMINI operating range of a silica-gel machine) |
