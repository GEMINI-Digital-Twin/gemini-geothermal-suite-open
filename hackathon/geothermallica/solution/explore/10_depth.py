"""Depth sensitivity of the 2-doublet, 60 C design at the 30/10 MW peaks, 2 000-3 500 m, every other input as in 01-08.

Why: a brief may name another depth; the tools now accept it (3 Nov). Deeper brine is hotter, but under the brief's 40 K
cooling cap a doublet still delivers q x rho x cp x 40 K, so the exchanger replaces the heat pump and the capacity hardly
moves. Caveats carried from the tables: 24 ESP stages sized at 2 500 m [A], the doublet price 9.3 MEUR at every depth
[A, no sourced depth curve], SodM limit 0.135 bar/m at 50 m above the datum depth [A], reservoir pressure 250 bar at 2 500 m [D]
plus a brine hydrostatic gradient off it [A].
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from geo import cost, year
from geo.common import t_reservoir_c

DEPTHS, N, T_RET, PEAK_H, PEAK_C = (2000, 2250, 2500, 2750, 3000, 3250, 3500), 2, 60.0, 30.0, 10.0
gwh = lambda s: float(s.sum() * 24 / 1000)


def row(dm):
    tab, d = year.table(T_RET, float(dm)), year.heating_year(N, T_RET, peak_heat_MW=PEAK_H, depth_m=float(dm))
    ck, e = year.checks(N, T_RET, PEAK_H, PEAK_C, depth_m=float(dm)), cost.economics(N, T_RET, PEAK_H, PEAK_C, depth_m=float(dm))
    worst, c = min(year.injector_rows(float(dm)), key=lambda r: r["sodm_margin_bar"]), {k: v[-1] for k, v in tab.cols.items()}   # last row: 300 m3/h
    n_ok = next((n for n in (1, 2, 3) if all(x["status"].startswith("pass") for x in year.checks(n, T_RET, PEAK_H, PEAK_C, depth_m=float(dm)))), "none")
    return [f"{dm}", f"{t_reservoir_c(dm):.0f}", f"{c['T_wh_C']:.1f}", f"{c['freq_hz']:.1f}", f"{c['MW_hx']:.2f} / {c['MW_hp']:.2f} / {c['MW_el_hp']:.2f}",
            f"{N * tab.out_max:.2f}", f"{100 * (N * tab.out_max / PEAK_H - 1):+.1f}", f"{gwh(d.el_hp):.2f}", f"{gwh(d.boiler):.2f}",
            f"{100 * (gwh(d.geo) + gwh(d.hp) - gwh(d.el_hp)) / gwh(d.demand):.1f}", f"{worst['sodm_margin_bar']:.1f}", f"{e['lcoh_EUR_MWh']:.1f}",
            f"{sum(x['status'].startswith('pass') for x in ck)}/{len(ck)}", f"{n_ok}"]


head = ["depth m", "T_res C", "T_wh C at 300 m3/h", "ESP Hz", "exchanger / heat pump / HP electricity MW per doublet", "capacity MW (2 doublets)",
        "peak margin %", "HP electricity GWh", "boiler GWh", "geothermal share %", "SodM margin bar", "LCoH EUR/MWh", "checks", "smallest n passing all"]
md = ["# Depth sensitivity, 2 doublets at a 60 C return, 30/10 MW peaks [C; 24 stages, 9.3 MEUR per doublet, the SodM datum and the hydrostatic pressure gradient are A off 2 500 m]", "",
      "| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join(row(dm)) + " |" for dm in DEPTHS]
print("\n".join(md))
(Path(__file__).parent / "tables" / "10_depth.md").write_text("\n".join(md) + "\n")
