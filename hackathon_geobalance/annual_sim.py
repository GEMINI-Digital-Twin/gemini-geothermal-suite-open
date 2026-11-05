"""365-day evaluation of an integrated geothermal heating + cooling design.

Wells and pumps come from GEMINI (gemini_wrapper). Surface components use
the GeoBalance tools (tools.py) and GEMINI's Carnot heat pump formula.
Each day the cheapest source is used first:
  direct geothermal heat -> heat pump top-up -> gas engine heat -> storage -> backup boiler
  absorption chiller (geothermal) -> electric chiller
The full system must meet demand on all 365 days; each doublet has a
35-day outage (330 days geothermal availability).
"""
import csv
import math
from pathlib import Path

import gemini_wrapper as gw
import tools
from storage import HeatStorage

DATA = Path(__file__).resolve().parent / "data"
RC = tools.RHO * tools.CP / 3600 / 1e6          # MW per (m3/h * K)
SUPPLY_HEAT_C = 100.0
SUPPLY_COOL_C = 20.0
CHILLER_BRINE_OUT_C = 70.0
CHILLER_MIN_DRIVE_C = 80.0
ABS_COP, ELEC_CHILLER_COP = 0.7, 5.0
BOILER_EFF, BOILER_CO2_KG_KWH_FUEL = 0.92, 0.202
APPROACH_C = 5.0
OUTAGE_DAYS = 35

DEFAULT_DESIGN = {
    "name": "baseline",
    "depth_m": 2500,
    "n_doublets": 2,
    "target_flow_m3h": 250,          # per doublet; GEMINI sizes the ESP for it
    "network_return_c": 50,
    "heating_mode": "preheat_hp",    # preheat_hp | direct | hp_only
    "absorption_chiller": True,
    "gas_use": "engine",             # engine | flare | reinject
    "storage_mwh": 0,
    "maintenance_start_day": None,   # list, one start day (0-364) per doublet
}


def load_demand():
    def read(name, col):
        with open(DATA / name, newline="") as f:
            rows = list(csv.DictReader(f))
        return [r["date"] for r in rows], [float(r[col]) for r in rows]
    dates, heat = read("gemini_heating_demand_daily_2027.csv", "heating_demand_MWth")
    _, cool = read("gemini_cooling_demand_daily_2027.csv", "cooling_demand_MWcool")
    return dates, heat, cool


def demand_summary():
    dates, H, C = load_demand()
    month = {}
    for d, h, c in zip(dates, H, C):
        m = d[5:7]
        month.setdefault(m, [0, 0, 0])
        month[m][0] += h * 24 / 1000
        month[m][1] += c * 24 / 1000
        month[m][2] = max(month[m][2], h)
    return {
        "heating_peak_mw": max(H), "heating_peak_date": dates[H.index(max(H))],
        "heating_min_mw": min(H), "heating_gwh": round(sum(H) * 24 / 1000, 2),
        "cooling_peak_mw": max(C), "cooling_peak_date": dates[C.index(max(C))],
        "cooling_gwh": round(sum(C) * 24 / 1000, 2),
        "zero_cooling_days": sum(1 for c in C if c == 0),
        "monthly_gwh_heat_cool_peakheat": {m: [round(a, 2), round(b, 2), round(p, 1)]
                                           for m, (a, b, p) in month.items()},
    }


def hp_cop(source_in_c, source_out_c, supply_c=SUPPLY_HEAT_C, eta=0.5, cap=6.0):
    """GEMINI HeatpumpBasic Carnot formula, COP = eta*Th/(Th-Ts), with the mean
    source temperature (more conservative than GEMINI's source-inlet value)."""
    th = supply_c + 273.15
    ts = (source_in_c + source_out_c) / 2 + 273.15
    return min(eta * th / (th - ts), cap)


def _maintenance(design, n):
    starts = design.get("maintenance_start_day")
    if starts is None:   # default: staggered spring windows (low demand, little cooling)
        starts = [82 + 35 * i for i in range(n)]  # 24 Mar, 28 Apr, 2 Jun
    return list(starts)


