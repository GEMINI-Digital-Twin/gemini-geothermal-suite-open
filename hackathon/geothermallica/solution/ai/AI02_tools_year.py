"""Year tools: heating and cooling over 2027, the constraint checks, and the return-temperature sweep."""
from AI02_tools_common import _cool, _esp, _heat, _mode, _need, _peaks, gwh, r2
from geo.common import DEPTH_M
from geo import outage, year


def heating_year(n_doublets, t_return_c, peak_heat_MW=None, depth_m=DEPTH_M, esp_depth_m=None, outage_mode="staggered"):
    """Daily dispatch over 2027 of 1-3 doublets at a network return of 30-70 C, reservoir at depth_m (default 2500 m), heat demand
    scaled to peak_heat_MW if given (else 30 MW), 16 MW backup boiler, 35-day planned outage per doublet placed by outage_mode
    (staggered = the least-demand non-overlapping windows, the default; all_at_once = every doublet in one window): annual GWh by
    source, electricity (ESP, heat pump, injection pump), unmet heat, capacity, the peak-day MW by source and margin, brine heat above
    78 C left for absorption chillers, the outage windows (day of year and dates) with the backup heat in them for both modes, and
    one doublet out unplanned for 7 days over the coldest week: extra boiler GWh, cost MEUR, CO2 kt [C, A]."""
    return {**_year_row(n_doublets, t_return_c, peak_heat_MW, depth_m, esp_depth_m, outage_mode),
            **r2(outage.summary(int(n_doublets), float(t_return_c), peak_heat_MW, float(depth_m), _esp(esp_depth_m), outage_mode))}


def _year_row(n_doublets, t_return_c, peak_heat_MW=None, depth_m=DEPTH_M, esp_depth_m=None, outage_mode="staggered"):
    """The heating_year dict without the outage keys (return_sweep runs it six times)."""
    d = _heat(n_doublets, t_return_c, peak_heat_MW, depth_m, esp_depth_m, outage_mode)
    tab = year.table(float(t_return_c), float(depth_m), esp_depth_m=_esp(esp_depth_m))
    pk = d.demand.idxmax()
    cap = n_doublets * tab.out_max
    return r2({"demand_GWh": gwh(d.demand), "exchanger_GWh": gwh(d.geo), "heat_pump_GWh": gwh(d.hp),
               "heat_pump_electricity_GWh": gwh(d.el_hp), "esp_electricity_GWh": gwh(d.esp),
               "injection_pump_electricity_GWh": gwh(year.injection_pump_MW(d)), "boiler_GWh": gwh(d.boiler),
               "boiler_days": int((d.boiler > 0.01).sum()), "unmet_GWh": gwh(d.unmet),
               "geothermal_share_pct": 100 * (gwh(d.geo) + gwh(d.hp) - gwh(d.el_hp)) / gwh(d.demand),
               "capacity_MW": cap, "peak_demand_MW": d.demand[pk], "peak_margin_pct": 100 * (cap / d.demand[pk] - 1),
               "peak_exchanger_MW": d.geo[pk], "peak_heat_pump_MW": d.hp[pk], "peak_boiler_MW": d.boiler[pk],
               "n_minus_1_with_backup_boiler_MW": (n_doublets - 1) * tab.out_max + year.BACKUP_BOILER_MW,
               "backup_boiler_MW": year.BACKUP_BOILER_MW,
               "hot_brine_for_absorption_GWh": gwh(d.surplus), "tag": "[C, A]"})


def cooling_year(t_return_c, n_doublets=2, peak_heat_MW=None, peak_cold_MW=None, depth_m=DEPTH_M, esp_depth_m=None):
    """Cold at 20 C over 2027, cold demand scaled to peak_cold_MW if given (else 10 MW): free cooling from the De Bilt wet bulb (26 C
    return, 4 K tower approach), absorption on the hot brine left by heating_year (same peak_heat_MW and depth_m), electric
    chillers COP 7 for the rest; GWh and share by source, the peak-day split in MW, electricity of the chillers and of the tower
    fans and pumps [C, A]."""
    c, t = _cool(n_doublets, t_return_c, peak_heat_MW, peak_cold_MW, depth_m, esp_depth_m)
    pk = c.cold.idxmax()
    return r2({"cold_GWh": t["cold"], "free_GWh": t["free"], "absorption_GWh": t["absorption"], "electric_GWh": t["electric"],
               "free_pct": 100 * t["free"] / t["cold"], "absorption_pct": 100 * t["absorption"] / t["cold"],
               "electric_pct": 100 * t["electric"] / t["cold"], "peak_day": str(pk.date()), "peak_wet_bulb_C": c.T_wb[pk],
               "peak_free_MW": c.free[pk], "peak_absorption_MW": c.absorption[pk], "peak_electric_MW": c.electric[pk],
               "chiller_electricity_GWh": t["el_chillers"], "aux_electricity_GWh": t["el_aux"],
               "electricity_GWh": t["el_chillers"] + t["el_aux"], "tag": "[C, A]"})


