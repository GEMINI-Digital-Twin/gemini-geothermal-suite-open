# One-at-a-time sensitivity of the final design

Base: `n2_q300_s1.8_ua1000_z3250_co2ri`, 4252 t CO2/yr. Each row moves one input (ASSUMED spread) with everything else at the base value. "Final design" is the base pick re-simulated; "Agent pick" is a fresh rules-agent run with the changed input.
Rerun: `$env:PYTHONPATH="src"; py -3.11 -m poetry run python hackathon_work/sensitivity.py`.

| Input | Value | Final design emissions (t) | Delta (t) | Delta (%) | Hard constraints | Agent pick | Pick changed |
|---|---|---|---|---|---|---|---|
| Heating return temperature (C) | 50 (base 60) | 4024 | -228 | -5.4% | PASS | `n2_q300_s1.8_ua1000_z3250_co2ri` (4024 t) | no |
| Heating return temperature (C) | 70 (base 60) | 5012 | +761 | +17.9% | PASS | `n2_q300_s1.8_ua1000_z3500_co2ri` (4172 t) | **yes** |
| Heat pump Lorenz efficiency (-) | 0.4 (base 0.45) | 4289 | +37 | +0.9% | PASS | `n2_q300_s1.8_ua1000_z3250_co2ri` (4289 t) | no |
| Heat pump Lorenz efficiency (-) | 0.5 (base 0.45) | 4243 | -9 | -0.2% | PASS | `n3_q300_s1.8_ua1000_z3500_co2ri` (3979 t) | **yes** |
| Absorption chiller COP (-) | 0.6 (base 0.7) | 4402 | +150 | +3.5% | PASS | `n2_q300_s1.8_ua1000_z2750_co2ri` (6602 t) | **yes** |
| Absorption chiller COP (-) | 0.8 (base 0.7) | 4137 | -114 | -2.7% | PASS | `n2_q300_s1.8_ua1000_z3500_co2ri` (3874 t) | **yes** |
| Geothermal gradient (C/km) | 27 (base 30) | 5499 | +1247 | +29.3% | PASS | `n2_q300_s1.8_ua1000_z3750_co2ri` (4018 t) | **yes** |
| Geothermal gradient (C/km) | 33 (base 30) | 3963 | -289 | -6.8% | PASS | `n2_q300_s1.8_ua1000_z3000_co2ri` (4104 t) | **yes** |
| Brine specific heat (J/(kg K)) | 4000 (base 4100) | 4344 | +93 | +2.2% | PASS | `n2_q300_s1.8_ua1000_z3000_co2ri` (5231 t) | **yes** |
| Brine specific heat (J/(kg K)) | 4200 (base 4100) | 4169 | -83 | -2.0% | PASS | `n2_q300_s1.8_ua1000_z3500_co2ri` (3904 t) | **yes** |

Pick changes in: heating_return_T=70, hp_eta_lorenz=0.5, absorption_COP=0.6, absorption_COP=0.8, gradient=27, gradient=33, brine_cp=4000, brine_cp=4200.
