"""Interactive orchestration driver: Claude (in Claude Code) calls the design toolbox step by step.

State is pickled between calls so each command is one engineering action with its rationale.

    python claude_session.py context
    python claude_session.py build  <name> <n_doublets> <depth_m> <absorption|electric|hybrid> "<rationale>"
    python claude_session.py modify <source> <new_name> '<json changes>' "<rationale>"
    python claude_session.py suggest <name>
    python claude_session.py rank
    python claude_session.py finalize <name> "<summary>" [--years 25]
"""

from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from gemini_design_agent.agent import DesignToolbox, AgentStep, _kpi_subset  # noqa: E402
from gemini_design_agent.closed_loop import GeothermalManagementLoop  # noqa: E402
from gemini_design_agent.demand import load_demand  # noqa: E402
from gemini_design_agent.report import write_report  # noqa: E402
from gemini_design_agent.spec import SPEC  # noqa: E402

OUT = ROOT / "outputs_claude"
STATE = OUT / "session.pkl"
LOG = OUT / "orchestration_log.md"


def log(msg: str):
    print(msg, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(msg + "\n")


def load_tb() -> DesignToolbox:
    if STATE.exists():
        with STATE.open("rb") as f:
            tb = pickle.load(f)
        tb.log = log
        return tb
    demand = load_demand(ROOT.parent / "GEMINI_Heating_Demand_Daily_2027.csv",
                         ROOT.parent / "GEMINI_Cooling_Demand_Daily_2027.csv")
    return DesignToolbox(demand, SPEC, log)


def save_tb(tb: DesignToolbox):
    tb.log = None
    with STATE.open("wb") as f:
        pickle.dump(tb, f)
    tb.log = log


def show(res):
    s = res.summary()
    print(json.dumps({"name": s["name"], "feasible": s["feasible"],
                      "violations": [(v["code"], v["severity"], v["days"], round(v["worst_value"], 2)) for v in s["violations"]],
                      "kpis": _kpi_subset(s["kpis"]),
                      "cost": {k: round(v, 2) for k, v in s["cost"].items()}}, indent=1, default=float))


def main(argv):
    OUT.mkdir(exist_ok=True)
    cmd, args = argv[0], argv[1:]
    tb = load_tb()
    if cmd == "context":
        print(json.dumps({"spec": SPEC.to_dict(), "demand": tb.dsum}, indent=1, default=float))
        return
    if cmd == "build":
        name, n, depth, cooling, why = args[0], int(args[1]), float(args[2]), args[3], args[4]
        ds = tb.archetype(name, n, depth, cooling)
        ds.rationale = [why] + ds.rationale
        log(f"\n### Claude: build `{name}`\n{why}\n")
        show(tb.evaluate(ds, "claude", "build candidate", why))
    elif cmd == "modify":
        src, new, changes, why = args[0], args[1], json.loads(args[2]), args[3]
        ds = tb.results[src].design.copy(name=new, **changes)
        ds.rationale = list(tb.results[src].design.rationale) + [why]
        log(f"\n### Claude: modify `{src}` -> `{new}` {changes}\n{why}\n")
        show(tb.evaluate(ds, "claude", f"modify {list(changes)}", why))
    elif cmd == "suggest":
        fix = tb.diagnose(tb.results[args[0]])
        print("no suggestion" if fix is None else json.dumps({"action": fix[1], "rationale": fix[2]}, indent=1))
    elif cmd == "rank":
        for r in tb.rank():
            print(f"{r.design.name:<40} annual {r.cost['total_annual_cost_meur']:.2f} MEUR  LCOE {r.cost['levelised_cost_eur_per_mwh']:.1f}  "
                  f"COP {r.kpis['system_cop']:.1f}  el {r.kpis['electricity_gwh']:.1f} GWh  geo {r.kpis['geothermal_share'] * 100:.0f}%")
    elif cmd == "finalize":
        name, summary = args[0], args[1]
        years = int(args[args.index("--years") + 1]) if "--years" in args else 25
        final = tb.results[name]
        log(f"\n### Claude: finalize `{name}`\n{summary}\n")
        tb.steps.append(AgentStep(len(tb.steps) + 1, "claude", "finalize", summary, name, final.feasible))
        closed = GeothermalManagementLoop(final.design, tb.demand, SPEC, years=years, log=log).run(year1_result=final) if years else None
        run = {"final": final, "ranked": tb.rank(), "steps": tb.steps, "results": tb.results}
        path = write_report(run, closed, tb.dsum, OUT, SPEC, mode="Claude (Claude Code session orchestrating the toolbox)")
        print(f"report: {path}")
    else:
        raise SystemExit(__doc__)
    save_tb(tb)


if __name__ == "__main__":
    main(sys.argv[1:])
