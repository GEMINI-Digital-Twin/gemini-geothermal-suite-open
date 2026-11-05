"""Ground truth for the benchmark: an exhaustive design grid on the current code.

The oracle runs every combination of the discrete design options that the agent can
reach (doublets, depth, upgrade, cooling, chiller type, CHP) for one set of assumption
overrides, and keeps the year KPIs. Design cases score the agent's pick against it:
regret = (agent LCOE - best LCOE) / best LCOE, and distance to the cost/CO2 Pareto
front. Results are cached on disk by a hash of the code, data files, demand profile and
overrides, so the reference can not go out of date when the models or inputs change.

Free cooling and ATES are left out: they need outdoor temperatures, which the agent's
demand input does not carry, so they have no effect on its runs.
"""

import hashlib
import itertools
import json
import warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from gemini_agent.fingerprint import code_hash, demand_hash
from gemini_agent.physics_gate import check_run
from gemini_agent.tools import make_design, split_overrides
from gemini_design.annual import run_year
from gemini_design.challenge import CHILLER_TYPES

DEPTHS_M = (2500, 2800, 3100, 3400, 3700)
GRID = {
    "n_doublets": (1, 2, 3),
    "depth_m": DEPTHS_M,
    "upgrade": ("boiler", "heat_pump"),
    "cooling": ("absorption", "electric"),
    "chiller_type": tuple(CHILLER_TYPES),
    "chp": (False, True),
}
SMALL_GRID = {  # the test grid: matches cases.SMALL_SCREEN
    "n_doublets": (1, 2),
    "depth_m": (2800, 3100, 3400),
    "upgrade": ("boiler", "heat_pump"),
    "cooling": ("electric",),
    "chiller_type": ("legacy", "screw_dry_cooler"),
    "chp": (True,),
}
# Tracked, so a fresh clone (e.g. the PC that runs the live models) need not rebuild it.
CACHE_DIR = Path(__file__).resolve().parents[3] / "simulator_examples" / "agent_bench_oracle"


def grid_designs(grid=None):
    """All option combinations; absorption cooling only with the default chiller type."""
    grid = grid or GRID
    keys = list(grid)
    out = []
    for combo in itertools.product(*(grid[k] for k in keys)):
        args = dict(zip(keys, combo))
        if args["cooling"] == "absorption" and args["chiller_type"] != "legacy":
            continue
        out.append(args)
    return out


def _worker(job):
    args, demand, overrides = job
    challenge, assumptions, scale = split_overrides(overrides)
    if scale != 1.0:
        demand = demand.copy()
        demand[["heating_mw", "cooling_mw"]] *= scale
    design = make_design(args, float(demand["heating_mw"].max()), float(demand["cooling_mw"].max()))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        daily, summary = run_year(design, demand, challenge, assumptions)
        gate = check_run(summary, daily, challenge, assumptions)
    k, e = summary["kpi"], summary["energy_mwh"]
    return {
        "args": args,
        "design": summary["design"]["name"],
        "lcoe_eur_per_mwh": round(float(summary["economics"]["lcoe_eur_per_mwh"]), 3),
        "co2_t_per_year": round(float(k["co2_t_per_year"]), 1),
        "meets_all_hard_rules": bool(summary["all_hard_constraints_met"]),
        "gate_passed": bool(gate["passed"]),
        "unmet_heating_mwh": round(float(e["unmet_heating"]), 2),
        "unmet_cooling_mwh": round(float(e["unmet_cooling"]), 2),
    }


def save(rows, overrides, designs, demand=None):
    """Write grid rows to the cache (with a small meta file saying what they are)."""
    path = Oracle.cache_path(overrides, designs, demand)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, separators=(",", ":")), encoding="utf-8")
    meta = {
        "code": code_hash(),
        "demand": demand_hash(demand),
        "overrides": overrides,
        "n_designs": len(designs),
    }
    path.with_suffix(".meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return path


class Oracle:
    """Exhaustive grid results for one set of overrides, with lookups used by scorers."""

    def __init__(self, rows, overrides=None):
        """Wrap grid rows (dicts from the worker)."""
        self.rows = rows
        self.overrides = dict(overrides or {})
        self.feasible = sorted(
            (r for r in rows if r["meets_all_hard_rules"] and r["gate_passed"]),
            key=lambda r: r["lcoe_eur_per_mwh"],
        )

    @staticmethod
    def cache_path(overrides, designs, demand=None):
        """Cache file for a grid, overrides and demand profile on the current code and data."""
        tag = hashlib.sha256(
            json.dumps(
                [code_hash(), demand_hash(demand), overrides, designs], sort_keys=True
            ).encode()
        ).hexdigest()[:16]
        return CACHE_DIR / f"oracle_{tag}.json"

    @classmethod
    def build(cls, demand, overrides=None, workers=4, cache=True, designs=None):
        """Run (or load) the grid for ``overrides``."""
        overrides = dict(overrides or {})
        designs = designs or grid_designs()
        path = cls.cache_path(overrides, designs, demand)
        if cache and path.exists():
            return cls(json.loads(path.read_text(encoding="utf-8")), overrides)
        jobs = [(a, demand, overrides) for a in designs]
        if workers > 1:
            with ProcessPoolExecutor(max_workers=workers) as pool:
                rows = list(pool.map(_worker, jobs, chunksize=4))
        else:
            rows = [_worker(j) for j in jobs]
        if cache:
            save(rows, overrides, designs, demand)
        return cls(rows, overrides)

    # ------------------------------------------------------------ lookups
    @property
    def best(self):
        """Cheapest feasible, gate-passing design."""
        return self.feasible[0] if self.feasible else None

    def pareto(self):
        """Feasible designs not beaten on both LCOE and CO2."""
        front, best_co2 = [], float("inf")
        for r in self.feasible:  # sorted by LCOE
            if r["co2_t_per_year"] < best_co2 - 1e-9:
                front.append(r)
                best_co2 = r["co2_t_per_year"]
        return front

    def best_under(self, lcoe_max=None, co2_max=None, key="lcoe_eur_per_mwh"):
        """Best feasible design by ``key`` within the given caps."""
        rows = [
            r
            for r in self.feasible
            if (lcoe_max is None or r["lcoe_eur_per_mwh"] <= lcoe_max)
            and (co2_max is None or r["co2_t_per_year"] <= co2_max)
        ]
        return min(rows, key=lambda r: r[key]) if rows else None

    def find(self, **args):
        """Grid row matching the given design arguments, if any."""
        for r in self.rows:
            if all(r["args"].get(k) == v for k, v in args.items()):
                return r
        return None

    def regret(self, lcoe):
        """Relative LCOE regret of ``lcoe`` against the best design (0 = optimal)."""
        best = self.best
        if best is None or lcoe is None:
            return None
        return max(0.0, (lcoe - best["lcoe_eur_per_mwh"]) / best["lcoe_eur_per_mwh"])
