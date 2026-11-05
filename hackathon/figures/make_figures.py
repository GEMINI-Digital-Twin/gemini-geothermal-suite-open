"""Slide figures (PNG) from our models and the agent run logs. Adds no values of its own.

Run from the repo root:
    PYTHONPATH=. python -m hackathon.figures.make_figures            # all figures
    PYTHONPATH=. python -m hackathon.figures.make_figures --only demand dispatch

Figures (written to hackathon/figures/out/):
    fig_demand.png       daily heating and cooling demand (organisers' data)        -> slide 2
    fig_dispatch.png     365-day supply by equipment, recommended design             -> slide 8
    fig_energy_split.png annual heat and cooling by source, recommended design       -> slide 8
    fig_cost_co2.png     LCOH vs CO2 of every feasible design (agent runs + ours)    -> slide 9
    fig_runs.png         agent runs: calls, model time, prompt tokens                -> slide 7
"""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from hackathon.models.config import load_config  # noqa: E402
from hackathon.models.dispatch import Design, evaluate_design, load_demand  # noqa: E402
from hackathon.models.surface import SurfaceParams  # noqa: E402

HACK = Path(__file__).resolve().parents[1]
OUT = HACK / "figures" / "out"
RUNS = HACK / "runs"

# Agent runs to show (label -> run folder). Run 5 is the newest folder unless given with --run5.
AGENT_RUNS = {"Run 2": "20261104_192033", "Run 3": "20261105_083545", "Run 4": "20261105_092244"}

# Owner's choices for the slides (designs evaluated with the same tools as the agent).
RECOMMENDED = ("2 x 3300 m (recommended)", dict(
    depth_m=3300, n_doublets=2, spacing_m=1600, hp_capacity_mw=4, chiller_type="absorption_dh",
    sorption_capacity_mw=10, elec_chiller_capacity_mw=4, boiler_capacity_mw=10))
REFERENCES = [
    RECOMMENDED,
    ("2 x 2500 m + HP 15", dict(depth_m=2500, n_doublets=2, spacing_m=1600, hp_capacity_mw=15,
                                chiller_type="absorption_dh", sorption_capacity_mw=10,
                                elec_chiller_capacity_mw=4, boiler_capacity_mw=10)),
    ("1 x 2500 m + gas boiler", dict(depth_m=2500, n_doublets=1, spacing_m=1600, hp_capacity_mw=30,
                                     chiller_type="absorption_dh", sorption_capacity_mw=10,
                                     elec_chiller_capacity_mw=10, boiler_capacity_mw=15)),
]

# Reference palette (dataviz skill, light mode), categorical slots in fixed order.
C = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"

plt.rcParams.update({
    "figure.dpi": 200, "font.size": 11, "axes.edgecolor": INK2, "axes.labelcolor": INK2,
    "xtick.color": INK2, "ytick.color": INK2, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
    "legend.frameon": False, "axes.titleweight": "bold", "axes.titlesize": 13, "axes.titlecolor": INK,
})

SURFACE_KEYS = {"hp_capacity_mw", "chiller_type", "sorption_capacity_mw", "elec_chiller_capacity_mw",
                "boiler_capacity_mw"}
DESIGN_KEYS = {"depth_m", "n_doublets", "spacing_m", "max_flow_m3h", "outage", "heating_return_c"}


def make_design(args):
    """Same mapping as the agent's evaluate_design tool (unknown keys such as label are ignored)."""
    d = {k: v for k, v in args.items() if k in DESIGN_KEYS}
    s = {k: v for k, v in args.items() if k in SURFACE_KEYS}
    d["n_doublets"] = int(d["n_doublets"])
    return Design(surface=SurfaceParams(**s), **d)


def in_range(args, cfg):
    dv = cfg.raw["design_variables"]
    checks = [("depth_m", "well_depth_m"), ("n_doublets", "n_doublets"),
              ("max_flow_m3h", "flow_m3h_per_doublet"), ("spacing_m", "well_spacing_m")]
    return all(args.get(a) is None or dv[k][0] <= args[a] <= dv[k][1] for a, k in checks)


def save(fig, name):
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / name, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote", OUT / name)


def fig_demand(cfg):
    d = load_demand(cfg)
    fig, ax = plt.subplots(figsize=(10, 3.6))
    ax.plot(d.date, d.heat_mw, color=C[1], lw=2, label=f"Heating, 100 C supply ({d.heat_mw.sum() * 24 / 1000:.1f} GWh)")
    ax.plot(d.date, d.cool_mw, color=C[0], lw=2, label=f"Cooling, 20 C supply ({d.cool_mw.sum() * 24 / 1000:.1f} GWh)")
    ax.set_ylabel("Daily mean demand (MW)")
    ax.set_title("Daily heating and cooling demand", loc="left")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=2)
    ax.text(0, -0.32, "Source: hackathon demand data (organisers)", transform=ax.transAxes, color=INK2, fontsize=9)
    save(fig, "fig_demand.png")


