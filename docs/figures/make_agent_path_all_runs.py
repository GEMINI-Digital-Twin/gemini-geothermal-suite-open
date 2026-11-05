"""All three repeats of the showcase agent run, side by side, failures included.

``fig_agent_path.png`` tells the story of run 1. This figure shows that run 1 was the
best of three. Run 2 gave up at the step limit, and run 3 answered but made a false
claim. For each run it draws every design the agent simulated (LCOE against CO2, in the
agent's terms, with CO2 at 180 EUR/t), the design it ended on, and the session timeline
(LLM calls, tool calls, physics gate)::

    python docs/figures/make_agent_path_all_runs.py \
        simulator_examples/agent_compare_results/2026-11-03-objective \
        docs/figures/fig_agent_path_all_runs.png

Author: Sa'eed Telvari
"""

import json
import sys
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

NAVY, RUST, BLUE, GREY, BG = "#14213D", "#A8431A", "#1F6FA8", "#8A93A3", "#F6F4EF"
GREEN, RED, AMBER = "#2E7D4F", "#C0392B", "#B07A1A"
MARKERS = {1: "o", 2: "s", 3: "^"}

# What each run ended with, checked by hand in the run folder's summary.md.
RUNS = {
    "r1": {
        "end": "R0038",
        "label": "answered",
        "colour": GREEN,
        "text": "Answer: 2 doublets · 3.0 km · boiler · CHP · tower chiller + free cooling.\n"
        "Tested a doublet trip itself. Gate rejected 2 drafts, then passed.",
    },
    "r2": {
        "end": "R0077",
        "label": "gave up at the 30-step limit",
        "colour": RED,
        "text": "No answer. It reran the outage case without CHP about 15 times\n"
        "(the ledger correctly returned the same run). Best found: screw dry cooler.",
    },
    "r3": {
        "end": "R0109",
        "label": "answered, with one false claim",
        "colour": AMBER,
        "text": "Answer: 2 doublets · 3.0 km · boiler · CHP · screw dry cooler.\n"
        "Said the weather was not loaded (it was); the gate checks numbers,\n"
        "not such claims. Star: its cited run with the peak-day outage.",
    },
}
plt.rcParams.update({"font.family": ["Inter", "DejaVu Sans"], "font.size": 10})


