# Cross-check of our doublet against TNO ThermoGIS (2 Nov 2026)

Author: Sa'eed Telvari

**Result.** TNO's ThermoGIS (pyThermoGIS 3.0.3, DoubletCalc1D engine), run on our
reservoir at the pick's 3,100 m with our assumptions, agrees with our GEMINI doublet
within 6% on pump pressure and pump power, and within 6% on well spacing. Its heat output
is 12.6 MW against our 14.35 MW per doublet at 300 m³/h. Two definitions explain all of
that gap (to 0.4%), and the one that matters, brine heat capacity, moves our headline by
only €0.21/MWh.

Script: `simulator_examples/run_thermogis_crosscheck.py` (needs its own venv, see its
docstring). Raw output: `thermogis_runs.csv`, `run_info.json`. Run on Sa'eed's PC
(Windows 11, Python 3.12), because TNO's package index is not reachable from the cloud.

## One doublet at 3,100 m, 300 m³/h

ThermoGIS case `matched_brief_salinity`: our temperatures, 40 K brine cool-down, 70% pump
efficiency, skin 0, steel-casing roughness, flow capped at 300 m³/h, brine salinity set to
the brief's ~43 g/kg (1,030 kg/m³ brine). Porosity 0.20 (not in the brief; 0.15 and 0.25
change nothing but the spacing by ±1%).

| Quantity | GEMINI (ours) | ThermoGIS | Difference |
|---|---|---|---|
| Production temperature at wellhead | 102.4 °C | 103.0 °C | +0.6 K |
| Injection temperature | 62.4 °C at full load (40 K below wellhead) | 65.0 °C (40 K below reservoir) | definition |
| Heat to the plant | 14.35 MW | 12.56 MW | −12.5%, explained below |
| Total pump pressure | 62.3 bar (ESP 42.8 + injection 19.5) | 58.5 bar | −6% |
| Pump electricity | 0.74 MW | 0.70 MW (12.56 MW / COP 18.0) | −6% |
| Well spacing | 1,200 m (Fimbul runs, no breakthrough in 30 yr) | 1,272 m (≤1% cooling in 50 yr) | +6% |
| CAPEX per doublet | 18.4 M€ (wells 12.9, surface 3.0, lined casing 2.5) | 23.9 M€ | +30% |

**The heat gap.** ThermoGIS limits the cool-down to 40 K below the *reservoir*
temperature (105 → 65 °C, ΔT 38.0 K), while we cool 40 K below the *wellhead* temperature
(−5.4%). And ThermoGIS uses Batzle-Wang brine properties at temperature (ρ ≈ 990–1,010
kg/m³, cp ≈ 4.0 kJ/kg·K, ρ·cp ≈ 3.99 MJ/m³·K), while we use the brief's 1,030 kg/m³ with
pure-water cp 4,180 J/kg·K (4.31 MJ/m³·K, −7.4%). Correcting for both:
12.56 × 40/37.96 × 4.31/3.99 = 14.30 MW, against our 14.35 MW.

**What that means for our numbers.** The ΔT definition is a choice (the brief limits
brine cooling to 40 K and we apply it across the plant). The heat capacity is a real
correction: 43 g/kg brine has cp ≈ 4.0 kJ/kg·K, not 4.18. Rerunning the final pick
(KNMI 2025, staggered stops, 33 MW boiler) in our toolkit with a lower cp:

| brine cp (J/kg·K) | LCOE (€/MWh) | CO₂ (t/yr) | Demand met |
|---|---|---|---|
| 4,180 (report) | 35.71 | 4,345 | yes |
| 4,000 (ThermoGIS at brief salinity) | 35.92 | 4,510 | yes |
| 3,900 | 36.05 | 4,615 | yes |

The boiler and CHP fill the slightly smaller geothermal share; no hard rule is broken.

**CAPEX.** ThermoGIS's NL base-case costs give 23.9 M€ per doublet against our 18.4 M€.
The main differences are its 15% contingency, a larger plant cost (3 M€ + 300 €/kW
against our 3 M€ per doublet) and deviated wells (1.1 × depth along hole). Pricing both
doublets at the ThermoGIS figure adds about 11 M€, or roughly €7.5/MWh (6% discount rate,
30 years, 2% O&M). That would put the pick near €43/MWh, still about 27% below the
€59.3/MWh gas-boiler-and-chiller reference. Our Monte Carlo already samples a right-skewed
well-cost factor; ThermoGIS's number is a useful conservative bound.

## Depth sweep (2,000–3,600 m, same settings, default salinity)

ThermoGIS's geothermal-only unit technical cost is lowest at 2,400–2,600 m
(6.47 ct/kWh) and 6.89 ct/kWh at 3,100 m (+6%). ThermoGIS values heat in MWh only, not
its temperature. Our pick goes to 3,100 m because 103 °C brine meets the 100 °C supply
temperature directly, with no heat pump or boiler top-up; our own 600-design screen,
which prices that upgrade, picks 3,100 m. From 2,800 m down, flow reaches the 300 m³/h cap;
shallower doublets are limited by the pump pressure.

## Notes on pyThermoGIS 3.0.3 found during the run

- `roughness` is read in milli-inch (the Java code multiplies by 2.54e-5 m), although the
  docstring says mm. The script passes 0.045 mm as 1.77 milli-inch.
- `Aquifer.depth` is the top of the reservoir; the script passes midpoint − 50 m.
- Salinity is a mass fraction from `surface_salinity + salinity_gradient × depth` in ppm
  and ppm/m (not g/L). The default 46.67 ppm/m gives 142 g/kg at 3,050 m, about three times
  the brief's brine; that lowers power 4.6% and raises pump pressure from 58.5 to 74.2 bar
  (case `matched`).
- `opex` is reported with a negative sign; `hprod` is discounted lifetime MWh, not TJ/yr;
  NPV jumps at 2,700 and 3,200 m because of the built-in depth bands of the UTC cut-off.
  We use UTC, not NPV.
- `tno_defaults` (100 K cool-down to 30 °C, TNO costs) gives 24.8 MW and 5.13 ct/kWh; it
  ignores the brief's 40 K limit, so it is shown only for reference.
