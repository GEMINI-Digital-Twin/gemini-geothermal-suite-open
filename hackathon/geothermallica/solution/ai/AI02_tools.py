"""The design scripts as plain functions the agent may call. Each returns a flat dict, units in the key names."""
import json
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

import geo.gemini_path  # noqa: F401  (GEMINI tree with our models first)
from geo.common import DEPTH_M, DT_BRINE_MAX_K, Q_MAX_M3H, Q_MIN_M3H, t_reservoir_c
from gemini_model.heatpump.heatpump_lift import HeatPumpLift
from geo.plant import doublet_at
from geo.well import ESP_DEPTH_M, Producer, injector_at, reservoir_pressure
from geo import cost, gas, gemini_project, lifetime, optimise, outage, storage, year

gwh = lambda s: float(s.sum() * 24 / 1000)
# the GEMINI classes each tool runs, so a tool result names the twin's components
PRODUCER_GEMINI = ["IPR", "DPDT", "ESP via similarity law (ESPAffinity-equivalent)", "PVTConstantSTP"]
INJECTOR_GEMINI = ["IPR (injection_reservoir)", "DPDT (signed flow, injector sign fix)", "PVTConstantSTP"]


@lru_cache
def gemini_version():
    """Path and git commit of the GEMINI package the tools import."""
    import gemini_model
    root = Path(gemini_model.__file__).parents[2]
    sha = subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    return f"{_short(root)} @ {sha or 'no git'}"


def _short(path):
    """A path written from the home directory as ~/..., so no user name leaks into tool results."""
    try:
        return "~/" + str(path.relative_to(Path.home()))
    except ValueError:
        return str(path)


def gemini(names):
    return {"gemini_components": names, "gemini_version": gemini_version()}


# a result made JSON-ready: text and bools kept, integers as int, every other number rounded to 2 decimals
def r2(d):
    def one(k, v):
        if isinstance(v, (str, bool, np.bool_)):
            return v if isinstance(v, str) else bool(v)
        if isinstance(v, (int, np.integer)):
            return int(v)
        return round(float(v), 3 if k.startswith("co2_") else 2)   # CO2 in kt keeps 3 decimals (front rows differ by 0.03 kt)
    return {k: one(k, v) for k, v in d.items()}


def _need(name, x, lo, hi):
    if x is not None and not lo <= x <= hi:
        raise ValueError(f"{name}={x} outside {lo}-{hi}")


def _peaks(peak_heat_MW, peak_cold_MW):
    _need("peak_heat_MW", peak_heat_MW, 1, 100)
    _need("peak_cold_MW", peak_cold_MW, 0, 50)


def _esp(esp_depth_m):
    """ESP setting depth 300-1 250 m (ThermoGIS keeps the pump above half the TVD); None = the 1 100 m default."""
    _need("esp_depth_m", esp_depth_m, 300, 1250)
    return ESP_DEPTH_M if esp_depth_m is None else float(esp_depth_m)


def site_inputs(supply_heat_c, supply_cold_c, depth_m=DEPTH_M):
    """Call first. Reservoir at depth_m (1500-4000 m): temperature from the 30 C/km gradient, pressure (the brief's 250 bar at 2500
    m, hydrostatic elsewhere), producer wellhead T at 300 m3/h; and whether the design tables cover the supply setpoints (built
    for 100 C heat / 20 C cold only). Any depth in range is supported: pass the same depth_m to every other tool [D, A]."""
    _need("depth_m", depth_m, 1500, 4000)
    _need("supply_heat_c", supply_heat_c, 60, 120)
    _need("supply_cold_c", supply_cold_c, 6, 25)
    w = Producer(depth_m=float(depth_m), stages=24)
    f = w.freq_for_wellhead(300.0)
    ok = supply_heat_c == 100 and supply_cold_c == 20
    problems = [] if ok else ["design tables assume 100 C heat / 20 C cold supply; other setpoints need the exchanger and heat pump "
                              "recomputed (not implemented)"]
    depth_msg = "" if abs(depth_m - DEPTH_M) < 1e-6 else (f" at {depth_m:.0f} m (24 ESP stages as at 2500 m [A]; "
                                                          "doublet price on the ThermoGIS depth curve [L])")
    return r2({"depth_m": depth_m, "T_reservoir_C": t_reservoir_c(depth_m), "T_reservoir_tag": "[D] 12 C + 30 C/km",
               "p_reservoir_bar": reservoir_pressure(depth_m),
               "p_reservoir_tag": "[D] brief" if abs(depth_m - DEPTH_M) < 1e-6 else "[A] hydrostatic",
               "T_wellhead_300m3h_C": w.run(300.0, f if f is not None else 60.0)["T_wellhead_C"],
               "wellhead_10bar_reached_at_60Hz": f is not None,
               "supply_heat_c": supply_heat_c, "supply_cold_c": supply_cold_c, "supported": ok,
               "message": ("design tables built for 100 C heat / 20 C cold supply" + depth_msg) if ok else "; ".join(problems),
               "tag": "[D, A]"}) | gemini(PRODUCER_GEMINI)


