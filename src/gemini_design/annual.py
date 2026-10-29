"""Year-round daily dispatch of a design and constraint/KPI reporting.

Each of the 365 days is a steady state (daily-average demand, energy =
power x 24 h). Every doublet is available on at most ``operating_days``
(330) days; its outage window is scheduled in the period where the
geothermal plant is needed least. On each day the dispatcher tries every
feasible number of active doublets and per-doublet flow rate in
[50, 300] m3/h, runs the GEMINI flowsheet, and keeps the cheapest option
that meets demand without breaking a hard constraint.
"""

import warnings

import numpy as np
import pandas as pd

from gemini_design.challenge import ASSUMPTIONS, CHALLENGE
from gemini_design.doublet import DoubletHydraulics
from gemini_design.economics import levelised_cost
from gemini_design.plant import Plant

UNMET_PENALTY_EUR_PER_MWH = 10000.0
HOURS_PER_DAY = 24.0


def schedule_outages(demand, design, challenge=CHALLENGE, assumptions=ASSUMPTIONS):
    """Return a (365, n_doublets) bool array of doublet availability.

    Each doublet gets one contiguous outage of ``365 - operating_days``
    days. Windows are placed greedily, without overlap, where the load
    that needs geothermal heat (heating, plus absorption-chiller drive
    heat when absorption cooling is used) is lowest.
    """
    n_days = len(demand)
    outage = max(0, n_days - int(challenge["operating_days"]))
    load = demand["heating_mw"].to_numpy(dtype=float)
    if design.cooling == "absorption":
        load = load + demand["cooling_mw"].to_numpy(dtype=float) / assumptions["absorption_cop_max"]
    available = np.ones((n_days, design.n_doublets), dtype=bool)
    if outage == 0:
        return available
    blocked = np.zeros(n_days, dtype=bool)
    window_load = np.convolve(load, np.ones(outage), mode="valid")
    for i in range(design.n_doublets):
        order = np.argsort(window_load)
        for start in order:
            if not blocked[start : start + outage].any():
                available[start : start + outage, i] = False
                blocked[start : start + outage] = True
                break
        else:  # no free window left: overlap with the best one
            start = int(order[0])
            available[start : start + outage, i] = False
    return available


def _score(result):
    unmet_mwh = (result["unmet_heat_w"] + result["unmet_cooling_w"]) / 1e6 * HOURS_PER_DAY
    cost_eur = result["cost_eur_s"] * 86400.0
    return cost_eur + UNMET_PENALTY_EUR_PER_MWH * unmet_mwh


def dispatch_day(plant, heating_w, cooling_w, n_available, challenge=CHALLENGE):
    """Return the best feasible operating point for one day."""
    q_min, q_max = challenge["flow_min_m3h"], challenge["flow_max_m3h"]
    best = plant.evaluate(heating_w, cooling_w, 0, 0.0)
    best_score = _score(best) if not best["violations"] else float("inf")
    for n in range(1, n_available + 1):
        grid = list(np.linspace(q_min, q_max, 6))
        tried = {}
        for q in grid:
            tried[q] = plant.evaluate(heating_w, cooling_w, n, q)
        for step in (25.0, 12.5, 6.25):
            ok = {q: r for q, r in tried.items() if not r["violations"]}
            if not ok:
                break
            q0 = min(ok, key=lambda q: _score(ok[q]))
            for q in (q0 - step, q0 + step):
                if q_min <= q <= q_max and q not in tried:
                    tried[q] = plant.evaluate(heating_w, cooling_w, n, q)
        for r in tried.values():
            if r["violations"]:
                continue
            s = _score(r)
            if s < best_score:
                best, best_score = r, s
    return best


def run_year(design, demand, challenge=CHALLENGE, assumptions=ASSUMPTIONS):
    """Simulate a design over the 365 demand days.

    Returns
    -------
    (pandas.DataFrame, dict)
        One row per day, and a summary dict of KPIs, hard-constraint
        checks and economics.
    """
    hydraulics = DoubletHydraulics(design.depth_m, challenge, assumptions)
    plant = Plant(design, hydraulics, challenge, assumptions)
    availability = schedule_outages(demand, design, challenge, assumptions)

    rows = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        for i, day in demand.iterrows():
            n_available = int(availability[i].sum())
            r = dispatch_day(
                plant, day["heating_mw"] * 1e6, day["cooling_mw"] * 1e6, n_available, challenge
            )
            r = dict(r)
            r["date"] = day["date"]
            r["n_available"] = n_available
            r["violations"] = ";".join(r["violations"])
            rows.append(r)
    daily = pd.DataFrame(rows)
    return daily, summarise(design, daily, availability, hydraulics, challenge, assumptions)


