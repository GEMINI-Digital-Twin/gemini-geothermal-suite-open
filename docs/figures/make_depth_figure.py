"""Deep well versus shallow well + heat pump (the brief's own example), same plant otherwise.

Reads simulator_examples/study_results/2026-11-04/new_defaults/shallow_wells/results.csv (from
run_shallow_wells.py, new defaults): 2 doublets, CHP, free cooling + ATES +
air-cooled chiller, KNMI 2025.
Writes docs/figures/fig_depth.png.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CSV = ROOT / "simulator_examples/study_results/2026-11-04/new_defaults/shallow_wells/results.csv"

d = pd.read_csv(CSV)
d = d[(d.n_doublets == 2) & d.chp & d.cooling_option.str.contains("ATES")]
fig, ax = plt.subplots(1, 2, figsize=(10, 3.8), dpi=200)
style = {"boiler": ("#C2501E", "heat exchanger + boiler top-up"),
         "heat_pump": ("#1F6FA8", "heat pump lifts to 100 °C")}
for up, (c, lab) in style.items():
    g = d[d.upgrade == up].sort_values("depth_m")
    km = g.depth_m / 1000
    ax[0].plot(km, g.lcoe_eur_per_mwh, "o-", color=c, label=lab, ms=4)
    ax[1].plot(km, g.co2_t_per_year / 1000, "o-", color=c, label=lab, ms=4)
for a in ax:
    a.axvline(3.1, color="#14213D", lw=0.8, ls=":")
    a.axvline(2.5, color="#8A93A3", lw=0.8, ls=":")
    sec = a.secondary_xaxis("top", functions=(lambda x: 12 + 30 * x, lambda t: (t - 12) / 30))
    sec.set_xlabel("reservoir temperature, °C", fontsize=8)
    sec.tick_params(labelsize=7)
    a.set_xlabel("well depth, km", fontsize=8)
    a.tick_params(labelsize=7)
    for s in ("right",):
        a.spines[s].set_visible(False)
ax[0].set_ylabel("LCOE, €/MWh", fontsize=8)
ax[1].set_ylabel("CO₂, kt/yr", fontsize=8)
ax[0].legend(fontsize=7, frameon=False)
ax[0].text(3.12, ax[0].get_ylim()[1] * 0.97, "pick 3.1 km", fontsize=7, va="top")
ax[0].text(2.52, ax[0].get_ylim()[1] * 0.97, "brief 2.5 km", fontsize=7, va="top", color="#5A6474")
fig.tight_layout()
fig.savefig(Path(__file__).with_name("fig_depth.png"))
