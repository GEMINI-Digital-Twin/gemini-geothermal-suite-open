"""Report figures for the uncertainty study (matplotlib, PNG).

Colours follow a fixed categorical order (blue, orange, aqua, yellow,
magenta, green) assigned by design in the order given, never by rank,
so a design keeps its colour across every figure.
"""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

SERIES = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948")
INK, INK_2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
DIVERGING = ("#2a78d6", "#d9d8d4", "#e34948")  # blue, neutral grey, red


def _style(ax):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(INK_2)
    ax.tick_params(colors=INK_2, labelsize=9)
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def _figure(width=7.0, height=4.2):
    fig, ax = plt.subplots(figsize=(width, height), dpi=160)
    fig.patch.set_facecolor(SURFACE)
    _style(ax)
    return fig, ax


def colours(designs):
    """Return ``{design: colour}`` in fixed categorical order."""
    return {d: SERIES[i % len(SERIES)] for i, d in enumerate(designs)}


def lcoe_ecdf(results, designs, path):
    """Cumulative distribution of levelised cost for each design."""
    fig, ax = _figure()
    col = colours(designs)
    for d in designs:
        x = np.sort(results.loc[results["design"] == d, "lcoe_eur_per_mwh"].dropna().to_numpy())
        if not len(x):
            continue
        y = np.arange(1, len(x) + 1) / len(x)
        ax.plot(x, y, color=col[d], linewidth=2, label=d)
    for q in (0.1, 0.5, 0.9):
        ax.axhline(q, color=INK_2, linewidth=0.8, linestyle=":")
        ax.text(ax.get_xlim()[1], q, f" P{int(q * 100)}", va="center", color=INK_2, fontsize=8)
    ax.set_xlabel("Levelised cost of heating + cooling (EUR/MWh)", color=INK)
    ax.set_ylabel("Probability cost is at or below", color=INK)
    ax.set_title("Levelised cost under uncertainty", color=INK, loc="left", fontsize=11)
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def cost_co2_scatter(results, designs, path):
    """Levelised cost vs annual CO2 clouds (at most three designs stay distinguishable)."""
    fig, ax = _figure()
    col = colours(designs)
    for d in designs[:3]:
        g = results[results["design"] == d]
        ax.scatter(
            g["co2_t_per_year"] / 1e3,
            g["lcoe_eur_per_mwh"],
            s=14,
            color=col[d],
            alpha=0.55,
            edgecolors=SURFACE,
            linewidths=0.5,
            label=d,
        )
        ax.scatter(
            g["co2_t_per_year"].median() / 1e3,
            g["lcoe_eur_per_mwh"].median(),
            s=90,
            color=col[d],
            edgecolors=INK,
            linewidths=1.2,
            marker="D",
        )
    ax.set_xlabel("CO2 emitted (kt/yr)", color=INK)
    ax.set_ylabel("Levelised cost (EUR/MWh)", color=INK)
    ax.set_title(
        "Cost vs emissions per Monte Carlo sample (diamond = median)",
        color=INK,
        loc="left",
        fontsize=11,
    )
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def tornado_chart(table, design, path, metric="lcoe", unit="EUR/MWh", top=10):
    """Tornado of P10/P90 one-at-a-time swings around the base case."""
    t = table.sort_values(f"{metric}_swing", ascending=False).head(top).iloc[::-1]
    base = float(t[f"{metric}_base"].iloc[0])
    fig, ax = _figure(7.2, 0.42 * len(t) + 1.4)
    y = np.arange(len(t))
    lo = t[f"{metric}_low"].to_numpy() - base
    hi = t[f"{metric}_high"].to_numpy() - base
    ax.barh(y, lo, left=base, color=DIVERGING[0], height=0.6, label="input at P10")
    ax.barh(y, hi, left=base, color=DIVERGING[2], height=0.6, label="input at P90")
    ax.axvline(base, color=INK, linewidth=1)
    labels = [
        f"{r.label}  ({r.input_low:.3g} / {r.input_high:.3g} {r.unit})" for r in t.itertuples()
    ]
    ax.set_yticks(y, labels, fontsize=8, color=INK)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel(f"{'Levelised cost' if metric == 'lcoe' else 'CO2'} ({unit})", color=INK)
    fig.suptitle(
        f"{design}\nP10/P90 swing around the base case ({base:,.1f} {unit})",
        color=INK,
        x=0.02,
        ha="left",
        fontsize=10,
    )
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def probability_bars(summary, path):
    """Probability that each design meets all demand under every hard constraint."""
    s = summary.iloc[::-1]
    fig, ax = _figure(7.2, 0.42 * len(s) + 1.4)
    y = np.arange(len(s))
    ax.barh(y, s["p_demand_met"] * 100, color=SERIES[0], height=0.6)
    for yi, p in zip(y, s["p_demand_met"]):
        ax.text(p * 100 + 1, yi, f"{p * 100:.0f}%", va="center", fontsize=8, color=INK)
    ax.set_yticks(y, s["design"], fontsize=8, color=INK)
    ax.set_xlim(0, 108)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Samples meeting all heating and cooling demand (%)", color=INK)
    ax.set_title("Probability of meeting demand", color=INK, loc="left", fontsize=11)
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def correlation_heatmap(corr, labels, path):
    """Spearman rank correlation of inputs (rows) with levelised cost, per design (columns)."""
    from matplotlib.colors import LinearSegmentedColormap

    cmap = LinearSegmentedColormap.from_list("div", DIVERGING)
    fig, ax = plt.subplots(figsize=(1.3 * corr.shape[1] + 3.4, 0.36 * corr.shape[0] + 1.6), dpi=160)
    fig.patch.set_facecolor(SURFACE)
    im = ax.imshow(corr.to_numpy(), cmap=cmap, vmin=-1, vmax=1, aspect="auto")
    ax.set_xticks(range(corr.shape[1]), corr.columns, rotation=30, ha="right", fontsize=8)
    ax.set_yticks(range(corr.shape[0]), [labels.get(i, i) for i in corr.index], fontsize=8)
    for i in range(corr.shape[0]):
        for j in range(corr.shape[1]):
            v = corr.iat[i, j]
            ax.text(j, i, f"{v:+.2f}", ha="center", va="center", fontsize=7, color=INK)
    ax.set_title("Rank correlation with levelised cost", color=INK, loc="left", fontsize=11)
    fig.colorbar(im, ax=ax, shrink=0.7)
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def margin_curve(capacities, probabilities, path, label="Chiller capacity (MW)"):
    """Probability of meeting demand against an equipment capacity."""
    fig, ax = _figure(6.0, 3.6)
    ax.plot(capacities, np.asarray(probabilities) * 100, color=SERIES[0], linewidth=2, marker="o")
    for c, p in zip(capacities, probabilities):
        ax.annotate(
            f"{p * 100:.0f}%",
            (c, p * 100),
            textcoords="offset points",
            xytext=(0, 8),
            ha="center",
            fontsize=8,
            color=INK,
        )
    ax.set_ylim(0, 110)
    ax.set_xlabel(label, color=INK)
    ax.set_ylabel("Samples meeting all demand (%)", color=INK)
    ax.set_title(
        "Sizing margin vs probability of meeting demand", color=INK, loc="left", fontsize=11
    )
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
