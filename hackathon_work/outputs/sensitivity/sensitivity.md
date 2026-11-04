# One-at-a-time sensitivity of the final design

Base: `n2_q300_s1.8_ua1000_z3500_co2ri`, 3983 t CO2/yr. Each row moves one input (ASSUMED spread) with everything else at the base value. "Final design" is the base pick re-simulated; "Agent pick" is a fresh rules-agent run with the changed input.
Rerun: `$env:PYTHONPATH="src"; py -3.11 -m poetry run python hackathon_work/sensitivity.py`.

| Input | Value | Final design emissions (t) | Delta (t) | Delta (%) | Hard constraints | Agent pick | Pick changed |
|---|---|---|---|---|---|---|---|
| Heating return temperature (C) | 50 (base 60) | 3958 | -25 | -0.6% | PASS | `n2_q300_s1.8_ua1000_z3250_co2ri` (4024 t) | **yes** |
| Heating return temperature (C) | 70 (base 60) | 4172 | +189 | +4.7% | PASS | `n2_q300_s1.8_ua1000_z3500_co2ri` (4172 t) | no |
| Heat pump Lorenz efficiency (-) | 0.4 (base 0.45) | 3983 | +0 | +0.0% | PASS | `n2_q300_s1.8_ua1000_z3500_co2ri` (3983 t) | no |
| Heat pump Lorenz efficiency (-) | 0.5 (base 0.45) | 3983 | +0 | +0.0% | PASS | `n2_q300_s1.8_ua1000_z3500_co2ri` (3983 t) | no |
| Absorption chiller COP (-) | 0.6 (base 0.7) | 4137 | +153 | +3.8% | PASS | `n3_q300_s1.8_ua1000_z3500_co2ri` (4099 t) | **yes** |
| Absorption chiller COP (-) | 0.8 (base 0.7) | 3874 | -109 | -2.7% | PASS | `n2_q300_s1.8_ua1000_z3500_co2ri` (3874 t) | no |
| Geothermal gradient (C/km) | 27 (base 30) | 4618 | +635 | +15.9% | PASS | `n2_q300_s1.8_ua1000_z3750_co2ri` (4018 t) | **yes** |
| Geothermal gradient (C/km) | 33 (base 30) | 3971 | -12 | -0.3% | PASS | `n2_q300_s1.8_ua1000_z3000_co2ri` (4104 t) | **yes** |
| Brine specific heat (J/(kg K)) | 4000 (base 4100) | 4085 | +102 | +2.6% | PASS | `n2_q300_s1.8_ua1000_z3250_co2ri` (4344 t) | **yes** |
| Brine specific heat (J/(kg K)) | 4200 (base 4100) | 3904 | -80 | -2.0% | PASS | `n2_q300_s1.8_ua1000_z3500_co2ri` (3904 t) | no |

Pick changes in 5 of 10 cases: heating_return_T=50, absorption_COP=0.6, gradient=27, gradient=33, brine_cp=4000.

Why the base pick loses where the pick changes:

- Heating return temperature = 50: parsimony rule not met: ranks better than n2_q300_s1.8_ua1000_z3250_co2ri (decided by emissions_t: 3958 vs 4024); deeper 3250 -> 3500 m: emissions +1.634% (needs >= 5% beyond the tie tolerance), marginal abatement 0.066 t CO2/yr per extra metre drilled
- Absorption chiller COP = 0.6: superseded by n3_q300_s1.8_ua1000_z3500_co2ri: ranks better than n2_q300_s1.8_ua1000_z3500_co2ri (decided by external_gas_fuel_GWh: 0.00468 vs 0.1577, beyond its tie tolerance); extra doublet: external gas +97.0%, emissions +0.9% (needs >= 5% on either, beyond the tie tolerance)
- Geothermal gradient = 27: not evaluated: the depth ladder stopped elsewhere (each step must cut emissions >= 5%)
- Geothermal gradient = 33: not evaluated: the depth ladder stopped elsewhere (each step must cut emissions >= 5%)
- Brine specific heat = 4000: parsimony rule not met: ranks better than n2_q300_s1.8_ua1000_z3250_co2ri (decided by emissions_t: 4085 vs 4344); deeper 3250 -> 3500 m: emissions +5.962% (needs >= 5% beyond the tie tolerance), marginal abatement 0.259 t CO2/yr per extra metre drilled - within the tie tolerance of the threshold, counts as NOT met (marginal sensitivity case)
