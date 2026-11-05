"""Year-round daily dispatch of a design and constraint/KPI reporting.

Each of the 365 days is a steady state (daily-average demand, energy =
power x 24 h). The geothermal source is available on at most
``operating_days`` (330) days; the organisers confirmed (1 Nov 2026) that
the other 35 days are a planned or unplanned shutdown of the geothermal
source only, and the full system (boiler, chillers, ATES, storage) must
still meet demand on all 365 days. The schedule is a design choice (their
second answer): by default each doublet takes its 35-day stop at a different
time, in the windows where the plant is needed least; see
:func:`schedule_outages` for the whole-source and fixed-date options.
On each day the dispatcher tries every feasible number of active doublets
and per-doublet flow rate in [50, 300] m3/h (narrowed to a sized ESP's range,
:mod:`gemini_design.esp`), runs the GEMINI flowsheet, and keeps the cheapest
option that meets demand without breaking a hard constraint.

With ``operations`` (:class:`gemini_design.operations.OperatingRules`) the
days are linked: the number of running doublets is chosen for the whole
year at once, with a cost per start and minimum run and stop times, and
each producer's wellbore heat loss follows its time since start.
"""

import warnings

import numpy as np
import pandas as pd

from gemini_design import ates as cold_storage
from gemini_design import esp, network, pit_storage, prices
from gemini_design import storage as heat_storage
from gemini_design.challenge import ASSUMPTIONS, CHALLENGE
from gemini_design.doublet import esp_pumps, flow_limits_m3h, hydraulics_for
from gemini_design.economics import levelised_cost
from gemini_design.operations import WellboreModel, WellboreThermalState, commit
from gemini_design.plant import Plant

UNMET_PENALTY_EUR_PER_MWH = 1.0e6  # demand comes first; cost only breaks ties
HOURS_PER_DAY = 24.0


def schedule_outages(demand, design, challenge=CHALLENGE, assumptions=ASSUMPTIONS):
    """Return a (365, n_doublets) bool array of doublet availability.

    The geothermal source is down for ``365 - operating_days`` (35)
    contiguous days. Two assumptions control where:

    ``geothermal_outage_common`` (default 0)
        0: each doublet gets its own 35-day stop, placed greedily without
        overlap, so with two or more doublets some geothermal heat is
        available every day (allowed by the organisers, 1 Nov 2026).
        1: the whole geothermal source (all doublets) stops together.
    ``geothermal_outage_start_day`` (default -1)
        -1: the window starts where the load that needs geothermal heat
        (heating, plus absorption-chiller drive heat when absorption
        cooling is used) is lowest, i.e. planned maintenance.
        0-330: the (first) window starts on that day of the year (0 = 1
        January), to test an unplanned outage, e.g. at the winter peak.

    A design with ``outage_start_days`` (one entry per doublet) overrides
    both: each doublet stops on its own start day (0-330), and doublets
    given -1 are placed greedily in the lowest-load free windows after the
    fixed ones. Stops may overlap if the design says so.
    """
    n_days = len(demand)
    outage = max(0, n_days - int(challenge["operating_days"]))
    available = np.ones((n_days, design.n_doublets), dtype=bool)
    if outage == 0:
        return available
    starts = tuple(getattr(design, "outage_start_days", ()) or ())
    if starts and any(x > n_days - outage for x in starts):
        raise ValueError(f"outage start days must be -1 or 0-{n_days - outage}")
    common = bool(round(float(assumptions.get("geothermal_outage_common", 0.0))))
    fixed_start = int(round(float(assumptions.get("geothermal_outage_start_day", -1.0))))
    if fixed_start > n_days - outage:
        raise ValueError(
            f"geothermal_outage_start_day must be -1 or 0-{n_days - outage}, got {fixed_start}"
        )
    load = demand["heating_mw"].to_numpy(dtype=float)
    if design.cooling == "absorption":
        load = load + demand["cooling_mw"].to_numpy(dtype=float) / assumptions["absorption_cop_max"]
    window_load = np.convolve(load, np.ones(outage), mode="valid")
    order = np.argsort(window_load, kind="stable")
    if fixed_start >= 0:
        order = np.concatenate([[fixed_start], order[order != fixed_start]])
    if starts:
        blocked = np.zeros(n_days, dtype=bool)
        for i, start in enumerate(starts):
            if start >= 0:
                available[start : start + outage, i] = False
                blocked[start : start + outage] = True
        for i, start in enumerate(starts):
            if start < 0:
                free = [s for s in order if not blocked[s : s + outage].any()]
                start = int(free[0]) if free else int(order[0])
                available[start : start + outage, i] = False
                blocked[start : start + outage] = True
        return available
    if common:
        start = int(order[0])
        available[start : start + outage, :] = False
        return available
    blocked = np.zeros(n_days, dtype=bool)
    for i in range(design.n_doublets):
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


