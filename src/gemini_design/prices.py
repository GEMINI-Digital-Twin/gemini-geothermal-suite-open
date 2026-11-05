"""Daily electricity prices from the 2025 Dutch day-ahead market.

With ``assumptions["electricity_daily_prices"] = 1`` each day of the year
gets its own import and export price instead of the flat
``electricity_price_eur_per_mwh`` / ``electricity_export_price_eur_per_mwh``:

- import = day-ahead daily mean + (flat import price - annual day-ahead mean),
  i.e. the grid fees and taxes stay a fixed adder;
- export = day-ahead daily mean x (flat export price / annual day-ahead mean).

Both keep their annual means, so a plant with a flat electricity profile
pays the same over the year; one that shifts electricity use or generation
between days (electric boiler, CHP, ORC, storage) sees the spread. Daily
means hide the hourly spread inside a day (the dispatch is daily).
Data: ``gemini_design/data/nl_day_ahead_2025_daily.csv`` (Energy-Charts, see the
README there). 2025 and the 2027 demand year both have 365 days; days are
matched by month and day.
"""

from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parent / "data" / "nl_day_ahead_2025_daily.csv"


def day_ahead_daily(path=DATA):
    """Return the daily day-ahead table (date, mean/min/max EUR/MWh, n_values)."""
    table = pd.read_csv(path, parse_dates=["date"])
    if len(table) != 365:
        raise ValueError(f"expected 365 days of prices, got {len(table)}")
    return table


def daily_prices(demand, assumptions, path=DATA):
    """Return (import, export) EUR/MWh arrays aligned with ``demand`` rows, or None if off."""
    if not round(float(assumptions.get("electricity_daily_prices", 0.0))):
        return None
    table = day_ahead_daily(path)
    by_day = {(d.month, d.day): p for d, p in zip(table["date"], table["mean_eur_per_mwh"])}
    wholesale = np.array([by_day[(d.month, d.day)] for d in pd.to_datetime(demand["date"])])
    mean = float(table["mean_eur_per_mwh"].mean())
    imp = wholesale + (assumptions["electricity_price_eur_per_mwh"] - mean)
    exp = wholesale * (assumptions["electricity_export_price_eur_per_mwh"] / mean)
    # floor: a low import mean must not give negative import prices or export above import
    # (at the default 120 EUR/MWh mean the floor never binds)
    imp = np.maximum(imp, np.maximum(exp, 0.0))
    return imp, exp
