"""Design search: compare 1/2/3 doublets x HEX size x ESP stages.

Every candidate is simulated for the full year (365 days, 330 geothermal)
and checked by the independent validator.  Infeasible candidates are
rejected; the feasible one with the lowest annual CO2 is selected.
A sensitivity study on the selected design follows.

Outputs: design_comparison.csv, sensitivity.csv, best_design.json
Run:     python optimize_design.py
"""

import itertools
import json
import time
from dataclasses import asdict, replace
from pathlib import Path

import pandas as pd

from plant_model import Assumptions, Design
from dispatch import Plant, load_demand, summarize, validate

HERE = Path(__file__).resolve().parent

N_DOUBLETS = (1, 2, 3)
HEX_UA = (100e3, 200e3, 400e3, 800e3, 1600e3)     # W/K per doublet
ESP_STAGES = (30, 40, 60)


def evaluate(design, a, dates, H, C):
    df = Plant(design, a).simulate_year(dates, H, C)
    s = summarize(df, design)
    checks = validate(df, design)
    s["feasible"] = all(ok for _, ok, _ in checks)
    s["failed_checks"] = "; ".join(n for n, ok, _ in checks if not ok)
    return s


def main():
    dates, H, C = load_demand(HERE)
    a = Assumptions()
    t0 = time.time()
    rows = []
    grid = list(itertools.product(N_DOUBLETS, HEX_UA, ESP_STAGES))
    for k, (n, ua, st) in enumerate(grid, 1):
        d = Design(n_doublets=n, hex_ua_w_per_k=ua, esp_stages=st)
        s = evaluate(d, a, dates, H, C)
        rows.append(s)
        print(f"[{k:2d}/{len(grid)}] {d.label():32s} CO2 {s['co2_t_per_year']:9.1f} t  "
              f"backup {s['backup_boiler_share_pct']:5.1f}%  {'OK' if s['feasible'] else 'REJECT ' + s['failed_checks']}")
    comp = pd.DataFrame(rows).sort_values("co2_t_per_year")
    comp.to_csv(HERE / "design_comparison.csv", index=False)

    feas = comp[comp.feasible]
    best_row = feas.iloc[0]
    best = Design(n_doublets=int(best_row.n_doublets), hex_ua_w_per_k=best_row.hex_ua_kW_per_K * 1e3,
                  esp_stages=int(best_row.esp_stages))
    print(f"\nBest feasible design: {best.label()}  ->  {best_row.co2_t_per_year:.1f} t CO2/yr")
    for n in N_DOUBLETS:
        b = feas[feas.n_doublets == n]
        if len(b):
            print(f"  best with {n} doublet(s): {b.iloc[0].design:32s} {b.iloc[0].co2_t_per_year:9.1f} t")

    # ── sensitivity on the selected design ──
    sens = []
    cases = [("t_return", v) for v in (35.0, 40.0, 45.0, 50.0)] + \
            [("eta_lorenz", v) for v in (0.40, 0.50, 0.60)] + \
            [("cop_electric_chiller", v) for v in (3.0, 4.0, 5.0)] + \
            [("grid_ef_kg_per_kwh", v) for v in (0.10, 0.30, 0.50)]
    for param, val in cases:
        s = evaluate(best, replace(a, **{param: val}), dates, H, C)
        sens.append(dict(parameter=param, value=val, co2_t_per_year=s["co2_t_per_year"],
                         backup_boiler_share_pct=s["backup_boiler_share_pct"],
                         geothermal_chain_share_pct=s["geothermal_chain_share_pct"],
                         net_electricity_MWh=s["net_electricity_MWh"], feasible=s["feasible"]))
        print(f"  sensitivity {param}={val}: CO2 {s['co2_t_per_year']:.1f} t  feasible={s['feasible']}")
    pd.DataFrame(sens).to_csv(HERE / "sensitivity.csv", index=False)

    (HERE / "best_design.json").write_text(json.dumps(
        {"design": asdict(best), "assumptions": asdict(a),
         "co2_t_per_year": float(best_row.co2_t_per_year)}, indent=2))
    print(f"\nDone in {time.time() - t0:.0f}s -> design_comparison.csv, sensitivity.csv, best_design.json")


if __name__ == "__main__":
    main()