def load(run_dir):
    ledger = {}
    for line in (run_dir / "run_ledger.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        ledger[r["run_id"]] = r
    path = next((run_dir / "transcripts").glob("*.jsonl"))
    events = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
    return ledger, events


def xy(rec):
    h = rec["headline"]
    return h["co2_t_per_year"] / 1000, h["lcoe_eur_per_mwh"]


def design_panel(ax, ledger, run):
    n = 0
    for rec in ledger.values():
        if rec["kind"] != "design":
            continue
        n += 1
        q, h = rec["request"], rec["headline"]
        x, y = xy(rec)
        if h.get("physics_gate") != "pass" or not h.get("meets_all_hard_rules"):
            ax.scatter(x, y, marker="x", s=26, color=RED, linewidths=1.2, alpha=0.7, zorder=3)
            continue
        colour = RUST if q.get("upgrade") == "heat_pump" else NAVY
        chp = q.get("chp_capacity_mw_el") or q.get("chp")
        ax.scatter(
            x,
            y,
            marker=MARKERS.get(q.get("n_doublets"), "o"),
            s=26,
            color=colour if chp else "none",
            edgecolors=colour,
            linewidths=1.0,
            alpha=0.7,
            zorder=3,
        )
    ex, ey = xy(ledger[run["end"]])
    ax.scatter(
        ex, ey, marker="*", s=420, color=run["colour"], edgecolors=NAVY, linewidths=0.8, zorder=6
    )
    ax.annotate(
        f"{run['end']}: €{ey:.2f}/MWh, {ex * 1000:,.0f} t",
        (ex, ey),
        xytext=(ex + 1.2, ey + 6),
        color=run["colour"],
        fontsize=9.5,
        fontweight="bold",
        arrowprops={"arrowstyle": "->", "color": run["colour"], "lw": 1.0},
    )
    ax.set_xlim(3, 19)
    ax.set_ylim(34, 77)
    ax.set_xlabel("CO₂, kt per year")
    return n


def timeline_panel(ax, events):
    def t(e):
        return datetime.strptime(e["t"], "%H:%M:%S")

    t0 = t(events[0])

    def m(e):
        return (t(e) - t0).total_seconds() / 60

    for e in events:
        if e["kind"] == "llm":
            ax.scatter(m(e), 2, s=12 + int(e.get("prompt_tokens", 0)) / 200, color=RUST, alpha=0.8)
        elif e["kind"] == "tool":
            bad = "error" in e.get("result_preview", "")[:12]
            ax.scatter(
                m(e),
                1,
                marker="x" if bad else "|",
                s=30 if bad else 140,
                color=RED if bad else (NAVY if e["name"] == "screen" else BLUE),
                linewidths=1.6,
            )
        elif e["kind"] == "gate_reject":
            ax.scatter(m(e), 0, marker="X", s=60, color=RED, zorder=4)
        elif e["kind"] == "gate_pass":
            ax.scatter(m(e), 0, marker="P", s=70, color=GREEN, zorder=4)
    ax.set_yticks([2, 1, 0], ["LLM", "tools", "gate"])
    ax.set_ylim(-0.7, 2.6)
    ax.set_xlabel("minutes since the question")
    ax.tick_params(axis="y", length=0)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    calls = [e for e in events if e["kind"] == "llm"]
    tools = [e for e in events if e["kind"] == "tool"]
    return len(calls), len(tools), m(events[-1])


def main(folder, out):
    folder = Path(folder)
    fig = plt.figure(figsize=(17, 8.0), dpi=150, facecolor=BG)
    gs = fig.add_gridspec(
        3,
        3,
        height_ratios=[3.0, 0.62, 0.55],
        hspace=0.55,
        wspace=0.14,
        left=0.05,
        right=0.99,
        top=0.80,
        bottom=0.03,
    )
    for i, (key, run) in enumerate(RUNS.items()):
        ledger, events = load(folder / key)
        ax = fig.add_subplot(gs[0, i])
        tx = fig.add_subplot(gs[1, i])
        note = fig.add_subplot(gs[2, i])
        for a in (ax, tx, note):
            a.set_facecolor(BG)
            for side in ("top", "right"):
                a.spines[side].set_visible(False)
        n = design_panel(ax, ledger, run)
        calls, tools, mins = timeline_panel(tx, events)
        if i == 0:
            ax.set_ylabel("LCOE with CO₂ at €180/t, €/MWh")
        ax.set_title(
            f"Run {i + 1}: {run['label']}",
            loc="left",
            color=run["colour"],
            fontsize=13,
            fontweight="bold",
        )
        ax.text(
            0.98,
            0.97,
            f"{n} designs simulated\n{calls} LLM calls · {tools} tool calls" f" · {mins:.0f} min",
            transform=ax.transAxes,
            ha="right",
            va="top",
            fontsize=9.5,
            color="#3D4757",
        )
        note.axis("off")
        note.text(0, 1, run["text"], va="top", fontsize=10, color="#3D4757")
    handles = [
        plt.Line2D([], [], marker="o", ls="", color=NAVY, label="boiler top-up"),
        plt.Line2D([], [], marker="o", ls="", color=RUST, label="heat pump"),
        plt.Line2D([], [], marker="o", ls="", mfc="none", mec=GREY, label="hollow = no CHP"),
        plt.Line2D([], [], marker="s", ls="", color=GREY, label="○ 1  □ 2  △ 3 doublets"),
        plt.Line2D([], [], marker="x", ls="", color=RED, label="fails a hard rule or the gate"),
        plt.Line2D([], [], marker="*", ls="", ms=13, color=GREY, label="where the run ended"),
    ]
    fig.legend(
        handles=handles,
        ncol=6,
        frameon=False,
        fontsize=9.5,
        bbox_to_anchor=(0.05, 0.905),
        loc="upper left",
    )
    fig.suptitle(
        "The same question asked three times: one clean answer, one give-up, one " "false claim",
        x=0.05,
        ha="left",
        fontsize=17,
        fontweight="bold",
        color=NAVY,
        y=0.98,
    )
    fig.text(
        0.05,
        0.935,
        "DeepSeek V4.1 Flash, 3 Nov 2026, scenario 10 (lowest cost, CO₂ at "
        "€100/t on top, meet demand if the wells trip on the coldest days), KNMI 2025 "
        "weather. All three chose 2 doublets at 3.0 km with CHP; none tried ATES.",
        fontsize=10.5,
        color="#3D4757",
        va="top",
    )
    fig.savefig(out, facecolor=BG)
    print("wrote", out)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
