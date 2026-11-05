# What each model picked, on our basis and through our 13 stress tests

Official = the benchmark's basis (official profiles); KNMI 2025 = our headline basis (CO2 at EUR 80/t inside the LCOE).

| model | question | design | boiler MW | official EUR/MWh (reported) | KNMI 2025 EUR/MWh | CO2 t/yr | stress tests met | failed |
|---|---|---|---|---|---|---|---|---|
| Our pick | headline | 2D-3200m-boiler-electric-chp-aircooled-fc-ates3 | 33 | nan | 36.35 | 4269 | 13/13 |  |
| GPT-6.1 Sol | B1 r1 | 2D-3010m-boiler-electric-chp-screw-orc0.35-ret45/29 | 0.25 | 31.84 (31.84) | 31.97 | 5092 | 4/13 | producer 1.5 K cooler (378.3 MWh); gradient 29 degC/km (2949.1 MWh); low reservoir (28.1 degC/km, 100 mD) (8118.1 MWh); whole source down 35 days (summer) (2144.5 MWh); whole source down 35 days from the heating peak (19129.8 MWh); KNMI 2020, cooling +10 % (92.8 MWh); heating and cooling +10 % (263.2 MWh); smaller HEX (1.45 MW/K, ~3 K approach) (694.5 MWh); smaller HEX and producer 1.5 K cooler (2162.9 MWh) |
| GPT-6.1 Terra | B5b r1 | 2D-3100m-boiler-electric-chp-screw-orc0.4-esp250v-ret45/28 | 0 | 32.32 (32.32) | 32.47 | 5438 | 4/13 | producer 1.5 K cooler (0.2 MWh); gradient 29 degC/km (2371.0 MWh); low reservoir (28.1 degC/km, 100 mD) (7872.9 MWh); whole source down 35 days (summer) (2354.5 MWh); whole source down 35 days from the heating peak (19339.8 MWh); KNMI 2020, cooling +10 % (92.8 MWh); heating and cooling +10 % (287.2 MWh); smaller HEX (1.45 MW/K, ~3 K approach) (319.7 MWh); smaller HEX and producer 1.5 K cooler (1426.0 MWh) |
| GLM 5.3 | B1 r1 | 2D-3050m-boiler-electric-chp-screw-esp250v-retref/30 | 15 | 33.58 (33.58) | 33.61 | 4781 | 10/13 | whole source down 35 days from the heating peak (6739.8 MWh); KNMI 2020, cooling +10 % (92.8 MWh); heating and cooling +10 % (92.8 MWh) |
| DeepSeek V4.1 Flash | B1 r2 | 1D-3040m-boiler-electric-chp-screw-2xB-ret45/28 | 15 | 33.43 (33.43) | 33.46 | 9862 | 10/13 | whole source down 35 days from the heating peak (6739.8 MWh); KNMI 2020, cooling +10 % (92.8 MWh); heating and cooling +10 % (284.5 MWh) |
| Qwen 3.8 27B | B1 r2 | 1D-3500m-boiler-electric-chp-screw-2xB | 30 | 36.11 | 36.14 | 9845 | 11/13 | KNMI 2020, cooling +10 % (92.8 MWh); heating and cooling +10 % (92.8 MWh) |
| GPT-6 Luna | B1 r1 | 1D-3000m-boiler-electric-chp-screw-2xB | 30 | 35.65 (35.65) | 35.68 | 10325 | 11/13 | KNMI 2020, cooling +10 % (92.8 MWh); heating and cooling +10 % (92.8 MWh) |
| DeepSeek V4.1 Flash | brief r1 | 2D-3000m-boiler-electric-chp-screw-fc-3xB-retref/30 | 15 | 35.89 | 35.07 | 5076 | 11/13 | whole source down 35 days from the heating peak (6739.8 MWh); heating and cooling +10 % (30.4 MWh) |
| GPT-6.1 Sol | brief r1 (candidate) | 2D-3075m-boiler-electric-chp-screw-fc-orc0.05-esp220v-ret45/30 | 30 | 35.03 | 34.29 | 4495 | 12/13 | heating and cooling +10 % (30.4 MWh) |