def demand_summary(peak_heat_MW=None, peak_cold_MW=None):
    """Heating and cooling demand of the brief's two daily CSV files for 2027, scaled to peak_heat_MW / peak_cold_MW if given (else
    the files as they are, 30 / 10 MW): peak MW, peak dates, annual GWh and the cooling season (first and last day with cold
    demand). Data from the brief [D]."""
    _peaks(peak_heat_MW, peak_cold_MW)
    h, c = year.scaled(year.heat, peak_heat_MW), year.scaled(year.cold, peak_cold_MW)
    season = c[c > 0].index
    return r2({"heat_peak_MW": h.max(), "heat_peak_date": str(h.idxmax().date()), "heat_GWh": gwh(h), "heat_min_MW": h.min(),
            "cold_peak_MW": c.max(), "cold_peak_date": str(c.idxmax().date()), "cold_GWh": gwh(c),
            "cooling_season_start": str(season[0].date()), "cooling_season_end": str(season[-1].date()), "tag": "[D]"})


def doublet_point(q_m3h, t_return_c, depth_m=DEPTH_M, esp_depth_m=None):
    """One doublet at flow q_m3h (50-300 m3/h) and network return t_return_c (30-70 C), reservoir at depth_m (default 2500 m),
    24-stage ESP to a 10 bar wellhead, exchanger then a brine-source heat pump lifting to 100 C: wellhead T, MW by source, ESP kW,
    COP, whether the pump is inside its 158-342 m3/h curve. GEMINI models plus our exchanger and Lorenz heat pump [C, A]."""
    _need("q_m3h", q_m3h, Q_MIN_M3H, Q_MAX_M3H)
    _need("t_return_c", t_return_c, 30, 70)
    _need("depth_m", depth_m, 1500, 4000)
    w = Producer(depth_m=float(depth_m), stages=24, esp_depth_m=_esp(esp_depth_m))
    p = doublet_at(w, float(q_m3h), float(t_return_c))
    return r2({"q_m3h": q_m3h, "depth_m": depth_m, "esp_freq_Hz": p["freq_hz"], "T_wellhead_C": p["T_wh_C"], "exchanger_MW": p["MW_hx"],
               "heat_pump_MW": p["MW_hp"], "heat_pump_electricity_MW": p["MW_el_hp"], "boiler_lift_MW": p["MW_boiler_lift"],
               "total_heat_MW": p["MW_out"], "esp_kW": p["kW_esp"], "heat_pump_COP": p["cop"],
               "in_pump_envelope": bool(w.q_min <= q_m3h <= w.q_max), "tag": "[C, A]"}) | gemini(PRODUCER_GEMINI)


@lru_cache
def _heat(n, t, ph=None, depth=DEPTH_M, esp=None, mode="staggered"):
    _need("n_doublets", n, 1, 3)
    _need("t_return_c", t, 30, 70)
    _peaks(ph, None)
    _need("depth_m", depth, 1500, 4000)
    _mode(mode)
    return year.heating_year(int(n), float(t), peak_heat_MW=ph, depth_m=float(depth), esp_depth_m=_esp(esp), outage_mode=mode)


@lru_cache
def _cool(n, t, ph=None, pc=None, depth=DEPTH_M, esp=None):
    _peaks(ph, pc)
    return year.cooling_year(_heat(n, t, ph, depth, esp).surplus, peak_cold_MW=pc)


def _mode(outage_mode):
    if outage_mode not in outage.MODES:
        raise ValueError(f"outage_mode={outage_mode} not one of {outage.MODES}")
    return outage_mode


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


def injector_point(q_m3h, depth_m=DEPTH_M):
    """Injection well at q_m3h (50-300 m3/h), reservoir at depth_m (default 2500 m), brine back at wellhead T minus 40 K: cold
    injectivity, bottomhole and wellhead pressure needed, injection pump kW, margin to the SodM 0.135 bar/m limit at that depth,
    and the wellhead pressure GEMINI's own friction sign would give [C, A]."""
    _need("q_m3h", q_m3h, Q_MIN_M3H, Q_MAX_M3H)
    _need("depth_m", depth_m, 1500, 4000)
    r = injector_at(float(q_m3h), float(depth_m))
    return r2({"q_m3h": q_m3h, "depth_m": depth_m, "T_inj_C": r["T_inj_C"], "injectivity_m3h_per_bar": r["II"], "p_bottomhole_bar": r["p_bh_req_bar"],
               "p_wellhead_bar": r["p_wh_bar"], "p_wellhead_gemini_sign_bar": r["p_wh_gemini_sign_bar"],
               "pump_kW": r["pump_kW"], "sodm_limit_bar": r["sodm_limit_bar"], "sodm_margin_bar": r["sodm_margin_bar"], "tag": "[C, A]"}) \
        | gemini(INJECTOR_GEMINI + ["producer for the brine T: " + ", ".join(PRODUCER_GEMINI)])


