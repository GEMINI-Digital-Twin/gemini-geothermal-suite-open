"""Deterministic design search, robustness (Monte Carlo) and stress tests.

The LLM chooses *what* to explore and *why*; this module does the number
crunching on the GEMINI-based simulator, so no engineering number is produced
by the LLM.

Search (staged, ~100 annual simulations):
  1. subsurface + heat: depth x doublets x heat-pump size (cooling by electric
     chiller, gas reinjected, DH return 50 C), boiler right-sized;
  2. refine the best candidates: cooling technology mix, gas handling, DH return.
Objective: LCOE (CO2 priced at the assumed CO2 price) or a CO2-weighted score.
"""

from __future__ import annotations

import itertools
import math
import random

from gemini_agent.physics.design import DesignSpec
from gemini_agent.physics.site import Brief, Demand
from gemini_agent.service import DesignService, Evaluation

OBJECTIVES = {
    "min_lcoe": 0.0,  # extra CO2 shadow price on top of the assumed CO2 price (EUR/t)
    "balanced": 110.0,  # -> effective 200 EUR/t
    "min_co2": None,  # lexicographic: lowest CO2, then LCOE
}


def score(ev: Evaluation, objective: str) -> float:
    """Lower is better. Infeasible designs are pushed to the back."""
    e, k = ev.economics, ev.kpis
    energy = (k["heat_demand_gwh"] + k["cool_demand_gwh"]) * 1000
    if OBJECTIVES[objective] is None:  # min_co2: CO2 dominates, LCOE breaks ties
        s = k["co2_t"] + e["lcoe_eur_per_mwh"] * 1e-3
    else:
        s = e["lcoe_eur_per_mwh"] + OBJECTIVES[objective] * k["co2_t"] / energy
    return s + (1e4 if not ev.checks["passed"] else 0.0)


def right_size_boiler(svc: DesignService, spec: DesignSpec, n1_margin: bool = True) -> Evaluation:
    """Size the backup boiler from the year's actual need (+ N-1 peak-day margin)."""
    big = spec.model_copy(update={"backup_boiler_mw": 40.0})
    ev = svc.evaluate(big)
    need = max(d.q_boiler for d in ev.result.days)
    if n1_margin and spec.n_doublets >= 1:
        peak_day = max(range(len(svc.demand.heating_mw)), key=lambda i: svc.demand.heating_mw[i])
        ev_n1 = svc.evaluate(big, outage={"doublets": 1, "days": [peak_day]})
        need = max(need, ev_n1.result.days[peak_day].q_boiler)
    size = math.ceil(need * 1.05 * 2) / 2  # 5 % margin, 0.5 MW steps
    return svc.evaluate(spec.model_copy(update={"backup_boiler_mw": size}))


def search(
    svc: DesignService,
    objective: str = "min_lcoe",
    depths=(2200, 2500, 2800, 3100, 3400),
    doublets=(1, 2, 3),
    heat_pumps=(0.0, 5.0, 10.0, 15.0),
    top_k: int = 3,
    progress=None,
) -> dict:
    """Staged search; returns ranked candidates and the full evaluated set."""
    peak_cool = max(svc.demand.cooling_mw)
    stage1: list[Evaluation] = []
    combos = list(itertools.product(depths, doublets, heat_pumps))
    for i, (z, n, hp) in enumerate(combos):
        spec = DesignSpec(
            well_depth_m=z,
            n_doublets=n,
            heat_pump_mw=hp,
            electric_chiller_mw=math.ceil(peak_cool),
            gas_handling="keep_in_solution_reinject",
            dh_return_temperature_c=50.0,
        )
        stage1.append(right_size_boiler(svc, spec))
        if progress:
            progress(f"stage 1: {i + 1}/{len(combos)}")
    stage1.sort(key=lambda ev: score(ev, objective))
    stage2: list[Evaluation] = []
    seeds = stage1[:top_k]
    variants = list(
        itertools.product(
            (0.0, math.ceil(peak_cool / 2), math.ceil(peak_cool)),  # absorption share
            ("keep_in_solution_reinject", "separate_and_burn"),
            (45.0, 50.0, 55.0),
        )
    )
    for j, ev in enumerate(seeds):
        for abs_mw, gas, tr in variants:
            spec = ev.spec.model_copy(
                update={
                    "absorption_chiller_mw": abs_mw,
                    "electric_chiller_mw": max(0.0, math.ceil(peak_cool) - abs_mw)
                    + (1.0 if abs_mw else 0.0),
                    "gas_handling": gas,
                    "dh_return_temperature_c": tr,
                }
            )
            stage2.append(right_size_boiler(svc, spec))
        if progress:
            progress(f"stage 2: seed {j + 1}/{len(seeds)}")
    everything = {ev.spec.key(): ev for ev in stage1 + stage2}
    ranked = sorted(everything.values(), key=lambda ev: score(ev, objective))
    return {
        "objective": objective,
        "n_evaluated": len(everything),
        "best": ranked[0],
        "ranked": ranked,
        "pareto": pareto_front(list(everything.values())),
    }


