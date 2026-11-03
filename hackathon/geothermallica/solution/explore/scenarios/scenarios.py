"""Design scenarios side by side: boiler vs heat pump, doublet count, return temperature, heat-pump efficiency."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import numpy as np

from geo import plant
from geo.common import COLORS, DT_BRINE_MAX_K, Q_MAX_M3H, RHO, T_SUPPLY_HEAT_C, fig_height, fig_width, plt
from geo.well import Producer
from geo.year import heat, heating_year

OUT = Path(__file__).resolve().parents[1] / "figures"


def layout_a(tab):
    """Exchanger + boiler: the boiler lifts the exchanger water from T_wh - 3 to 100 C (as script 04)."""
    c = tab.cols
    share = (T_SUPPLY_HEAT_C - (c["T_wh_C"] - plant.APPROACH_K)) / (T_SUPPLY_HEAT_C - tab.t_return_c)
    out = c["MW_hx"] / (1 - share)

    def point(mw):
        if mw <= out[0]:
            hx = mw / out[0] * c["MW_hx"][0]
            return {"MW_out": mw, "MW_hx": hx, "MW_hp": 0.0, "MW_el_hp": 0.0, "MW_boiler_lift": mw - hx, "kW_esp": c["kW_esp"][0]}
        mw = min(mw, out[-1])
        hx = np.interp(mw, out, c["MW_hx"])
        return {"MW_out": mw, "MW_hx": hx, "MW_hp": 0.0, "MW_el_hp": 0.0, "MW_boiler_lift": mw - hx,
                "kW_esp": np.interp(mw, out, c["kW_esp"])}
    return point


def year(point, n):
    """heating_year (script 05's dispatch, staggered 35-d outages) with this layout's operating point: GWh and shares."""
    d = heating_year(n, None, point=point)
    gwh = lambda x: x.sum() * 24 / 1000
    g = {k: gwh(d[col]) for k, col in (("geo", "geo"), ("hp", "hp"), ("el_hp", "el_hp"), ("esp", "esp"), ("lift", "boiler_lift"))}
    g["short"] = gwh(d.boiler_peak + d.unmet)
    dem = gwh(d.demand)
    g.update(boiler=g["lift"] + g["short"], el=g["el_hp"] + g["esp"], sh_geo=100 * (g["geo"] + g["hp"] - g["el_hp"]) / dem,
             sh_el=100 * g["el_hp"] / dem, sh_boiler=100 * (g["lift"] + g["short"]) / dem)
    return g


def table_at(t_ret, eff=0.50):
    plant.LORENZ_EFF, keep = eff, plant.LORENZ_EFF
    tab = plant.DoubletTable(t_ret)
    plant.LORENZ_EFF = keep
    return tab


tabs = {t: table_at(t) for t in (40, 50, 60, 70)}
ra = {t: (year(layout_a(tabs[t]), 2), year(tabs[t].at_output, 2)) for t in tabs}
peak = heat.max()
rb = {n: year(tabs[60].at_output, n) | {"margin": 100 * (n * tabs[60].out_max / peak - 1)} for n in (1, 2, 3)}
w = Producer(stages=24)
rc = []
for t in range(30, 71, 5):
    r = plant.doublet_at(w, Q_MAX_M3H, t)
    share = (T_SUPPLY_HEAT_C - (r["T_wh_C"] - plant.APPROACH_K)) / (T_SUPPLY_HEAT_C - t)
    rc.append((t, r["MW_hx"], r["MW_hx"] / (1 - share), r["MW_hx"] + r["MW_hp"], 100 * r["MW_el_hp"] / (r["MW_hx"] + r["MW_hp"])))
cap = Q_MAX_M3H / 3600 * RHO * plant.CP * DT_BRINE_MAX_K / 1000
rd = {e: year((tabs[60] if e == 0.50 else table_at(60, e)).at_output, 2) for e in (0.35, 0.50, 0.60)}

print("(a) 2 doublets, annual shares of served heat (%) [C]\n return  A geo  A el  A boiler | B geo  B el  B boiler")
for t, (a, b) in ra.items():
    print(f"{t:6d} {a['sh_geo']:6.1f} {a['sh_el']:5.1f} {a['sh_boiler']:8.1f} | {b['sh_geo']:5.1f} {b['sh_el']:5.1f} {b['sh_boiler']:8.1f}")
print(f"(b) layout B, 60 C return, peak {peak:.1f} MW [C]\n doublets  unmet before backup (GWh)  peak margin (%)")
for n, r in rb.items():
    print(f"{n:8d} {r['short']:26.2f} {r['margin']:16.1f}")
print(f"(c) per doublet at {Q_MAX_M3H:.0f} m3/h [C]; 40 K cap {cap:.2f} MW\n return  A geo MW  A with boiler MW  B MW at 100 C  B el/heat (%)")
for t, a, ab, b, e in rc:
    print(f"{t:6d} {a:8.2f} {ab:16.2f} {b:14.2f} {e:14.1f}")
print("(d) layout B, 60 C return, 2 doublets [C]\n Lorenz eff  electricity HP+ESP (GWh)  geo share (%)  boiler (GWh)")
for e, r in rd.items():
    print(f"{e:10.2f} {r['el']:24.2f} {r['sh_geo']:14.1f} {r['boiler']:13.2f}")

fig, ax = plt.subplots(2, 2, figsize=(2 * fig_width, 2 * fig_height))
x, bw = np.arange(len(ra)), 0.38
for off, li, lab in ((-bw / 2, 0, "A"), (bw / 2, 1, "B")):
    bottom = np.zeros(len(ra))
    for key, col, name in (("sh_geo", COLORS[0], "geothermal"), ("sh_el", COLORS[2], "electricity"), ("sh_boiler", COLORS[1], "boiler")):
        v = np.array([ra[t][li][key] for t in ra])
        ax[0, 0].bar(x + off, v, bw, bottom=bottom, color=col, edgecolor="k", lw=0.3, label=name if li == 0 else None)
        bottom += v
    for xi in x:
        ax[0, 0].text(xi + off, 101.5, lab, ha="center", fontsize=7)
ax[0, 0].set(xticks=x, xticklabels=[str(t) for t in ra], xlabel=r"network return ($^\circ$C)", ylabel=r"share of served heat (\%)",
             title="(a) A: exchanger + boiler, B: + heat pump", ylim=(0, 125))
ax[0, 0].legend(fontsize=7, loc="upper center", ncol=3, framealpha=1)
n = np.array(list(rb))
for vals, off, col, name in (([rb[k]["short"] for k in n], -0.2, COLORS[1], "unmet before backup (GWh)"),
                             ([rb[k]["margin"] for k in n], 0.2, COLORS[0], r"peak margin (\%)")):
    bars = ax[0, 1].bar(n + off, vals, 0.4, color=col, label=name)
    ax[0, 1].bar_label(bars, fmt="%.1f", fontsize=7)
ax[0, 1].axhline(0, color="k", lw=0.5)
ax[0, 1].set(xticks=n, xlabel="doublets (layout B, 60 C return)", title="(b) why two doublets")
ax[0, 1].legend(fontsize=7)
t = [r[0] for r in rc]
ax[1, 0].plot(t, [r[1] for r in rc], color=COLORS[0], label="A: exchanger only (geothermal MW)")
ax[1, 0].plot(t, [r[3] for r in rc], color=COLORS[1], label="B: exchanger + heat pump (MW at 100 C)")
ax[1, 0].axhline(cap, color="0.5", lw=0.8, label="40 K cap (brine heat)")
ax[1, 0].set(xlabel=r"network return ($^\circ$C)", ylabel="per doublet at 100 C (MW)", title="(c) return temperature")
tw = ax[1, 0].twinx()
tw.plot(t, [r[4] for r in rc], color=COLORS[2], ls="--", label=r"B: electricity / heat (\%)")
tw.set_ylabel(r"B: electricity / heat (\%)")
ax[1, 0].legend(handles=ax[1, 0].get_lines() + tw.get_lines(), fontsize=7, loc="lower left", framealpha=1)
e = np.arange(len(rd))
for vals, off, col, name in (([r["el"] for r in rd.values()], -0.27, COLORS[2], "electricity HP + ESP (GWh)"),
                             ([r["sh_geo"] for r in rd.values()], 0.0, COLORS[0], r"geothermal share (\%)"),
                             ([r["boiler"] for r in rd.values()], 0.27, COLORS[1], "boiler (GWh)")):
    ax[1, 1].bar_label(ax[1, 1].bar(e + off, vals, 0.27, color=col, label=name), fmt="%.1f", fontsize=7)
ax[1, 1].set(xticks=e, xticklabels=[f"{k:.2f}" for k in rd], xlabel="Lorenz efficiency (layout B, 60 C)",
             title="(d) heat-pump efficiency", ylim=(0, 140))
ax[1, 1].legend(fontsize=7, loc="upper center", ncol=2, framealpha=1)
fig.tight_layout()
OUT.mkdir(exist_ok=True)
for ext in ("pdf", "png"):
    fig.savefig(OUT / f"scenarios.{ext}", dpi=300)
print("saved", OUT / "scenarios.pdf")

a40, b60 = ra[40], ra[60]
print(f"(a) At a 40 C return the boiler supplies {a40[0]['sh_boiler']:.0f} % (A) and {a40[1]['sh_boiler']:.0f} % (B) of the heat; at 60 C "
      f"the heat pump takes it to {b60[1]['sh_boiler']:.1f} % for {b60[1]['sh_el']:.1f} % electricity, against {b60[0]['sh_boiler']:.0f} % boiler in A.")
print(f"(b) One doublet leaves {rb[1]['short']:.1f} GWh unmet and is {-rb[1]['margin']:.0f} % short at the peak; two cover the year with "
      f"{rb[2]['margin']:.1f} % peak margin; a third adds margin ({rb[3]['margin']:.0f} %) but no heat.")
print(f"(c) Up to a 40 C return the exchanger alone uses the whole 40 K ({cap:.1f} MW) and the heat pump has nothing to take; at 60 C "
      f"the exchanger gives {rc[6][1]:.1f} MW while B still delivers {rc[6][3]:.1f} MW at 100 C, for {rc[6][4]:.0f} % electricity per unit heat.")
print(f"(d) Across Lorenz 0.35-0.60 electricity moves {rd[0.35]['el']:.1f} to {rd[0.60]['el']:.1f} GWh and geothermal share "
      f"{rd[0.35]['sh_geo']:.1f} to {rd[0.60]['sh_geo']:.1f} %, with boiler {max(r['boiler'] for r in rd.values()):.2f} GWh at most: the efficiency moves cost, not the design.")