def heat_pump_point(t_brine_in_c, t_water_in_c, brine_m3h, water_m3h, t_brine_floor_c=None):
    """GEMINI's own heat pump (HeatpumpBasic, Lorenz mode, via our HeatPumpLift) lifting district water at t_water_in_c (40-99 C,
    water_m3h 50-600 m3/h) to 100 C on brine at t_brine_in_c (40-90 C, brine_m3h 50-600 m3/h) cooled no lower than t_brine_floor_c
    (the wellhead T - 40 K; omitted = t_brine_in_c - 40 K, right only with no exchanger upstream): COP, heat and electricity MW,
    brine and water out, and whether the floor binds (then the water falls short of 100 C). A cross-check of the plant tables, not
    used by the code plan [C, A]."""
    _need("t_brine_in_c", t_brine_in_c, 40, 90)
    _need("t_water_in_c", t_water_in_c, 40, 99)
    _need("brine_m3h", brine_m3h, 50, 600)
    _need("water_m3h", water_m3h, 50, 600)
    floor = t_brine_in_c - DT_BRINE_MAX_K if t_brine_floor_c is None else t_brine_floor_c
    _need("t_brine_floor_c", floor, t_brine_in_c - DT_BRINE_MAX_K - 50, t_brine_in_c)
    hp = HeatPumpLift()
    hp.calculate_output({"T_brine_in_C": t_brine_in_c, "brine_flow_m3h": brine_m3h, "T_brine_floor_C": floor,
                         "T_water_in_C": t_water_in_c, "water_flow_m3h": water_m3h})
    y = hp.get_output()
    return r2({"COP": y["COP"], "Q_th_MW": y["Q_th_MW"], "P_el_MW": y["P_el_MW"], "Q_brine_MW": y["Q_brine_MW"],
               "T_brine_floor_C": floor, "T_brine_out_C": y["T_brine_out_C"], "T_water_out_C": y["T_water_out_C"], "floor_binds": y["floor_binds"],
               "eta_lorenz": hp.parameters["eta_lorenz"], "tag": "[C, A]"}) \
        | gemini(["HeatpumpBasic (Lorenz) via HeatPumpLift, floor-branch root fixed"])


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
    n_declared = sum("declared" in r["status"] for r in rows)   # rows true by construction or set as inputs, not computed
    summary = f"{n_pass}/{len(rows)} pass ({len(rows) - n_declared} computed + {n_declared} declared rows)"
    return {**out, "n_pass": n_pass, "n_fail": len(rows) - n_pass, "n_rows": len(rows), "n_declared": n_declared,
            "summary": summary, "tag": "[C]"}


def economics(n_doublets, t_return_c, peak_heat_MW=None, peak_cold_MW=None, depth_m=DEPTH_M, esp_depth_m=None, outage_mode="staggered",
              gas_handling=gas.GAS_HANDLING):
    """Cost of 1-3 doublets at a 30-70 C return over 2027, reservoir at depth_m (default 2500 m; doublet price from the ThermoGIS
    well-cost curve at that depth, 9.33 MEUR at 2500 m), demand scaled to the given peaks: CAPEX in MEUR by item (doublets, heat
    pump, 16 MW backup boiler, chillers, tower, absorption), annual cost in MEUR, levelised cost of heat lcoh_EUR_MWh (doublets,
    heat pump, boiler, ESP and injection electricity, gas, CO2) and of cold lcoc_EUR_MWh, electricity, gas; CO2 kt from the boiler gas
    (co2_kt), grid electricity at 0.3 kg/kWh, the associated gas as handled by gas_handling (vent, flare, engine, boiler or
    reinject; default engine; reinject adds its compression electricity, associated_gas_compression_GWh, to the bill and the
    grid CO2) and the total; 5.2 % real, 30/20 yr lives, sourced prices [C, L, A]."""
    _need("n_doublets", n_doublets, 1, 3)
    _need("t_return_c", t_return_c, 30, 70)
    _peaks(peak_heat_MW, peak_cold_MW)
    _need("depth_m", depth_m, 1500, 4000)
    if gas_handling not in gas.OPTIONS:
        raise ValueError(f"gas_handling={gas_handling} not one of {gas.OPTIONS}")
    e = cost.economics(int(n_doublets), float(t_return_c), peak_heat_MW, peak_cold_MW, depth_m=float(depth_m), esp_depth_m=_esp(esp_depth_m),
                       outage_mode=_mode(outage_mode), gas_handling=gas_handling)
    cap, ann = e["capex_MEUR"], e["annual_cost_MEUR"]
    flat = {**{f"capex_{k}_MEUR": v for k, v in cap.items()},
            **{f"annual_{side}_{k}_MEUR": v for side in ("heating", "cooling") for k, v in ann[side].items()},
            "annual_total_MEUR": ann["total"]}
    keys = ("n_doublets", "heat_served_GWh", "cold_served_GWh", "lcoh_EUR_MWh", "lcoc_EUR_MWh", "electricity_GWh", "gas_GWh", "co2_kt",
            "co2_electricity_kt", "co2_associated_gas_kt", "co2_total_kt", "gas_handling", "associated_gas_q_m3h",
            "associated_gas_electricity_GWh", "associated_gas_heat_GWh", "associated_gas_compression_GWh", "esp_GWh", "outage_mode")
    return {**r2({**{k: e[k] for k in keys}, **flat}), "tag": "[C]", "basis": e["basis"]}


