"""Uncertainty of the 2-doublet, 60 C design at the 30/10 MW challenge peaks: one-at-a-time tornado plus a Latin-hypercube sample.

Why: every headline number rests on four weak inputs (PI, II, Lorenz efficiency, doublet CAPEX); a jury asks which one moves
the answer and whether the design still passes its checks. Inputs vary independently (no PI-II correlation) [A]; module
globals (plant.Producer, plant.LORENZ_EFF, year.table, year.injector_rows) are swapped per case and always restored.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np

from geo import cost, plant, year
from geo.common import COLORS, DT_BRINE_MAX_K, fig_height, fig_width, plt, save
from geo.well import Injector, Producer, sodm_limit_bar

N, T_RET, PEAK_H, PEAK_C, N_SAMPLES = 2, 60.0, 30.0, 10.0, 200
BASE = {"PI": None, "II": None, "LORENZ": 0.50, "CAPEX": 9.3}   # None = model value (Darcy PI 11.88; II from viscosity ratio) [C]
RANGES = {"PI": (11.9, 12.4, "m3/h/bar [C, research/03 DoubletCalc]"), "II": (5.5, 7.0, "m3/h/bar [C, research/03 cold brine]"),
          "LORENZ": (0.35, 0.60, "[L, research/01]"), "CAPEX": (9.3, 37.2, "MEUR/doublet [C/TBC, research/03 vs 04]")}
STRESS = [("PI", 10.6, "[C, research/03 TNO example]"), ("PI", 13.2, "[A, 500 m drainage radius]")]
OUT = ["capacity_MW", "margin_pct", "geo_share_pct", "el_GWh", "boiler_GWh", "sodm_bar", "esp_Hz", "lcoh"]


def case(PI, II, LORENZ, CAPEX):
    keep = plant.Producer, plant.LORENZ_EFF, year.table, year.injector_rows
    try:
        plant.Producer, plant.LORENZ_EFF = (lambda **k: Producer(pi=PI, **k)), LORENZ
        tab = plant.DoubletTable(T_RET)
        prod, inj, rows = Producer(stages=24, pi=PI), Injector(ii=II), []
        for q in year.Q_INJ:                     # as well.injector_at, with the overrides
            f = prod.freq_for_wellhead(q)
            r = inj.run(q, prod.run(q, f if f is not None else 60.0)["T_wellhead_C"] - DT_BRINE_MAX_K)
            rows.append({**r, "sodm_limit_bar": sodm_limit_bar(), "sodm_margin_bar": sodm_limit_bar() - r["p_bh_req_bar"]})
        year.table, year.injector_rows = (lambda *a: tab), (lambda *a: rows)
        e = cost.economics.__wrapped__(N, T_RET, PEAK_H, PEAK_C, doublet_MEUR=CAPEX)
        d = year.heating_year(N, T_RET, peak_heat_MW=PEAK_H)
        rows_ck = year.checks(N, T_RET, PEAK_H, PEAK_C)
        ok = all(c["status"].startswith("pass") for c in rows_ck)
    finally:
        plant.Producer, plant.LORENZ_EFF, year.table, year.injector_rows = keep
    cap = N * tab.out_max
    return {"capacity_MW": cap, "margin_pct": 100 * (cap / PEAK_H - 1), "geo_share_pct": 100 * (d.geo + d.hp - d.el_hp).sum() / d.demand.sum(),
            "el_GWh": e["electricity_GWh"], "boiler_GWh": d.boiler.sum() * 24 / 1000, "sodm_bar": min(r["sodm_margin_bar"] for r in rows), "esp_Hz": float(np.nanmax(tab.cols["freq_hz"])),
            "lcoh": e["lcoh_EUR_MWh"], "all_pass": ok, "n_checks": len(rows_ck), "short_60Hz": tab.w.run(300.0, 60.0)["p_wellhead_bar"] < 10.0}


t0 = time.time()
base = case(**BASE)
oat = [(k, lo, hi, tag, case(**{**BASE, k: lo}), case(**{**BASE, k: hi})) for k, (lo, hi, tag) in RANGES.items()]
stress = [(k, v, tag, case(**{**BASE, k: v})) for k, v, tag in STRESS]
t_oat = time.time() - t0
rng = np.random.default_rng(0)
u = (np.array([rng.permutation(N_SAMPLES) for _ in RANGES]).T + rng.random((N_SAMPLES, len(RANGES)))) / N_SAMPLES   # Latin hypercube
X = {k: lo + u[:, i] * (hi - lo) for i, (k, (lo, hi, _)) in enumerate(RANGES.items())}
t1 = time.time()
S = [case(**{k: X[k][j] for k in RANGES}) for j in range(N_SAMPLES)]
t_mc = time.time() - t1

hdr = "| capacity MW | peak margin % | geothermal share % | electricity GWh | backup boiler GWh | SodM margin bar | max ESP Hz | LCoH EUR/MWh |"
md = [f"Base [C]: " + ", ".join(f"{k} {base[k]:.2f}" for k in OUT) + f"; all {base['n_checks']} checks pass: {base['all_pass']}", "",
      "One at a time, change from base at low / high [C]", "", "| input | low / high |" + hdr[1:], "|---" * 10 + "|"]
for k, lo, hi, tag, a, b in oat:
    md.append(f"| {k} {tag} | {lo:g} / {hi:g} | " + " | ".join(f"{a[o] - base[o]:+.2f} / {b[o] - base[o]:+.2f}" for o in OUT)
              + f" |{'' if a['all_pass'] and b['all_pass'] else ' (checks fail at one end)'}")
for k, v, tag, a in stress:
    md.append(f"| {k} stress {tag} | {v:g} | " + " | ".join(f"{a[o] - base[o]:+.2f}" for o in OUT)
              + f" |{' 60 Hz short of 10 bar wellhead' if a['short_60Hz'] else ''}{'' if a['all_pass'] else ' checks FAIL'}")
P = {o: np.percentile([s[o] for s in S], [10, 50, 90]) for o in OUT}
md += ["", f"Latin hypercube, N = {N_SAMPLES}, seed 0, uniform over the four ranges [C]", "", "| output | p10 | p50 | p90 |", "|---|---|---|---|"]
md += [f"| {o} | {p[0]:.2f} | {p[1]:.2f} | {p[2]:.2f} |" for o, p in P.items()]
md += ["", f"Samples passing all {base['n_checks']} checks: {np.mean([s['all_pass'] for s in S]):.1%}; 60 Hz short: {np.mean([s['short_60Hz'] for s in S]):.1%} [C]",
       f"Samples firing the backup boiler (> 1 MWh: capacity below a peak day): {np.mean([s['boiler_GWh'] > 1e-3 for s in S]):.1%} [C]",
       f"Runtime: {len(oat) * 2 + len(stress) + 1} OAT cases {t_oat:.1f} s, {N_SAMPLES} samples {t_mc:.1f} s ({t_mc / N_SAMPLES:.2f} s each) [C]"]
out = Path(__file__).resolve().parent / "tables"
(out / "09_uq.md").write_text("\n".join(md) + "\n")
print("\n".join(md))

fig, ax = plt.subplots(1, 3, figsize=(2 * fig_width, fig_height))
for a, o, lab in ((ax[0], "lcoh", r"$\Delta$ LCoH (EUR/MWh)"), (ax[1], "geo_share_pct", r"$\Delta$ geothermal share (\%-points)")):
    rows = sorted(oat, key=lambda r: abs(r[5][o] - r[4][o]))
    y = np.arange(len(rows))
    a.barh(y, [r[4][o] - base[o] for r in rows], color=COLORS[0], label="low")
    a.barh(y, [r[5][o] - base[o] for r in rows], color=COLORS[1], label="high")
    a.axvline(0, color="k", lw=0.5)
    a.set(yticks=y, yticklabels=[r[0] for r in rows], xlabel=lab)
ax[0].legend(fontsize=7)
lc = np.sort([s["lcoh"] for s in S])
ax[2].step(lc, np.arange(1, N_SAMPLES + 1) / N_SAMPLES, color=COLORS[0], where="post")
ax[2].axvline(base["lcoh"], color="0.5", ls="--", lw=0.8)
ax[2].set(xlabel="LCoH (EUR/MWh)", ylabel="ECDF", title=f"N = {N_SAMPLES}")
save(fig, "09_uq")
