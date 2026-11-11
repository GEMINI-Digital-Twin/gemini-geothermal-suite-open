# KNMI hourly weather, De Bilt (station 260), 2021-01-01 to 2026-10-17

- Source: KNMI, hourly station data, station 260 De Bilt,
  https://www.knmi.nl/nederland-nu/klimatologie/uurgegevens
  (file `uurgeg_260_2021-2030.zip`, downloaded 2026-10-19).
- Licence: KNMI open data, free reuse with attribution "KNMI"; the KNMI Data Platform states
  CC BY 4.0, see the link above.
- `knmi_260_debilt_hourly_2021_2026.csv` is derived from the KNMI file: time_utc_start
  (date + HH - 1 h, UT), T_degC, TD_degC, FH_m_s, Q_J_cm2, U_pct, P_hPa, RH_mm, converted from
  KNMI's 0.1 units. KNMI notes the series are inhomogeneous (station relocations, method changes).
