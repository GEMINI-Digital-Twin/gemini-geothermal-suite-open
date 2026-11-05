# Measured weather

`knmi_etmgeg_240_1991_2025.txt`: KNMI daily station data for Amsterdam Schiphol (station 240),
1 January 1991 to 31 December 2025, with KNMI's original header. Source: Royal Netherlands
Meteorological Institute (KNMI), open data,
https://www.knmi.nl/nederland-nu/klimatologie/daggegevens
(downloaded 1 Nov 2026 from
https://cdn.knmi.nl/knmi/map/page/klimatologie/gegevens/daggegevens/etmgeg_240.zip and trimmed
to 1991-2025). Read with `gemini_design.climate.read_knmi_daily(path, year)`; the 2027 demand
profiles are aligned by day of year and 29 February is dropped.

To refresh (PowerShell):

    curl.exe -L -o etmgeg_240.zip https://cdn.knmi.nl/knmi/map/page/klimatologie/gegevens/daggegevens/etmgeg_240.zip
