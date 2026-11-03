"""Evaluate one hand-picked design over 365 days and print KPIs and violations.

Run from the repo root:
    PYTHONPATH=. python hackathon/run_design.py
"""

import json
from pathlib import Path

from hackathon.models.dispatch import Design, evaluate_design, summarize
from hackathon.models.surface import SurfaceParams

RUNS = Path(__file__).parent / "runs"


def main():
    design = Design(
        depth_m=2500,
        n_doublets=2,
        max_flow_m3h=300,
        outage="staggered",
        surface=SurfaceParams(
            hp_capacity_mw=15,
            chiller_type="absorption_single_effect",
            sorption_capacity_mw=8,
            elec_chiller_capacity_mw=6,
            boiler_capacity_mw=10,
        ),
    )
    result = evaluate_design(design)
    print(summarize(result))
    RUNS.mkdir(exist_ok=True)
    result["daily"].to_csv(RUNS / "hand_picked_daily.csv", index=False)
    with open(RUNS / "hand_picked_result.json", "w", encoding="utf-8") as f:
        json.dump({k: result[k] for k in ("design", "kpis", "violations")}, f, indent=2,
                  default=str)
    print(f"\nSaved daily table and result to {RUNS}")


if __name__ == "__main__":
    main()
