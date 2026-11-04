"""Command-line entry point.

    python -m gemini_design_agent run --heating ../GEMINI_Heating_Demand_Daily_2027.csv \
        --cooling ../GEMINI_Cooling_Demand_Daily_2027.csv --out outputs [--mode rule|claude|auto] \
        [--years 25] [--no-explore] [--no-closed-loop]
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .agent import make_agent
from .closed_loop import GeothermalManagementLoop, ReservoirThermalModel
from .demand import load_demand
from .report import write_report
from .spec import SPEC


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="gemini_design_agent")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run the agentic design workflow")
    r.add_argument("--heating", required=True)
    r.add_argument("--cooling", required=True)
    r.add_argument("--out", default="outputs")
    r.add_argument("--mode", default="auto", choices=["auto", "rule", "claude"])
    r.add_argument("--years", type=int, default=25, help="closed-loop management horizon (0 = skip)")
    r.add_argument("--spacing", type=float, default=1500.0, help="assumed producer-injector spacing at reservoir level (m)")
    r.add_argument("--no-explore", action="store_true", help="skip the alternative-exploration phase")
    r.add_argument("--no-closed-loop", action="store_true")
    a = ap.parse_args(argv)

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    log_lines: list[str] = []

    def log(msg: str):
        print(msg, flush=True)
        log_lines.append(msg)

    t0 = time.time()
    # intake gate: refuse to run on incomplete inputs (evidence for the committee: demo_interactions.py)
    from .intake import check_request
    rep = check_request({"heating_demand_csv": a.heating, "cooling_demand_csv": a.cooling,
                         "supply_temperature_heating_c": SPEC.constraints.heating_supply_temperature_c,
                         "supply_temperature_cooling_c": SPEC.constraints.cooling_supply_temperature_c,
                         "reservoir_depth_m": SPEC.reservoir.midpoint_depth_m, "geothermal_gradient_c_per_km": SPEC.reservoir.geothermal_gradient_c_per_km,
                         "reservoir_pressure_bar": SPEC.reservoir.pressure_bar_g, "permeability_md": SPEC.reservoir.permeability_md,
                         "brine_glr_nm3_per_m3": SPEC.brine.glr_nm3_per_m3}, "design the geothermal heating and cooling system")
    for line in rep.markdown().splitlines():
        log("[intake] " + line)
    if rep.status != "ok":
        return 2
    demand = load_demand(a.heating, a.cooling)
    agent = make_agent(demand, SPEC, log, mode=("rule" if a.mode == "rule" else a.mode), explore=not a.no_explore)
    mode_name = type(agent).__name__.replace("DesignAgent", "").lower() or "rule-based"
    log(f"Agent: {type(agent).__name__}")
    run = agent.run()
    final = run["final"]
    log(f"\nFinal design: {final.design.name}  feasible={final.feasible}  "
        f"annual cost {final.cost['total_annual_cost_meur']:.2f} MEUR  LCOE {final.cost['levelised_cost_eur_per_mwh']:.1f} EUR/MWh")

    closed = None
    if not a.no_closed_loop and a.years > 0:
        loop = GeothermalManagementLoop(final.design, demand, SPEC, years=a.years,
                                        thermal=ReservoirThermalModel(well_spacing_m=a.spacing,
                                                                      thickness_m=SPEC.reservoir.gross_thickness_m), log=log)
        closed = loop.run(year1_result=final)

    path = write_report(run, closed, demand.summary(), out, SPEC, mode=mode_name)
    (out / "agent_log.txt").write_text("\n".join(log_lines), encoding="utf-8")
    log(f"\nReport written to {path}  ({time.time() - t0:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