def layout_compare(n_doublets, t_return_c, peak_heat_MW=None, peak_cold_MW=None, depth_m=DEPTH_M, esp_depth_m=None):
    """Price the two ways to reach 100 C for 1-3 doublets at a 30-70 C return, reservoir at depth_m (default 2500 m), demand scaled
    to the given peaks: B = exchanger then a brine-source heat pump (our design), A = exchanger then a gas boiler lifts the
    network water from wellhead T minus 3 K to 100 C (no heat pump); per layout LCoH EUR/MWh, boiler and gas GWh, CO2 kt (boiler gas,
    and co2_total_kt with grid electricity and associated gas),
    electricity GWh, geothermal share, heat-pump and total CAPEX MEUR; chosen = the lower LCoH, delta_lcoh_EUR_MWh = A minus B
    [C]."""
    _need("n_doublets", n_doublets, 1, 3)
    _need("t_return_c", t_return_c, 30, 70)
    _peaks(peak_heat_MW, peak_cold_MW)
    _need("depth_m", depth_m, 1500, 4000)
    out, esp = {}, _esp(esp_depth_m)
    for hp, key in ((True, "B"), (False, "A")):
        e = cost.economics(int(n_doublets), float(t_return_c), peak_heat_MW, peak_cold_MW, depth_m=float(depth_m), heat_pump=hp, esp_depth_m=esp)
        d = year.heating_year(int(n_doublets), float(t_return_c), peak_heat_MW=peak_heat_MW, depth_m=float(depth_m), heat_pump=hp, esp_depth_m=esp)
        out[key] = r2({"layout": e["layout"], "lcoh_EUR_MWh": e["lcoh_EUR_MWh"], "boiler_GWh": gwh(d.boiler),
                       "boiler_share_pct": 100 * gwh(d.boiler) / gwh(d.demand - d.unmet), "gas_GWh": e["gas_GWh"], "co2_kt": e["co2_kt"],
                       "co2_electricity_kt": e["co2_electricity_kt"], "co2_total_kt": e["co2_total_kt"],
                       "electricity_GWh": e["electricity_GWh"], "geothermal_share_pct": 100 * (gwh(d.geo) + gwh(d.hp) - gwh(d.el_hp)) / gwh(d.demand),
                       "capex_heat_pump_MEUR": e["capex_MEUR"]["heat_pump"], "capex_total_MEUR": e["capex_MEUR"]["total"]})
    delta = round(out["A"]["lcoh_EUR_MWh"] - out["B"]["lcoh_EUR_MWh"], 2)
    return {"n_doublets": int(n_doublets), "t_return_c": float(t_return_c), "B": out["B"], "A": out["A"],
            "chosen": out["B"]["layout"] if delta > 0 else out["A"]["layout"], "delta_lcoh_EUR_MWh": delta, "tag": "[C]"}


def storage_point(n_doublets, t_return_c, peak_heat_MW=None, depth_m=DEPTH_M, outage_days=7, esp_depth_m=None):
    """A steel heat-storage tank as the alternative to the 16 MW backup boiler for 1-3 doublets at a 30-70 C return, reservoir at
    depth_m (default 2500 m), heat demand scaled to peak_heat_MW: tank MWh for the peak with every doublet on, tank MWh, number of
    175 MWh / 2.9 MW units and MEUR for one doublet out over outage_days (1-35, default 7 [A]) in winter at 3 000 EUR/MWh [L,
    DEA], the boiler's MEUR, and a verdict sentence; daily data make the peak tank a lower bound [C, L, A]."""
    _need("n_doublets", n_doublets, 1, 3)
    _need("t_return_c", t_return_c, 30, 70)
    _peaks(peak_heat_MW, None)
    _need("depth_m", depth_m, 1500, 4000)
    _need("outage_days", outage_days, 1, 35)
    s = storage.storage_case(int(n_doublets), float(t_return_c), peak_heat_MW, depth_m=float(depth_m), outage_days=int(outage_days),
                             esp_depth_m=_esp(esp_depth_m))
    return r2(s)


def gas_point(q_m3h, depth_m=DEPTH_M, esp_depth_m=None):
    """Gas dissolved in the brine of one doublet at q_m3h (50-300 m3/h), reservoir at depth_m (default 2500 m): GLR 0.8 Nm3/m3 of
    80/20 CH4/CO2 [D] as gas, CH4 and CO2 Nm3/h, CH4 fuel power MW (LHV), CO2 kg/h in the gas, the same per year over 330
    operating days, a Henry's-law bubble point (pure water, not a PVT model; salt raises it) against the ESP intake pressure
    (free_gas_at_intake true means gas breaks out before the pump), and five handling options (vent, flare, gas engine, site boiler,
    reinjection) with CO2 t/yr, energy credit or compression duty; the chosen option (gas engine) in kt and GWh per doublet-year
    against the ESP electricity at the same flow [C, L, A]."""
    _need("q_m3h", q_m3h, Q_MIN_M3H, Q_MAX_M3H)
    _need("depth_m", depth_m, 1500, 4000)
    g = gas.gas_at(float(q_m3h), float(depth_m))
    w = Producer(depth_m=float(depth_m), stages=24, esp_depth_m=_esp(esp_depth_m))
    f = w.freq_for_wellhead(float(q_m3h))
    run = w.run(float(q_m3h), f if f is not None else 60.0)
    p_in = run["p_esp_intake_bar"]
    hours = gas.OPERATING_DAYS * 24
    opts = gas.handling_options(float(q_m3h), float(depth_m), esp_kW=run["esp_electric_kW"])
    ch = next(o for o in opts if o["option"] == gas.GAS_HANDLING)
    return {**r2({**g, "depth_m": depth_m, "gas_Mm3_per_yr": g["gas_Nm3h"] * hours / 1e6, "CH4_GWh_LHV_per_yr": g["CH4_MW_LHV"] * hours / 1000,
                  "CO2_in_gas_t_per_yr": g["CO2_in_gas_kg_h"] * hours / 1000, "esp_depth_m": w.esp_depth_m, "p_esp_intake_bar": p_in,
                  "intake_margin_bar": p_in - g["p_bubble_bar"],
                  "free_gas_at_intake": bool(p_in < g["p_bubble_bar"]), "free_gas_at_intake_upper_bound": bool(p_in < g["p_bubble_upper_bar"]),
                  "gas_handling": gas.GAS_HANDLING, "handling_CO2_kt_per_yr": ch["CO2e_t_per_yr"] / 1000,
                  "handling_electricity_GWh_per_yr": ch["electricity_MWh_per_yr"] / 1000, "handling_heat_GWh_per_yr": ch["heat_MWh_per_yr"] / 1000,
                  "esp_GWh_per_yr": run["esp_electric_kW"] * hours / 1e6}),
            "handling_options": [r2(o) for o in opts],
            "handling_reason": "gas engine: same CO2 as a flare, its electricity covers the ESP load; the organisers allow any option",
            "CH4_mol_per_kg": round(g["CH4_mol_per_kg"], 4), "CO2_mol_per_kg": round(g["CO2_mol_per_kg"], 4),
            "basis": gas.BASIS + f"; handling: GWP100 fossil CH4 {gas.GWP100_CH4_FOSSIL} [L, GHG Protocol AR6 table], CHP electric share 1/3 "
                     f"[D, GEMINI chp.py], CHP total {gas.CHP_TOTAL_EFF} [A], separator {gas.P_SEPARATOR_BAR:g} bar [A], "
                     "permit for reinjection [A]", "tag": "[C, L, A]"} | gemini(PRODUCER_GEMINI)


