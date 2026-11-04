"""Continuous design optimisation with external optimisers (petlab / py-trsqp / StoSAG).

The rule-based and Claude agents search a discrete design space with engineering heuristics.
This module hands the continuous design variables to proper black-box optimisers:

* **DFTR-Filter** (``py_trsqp``, through ``petlab.optimization``): derivative-free trust-region
  method with output constraints - the natural fit for a simulator-in-the-loop design problem.
* **COBYLA** (scipy, through ``petlab.optimization``): cheap baseline for comparison.
* **StoSAG** (``stosag``): ensemble-gradient robust optimisation over geological uncertainty
  (permeability, geothermal gradient, injector skin) - minimises the expected annual cost.

Design vector (fixed number of doublets):
    x = [reservoir depth m, heat pump MW, absorption chiller MW, electric chiller MW,
         ESP depth m, ESP BEP m3/h]
Objective: total annual cost (MEUR). Output constraints (>= 0 is feasible):
    c1 = -(unmet heat + unmet cool) GWh          (demand always met)
    c2 = ESP intake margin above bubble point    (bar, minus 5 bar safety)
    c3 = injection WHP margin to the limit       (bar)
    c4 = erosional velocity margin               (m/s)
"""

from __future__ import annotations

import dataclasses
import json
import sys
import time
from pathlib import Path

import numpy as np

from .demand import DemandProfile
from .spec import HackathonSpec, ReservoirSpec, SPEC
from .subsurface import WellDesign
from .system import SystemDesign, evaluate_design

_ROOT = Path(__file__).resolve().parents[2]
for sub in ["petlab-master/petlab-master/src", "py-trsqp-main/py-trsqp-main", "stosag-master/stosag-master"]:
    p = _ROOT / sub
    if p.exists() and str(p) not in sys.path:
        sys.path.insert(0, str(p))

X_NAMES = ["depth_m", "heat_pump_mw", "absorption_mw", "electric_chiller_mw", "esp_depth_m", "esp_bep_m3_h"]
LB = [2500.0, 0.0, 0.0, 0.0, 500.0, 100.0]
UB = [4000.0, 35.0, 12.0, 12.0, 1500.0, 300.0]


def design_from_x(x, n_doublets: int, name: str = "opt") -> SystemDesign:
    # optimisers (COBYLA in particular) may probe outside the box; the physical design is clipped
    x = [float(np.clip(v, lo, hi)) for v, lo, hi in zip(x, LB, UB)]
    well = WellDesign(reservoir_midpoint_m=x[0], esp_depth_m=x[4], esp_bep_m3_h=x[5])
    return SystemDesign(name=name, n_doublets=n_doublets, well=well, heat_pump_mw=x[1],
                        absorption_chiller_mw=x[2], electric_chiller_mw=x[3])


def spec_with(permeability_md: float | None = None, gradient: float | None = None) -> HackathonSpec:
    res = SPEC.reservoir
    res = dataclasses.replace(res, **{k: v for k, v in {"permeability_md": permeability_md,
                                                        "geothermal_gradient_c_per_km": gradient}.items() if v is not None})
    return dataclasses.replace(SPEC, reservoir=res)


