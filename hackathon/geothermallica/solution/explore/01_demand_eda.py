"""Look at the two demand files: daily series and load-duration curves."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd

from geo.common import COLORS, DATA, fig_height, fig_width, plt, save

heat = pd.read_csv(DATA / "GEMINI_Heating_Demand_Daily_2027.csv", parse_dates=["date"]).set_index("date").iloc[:, 0]
cold = pd.read_csv(DATA / "GEMINI_Cooling_Demand_Daily_2027.csv", parse_dates=["date"]).set_index("date").iloc[:, 0]

for name, s in (("heat", heat), ("cold", cold)):
    print(f"{name}: {len(s)} days, peak {s.max():.2f} MW on {s.idxmax().date()}, mean {s.mean():.2f} MW, "
          f"{s.sum() * 24 / 1000:.2f} GWh/yr, days > 0: {(s > 0).sum()}")

# daily series
fig, ax = plt.subplots(figsize=(2 * fig_width, fig_height))
ax.plot(heat.index, heat, color=COLORS[0], label="heating")
ax.plot(cold.index, cold, color=COLORS[1], label="cooling")
ax.set_ylabel("daily mean power (MW)")
ax.set_xlabel("2027")
ax.legend()
fig.tight_layout()
save(fig, "01_demand_daily")

# load-duration curves
fig, ax = plt.subplots(figsize=(fig_width, fig_height))
days = np.arange(1, 366)
ax.plot(days, np.sort(heat.values)[::-1], color=COLORS[0], label="heating")
ax.plot(days, np.sort(cold.values)[::-1], color=COLORS[1], label="cooling")
ax.set_xlabel("days per year at or above")
ax.set_ylabel("power (MW)")
ax.legend()
fig.tight_layout()
save(fig, "01_demand_duration")

# how many days each number of doublets would cover at the caps (13.7 MW each, cp 4.0) [A]
per_doublet = 300 / 3600 * 1030 * 4.0 * 40 / 1000
for n in (1, 2, 3):
    short = (heat - n * per_doublet).clip(lower=0)
    print(f"{n} doublet(s) = {n * per_doublet:.1f} MW: {int((short > 0).sum())} days short, "
          f"{short.sum() * 24:.0f} MWh unmet ({100 * short.sum() / heat.sum():.1f} %)")