def fig_dispatch_and_split(cfg):
    name, args = RECOMMENDED
    r = evaluate_design(make_design(args))
    d, k = r["daily"], r["kpis"]
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True, gridspec_kw={"height_ratios": [3, 2]})
    heat = [("Direct (geothermal HX)", d.heat_direct, C[0]), ("Heat pump", d.heat_hp, C[1]),
            ("CHP (associated gas)", d.heat_chp, C[2]), ("Gas boiler", d.heat_boiler_ng, C[3])]
    a1.stackplot(d.date, *[h[1] for h in heat], colors=[h[2] for h in heat], labels=[h[0] for h in heat],
                 edgecolor="white", linewidth=0.3)
    a1.plot(d.date, d.heat_demand_mw, color=INK, lw=1.2, label="Demand")
    a1.set_ylabel("Heating (MW)")
    a1.set_title(f"{name}: supply on all 365 days", loc="left")
    a1.legend(loc="upper center", bbox_to_anchor=(0.5, -0.04), ncol=5, fontsize=9)
    cool = [("Absorption (geothermal)", d.cool_sorption, C[0]), ("Electric chiller", d.cool_electric, C[1])]
    a2.stackplot(d.date, *[c[1] for c in cool], colors=[c[2] for c in cool], labels=[c[0] for c in cool],
                 edgecolor="white", linewidth=0.3)
    a2.plot(d.date, d.cool_demand_mw, color=INK, lw=1.2, label="Demand")
    a2.set_ylabel("Cooling (MW)")
    a2.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=3, fontsize=9)
    fig.subplots_adjust(hspace=0.35)
    save(fig, "fig_dispatch.png")

    fig, ax = plt.subplots(figsize=(7, 3.2))
    rows = [("Heating", [k["heat_direct_gwh"], k["heat_hp_gwh"], k["heat_chp_gwh"], k["heat_boiler_ng_gwh"]],
             ["Direct", "Heat pump", "CHP", "Gas boiler"]),
            ("Cooling", [k["cool_sorption_gwh"], k["cool_electric_gwh"]], ["Absorption", "Electric"])]
    for y, (lab, vals, names) in enumerate(rows):
        left = 0
        for i, (v, n) in enumerate(zip(vals, names)):
            ax.barh(y, v, left=left, color=C[i], height=0.55, edgecolor="white", linewidth=2,
                    label=f"{lab}: {n} {v:.1f}")
            if v > 15:  # label wide segments in place; all values are in the legend
                ax.text(left + v / 2, y, f"{n} {v:.1f}", ha="center", va="center", color="white", fontsize=9)
            left += v
    ax.set_yticks([0, 1], ["Heating", "Cooling"])
    ax.invert_yaxis()
    ax.set_xlabel("GWh per year")
    ax.set_title(f"Annual supply by source, {name}", loc="left", fontsize=11)
    ax.grid(axis="y", visible=False)
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1), fontsize=8)
    save(fig, "fig_energy_split.png")


def agent_candidates(run_dirs, cfg):
    """Every distinct in-range evaluate_design call the agent made, re-evaluated with current models."""
    out = {}
    for label, folder in run_dirs.items():
        log = RUNS / folder / "llm_log.jsonl"
        if not log.exists():
            print("skip (no log):", log)
            continue
        for line in open(log, encoding="utf-8"):
            for tc in json.loads(line)["response"].get("tool_calls") or []:
                if tc["function"]["name"] != "evaluate_design":
                    continue
                try:
                    a = json.loads(tc["function"]["arguments"] or "{}")
                except json.JSONDecodeError:
                    continue
                a = {k: v for k, v in a.items() if k != "label"}
                key = json.dumps(a, sort_keys=True)
                if key not in out and in_range(a, cfg) and "depth_m" in a and "n_doublets" in a:
                    out[key] = (label, a)
    return list(out.values())


