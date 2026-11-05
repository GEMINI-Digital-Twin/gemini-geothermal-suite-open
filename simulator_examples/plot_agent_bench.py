"""Figure for the max-thinking agent benchmark: score per model, and score against cost.

    $env:PYTHONPATH="src"
    python simulator_examples/plot_agent_bench.py `
        simulator_examples/agent_bench_results/2026-11-04-max/merged `
        --baseline simulator_examples/agent_bench_results/2026-11-01/results_rescored.json `
        --out docs/figures/fig_agent_benchmark.png

Left: mean total score (grid-scored, 95 % bootstrap CI) per model, the same score with
design cases scored against the pooled best (open marker), and the 1 Nov run at its
lower thinking settings (grey tick) where the model was in it. Hatched bars are
partial: some runs were lost to credit or quota stops and are left out of the mean. Right: mean score
against USD per run (OpenRouter billed cost, or API-equivalent at list prices for the
ChatGPT-plan models). Writes a CSV of the plotted numbers next to the PNG.
"""

import argparse
import csv
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).parent))
from run_agent_bench import bootstrap_ci

NAMES = {
    "gpt-6.1-sol": "GPT-6.1 Sol",
    "gpt-6.1-terra": "GPT-6.1 Terra",
    "gpt-6-luna": "GPT-6 Luna",
    "deepseek-v4.1-flash": "DeepSeek V4.1 Flash",
    "glm-5.3": "GLM 5.3",
    "qwen3.8-27b": "Qwen 3.8 27B",
}
COLORS = {
    "gpt-6.1-sol": "#1f5fa8",
    "gpt-6.1-terra": "#4f8fd6",
    "gpt-6-luna": "#8fb8e8",
    "deepseek-v4.1-flash": "#c2562b",
    "glm-5.3": "#d9913a",
    "qwen3.8-27b": "#5a9e4b",
}


def stats(rows):
    """Per backend: runs, mean, CI, pooled mean, pass rate, USD per run."""
    out = {}
    for b in dict.fromkeys(r["backend"] for r in rows):
        rs = [r for r in rows if r["backend"] == b]
        tot = [r["total"] for r in rs]
        pooled = [r.get("pooled_total", r["total"]) for r in rs]
        billed = sum(r.get("billed_usd") or 0 for r in rs)
        usd = billed if billed > 0 else sum(r.get("cost_usd") or 0 for r in rs)
        lo, hi = bootstrap_ci(tot)
        out[b] = {
            "runs": len(rs),
            "mean": sum(tot) / len(tot),
            "lo": lo,
            "hi": hi,
            "pooled": sum(pooled) / len(pooled),
            "pass_rate": sum(r["passed"] for r in rs) / len(rs),
            "usd_per_run": usd / len(rs),
            "cost_basis": "billed" if billed > 0 else "API-equivalent",
        }
    return out


def main(argv=None):
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("merged", help="folder with the merged results.json")
    ap.add_argument(
        "--baseline", help="1 Nov results(_rescored).json for the grey ticks"
    )
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    rows = json.loads((Path(args.merged) / "results.json").read_text(encoding="utf-8"))
    s = stats(rows)
    base = {}
    if args.baseline:
        base = stats(json.loads(Path(args.baseline).read_text(encoding="utf-8")))
    order = sorted(s, key=lambda b: s[b]["mean"])

    fig, (ax, bx) = plt.subplots(
        1, 2, figsize=(10, 4.2), gridspec_kw={"width_ratios": [1.3, 1]}
    )
    full = max(v["runs"] for v in s.values())
    for i, b in enumerate(order):
        v = s[b]
        c = COLORS.get(b, "#777")
        partial = v["runs"] < full  # runs lost to credit or quota stops: hatched
        ax.barh(
            i,
            v["mean"],
            color=c,
            height=0.6,
            hatch="///" if partial else None,
            edgecolor="white" if partial else None,
            lw=0,
        )
        ax.errorbar(
            v["mean"],
            i,
            xerr=[[v["mean"] - v["lo"]], [v["hi"] - v["mean"]]],
            fmt="none",
            ecolor="#222",
            capsize=3,
            lw=1,
        )
        ax.plot(v["pooled"], i, "o", mfc="white", mec="#222", ms=6, zorder=3)
        if b in base:
            ax.plot([base[b]["mean"]] * 2, [i - 0.32, i + 0.32], color="#888", lw=2.5)
        ax.text(
            1.02,
            i,
            f"{v['pass_rate']:.0%} pass, n={v['runs']}"
            + (" of 33*" if partial else ""),
            va="center",
            fontsize=8,
        )
    ax.set_yticks(range(len(order)), [NAMES.get(b, b) for b in order])
    ax.set_xlim(0, 1.0)
    ax.axvline(0.7, color="#999", ls=":", lw=1)
    ax.set_xlabel("mean total score (0-1), 95 % CI; pass mark 0.7")
    ax.set_title("Score per model at its highest thinking setting", fontsize=10)
    handles = [
        plt.Line2D(
            [],
            [],
            marker="o",
            ls="",
            mfc="white",
            mec="#222",
            label="pooled-best scoring",
        ),
        plt.Line2D([], [], color="#888", lw=2.5, label="1 Nov run (lower thinking)"),
        plt.Rectangle(
            (0, 0),
            1,
            1,
            fc="#bbb",
            hatch="///",
            ec="white",
            lw=0,
            label="*partial: runs lost to credit or quota stops",
        ),
    ]
    ax.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.17),
        ncol=3,
        fontsize=7,
        frameon=False,
    )

    for b in order:
        v = s[b]
        bx.scatter(
            v["usd_per_run"], v["mean"], s=60, color=COLORS.get(b, "#777"), zorder=3
        )
        left = (
            v["usd_per_run"] > 0.3
        )  # keep labels of the dearest models inside the axes
        bx.annotate(
            NAMES.get(b, b) + ("*" if v["runs"] < full else ""),
            (v["usd_per_run"], v["mean"]),
            textcoords="offset points",
            xytext=(
                -6 if left else 6,
                {"gpt-6.1-terra": 5, "gpt-6.1-sol": -13}.get(b, -3),
            ),  # Terra just above Sol, Sol below
            ha="right" if left else "left",
            fontsize=8,
        )
    bx.set_xscale("log")
    bx.set_xlabel(
        "USD per run (log scale)\nbilled, or API-equivalent for plan models", fontsize=9
    )
    bx.set_ylabel("mean total score")
    bx.set_ylim(0.6, 1.0)
    bx.grid(alpha=0.3, which="both")
    bx.set_title("Score against cost", fontsize=10)
    fig.tight_layout()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=200, bbox_inches="tight")
    with open(out.with_suffix(".csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "backend",
                "runs",
                "mean_total",
                "ci_lo",
                "ci_hi",
                "pooled_mean",
                "pass_rate",
                "usd_per_run",
                "cost_basis",
                "nov1_mean",
            ]
        )
        for b in reversed(order):
            v = s[b]
            w.writerow(
                [
                    b,
                    v["runs"],
                    round(v["mean"], 3),
                    v["lo"],
                    v["hi"],
                    round(v["pooled"], 3),
                    round(v["pass_rate"], 3),
                    round(v["usd_per_run"], 4),
                    v["cost_basis"],
                    round(base[b]["mean"], 3) if b in base else "",
                ]
            )
    print(f"wrote {out} and {out.with_suffix('.csv')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
