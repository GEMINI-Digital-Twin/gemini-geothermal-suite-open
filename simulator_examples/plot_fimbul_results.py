"""Plot the Fimbul.jl sweep: production temperature decline and pressures.

Reads the cached runs and ``outputs/fimbul/sweep_report.json`` (run
``run_fimbul_sweep.py`` first) and writes PNGs to ``outputs/fimbul/``.

Run with:
    $env:PYTHONPATH="src"; python simulator_examples/plot_fimbul_results.py
"""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from gemini_design.fimbul.lookup import load_table  # noqa: E402
from gemini_design.fimbul.runner import DEFAULT_CACHE  # noqa: E402

OUTPUTS = Path(__file__).parent / "outputs" / "fimbul"


def plot_grid(tab, path):
    """Production temperature over 30 years for every spacing and rate."""
    t_res = tab["meta"]["reservoir_temperature_c"]
    t_inj = tab["meta"]["injection_temperature_c"]
    fig, axes = plt.subplots(1, len(tab["flow_m3h"]), figsize=(13, 3.6), sharey=True)
    colors = plt.cm.viridis(np.linspace(0, 0.9, len(tab["spacing_m"])))
    for j, (ax, q) in enumerate(zip(axes, tab["flow_m3h"])):
        for i, (s, c) in enumerate(zip(tab["spacing_m"], colors)):
            temp = t_res - tab["theta"][i, j] * (t_res - t_inj)
            ax.plot(tab["years"], temp, color=c, label=f"{int(s)} m")
        ax.set_title(f"{int(q)} m³/h (constant)")
        ax.set_xlabel("Year")
        ax.grid(alpha=0.3)
    axes[0].set_ylabel("Producer bottomhole T (°C)")
    axes[-1].legend(title="Well spacing", fontsize=8)
    fig.suptitle("Fimbul.jl: one doublet at 3.1 km, 200 mD, 100 m, reinjection at 60 °C")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_pick(path):
    """The likely pick on its real monthly schedule (2 doublets)."""
    runs = []
    for f in sorted(DEFAULT_CACHE.glob("*.json")):
        r = json.loads(f.read_text())
        if r["inputs"]["n_doublets"] == 2:
            runs.append(r)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 3.8))
    for r in runs:
        inp = r["inputs"]
        label = f"L={int(inp['well_spacing_m'])} m, D={int(inp['doublet_separation_m'])} m"
        t = np.asarray(r["time_days"]) / 365.0
        ax1.plot(t, r["wells"]["Producer1"]["bottomhole_temperature_c"], label=label)
    ax1.set_xlabel("Year")
    ax1.set_ylabel("Producer 1 bottomhole T (°C)")
    ax1.set_ylim(100, 107)
    ax1.grid(alpha=0.3)
    ax1.legend(fontsize=8)
    ax1.set_title("Production temperature, real monthly schedule")
    r = next(
        r
        for r in runs
        if r["inputs"]["well_spacing_m"] == 1200.0 and r["inputs"]["doublet_separation_m"] == 1500.0
    )
    t = np.asarray(r["time_days"]) / 365.0
    sel = t <= 3.0
    for w in ("Producer1", "Injector1", "Producer2", "Injector2"):
        p = (
            np.asarray(r["wells"][w]["bottomhole_pressure_bar"])
            - r["wells"][w]["initial_pressure_bar"]
        )
        ax2.plot(t[sel], p[sel], label=w)
    ax2.axhline(0, color="k", lw=0.5)
    ax2.set_xlabel("Year")
    ax2.set_ylabel("Bottomhole pressure change (bar)")
    ax2.grid(alpha=0.3)
    ax2.legend(fontsize=8)
    ax2.set_title("Pressure response, first 3 years (L=1200 m)")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main():
    """Write both figures."""
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    plot_grid(load_table(), OUTPUTS / "fimbul_temperature_sweep.png")
    plot_pick(OUTPUTS / "fimbul_pick_schedule.png")
    print(f"Figures written to {OUTPUTS}")


if __name__ == "__main__":
    main()
