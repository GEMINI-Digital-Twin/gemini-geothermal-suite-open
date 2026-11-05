# Pooled best design per design case and oracle world

| case | oracle world | grid best | pooled best | EUR/MWh | found by |
|---|---|---|---|---|---|
| B1 | `{}` | 2D-3100m-boiler-electric-chp-screw 35.158 | 2D-3010m-boiler-electric-chp-screw-orc0.35-ret45/29 | 31.88 | gpt-6.1-sol r1 |
| B4 | `{"co2_price_eur_per_t": 180, "electricity_price_eur_per_mwh": 70, "gas_price_eur_per_mwh": 90}` | 2D-3100m-boiler-electric-chp-screw 37.722 | 2D-3100m-boiler-electric-chp-screw-orc0.05-ret40/28 | 34.81 | gpt-6.1-sol r2 |
| B4 | `{"co2_price_eur_per_t": 250, "electricity_price_eur_per_mwh": 120, "gas_price_eur_per_mwh": 120}` | 2D-3100m-boiler-electric-chp-screw 41.519 | 2D-3175m-boiler-electric-chp-screw-orc0.2-ret45/30 | 38.39 | gpt-6.1-sol r1 |
| B5a | `{"co2_price_eur_per_t": 50, "electricity_price_eur_per_mwh": 200, "gas_price_eur_per_mwh": 30}` | 1D-3100m-boiler-electric-chp-tower 33.015 | 1D-3050m-boiler-electric-chp-tower-ret45/30 | 31.18 | deepseek-v4.1-flash r1 |
| B5b | `{}` | 2D-3100m-boiler-electric-chp-screw 35.158 | 2D-3050m-boiler-electric-chp-screw-ret40/30 | 33.67 | gpt-6.1-sol r3 |
