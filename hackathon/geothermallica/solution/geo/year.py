"""The year, day by day: heating dispatch (script 05) and the cooling stack (script 06) as functions."""
from functools import lru_cache

import numpy as np
import pandas as pd

from geo.common import DATA, DEPTH_M, DT_BRINE_MAX_K, PROJECT, Q_MAX_M3H, Q_MIN_M3H, RHO, T_SUPPLY_COLD_C, T_SUPPLY_HEAT_C
from geo.plant import CP, Q_FLOOR_M3H, DoubletTable
from geo.well import PUMP_EFF, injector_at

BACKUP_BOILER_MW = 16.0      # security of supply, one doublet out at the winter peak; Dutch practice [L, research/04]
STAGGERED = {0: ("2027-06-01", "2027-07-05"), 1: ("2027-08-01", "2027-09-04"), 2: ("2027-09-15", "2027-10-19")}  # 35 d each [A]
T_COLD_SUPPLY, T_COLD_RETURN = 20.0, 26.0   # supply [D], return [A]
TOWER_APPROACH_K = 4.0                        # cooling-tower water above wet bulb [A]
COP_ABSORPTION = 0.75                         # single-effect LiBr, hot water >= 80 C [L, research/02]
COP_ELECTRIC = 7.0                            # at 20 C chilled water, Carnot-fraction estimate [A, research/02]
AUX_KW_PER_KW_COLD = 0.03                     # tower fans and pumps [A]
WEATHER_YEAR = 2024                           # KNMI De Bilt year laid over the 2027 calendar [A]
KNMI = PROJECT / "data" / "raw" / "knmi_debilt_hourly" / "knmi_260_debilt_hourly_2021_2026.csv"

heat = pd.read_csv(DATA / "GEMINI_Heating_Demand_Daily_2027.csv", parse_dates=["date"]).set_index("date").iloc[:, 0]
cold = pd.read_csv(DATA / "GEMINI_Cooling_Demand_Daily_2027.csv", parse_dates=["date"]).set_index("date").iloc[:, 0]


Q_INJ = np.linspace(Q_FLOOR_M3H, Q_MAX_M3H, 8)   # injector grid for the SodM check and the injection pump [C]


def scaled(series, peak_MW=None):
    """The CSV series scaled linearly so its maximum is peak_MW; None keeps the file as is."""
    return series if peak_MW is None else series * (peak_MW / series.max())


@lru_cache
def _table(t_return_c, depth_m):
    return DoubletTable(t_return_c, depth_m=depth_m)


def table(t_return_c, depth_m=DEPTH_M):
    return _table(float(t_return_c), float(depth_m))   # one cache entry per (return, depth), however the caller spells it


@lru_cache
def _injector_rows(depth_m):
    return [injector_at(q, depth_m) for q in Q_INJ]


def injector_rows(depth_m=DEPTH_M):
    return _injector_rows(float(depth_m))


def injection_pump_MW(d):
    """Injection pump electricity per day, interpolated on the daily flow, times the doublets running."""
    return np.interp(d.q_m3h, Q_INJ, [r["pump_kW"] for r in injector_rows(d.attrs.get("depth_m", DEPTH_M))]) / 1000 * d.doublets_on


def heating_year(n, t_return_c, outages=None, peak_heat_MW=None, point=None, depth_m=DEPTH_M):
    """Daily dispatch of n doublets: among 1..k available, equal split, least electricity (ESP + heat pump).

    point(MW per doublet) -> operating point; defaults to the DoubletTable's at_output at depth_m."""
    point = point or table(t_return_c, depth_m).at_output
    heat_d = scaled(heat, peak_heat_MW)
    outages = {i: STAGGERED[i] for i in range(n)} if outages is None else outages
    avail = pd.DataFrame(1, index=heat_d.index, columns=range(n))
    for i, (a, b) in outages.items():
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
            j, pt, geo, hp, el_hp, esp, boiler_lift, abs_drive = 0, None, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
        else:
            j, _, _, pt = best
            geo, hp, el_hp = j * pt["MW_hx"], j * pt["MW_hp"], j * pt["MW_el_hp"]
            esp, boiler_lift = j * pt["kW_esp"] / 1000, j * pt["MW_boiler_lift"]
            abs_drive = j * pt.get("MW_abs_drive", 0.0)        # brine heat above 78 C not needed for heating: usable by absorption
        delivered = geo + hp + boiler_lift
        boiler_peak = min(BACKUP_BOILER_MW, max(0.0, demand - delivered))
        rows.append(dict(date=day, demand=demand, doublets_on=j, q_m3h=pt.get("q_m3h", 0.0) if pt else 0.0, geo=geo, hp=hp,
                         el_hp=el_hp, esp=esp, boiler=boiler_lift + boiler_peak, boiler_lift=boiler_lift,
                         boiler_peak=boiler_peak, unmet=max(0.0, demand - delivered - boiler_peak), surplus=abs_drive))
    d = pd.DataFrame(rows).set_index("date")
    d.attrs["depth_m"] = depth_m
    for i in range(n):
        d[f"avail_{i}"] = avail[i].values
    return d