def lifetime_point(n_doublets, t_return_c, peak_heat_MW=None, depth_m=DEPTH_M, spacing_m=1500, doublet_spacing_m=None, esp_depth_m=None):
    """Lifetime of 1-3 doublets at a 30-70 C return, reservoir at depth_m (default 2500 m), heat demand scaled to peak_heat_MW:
    Gringarten-Sauty thermal breakthrough t_BT in years at the mean running flow of heating_year and at the 300 m3/h cap for
    producer-injector spacing_m (500-3000 m, default 1500 m), the spacing that gives 30 and 50 yr, and the extra injector pressure
    from the neighbouring doublets placed side by side doublet_spacing_m apart (default = spacing_m) against the SodM margin [C,
    L, A]."""
    _need("n_doublets", n_doublets, 1, 3)
    _need("t_return_c", t_return_c, 30, 70)
    _peaks(peak_heat_MW, None)
    _need("depth_m", depth_m, 1500, 4000)
    _need("spacing_m", spacing_m, 500, 3000)
    _need("doublet_spacing_m", doublet_spacing_m, 300, 5000)
    d = _heat(int(n_doublets), float(t_return_c), peak_heat_MW, float(depth_m), esp_depth_m)
    q_mean = float(d.q_m3h[d.doublets_on > 0].mean())
    dp = lifetime.interference_bar(int(n_doublets), Q_MAX_M3H, float(spacing_m), doublet_spacing_m)
    sodm = min(year.injector_rows(float(depth_m)), key=lambda r: r["sodm_margin_bar"])["sodm_margin_bar"]
    return {**r2({"n_doublets": int(n_doublets), "spacing_m": spacing_m,
                  "doublet_spacing_m": spacing_m if doublet_spacing_m is None else doublet_spacing_m,
                  "q_mean_running_m3h": q_mean, "t_bt_mean_flow_yr": lifetime.t_bt_yr(q_mean, float(spacing_m)),
                  "t_bt_300m3h_yr": lifetime.t_bt_yr(Q_MAX_M3H, float(spacing_m)),
                  "spacing_for_30yr_at_300m3h_m": lifetime.spacing_for_yr(30, Q_MAX_M3H),
                  "spacing_for_50yr_at_300m3h_m": lifetime.spacing_for_yr(50, Q_MAX_M3H), "interference_worst_injector_bar": max(dp),
                  "sodm_margin_bar": sodm, "sodm_margin_after_interference_bar": sodm - max(dp)}),
            "interference_per_injector_bar": [round(x, 2) for x in dp], "basis": lifetime.BASIS, "tag": "[C, L, A]"}


