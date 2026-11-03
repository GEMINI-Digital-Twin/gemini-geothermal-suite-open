"""The design scripts as plain functions the agent may call. Each returns a flat dict, units in the key names."""
import json
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

import geo.gemini_contrib  # noqa: F401  (development tree first; the open release is an identical subset, checked 2 Nov)
from geo.common import DEPTH_M, DT_BRINE_MAX_K, Q_MAX_M3H, Q_MIN_M3H, t_reservoir_c
from geo.gemini_contrib.heatpump_lift import HeatPumpLift
from geo.plant import doublet_at
from geo.well import Producer, injector_at, reservoir_pressure
from geo import cost, year

gwh = lambda s: float(s.sum() * 24 / 1000)
# the GEMINI classes each tool runs (see geo/well.py), so a tool result names the twin's components [C]
PRODUCER_GEMINI = ["IPR", "DPDT", "ESP via similarity law (ESPAffinity-equivalent, F5)", "PVTConstantSTP"]
INJECTOR_GEMINI = ["IPR (injection_reservoir)", "DPDT (signed flow, injector sign fix F6)", "PVTConstantSTP"]


@lru_cache
def gemini_version():
    """Path and git commit of the GEMINI package the tools import (as AI03_agent.gemini_version)."""
    import gemini_model
    root = str(Path(gemini_model.__file__).parents[2])
    sha = subprocess.run(["git", "-C", root, "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    return f"{root} @ {sha or 'no git'}"


def gemini(names):
    return {"gemini_components": names, "gemini_version": gemini_version()}


# a result made JSON-ready: text and bools kept, integers as int, every other number rounded to 2 decimals
def r2(d):
    def one(v):
        if isinstance(v, (str, bool, np.bool_)):
            return v if isinstance(v, str) else bool(v)
        return int(v) if isinstance(v, (int, np.integer)) else round(float(v), 2)
    return {k: one(v) for k, v in d.items()}


def _need(name, x, lo, hi):
    if x is not None and not lo <= x <= hi:
        raise ValueError(f"{name}={x} outside {lo}-{hi}")


def _peaks(peak_heat_MW, peak_cold_MW):
    _need("peak_heat_MW", peak_heat_MW, 1, 100); _need("peak_cold_MW", peak_cold_MW, 0, 50)


def site_inputs(supply_heat_c, supply_cold_c, depth_m=DEPTH_M):
    """Call first. Reservoir at depth_m (1500-4000 m): temperature from the 30 C/km gradient, pressure (the brief's 250 bar at 2500 m, hydrostatic elsewhere), producer wellhead T at 300 m3/h; and whether the design tables cover the supply setpoints (built for 100 C heat / 20 C cold only). Any depth in range is supported: pass the same depth_m to every other tool [D, A]."""
    _need("depth_m", depth_m, 1500, 4000); _need("supply_heat_c", supply_heat_c, 60, 120); _need("supply_cold_c", supply_cold_c, 6, 25)
    w = Producer(depth_m=float(depth_m), stages=24)
    f = w.freq_for_wellhead(300.0)
    ok = supply_heat_c == 100 and supply_cold_c == 20
    problems = [] if ok else ["design tables assume 100 C heat / 20 C cold supply; other setpoints need the exchanger and heat pump recomputed (not implemented)"]
    depth_msg = "" if abs(depth_m - DEPTH_M) < 1e-6 else f" at {depth_m:.0f} m (24 ESP stages and 9.3 MEUR per doublet as at 2500 m [A])"
    return r2({"depth_m": depth_m, "T_reservoir_C": t_reservoir_c(depth_m), "T_reservoir_tag": "[D] 12 C + 30 C/km",
               "p_reservoir_bar": reservoir_pressure(depth_m),
               "p_reservoir_tag": "[D] brief" if abs(depth_m - DEPTH_M) < 1e-6 else "[A] hydrostatic",
               "T_wellhead_300m3h_C": w.run(300.0, f if f is not None else 60.0)["T_wellhead_C"],
               "wellhead_10bar_reached_at_60Hz": f is not None,
               "supply_heat_c": supply_heat_c, "supply_cold_c": supply_cold_c, "supported": ok,
               "message": ("design tables built for 100 C heat / 20 C cold supply" + depth_msg) if ok else "; ".join(problems),
               "tag": "[D, A]"}) | gemini(PRODUCER_GEMINI)


def demand_summary(peak_heat_MW=None, peak_cold_MW=None):
    """Heating and cooling demand of the brief's two daily CSV files for 2027, scaled to peak_heat_MW / peak_cold_MW if given (else the files as they are, 30 / 10 MW): peak MW, peak dates, annual GWh and the cooling season (first and last day with cold demand). Data from the brief [D]."""
    _peaks(peak_heat_MW, peak_cold_MW)
    h, c = year.scaled(year.heat, peak_heat_MW), year.scaled(year.cold, peak_cold_MW)
    season = c[c > 0].index
    return r2({"heat_peak_MW": h.max(), "heat_peak_date": str(h.idxmax().date()), "heat_GWh": gwh(h), "heat_min_MW": h.min(),
            "cold_peak_MW": c.max(), "cold_peak_date": str(c.idxmax().date()), "cold_GWh": gwh(c),
            "cooling_season_start": str(season[0].date()), "cooling_season_end": str(season[-1].date()), "tag": "[D]"})


def doublet_point(q_m3h, t_return_c, depth_m=DEPTH_M):
    """One doublet at flow q_m3h (50-300 m3/h) and network return t_return_c (30-70 C), reservoir at depth_m (default 2500 m), 24-stage ESP to a 10 bar wellhead, exchanger then a brine-source heat pump lifting to 100 C: wellhead T, MW by source, ESP kW, COP, whether the pump is inside its 158-342 m3/h curve. GEMINI models plus our exchanger and Lorenz heat pump [C, A]."""
    _need("q_m3h", q_m3h, Q_MIN_M3H, Q_MAX_M3H); _need("t_return_c", t_return_c, 30, 70); _need("depth_m", depth_m, 1500, 4000)
    w = Producer(depth_m=float(depth_m), stages=24)
    p = doublet_at(w, float(q_m3h), float(t_return_c))
    return r2({"q_m3h": q_m3h, "depth_m": depth_m, "esp_freq_Hz": p["freq_hz"], "T_wellhead_C": p["T_wh_C"], "exchanger_MW": p["MW_hx"],
               "heat_pump_MW": p["MW_hp"], "heat_pump_electricity_MW": p["MW_el_hp"], "boiler_lift_MW": p["MW_boiler_lift"],
               "total_heat_MW": p["MW_out"], "esp_kW": p["kW_esp"], "heat_pump_COP": p["cop"],
               "in_pump_envelope": bool(w.q_min <= q_m3h <= w.q_max), "tag": "[C, A]"}) | gemini(PRODUCER_GEMINI)


@lru_cache
def _heat(n, t, ph=None, depth=DEPTH_M):
    _need("n_doublets", n, 1, 3); _need("t_return_c", t, 30, 70); _peaks(ph, None); _need("depth_m", depth, 1500, 4000)
    return year.heating_year(int(n), float(t), peak_heat_MW=ph, depth_m=float(depth))


@lru_cache
def _cool(n, t, ph=None, pc=None, depth=DEPTH_M):
    _peaks(ph, pc)
    return year.cooling_year(_heat(n, t, ph, depth).surplus, peak_cold_MW=pc)


def heating_year(n_doublets, t_return_c, peak_heat_MW=None, depth_m=DEPTH_M):
    """Daily dispatch over 2027 of 1-3 doublets at a network return of 30-70 C, reservoir at depth_m (default 2500 m), heat demand scaled to peak_heat_MW if given (else 30 MW), staggered 35-day outage per doublet, 16 MW backup boiler: annual GWh by source, electricity (ESP, heat pump, injection pump), unmet heat, capacity, the peak-day MW by source and margin, and brine heat above 78 C left for absorption chillers [C, A]."""
    d, tab = _heat(n_doublets, t_return_c, peak_heat_MW, depth_m), year.table(float(t_return_c), float(depth_m))
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


def cooling_year(t_return_c, n_doublets=2, peak_heat_MW=None, peak_cold_MW=None, depth_m=DEPTH_M):
    """Cold at 20 C over 2027, cold demand scaled to peak_cold_MW if given (else 10 MW): free cooling from the De Bilt wet bulb (26 C return, 4 K tower approach), absorption on the hot brine left by heating_year (same peak_heat_MW and depth_m), electric chillers COP 7 for the rest; GWh and share by source, the peak-day split in MW, electricity of the chillers and of the tower fans and pumps [C, A]."""
    c, t = _cool(n_doublets, t_return_c, peak_heat_MW, peak_cold_MW, depth_m)
    pk = c.cold.idxmax()
    return r2({"cold_GWh": t["cold"], "free_GWh": t["free"], "absorption_GWh": t["absorption"], "electric_GWh": t["electric"],
               "free_pct": 100 * t["free"] / t["cold"], "absorption_pct": 100 * t["absorption"] / t["cold"],
               "electric_pct": 100 * t["electric"] / t["cold"], "peak_day": str(pk.date()), "peak_wet_bulb_C": c.T_wb[pk],
               "peak_free_MW": c.free[pk], "peak_absorption_MW": c.absorption[pk], "peak_electric_MW": c.electric[pk],
               "chiller_electricity_GWh": t["el_chillers"], "aux_electricity_GWh": t["el_aux"],
               "electricity_GWh": t["el_chillers"] + t["el_aux"], "tag": "[C, A]"})


def injector_point(q_m3h, depth_m=DEPTH_M):
    """Injection well at q_m3h (50-300 m3/h), reservoir at depth_m (default 2500 m), brine back at wellhead T minus 40 K: cold injectivity, bottomhole and wellhead pressure needed, injection pump kW, margin to the SodM 0.135 bar/m limit at that depth, and the wellhead pressure GEMINI's own friction sign would give (finding F6) [C, A]."""
    _need("q_m3h", q_m3h, Q_MIN_M3H, Q_MAX_M3H); _need("depth_m", depth_m, 1500, 4000)
    r = injector_at(float(q_m3h), float(depth_m))
    return r2({"q_m3h": q_m3h, "depth_m": depth_m, "T_inj_C": r["T_inj_C"], "injectivity_m3h_per_bar": r["II"], "p_bottomhole_bar": r["p_bh_req_bar"],
               "p_wellhead_bar": r["p_wh_bar"], "p_wellhead_gemini_sign_bar": r["p_wh_gemini_sign_bar"],
               "pump_kW": r["pump_kW"], "sodm_limit_bar": r["sodm_limit_bar"], "sodm_margin_bar": r["sodm_margin_bar"], "tag": "[C, A]"}) \
        | gemini(INJECTOR_GEMINI + ["producer for the brine T: " + ", ".join(PRODUCER_GEMINI)])


def heat_pump_point(t_brine_in_c, t_water_in_c, brine_m3h, water_m3h, t_brine_floor_c=None):
    """GEMINI's own heat pump (HeatpumpBasic, Lorenz mode, via our HeatPumpLift) lifting district water at t_water_in_c (40-99 C, water_m3h 50-600 m3/h) to 100 C on brine at t_brine_in_c (40-90 C, brine_m3h 50-600 m3/h) cooled no lower than t_brine_floor_c (the wellhead T - 40 K; omitted = t_brine_in_c - 40 K, right only with no exchanger upstream): COP, heat and electricity MW, brine and water out, and whether the floor binds (then the water falls short of 100 C). A cross-check of the plant tables, not used by the code plan [C, A]."""
    _need("t_brine_in_c", t_brine_in_c, 40, 90); _need("t_water_in_c", t_water_in_c, 40, 99)
    _need("brine_m3h", brine_m3h, 50, 600); _need("water_m3h", water_m3h, 50, 600)
    floor = t_brine_in_c - DT_BRINE_MAX_K if t_brine_floor_c is None else t_brine_floor_c
    _need("t_brine_floor_c", floor, t_brine_in_c - DT_BRINE_MAX_K - 50, t_brine_in_c)
    hp = HeatPumpLift()
    hp.calculate_output({"T_brine_in_C": t_brine_in_c, "brine_flow_m3h": brine_m3h, "T_brine_floor_C": floor,
                         "T_water_in_C": t_water_in_c, "water_flow_m3h": water_m3h})
    y = hp.get_output()
    return r2({"COP": y["COP"], "Q_th_MW": y["Q_th_MW"], "P_el_MW": y["P_el_MW"], "Q_brine_MW": y["Q_brine_MW"],
               "T_brine_floor_C": floor, "T_brine_out_C": y["T_brine_out_C"], "T_water_out_C": y["T_water_out_C"], "floor_binds": y["floor_binds"],
               "eta_lorenz": hp.parameters["eta_lorenz"], "tag": "[C, A]"}) \
        | gemini(["HeatpumpBasic (Lorenz) via HeatPumpLift, floor-branch root fixed F12"])


def checks(n_doublets, t_return_c, peak_heat_MW=None, peak_cold_MW=None, depth_m=DEPTH_M):
    """The brief's 13 constraints (as in script 08, incl. capacity covers the peak) for 1-3 doublets at a 30-70 C return, reservoir at depth_m (default 2500 m), demand scaled to the given peaks: each row is name: value (limit) -> pass or FAIL [C]."""
    _need("n_doublets", n_doublets, 1, 3); _need("t_return_c", t_return_c, 30, 70); _peaks(peak_heat_MW, peak_cold_MW); _need("depth_m", depth_m, 1500, 4000)
    rows = year.checks(int(n_doublets), float(t_return_c), peak_heat_MW, peak_cold_MW, depth_m=float(depth_m))
    out = {f"{i + 1:02d} {r['name']}": f"{r['value']} (limit {r['limit']}) -> {r['status']}" for i, r in enumerate(rows)}
    n_pass = sum(r["status"].startswith("pass") for r in rows)
    return {**out, "n_pass": n_pass, "n_fail": len(rows) - n_pass, "n_rows": len(rows), "tag": "[C]"}


def economics(n_doublets, t_return_c, peak_heat_MW=None, peak_cold_MW=None, depth_m=DEPTH_M):
    """Cost of 1-3 doublets at a 30-70 C return over 2027, reservoir at depth_m (default 2500 m; doublet price unchanged with depth), demand scaled to the given peaks: CAPEX in MEUR by item (doublets 9.3 MEUR each, heat pump, 16 MW backup boiler, chillers, tower, absorption), annual cost in MEUR, levelised cost of heat lcoh_EUR_MWh (doublets, heat pump, boiler, ESP and injection electricity, gas, CO2) and of cold lcoc_EUR_MWh, electricity, gas and CO2; 5.2 % real, 30/20 yr lives, sourced prices [C, L, A]."""
    _need("n_doublets", n_doublets, 1, 3); _need("t_return_c", t_return_c, 30, 70); _peaks(peak_heat_MW, peak_cold_MW); _need("depth_m", depth_m, 1500, 4000)
    e = cost.economics(int(n_doublets), float(t_return_c), peak_heat_MW, peak_cold_MW, depth_m=float(depth_m))
    cap, ann = e["capex_MEUR"], e["annual_cost_MEUR"]
    flat = {**{f"capex_{k}_MEUR": v for k, v in cap.items()},
            **{f"annual_{side}_{k}_MEUR": v for side in ("heating", "cooling") for k, v in ann[side].items()},
            "annual_total_MEUR": ann["total"]}
    keys = ("n_doublets", "heat_served_GWh", "cold_served_GWh", "lcoh_EUR_MWh", "lcoc_EUR_MWh", "electricity_GWh", "gas_GWh", "co2_kt")
    return {**r2({**{k: e[k] for k in keys}, **flat}), "tag": "[C]", "basis": e["basis"]}


SWEEP_C = (40, 50, 55, 60, 65, 70)


def return_sweep(n_doublets, peak_heat_MW=None, depth_m=DEPTH_M):
    """Compare network return temperatures 40, 50, 55, 60, 65 and 70 C for 1-3 doublets over the 2027 year, reservoir at depth_m (default 2500 m), heat demand scaled to peak_heat_MW if given: boiler GWh, heat-pump and ESP electricity GWh, geothermal share, unmet heat and peak margin per return, and best_return_c = the lowest return that needs no boiler energy (else the one with the least boiler). Use it before calling any return temperature best [C]."""
    rows = {}
    for t in SWEEP_C:
        h = heating_year(n_doublets, t, peak_heat_MW, depth_m)
        rows[str(t)] = {"boiler_GWh": h["boiler_GWh"], "served_GWh": round(h["demand_GWh"] - h["unmet_GWh"], 2),
                        "boiler_share_pct": round(100 * h["boiler_GWh"] / max(h["demand_GWh"] - h["unmet_GWh"], 1e-9), 2), "heat_pump_electricity_GWh": h["heat_pump_electricity_GWh"],
                        "esp_GWh": h["esp_electricity_GWh"], "geothermal_share_pct": h["geothermal_share_pct"],
                        "unmet_GWh": h["unmet_GWh"], "peak_margin_pct": h["peak_margin_pct"]}
    free = [t for t in SWEEP_C if rows[str(t)]["boiler_GWh"] < 0.01]
    best = free[0] if free else min(SWEEP_C, key=lambda t: rows[str(t)]["boiler_GWh"])
    return {"n_doublets": int(n_doublets), "depth_m": depth_m, "by_return_C": rows, "best_return_c": best, "tag": "[C]",
            "backup_boiler_MW": year.BACKUP_BOILER_MW, "backup_boiler_tag": "[L] security of supply, not energy"}


def gemini_traps():
    """GEMINI findings (F1-F6 and F12 of NOTES_findings.md) as short sentences the agent may cite; heat_pump_point runs GEMINI's own heat pump with the F12 fix [C]."""
    return {"F1": "The ESP curve is valid 158-342 m3/h; GEMINI returns numbers at 50 m3/h without warning, so 160 m3/h is the real floor.",
            "F2": "The network return temperature decides the plant: at 55-60 C a brine-source heat pump replaces the boiler.",
            "F3": "Most summer surplus brine is 46-63 C, too cold for absorption; only the slice above 78 C (about 3 GWh) drives chillers.",
            "F4": "Free cooling 77 % rests on a 26 C return, 4 K approach, De Bilt 2024 weather and daily maximum wet bulb (92 % with daily mean).",
            "F5": "GEMINI's ESP reads the head curve at the actual flow, not q*60/f (similarity law); it overstates head at reduced speed, 9 % at 57 Hz and 300 m3/h; corrected in ESPAffinity.",
            "F6": "GEMINI's well model is right (signed flow), but its simulator passes a positive flow for the injector, so friction is added going down and the injector wellhead is understated by 25 bar at 300 m3/h; one-sign fix in gemini_contrib.",
            "F12": "GEMINI's HeatpumpBasic finds an unphysical root (COP 1.0, water out 796 C, 602 MW) when the source floor binds; HeatPumpLift brackets the solve and gets 91 C.",
            "tag": "[C]"}


FUNCS = {f.__name__: f for f in (site_inputs, demand_summary, doublet_point, heating_year, cooling_year, injector_point, heat_pump_point, checks, economics, return_sweep, gemini_traps)}
NUM = lambda desc, lo, hi, kind="number": {"type": kind, "description": f"{desc}, {lo} to {hi}", "minimum": lo, "maximum": hi}
ARGS = {"depth_m": NUM("reservoir depth in m (omit for the brief's 2500 m); give the brief's depth to every tool", 1500, 4000), "supply_heat_c": NUM("heating supply temperature in C", 60, 120),
        "supply_cold_c": NUM("cooling supply temperature in C", 6, 25), "q_m3h": NUM("flow per well in m3/h", 50, 300), "t_return_c": NUM("network return temperature in C", 30, 70),
        "n_doublets": NUM("number of doublets", 1, 3, "integer"),
        "t_brine_in_c": NUM("brine temperature into the heat pump evaporator in C", 40, 90),
        "t_water_in_c": NUM("district water temperature into the heat pump condenser in C", 40, 99),
        "t_brine_floor_c": NUM("coldest brine allowed out of the evaporator in C, the wellhead T minus 40 K (omit: brine in minus 40 K)", 0, 90),
        "brine_m3h": NUM("brine flow through the evaporator in m3/h", 50, 600), "water_m3h": NUM("district water flow through the condenser in m3/h", 50, 600),
        "peak_heat_MW": NUM("peak heating demand of the brief in MW (omit for the 30 MW demand file)", 1, 100),
        "peak_cold_MW": NUM("peak cooling demand of the brief in MW (omit for the 10 MW demand file)", 0, 50)}
PEAKS = ["peak_heat_MW", "peak_cold_MW"]
OPTIONAL = PEAKS + ["t_brine_floor_c", "depth_m"]
D = ["depth_m"]
SIG = {"site_inputs": ["depth_m", "supply_heat_c", "supply_cold_c"], "demand_summary": PEAKS, "doublet_point": ["q_m3h", "t_return_c"] + D, "heating_year": ["n_doublets", "t_return_c", "peak_heat_MW"] + D,
       "cooling_year": ["t_return_c", "n_doublets"] + PEAKS + D, "injector_point": ["q_m3h"] + D,
       "heat_pump_point": ["t_brine_in_c", "t_water_in_c", "brine_m3h", "water_m3h", "t_brine_floor_c"], "checks": ["n_doublets", "t_return_c"] + PEAKS + D, "economics": ["n_doublets", "t_return_c"] + PEAKS + D,
       "return_sweep": ["n_doublets", "peak_heat_MW"] + D, "gemini_traps": []}
TOOLS = [{"type": "function", "function": {"name": n, "description": " ".join(FUNCS[n].__doc__.split()),
          "parameters": {"type": "object", "properties": {a: ARGS[a] for a in args},
                         "required": [a for a in args if a not in OPTIONAL]}}} for n, args in SIG.items()]


def call(name, args):
    if name not in FUNCS:
        raise ValueError(f"unknown tool {name}; valid: {sorted(FUNCS)}")
    conv = lambda k, v: v if v is None else int(v) if k == "n_doublets" else float(v)
    return FUNCS[name](**{k: conv(k, v) for k, v in (args or {}).items()})


if __name__ == "__main__":
    for name, args in (("site_inputs", {"depth_m": 2500, "supply_heat_c": 100, "supply_cold_c": 20}), ("demand_summary", {}), ("doublet_point", {"q_m3h": 300, "t_return_c": 60}),
                       ("heating_year", {"n_doublets": 2, "t_return_c": 60}), ("cooling_year", {"t_return_c": 60}),
                       ("injector_point", {"q_m3h": 300}), ("heat_pump_point", {"t_brine_in_c": 63, "t_water_in_c": 82.58, "brine_m3h": 300, "water_m3h": 388, "t_brine_floor_c": 45.58}),
                       ("checks", {"n_doublets": 2, "t_return_c": 60}), ("economics", {"n_doublets": 2, "t_return_c": 60}), ("return_sweep", {"n_doublets": 2}),
                       ("gemini_traps", {})):
        print(f"\n{name}({args})\n" + json.dumps(call(name, args), indent=1))
    print(f"\n{len(TOOLS)} tools, about {len(json.dumps(TOOLS)) // 4} tokens of schema")
