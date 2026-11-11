"""The 17 constraint checks of one design over 2027: name, value, limit and pass or FAIL per row."""
import numpy as np

from geo import gas, lifetime
from geo.common import DEPTH_M, DT_BRINE_MAX_K, Q_MAX_M3H, Q_MIN_M3H, RHO, T_SUPPLY_COLD_C, T_SUPPLY_HEAT_C
from geo.cooling import COP_ABSORPTION, chiller_MW, cooling_year
from geo.plant import APPROACH_K, CP, Q_FLOOR_M3H
from geo.well import ESP_DEPTH_M, PUMP_EFF


def checks(n, t_return_c, peak_heat_MW=None, peak_cold_MW=None, depth_m=DEPTH_M, esp_depth_m=ESP_DEPTH_M, outage_mode="staggered"):
    """17 check rows (name, value, limit, status) for n doublets at t_return_c; four are declared, the rest computed."""
    from geo.year import BACKUP_BOILER_MW, heating_year, injector_rows, table   # here: year re-exports checks
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
