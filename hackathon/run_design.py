"""Evaluate one hand-picked design over 365 days: KPIs, LCOH, violations.

Run from the repo root:
    PYTHONPATH=. python hackathon/run_design.py            # deterministic run
    PYTHONPATH=. python hackathon/run_design.py --robust   # plus P10/P50/P90 (about 1 minute)
"""

import argparse
import json
from pathlib import Path

from hackathon.models.dispatch import Design, evaluate_design, summarize
from hackathon.models.robustness import run_robustness
from hackathon.models.surface import SurfaceParams

RUNS = Path(__file__).parent / "runs"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--robust", action="store_true")
    a = ap.parse_args()
    design = Design(
        depth_m=2500, n_doublets=2, spacing_m=1600, max_flow_m3h=300, outage="staggered",
        surface=SurfaceParams(hp_capacity_mw=15, chiller_type="absorption_dh", sorption_capacity_mw=10,
                              elec_chiller_capacity_mw=4, boiler_capacity_mw=10),
    )
    result = evaluate_design(design)
    print(summarize(result))
    print("CAPEX (M EUR):", result["economics"]["capex_meur"])
    out = {k: result[k] for k in ("design", "kpis", "economics", "violations")}
    if a.robust:
        rb = run_robustness(design)
        out["robustness"] = rb
        print("Robustness:", {k: rb[k] for k in ("feasible_share", "lcoh_eur_per_mwh",
                                                 "net_electricity_gwh")})
    RUNS.mkdir(exist_ok=True)
    result["daily"].to_csv(RUNS / "hand_picked_daily.csv", index=False)
    with open(RUNS / "hand_picked_result.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nSaved to {RUNS}")


if __name__ == "__main__":
    main()