def pareto_front(evs: list[Evaluation]) -> list[Evaluation]:
    """Feasible designs not dominated in (LCOE, CO2)."""
    feas = [e for e in evs if e.checks["passed"]]
    front = []
    for a in feas:
        la, ca = a.economics["lcoe_eur_per_mwh"], a.kpis["co2_t"]
        if not any(
            (b.economics["lcoe_eur_per_mwh"] <= la and b.kpis["co2_t"] <= ca)
            and (b.economics["lcoe_eur_per_mwh"] < la or b.kpis["co2_t"] < ca)
            for b in feas
        ):
            front.append(a)
    return sorted(front, key=lambda e: e.kpis["co2_t"])


def stress_test(svc: DesignService, spec: DesignSpec, scenario: str) -> dict:
    """Named stress scenarios on a fixed design."""
    if scenario == "doublet_trip_on_peak_day":
        peak = max(range(365), key=lambda i: svc.demand.heating_mw[i])
        ev = svc.evaluate(spec, outage={"doublets": 1, "days": [peak]})
        d = ev.result.days[peak]
        return {
            "scenario": scenario,
            "date": svc.demand.dates[peak],
            "unmet_heat_mw": round(d.unmet_heat, 3),
            "boiler_mw": round(d.q_boiler, 2),
            "survives": bool(d.unmet_heat < 1e-3),
        }
    if scenario.startswith("demand_plus_"):
        pct = float(scenario.split("_")[-1])
        f = 1 + pct / 100
        demand = Demand(
            svc.demand.dates,
            [h * f for h in svc.demand.heating_mw],
            [c * f for c in svc.demand.cooling_mw],
            svc.demand.heating_supply_c,
            svc.demand.cooling_supply_c,
        )
        ev = DesignService(svc.brief, demand, weather=svc.weather).evaluate(spec)
        return {
            "scenario": scenario,
            "feasible": bool(ev.checks["passed"]),
            "violations": [v["check"] for v in ev.checks["violations"]],
            "unmet_heat_mwh": ev.kpis["unmet_heat_mwh"],
            "unmet_cool_mwh": ev.kpis["unmet_cool_mwh"],
        }
    raise ValueError("scenario must be 'doublet_trip_on_peak_day' or 'demand_plus_<pct>'")


def monte_carlo(svc: DesignService, spec: DesignSpec, n: int = 30, seed: int = 7) -> dict:
    """Subsurface + demand + price uncertainty -> P10/P50/P90 of key outputs."""
    rng = random.Random(seed)
    lcoe, co2, unmet, geo = [], [], [], []
    base_raw = svc.brief.raw
    for _ in range(n):
        raw = _deepcopy(base_raw)
        raw["reservoir"]["geothermal_gradient_c_per_km"] = rng.gauss(30.0, 1.5)
        raw["reservoir"]["permeability_md"] = math.exp(rng.gauss(math.log(200.0), 0.35))
        b = Brief(raw=raw)
        f = rng.uniform(0.9, 1.1)
        dem = Demand(
            svc.demand.dates,
            [h * f for h in svc.demand.heating_mw],
            [c * f for c in svc.demand.cooling_mw],
            svc.demand.heating_supply_c,
            svc.demand.cooling_supply_c,
        )
        s2 = DesignService(b, dem, weather=svc.weather)
        vals = s2.econ["values"]
        vals["heat_pump_eta_lorenz"] = rng.uniform(0.45, 0.55)
        vals["electricity_eur_per_mwh"] = rng.uniform(100, 220)
        vals["natural_gas_eur_per_mwh"] = rng.uniform(30, 70)
        vals["well_per_m_eur"] = rng.uniform(1600, 2600)
        vals["heat_pump_eur_per_mw_th"] = rng.uniform(450e3, 800e3)
        ev = s2.evaluate(spec)
        lcoe.append(ev.economics["lcoe_eur_per_mwh"])
        co2.append(ev.kpis["co2_t"])
        unmet.append(ev.kpis["unmet_heat_mwh"] + ev.kpis["unmet_cool_mwh"])
        geo.append(ev.kpis["geothermal_share_of_heat_pct"])

    def p(xs, q):
        ys = sorted(xs)
        return round(ys[min(len(ys) - 1, int(q * (len(ys) - 1) + 0.5))], 2)

    return {
        "samples": n,
        "lcoe_eur_per_mwh": {"P10": p(lcoe, 0.1), "P50": p(lcoe, 0.5), "P90": p(lcoe, 0.9)},
        "co2_t": {"P10": p(co2, 0.1), "P50": p(co2, 0.5), "P90": p(co2, 0.9)},
        "geothermal_share_pct": {"P10": p(geo, 0.1), "P50": p(geo, 0.5), "P90": p(geo, 0.9)},
        "probability_demand_fully_met": round(sum(1 for u in unmet if u < 1e-3) / n, 3),
        "varied": {
            "gradient_c_per_km": "N(30, 1.5)",
            "permeability_md": "lognormal(200, 0.35)",
            "demand_scale": "U(0.9, 1.1)",
            "hp_eta_lorenz": "U(0.45, 0.55)",
            "electricity_eur_per_mwh": "U(100, 220)",
            "gas_eur_per_mwh": "U(30, 70)",
            "well_cost_eur_per_m": "U(1600, 2600)",
            "heat_pump_capex_eur_per_mw": "U(450k, 800k)",
        },
    }


def _deepcopy(d):
    import copy

    return copy.deepcopy(d)
