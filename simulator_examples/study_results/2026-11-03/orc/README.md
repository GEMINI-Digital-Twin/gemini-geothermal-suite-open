# Can the plant also make electricity? ORC study (3 Nov 2026)

**Short answer:** it is physically possible, but it does not pay and it raises CO2.
On the final pick (KNMI 2025) the best ORC adds €0.07/MWh (0.5 MW_e) and about 900 t CO2 a year;
1 MW_e adds €1.14/MWh and 1,350 t. Deeper wells do not change that. It pays only if three
optimistic assumptions all hold at once, and even then it adds about 2,100 t CO2.
The ORC is now a neutral option in the toolkit and the agent's tools, so the agent can test it.

## Model

- `gemini_model.orc.OrganicRankineCycle` (registry type `orc`): air-cooled binary unit. Net
  power = 0.45 x the brine's exergy drop against the condensing temperature (air + 15 K), with a
  floor on the brine outlet (condensing + 20 K, and the 40 K cap), a rating cap, 30 % minimum load
  and a part-load penalty.
- Calibration (`run_orc_cycle_check.py`, `cycle_check.csv`): a CoolProp subcritical cycle (best of
  seven fluids, turbine 0.82, pump 0.70, generator 0.96, 5 K pinch, fans 1.5 % of heat rejected)
  gives a second-law fraction of 0.45 to 0.54 at 100 to 140 degC. So 0.45 matches at about 100 degC
  and is conservative by about 15 % at 140 degC. Below 90 degC the cycle drops to 0.33 to 0.45, so
  the model is optimistic there.
- Cycle numbers at 300 m3/h, brine cooled 40 K, air at 10 degC: 102 degC (3.1 km) gives 7.2 % net,
  about 1.0 MW_e. 128 degC (4.0 km) gives 11 %, about 1.6 MW_e. 141.5 degC (4.5 km) gives 13 %,
  about 1.9 MW_e.
- In the plant the ORC sits after the district HEX and heat pump. It takes only brine heat the
  district did not use, down to the 40 K cap. Its power offsets plant electricity, and any surplus
  is exported at €60/MWh. The dispatcher picks each day's flow, so it pumps more brine when the
  power is worth it.
- Gate: the brine and grid balances include the ORC. A new sanity check enforces efficiency below
  Carnot (inlet vs air) and power below heat in. The Solver cross-check compares at the ORC inlet.
  CAPEX is €3,000/kW_e (literature 2,000 to 4,500).

## Why it does not pay here

1. **The 40 K cap is shared.** The district needs the full 40 K in winter. At 3.1 km the brine is
   102 degC, below the 103 degC an ORC ahead of the HEX would need to leave for the 100 degC supply,
   so a topping cascade gets 0 MW. At 4.5 km a topping ORC (1.3 MW_e) leaves only 0.5 MW_th for the
   district (`cascade.csv`). The ORC can only use spare summer capacity.
2. **Pumping eats the output.** One doublet at 300 m3/h needs 0.74 MW of ESP and injection pumping.
   An ORC on its full 40 K at 102 degC makes 0.76 to 0.96 MW_e, depending on the air temperature.
   Most extra brine pumped for power costs almost as much electricity as it yields.
3. **Summer power is exported at €60/MWh**, because the CHP already covers the plant's own use.
4. **More brine means more co-produced gas.** The gas is burned (CHP, boiler or flare) and its CO2
   is counted, so ORC designs emit 900 to 2,800 t more. Even crediting exports at 0.3 kg/kWh only
   offsets about 700 t.

## Results (KNMI 2025, staggered stops; `runs.md`)

| Case | EUR/MWh | t CO2 | ORC MWh_e |
|---|---|---|---|
| Pick, no ORC | 35.71 | 4,345 | 0 |
| Pick + ORC 0.5 MW | 35.78 | 5,242 | 2,725 |
| Pick + ORC 1 MW | 36.85 | 5,696 | 3,513 |
| Pick + ORC 2 MW | 39.04 | 5,557 | 3,024 |
| 3.5 km, no ORC / + 1 MW | 37.67 / 38.67 | 4,080 / 5,929 | 0 / 5,016 |
| 4.0 km, no ORC / + 1 MW | 40.47 / 40.95 | 4,094 / 6,098 | 0 / 6,759 |
| 4.5 km, no ORC / + 1 MW | 43.27 / 43.32 | 4,091 / 6,016 | 0 / 7,624 |
| 3 doublets at 4.5 km, no ORC / + 4 MW | 59.11 / 63.57 | 4,004 / 10,680 | 0 / 23,184 |

All of these designs meet every hard rule. A larger ORC runs fewer hours: the 2 MW unit makes less
power than the 1 MW unit because it is often below its 30 % minimum load.

Sensitivity for the pick + 1 MW, each change compared with the pick under the same assumption:
- Export price equal to the €120 import price: €35.58, the same as the pick at €35.58. That is
  break-even.
- ORC cost €2,000/kW: €36.17 against €35.71.
- Cycle at the top of its range (0.54): €36.40 against €35.71.
- All three together: €34.02 against €35.58, so €1.56/MWh cheaper, but with 6,524 t against
  4,392 t CO2.

## Verdict

Keep the ORC as an option the agent can explore and reject, and as a "we checked" line in the
report. Don't add it to the pick. It only becomes interesting with brine above about 130 degC and
no 40 K cap, or with a high power price.

## Fixes after the agent reruns (3 Nov, evening)

- `geothermal_share_of_heat` counted the brine heat the ORC turns into power as district
  heat, so ORC designs showed up to 192 %. The ORC heat is now left out, and the share stays at
  or below 100 %. Costs, CO2 and every number above are unchanged (the study was rerun and its
  tables came out identical).
- When an installed ORC never runs, the agent now sees `orc_electricity_mwh: 0`, the full-load
  hours, the ORC CAPEX and a note saying the same design without it is cheaper. A zero output is
  a real dispatch result, not a bug: in those designs (for example 2 doublets at 3.0 km without
  CHP) pumping the extra brine every day costs more than the ORC's power is worth.