def summarise(
    design, daily, availability, hydraulics, challenge=CHALLENGE, assumptions=ASSUMPTIONS
):
    """Return annual KPIs, hard-constraint checks and economics from daily results."""

    def mwh(col):
        return float(daily[col].sum()) / 1e6 * HOURS_PER_DAY

    heat_demand, cool_demand = mwh("heating_demand_w"), mwh("cooling_demand_w")
    heat_delivered, cool_delivered = mwh("heat_delivered_w"), mwh("cooling_delivered_w")
    co2_t = float(daily["co2_kg_s"].sum()) * 86400.0 / 1000.0
    energy_cost = float(daily["cost_eur_s"].sum()) * 86400.0
    active = daily[daily["n_active"] > 0]

    doublet_days = availability.sum(axis=0).tolist()
    checks = {
        "heating_demand_met": mwh("unmet_heat_w") < 1e-3,
        "cooling_demand_met": mwh("unmet_cooling_w") < 1e-3,
        "flow_within_50_300_m3h": bool(
            active.empty
            or (
                (active["flow_per_doublet_m3h"] >= challenge["flow_min_m3h"] - 1e-9).all()
                and (active["flow_per_doublet_m3h"] <= challenge["flow_max_m3h"] + 1e-9).all()
            )
        ),
        "brine_cooling_within_40K": bool(
            active.empty
            or (active["brine_cooling_k"] <= challenge["brine_cooling_max_k"] + 1e-6).all()
        ),
        "production_equals_injection": True,  # by construction: one flow per doublet
        "doublet_days_within_330": all(d <= challenge["operating_days"] for d in doublet_days),
        "doublets_within_1_3": challenge["doublets_min"]
        <= design.n_doublets
        <= challenge["doublets_max"],
        "no_daily_violations": bool((daily["violations"] == "").all()),
    }
    economics = levelised_cost(design, energy_cost, heat_delivered + cool_delivered, assumptions)
    summary = {
        "design": design.as_dict(),
        "reservoir": {
            "depth_m": design.depth_m,
            "temperature_c": hydraulics.reservoir_temperature_c,
            "pressure_bar": hydraulics.reservoir_pressure_bar,
            "productivity_index_m3h_per_bar": hydraulics.pi_m3h_per_bar,
        },
        "energy_mwh": {
            "heating_demand": heat_demand,
            "heating_delivered": heat_delivered,
            "unmet_heating": mwh("unmet_heat_w"),
            "cooling_demand": cool_demand,
            "cooling_delivered": cool_delivered,
            "unmet_cooling": mwh("unmet_cooling_w"),
            "geothermal_heat": mwh("geothermal_heat_w"),
            "heat_pump_heat": mwh("heat_pump_heat_w"),
            "boiler_heat": mwh("boiler_heat_w"),
            "associated_gas_heat": mwh("associated_gas_heat_w"),
            "purchased_gas_fuel": mwh("purchased_gas_w"),
            "absorption_drive_heat": mwh("absorption_heat_w"),
            "electricity": mwh("electricity_w"),
        },
        "kpi": {
            "geothermal_share_of_heat": mwh("geothermal_heat_w")
            / max(heat_delivered + mwh("absorption_heat_w"), 1e-9),
            "gas_boiler_share_of_heat": mwh("boiler_heat_w")
            / max(heat_delivered + mwh("absorption_heat_w"), 1e-9),
            "associated_gas_unused_mwh": mwh("associated_gas_available_w")
            - mwh("associated_gas_heat_w"),
            "co2_t_per_year": co2_t,
            "co2_kg_per_mwh_delivered": co2_t * 1000.0 / max(heat_delivered + cool_delivered, 1e-9),
            "max_unmet_heat_mw": float(daily["unmet_heat_w"].max()) / 1e6,
            "max_unmet_cooling_mw": float(daily["unmet_cooling_w"].max()) / 1e6,
            "max_flow_per_doublet_m3h": (
                float(active["flow_per_doublet_m3h"].max()) if not active.empty else 0.0
            ),
            "max_brine_cooling_k": (
                float(active["brine_cooling_k"].max()) if not active.empty else 0.0
            ),
            "doublet_operating_days": doublet_days,
            "doublet_active_days": int((daily["n_active"] > 0).sum()),
            "max_esp_dp_bar": float(active["esp_dp_bar"].max()) if not active.empty else 0.0,
            "esp_setting_depth_m": float(active["esp_depth_m"].max()) if not active.empty else 0.0,
            "max_injector_wellhead_pressure_bar": (
                float(active["injector_wellhead_pressure_bar"].max()) if not active.empty else 0.0
            ),
        },
        "checks": checks,
        "all_hard_constraints_met": all(checks.values()),
        "economics": economics,
    }
    return summary