@lru_cache
def wet_bulb(agg="max"):
    """Daily wet bulb (Stull 2011 from KNMI T and RH), daily max by default [A], mapped onto 2027."""
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
    """Free cooling from the wet bulb, absorption on the free hot brine (MW per day), electric for the rest."""
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


def checks(n, t_return_c, peak_heat_MW=None, peak_cold_MW=None, depth_m=DEPTH_M):
    """Every brief constraint for n doublets at a return of t_return_c: 13 rows of name, value, limit, status."""
    d = heating_year(n, t_return_c, peak_heat_MW=peak_heat_MW, depth_m=depth_m)
    c, _ = cooling_year(d.surplus, peak_cold_MW=peak_cold_MW)
    tab = table(t_return_c, depth_m)
    gwh = lambda s: s.sum() * 24 / 1000
    ok = lambda b: "pass" if b else "FAIL"
    on = d[d.doublets_on > 0]
    q = on.q_m3h
    mcp = q / 3600 * RHO * CP / 1000                                       # MW/K per doublet
    dt = ((on.geo + on.hp - on.el_hp) / on.doublets_on / mcp).max()      # brine cooling actually used, K
    days = [int(d[f"avail_{i}"].sum()) for i in range(n)]
    worst = min(injector_rows(depth_m), key=lambda r: r["sodm_margin_bar"])
    f_max = np.nanmax(tab.cols["freq_hz"])
    bal = (d.geo + d.hp + d.boiler - d.demand).abs().max()
    full = d[[f"avail_{i}" for i in range(n)]].all(axis=1)                 # days with every doublet available
    rows = [
        ("doublets 1-3 [D]", f"{n} built at {depth_m:.0f} m, {int(d.doublets_on.min())}-{int(d.doublets_on.max())} on", "1-3", ok(1 <= n <= 3)),
        ("flow per doublet [D]", f"{q.min():.0f}-{q.max():.0f} m3/h", f"{Q_MIN_M3H:.0f}-{Q_MAX_M3H:.0f}", ok(q.min() >= Q_MIN_M3H and q.max() <= Q_MAX_M3H)),
        ("flow above pump floor [C, 03]", f"min {q.min():.0f} m3/h", f">= {Q_FLOOR_M3H:.0f}", ok(q.min() >= Q_FLOOR_M3H - 1e-6)),
        ("brine cooling [D]", f"max {dt:.1f} K", f"<= {DT_BRINE_MAX_K:.0f} K", ok(dt <= DT_BRINE_MAX_K + 1e-6)),
        ("pump efficiency [D]", f"{PUMP_EFF:.2f} (ESP and injection pump)", "0.70", ok(PUMP_EFF == 0.70)),
        ("production = injection volume [D]", "q_inj = q_prod every day (07 by construction)", "equal", "pass [A]"),
        ("operating days per doublet [D]", " / ".join(str(x) for x in days) + " d available", "330", ok(all(x <= 330 for x in days))),
        ("heat supply 100 C [D]", f"boiler lift needed {gwh(d.boiler_lift):.2f} GWh on {int((d.boiler_lift > 0.01).sum())} days (heat pump does the lift)",
         f"{T_SUPPLY_HEAT_C:.0f} C", ok(d.boiler_lift.max() < 1e-6) + " [A, Lorenz HP]"),
        ("cold supply 20 C [D]", f"electric chiller sized {c.electric.max():.2f} MW for the peak day; stack meets demand by construction",
         f"{T_SUPPLY_COLD_C:.0f} C", "pass [A, return 26 C]"),
        ("SodM injection pressure [L]", f"worst p_bh {worst['p_bh_req_bar']:.1f} bar at {worst['q_m3h']:.0f} m3/h, margin {worst['sodm_margin_bar']:.1f} bar",
         f"<= {worst['sodm_limit_bar']:.1f} bar", ok(worst["sodm_margin_bar"] >= 0)),
        ("ESP envelope [C, 03]", f"{q.min():.0f}-{q.max():.0f} m3/h, f max {f_max:.1f} Hz", f"{tab.w.q_min:.0f}-{tab.w.q_max:.0f} m3/h, 60 Hz",
         ok(q.min() >= tab.w.q_min and q.max() <= tab.w.q_max and f_max <= 60)),
        ("accounting check 05 [C]", f"max abs(geo + hp + boiler - demand) {bal:.1e} MW (dispatch serves demand by construction)", "0 every day", ok(bal < 1e-6)),
        ("capacity covers the peak [D]", f"with every doublet available: backup boiler fired for capacity {gwh(d.boiler_peak[full]):.3f} GWh on "
         f"{int((d.boiler_peak[full] > 0.01).sum())} days, unmet {gwh(d.unmet[full]):.3f} GWh (outage days excluded)",
         "0 GWh with all doublets on", ok(d.boiler_peak[full].max() < 1e-6 and d.unmet[full].max() < 1e-6)),
    ]
    return [dict(name=a, value=v, limit=lim, status=st) for a, v, lim, st in rows]