def optimise_point(peak_heat_MW=None, peak_cold_MW=None, depth_m=DEPTH_M, priority="lcoh", esp_depth_m=None, max_doublets=3):
    """Search doublet count (1-3), network return (50-70 C) and ESP depth (300-1250 m) for the lowest LCoH and the lowest CO2 at
    once, reservoir at depth_m (default 2500 m), demand scaled to the given peaks: a coarse grid then a pattern search, feasible =
    all 17 checks pass and the doublet rule (no unmet heat, peak covered, boiler at most 5 %); returns the Pareto front (designs no
    other beats on both LCoH and CO2, with the breakthrough time and co2_reinject_kt = the row's CO2 with the associated gas
    reinjected), best_lcoh and best_co2 rows, best_on_priority for priority
    'lcoh' or 'co2', the number of designs evaluated and the seconds taken [C]."""
    _peaks(peak_heat_MW, peak_cold_MW)
    _need("depth_m", depth_m, 1500, 4000)
    if priority not in ("lcoh", "co2"):
        raise ValueError(f"priority must be 'lcoh' or 'co2', got {priority!r}")
    _need("max_doublets", max_doublets, 1, 3)
    r = optimise.optimise(peak_heat_MW, peak_cold_MW, float(depth_m), _esp(esp_depth_m), n_max=int(max_doublets))
    row = lambda p: None if p is None else r2({k: v for k, v in p.items() if k != "fails"})
    return {"priority": priority, "front": [row(p) for p in r["front"]], "best_lcoh": row(r["best_lcoh"]), "best_co2": row(r["best_co2"]),
            "best_on_priority": row(r["best_lcoh"] if priority == "lcoh" else r["best_co2"]), "n_evaluated": r["n_evaluated"],
            "n_feasible": r["n_feasible"], "seconds": r["seconds"], "basis": r["basis"], "tag": "[C]"}


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
        key = str(int(t)) if float(t).is_integer() else str(t)   # "60" for the swept integers, "57.5" for an optimised return
        rows[key] = {"boiler_GWh": h["boiler_GWh"], "served_GWh": round(h["demand_GWh"] - h["unmet_GWh"], 2),
                        "boiler_share_pct": round(100 * h["boiler_GWh"] / max(h["demand_GWh"] - h["unmet_GWh"], 1e-9), 2),
                        "heat_pump_electricity_GWh": h["heat_pump_electricity_GWh"],
                        "esp_GWh": h["esp_electricity_GWh"], "geothermal_share_pct": h["geothermal_share_pct"],
                        "unmet_GWh": h["unmet_GWh"], "peak_margin_pct": h["peak_margin_pct"]}
    free = [t for t in swept if rows[str(t)]["boiler_GWh"] < 0.01]
    best = free[0] if free else min(swept, key=lambda t: rows[str(t)]["boiler_GWh"])
    return {"n_doublets": int(n_doublets), "depth_m": depth_m, "by_return_C": rows, "best_return_c": best, "tag": "[C]",
            "backup_boiler_MW": year.BACKUP_BOILER_MW, "backup_boiler_tag": "[L] security of supply, not energy"}


def gemini_traps():
    """GEMINI findings as short sentences the agent may cite; heat_pump_point runs GEMINI's own heat pump with the root fix [C]."""
    return {"esp_floor": "The ESP curve is valid 158-342 m3/h; GEMINI returns numbers at 50 m3/h without warning, "
                         "so 160 m3/h is the real floor.",
            "return_temperature": "The network return temperature decides the plant: at 55-60 C a brine-source heat pump replaces the boiler.",
            "absorption_brine": "Most summer surplus brine is 46-63 C, too cold for absorption; "
                                "only the slice above 78 C (about 3 GWh) drives chillers.",
            "free_cooling": "Free cooling 77 % rests on a 26 C return, 4 K approach, De Bilt 2024 weather and daily maximum wet bulb "
                            "(92 % with daily mean).",
            "esp_head_law": "GEMINI's ESP reads the head curve at the actual flow, not q*60/f (similarity law); it overstates head "
                            "at reduced speed, 9 % at 57 Hz and 300 m3/h; corrected in ESPAffinity.",
            "injector_sign": "nodal_solver.py:150 passes a positive injection flow, so friction adds pressure going down. The 0.001 "
                             "bar injection wellhead others see at 300 m3/h is this bug: TNO 38.3 bar at 0.045 mm roughness, 0.001 at "
                             "the 10 mm default, our fork 63.3. Fixed on the fork [C, reproduced 5 Nov; reported by PR #58/#59].",
            "heatpump_floor_branch": "heatpump_basic.py:286-305: when the source floor binds, HeatpumpBasic has two roots and Nelder-Mead "
                                     "may pick the unphysical one (COP 1.01, water out 796 C at 720 m3/h); it flips root at 398.66 and "
                                     "534.48 m3/h. Our HeatPumpLift brackets the solve, swept 100-720 m3/h: never above 100 C, not "
                                     "exposed [C, reproduced 5 Nov; reported by PR #58/#59].",
            "exchanger_abs": "heat_exchanger.py:107 takes abs() of the temperature difference, so 2.15 MW flows from a 50 C primary to "
                             "a 56.5 C secondary. Our chain feeds the exchanger at 78 C or more against a 56.5 C return and never "
                             "enters that case [C, reproduced 5 Nov; reported by PR #58].",
            "esp_intake_clamp": "nodal_solver.py:67 and well_flow.py:295 floor the ESP intake at 0 bar without a warning: 168.9 m3/h "
                                "reported with intake 0.00 bar where discharge minus head is -36.2 bar. Our check 14 needs the intake "
                                "above the gas bubble point, so a clamped intake fails, not passes [C, reproduced 5 Nov; reported by PR #58/#59].",
            "roughness_default": "well_flow.py defaults roughness to 0.01, read as metres (10 mm): 61.7 bar vs 12.5 bar of friction at "
                                 "300 m3/h in 7 in tubing over 2 500 m. We set 0.045 mm in geo/well.py and write it into every "
                                 "generated project [C, reproduced 5 Nov; reported by PR #58].",
            "tag": "[C]"}


def _within(days, key):
    """'within X %' for the largest |key_diff_pct| over the days, or 'not compared' when no day has it."""
    diffs = [abs(d[key + "_diff_pct"]) for d in days if key + "_diff_pct" in d]
    return f"within {max(diffs):.1f} %" if diffs else "not compared"


