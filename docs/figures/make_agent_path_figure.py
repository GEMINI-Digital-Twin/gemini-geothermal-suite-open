"""Draw how the design agent reached its answer: every design it simulated, in order.

Reads one live agent run (run ledger + transcript) and draws three panels:

- left: the agent's first broad screen (36 designs) on LCOE against CO2, in the
  agent's own terms (CO2 counted at the price it chose, 180 EUR/t);
- right: a zoom on the refinement, with each probe numbered in the order the
  agent ran it, its verdict, the trip test, the price sensitivity and the answer;
- bottom: the timeline of the session (LLM calls, tool calls, the physics gate).

    python docs/figures/make_agent_path_figure.py \
        simulator_examples/agent_compare_results/2026-11-03-objective/r1 \
        docs/figures/fig_agent_path.png

Author: Sa'eed Telvari
"""

import json
import sys
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, Rectangle  # noqa: E402

NAVY, RUST, BLUE, GREY, BG = "#14213D", "#A8431A", "#1F6FA8", "#8A93A3", "#F6F4EF"
GREEN, RED = "#2E7D4F", "#C0392B"
MARKERS = {1: "o", 2: "s", 3: "^"}
plt.rcParams.update(
    {
        "font.family": ["Inter", "DejaVu Sans"],
        "font.size": 11,
        "axes.edgecolor": "#5A6474",
        "axes.labelcolor": NAVY,
        "xtick.color": "#5A6474",
        "ytick.color": "#5A6474",
    }
)