class DesignProblem:
    """Cached, constraint-returning evaluator around ``evaluate_design``."""

    def __init__(self, demand: DemandProfile, n_doublets: int, spec: HackathonSpec = SPEC,
                 overrides: dict | None = None, day_stride: int = 2, log=print):
        self.demand, self.n, self.spec, self.overrides = demand, n_doublets, spec, overrides
        self.day_stride, self.log = day_stride, log
        self.cache: dict[tuple, dict] = {}
        self.history: list[dict] = []
        self.n_eval = 0
        self.checkpoint: Path | None = None

    def _key(self, x):
        return tuple(round(float(v), 3) for v in x)

    def evaluate(self, x) -> dict:
        k = self._key(x)
        if k in self.cache:
            return self.cache[k]
        t0 = time.time()
        ds = design_from_x(x, self.n)
        r = evaluate_design(ds, self.demand, self.spec, overrides=self.overrides, fast=True, day_stride=self.day_stride)
        kp, c = r.kpis, self.spec.constraints
        out = {
            "x": list(k), "f": r.cost["total_annual_cost_meur"], "lcoe": r.cost["levelised_cost_eur_per_mwh"],
            "feasible": r.feasible, "cop": kp["system_cop"], "electricity_gwh": kp["electricity_gwh"],
            "c1_unmet": -(kp["unmet_heat_gwh"] + kp["unmet_cool_gwh"]),
            "c2_bubble": kp["esp_intake_pressure_at_300_bar"] - kp["bubble_point_bar"] - 5.0,
            "c3_whp": c.max_wellhead_pressure_bar - kp["injection_whp_at_300_bar"],
            "c4_erosion": kp["erosional_velocity_m_s"] - kp["tubing_velocity_at_300_m_s"],
            "hard": [v.code for v in r.violations if v.severity == "hard"],
            "t_s": time.time() - t0,
        }
        self.n_eval += 1
        self.cache[k] = out
        self.history.append(out)
        if self.checkpoint is not None:
            self.checkpoint.write_text(json.dumps(self.history, default=float), encoding="utf-8")
        if self.log and self.n_eval % 10 == 0:
            best = min((h for h in self.history if h["c1_unmet"] >= -1e-6 and not h["hard"]), key=lambda h: h["f"], default=None)
            self.log(f"    eval {self.n_eval:4d}: f={out['f']:.3f} unmet={-out['c1_unmet']:.3f} "
                     f"best feasible so far: {best['f'] if best else float('nan'):.3f} MEUR")
        return out

    # scalar interfaces for petlab / py_trsqp / scipy
    def cf(self, x):
        return float(self.evaluate(x)["f"])

    def ineqs(self):
        return [lambda x: float(self.evaluate(x)["c1_unmet"]),
                lambda x: float(self.evaluate(x)["c2_bubble"]),
                lambda x: float(self.evaluate(x)["c3_whp"]),
                lambda x: float(self.evaluate(x)["c4_erosion"])]

    def best_feasible(self) -> dict | None:
        feas = [h for h in self.history if h["c1_unmet"] >= -1e-6 and not h["hard"]]
        return min(feas, key=lambda h: h["f"]) if feas else None


# ------------------------------------------------------------------------------------------------
# Deterministic optimisers via petlab's backend interface
# ------------------------------------------------------------------------------------------------
def run_petlab_backend(problem: DesignProblem, x0, backend: str = "DFTR", max_iter: int = 30, budget: int = 150,
                       constants: dict | None = None) -> dict:
    from petlab.config import OptimizationConfig
    from petlab.optimization import optimize

    cfg = OptimizationConfig(optimizer=backend, max_iter=max_iter, constants=constants or {}, options={"budget": budget})
    t0 = time.time()
    res = optimize(problem.cf, [], problem.ineqs(), list(x0), list(LB), list(UB), cfg)
    best = problem.best_feasible()
    return {"backend": backend, "x_best": list(res.x_best), "f_best": float(res.f_best),
            "n_evaluations": int(res.n_evaluations), "termination": res.termination_status,
            "best_feasible_point": best, "elapsed_s": time.time() - t0,
            "history_f": [None if v is None else float(v) for v in res.history.get("f", [])]}


# ------------------------------------------------------------------------------------------------
# Robust optimisation under geological uncertainty via StoSAG
# ------------------------------------------------------------------------------------------------
def make_ensemble(m: int, seed: int = 7) -> list[dict]:
    rng = np.random.default_rng(seed)
    perm = np.exp(rng.normal(np.log(200.0), 0.35, m))           # lognormal around 200 mD (P10~130, P90~310)
    grad = rng.normal(30.0, 1.5, m)                              # 30 +/- 1.5 C/km
    skin = np.clip(rng.normal(2.0, 1.5, m), 0.0, 6.0)            # injector skin uncertainty
    return [{"permeability_md": float(p), "gradient": float(g), "skin_injection_extra": float(s) - 2.0}
            for p, g, s in zip(perm, grad, skin)]


