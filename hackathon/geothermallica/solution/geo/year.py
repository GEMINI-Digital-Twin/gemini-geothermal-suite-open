"""The year 2027 day by day: heating dispatch of n doublets, the cooling supply, and the constraint checks of the challenge brief.

Demand comes from the brief's daily heating and cooling CSVs; weather from KNMI (the Dutch weather service), De Bilt hourly.
Parameter sources are in the inline comments.
heating_year() returns a DataFrame per day (demand, doublets on, flow, heat by source, electricity, boiler, unmet, availability);
cooling_year() a DataFrame per day of cold by source plus yearly totals; checks() a list of dicts (name, value, limit, status).
"""
from functools import lru_cache

import numpy as np
import pandas as pd

from geo import gas, lifetime
from geo.common import DATA, DEPTH_M, DT_BRINE_MAX_K, PROJECT, Q_MAX_M3H, Q_MIN_M3H, RHO, T_SUPPLY_COLD_C, T_SUPPLY_HEAT_C
from geo.plant import APPROACH_K, CP, Q_FLOOR_M3H, DoubletTable
from geo.well import ESP_DEPTH_M, PUMP_EFF, injector_at

# backup gas boiler, MW: covers the winter peak with one doublet out (N-1); a backup boiler is Dutch practice,
# source: Hydreco 2020, production plan Haagse Aardwarmte Leyweg,
# https://www.nlog.nl/sites/default/files/2020-10/200129_verzoek_tot_instemming_wp_haagse_aardwarmte_leyweg_publiek_gelakt.pdf
BACKUP_BOILER_MW = 16.0
# the hand-picked summer outage windows used before geo/outage.py placed them on the demand; kept to compare against
STAGGERED_HAND = {0: ("2027-06-01", "2027-07-05"), 1: ("2027-08-01", "2027-09-04"), 2: ("2027-09-15", "2027-10-19")}
T_COLD_SUPPLY, T_COLD_RETURN = 20.0, 26.0   # district-cooling supply and return, C; supply from the challenge brief, return assumed
TOWER_APPROACH_K = 4.0                        # cooling-tower water temperature above the wet bulb, K; assumed, no source
# coefficient of performance (COP, cold out per heat in) of a single-effect lithium-bromide (LiBr) absorption chiller;
# source: US Department of Energy, CHP (combined heat and power) Technology Fact Sheet: Absorption Chillers, DOE/EE-1608 (2017),
# https://www.energy.gov/sites/prod/files/2017/06/f35/CHP-Absorption%20Chiller-compliant.pdf
COP_ABSORPTION = 0.75
COP_ELECTRIC = 7.0                            # electric chiller COP at 20 C chilled water; assumed, estimated as a fraction of Carnot
AUX_KW_PER_KW_COLD = 0.03                     # electricity for cooling-tower fans and pumps per kW of cold; assumed, no source
WEATHER_YEAR = 2024                           # KNMI De Bilt weather year laid over the 2027 calendar; our choice
KNMI = PROJECT / "data" / "raw" / "knmi_debilt_hourly" / "knmi_260_debilt_hourly_2021_2026.csv"   # KNMI station 260, hourly

heat = pd.read_csv(DATA / "GEMINI_Heating_Demand_Daily_2027.csv", parse_dates=["date"]).set_index("date").iloc[:, 0]
cold = pd.read_csv(DATA / "GEMINI_Cooling_Demand_Daily_2027.csv", parse_dates=["date"]).set_index("date").iloc[:, 0]


# flows at which the injector is solved, m3/h: for the injection-pressure limit of SodM (Dutch State Supervision of Mines)
# and for the injection-pump power
Q_INJ = np.linspace(Q_FLOOR_M3H, Q_MAX_M3H, 8)


def scaled(series, peak_MW=None):
    """The demand series scaled linearly so its maximum is peak_MW, MW per day; peak_MW None returns it unchanged."""
    return series if peak_MW is None else series * (peak_MW / series.max())


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


