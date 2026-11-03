"""Daily dispatch of two doublets against the heating CSV: follow load, staggered outages, boiler for the rest."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from geo.common import COLORS, DATA, fig_height, fig_width, plt, save
from geo.year import BACKUP_BOILER_MW, heating_year, table

N_DOUBLETS = 2
T_RETURN_C = 60.0            # design variable, see script 04 [A]
OUTAGES = {0: ("2027-06-01", "2027-07-05"), 1: ("2027-08-01", "2027-09-04")}   # 35 days each, staggered [A]
GREY = (0.55, 0.57, 0.62)

tab = table(T_RETURN_C)
print(f"one doublet at {T_RETURN_C:.0f} C return: {tab.out_min:.2f} MW at {tab.q[0]:.0f} m3/h .. {tab.out_max:.2f} MW at {tab.q[-1]:.0f} m3/h")

d = heating_year(N_DOUBLETS, T_RETURN_C, OUTAGES)
for c in ("geo", "hp", "el_hp"):
    d[c + "_used"] = d[c]

gwh = lambda s: s.sum() * 24 / 1000
print(f"demand {gwh(d.demand):.2f} GWh | brine heat above 78 C left for absorption {gwh(d.surplus):.2f} GWh on "
      f"{int((d.surplus > 0.01).sum())} days, max {d.surplus.max():.1f} MW | unmet {gwh(d.unmet):.3f} GWh")
peak = d.demand.idxmax()
print(f"peak {peak.date()}: {d.demand[peak]:.1f} MW with {int(d.doublets_on[peak])} doublets at {d.q_m3h[peak]:.0f} m3/h each, "
      f"capacity {2 * tab.out_max:.2f} MW, margin {100 * (2 * tab.out_max / d.demand[peak] - 1):.1f} %; "
      f"N-1 at the peak: one doublet {tab.out_max:.2f} MW + boiler {BACKUP_BOILER_MW:.0f} MW = {tab.out_max + BACKUP_BOILER_MW:.1f} MW")
print(f"doublets on: {int((d.doublets_on == 2).sum())} days both, {int((d.doublets_on == 1).sum())} days one")
print(f"served: exchanger {gwh(d.geo_used):.2f} + heat pump {gwh(d.hp_used):.2f} (of which electricity {gwh(d.el_hp_used):.2f}) "
      f"+ boiler {gwh(d.boiler):.2f} = {gwh(d.geo_used) + gwh(d.hp_used) + gwh(d.boiler):.2f} GWh")
print(f"geothermal share of served heat {(gwh(d.geo_used) + gwh(d.hp_used) - gwh(d.el_hp_used)) / gwh(d.demand) * 100:.1f} %, "
      f"electricity share {gwh(d.el_hp_used) / gwh(d.demand) * 100:.1f} %, boiler share {gwh(d.boiler) / gwh(d.demand) * 100:.1f} %; "
      f"ESP electricity {gwh(d.esp):.2f} GWh; boiler used on {int((d.boiler > 0.01).sum())} days, max {d.boiler.max():.2f} MW")

fig, ax = plt.subplots(figsize=(2 * fig_width, 1.2 * fig_height))
ax.stackplot(d.index, d.geo, d.hp, d.boiler, colors=[COLORS[0], COLORS[2], COLORS[1]],
             labels=["geothermal via exchanger", "heat pump (brine source)", "boiler"], alpha=0.85)
ax.plot(d.index, d.demand, color="k", lw=0.8, label="demand")
ax.plot(d.index, -d.surplus, color=GREY, lw=0.8, label="brine heat above 78 C left for absorption (below axis)")
ax.set_ylabel("MW (daily mean)")
ax.set_xlabel("2027")
ax.legend(fontsize=7, ncol=3)
fig.tight_layout()
save(fig, "05_dispatch")
d.to_csv(DATA.parent.parent / "processed" / "solution_05_dispatch_daily.csv")

# second reading of "330 days": the whole plant off together, 9 Jul to 12 Aug (35 days) [A]
plant_wide = {i: ("2027-07-09", "2027-08-12") for i in range(N_DOUBLETS)}
for name, dd in (("staggered (default)", d), ("plant-wide 9 Jul-12 Aug", heating_year(N_DOUBLETS, T_RETURN_C, plant_wide))):
    print(f"{name}: boiler {gwh(dd.boiler):.2f} GWh, max {dd.boiler.max():.2f} MW, on {int((dd.boiler > 0.01).sum())} days, "
          f"unmet {gwh(dd.unmet):.3f} GWh [C, A]")
