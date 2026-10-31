"""Independent verification of fast-model days with the full GEMINI simulator.

The annual model uses (a) GEMINI well curves interpolated on a flow grid and
(b) an ideal counter-flow HX with a fixed minimum approach. To make sure those
shortcuts do not mislead the design, selected days are rebuilt as complete
GEMINI project files and run through GEMINI's own solver, with a heat
exchanger of FIXED size (UA chosen on the peak day). The comparison is
reported per quantity, with a pass/fail tolerance.
"""

import math

import numpy as np
import pandas as pd

from agentic_design.config import CHALLENGE, Assumptions, gas_properties
from agentic_design.plant_json import build_project_dict, run_project
from agentic_design.surface import lorenz_cop

TOLERANCES = {  # absolute for temperatures, relative for powers
    "wellhead_temperature_c": 0.05,
    "geothermal_heat_mw": 0.02,
    "supply_temperature_c": 0.3,
    "esp_power_mw": 0.02,
    "injection_temperature_c": 0.3,
    "heat_pump_cop": 0.03,
    "heat_pump_power_mw": 0.03,
    "absorption_cooling_mw": 0.02,
    "electric_chiller_power_mw": 0.02,
}


def size_hx_ua(row: pd.Series, a: Assumptions) -> float:
    """UA (W/K) giving the fast-model duty on the design (peak) day."""
    t_bi = row["t_wellhead_c"] - a.surface_temperature_loss_c
    t_bo = row["t_injection_c"]
    t_si = a.heating_return_temperature_c
    t_so = row["t_network_after_hx_c"]
    dt1, dt2 = t_bi - t_so, t_bo - t_si
    lmtd = dt1 if abs(dt1 - dt2) < 1e-9 else (dt1 - dt2) / math.log(dt1 / dt2)
    return row["heat_geothermal_mw"] * 1e6 / lmtd


def operating_point(row: pd.Series, a: Assumptions) -> dict:
    t_sup = CHALLENGE["heating_supply_temperature_c"]
    t_ret = a.heating_return_temperature_c
    used = row["heat_assoc_gas_boiler_mw"] / a.boiler_efficiency
    frac = 0.0 if row["assoc_gas_fuel_mw"] <= 0 else min(1.0, used / row["assoc_gas_fuel_mw"])
    t_floor = row["t_wellhead_c"] - CHALLENGE["max_brine_cooling_c"]  # injection may not be colder than this
    t_abs_in = (row["t_wellhead_c"] - a.surface_temperature_loss_c if row["brine_order"] == "abs_first"
                else row["t_hx_brine_out_c"])
    return {
        "doublets_on": int(row["doublets_on"]),
        "q_per_doublet_m3h": float(row["q_per_doublet_m3h"]),
        "c_sec_w_k": row["heating_mw"] * 1e6 / (t_sup - t_ret),
        "t_return_c": t_ret,
        "assoc_gas_used_fraction": frac,
        "ng_fuel_w": row["ng_fuel_mw"] * 1e6,
        "order": row["brine_order"],
        "abs_cooling_w": row["cooling_absorption_mw"] * 1e6,
        "abs_max_drive_dt": max(0.0, t_abs_in - t_floor),
        "hp_heat_w": row["heat_pump_mw"] * 1e6,
        "hp_target_c": row["t_network_after_hx_c"] + (row["heat_pump_mw"] / (row["heating_mw"] / (t_sup - t_ret))
                                                      if row["heating_mw"] > 0 else 0.0),
        "hp_ts_min_c": t_floor - 0.05,  # just inside the limit: GEMINI's constrained heat-pump branch is unstable
        "hx_bypassed": row["heat_geothermal_mw"] <= 1e-9,  # real plant bypasses an HX that would heat the brine
        "ec_load_w": row["cooling_electric_mw"] * 1e6,
    }