def dispatch_day(
    plant,
    heating_w,
    cooling_w,
    n_available,
    challenge=CHALLENGE,
    ambient_c=None,
    heat_loss_multiplier=1.0,
    **day_inputs,
):
    """Return the best feasible operating point for one day.

    ``day_inputs`` are passed to :meth:`Plant.evaluate` (``wet_bulb_c``,
    ``ates_cooling_w``, ``ates_power_w``).
    """
    options = dispatch_options(
        plant,
        heating_w,
        cooling_w,
        n_available,
        challenge,
        ambient_c,
        heat_loss_multiplier,
        **day_inputs,
    )
    best, best_score = options[0]
    for r, s in options[1:]:
        if s < best_score:
            best, best_score = r, s
    return best


def dispatch_options(
    plant,
    heating_w,
    cooling_w,
    n_available,
    challenge=CHALLENGE,
    ambient_c=None,
    heat_loss_multiplier=1.0,
    counts=None,
    **day_inputs,
):
    """Return ``[(result, score), ...]`` for 0..``n_available`` running doublets.

    Each entry is the cheapest feasible flow for that number of doublets;
    its score is ``inf`` when no flow is feasible. ``counts`` limits the
    search to those numbers of doublets (the others get ``(None, inf)``).
    ``day_inputs`` are passed to :meth:`Plant.evaluate`, as in
    :func:`dispatch_day`.
    """
    q_min, q_max = flow_limits_m3h(plant.hyd, challenge)
    kw = {k: v for k, v in day_inputs.items() if v is not None}
    if ambient_c is not None:
        kw["ambient_c"] = ambient_c
    if heat_loss_multiplier != 1.0:
        kw["heat_loss_multiplier"] = heat_loss_multiplier
    options = [(None, float("inf"))] * (n_available + 1)
    if counts is None or 0 in counts:
        r0 = plant.evaluate(heating_w, cooling_w, 0, 0.0, **kw)
        options[0] = (r0, _score(r0) if not r0["violations"] else float("inf"))
    for n in range(1, n_available + 1):
        if counts is not None and n not in counts:
            continue
        best, best_score = None, float("inf")
        grid = list(np.linspace(q_min, q_max, 6))
        tried = {}
        for q in grid:
            tried[q] = plant.evaluate(heating_w, cooling_w, n, q, **kw)
        for step in (25.0, 12.5, 6.25):
            ok = {q: r for q, r in tried.items() if not r["violations"]}
            if not ok:
                break
            q0 = min(ok, key=lambda q: _score(ok[q]))
            for q in (q0 - step, q0 + step):
                if q_min <= q <= q_max and q not in tried:
                    tried[q] = plant.evaluate(heating_w, cooling_w, n, q, **kw)
        for r in tried.values():
            if r["violations"]:
                continue
            s = _score(r)
            if s < best_score:
                best, best_score = r, s
        if best is None:  # keep an infeasible point so a forced day still has a result
            best = min(tried.values(), key=_score)
        options[n] = (best, best_score)
    return options