def fig_cost_co2(cfg, run_dirs):
    pts = []
    for label, a in agent_candidates(run_dirs, cfg):
        r = evaluate_design(make_design(a))
        if not any(v["severity"] == "hard" for v in r["violations"]):
            pts.append(("Agent runs (feasible designs)", label, r["kpis"]))
    for name, a in REFERENCES:
        pts.append(("Our exploration", name, evaluate_design(make_design(a))["kpis"]))
    fig, ax = plt.subplots(figsize=(8, 4.8))
    for i, group in enumerate(["Agent runs (feasible designs)", "Our exploration"]):
        g = [p for p in pts if p[0] == group]
        ax.scatter([p[2]["co2_total_kt"] for p in g], [p[2]["lcoh_eur_per_mwh"] for p in g], s=70, color=C[i],
                   edgecolor="white", linewidth=1.5, label=f"{group} ({len(g)})", zorder=3)
    for _, name, k in [p for p in pts if p[0] == "Our exploration"]:
        ax.annotate(name, (k["co2_total_kt"], k["lcoh_eur_per_mwh"]), textcoords="offset points",
                    xytext=(8, 8), fontsize=9, color=INK)
    ax.set_xlabel("CO2 (kt per year): grid electricity + gas boiler + associated gas")
    ax.set_ylabel("LCOH (EUR/MWh, base case)")
    ax.set_title("Cost vs CO2 of every feasible design evaluated", loc="left")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=2)
    save(fig, "fig_cost_co2.png")
    with open(OUT / "cost_co2_points.json", "w", encoding="utf-8") as f:
        json.dump([{"group": g, "name": n, "lcoh": k["lcoh_eur_per_mwh"], "co2_kt": k["co2_total_kt"]}
                   for g, n, k in pts], f, indent=1)


def fig_runs(run_dirs):
    llm = __import__("yaml").safe_load(open(HACK / "agent" / "llm_config.yaml"))["routes"]["api"]
    rows = []
    for label, folder in run_dirs.items():
        log = RUNS / folder / "llm_log.jsonl"
        if not log.exists():
            continue
        recs = [json.loads(l) for l in open(log, encoding="utf-8")]
        pin = sum(r["usage"]["prompt_tokens"] for r in recs)
        pout = sum(r["usage"]["completion_tokens"] for r in recs)
        final = RUNS / folder / "final_design.json"
        rows.append({"run": label, "calls": len(recs), "minutes": sum(r["latency_s"] for r in recs) / 60,
                     "prompt_ktok": pin / 1000,
                     "est_api_usd": (pin * llm["price_in_per_mtok_usd"] + pout * llm["price_out_per_mtok_usd"]) / 1e6,
                     "final": json.load(open(final))["candidate_id"] if final.exists() else "none"})
    fig, axs = plt.subplots(1, 3, figsize=(11, 3.4))
    for ax, (key, title) in zip(axs, [("calls", "LLM calls"), ("minutes", "Model time (min, laptop CPU)"),
                                      ("prompt_ktok", "Prompt tokens (thousands)")]):
        ax.bar([r["run"] for r in rows], [r[key] for r in rows], color=C[0], width=0.55)
        for i, r in enumerate(rows):
            ax.text(i, r[key], f"{r[key]:.0f}", ha="center", va="bottom", fontsize=9, color=INK)
        ax.set_title(title, loc="left", fontsize=11)
        ax.grid(axis="x", visible=False)
    fig.suptitle("Agent runs, local qwen3.5 4B, cost EUR 0", x=0.01, ha="left", fontweight="bold", color=INK)
    fig.tight_layout()
    save(fig, "fig_runs.png")
    with open(OUT / "runs_table.json", "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=1)
    for r in rows:
        print(f"{r['run']}: {r['calls']} calls, {r['minutes']:.0f} min, {r['prompt_ktok']:.0f}k prompt tokens, "
              f"final {r['final']}, est. paid-API cost ${r['est_api_usd']:.3f} (estimate only)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", choices=["demand", "dispatch", "cost_co2", "runs"])
    ap.add_argument("--run5", help="run 5 folder name (default: newest run folder)")
    a = ap.parse_args()
    cfg = load_config()
    runs = dict(AGENT_RUNS)
    newest = sorted(p.name for p in RUNS.glob("2*") if p.is_dir() and "aborted" not in p.name)
    run5 = a.run5 or (newest[-1] if newest else None)
    if run5 and run5 not in runs.values():
        runs["Run 5"] = run5
    todo = a.only or ["demand", "dispatch", "cost_co2", "runs"]
    if "demand" in todo:
        fig_demand(cfg)
    if "dispatch" in todo:
        fig_dispatch_and_split(cfg)
    if "cost_co2" in todo:
        fig_cost_co2(cfg, runs)
    if "runs" in todo:
        fig_runs(runs)


if __name__ == "__main__":
    main()
