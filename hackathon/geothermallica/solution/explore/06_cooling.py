"""Cooling at 20 C supply: free cooling from the wet bulb first, then absorption on the brine heat not needed for heating, electric for the rest.

Absorption takes the hot end of the brine (>= 78 C) before the heating exchanger; script 05 reports how much of that is free."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd

from geo.common import COLORS, PROJECT, fig_height, fig_width, plt, save
from geo.plant import T_ABS_MIN_C, DoubletTable
from geo.year import AUX_KW_PER_KW_COLD, COP_ABSORPTION, COP_ELECTRIC, cooling_year

disp = pd.read_csv(PROJECT / "data" / "processed" / "solution_05_dispatch_daily.csv", parse_dates=["date"]).set_index("date")
c, _ = cooling_year(disp.surplus)
cold, free, absorption, electric = c.cold, c.free, c.absorption, c.electric
twb, free_frac, drive_avail, drive_needed = c.T_wb, c.free_frac, c.drive_avail, c.drive_needed
rest = cold - free

gwh = lambda s: s.sum() * 24 / 1000
print(f"cold demand {gwh(cold):.2f} GWh: free cooling {gwh(free):.2f} ({gwh(free) / gwh(cold) * 100:.0f} %), "
      f"absorption on surplus heat {gwh(absorption):.2f} ({gwh(absorption) / gwh(cold) * 100:.0f} %), "
      f"electric {gwh(electric):.2f} ({gwh(electric) / gwh(cold) * 100:.0f} %)")
print(f"drive heat used {gwh(absorption / COP_ABSORPTION):.2f} GWh of {gwh(drive_avail):.2f} GWh surplus; "
      f"electricity: chillers {gwh(electric / COP_ELECTRIC):.2f} GWh + auxiliaries {gwh(cold * AUX_KW_PER_KW_COLD):.2f} GWh; "
      f"peak day {cold.idxmax().date()}: wet bulb {twb[cold.idxmax()]:.1f} C, free {free_frac[cold.idxmax()] * 100:.0f} %, "
      f"drive needed {drive_needed[cold.idxmax()]:.1f} MW vs surplus {drive_avail[cold.idxmax()]:.1f} MW")
print(f"electricity for this stack {gwh(electric / COP_ELECTRIC) + gwh(cold * AUX_KW_PER_KW_COLD):.2f} GWh (chillers + auxiliaries)")
print(f"all-electric alternative: {gwh(cold / COP_ELECTRIC):.2f} GWh electricity without free cooling, "
      f"{gwh(rest / COP_ELECTRIC):.2f} with")

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(2 * fig_width, fig_height))
ax1.stackplot(cold.index, free, absorption, electric, colors=[COLORS[2], COLORS[0], COLORS[1]],
              labels=["free cooling (wet bulb)", "absorption on surplus heat", "electric chiller"], alpha=0.85)
ax1.set_ylabel("cold (MW, daily mean)")
ax1.set_xlabel("2027")
ax1.legend(fontsize=7)
ax2.plot(cold.index, drive_avail, color=COLORS[0], label="brine heat above 78 C left after heating (script 05)")
ax2.plot(cold.index, drive_needed, color=COLORS[1], label="absorption drive heat needed")
ax2.set_ylabel("MW")
ax2.set_xlabel("2027")
ax2.legend(fontsize=7)
fig.tight_layout()
save(fig, "06_cooling")
c.drop(columns="free_frac").to_csv(
    PROJECT / "data" / "processed" / "solution_06_cooling_daily.csv")

# sensitivity: daily mean instead of daily maximum wet bulb [A]
for name, agg in (("daily maximum", "max"), ("daily mean", "mean")):
    cc, _ = cooling_year(disp.surplus, agg)
    print(f"free cooling with {name} wet bulb: {gwh(cc.free) / gwh(cold) * 100:.0f} % of cold energy [C, A]")

# peak cooling day: electric chiller for the cold absorption cannot cover, vs starting doublet 2 at the pump floor for drive
fl = {key: v[0] for key, v in DoubletTable(60.0).cols.items()}
pk = cold.idxmax()
cold_d2 = fl["mcp_MW_per_K"] * (fl["T_wh_C"] - T_ABS_MIN_C) * COP_ABSORPTION   # MW cold from doublet 2's hot slice
print(f"peak cooling day {pk.date()}: electric chiller for {electric[pk]:.2f} MW uncovered cold {electric[pk] / COP_ELECTRIC * 1000:.0f} kW; "
      f"doublet 2 at {fl['q_m3h']:.0f} m3/h ESP {fl['kW_esp']:.0f} kW gives {cold_d2:.2f} MW cold "
      f"(chiller would need {cold_d2 / COP_ELECTRIC * 1000:.0f} kW for it) -> "
      f"{'electric chiller' if cold_d2 / COP_ELECTRIC * 1000 < fl['kW_esp'] else 'doublet 2'} is cheaper; doublet 2's injection pump (~170 kW) not counted, which would make it worse [C, A]")