def run_year(design, demand, challenge=CHALLENGE, assumptions=ASSUMPTIONS, operations=None):
    """Simulate a design over the 365 demand days.

    ``operations`` (:class:`gemini_design.operations.OperatingRules`, optional)
    links the days: doublet starts cost money and must respect minimum run
    and stop times, and the wellbore heat loss depends on time since start.
    Without it every day is dispatched on its own (the original model).

    A design with heat storage (``storage_mwh > 0``) needs a registered
    ``thermal_storage`` model (see :mod:`gemini_design.storage`); the plant is
    then dispatched on demand + charge - discharge, and the daily table
    keeps the district demand in ``heating_demand_w``.

    Returns
    -------
    (pandas.DataFrame, dict)
        One row per day, and a summary dict of KPIs, hard-constraint
        checks and economics.
    """
    assumptions = network.design_assumptions(design, assumptions)
    network.check_returns(challenge, assumptions)
    hydraulics = hydraulics_for(design, challenge, assumptions)
    plant = Plant(design, hydraulics, challenge, assumptions)
    availability = schedule_outages(demand, design, challenge, assumptions)
    plant.availability = availability  # which doublets may run each day (mixed depths)
    day_prices = prices.daily_prices(demand, assumptions)

    store = None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        if getattr(design, "storage_mwh", 0.0) > 0:
            model = heat_storage.build_model(design, assumptions)
            problems = heat_storage.check_model(model)
            if problems:
                raise heat_storage.MissingModelError(
                    "the registered thermal_storage model fails the interface check: "
                    + "; ".join(problems)
                )
            store = heat_storage.plan(design, plant, demand, availability, model, challenge)
        elif getattr(design, "pit_store_m3", 0.0) > 0:
            store = pit_storage.plan(design, plant, demand, availability, challenge, assumptions)
        cold = None
        if getattr(design, "ates_doublets", 0) > 0:
            cold = cold_storage.plan(design, plant, demand, challenge, assumptions)
        loads, day_inputs = [], []
        for i, day in demand.iterrows():
            heating_w = day["heating_mw"] * 1e6
            if store is not None:
                # a pit store covers its discharge stream from the return to 100 degC: its own
                # heat up to the top temperature plus the boiler top-up booked after dispatch
                out_mw = store["discharge_mw"][i] + (
                    store["topup_mw"][i] if "topup_mw" in store else 0.0
                )
                heating_w += (store["charge_mw"][i] - out_mw) * 1e6
            loads.append(
                (
                    heating_w,
                    day["cooling_mw"] * 1e6,
                    int(availability[i].sum()),
                    day["ambient_c"] if "ambient_c" in day else None,
                )
            )
            inputs = {
                "day": i,
                "electricity_price": None if day_prices is None else float(day_prices[0][i]),
                "export_price": None if day_prices is None else float(day_prices[1][i]),
                "wet_bulb_c": day["wet_bulb_c"] if "wet_bulb_c" in day else None,
                "ambient_mean_c": day["ambient_mean_c"] if "ambient_mean_c" in day else None,
            }
            if cold is not None:
                inputs["ates_cooling_w"] = cold["cooling_w"][i]
                inputs["ates_power_w"] = cold["power_w"][i]
            day_inputs.append(inputs)
        if operations is None:
            loss = float(assumptions.get("wellbore_heat_loss_multiplier", 1.0))
            day_results = [
                dispatch_day(
                    plant, h, c, n, challenge, ambient_c=amb, heat_loss_multiplier=loss, **inputs
                )
                for (h, c, n, amb), inputs in zip(loads, day_inputs)
            ]
            ops_rows = [{} for _ in loads]
        else:
            day_results, ops_rows = _run_with_operations(
                design, plant, loads, day_inputs, availability, operations, challenge, assumptions
            )
        rows = []
        for i, day in demand.iterrows():
            n_available = loads[i][2]
            r = dict(day_results[i])
            r.update(ops_rows[i])
            if cold is not None:
                r["ates_charge_w"] = cold["charge_w"][i]
                r["ates_flow_m3h"] = cold["flow_m3h"][i]
                r["ates_cold_well_extraction_c"] = cold["extraction_c"][i]
                r["ates_cold_volume_m3"] = cold["cold_volume_m3"][i]
                r["ates_cold_temperature_c"] = cold["cold_temperature_c"][i]
                r["ates_warm_temperature_c"] = cold["warm_temperature_c"][i]
            if store is not None:
                charge, discharge = store["charge_mw"][i] * 1e6, store["discharge_mw"][i] * 1e6
                r["plant_heating_load_w"] = r["heating_demand_w"]
                r["heating_demand_w"] = day["heating_mw"] * 1e6
                r["heat_delivered_w"] = r["heat_delivered_w"] - charge + discharge
                r["storage_charge_w"] = charge
                r["storage_discharge_w"] = discharge
                r["storage_loss_mwh"] = store["loss_mwh"][i]
                r["storage_soc_start_mwh"] = store["soc_start_mwh"][i]
                r["storage_soc_mwh"] = store["soc_end_mwh"][i]
                if "topup_mw" in store:
                    _book_pit_topup(r, design, plant, store, i, assumptions)
            r["date"] = day["date"]
            r["n_available"] = n_available
            r["violations"] = ";".join(r["violations"])
            rows.append(r)
    daily = pd.DataFrame(rows)
    summary = summarise(design, daily, availability, hydraulics, challenge, assumptions)
    if cold is not None:
        summary["ates"] = {
            "well_pairs": int(design.ates_doublets),
            "nominal_capacity_mw": cold["nominal_capacity_mw"],
            "heat_balance_imbalance": cold["imbalance"],
            "discharge_flow_fraction": cold["discharge_flow_fraction"],
            "charge_flow_fraction": cold["charge_flow_fraction"],
            "cooling_mwh": float(cold["cooling_w"].sum()) / 1e6 * HOURS_PER_DAY,
            "charge_mwh": float(cold["charge_w"].sum()) / 1e6 * HOURS_PER_DAY,
            "electricity_mwh": float(cold["power_w"].sum()) / 1e6 * HOURS_PER_DAY,
            "standing_loss_mwh": float(cold["loss_mwh"].sum()),
            "max_cold_volume_m3": float(np.max(cold["cold_volume_m3"])),
            "max_cold_well_extraction_c": (
                float(np.nanmax(cold["extraction_c"]))
                if np.isfinite(cold["extraction_c"]).any()
                else None
            ),
        }
    if store is not None and "topup_mw" in store:
        summary["pit_store"] = pit_storage.summary(design, store, assumptions)
        limit = assumptions["pit_store_top_max_c"]
        summary["checks"]["pit_store_within_temperature_limits"] = bool(
            store["top_c"].max() <= limit + 1e-6
            and (store["top_c"] >= store["bottom_c"] - 1e-6).all()
        )
        summary["all_hard_constraints_met"] = all(summary["checks"].values())
    if operations is not None:
        _add_operations_summary(summary, daily, operations, assumptions)
    return daily, summary


