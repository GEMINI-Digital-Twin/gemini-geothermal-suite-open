"""Run the recommended design for 365 days and save the full calculation.

Run from the repo root:
    PYTHONPATH=. python hackathon/run_design.py            # deterministic run
    PYTHONPATH=. python hackathon/run_design.py --robust   # plus P10/P50/P90 and return-temperature sensitivity

Output goes to hackathon/results/ (kept in git):
    recommended_design.json  design, KPIs, CAPEX/OPEX breakdown, violations,
                             and with --robust the P10/P50/P90 and the sensitivity
    recommended_daily.csv    all 365 days: demand and what each piece of equipment supplies
"""

import argparse
import json
from pathlib import Path

from hackathon.models.dispatch import Design, evaluate_design, summarize
from hackathon.models.robustness import return_temperature_sensitivity, run_robustness
from hackathon.models.surface import SurfaceParams

RESULTS = Path(__file__).parent / "results"

# Recommended design: 2 doublets at 3300 m. The 15 MW boiler and 4 MW electric chiller are
# backup; the boiler covers the peak day with one doublet out.
RECOMMENDED = Design(
    depth_m=3300, n_doublets=2, spacing_m=1600, max_flow_m3h=300, outage="staggered",
    surface=SurfaceParams(hp_capacity_mw=4, chiller_type="absorption_dh", sorption_capacity_mw=10,
                          elec_chiller_capacity_mw=4, boiler_capacity_mw=15),
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--robust", action="store_true")
    ap.add_argument("--samples", type=int, default=100)
    a = ap.parse_args()
    result = evaluate_design(RECOMMENDED)
    print(summarize(result))
    print("CAPEX (M EUR):", result["economics"]["capex_meur"])
    out = {k: result[k] for k in ("design", "kpis", "economics", "violations")}
    if a.robust:
        rb = run_robustness(RECOMMENDED, n_samples=a.samples)
        out["robustness"] = rb
        out["return_temperature_sensitivity"] = return_temperature_sensitivity(RECOMMENDED)
        print("Robustness:", {k: rb[k] for k in ("feasible_share", "lcoh_eur_per_mwh", "co2_total_kt")})
    RESULTS.mkdir(exist_ok=True)
    result["daily"].to_csv(RESULTS / "recommended_daily.csv", index=False)
    with open(RESULTS / "recommended_design.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nSaved to {RESULTS}")


if __name__ == "__main__":
    main()