def evaluate_design(design=None, save_daily=None):
    d = dict(DEFAULT_DESIGN, **(design or {}))
    violations, warnings = [], []
    n = int(d["n_doublets"])
    if not 1 <= n <= 3:
        violations.append(f"n_doublets={n}: must be 1-3")
        return {"design": d, "violations": violations, "warnings": warnings}
    starts = _maintenance(d, n)
    if len(starts) != n or any(not 0 <= s <= 365 - OUTAGE_DAYS for s in starts):
        violations.append("maintenance_start_day needs one start day (0-330) per doublet")
        return {"design": d, "violations": violations, "warnings": warnings}
    for a in range(n):
        for b in range(a + 1, n):
            overlap = max(0, min(starts[a], starts[b]) + OUTAGE_DAYS - max(starts[a], starts[b]))
            if overlap:
                violations.append(f"Doublets {a + 1} and {b + 1} are offline at the same time on {overlap} "
                                  "days: stagger the 35-day outages (e.g. start days 82 and 117)")
    for k, s0 in enumerate(starts):
        heating_season = sum(1 for day in range(s0, s0 + OUTAGE_DAYS) if day < 59 or day >= 319)
        if heating_season:
            warnings.append(f"Doublet {k + 1} outage has {heating_season} days in the peak heating season "
                            "(Dec-Feb / mid-Nov): move it to spring (start day 82-130) or late summer")

    # --- GEMINI: size one doublet (all doublets identical) ---
    well = gw.size_doublet(d["depth_m"], d["target_flow_m3h"])
    if "error" in well:
        violations.append("GEMINI sizing failed: " + well["error"])
        return {"design": d, "violations": violations, "warnings": warnings}
    for w in well["warnings"]:
        (violations if "NON-PHYSICAL" in w else warnings).append("GEMINI: " + w)
    q_d = well["flow_m3h"]
    tw = well["brine_temp_at_plant_c"]
    t_res = well["reservoir_temperature_c"]
    t_inj_min = t_res - tools.MAX_BRINE_DT
    tr = float(d["network_return_c"])
    pump_per_doublet = well["esp_power_mw"] + well["injector_pump_mw"]
    if tr + APPROACH_C <= t_inj_min:
        warnings.append(f"Network return {tr} C: brine leaving the direct heat exchanger is "
                        f"limited to {t_inj_min:.0f} C by the 40 C cooling cap")
    if d["heating_mode"] == "hp_only" and tw > tr:
        warnings.append(f"hp_only: brine {tw:.0f} C is hotter than the {tr:.0f} C network return, "
                        "so sending all heat through a heat pump wastes exergy and electricity. "
                        "(Note: GEMINI's heat pump solver fails for this case and returns ~390 C; that is "
                        "a solver error, NOT a real temperature. Our simulation uses COP 3.) Prefer preheat_hp.")
    if d["absorption_chiller"] and tw < CHILLER_MIN_DRIVE_C:
        warnings.append(f"Brine {tw:.0f} C below absorption drive temperature "
                        f"{CHILLER_MIN_DRIVE_C:.0f} C: absorption disabled")

    chiller_out = max(CHILLER_BRINE_OUT_C, t_inj_min)   # respect the 40 C brine cooling cap
    dates, H, C = load_demand()
    tank = HeatStorage(d["storage_mwh"])
    acc = {k: 0.0 for k in ["direct", "hp_heat", "engine_heat", "storage_out", "boiler",
                            "abs_cool", "elec_cool", "hp_el", "chiller_el", "pump_el",
                            "engine_el", "grid_el", "co2_grid", "co2_gas", "co2_boiler",
                            "storage_in", "geo_heat"]}
    peaks = {"boiler_mw": 0.0, "elec_chiller_mw": 0.0, "hp_out_mw": 0.0, "flow_m3h": 0.0}
    days_capped = days_min_flow = 0
    rows = []
    for i, (date, h, c) in enumerate(zip(dates, H, C)):
        avail = sum(1 for s in starts if not (s <= i < s + OUTAGE_DAYS))
        qmax = avail * q_d
        tank.step_losses()
        # ---- cooling: absorption first ----
        chiller_on = d["absorption_chiller"] and tw >= CHILLER_MIN_DRIVE_C and c > 0
        a_full = c / ABS_COP if chiller_on else 0.0
        f_ch = a_full / (RC * max(tw - chiller_out, 0.1)) if chiller_on else 0.0
        # ---- heating: direct heat exchanger, then top-up ----
        use_hp = d["heating_mode"] in ("preheat_hp", "hp_only")
        brine_out_direct = max(tr + APPROACH_C, t_inj_min)

        def heating(tb):
            t_direct = min(SUPPLY_HEAT_C, tb - APPROACH_C)
            frac = max(0.0, (t_direct - tr) / (SUPPLY_HEAT_C - tr))
            if d["heating_mode"] == "hp_only":
                frac = 0.0
            direct = h * frac
            cop = 3.0 if d["heating_mode"] == "hp_only" else hp_cop(tb, t_inj_min)
            hp_out = (h - direct) if use_hp else 0.0
            hp_el = hp_out / cop if use_hp else 0.0
            evap = hp_out - hp_el
            f_h = 0.0
            if direct > 0:
                f_h += direct / (RC * max(tb - brine_out_direct, 0.1))
            if evap > 0:
                f_h += evap / (RC * max(tb - t_inj_min, 0.1))
            return frac, direct, cop, hp_out, hp_el, f_h

        # Parallel: chiller and heating both get wellhead brine.
        # Series cascade: heating uses the brine leaving the chiller.
        # Pick whichever needs less total brine flow today.
        par = heating(tw)
        need_par = f_ch + par[5]
        series = False
        if chiller_on and d["heating_mode"] != "direct":
            ser = heating(chiller_out)
            need_ser = max(f_ch, ser[5])
            series = need_ser < need_par
        frac, direct, cop, hp_out, hp_el, f_h = ser if series else par
        need = need_ser if series else need_par
        # ---- capacity limit ----
        abs_heat = a_full
        if need > qmax:
            days_capped += 1
            if series:
                if chiller_on and f_ch > qmax:
                    abs_heat = qmax * RC * (tw - chiller_out)
                f_h_cap = qmax
            else:   # parallel: heating gets priority, chiller gets the rest of the flow
                f_h_cap = min(f_h, qmax)
                if chiller_on:
                    abs_heat = min(a_full, (qmax - f_h_cap) * RC * (tw - chiller_out))
            if f_h > f_h_cap:
                s = f_h_cap / f_h if f_h > 0 else 0.0
                direct, hp_out, hp_el = direct * s, hp_out * s, hp_el * s
            need = min(need, qmax)
        abs_cool = abs_heat * ABS_COP
        elec_cool = c - abs_cool
        # ---- minimum stable flow per active doublet ----
        flow = need
        n_act = min(avail, max(1, math.ceil(flow / q_d - 1e-9))) if (flow > 0 and avail) else 0
        if n_act and flow / n_act < tools.MIN_FLOW:
            flow = tools.MIN_FLOW * n_act
            days_min_flow += 1
        peaks["flow_m3h"] = max(peaks["flow_m3h"], flow)
        # ---- associated gas ----
        gas = tools.gas_engine(flow)
        engine_el = gas["electricity_mw"] if d["gas_use"] == "engine" else 0.0
        engine_heat = gas["heat_mw"] if d["gas_use"] == "engine" else 0.0
        co2_gas = 0.0 if d["gas_use"] == "reinject" else gas["co2_t_per_h"] * 24
        # ---- heat balance: engine heat, storage, boiler ----
        delivered = direct + (hp_out if use_hp else 0.0)
        short = max(0.0, h - delivered)
        used_engine = min(engine_heat, short)
        short -= used_engine
        if used_engine < engine_heat and use_hp and hp_out > 0:   # spare engine heat replaces HP output
            extra = min(engine_heat - used_engine, hp_out)
            hp_el -= extra / cop
            hp_out -= extra
            used_engine += extra
        from_tank = tank.discharge(short)
        short -= from_tank
        boiler = short
        # charge tank with spare geothermal capacity (top-up by heat pump where needed)
        stored = 0.0
        if tank.capacity > 0 and qmax > flow and boiler == 0:
            spare_heat = (qmax - flow) * RC * (tw - brine_out_direct)
            stored = tank.charge(spare_heat)
            if stored and frac < 1 and use_hp:
                hp_el += stored * (1 - frac) / cop
        # ---- electricity and CO2 ----
        pump_el = n_act * pump_per_doublet * ((flow / n_act) / q_d) ** 2 if n_act else 0.0
        chiller_el = elec_cool / ELEC_CHILLER_COP
        total_el = hp_el + chiller_el + pump_el
        grid_el = max(0.0, total_el - engine_el)
        co2_grid = grid_el * 24 * gw.GRID_CO2_KG_KWH
        co2_boiler = boiler / BOILER_EFF * 24 * BOILER_CO2_KG_KWH_FUEL
        geo_heat = direct + (hp_out - hp_el if use_hp else 0) + abs_heat
        for k, v in [("direct", direct), ("hp_heat", hp_out), ("engine_heat", used_engine),
                     ("storage_out", from_tank), ("boiler", boiler), ("abs_cool", abs_cool),
                     ("elec_cool", elec_cool), ("hp_el", hp_el), ("chiller_el", chiller_el),
                     ("pump_el", pump_el), ("engine_el", min(engine_el, total_el)),
                     ("grid_el", grid_el), ("storage_in", stored), ("geo_heat", geo_heat)]:
            acc[k] += v * 24 / 1000          # GWh
        acc["co2_grid"] += co2_grid
        acc["co2_gas"] += co2_gas
        acc["co2_boiler"] += co2_boiler
        peaks["boiler_mw"] = max(peaks["boiler_mw"], boiler)
        peaks["elec_chiller_mw"] = max(peaks["elec_chiller_mw"], elec_cool)
        peaks["hp_out_mw"] = max(peaks["hp_out_mw"], hp_out)
        rows.append({"date": date, "doublets_available": avail, "doublets_active": n_act,
                     "flow_m3h": round(flow, 1), "heat_demand_mw": h, "direct_mw": round(direct, 3),
                     "heat_pump_mw": round(hp_out, 3), "engine_heat_mw": round(used_engine, 3),
                     "storage_out_mw": round(from_tank, 3), "boiler_mw": round(boiler, 3),
                     "cool_demand_mw": c, "absorption_mw": round(abs_cool, 3),
                     "electric_chiller_mw": round(elec_cool, 3), "grid_el_mw": round(grid_el, 3),
                     "storage_soc_mwh": round(tank.soc, 1)})

    heat_total = sum(H) * 24 / 1000
    cool_total = sum(C) * 24 / 1000
    served_heat = acc["direct"] + acc["hp_heat"] + acc["engine_heat"] + acc["storage_out"] + acc["boiler"]
    served_cool = acc["abs_cool"] + acc["elec_cool"]
    co2_total = acc["co2_grid"] + acc["co2_gas"] + acc["co2_boiler"]   # t
    ref_co2 = (heat_total / BOILER_EFF * BOILER_CO2_KG_KWH_FUEL * 1000
               + cool_total / ELEC_CHILLER_COP * gw.GRID_CO2_KG_KWH * 1000)     # t, gas boiler + chiller
    if abs(served_heat - heat_total) > 0.01 or abs(served_cool - cool_total) > 0.01:
        violations.append(f"Demand not met: heat {served_heat:.2f}/{heat_total:.2f} GWh, "
                          f"cool {served_cool:.2f}/{cool_total:.2f} GWh")
    boiler_share = acc["boiler"] / heat_total * 100
    if boiler_share > 10:
        warnings.append(f"Backup boiler supplies {boiler_share:.0f}% of heat")
    if days_capped:
        warnings.append(f"Geothermal flow at capacity on {days_capped} days (backup used)")
    if days_min_flow:
        warnings.append(f"Minimum stable flow forced on {days_min_flow} days")

    summary = {
        "design": d,
        "gemini_doublet": {k: well[k] for k in ("flow_m3h", "esp_stages", "tubing_id_m", "esp_freq_hz",
                                                "esp_power_mw", "esp_intake_bar", "injector_pump_mw",
                                                "brine_temp_at_plant_c", "reservoir_temperature_c",
                                                "reservoir_pressure_bar")},
        "maintenance_start_days": starts,
        "demand_met": not any("Demand not met" in v for v in violations),
        "heat_gwh": {"demand": round(heat_total, 2), "direct_geothermal": round(acc["direct"], 2),
                     "heat_pump": round(acc["hp_heat"], 2), "gas_engine": round(acc["engine_heat"], 2),
                     "storage": round(acc["storage_out"], 2), "backup_boiler": round(acc["boiler"], 2)},
        "cool_gwh": {"demand": round(cool_total, 2), "absorption": round(acc["abs_cool"], 2),
                     "electric_chiller": round(acc["elec_cool"], 2)},
        "electricity_gwh": {"heat_pump": round(acc["hp_el"], 2), "electric_chiller": round(acc["chiller_el"], 2),
                            "pumps": round(acc["pump_el"], 2), "gas_engine_supply": round(acc["engine_el"], 2),
                            "from_grid": round(acc["grid_el"], 2)},
        "co2_t": {"grid": round(acc["co2_grid"]), "associated_gas": round(acc["co2_gas"]),
                  "boiler": round(acc["co2_boiler"]), "total": round(co2_total),
                  "reference_gas_boiler_plus_chiller": round(ref_co2),
                  "reduction_pct": round((1 - co2_total / ref_co2) * 100, 1)},
        "equipment_mw": {"heat_pump": round(peaks["hp_out_mw"], 1), "backup_boiler": round(peaks["boiler_mw"], 1),
                         "electric_chiller": round(peaks["elec_chiller_mw"], 1),
                         "absorption_chiller": 10.0 if d["absorption_chiller"] else 0.0,
                         "peak_brine_flow_m3h": round(peaks["flow_m3h"])},
        "renewable_heat_share_pct": round((acc["direct"] + acc["hp_heat"]) / heat_total * 100, 1),
        "violations": violations,
        "warnings": warnings,
    }
    if save_daily:
        with open(save_daily, "w", newline="") as f:
            wr = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            wr.writeheader()
            wr.writerows(rows)
    return summary


if __name__ == "__main__":
    import json
    print(json.dumps(demand_summary(), indent=1)[:600])
    for des in [{"name": "shallow_preheat_hp"},
                {"name": "hp_only (her first idea)", "heating_mode": "hp_only"},
                {"name": "deep_direct", "depth_m": 3400, "heating_mode": "direct", "n_doublets": 3}]:
        r = evaluate_design(des)
        print("\n==", des["name"])
        print(json.dumps({k: r.get(k) for k in ("heat_gwh", "cool_gwh", "electricity_gwh", "co2_t",
                                                 "equipment_mw", "violations", "warnings")}, indent=1))
