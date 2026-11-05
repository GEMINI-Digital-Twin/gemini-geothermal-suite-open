"""Cooling over 2027 day by day: free cooling from the wet bulb, absorption on spare hot brine, electric chillers for the rest."""
from functools import lru_cache

import numpy as np
import pandas as pd

from geo.common import PROJECT
from geo.demand import cold, scaled

T_COLD_SUPPLY, T_COLD_RETURN = 20.0, 26.0   # district-cooling supply and return, C; return assumed
TOWER_APPROACH_K = 4.0                        # cooling-tower water above the wet bulb, K; assumed
COP_ABSORPTION = 0.75                         # single-effect LiBr absorption chiller; US DOE 2017, see SOURCES.md
COP_ELECTRIC = 7.0                            # electric chiller at 20 C chilled water; assumed, fraction of Carnot
AUX_KW_PER_KW_COLD = 0.03                     # tower fans and pumps per kW of cold; assumed
WEATHER_YEAR = 2024                           # KNMI De Bilt weather year laid over the 2027 calendar
KNMI = PROJECT / "data" / "raw" / "knmi_debilt_hourly" / "knmi_260_debilt_hourly_2021_2026.csv"   # KNMI station 260, hourly


@lru_cache
def wet_bulb(agg="max"):
    """Daily wet-bulb temperature, C, mapped onto 2027: Stull 2011 formula on KNMI temperature and humidity, daily max by default."""
    k = pd.read_csv(KNMI, parse_dates=["time_utc_start"]).set_index("time_utc_start")
    k = k[k.index.year == WEATHER_YEAR]
    T, RH = k.T_degC, k.U_pct.clip(1, 100)
    wb = (T * np.arctan(0.151977 * np.sqrt(RH + 8.313659)) + np.arctan(T + RH) - np.arctan(RH - 1.676331)
          + 0.00391838 * RH ** 1.5 * np.arctan(0.023101 * RH) - 4.686035)
    t = wb.resample("D").agg(agg)
    t = t[~((t.index.month == 2) & (t.index.day == 29))]
    t.index = t.index.map(lambda x: x.replace(year=2027))
    return t.reindex(cold.index).interpolate()


def cooling_year(drive_avail, agg="max", peak_cold_MW=None):
    """(DataFrame per day, totals in GWh): free cooling from the wet bulb, absorption on spare hot brine, electric for the rest."""
    cold_d = scaled(cold, peak_cold_MW)
    twb = wet_bulb(agg)
    tower = twb + TOWER_APPROACH_K
    free_frac = ((T_COLD_RETURN - tower.clip(lower=T_COLD_SUPPLY)) / (T_COLD_RETURN - T_COLD_SUPPLY)).clip(0, 1)
    free = cold_d * free_frac
    rest = cold_d - free
    drive_avail = drive_avail.reindex(cold.index).fillna(0.0)
    absorption = np.minimum(rest, drive_avail * COP_ABSORPTION)
    c = pd.DataFrame({"cold": cold_d, "free": free, "absorption": absorption, "electric": rest - absorption, "T_wb": twb,
                      "drive_avail": drive_avail, "drive_needed": rest / COP_ABSORPTION}).rename_axis("date")
    c["free_frac"] = free_frac
    gwh = lambda s: s.sum() * 24 / 1000
    totals = {k: gwh(c[k]) for k in ("cold", "free", "absorption", "electric")}
    totals["el_chillers"] = gwh(c.electric / COP_ELECTRIC)
    totals["el_aux"] = gwh(c.cold * AUX_KW_PER_KW_COLD)
    return c, totals


def chiller_MW(c):
    """Electric chillers installed, MW: all cold above free cooling on the worst day, so they back up the absorption chillers."""
    return float((c.cold - c.free).max())