def checks(n_doublets, t_return_c, peak_heat_MW=None, peak_cold_MW=None, depth_m=DEPTH_M, esp_depth_m=None, outage_mode="staggered"):
    """The brief's constraints, 17 rows (incl. capacity covers the peak, free gas at the ESP intake, thermal breakthrough, doublet
    interference and one doublet out on the coldest day with the 16 MW backup boiler) for 1-3 doublets at a 30-70 C return, reservoir at depth_m (default 2500 m), demand scaled to the given peaks:
    each row is name: value (limit) -> pass or FAIL; four rows are declared (inputs or true by construction), the summary says
    how many are computed [C]."""
    _need("n_doublets", n_doublets, 1, 3)
    _need("t_return_c", t_return_c, 30, 70)
    _peaks(peak_heat_MW, peak_cold_MW)
    _need("depth_m", depth_m, 1500, 4000)
    rows = year.checks(int(n_doublets), float(t_return_c), peak_heat_MW, peak_cold_MW, depth_m=float(depth_m), esp_depth_m=_esp(esp_depth_m),
                       outage_mode=_mode(outage_mode))
    out = {f"{i + 1:02d} {r['name']}": f"{r['value']} (limit {r['limit']}) -> {r['status']}" for i, r in enumerate(rows)}
    n_pass = sum(r["status"].startswith("pass") for r in rows)
    n_declared = sum("declared" in r["status"] for r in rows)   # inputs or true by construction
    summary = f"{n_pass}/{len(rows)} pass ({len(rows) - n_declared} computed + {n_declared} declared rows)"
    return {**out, "n_pass": n_pass, "n_fail": len(rows) - n_pass, "n_rows": len(rows), "n_declared": n_declared,
            "summary": summary, "tag": "[C]"}


SWEEP_C = (40, 50, 55, 60, 65, 70)


def return_sweep(n_doublets, peak_heat_MW=None, depth_m=DEPTH_M, esp_depth_m=None, extra_return_c=None):
    """Compare network return temperatures 40, 50, 55, 60, 65 and 70 C (plus extra_return_c if given, e.g. an optimised return) for
    1-3 doublets over the 2027 year, reservoir at depth_m
    (default 2500 m), heat demand scaled to peak_heat_MW if given: boiler GWh, heat-pump and ESP electricity GWh, geothermal
    share, unmet heat and peak margin per return, and best_return_c = the lowest return that needs no boiler energy (else the one
    with the least boiler). Use it before calling any return temperature best [C]."""
    rows, swept = {}, SWEEP_C if extra_return_c is None else tuple(sorted({*SWEEP_C, float(extra_return_c)}))
    for t in swept:
        h = _year_row(n_doublets, t, peak_heat_MW, depth_m, esp_depth_m)
        key = str(int(t)) if float(t).is_integer() else str(t)   # "60", or "57.5" for an extra return
        rows[key] = {"boiler_GWh": h["boiler_GWh"], "served_GWh": round(h["demand_GWh"] - h["unmet_GWh"], 2),
                        "boiler_share_pct": round(100 * h["boiler_GWh"] / max(h["demand_GWh"] - h["unmet_GWh"], 1e-9), 2),
                        "heat_pump_electricity_GWh": h["heat_pump_electricity_GWh"],
                        "esp_GWh": h["esp_electricity_GWh"], "geothermal_share_pct": h["geothermal_share_pct"],
                        "unmet_GWh": h["unmet_GWh"], "peak_margin_pct": h["peak_margin_pct"]}
    free = [t for t in swept if rows[str(t)]["boiler_GWh"] < 0.01]
    best = free[0] if free else min(swept, key=lambda t: rows[str(t)]["boiler_GWh"])
    return {"n_doublets": int(n_doublets), "depth_m": depth_m, "by_return_C": rows, "best_return_c": best, "tag": "[C]",
            "backup_boiler_MW": year.BACKUP_BOILER_MW, "backup_boiler_tag": "[L] security of supply, not energy"}
