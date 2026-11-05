---
name: geothermal-subsurface
description: Reservoir temperature/pressure vs depth, doublet capacity, flow and 40 K limits, well pumping, thermal breakthrough, and the deep-wells-vs-heat-pump trade-off. Read before choosing well depth or number of doublets.
---
# Geothermal subsurface rules

- Reservoir temperature: T = 12 C + 30 C/km x depth. 2.5 km -> 87 C; 3.1 km -> 105 C. Wellhead is ~1-3 K lower (wellbore heat loss); get it from `well_performance`.
- Pressure is hydrostatic (~0.1 bar/m). Use `reservoir_at_depth`.
- One doublet = one producer + one injector, same reservoir, equal volumes (volume balance).
- Flow per active doublet: 50-300 m3/h (hard limits). Brine may cool at most 40 K (producer -> injector).
- Max heat per doublet ~ Q x rho x cp x 40 K: about 13.7 MW at 300 m3/h. So 30 MW peak heating needs 2-3 doublets, or extra heat from a heat pump/boiler.
- Supply must be 100 C. If wellhead < ~103 C, direct heat exchange cannot reach 100 C: either drill deeper (>= ~3.1 km) or add a heat pump/boiler to lift the last degrees.
- Trade-off to evaluate with tools (never guess): deeper wells cost more to drill (~2,000 EUR/m) but remove heat-pump CAPEX and electricity. Compare with `search_designs`; test drilling-cost sensitivity with `uncertainty_analysis`.
- Pumping: ESP lifts brine to a pressurised surface loop; injection pump pushes cooled brine back. Both use eta = 70 %. Pump power grows ~ with flow^1.3-2.
- Thermal breakthrough: keep it beyond the 30-year life (checked automatically at the design spacing).
- 330 operating days per doublet: the geothermal SOURCE can be down 35 days; the system must still meet demand all 365 days (staggered maintenance and/or backup).