def _book_pit_topup(r, design, plant, store, i, assumptions):
    """Book a pit store's boiler top-up (store top temperature -> 100 degC) on day ``i``.

    The top-up uses boiler capacity left after the plant's own boiler duty,
    associated gas that would otherwise be flared first, then purchased gas
    (with its CO2 and cost). Top-up the boiler can not give is unmet heat.
    """
    a = assumptions
    topup = store["topup_mw"][i] * 1e6
    room = max(0.0, design.boiler_capacity_mw * 1e6 - r["boiler_heat_w"])
    served = min(topup, room)
    eff = a["boiler_efficiency"]
    ratio = plant.boiler_part_load_ratio(r["boiler_heat_w"] + served)
    if ratio == 1.0 and not r.get("boiler_efficiency_day"):
        assoc = min(served, max(0.0, r["associated_gas_flared_w"]) * eff)
        purchased = (served - assoc) / eff
        r["associated_gas_heat_w"] += assoc
        r["associated_gas_flared_w"] -= assoc / eff
    else:
        # part load: the top-up changes the boiler's load, so rebook its whole day at the
        # efficiency of the new load (associated gas the plant did not burn first)
        eff_old = r.get("boiler_efficiency_day") or eff
        eff_new = eff * ratio
        boiler_heat = r["boiler_heat_w"] + served
        assoc_fuel = r["associated_gas_heat_w"] / eff_old + max(0.0, r["associated_gas_flared_w"])
        assoc_heat = min(boiler_heat, assoc_fuel * eff_new)
        purchased = (boiler_heat - assoc_heat) / eff_new - r["purchased_gas_w"]
        r["associated_gas_heat_w"] = assoc_heat
        r["associated_gas_flared_w"] = assoc_fuel - assoc_heat / eff_new
        r["boiler_efficiency_day"] = eff_new
    co2 = purchased * a["natural_gas_emission_kg_per_gj"] / 1e9
    r["storage_topup_w"] = served
    r["boiler_heat_w"] += served
    r["purchased_gas_w"] += purchased
    r["co2_kg_s"] += co2
    r["cost_eur_s"] += (
        purchased / 3.6e9 * a["gas_price_eur_per_mwh"] + co2 / 1000.0 * a["co2_price_eur_per_t"]
    )
    # the plant was dispatched without the top-up, so book what the boiler gives on top
    r["heat_delivered_w"] += served
    r["unmet_heat_w"] += topup - served
    r["storage_top_c"] = store["top_c"][i]
    r["storage_bottom_c"] = store["bottom_c"][i]