def load(run_dir):
    run_dir = Path(run_dir)
    ledger = {}
    for line in (run_dir / "run_ledger.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        ledger[r["run_id"]] = r
    events = [
        json.loads(line)
        for line in next((run_dir / "transcripts").glob("*.jsonl"))
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    return ledger, events


def xy(rec):
    h = rec["headline"]
    return h["co2_t_per_year"] / 1000, h["lcoe_eur_per_mwh"]


def screen_panel(ax, ledger):
    screen = next(r for r in ledger.values() if r["kind"] == "screen")
    for rid in screen["members"]:
        rec = ledger[rid]
        q, h = rec["request"], rec["headline"]
        x, y = xy(rec)
        hp = q["upgrade"] == "heat_pump"
        colour = RUST if hp else NAVY
        m = MARKERS[q["n_doublets"]]
        if h.get("physics_gate") != "pass":
            ax.scatter(x, y, marker="x", s=46, color=RED, linewidths=1.6, zorder=4)
        else:
            ax.scatter(
                x, y, marker=m, s=46, color=colour if q["chp_capacity_mw_el"] else "none",
                edgecolors=colour, linewidths=1.2, alpha=0.85, zorder=3,
            )
    best = ledger["R0022"]
    bx, by = xy(best)
    ax.scatter(bx, by, s=260, facecolors="none", edgecolors=BLUE, linewidths=2.2, zorder=5)
    ax.annotate(
        "best of the screen\n2 doublets · 3.0 km · boiler · CHP",
        (bx, by), xytext=(bx + 2.6, by - 5.5), color=BLUE, fontsize=10.5, fontweight="bold",
        arrowprops={"arrowstyle": "->", "color": BLUE, "lw": 1.2},
    )
    # depth labels: groups of the screen
    depth_labels = {"2.0 km": (16.4, 62), "2.5 km": (11.3, 52.5), "3.0 km": (10.6, 41.0)}
    for depth, (tx, ty) in depth_labels.items():
        ax.text(tx, ty, depth, color="#5A6474", fontsize=10, style="italic")
    ax.add_patch(
        Rectangle((3.9, 38.9), 3.0, 7.0, fill=False, ls="--", lw=1.1, ec=BLUE, zorder=2)
    )
    ax.text(3.95, 46.3, "zoom →", color=BLUE, fontsize=10)
    ax.set_xlim(3, 19)
    ax.set_ylim(36, 77)
    ax.set_xlabel("CO₂, kt per year")
    ax.set_ylabel("LCOE with CO₂ at €180/t, €/MWh")
    ax.set_title(
        "① Broad screen: 36 designs, 7 minutes of simulation", loc="left",
        color=NAVY, fontsize=13, fontweight="bold",
    )
    # legend
    handles = [
        ax.scatter([], [], marker="o", color=NAVY, s=40, label="boiler top-up"),
        ax.scatter([], [], marker="o", color=RUST, s=40, label="heat pump"),
        ax.scatter([], [], marker="o", facecolors="none", edgecolors=GREY, s=40,
                   label="hollow = no CHP"),
        ax.scatter([], [], marker="o", color=GREY, s=40, label="○ 1  □ 2  △ 3 doublets"),
        ax.scatter([], [], marker="x", color=RED, s=40, label="rejected by physics gate (5)"),
    ]
    ax.legend(handles=handles, frameon=False, fontsize=9.5, loc="lower right")


def zoom_panel(ax, ledger):
    base, pick = ledger["R0022"], ledger["R0038"]
    px, py = xy(pick)
    bx, by = xy(base)

    def note(text, xy_text, colour, bold=False):
        ax.text(*xy_text, text, fontsize=10, color=colour, fontweight="bold" if bold else None,
                va="top", bbox={"fc": BG, "ec": "none", "pad": 1.5}, zorder=7)

    def arrow(a, b, colour, ls="--", lw=1.1):
        ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=12, color=colour,
                                     lw=lw, ls=ls, shrinkA=8, shrinkB=6, zorder=3))

    ax.scatter(bx, by, marker="s", s=80, color=NAVY, zorder=4)
    note("screen best", (bx + 0.08, by + 0.2), NAVY)
    arrow((bx, by), (px, py), BLUE, ls="-", lw=2.4)
    d_cost = pick["headline"]["lcoe_eur_per_mwh"] - by
    d_co2 = pick["headline"]["co2_t_per_year"] - base["headline"]["co2_t_per_year"]
    text = f"② add free cooling + tower chiller\n    {d_cost:+.2f} €/MWh, {d_co2:+.0f} t CO₂"
    note(text.replace("-", "−"), (5.38, 40.5), BLUE)

    # ③ probes around the new best, each with the agent's verdict
    for rid in ("R0040", "R0047", "R0044", "R0042"):
        rec = ledger[rid]
        x, y = xy(rec)
        hp = rec["request"]["upgrade"] == "heat_pump"
        colour = "#B07A1A" if rid == "R0044" else RED
        arrow((px, py), (x, y), colour)
        ax.scatter(x, y, marker="s", s=70, color=RUST if hp else NAVY, zorder=4)
    note("③ 3.5 km, with either chiller\n    rejected: less CO₂ but dearer", (3.97, 41.45), RED)
    note("③ screw chiller + dry cooler\n    kept as the water-free alternative", (5.05, 39.78),
         "#B07A1A")
    x, y = xy(ledger["R0042"])
    note("③ heat pump instead of boiler\n    rejected: dearer and more CO₂", (x + 0.07, y + 0.3),
         RED)
    x3, y3 = xy(ledger["R0041"])
    arrow((px, py), (x3, 46.0), RED)
    note(f"③ 3 doublets: €{y3:.1f}/MWh ↑ off the chart\n    rejected", (3.97, 46.3), RED)

    # ④ trip test at the January peak
    x, y = xy(ledger["R0043"])
    arrow((px, py), (x, y), GREEN, ls=":", lw=1.4)
    ax.scatter(x, y, marker="s", s=80, facecolors="none", edgecolors=GREEN, linewidths=1.8,
               zorder=4)
    note("④ stress test: a doublet down 35 days\n    from 28 Jan, the coldest day. Demand met",
         (5.5, y - 0.3), GREEN)

    # ⑤ CO2 price sensitivity and ⑥ the answer
    lo, hi = ledger["R0045"]["headline"], ledger["R0046"]["headline"]
    note(f"⑤ CO₂ at €80 or €300/t: €{lo['lcoe_eur_per_mwh']:.1f} to "
         f"€{hi['lcoe_eur_per_mwh']:.1f}/MWh,\n    the pick holds. "
         "⑥ Cross-checked in GEMINI's solver",
         (5.05, 38.85), "#3D4757")
    ax.scatter(px, py, marker="*", s=620, color=RUST, edgecolors=NAVY, linewidths=1.0, zorder=6)
    note("⑥ answer\n2 doublets · 3.0 km\nboiler · CHP · tower\nchiller + free cooling",
         (3.97, 40.15), RUST, bold=True)
    ax.set_xlim(3.9, 7.0)
    ax.set_ylim(37.9, 46.9)
    ax.set_xlabel("CO₂, kt per year")
    ax.set_title("②–⑥ Refine, probe, stress-test, answer: 10 more runs in 1½ minutes",
                 loc="left", color=NAVY, fontsize=13, fontweight="bold")