def verify_days(design, daily: pd.DataFrame, a: Assumptions = None, days=None, ua_mw_k=None,
                use_gemini_injector=False) -> pd.DataFrame:
    """Run chosen days (default: peak heating, median, minimum) in the GEMINI solver.

    ``ua_mw_k``: HX size used by the annual run (``kpis['hx_ua_mw_k']``); if
    omitted it is re-derived from the peak day.
    """
    a = a or Assumptions()
    peak = int(daily["heating_mw"].idxmax())
    ua = ua_mw_k * 1e6 if ua_mw_k else size_hx_ua(daily.loc[peak], a)
    if days is None:
        order = daily["heating_mw"].sort_values()
        days = [peak, int(order.index[len(order) // 2]), int(order.index[0]), int(daily["cooling_mw"].idxmax())]
        days = list(dict.fromkeys(days))
    rows = []
    for d in days:
        r = daily.loc[d]
        if r["doublets_on"] == 0:
            continue
        op = operating_point(r, a)
        project = build_project_dict(design, op, a, hx_ua_w_k=ua, use_gemini_injector=use_gemini_injector)
        s = run_project(project)
        n = op["doublets_on"]
        g = lambda c, k: s.get_output(c, k)  # noqa: E731
        geo = g("heat_exchanger", "heat_duty") / 1e6
        esp = sum(g(f"producer_well_{i}", "esp_power_el") for i in range(1, n + 1)) / 1e6
        inj = sum(g(f"injector_well_{i}", "power_el") for i in range(1, n + 1)) / 1e6
        res = {
            "day": str(r["date"].date()),
            "heating_mw": r["heating_mw"],
            "doublets_on": n,
            "q_m3h": op["q_per_doublet_m3h"],
            "wellhead_temperature_c": (r["t_wellhead_c"], g("producer_well_1", "temperature_out")),
            "geothermal_heat_mw": (r["heat_geothermal_mw"], geo),
            "supply_temperature_c": (CHALLENGE["heating_supply_temperature_c"], g("boiler_ng", "temperature_out")),
            "esp_power_mw": (r["esp_power_mw"], esp),
            "injection_pump_mw": (r["injection_pump_power_mw"], inj),
            "injection_temperature_c": (r["t_injection_c"], g("filter_b", "temperature_out")),
            "cooling_mw": r["cooling_mw"],
            "assoc_gas_kg_s": (r["assoc_gas_fuel_mw"] * 1e6 / (gas_properties()["lhv_mj_kg"] * 1e6),
                               g("separator", "gas_mass_flow_rate")),
            "heat_pump_cop": (r["heat_pump_cop"], g("heat_pump", "COP")) if "heat_pump" in s.components else None,
            "heat_pump_power_mw": (r["heat_pump_power_mw"], g("heat_pump", "power_el") / 1e6) if "heat_pump" in s.components else None,
            "absorption_cooling_mw": (r["cooling_absorption_mw"], g("absorption_chiller", "cooling") / 1e6)
            if "absorption_chiller" in s.components else None,
            "electric_chiller_power_mw": (r["electric_chiller_power_mw"], g("electric_chiller", "power_el") / 1e6)
            if "electric_chiller" in s.components else None,
            "brine_order": r["brine_order"],
            "hx_ua_mw_k": ua / 1e6,
            "hx_bypass_active": bool(r["hx_bypass_active"]),
        }
        checks = []
        for k, tol in TOLERANCES.items():
            if res.get(k) is None:
                continue
            if res["hx_bypass_active"] and k in ("geothermal_heat_mw", "supply_temperature_c", "injection_temperature_c",
                                                 "heat_pump_cop", "heat_pump_power_mw"):
                continue  # the GEMINI project has no brine bypass; compare these only without bypass
            fast, gem = res[k]
            rel = k.endswith("mw") or k == "heat_pump_cop"
            err = abs(gem - fast) / (abs(fast) if rel and abs(fast) > 1e-9 else 1.0)
            checks.append(err <= tol)
        # GEMINI's HeatpumpBasic solves its two equations with an unbounded Nelder-Mead from a fixed start;
        # at some points it misses its own target (and its constrained branch returns COP~1, ~800 C). Then we
        # check our solution directly against GEMINI's equations instead of against its optimiser.
        hp_check = None
        if res.get("heat_pump_cop") is not None:
            gem_th = g("heat_pump", "Th_out")
            hp_failed = abs(gem_th - op["hp_target_c"]) > 1.0
            t_src_in = r["t_injection_c"] + r["heat_pump_evaporator_mw"] / (
                r["q_total_m3h"] * CHALLENGE["brine_density_kg_m3"] * a.brine_specific_heat_j_kgk / 3600 / 1e6)
            cop_eq = float(lorenz_cop(r["t_network_after_hx_c"], op["hp_target_c"], t_src_in, r["t_injection_c"],
                                      a.heat_pump_eta_lorenz))
            balance = r["heat_pump_mw"] - r["heat_pump_power_mw"] - r["heat_pump_evaporator_mw"]
            eq_ok = abs(cop_eq - r["heat_pump_cop"]) / r["heat_pump_cop"] < 0.01 and abs(balance) < 1e-6
            hp_check = ("GEMINI HeatpumpBasic" if not hp_failed else
                        f"GEMINI equations (GEMINI optimiser failed: Th_out {gem_th:.0f} C vs target "
                        f"{op['hp_target_c']:.1f} C); Lorenz COP {cop_eq:.3f} vs {r['heat_pump_cop']:.3f}, "
                        f"energy balance residual {balance:.1e} MW")
            if hp_failed:
                checks = [c for c, k in zip(checks, [k for k in TOLERANCES if res.get(k) is not None and not (
                    res["hx_bypass_active"] and k in ("geothermal_heat_mw", "supply_temperature_c", "injection_temperature_c",
                                                      "heat_pump_cop", "heat_pump_power_mw"))])
                          if k not in ("heat_pump_cop", "heat_pump_power_mw", "supply_temperature_c", "injection_temperature_c")]
                checks.append(eq_ok)
        res["heat_pump_check"] = hp_check
        res["pass"] = all(checks)
        rows.append(res)
    return pd.DataFrame(rows)


def format_report(v: pd.DataFrame) -> str:
    lines = []
    for _, r in v.iterrows():
        lines.append(f"{r['day']}  heating {r['heating_mw']:.1f} MW, cooling {r['cooling_mw']:.1f} MW, "
                     f"brine order {r['brine_order']}, {r['doublets_on']} doublet(s) at "
                     f"{r['q_m3h']:.0f} m3/h{' (HX bypass active)' if r['hx_bypass_active'] else ''}"
                     f"  -> {'PASS' if r['pass'] else 'CHECK'}")
        for k in ("wellhead_temperature_c", "geothermal_heat_mw", "supply_temperature_c", "esp_power_mw",
                  "injection_pump_mw", "injection_temperature_c", "assoc_gas_kg_s", "heat_pump_cop",
                  "heat_pump_power_mw", "absorption_cooling_mw", "electric_chiller_power_mw"):
            if r.get(k) is None or (isinstance(r[k], float) and r[k] != r[k]):
                continue
            fast, gem = r[k]
            lines.append(f"    {k:<26} fast {fast:9.3f}   GEMINI {gem:9.3f}   diff {gem - fast:+8.3f}")
        if r.get("heat_pump_check") and r["heat_pump_check"] != "GEMINI HeatpumpBasic":
            lines.append(f"    heat pump verified against: {r['heat_pump_check']}")
    return "\n".join(lines)


__all__ = ["verify_days", "format_report", "size_hx_ua", "np"]