def _peak_heat_rejected_mw(design, daily):
    """Design heat rejection of a wet cooling tower (MW): chiller rating x (1 + 1/COP)."""
    if getattr(design, "chiller_type", "legacy") != "centrifugal_tower":
        return 0.0
    cop = daily["electric_chiller_cop"].dropna() if "electric_chiller_cop" in daily else None
    worst = float(cop.min()) if cop is not None and not cop.empty else 5.0
    return design.chiller_capacity_mw * (1.0 + 1.0 / max(worst, 1.0))


def _run_with_operations(
    design, plant, loads, day_inputs, availability, rules, challenge, assumptions
):
    """Dispatch the year with commitment rules and wellbore warm-up.

    Pass 1 scores every number of running doublets on every day at the
    long-run wellbore heat loss and picks the yearly plan with
    :func:`gemini_design.operations.commit`. Pass 2 walks the plan, tracks
    each producer's time since start and re-dispatches each day's flow
    with that day's heat loss.
    """
    steady = WellboreModel(assumptions).multiplier(rules.reference_age_days)
    options = [
        dispatch_options(plant, h, c, n, challenge, amb, heat_loss_multiplier=steady, **inputs)
        for (h, c, n, amb), inputs in zip(loads, day_inputs)
    ]
    scores = [[s for _, s in day] for day in options]
    plan, breaks = commit(scores, [n for _, _, n, _ in loads], rules)
    state = WellboreThermalState(design.n_doublets, rules, assumptions)
    results, extra = [], []
    for i, (h, c, n_avail, amb) in enumerate(loads):
        n = plan[i]
        step = state.step(n, availability[i])
        mult = step["heat_loss_multiplier"]
        if n == 0 or abs(mult - steady) < 1e-9:
            r = options[i][n][0]
        else:
            r = dispatch_options(
                plant,
                h,
                c,
                n_avail,
                challenge,
                amb,
                heat_loss_multiplier=mult,
                counts={n},
                **day_inputs[i],
            )[n][0]
        results.append(r)
        extra.append(
            {
                "doublet_starts": step["starts"],
                "heat_loss_multiplier": mult,
                "running_doublets": ",".join(str(k + 1) for k in step["running"]),
            }
        )
    extra[0]["commitment_rule_breaks"] = breaks
    return results, extra


