"""Run one external-optimiser case and write JSON to outputs_opt/.

    python run_optimizers.py dftr_final | dftr_from2500 | cobyla_final | stosag_robust | robust_nominal
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from gemini_design_agent.demand import load_demand  # noqa: E402
from gemini_design_agent.optimize_ext import (DesignProblem, make_ensemble, robustness_check,  # noqa: E402
                                              run_petlab_backend, run_stosag)

OUT = ROOT / "outputs_opt"
OUT.mkdir(exist_ok=True)
X_FINAL = [3500.0, 2.5, 10.0, 0.0, 1000.0, 170.0]        # agent's selected design (3 doublets)
X_2500 = [2500.0, 31.5, 10.0, 10.0, 800.0, 220.0]        # as-specified depth baseline (3 doublets)


def main(case: str):
    demand = load_demand(ROOT.parent / "GEMINI_Heating_Demand_Daily_2027.csv",
                         ROOT.parent / "GEMINI_Cooling_Demand_Daily_2027.csv")
    log = lambda m: print(m, flush=True)  # noqa: E731
    t0 = time.time()
    if case == "dftr_final":
        p = DesignProblem(demand, 3, day_stride=2, log=log)
        p.checkpoint = OUT / f"{case}_history.json"
        res = run_petlab_backend(p, X_FINAL, "DFTR", max_iter=40, budget=220)
        res["history"] = p.history
    elif case == "dftr_from2500":
        p = DesignProblem(demand, 3, day_stride=2, log=log)
        p.checkpoint = OUT / f"{case}_history.json"
        res = run_petlab_backend(p, X_2500, "DFTR", max_iter=40, budget=220)
        res["history"] = p.history
    elif case == "cobyla_final":
        p = DesignProblem(demand, 3, day_stride=2, log=log)
        p.checkpoint = OUT / f"{case}_history.json"
        res = run_petlab_backend(p, X_FINAL, "COBYLA", max_iter=200, budget=180)
        res["history"] = p.history
    elif case == "stosag_robust":
        ens = make_ensemble(6)
        res = run_stosag(demand, 3, X_FINAL, ens, max_iter=8, day_stride=3, log=log)
    elif case == "robust_nominal":
        ens = make_ensemble(6)
        res = {"backend": "nominal-check", **robustness_check(demand, 3, X_FINAL, ens, day_stride=3)}
    else:
        raise SystemExit(__doc__)
    res["case"] = case
    res["elapsed_total_s"] = time.time() - t0
    (OUT / f"{case}.json").write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    print(f"done {case} in {time.time() - t0:.0f} s -> {OUT / (case + '.json')}")


if __name__ == "__main__":
    main(sys.argv[1])
