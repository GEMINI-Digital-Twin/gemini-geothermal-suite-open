"""Where the 35 outage days of each doublet fall, and what an unplanned outage in the coldest week costs.

The source runs 330 days, the system serves 365, and the placement of the outage days is the designer's choice
(organiser answer of 1 Nov 2026 on the hackathon Discord).
windows() returns {doublet: (start date, end date)}; unplanned() returns a dict of the extra boiler gas, cost and CO2 of one
doublet out for a week over the heat peak; summary() collects both for the heating_year tool.
"""
from functools import lru_cache

import numpy as np
import pandas as pd

DAYS = 35            # planned outage per doublet, days: 365 - 330 (brief)
UNPLANNED_DAYS = 7   # unplanned outage of one doublet in the coldest week, days; assumed, no source
MODES = ("staggered", "all_at_once")


def demand():
    """Heat demand per day of the brief's file, MW. Cold is left out: free cooling and the electric chillers (sized to back up
    absorption) serve it with every doublet out, so an outage costs boiler heat, not cold."""
    from geo import year
    return year.heat


def _best(w, n, days):
    """Start indices of n non-overlapping windows of `days` days with the least summed w (dynamic programme over the year)."""
    s = np.r_[0.0, np.cumsum(w)]
    m = len(w) - days + 1
    win = s[days:days + m] - s[:m]                         # sum over the window starting at each day
    f = np.full((n + 1, len(w) + 1), np.inf)              # f[k][i]: least sum of k windows inside days 0..i-1
    f[0, :] = 0.0
    take = np.zeros((n + 1, len(w) + 1), dtype=bool)
    for k in range(1, n + 1):
        for i in range(1, len(w) + 1):
            f[k, i] = f[k, i - 1]
            if i >= days and f[k - 1, i - days] + win[i - days] < f[k, i]:
                f[k, i], take[k, i] = f[k - 1, i - days] + win[i - days], True
    starts, i = [], len(w)
    for k in range(n, 0, -1):
        while not take[k, i]:
            i -= 1
        starts.append(i - days)
        i -= days
    return sorted(starts)


@lru_cache
def _windows(n, days, mode):
    w = demand()
    idx = w.index
    if mode == "all_at_once":
        starts = _best(w.values, 1, days) * n
    else:
        starts = _best(w.values, n, days)
    return tuple((str(idx[a].date()), str(idx[a + days - 1].date())) for a in starts)


def windows(n, days=DAYS, mode="staggered", custom=None):
    """{doublet: (start date, end date)} of the planned outages; mode 'custom' returns the windows given in custom."""
    if mode == "custom":
        return dict(custom)
    if mode not in MODES:
        raise ValueError(f"outage_mode {mode!r}; valid: {MODES + ('custom',)}")
    return dict(enumerate(_windows(int(n), int(days), mode)))


def describe(w):
    """One string for the windows: 'doublet 1 days 126-160 (2027-05-06 to 2027-06-09); doublet 2 ...'."""
    doy = lambda x: pd.Timestamp(x).dayofyear
    return "; ".join(f"doublet {i + 1} days {doy(a)}-{doy(b)} ({a} to {b})" for i, (a, b) in sorted(w.items()))


@lru_cache
def _year(n, t_return_c, peak_heat_MW, depth_m, esp_depth_m, mode, extra=None):
    """heating_year with the planned windows of mode, plus doublet 1 out over extra=(start, end) if given (cached)."""
    from geo import year
    plan = windows(n, mode=mode)
    if extra:
        plan = {**plan, 0: [plan[0], extra]}
    return year.heating_year(n, t_return_c, outages=plan, peak_heat_MW=peak_heat_MW, depth_m=depth_m, esp_depth_m=esp_depth_m)


def coldest(days=UNPLANNED_DAYS):
    """(start date, end date) of the `days`-day window with the highest heat demand."""
    from geo import year
    end = year.heat.rolling(days).sum().idxmax()
    return str((end - pd.Timedelta(days=days - 1)).date()), str(end.date())