def gemini_replay(n_doublets, t_return_c, peak_heat_MW=None, depth_m=DEPTH_M, esp_depth_m=None):
    """GEMINI's own simulator re-runs our design: the tool writes one doublet of the design as a native GEMINI project file
    (producer well with ESP, separator, filters, our absorption chiller, exchanger, our heat pump, boiler on the separator gas,
    injector, plus our gas bubble-point and thermal-breakthrough models) and runs GEMINI's solver on the coldest, the median and
    the mildest day of 2027 at the day's dispatch per doublet, heat demand scaled to peak_heat_MW if given (else 30 MW). Per day: GEMINI's flow at our ESP frequency, the frequency GEMINI
    needs for our flow, and at that flow GEMINI's pressures, brine and supply temperatures, exchanger, heat-pump, boiler and
    chiller MW, heat-pump COP, bubble point, breakthrough years and interference next to ours (_ours, _gemini, _diff_pct);
    residual columns take out the known 1 000 vs 1 030 kg/m3 well-column offset. Also the project file path, gemini_version
    and a verdict sentence [C]."""
    _need("n_doublets", n_doublets, 1, 3)
    _need("t_return_c", t_return_c, 30, 70)
    _need("depth_m", depth_m, 1500, 4000)
    _peaks(peak_heat_MW, None)
    r = gemini_project.replay(int(n_doublets), float(t_return_c), float(depth_m), _esp(esp_depth_m), peak_heat_MW=peak_heat_MW)
    days = [r2({k: v for k, v in d.items() if v is not None and v == v}) for d in r["days"]]   # v == v drops nan
    solved = [d for d in days if "esp_head_residual_bar" in d]
    if not solved:
        return {"error": f"GEMINI's pump at 60 Hz cannot reach our flow on any of the {len(days)} days; nothing to compare"}
    head = max(abs(d["esp_head_residual_bar"]) for d in solved)
    inj = max(abs(d["p_injection_wellhead_residual_bar"]) for d in solved)
    gaps = [d["freq_hz_ours"] - d["freq_hz_gemini_same_flow"] for d in solved if "freq_hz_gemini_same_flow" in d]
    freq = (f" GEMINI needs up to {max(gaps):.1f} Hz less for the same flow (it reads the 60 Hz pump curve at the actual flow; "
            "we apply the similarity law)." if gaps else "")
    sign = (" GEMINI's injector friction sign (fixed on our branch) explains the rest."
            if inj > 3 and all(d["p_injection_wellhead_residual_bar"] < 0 for d in solved) else "")
    short = (f" GEMINI's pump at 60 Hz cannot reach our flow on {len(days) - len(solved)} of the days."
             if len(solved) < len(days) else "")
    cold = [d for d in solved if d.get("T_supply_C_gemini", 100.0) < 99.0]
    supply = (f" On {len(cold)} day(s) GEMINI's series chain (exchanger, then heat pump) reaches only "
              f"{min(d['T_supply_C_gemini'] for d in cold):.1f} C where our dispatch counts the heat at 100 C (heat pump cut "
              "back or off, or a boiler lift outside this chain); COP and duty differ on those days." if cold else "")
    verdict = (f"GEMINI's solver re-ran {len(solved)} days: ESP head within {head:.1f} bar, injection wellhead within {inj:.1f} bar, "
               f"heat-pump COP {_within(solved, 'cop_heat_pump')}, bubble point {_within(solved, 'p_bubble_bar')}, breakthrough "
               f"{_within(solved, 't_breakthrough_yr')}. "
               "The injection figure is after the water-column offset. Those come from GEMINI's nodal solve, its Lorenz "
               "heat-pump solve and its gas and breakthrough models with our "
               "parameters; flow, exchanger duty, full-draw heat-pump duty, boiler heat and chiller drive are equal by construction "
               "(the project carries our duty, floors, water flow and gas; the chiller has the same formula and wellhead temperature "
               "on both sides)." + freq + sign + short + supply)
    return {"n_doublets": int(n_doublets), "t_return_c": float(t_return_c), "peak_heat_MW": peak_heat_MW, "depth_m": float(depth_m),
            "esp_depth_m": _esp(esp_depth_m), "n_days": len(days), "days": days, "project_path": r["project_path"], "gemini_version": r["gemini_version"],
            "verdict": verdict, "basis": r["basis"], "tag": "[C]"}


FUNCS = {f.__name__: f for f in (site_inputs, demand_summary, doublet_point, heating_year, cooling_year, injector_point, gas_point,
                                 lifetime_point, heat_pump_point, checks, economics, layout_compare, storage_point, return_sweep,
                                 optimise_point, gemini_replay, gemini_traps)}
