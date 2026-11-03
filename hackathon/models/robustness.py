"""Robustness check: Monte Carlo over the sourced uncertainty ranges.

Reports P10 / P50 / P90 with **P90 as the conservative case** for every KPI
(SPE/WPC Petroleum Reserves Definitions 1997: 'at least a 90% probability
that the quantities actually recovered will equal or exceed the estimate'):

  * less-is-better KPIs (LCOH, net electricity, natural gas): P90 = value not
    exceeded in 90% of samples (90th percentile)
  * more-is-better KPIs (geothermal heat share): P90 = value exceeded in 90%
    of samples (10th percentile)

Feasible share = fraction of samples with no hard violation. A design is
robust when feasible share >= 0.90 (owner decision).

Uncertain inputs and their sourced ranges (sampled uniformly and
independently; uniform sampling and the seed are method choices):
  porosity 0.146-0.189 (owner, Slochteren studies) | skin producer and
  injector 0-5 (DoubletCalc 1.4 p.18; TNO 2012 p.29) | heat pump eta_Lorenz
  0.42-0.61 (Pieper et al. 2020) | absorption COP 0.65-0.84 (CIBSE 2016) |
  heat exchanger approach 3-5 C (Slihte et al. 2016) | CHP between EPA
  Table 2-2 systems 2 and 3 | natural gas 26.56-58.36 EUR/MWh (ACER 2025).
"""

import copy
from dataclasses import replace

import numpy as np

from .config import load_config
from .dispatch import evaluate_design, load_demand

RANGES = {
    "porosity": (0.146, 0.189),
    "skin_producer": (0.0, 5.0),
    "skin_injector": (0.0, 5.0),
    "hp_eta_lorenz": (0.42, 0.61),
    "absorption_cop": (0.65, 0.84),
    "hx_approach_k": (3.0, 5.0),
    "chp_mix": (0.0, 1.0),        # 0 = EPA system 2, 1 = EPA system 3
    "gas_price": (26.56, 58.36),
}
CHP_SYSTEMS = ((0.345 * 1.10, 0.444 * 1.10), (0.368 * 1.10, 0.416 * 1.10))  # (el, heat) LHV


def _sample(rng):
    return {k: float(rng.uniform(*v)) for k, v in RANGES.items()}


def run_robustness(design, n_samples=100, seed=2027):
    """Evaluate ``design`` under ``n_samples`` draws; return P10/P50/P90 and feasibility."""
    rng = np.random.default_rng(seed)
    base_over = {"heating_return_c": design.heating_return_c} if design.heating_return_c else {}
    demand = load_demand(load_config())
    rows = []
    for _ in range(n_samples):
        s = _sample(rng)
        cfg = load_config(overrides={**base_over, "porosity": s["porosity"],
                                     "skin_producer": s["skin_producer"],
                                     "skin_injector": s["skin_injector"]})
        cfg.economics = copy.deepcopy(cfg.economics)
        cfg.economics["other_sources"]["natural_gas_eur_per_mwh"] = s["gas_price"]
        (el2, h2), (el3, h3) = CHP_SYSTEMS
        m = s["chp_mix"]
        surf = replace(design.surface, hp_eta_lorenz=s["hp_eta_lorenz"],
                       absorption_cop=s["absorption_cop"], hx_approach_k=s["hx_approach_k"],
                       chp_elec_eff=el2 + m * (el3 - el2), chp_heat_eff=h2 + m * (h3 - h2))
        r = evaluate_design(replace(design, surface=surf), cfg=cfg, demand=demand)
        k = r["kpis"]
        rows.append({
            "feasible": not any(v["severity"] == "hard" for v in r["violations"]),
            "hard": [v["constraint"] for v in r["violations"] if v["severity"] == "hard"],
            "lcoh": k["lcoh_eur_per_mwh"], "net_elec": k["net_electricity_gwh"],
            "gas": k["natural_gas_gwh"], "geo_share": k["heat_share_geothermal_direct_and_hp"],
            "unmet": k["heat_unmet_gwh"] + k["cool_unmet_gwh"],
            "breakthrough": k["breakthrough_years"],
        })

    def less_better(key):
        a = np.array([x[key] for x in rows])
        return {"P10": float(np.percentile(a, 10)), "P50": float(np.percentile(a, 50)),
                "P90": float(np.percentile(a, 90))}

    def more_better(key):
        a = np.array([x[key] for x in rows])
        return {"P10": float(np.percentile(a, 90)), "P50": float(np.percentile(a, 50)),
                "P90": float(np.percentile(a, 10))}

    failures = {}
    for x in rows:
        for c in x["hard"]:
            failures[c] = failures.get(c, 0) + 1
    feasible_share = sum(x["feasible"] for x in rows) / len(rows)
    return {
        "n_samples": n_samples,
        "feasible_share": feasible_share,
        "robust": feasible_share >= 0.90,
        "failure_counts": failures,
        "lcoh_eur_per_mwh": less_better("lcoh"),
        "net_electricity_gwh": less_better("net_elec"),
        "natural_gas_gwh": less_better("gas"),
        "unmet_gwh": less_better("unmet"),
        "breakthrough_years": more_better("breakthrough"),
        "heat_share_geothermal": more_better("geo_share"),
        "convention": "P90 = conservative case (90% confidence of at least this good)",
    }


def return_temperature_sensitivity(design, temps=(45, 50, 55, 60, 65, 70)):
    """Re-run ``design`` at each heating return temperature (owner decision A5)."""
    out = []
    for t in temps:
        r = evaluate_design(replace(design, heating_return_c=float(t)))
        k = r["kpis"]
        out.append({"heating_return_c": t, "lcoh_eur_per_mwh": k["lcoh_eur_per_mwh"],
                    "net_electricity_gwh": k["net_electricity_gwh"],
                    "heat_hp_gwh": k["heat_hp_gwh"], "heat_direct_gwh": k["heat_direct_gwh"],
                    "hard_violations": [v["constraint"] for v in r["violations"]
                                        if v["severity"] == "hard"]})
    return out