def checks(n, t_return_c, peak_heat_MW=None, peak_cold_MW=None, depth_m=DEPTH_M, esp_depth_m=ESP_DEPTH_M, outage_mode="staggered"):
    """Every constraint of the brief for n doublets at return temperature t_return_c: 17 dicts of name, value, limit, status;
    four rows are declared (their status says so), the rest computed."""
    d = heating_year(n, t_return_c, peak_heat_MW=peak_heat_MW, depth_m=depth_m, esp_depth_m=esp_depth_m, outage_mode=outage_mode)
    c, _ = cooling_year(d.surplus, peak_cold_MW=peak_cold_MW)
    tab = table(t_return_c, depth_m, esp_depth_m=esp_depth_m)
    gwh = lambda s: s.sum() * 24 / 1000
    ok = lambda b: "pass" if b else "FAIL"
    on = d[d.doublets_on > 0]
    q = on.q_m3h
    mcp = q / 3600 * RHO * CP / 1000                                       # brine heat capacity flow, MW/K per doublet
    dt = ((on.geo + on.hp - on.el_hp) / on.doublets_on / mcp).max()      # brine cooling actually used, K
    days = [int(d[f"avail_{i}"].sum()) for i in range(n)]
    worst = min(injector_rows(depth_m), key=lambda r: r["sodm_margin_bar"])
    f_max = np.nanmax(tab.cols["freq_hz"])
    bal = (d.geo + d.hp + d.boiler - d.demand).abs().max()
    approach_ok = bool((on.t_hx_C <= on.T_wh_C - APPROACH_K + 1e-6).all())   # the exchanger can reach its water outlet every day
    full = d[[f"avail_{i}" for i in range(n)]].all(axis=1)                 # days with every doublet available
    used = np.r_[q.min(), tab.q[(tab.q >= q.min()) & (tab.q <= q.max())], q.max()]   # table flows inside the year's flow range
    p_in = float(np.interp(used, tab.q, tab.cols["p_esp_intake_bar"]).min())         # pump intake pressure falls with flow
    p_b, p_b10, p_pure = gas.p_bubble_bar(depth_m), gas.p_bubble_bar(depth_m, salt="log10"), gas.p_bubble_bar(depth_m, salt=None)
    p_b_worst = max(p_b, p_b10)                                            # log base of the salt correction is unconfirmed: take the worse
    q_mean = float(q.mean())                                               # mean flow per doublet on running days
    t_bt = lifetime.t_bt_yr(q_mean)                                        # thermal breakthrough time, years
    dp_int = max(lifetime.interference_bar(n, Q_MAX_M3H))                 # worst injector at 300 m3/h, doublets as far apart as the wells
    int_margin = worst["sodm_margin_bar"] - dp_int
    pk, pkc = d.demand.idxmax(), c.cold.idxmax()
    heat_n1 = (n - 1) * tab.out_max + BACKUP_BOILER_MW                     # the other doublets at full flow plus the backup boiler, MW
    j = int(d.doublets_on[pkc])
    drive = c.drive_avail[pkc] * (min(1.0, (n - 1) / j) if j else 0.0)    # hot brine left for absorption with one doublet out, MW
    rest = c.cold[pkc] - c.free[pkc]
    cold_n1 = c.free[pkc] + min(rest, drive * COP_ABSORPTION) + chiller_MW(c)   # free + absorption + the electric chillers installed
    rows = [
        ("doublets 1-3 [D]", f"{n} built at {depth_m:.0f} m, {int(d.doublets_on.min())}-{int(d.doublets_on.max())} on", "1-3", ok(1 <= n <= 3)),
        ("flow per doublet [D]", f"{q.min():.0f}-{q.max():.0f} m3/h", f"{Q_MIN_M3H:.0f}-{Q_MAX_M3H:.0f}",
         ok(q.min() >= Q_MIN_M3H and q.max() <= Q_MAX_M3H)),
        ("flow above pump floor [C]", f"min {q.min():.0f} m3/h", f">= {Q_FLOOR_M3H:.0f}", ok(q.min() >= Q_FLOOR_M3H - 1e-6)),
        ("brine cooling [D]", f"max {dt:.1f} K", f"<= {DT_BRINE_MAX_K:.0f} K", ok(dt <= DT_BRINE_MAX_K + 1e-6)),
        ("pump efficiency [D]", f"{PUMP_EFF:.2f} set as an input for the ESP and the injection pump (declared, not computed)", "0.70",
         ok(PUMP_EFF == 0.70) + " [declared]"),
        ("production = injection volume [D]", "q_inj = q_prod every day: the dispatch moves one flow through both wells (declared)",
         "equal", "pass [declared]"),
        ("operating days per doublet [D]", " / ".join(str(x) for x in days) + " d available", "330", ok(all(x <= 330 for x in days))),
        ("heat supply 100 C [D]",
         f"water leaves the exchanger at most {on.t_hx_C.max():.1f} C, always <= brine {on.T_wh_C.min():.1f} C - {APPROACH_K:.0f} K "
         f"approach ({'yes' if approach_ok else 'NO'}); the heat pump lifts to {T_SUPPLY_HEAT_C:.0f} C on {int((on.hp > 1e-6).sum())} "
         f"of {len(on)} running days, boiler lift {gwh(d.boiler_lift):.2f} GWh on {int((d.boiler_lift > 0.01).sum())} days",
         f"{T_SUPPLY_HEAT_C:.0f} C every day", ok(approach_ok and d.boiler_lift.max() < 1e-6) + " [A, Lorenz HP]"),
        ("cold supply 20 C [D]", f"electric chiller sized {chiller_MW(c):.2f} MW, all cold above free cooling (backs up absorption); "
         "the free, absorption, electric stack meets every day's cold by construction (declared)", f"{T_SUPPLY_COLD_C:.0f} C",
         "pass [declared, return 26 C]"),
        ("SodM injection pressure [L]",
         f"worst p_bh {worst['p_bh_req_bar']:.1f} bar at {worst['q_m3h']:.0f} m3/h, margin {worst['sodm_margin_bar']:.1f} bar",
         f"<= {worst['sodm_limit_bar']:.1f} bar", ok(worst["sodm_margin_bar"] >= 0)),
        ("ESP envelope [C]", f"{q.min():.0f}-{q.max():.0f} m3/h, f max {f_max:.1f} Hz",
         f"{tab.w.q_min:.0f}-{tab.w.q_max:.0f} m3/h, 60 Hz",
         ok(q.min() >= tab.w.q_min and q.max() <= tab.w.q_max and f_max <= 60)),
        ("accounting check [C]", f"max abs(geo + hp + boiler - demand) {bal:.1e} MW (the dispatch serves demand by construction; "
         "a bookkeeping check, declared)", "0 every day", ok(bal < 1e-6) + " [declared]"),
        ("capacity covers the peak [D]",
         f"with every doublet available: backup boiler fired for capacity {gwh(d.boiler_peak[full]):.3f} GWh on "
         f"{int((d.boiler_peak[full] > 0.01).sum())} days, unmet {gwh(d.unmet[full]):.3f} GWh (outage days excluded)",
         "0 GWh with all doublets on", ok(d.boiler_peak[full].max() < 1e-6 and d.unmet[full].max() < 1e-6)),
        ("free gas at ESP intake [D, L, A]", f"min intake {p_in:.1f} bar at {q.max():.0f} m3/h (ESP at {tab.w.esp_depth_m:.0f} m)",
         f">= p_bubble {p_b_worst:.1f} bar (Henry fits with 45 g/L NaCl, worse of ln {p_b:.1f} / log10 {p_b10:.1f} readings; "
         f"pure water {p_pure:.1f})",
         ok(p_in >= p_b_worst)),
        ("thermal breakthrough [L, A]", f"t_BT {t_bt:.0f} yr at the mean running flow {q_mean:.0f} m3/h, L {lifetime.SPACING_M:.0f} m "
         f"({lifetime.t_bt_yr(Q_MAX_M3H):.0f} yr at {Q_MAX_M3H:.0f} m3/h)",
         f">= {lifetime.T_BT_MIN_YR:.0f} yr [A criterion; ThermoGIS uses 1 % cooling at 50 yr]",
         ok(t_bt >= lifetime.T_BT_MIN_YR)),
        ("doublet interference [L, A]", (f"SodM margin {worst['sodm_margin_bar']:.1f} - interference {dp_int:.2f} bar (worst of {n} injectors, "
         f"D = L = {lifetime.SPACING_M:.0f} m, {Q_MAX_M3H:.0f} m3/h) = {int_margin:.1f} bar") if n > 1 else
         f"one doublet, no interference (0 bar); SodM margin {int_margin:.1f} bar", ">= 0 bar", ok(int_margin >= 0)),
        ("one doublet out on the coldest day [C]",
         f"heat {heat_n1:.1f} MW available ({n - 1} x {tab.out_max:.1f} MW + {BACKUP_BOILER_MW:.0f} MW backup boiler) vs "
         f"{d.demand[pk]:.0f} MW on {pk.date()}; cold {cold_n1:.1f} MW available vs {c.cold[pkc]:.0f} MW on {pkc.date()}",
         f">= {d.demand[pk]:.0f} MW heat and {c.cold[pkc]:.0f} MW cold", ok(heat_n1 >= d.demand[pk] - 1e-6 and cold_n1 >= c.cold[pkc] - 1e-6)),
    ]
    return [dict(name=a, value=v, limit=lim, status=st) for a, v, lim, st in rows]
