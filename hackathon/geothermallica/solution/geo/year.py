"""Heating over 2027 day by day for n doublets, plus the cached doublet table and injector rows.

Cooling lives in geo/cooling.py, the checks in geo/checks.py; both are re-exported here.
"""
from functools import lru_cache

import numpy as np
import pandas as pd

from geo.common import DEPTH_M, Q_MAX_M3H
from geo.plant import Q_FLOOR_M3H, DoubletTable
from geo.well import ESP_DEPTH_M, injector_at
from geo.demand import cold, heat, scaled  # noqa: F401
from geo.cooling import (AUX_KW_PER_KW_COLD, COP_ABSORPTION, COP_ELECTRIC, KNMI, T_COLD_RETURN, T_COLD_SUPPLY,  # noqa: F401
                         TOWER_APPROACH_K, WEATHER_YEAR, chiller_MW, cooling_year, wet_bulb)
from geo.checks import checks  # noqa: F401

BACKUP_BOILER_MW = 16.0   # backup gas boiler for the peak with one doublet out; Hydreco 2020, see SOURCES.md
# hand-picked summer outage windows from before geo/outage.py; kept for comparison
STAGGERED_HAND = {0: ("2027-06-01", "2027-07-05"), 1: ("2027-08-01", "2027-09-04"), 2: ("2027-09-15", "2027-10-19")}
Q_INJ = np.linspace(Q_FLOOR_M3H, Q_MAX_M3H, 8)   # flows at which the injector is solved, m3/h


@lru_cache
def _table(t_return_c, depth_m, heat_pump, esp_depth_m):
    """DoubletTable for these inputs (cached)."""
    return DoubletTable(t_return_c, depth_m=depth_m, heat_pump=heat_pump, esp_depth_m=esp_depth_m)


def table(t_return_c, depth_m=DEPTH_M, heat_pump=True, esp_depth_m=ESP_DEPTH_M):
    """DoubletTable of one doublet (cached); heat_pump=False is the layout where a boiler lifts the water to 100 C."""
    return _table(float(t_return_c), float(depth_m), bool(heat_pump), float(esp_depth_m))   # floats: one cache entry per input set


@lru_cache
def _injector_rows(depth_m):
    """Injector results at each flow of Q_INJ (cached)."""
    return [injector_at(q, depth_m) for q in Q_INJ]


def injector_rows(depth_m=DEPTH_M):
    """List of injector result dicts, one per flow in Q_INJ, at depth_m."""
    return _injector_rows(float(depth_m))


def injection_pump_MW(d):
    """Injection-pump electricity per day, MW: interpolated on the daily flow, times the doublets running."""
    return np.interp(d.q_m3h, Q_INJ, [r["pump_kW"] for r in injector_rows(d.attrs.get("depth_m", DEPTH_M))]) / 1000 * d.doublets_on


def heating_year(n, t_return_c, outages=None, peak_heat_MW=None, point=None, depth_m=DEPTH_M, heat_pump=True, esp_depth_m=ESP_DEPTH_M,
                 outage_mode="staggered"):
    """DataFrame per day for n doublets: of those available, run the count that meets demand with least electricity, equal split.
    outages {doublet: (start, end) or a list of them} overrides the windows that geo.outage places by outage_mode."""
    from geo import outage
    point = point or table(t_return_c, depth_m, heat_pump, esp_depth_m).at_output
    heat_d = scaled(heat, peak_heat_MW)
    outages = outage.windows(n, mode=outage_mode) if outages is None else outages
    avail = pd.DataFrame(1, index=heat_d.index, columns=range(n))
    for i, w in outages.items():
        for a, b in (w if isinstance(w, list) else [w]):
            avail.loc[a:b, i] = 0
    rows = []
    for day, demand in heat_d.items():
        k = int(avail.loc[day].sum())
        best = None
        for j in range(1, k + 1):
            pt = point(demand / j)
            short = max(0.0, demand - j * pt["MW_out"])
            el = j * (pt["kW_esp"] / 1000 + pt["MW_el_hp"])
            if best is None or (short, el) < (best[2], best[1]):
                best = (j, el, short, pt)
        if best is None:
            j, pt, geo, hp, el_hp, esp, boiler_lift, abs_drive = 0, {}, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
        else:
            j, _, _, pt = best
            geo, hp, el_hp = j * pt["MW_hx"], j * pt["MW_hp"], j * pt["MW_el_hp"]
            esp, boiler_lift = j * pt["kW_esp"] / 1000, j * pt["MW_boiler_lift"]
            abs_drive = j * pt.get("MW_abs_drive", 0.0)        # brine heat above 78 C left over for the absorption chillers, MW
        delivered = geo + hp + boiler_lift
        boiler_peak = min(BACKUP_BOILER_MW, max(0.0, demand - delivered))
        rows.append(dict(date=day, demand=demand, doublets_on=j, q_m3h=pt.get("q_m3h", 0.0), geo=geo, hp=hp,
                         el_hp=el_hp, esp=esp, boiler=boiler_lift + boiler_peak, boiler_lift=boiler_lift,
                         boiler_peak=boiler_peak, unmet=max(0.0, demand - delivered - boiler_peak), surplus=abs_drive,
                         T_wh_C=pt.get("T_wh_C", np.nan), t_hx_C=pt.get("t_hx_C", np.nan), part_load=pt.get("part_load", "off")))
    d = pd.DataFrame(rows).set_index("date")
    d.attrs["depth_m"], d.attrs["heat_pump"] = depth_m, heat_pump
    for i in range(n):
        d[f"avail_{i}"] = avail[i].values
    return d