def run_stosag(demand: DemandProfile, n_doublets: int, x0, ensemble: list[dict], max_iter: int = 8,
               day_stride: int = 3, penalty_meur_per_gwh: float = 5.0, log=print, seed: int = 1) -> dict:
    from stosag.stosag import stosag

    problems = [DesignProblem(demand, n_doublets, spec_with(e["permeability_md"], e["gradient"]),
                              overrides={"skin_injection_extra": e["skin_injection_extra"]},
                              day_stride=day_stride, log=None) for e in ensemble]
    m = len(ensemble)
    n_eval = {"n": 0}

    def penalised(prob, x):
        o = prob.evaluate(x)
        return o["f"] + penalty_meur_per_gwh * max(0.0, -o["c1_unmet"]) + (2.0 if o["hard"] else 0.0)

    def functions(x):
        x = np.asarray(x, dtype=float)
        if x.ndim == 1:                      # one design, all realisations
            vals = np.array([penalised(p, x) for p in problems])
        else:                                # one design per realisation (ensemble members)
            vals = np.array([penalised(p, x[i]) for i, p in enumerate(problems)])
        n_eval["n"] += m
        log(f"    stosag batch {n_eval['n']:4d} evals, mean f={vals.mean():.3f}")
        return vals

    np.random.seed(seed)
    # perturbation covariance in StoSAG's logit-normalised space (0.15 ~ 4 % of the range); the gradient
    # estimate is scaled by Ct, so the initial line-search step has to be large and let backtracking shrink it
    ct = np.eye(len(x0)) * 0.15 ** 2
    # StoSAG log-normalises the variables, so bounds and the start point must be strictly positive
    lb_pos = [max(v, 0.1) for v in LB]
    # ... and the start point strictly inside the bounds (logit transform: log((x-lb)/(ub-x)))
    x0_pos = [float(np.clip(v, lo + 0.02 * (hi - lo), hi - 0.02 * (hi - lo))) for v, lo, hi in zip(x0, lb_pos, UB)]
    opt = stosag(x0_pos, functions, lb_pos, list(UB), [], m, ct,
                 constants={"mode": 4, "max_iter": max_iter, "line_search_max_iter": 7,
                            "line_search_max_attempts": 3, "line_search_alpha": 40.0})
    t0 = time.time()
    opt.run()
    # expected cost / feasibility of the best iterate across the ensemble
    xb = np.array(opt.x_list[-1]) if opt.x_list else np.array(x0, dtype=float)
    evals = [p.evaluate(xb) for p in problems]
    return {"backend": "StoSAG", "x_best": [float(v) for v in xb],
            "expected_cost_meur": float(np.mean([e["f"] for e in evals])),
            "worst_cost_meur": float(max(e["f"] for e in evals)),
            "feasible_fraction": float(np.mean([e["c1_unmet"] >= -1e-6 and not e["hard"] for e in evals])),
            "per_realisation": [{"ensemble": ens, "cost": e["f"], "unmet_gwh": -e["c1_unmet"], "hard": e["hard"]}
                                for ens, e in zip(ensemble, evals)],
            "iterate_costs": [float(j) for j in opt.j_list], "n_evaluations": n_eval["n"],
            "elapsed_s": time.time() - t0}


def robustness_check(demand: DemandProfile, n_doublets: int, x, ensemble: list[dict], day_stride: int = 3) -> dict:
    """Evaluate a fixed design across the ensemble (used for the nominal design too)."""
    out = []
    for e in ensemble:
        p = DesignProblem(demand, n_doublets, spec_with(e["permeability_md"], e["gradient"]),
                          overrides={"skin_injection_extra": e["skin_injection_extra"]}, day_stride=day_stride, log=None)
        o = p.evaluate(x)
        out.append({"ensemble": e, "cost": o["f"], "unmet_gwh": -o["c1_unmet"], "hard": o["hard"]})
    return {"x": [float(v) for v in x], "expected_cost_meur": float(np.mean([o["cost"] for o in out])),
            "worst_cost_meur": float(max(o["cost"] for o in out)),
            "feasible_fraction": float(np.mean([o["unmet_gwh"] <= 1e-6 and not o["hard"] for o in out])),
            "per_realisation": out}
