"""Daily proof that the pick keeps every hard rule, all 365 days (KNMI Schiphol 2025).

Runs the final pick for a year and plots, per day: doublets running, flow per running
doublet against the 50-300 m3/h caps, brine cooling against the 40 K cap, and heat and
cooling supplied against demand, stacked by source.

    PYTHONPATH=src:simulator_examples python docs/figures/make_compliance_figure.py

Writes docs/figures/fig_compliance.png.
"""

import sys
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "simulator_examples")]

from gemini_agent.tools import make_design  # noqa: E402
from gemini_design.annual import run_year  # noqa: E402
from gemini_design.challenge import load_demand  # noqa: E402
from gemini_design.climate import read_knmi_daily, with_climate  # noqa: E402
from run_final_pick import PICK  # noqa: E402
from run_full_screen import INPUTS  # noqa: E402

KNMI = ROOT / "simulator_examples" / "weather" / "knmi_etmgeg_240_1991_2025.txt"
OUT = Path(__file__).with_name("fig_compliance.png")
INK, MUTED, LIMIT = "#14213D", "#5A6474", "#B03A2E"


def main():
    climate = with_climate(load_demand(INPUTS), read_knmi_daily(KNMI, 2025), "max")
    peaks = float(climate["heating_mw"].max()), float(climate["cooling_mw"].max())
    design = make_design(PICK, *peaks)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        d, s = run_year(design, climate)
    t = pd.to_datetime(d["date"])
    mw = 1e-6
    fig, ax = plt.subplots(4, 1, figsize=(10, 9), dpi=200, sharex=True,
                           gridspec_kw={"height_ratios": [1, 1, 1.4, 1.2]})

    a = ax[0]
    a.fill_between(t, d["flow_per_doublet_m3h"].where(d["n_active"] > 0), step="mid",
                   color="#C2501E", alpha=0.85, lw=0)
    for y in (50, 300):
        a.axhline(y, color=LIMIT, lw=1, ls="--")
    a.text(t.iloc[2], 308, "300 m³/h cap", color=LIMIT, fontsize=7, va="bottom")
    a.text(t.iloc[2], 56, "50 m³/h minimum", color=LIMIT, fontsize=7, va="bottom")
    maint = d["n_available"] < 2
    by_choice = (d["n_active"] == 1) & ~maint
    a.fill_between(t, 0, 330, where=maint, step="mid", color="#8A93A3", alpha=0.35, lw=0)
    a.fill_between(t, 0, 330, where=by_choice, step="mid", color="#D9D5CB", alpha=0.45, lw=0)
    mid = lambda m: t[m].iloc[len(t[m]) // 2]  # noqa: E731
    a.text(t[maint].iloc[0], 292, "  one doublet in planned\n  maintenance (35 days each)",
           fontsize=6.5, color=INK, va="top")
    a.text(mid(by_choice & (t.dt.month < 6)), 230, "one doublet\nis enough",
           fontsize=6.5, color=MUTED, ha="center")
    a.set_ylim(0, 340)
    a.set_ylabel("flow per\nrunning doublet\nm³/h", fontsize=8)

    a = ax[1]
    a.plot(t, d["brine_cooling_k"], color="#C2501E", lw=1)
    a.axhline(40, color=LIMIT, lw=1, ls="--")
    a.text(t.iloc[2], 41, "40 K cap", color=LIMIT, fontsize=7, va="bottom")
    a.set_ylim(0, 46)
    a.set_ylabel("brine cooling\nproducer→injector\nK", fontsize=8)

    a = ax[2]
    parts = [("hex_heat_w", "geothermal heat exchanger", "#C2501E"),
             ("chp_heat_w", "CHP on co-produced gas", "#E59866"),
             ("boiler_heat_w", "boiler", "#8A93A3")]
    a.stackplot(t, *[d[c] * mw for c, _, _ in parts], labels=[lab for _, lab, _ in parts],
                colors=[c for _, _, c in parts], step="mid", lw=0)
    a.plot(t, d["heating_demand_w"] * mw, color=INK, lw=0.8, label="heating demand")
    a.set_ylabel("heat at 100 °C\nMW", fontsize=8)
    a.legend(fontsize=7, frameon=False, loc="upper center", ncol=4)
    a.set_ylim(0, 36)

    a = ax[3]
    chiller = d["cooling_delivered_w"] - d["free_cooling_w"] - d["ates_cooling_w"]
    parts = [(d["free_cooling_w"], "free cooling (outdoor air)", "#7FB3D5"),
             (d["ates_cooling_w"], "aquifer cold store (ATES)", "#1F6FA8"),
             (chiller, "air-cooled chiller", "#8A93A3")]
    a.stackplot(t, *[p * mw for p, _, _ in parts], labels=[lab for _, lab, _ in parts],
                colors=[c for _, _, c in parts], step="mid", lw=0)
    a.plot(t, d["cooling_demand_w"] * mw, color=INK, lw=0.8, label="cooling demand")
    a.set_ylabel("cooling at 20 °C\nMW", fontsize=8)
    a.legend(fontsize=7, frameon=False, loc="upper left", ncol=2)
    a.set_ylim(0, 12)

    for a in ax:
        for sp in ("top", "right"):
            a.spines[sp].set_visible(False)
        a.tick_params(labelsize=7)
    unmet = (d["unmet_heat_w"].sum() + d["unmet_cooling_w"].sum()) * 24 * mw
    ok = all(s["checks"].values())
    fig.suptitle(f"Every hard rule, every day: {'all checks pass' if ok else 'CHECK FAILED'}, "
                 f"unmet demand {unmet:.0f} MWh", fontsize=10, color=INK, x=0.02, ha="left")
    fig.tight_layout()
    fig.savefig(OUT)
    print(OUT, s["checks"])


if __name__ == "__main__":
    main()