NUM = lambda desc, lo, hi, kind="number": {"type": kind, "description": f"{desc}, {lo} to {hi}", "minimum": lo, "maximum": hi}
ARGS = {"depth_m": NUM("reservoir depth in m (omit for the brief's 2500 m); give the brief's depth to every tool", 1500, 4000),
        "supply_heat_c": NUM("heating supply temperature in C", 60, 120),
        "supply_cold_c": NUM("cooling supply temperature in C", 6, 25), "q_m3h": NUM("flow per well in m3/h", 50, 300),
        "t_return_c": NUM("network return temperature in C", 30, 70),
        "n_doublets": NUM("number of doublets", 1, 3, "integer"),
        "t_brine_in_c": NUM("brine temperature into the heat pump evaporator in C", 40, 90),
        "t_water_in_c": NUM("district water temperature into the heat pump condenser in C", 40, 99),
        "t_brine_floor_c": NUM("coldest brine allowed out of the evaporator in C, the wellhead T minus 40 K (omit: brine in minus 40 K)", 0, 90),
        "brine_m3h": NUM("brine flow through the evaporator in m3/h", 50, 600),
        "water_m3h": NUM("district water flow through the condenser in m3/h", 50, 600),
        "peak_heat_MW": NUM("peak heating demand of the brief in MW (omit for the 30 MW demand file)", 1, 100),
        "peak_cold_MW": NUM("peak cooling demand of the brief in MW (omit for the 10 MW demand file)", 0, 50),
        "outage_days": NUM("days one doublet is out in winter for the tank sizing (omit for 7)", 1, 35, "integer"),
        "spacing_m": NUM("distance producer to injector of one doublet at reservoir level in m (omit for 1500)", 500, 3000),
        "doublet_spacing_m": NUM("distance between neighbouring doublets in m (omit: equal to spacing_m)", 300, 5000),
        "esp_depth_m": NUM("ESP setting depth in m (omit for 1100 m); give the brief's or the plan's value to every tool", 300, 1250),
        "extra_return_c": NUM("one more return temperature in C to add to the sweep (omit for the six standard ones)", 30, 70),
        "priority": {"type": "string", "enum": ["lcoh", "co2"],
                     "description": "what the brief wants first: lcoh (cheapest heat, the default) or co2 (lowest emissions)"},
        "max_doublets": NUM("most doublets the brief allows (omit for 3)", 1, 3, "integer"),
        "outage_mode": {"type": "string", "enum": list(outage.MODES),
                        "description": "where the 35 planned outage days of each doublet fall: staggered (the default, least-demand "
                                       "windows one doublet at a time) or all_at_once (every doublet out together, backup carries it)"},
        "gas_handling": {"type": "string", "enum": list(gas.OPTIONS),
                         "description": "what happens to the gas dissolved in the brine (omit for engine): vent, flare, engine "
                                        "(gas engine, the default), boiler (site boiler) or reinject (compressed into the injector)"}}
PEAKS = ["peak_heat_MW", "peak_cold_MW"]
OPTIONAL = PEAKS + ["t_brine_floor_c", "depth_m", "outage_days", "spacing_m", "doublet_spacing_m", "esp_depth_m", "extra_return_c",
            "priority", "max_doublets", "outage_mode", "gas_handling"]
D = ["depth_m", "esp_depth_m"]   # every tool that runs the producer takes both
SIG = {"site_inputs": ["depth_m", "supply_heat_c", "supply_cold_c"], "demand_summary": PEAKS,
       "doublet_point": ["q_m3h", "t_return_c"] + D, "heating_year": ["n_doublets", "t_return_c", "peak_heat_MW"] + D + ["outage_mode"],
       "cooling_year": ["t_return_c", "n_doublets"] + PEAKS + D, "injector_point": ["q_m3h", "depth_m"], "gas_point": ["q_m3h"] + D,
       "lifetime_point": ["n_doublets", "t_return_c", "peak_heat_MW"] + D + ["spacing_m", "doublet_spacing_m"],
       "heat_pump_point": ["t_brine_in_c", "t_water_in_c", "brine_m3h", "water_m3h", "t_brine_floor_c"],
       "checks": ["n_doublets", "t_return_c"] + PEAKS + D + ["outage_mode"], "economics": ["n_doublets", "t_return_c"] + PEAKS + D + ["outage_mode", "gas_handling"],
       "layout_compare": ["n_doublets", "t_return_c"] + PEAKS + D,
       "storage_point": ["n_doublets", "t_return_c", "peak_heat_MW"] + D + ["outage_days"],
       "return_sweep": ["n_doublets", "peak_heat_MW"] + D + ["extra_return_c"], "optimise_point": PEAKS + D + ["priority", "max_doublets"],
       "gemini_replay": ["n_doublets", "t_return_c", "peak_heat_MW"] + D,
       "gemini_traps": []}
TOOLS = [{"type": "function", "function": {"name": n, "description": " ".join(FUNCS[n].__doc__.split()),
          "parameters": {"type": "object", "properties": {a: ARGS[a] for a in args},
                         "required": [a for a in args if a not in OPTIONAL]}}} for n, args in SIG.items()]


STRINGS = ("priority", "outage_mode", "gas_handling")   # arguments passed through as text


def call(name, args):
    if name not in FUNCS:
        raise ValueError(f"unknown tool {name}; valid: {sorted(FUNCS)}")
    conv = lambda k, v: v if v is None or k in STRINGS else int(v) if k in ("n_doublets", "outage_days", "max_doublets") else float(v)
    return FUNCS[name](**{k: conv(k, v) for k, v in (args or {}).items()})


if __name__ == "__main__":
    two = {"n_doublets": 2, "t_return_c": 60}
    for name, args in (("site_inputs", {"depth_m": 2500, "supply_heat_c": 100, "supply_cold_c": 20}), ("demand_summary", {}),
                       ("doublet_point", {"q_m3h": 300, "t_return_c": 60}), ("heating_year", two), ("cooling_year", {"t_return_c": 60}),
                       ("injector_point", {"q_m3h": 300}), ("gas_point", {"q_m3h": 300}), ("lifetime_point", two),
                       ("heat_pump_point", {"t_brine_in_c": 63, "t_water_in_c": 82.58, "brine_m3h": 300, "water_m3h": 388,
                                            "t_brine_floor_c": 45.58}),
                       ("checks", two), ("economics", two), ("layout_compare", two), ("storage_point", two),
                       ("return_sweep", {"n_doublets": 2}), ("gemini_traps", {})):
        print(f"\n{name}({args})\n" + json.dumps(call(name, args), indent=1))
    print(f"\n{len(TOOLS)} tools, about {len(json.dumps(TOOLS)) // 4} tokens of schema")