def unplanned(n, t_return_c, days=UNPLANNED_DAYS, peak_heat_MW=None, depth_m=None, esp_depth_m=None, outage_mode="staggered"):
    """Extra boiler gas GWh, cost MEUR (gas, its CO2 price, electricity change) and CO2 kt of doublet 1 out over the coldest week.
    Heat the boiler cannot carry is reported as unmet_GWh, not priced."""
    from geo import cost, year
    key = (int(n), float(t_return_c), peak_heat_MW, float(depth_m or year.DEPTH_M), float(esp_depth_m or year.ESP_DEPTH_M), outage_mode)
    a, b = coldest(days)
    base, hit = _year(*key), _year(*key, extra=(a, b))
    gwh = lambda d, c: float(d[c].sum() * 24 / 1000)
    el = lambda d: gwh(d, "esp") + gwh(d, "el_hp") + float(year.injection_pump_MW(d).sum() * 24 / 1000)
    boiler = gwh(hit, "boiler") - gwh(base, "boiler")
    gas = boiler / cost.BOILER_EFF
    d_el = el(hit) - el(base)
    co2 = gas * cost.CO2_T_MWH + d_el * cost.EF_EL_KG_KWH
    meur = (gas * cost.P_GAS + gas * cost.CO2_T_MWH * cost.P_CO2 + d_el * cost.P_EL) / 1000
    return {"start": a, "end": b, "days": days, "boiler_GWh": boiler, "gas_GWh": gas, "electricity_GWh": d_el, "cost_MEUR": meur,
            "co2_kt": co2, "unmet_GWh": gwh(hit, "unmet") - gwh(base, "unmet"), "backup_max_MW": float(hit.loc[a:b, "boiler"].max())}


def in_windows(d, n):
    """(backup GWh, backup max MW, unmet GWh) on the days at least one doublet is out."""
    out = ~d[[f"avail_{i}" for i in range(n)]].all(axis=1)
    back = d.boiler_peak[out]
    return float(back.sum() * 24 / 1000), float(back.max()) if out.any() else 0.0, float(d.unmet[out].sum() * 24 / 1000)


def summary(n, t_return_c, peak_heat_MW=None, depth_m=None, esp_depth_m=None, outage_mode="staggered"):
    """Flat outage keys for the heating_year tool: windows, backup in them, the other mode as the alternative, the unplanned week."""
    from geo import cost, year
    key = (int(n), float(t_return_c), peak_heat_MW, float(depth_m or year.DEPTH_M), float(esp_depth_m or year.ESP_DEPTH_M))
    out, gas = {"outage_mode": outage_mode}, {}
    for mode, pre in (("staggered", "staggered_"), ("all_at_once", "all_at_once_")):
        d = _year(*key, mode)
        b_gwh, b_mw, unmet = in_windows(d, n)
        gas[mode] = float(d.boiler.sum() * 24 / 1000) / cost.BOILER_EFF
        out.update({pre + "windows": describe(windows(n, mode=mode)), pre + "backup_GWh": b_gwh, pre + "backup_max_MW": b_mw,
                    pre + "unmet_GWh": unmet})
    out["all_at_once_extra_gas_GWh"] = gas["all_at_once"] - gas["staggered"]
    out["all_at_once_extra_gas_MEUR"] = out["all_at_once_extra_gas_GWh"] * cost.P_GAS / 1000
    u = unplanned(n, t_return_c, peak_heat_MW=peak_heat_MW, depth_m=depth_m, esp_depth_m=esp_depth_m, outage_mode=outage_mode)
    out.update({"unplanned_7d_window": f"{u['start']} to {u['end']}", "unplanned_7d_boiler_GWh": u["boiler_GWh"],
                "unplanned_7d_cost_MEUR": u["cost_MEUR"], "unplanned_7d_co2_kt": u["co2_kt"],
                "unplanned_7d_unmet_GWh": u["unmet_GWh"], "unplanned_7d_backup_max_MW": u["backup_max_MW"],
                "outage_basis": (f"{DAYS} days per doublet (365 - 330, brief) [D]; staggered = the {n} non-overlapping windows with the "
                                 "least heat demand [C] (free cooling and the electric chillers serve the cold with doublets out [A]); "
                                 "all_at_once = every doublet in the one least-demand window [C]; "
                                 f"unplanned = doublet 1 out over the {UNPLANNED_DAYS} days of highest heat demand [A], "
                                 f"gas {cost.P_GAS} EUR/MWh, CO2 {cost.P_CO2} EUR/t, electricity {cost.P_EL} EUR/MWh [L]")})
    return out
