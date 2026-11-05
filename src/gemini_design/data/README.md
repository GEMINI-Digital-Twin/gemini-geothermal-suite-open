# Data

`nl_day_ahead_2025_daily.csv`: daily mean, minimum and maximum of the 2025 Dutch
(bidding zone NL) day-ahead electricity price, EUR/MWh, by Europe/Amsterdam local date.
Source: Fraunhofer ISE Energy-Charts API,
`https://api.energy-charts.info/price?bzn=NL&start=2025-01-01&end=2025-12-31`
(downloaded 3 Nov 2026). The market is hourly until 30 Sep 2025 and 15-minute from
1 Oct 2025 (`n_values` 24 or 96 per day; 23 and 100 on the clock-change days). The
daily mean is time-weighted. Annual mean: 86.81 EUR/MWh (TenneT/EPEX report about 87).
Used by `gemini_design.prices` when `electricity_daily_prices` is 1.