def _add_operations_summary(summary, daily, rules, assumptions):
    """Add operating KPIs and the commitment check to a run summary."""
    starts = int(daily["doublet_starts"].sum())
    breaks = int(daily["commitment_rule_breaks"].fillna(0).sum())
    start_cost = starts * rules.start_cost_eur
    summary["operations"] = {
        "rules": rules.as_dict(),
        "doublet_starts": starts,
        "start_cost_eur_per_year": start_cost,
        "commitment_rule_breaks": breaks,
        "steady_heat_loss_multiplier": WellboreModel(assumptions).multiplier(
            rules.reference_age_days
        ),
        "max_heat_loss_multiplier": float(daily["heat_loss_multiplier"].max()),
        "min_wellhead_temperature_c": float(
            daily.loc[daily["n_active"] > 0, "wellhead_temperature_c"].min()
        ),
    }
    summary["checks"]["min_run_stop_times_respected"] = breaks == 0
    summary["all_hard_constraints_met"] = all(summary["checks"].values())
    econ = summary["economics"]
    # starts are an operating cost like energy: add them to the levelised cost
    delivered = econ["annual_total_cost_eur"] / econ["lcoe_eur_per_mwh"]
    econ["annual_start_cost_eur"] = start_cost
    econ["annual_total_cost_eur"] += start_cost
    econ["lcoe_eur_per_mwh"] = econ["annual_total_cost_eur"] / delivered


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
    source_days = int(availability.any(axis=1).sum())  # days with any doublet available
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
    tower_water_m3 = (
        float(daily["tower_water_m3_s"].sum()) * 86400.0 if "tower_water_m3_s" in daily else 0.0
    )
    peak_heat_rejected_mw = _peak_heat_rejected_mw(design, daily)
    # district return temperatures other than the reference network's (gemini_design.network)
    net = network.delta_costs(
        daily["heating_demand_w"].to_numpy(dtype=float),
        daily["cooling_demand_w"].to_numpy(dtype=float),
        challenge,
        assumptions,
    )
    net_co2_t = net["pumping_mwh_el"] * assumptions["electricity_emission_kg_per_kwh"]
    net["energy_cost_eur"] = (
        net["pumping_mwh_el"] * assumptions["electricity_price_eur_per_mwh"]
        + net_co2_t * assumptions["co2_price_eur_per_t"]
    )
    co2_t += net_co2_t
    energy_cost += net["energy_cost_eur"]
    economics = levelised_cost(
        design,
        energy_cost,
        heat_delivered + cool_delivered,
        assumptions,
        peak_heat_rejected_mw=peak_heat_rejected_mw,
        network_capex_eur=net["substation_capex_eur"],
        esp_capex_eur=esp.capex_vs_reference_eur(esp_pumps(hydraulics, design), assumptions),
    )
    summary = {
        "design": design.as_dict(),
        "reservoir": {
            "depth_m": design.depth_m,
            **(
                {"doublet_depths_m": list(design.doublet_depths_m)}
                if getattr(design, "doublet_depths_m", ())
                else {}
            ),
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
            "free_cooling": mwh("free_cooling_w") if "free_cooling_w" in daily else 0.0,
            "ates_cooling": mwh("ates_cooling_w") if "ates_cooling_w" in daily else 0.0,
            "ates_electricity": mwh("ates_power_w") if "ates_power_w" in daily else 0.0,
            "unmet_cooling": mwh("unmet_cooling_w"),
            "geothermal_heat": mwh("geothermal_heat_w"),
            "heat_pump_heat": mwh("heat_pump_heat_w"),
            "boiler_heat": mwh("boiler_heat_w"),
            "electric_boiler_heat": (
                mwh("electric_boiler_heat_w") if "electric_boiler_heat_w" in daily else 0.0
            ),
            "heat_recovery_heat": (
                mwh("heat_recovery_heat_w") if "heat_recovery_heat_w" in daily else 0.0
            ),
            "heat_recovery_cooling": (
                mwh("heat_recovery_cooling_w") if "heat_recovery_cooling_w" in daily else 0.0
            ),
            "associated_gas_heat": mwh("associated_gas_heat_w"),
            "purchased_gas_fuel": mwh("purchased_gas_w"),
            "absorption_drive_heat": mwh("absorption_heat_w"),
            "electricity": mwh("electricity_w"),
            "chp_heat": mwh("chp_heat_w"),
            "chp_electricity": mwh("chp_power_el_w"),
            "orc_heat": mwh("orc_heat_w") if "orc_heat_w" in daily else 0.0,
            "orc_electricity": mwh("orc_power_el_w") if "orc_power_el_w" in daily else 0.0,
            "grid_import": mwh("grid_import_w"),
            "grid_export": mwh("grid_export_w"),
            "associated_gas_fuel": mwh("associated_gas_fuel_w"),
            "associated_gas_flared": mwh("associated_gas_flared_w"),
            "storage_charge": mwh("storage_charge_w") if "storage_charge_w" in daily else 0.0,
            "storage_discharge": (
                mwh("storage_discharge_w") if "storage_discharge_w" in daily else 0.0
            ),
            "storage_loss": (
                float(daily["storage_loss_mwh"].sum()) if "storage_loss_mwh" in daily else 0.0
            ),
        },
        "kpi": {
            # brine heat that reached the district (HEX, heat pump source, absorption drive);
            # brine heat an ORC turns into power is not district heat
            "geothermal_share_of_heat": (
                mwh("geothermal_heat_w") - (mwh("orc_heat_w") if "orc_heat_w" in daily else 0.0)
            )
            / max(heat_delivered + mwh("absorption_heat_w"), 1e-9),
            "gas_boiler_share_of_heat": mwh("boiler_heat_w")
            / max(heat_delivered + mwh("absorption_heat_w"), 1e-9),
            "associated_gas_unused_mwh": mwh("associated_gas_flared_w"),  # fuel (LHV), flared
            "co2_t_per_year": co2_t,
            "cooling_tower_water_m3_per_year": tower_water_m3,
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
            "geothermal_source_days": source_days,
            "days_without_geothermal": int(len(availability) - source_days),
            "doublet_active_days": int((daily["n_active"] > 0).sum()),
            "max_esp_dp_bar": float(active["esp_dp_bar"].max()) if not active.empty else 0.0,
            "esp_setting_depth_m": float(active["esp_depth_m"].max()) if not active.empty else 0.0,
            "max_injector_wellhead_pressure_bar": (
                float(active["injector_wellhead_pressure_bar"].max()) if not active.empty else 0.0
            ),
        },
        "network": {
            "heating_return_c": assumptions["heating_return_c"],
            "cooling_return_c": assumptions["cooling_return_c"],
            **net,
        },
        "checks": checks,
        "all_hard_constraints_met": all(checks.values()),
        "economics": economics,
    }
    pumps = esp_pumps(hydraulics, design)
    if pumps:
        summary["esp"] = {
            "pumps": [p.as_dict() for p in pumps],
            "capex_vs_reference_eur": economics["capex_eur"]["esp_vs_reference"],
            "min_efficiency": float(active["esp_efficiency"].min()) if not active.empty else 0.0,
            "max_choke_bar": float(active["esp_choke_bar"].max()) if not active.empty else 0.0,
            "days_out_of_range": int(
                daily["violations"].str.contains("esp_outside_operating_range").sum()
            ),
        }
    return summary
