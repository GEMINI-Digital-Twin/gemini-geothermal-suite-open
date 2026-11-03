"""Size the ESP with GEMINI's pump model: which frequency and stages lift 50-300 m3/h to a 10 bar wellhead, and at what power."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np

from geo.common import COLORS, Q_MAX_M3H, Q_MIN_M3H, fig_height, fig_width, plt, save
from geo.well import Producer

P_WH_TARGET_BAR = 10.0   # [A]
F_PICK_HZ = 58.5         # stage pick: 300 m3/h reached at or below this, 1.5 Hz margin for decline [A]
GREY = (0.55, 0.57, 0.62)

# pick the stage count: the smallest that reaches 300 m3/h at a 10 bar wellhead at or below 58.5 Hz (1.5 Hz margin for decline) [A]
for stages in range(10, 80, 2):
    w = Producer(stages=stages)
    f = w.freq_for_wellhead(Q_MAX_M3H, P_WH_TARGET_BAR)
    if f is not None and f <= F_PICK_HZ:
        break
# PI from the Darcy formula in well.py:  PI = 2 pi k h / (mu ln(r_e / r_w)), with r_e = well spacing (DoubletCalc)
print(f"PI {w.pi:.1f} m3/h/bar (DoubletCalc radius {1300} m) [C], T_res {w.t_res_c:.0f} C, ESP at {w.esp_depth_m:.0f} m, "
      f"{stages} stages, envelope {w.q_min:.0f}-{w.q_max:.0f} m3/h, 300 m3/h needs {f:.1f} Hz")

# GEMINI scales head by (f/60)^2 but reads the curve at the actual flow; the similarity (affinity) law reads it at q*60/f.
# Producer uses the similarity law by default (F5); affinity=False reproduces GEMINI's own law for comparison.
f_gem = Producer(stages=stages, affinity=False).freq_for_wellhead(Q_MAX_M3H, P_WH_TARGET_BAR)
print(f"300 m3/h at 10 bar: similarity law {f:.1f} Hz, GEMINI head law {f_gem:.1f} Hz (GEMINI overstates head at reduced speed) [C]")

q = np.linspace(Q_MIN_M3H, Q_MAX_M3H, 26)
rows = []
for qi in q:
    fi = w.freq_for_wellhead(qi, P_WH_TARGET_BAR)
    rows.append(w.run(qi, fi if fi is not None else 60.0) | {"feasible": fi is not None})
for r in rows[::5]:
    print(f"q {r['q_m3h']:5.0f}  f {r['freq_hz']:4.1f} Hz  intake {r['p_esp_intake_bar']:5.1f} bar  head {r['esp_head_bar']:5.1f} bar  "
          f"wellhead {r['p_wellhead_bar']:5.1f} bar  T_wh {r['T_wellhead_C']:4.1f} C  ESP {r['esp_electric_kW']:5.0f} kW  "
          f"{'ok' if r['in_envelope'] else 'outside envelope'}")

f_hz = np.array([r["freq_hz"] for r in rows])
head = np.array([r["esp_head_bar"] for r in rows])
kw = np.array([r["esp_electric_kW"] for r in rows])
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(2 * fig_width, fig_height))
ax1.plot(q, head, color=COLORS[0], label="ESP head needed (10 bar wellhead)")
ax1.set_xlabel(r"flow (m$^3$/h)")
ax1.set_ylabel("head (bar)")
ax1b = ax1.twinx()
ax1b.plot(q, f_hz, color=COLORS[1], ls="--", label="frequency")
ax1b.set_ylabel("frequency (Hz)")
ax1b.axhline(60, color=GREY, lw=0.8)
h1, l1 = ax1.get_legend_handles_labels()
h2, l2 = ax1b.get_legend_handles_labels()
ax1.legend(h1 + h2, l1 + l2, loc="upper left")
ax2.plot(q, kw, color=COLORS[0], label=r"ESP electric, $\eta$ = 0.70")
ax2.set_xlabel(r"flow (m$^3$/h)")
ax2.set_ylabel("power (kW)")
ax2b = ax2.twinx()
ax2b.plot(q, kw / q, color=COLORS[1], ls="--", label=r"specific energy")
ax2b.set_ylabel(r"kWh per m$^3$")
h1, l1 = ax2.get_legend_handles_labels()
h2, l2 = ax2b.get_legend_handles_labels()
ax2.legend(h1 + h2, l1 + l2, loc="upper left")
fig.tight_layout()
save(fig, "03_esp_sizing")

# sensitivity: where the stretched curve's best-efficiency point sits [A]
for bep in (200.0, 250.0, 300.0):
    for n in range(10, 80, 2):
        wb = Producer(stages=n, q_bep=bep)
        fb = wb.freq_for_wellhead(Q_MAX_M3H, P_WH_TARGET_BAR)
        if fb is not None and fb <= F_PICK_HZ:
            break
    flag = "" if wb.q_min <= Q_MAX_M3H <= wb.q_max else "  <- 300 m3/h outside the envelope"
    print(f"BEP {bep:.0f} m3/h: {n} stages, 300 m3/h at {fb:.1f} Hz, envelope {wb.q_min:.0f}-{wb.q_max:.0f} m3/h [A, C]{flag}")
