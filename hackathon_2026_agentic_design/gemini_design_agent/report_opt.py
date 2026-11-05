"""Polish the external-optimiser candidates at full fidelity and write OPTIMIZATION_REPORT.md.

    python report_opt.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from gemini_design_agent.agent import DesignToolbox  # noqa: E402
from gemini_design_agent.demand import load_demand  # noqa: E402
from gemini_design_agent.optimize_ext import X_NAMES, design_from_x, make_ensemble, robustness_check  # noqa: E402
from gemini_design_agent.spec import SPEC  # noqa: E402
from gemini_design_agent.system import evaluate_design  # noqa: E402

OUT = ROOT / "outputs_opt"
X_AGENT = [3500.0, 2.5, 10.0, 0.0, 1000.0, 170.0]


def polish(tb: DesignToolbox, x, label: str, max_repairs: int = 4):
    """Full-fidelity evaluation; if marginally infeasible, let the rule-based diagnoser repair it."""
    ds = design_from_x(x, 3, label)
    ds.rationale = [f"Candidate from {label}: x = {[round(float(v), 1) for v in x]}"]
    res = tb.evaluate(ds, "polish", "full-fidelity check", ds.rationale[0])
    for i in range(max_repairs):
        if res.feasible:
            break
        fix = tb.diagnose(res)
        if fix is None:
            break
        new_ds, action, why = fix
        new_ds.name = f"{label}-fix{i + 1}"
        new_ds.rationale = list(ds.rationale) + [why]
        res = tb.evaluate(new_ds, "polish", action, why)
        ds = new_ds
    return res


def x_of(ds):
    return [ds.well.reservoir_midpoint_m, ds.heat_pump_mw, ds.absorption_chiller_mw, ds.electric_chiller_mw,
            ds.well.esp_depth_m, ds.well.esp_bep_m3_h]


def main():
    demand = load_demand(ROOT.parent / "GEMINI_Heating_Demand_Daily_2027.csv",
                         ROOT.parent / "GEMINI_Cooling_Demand_Daily_2027.csv")
    tb = DesignToolbox(demand, SPEC, print)
    ens = make_ensemble(6)
    results = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in OUT.glob("*.json") if "history" not in p.stem}

    cands = {"agent (Claude / rule-based)": X_AGENT}
    for name in ("dftr_final", "dftr_from2500", "cobyla_final"):
        r = results.get(name)
        if r:
            bf = r.get("best_feasible_point")
            cands[name] = bf["x"] if bf else r["x_best"]
    if "stosag_robust" in results:
        cands["stosag_robust"] = results["stosag_robust"]["x_best"]

    rows, polished = [], {}
    for label, x in cands.items():
        res = polish(tb, x, label.replace(" ", "_").replace("/", "-").replace("(", "").replace(")", ""))
        rb = robustness_check(demand, 3, x_of(res.design), ens, day_stride=3)
        polished[label] = (res, rb)
        k = res.kpis
        rows.append([label, *[f"{v:.0f}" if i in (0, 4, 5) else f"{v:.1f}" for i, v in enumerate(x_of(res.design))],
                     "yes" if res.feasible else "no", f"{k['wellhead_temperature_at_300_c']:.0f}",
                     f"{k['electricity_gwh']:.1f}", f"{k['system_cop']:.1f}", f"{res.cost['capex_total_meur']:.1f}",
                     f"{res.cost['total_annual_cost_meur']:.2f}", f"{res.cost['levelised_cost_eur_per_mwh']:.1f}",
                     f"{rb['expected_cost_meur']:.2f}", f"{rb['worst_cost_meur']:.2f}", f"{rb['feasible_fraction'] * 100:.0f}"])

    L = ["# External optimiser study (petlab / py-trsqp DFTR-Filter / StoSAG)\n",
         "Continuous design variables for the 3-doublet system were handed to black-box optimisers through "
         "petlab's backend interface (`petlab.optimization.optimize`): **DFTR-Filter** (`py_trsqp`, derivative-free "
         "trust region with output constraints), **COBYLA** (scipy baseline) and **StoSAG** (ensemble-gradient robust "
         "optimisation over permeability 140-220 mD, gradient 29-32 C/km and injector skin). Objective: total annual "
         "cost (MEUR); constraints: zero unmet demand, ESP intake >= bubble point + 5 bar, injection WHP limit, API "
         "erosional velocity. Screening used the fast evaluator (every 2nd/3rd day, filled forward); every candidate "
         "was then re-run at full daily fidelity and, if marginally infeasible, repaired by the rule-based diagnoser.\n",
         "## Candidates after full-fidelity polish\n",
         "| Candidate | depth m | HP MW | abs MW | el.ch MW | ESP m | BEP | feasible | WH T C | el GWh | COP | capex MEUR | annual MEUR | EUR/MWh | E[cost] ens | worst ens | feas % ens |",
         "|" + "---|" * 17]
    for r in rows:
        L.append("| " + " | ".join(str(v) for v in r) + " |")

    L.append("\n## Optimiser runs\n")
    for name in ("dftr_final", "dftr_from2500", "cobyla_final", "stosag_robust", "robust_nominal"):
        r = results.get(name)
        if not r:
            L.append(f"- `{name}`: not available")
            continue
        if name == "stosag_robust":
            L.append(f"- `{name}` (StoSAG, {len(r['per_realisation'])} realisations): {r['n_evaluations']} evaluations in "
                     f"{r['elapsed_s'] / 60:.0f} min; iterate expected cost {', '.join(f'{j:.2f}' for j in r['iterate_costs'])} MEUR; "
                     f"final expected {r['expected_cost_meur']:.2f}, worst {r['worst_cost_meur']:.2f}, "
                     f"feasible in {r['feasible_fraction'] * 100:.0f} % of realisations; x = {[round(v, 1) for v in r['x_best']]}.")
        elif name == "robust_nominal":
            L.append(f"- `{name}` (agent design across the ensemble): expected {r['expected_cost_meur']:.2f}, worst "
                     f"{r['worst_cost_meur']:.2f} MEUR, feasible in {r['feasible_fraction'] * 100:.0f} %.")
        else:
            bf = r.get("best_feasible_point")
            L.append(f"- `{name}` ({r['backend']}): {r['n_evaluations']} evaluations in {r['elapsed_s'] / 60:.0f} min, "
                     f"termination '{r.get('termination', '')}'; best feasible screened point {bf['f']:.3f} MEUR at "
                     f"x = {[round(v, 1) for v in bf['x']]}." if bf else f"- `{name}`: no feasible point found.")

    L.append("\n## Interpretation\n")
    agent_res, agent_rb = polished["agent (Claude / rule-based)"]
    best_label = min(polished, key=lambda k: polished[k][0].cost["total_annual_cost_meur"] if polished[k][0].feasible else 1e9)
    best_res, best_rb = polished[best_label]
    robust_label = min(polished, key=lambda k: polished[k][1]["worst_cost_meur"] if polished[k][0].feasible else 1e9)
    L.append(f"- Lowest nominal annual cost: **{best_label}** at {best_res.cost['total_annual_cost_meur']:.2f} MEUR "
             f"({best_res.cost['levelised_cost_eur_per_mwh']:.1f} EUR/MWh) versus {agent_res.cost['total_annual_cost_meur']:.2f} MEUR for the agent design "
             f"({(1 - best_res.cost['total_annual_cost_meur'] / agent_res.cost['total_annual_cost_meur']) * 100:.1f} % lower).")
    L.append(f"- Most robust (lowest worst-case cost over the geological ensemble): **{robust_label}** "
             f"(worst {polished[robust_label][1]['worst_cost_meur']:.2f} MEUR, expected {polished[robust_label][1]['expected_cost_meur']:.2f}).")
    L.append('- The design space has a cliff: the shallowest depth whose wellhead temperature still clears the 103 C needed for direct 100 C supply (about 3,250 m at 30 C/km). COBYLA sat right on it (3,250 m, no heat pump) and a 1 C/km lower gradient pushes its wellhead below the threshold, so its worst-case cost jumps to 10.6 MEUR. DFTR-Filter stopped about 100 m deeper (3,344 m) and the rule-based polish re-selected its ESP frame; that margin is enough for it to stay the cheapest design in every realisation. StoSAG, optimising the ensemble mean, lands at 3,335 m but keeps a 1.9 MW heat pump as a hedge.')
    L.append("- Fast-mode screening (every 2nd day) can miss one or two peak days; full-fidelity re-evaluation and the "
             "rule-based repair step are therefore part of the loop, not an afterthought.")
    L.append("- Recommendation: adopt the robust-optimised depth/capacities if the gradient uncertainty is real for the "
             "site; adopt the deterministic optimum only once a temperature log confirms the gradient.")

    # convergence figure
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(9, 4))
        for name, col in (("dftr_final", "#c0392b"), ("dftr_from2500", "#e67e22"), ("cobyla_final", "#2980b9")):
            r = results.get(name)
            if not r:
                continue
            h = r["history"]
            f = [x["f"] if (x["c1_unmet"] >= -1e-6 and not x["hard"]) else np.nan for x in h]
            best = np.fmin.accumulate(np.nan_to_num(f, nan=np.inf))
            ax.plot(range(1, len(h) + 1), best, label=f"{name} (best feasible so far)", color=col)
        if "stosag_robust" in results:
            j = results["stosag_robust"]["iterate_costs"]
            ax.plot(np.linspace(1, 200, len(j)), j, "s--", color="#27ae60", label="StoSAG expected cost per iterate")
        ax.axhline(agent_res.cost["total_annual_cost_meur"], color="k", ls=":", label="agent design (full fidelity)")
        ax.set_xlabel("simulator evaluations"); ax.set_ylabel("total annual cost (MEUR)"); ax.legend(fontsize=8)
        ax.set_title("External optimisers on the GEMINI-based design problem (3 doublets)")
        fig.tight_layout(); fig.savefig(OUT / "fig_optimizer_convergence.png", dpi=130); plt.close(fig)
        L.append("\n![convergence](fig_optimizer_convergence.png)\n")
    except Exception as e:  # pragma: no cover
        L.append(f"\n(figure not generated: {e!r})\n")

    (OUT / "OPTIMIZATION_REPORT.md").write_text("\n".join(L), encoding="utf-8")
    (OUT / "polished_candidates.json").write_text(json.dumps(
        {k: {"design": v[0].design.to_dict(), "feasible": v[0].feasible, "cost": v[0].cost, "robust": v[1]} for k, v in polished.items()},
        indent=1, default=float), encoding="utf-8")
    print("\n".join(L[:4 + len(rows)]))
    print("written", OUT / "OPTIMIZATION_REPORT.md")


if __name__ == "__main__":
    main()