def timeline_panel(ax, events):
    def t(e):
        return datetime.strptime(e["t"], "%H:%M:%S")

    t0 = t(events[0])

    def s(e):
        return (t(e) - t0).total_seconds() / 60

    colours = {
        "screen": NAVY, "run_design": BLUE, "sensitivity": BLUE, "cross_check": GREEN,
        "get_run": GREY, "describe_inputs": GREY, "list_models": GREY,
        "log_option": "#B07A1A", "memory_write": "#B07A1A",
    }
    lanes = {"LLM thinks": 2, "simulations": 1, "physics gate": 0}
    prompt_total = 0
    for e in events:
        if e["kind"] == "llm":
            prompt_total += int(e.get("prompt_tokens", 0))
            ax.scatter(s(e), 2, s=20 + int(e["prompt_tokens"]) / 120, color=RUST, alpha=0.8)
        elif e["kind"] == "tool":
            dur = float(e.get("seconds", 0)) / 60
            c = colours.get(e["name"], GREY)
            if e["name"] == "screen":
                ax.add_patch(Rectangle((s(e) - dur, 0.75), dur, 0.5, color=c, alpha=0.9))
                ax.text(s(e) - dur / 2, 1, "screen: 36 year-long simulations (412 s)",
                        color="white", ha="center", va="center", fontsize=10, fontweight="bold")
            elif "error" in e.get("result_preview", "")[:12]:
                ax.scatter(s(e), 1, marker="x", s=40, color=RED)
            else:
                ax.scatter(s(e), 1, marker="|", s=260, color=c, linewidths=2.2)
        elif e["kind"] == "gate_reject":
            ax.scatter(s(e), 0, marker="X", s=90, color=RED, zorder=4)
        elif e["kind"] == "gate_pass":
            ax.scatter(s(e), 0, marker="P", s=110, color=GREEN, zorder=4)
    ax.text(8.05, -0.25, "answer rejected twice for a number no tool produced, then passed",
            fontsize=9.5, color=RED, ha="right", va="top")
    calls = [e for e in events if e["kind"] == "llm"]
    think = sum(float(e.get("latency_s", 0)) for e in calls)
    ax.text(0.08, 2.32, f"{len(calls)} LLM calls · {prompt_total / 1000:.0f} k prompt tokens · "
            f"{think:.0f} s of LLM time in total", fontsize=10, color=RUST)
    ax.text(7.25, 1.42, "runs · reads · cross-check · logs", fontsize=9.5, color="#5A6474",
            ha="center")
    ax.set_yticks(list(lanes.values()), list(lanes.keys()))
    ax.set_ylim(-1.0, 2.7)
    ax.set_xlim(-0.1, 8.6)
    ax.set_xlabel("minutes since the question")
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.set_title("The session in time: the LLM decides, the simulator does the work",
                 loc="left", color=NAVY, fontsize=13, fontweight="bold")


def main(run_dir, out):
    ledger, events = load(run_dir)
    fig = plt.figure(figsize=(16, 9), dpi=150, facecolor=BG)
    gs = fig.add_gridspec(2, 2, height_ratios=[3.1, 1.15], width_ratios=[1, 1.15],
                          hspace=0.42, wspace=0.12, left=0.075, right=0.985, top=0.85,
                          bottom=0.07)
    ax1, ax2 = fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[0, 1])
    ax3 = fig.add_subplot(gs[1, :])
    for ax in (ax1, ax2, ax3):
        ax.set_facecolor(BG)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    screen_panel(ax1, ledger)
    zoom_panel(ax2, ledger)
    timeline_panel(ax3, events)
    fig.suptitle(
        "How the agent reached its design: 46 simulated years, one question, 8½ minutes",
        x=0.075, ha="left", fontsize=19, fontweight="bold", color=NAVY, y=0.975,
    )
    fig.text(
        0.075, 0.935,
        "DeepSeek V4.1 Flash, 3 Nov 2026, run 1. Asked: lowest cost, CO₂ counted at €100/t on "
        "top of the €80 already priced, and meet demand if the wells trip on the coldest days.\n"
        "Every point is a full year simulated on KNMI 2025 weather. The agent chose every design "
        "and every test itself; nothing here is scripted.",
        fontsize=11, color="#3D4757", va="top",
    )
    fig.savefig(out, facecolor=BG)
    print("wrote", out)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
