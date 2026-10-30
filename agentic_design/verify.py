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

TOLERANCES = {
    "wellhead_temperature_c": 0.05,
    "geothermal_heat_mw": 0.05,  # relative
    "supply_temperature_c": 1.0,
    "esp_power_mw": 0.02,  # relative
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
    return {
        "doublets_on": int(row["doublets_on"]),
        "q_per_doublet_m3h": float(row["q_per_doublet_m3h"]),
        "c_sec_w_k": row["heating_mw"] * 1e6 / (t_sup - t_ret),
        "t_return_c": t_ret,
        "assoc_gas_used_fraction": frac,
        "ng_fuel_w": row["ng_fuel_mw"] * 1e6,
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
        days = [peak, int(order.index[len(order) // 2]), int(order.index[0])]
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
            "assoc_gas_kg_s": (r["assoc_gas_fuel_mw"] * 1e6 / (gas_properties()["lhv_mj_kg"] * 1e6),
                               g("separator", "gas_mass_flow_rate")),
            "hx_ua_mw_k": ua / 1e6,
            "hx_bypass_active": bool(r["hx_bypass_active"]),
        }
        checks = []
        for k, tol in TOLERANCES.items():
            if res["hx_bypass_active"] and k in ("geothermal_heat_mw", "supply_temperature_c"):
                continue  # the GEMINI project has no brine bypass; compare these only without bypass
            fast, gem = res[k]
            err = abs(gem - fast) / (abs(fast) if k.endswith("mw") and abs(fast) > 1e-9 else 1.0)
            checks.append(err <= tol)
        res["pass"] = all(checks)
        rows.append(res)
    return pd.DataFrame(rows)


def format_report(v: pd.DataFrame) -> str:
    lines = []
    for _, r in v.iterrows():
        lines.append(f"{r['day']}  heating {r['heating_mw']:.1f} MW, {r['doublets_on']} doublet(s) at "
                     f"{r['q_m3h']:.0f} m3/h{' (HX bypass active)' if r['hx_bypass_active'] else ''}"
                     f"  -> {'PASS' if r['pass'] else 'CHECK'}")
        for k in ("wellhead_temperature_c", "geothermal_heat_mw", "supply_temperature_c", "esp_power_mw",
                  "injection_pump_mw", "injection_temperature_c", "assoc_gas_kg_s"):
            fast, gem = r[k]
            lines.append(f"    {k:<26} fast {fast:9.3f}   GEMINI {gem:9.3f}   diff {gem - fast:+8.3f}")
    return "\n".join(lines)


__all__ = ["verify_days", "format_report", "size_hx_ua", "np"]
