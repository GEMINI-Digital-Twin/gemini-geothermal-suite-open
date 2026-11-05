"""Daily outdoor air temperature for the heat-rejection side of the plant.

The brief gives no site and no weather. A fixed 30 degC cooling-water
temperature (``ASSUMPTIONS["cooling_water_c"]``) is a design-day value; on
most cooling days the air is far colder. This module reads a measured or
typical year of outdoor temperature and adds it to the demand table as
``ambient_c`` (one value per day), which :func:`gemini_design.annual.run_year`
passes to the plant. The demand columns are never changed.

Supported sources (the data are not shipped with the code, see each licence):

- KNMI daily station data (``etmgeg_<station>.txt``, open data, KNMI
  https://www.knmi.nl/nederland-nu/klimatologie/daggegevens): columns
  ``TG`` (daily mean) and ``TX`` (daily max) in 0.1 degC.
- EnergyPlus weather files (``.epw``, hourly dry-bulb in column 7), for
  example the ASHRAE IWEC typical year for Amsterdam Schiphol (WMO 062400),
  https://energyplus.net/weather. IWEC data may not be redistributed.

The demand profiles are for 2027, so a typical year (or a measured one) is
aligned by day of year; 29 February is dropped.

Both readers also return the air wet-bulb temperature (Stull 2011, from
dry-bulb and relative humidity), which sets a wet cooling tower's outlet.
The EPW reader takes it hour by hour; the KNMI reader takes it at the
daily maximum temperature with the daily minimum humidity (and at the
daily mean with the mean humidity).
"""

from pathlib import Path

import numpy as np
import pandas as pd

STATISTICS = ("max", "mean")


def wet_bulb_c(t_c, rh_percent):
    """Air wet-bulb temperature (degC) from dry-bulb (degC) and relative humidity (%).

    Stull, R. (2011), "Wet-bulb temperature from relative humidity and air
    temperature", J. Appl. Meteor. Climatol. 50, 2267-2269 (sea-level
    pressure; within about 1 K for RH 5-99 % and -20 to 50 degC).
    """
    t = np.asarray(t_c, dtype=float)
    rh = np.clip(np.asarray(rh_percent, dtype=float), 5.0, 99.0)
    return (
        t * np.arctan(0.151977 * np.sqrt(rh + 8.313659))
        + np.arctan(t + rh)
        - np.arctan(rh - 1.676331)
        + 0.00391838 * rh**1.5 * np.arctan(0.023101 * rh)
        - 4.686035
    )


def read_epw_daily(path):
    """Return a 365-row DataFrame from an EPW file.

    Columns: month, day, mean, max, min (dry-bulb, degC), wet_bulb_mean and
    wet_bulb_max (degC, from the hourly dry-bulb and relative humidity).
    """
    rows = []
    for line in Path(path).read_text(encoding="latin-1").splitlines()[8:]:
        f = line.split(",")
        if len(f) > 6:
            rh = float(f[8]) if len(f) > 8 else float("nan")
            rows.append((int(f[1]), int(f[2]), float(f[6]), rh))
    hourly = pd.DataFrame(rows, columns=["month", "day", "t", "rh"])
    groups = hourly.groupby(["month", "day"], sort=True)
    daily = groups["t"].agg(["mean", "max", "min"])
    if hourly["rh"].notna().all():
        hourly["wb"] = wet_bulb_c(hourly["t"], hourly["rh"])
        groups = hourly.groupby(["month", "day"], sort=True)
        daily["wet_bulb_mean"] = groups["wb"].mean()
        daily["wet_bulb_max"] = groups["wb"].max()
    daily = daily.reset_index()
    return daily[~((daily["month"] == 2) & (daily["day"] == 29))].reset_index(drop=True)


def read_knmi_daily(path, year):
    """Return a 365-row DataFrame (month, day, mean, max, min in degC) from a KNMI etmgeg file."""
    lines = Path(path).read_text(encoding="latin-1").splitlines()
    header = next(i for i, ln in enumerate(lines) if ln.lstrip().startswith("# STN,YYYYMMDD"))
    names = [c.strip() for c in lines[header].lstrip("# ").split(",")]
    records = [ln.split(",") for ln in lines[header + 1 :] if ln.strip() and not ln.startswith("#")]
    df = pd.DataFrame(records, columns=names[: len(records[0])])
    df["date"] = pd.to_datetime(df["YYYYMMDD"].str.strip(), format="%Y%m%d")
    df = df[df["date"].dt.year == int(year)]

    def col(name, scale=1.0):
        return pd.to_numeric(df[name].str.strip()).to_numpy() * scale

    out = pd.DataFrame(
        {
            "month": df["date"].dt.month.to_numpy(),
            "day": df["date"].dt.day.to_numpy(),
            "mean": col("TG", 0.1),
            "max": col("TX", 0.1),
            "min": col("TN", 0.1),
        }
    )
    if {"UG", "UN"} <= set(df.columns):
        out["wet_bulb_mean"] = wet_bulb_c(out["mean"], col("UG"))
        out["wet_bulb_max"] = wet_bulb_c(out["max"], col("UN"))
    out = out[~((out["month"] == 2) & (out["day"] == 29))].reset_index(drop=True)
    if len(out) != 365:
        raise ValueError(f"KNMI file has {len(out)} days for {year}, expected 365")
    return out


def with_climate(demand, daily_weather, statistic="max"):
    """Return a copy of ``demand`` with an ``ambient_c`` column, aligned by day of year.

    ``statistic`` picks the daily ``max`` (conservative: the chiller and the
    free-cooling heat exchanger must work through the warmest hour) or the
    daily ``mean``.
    """
    if statistic not in STATISTICS:
        raise ValueError(f"statistic must be one of {STATISTICS}, got '{statistic}'")
    if len(daily_weather) != len(demand):
        raise ValueError(f"weather has {len(daily_weather)} days, demand has {len(demand)}")
    dates = pd.to_datetime(demand["date"])
    weather = daily_weather.reset_index(drop=True)
    if not (
        (weather["month"].to_numpy() == dates.dt.month.to_numpy()).all()
        and (weather["day"].to_numpy() == dates.dt.day.to_numpy()).all()
    ):
        raise ValueError("weather days do not line up with the demand days")
    out = demand.copy()
    out["ambient_c"] = weather[statistic].to_numpy(dtype=float)
    out["ambient_mean_c"] = weather["mean"].to_numpy(dtype=float)
    if f"wet_bulb_{statistic}" in weather:
        out["wet_bulb_c"] = weather[f"wet_bulb_{statistic}"].to_numpy(dtype=float)
    return out


def synthetic_year(mean_c=10.5, amplitude_k=7.5, warmest_day=200, daily_range_k=8.0, rh=75.0):
    """Return a smooth 365-day weather table (same columns as the readers) for tests and demos.

    A cosine year around ``mean_c`` peaking on day ``warmest_day``, with the
    daily max ``daily_range_k / 2`` above the mean. The defaults are close to
    De Bilt's 1991-2020 normals; this is not measured weather.
    """
    days = pd.date_range("2027-01-01", periods=365, freq="D")
    doy = np.arange(1, 366)
    mean = mean_c + amplitude_k * np.cos(2 * np.pi * (doy - warmest_day) / 365.0)
    out = pd.DataFrame(
        {
            "month": days.month,
            "day": days.day,
            "mean": mean,
            "max": mean + daily_range_k / 2,
            "min": mean - daily_range_k / 2,
        }
    )
    out["wet_bulb_mean"] = wet_bulb_c(out["mean"], rh)
    out["wet_bulb_max"] = wet_bulb_c(out["max"], rh - 15.0)
    return out
