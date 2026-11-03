"""Injection well with GEMINI models: equal volumes, brine back at T_wh - 40 K, cold-brine injectivity, SodM limit.

II = PI * mu(T_res) / mu(T_inj) with the Vogel viscosity, whole drainage area cold (worst case) [A].
GEMINI's DPDT "down" adds friction to the pressure going down; we pass -q so friction opposes the flow and print
GEMINI's own sign beside it [C]."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np

from geo.common import COLORS, fig_height, fig_width, plt, save
from geo.well import P_SODM_BAR, Z_TOP_M, Injector, injector_at

GREY = (0.55, 0.57, 0.62)
inj = Injector()


if __name__ == "__main__":
    print(f"PI {inj.pi:.2f} m3/h/bar at {inj.t_res_c:.0f} C [C]; SodM limit 0.135 bar/m x {Z_TOP_M:.0f} m = {P_SODM_BAR:.1f} bar [L]")
    q = np.linspace(50, 300, 26)
    rows = [injector_at(qi) for qi in q]
    print(f"{'q':>5} {'T_inj':>6} {'II':>5} {'p_bh req':>8} {'p_wh req':>8} {'(GEMINI sign)':>13} {'pump kW':>7} {'SodM margin':>11}")
    for r in rows[::5]:
        print(f"{r['q_m3h']:5.0f} {r['T_inj_C']:6.1f} {r['II']:5.2f} {r['p_bh_req_bar']:8.1f} {r['p_wh_bar']:8.1f} "
              f"{r['p_wh_gemini_sign_bar']:13.1f} {r['pump_kW']:7.0f} {r['sodm_margin_bar']:9.1f} {'pass' if r['sodm_margin_bar'] >= 0 else 'FAIL'}")
    print("[C] all rows; T_inj = T_wh(q) - 40 K at the cap, injection pump eta 0.70 [D]")

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(2 * fig_width, fig_height))
    ax1.plot(q, [r["p_bh_req_bar"] for r in rows], color=COLORS[0], label="bottomhole required (IPR, cold II)")
    ax1.plot(q, [r["p_bh_free_bar"] for r in rows], color=COLORS[1], ls="--", label="bottomhole from the column, 0 bar wellhead")
    ax1.axhline(P_SODM_BAR, color=GREY, lw=0.8, label="SodM 0.135 bar/m at 2450 m")
    ax1.set_xlabel(r"flow (m$^3$/h)")
    ax1.set_ylabel("pressure (bar)")
    ax1.legend(fontsize=7)
    ax2.plot(q, [r["pump_kW"] for r in rows], color=COLORS[0], label=r"injection pump, $\eta$ = 0.70")
    ax2.set_xlabel(r"flow (m$^3$/h)")
    ax2.set_ylabel("power (kW)")
    ax2.legend(fontsize=7)
    fig.tight_layout()
    save(fig, "07_injector")
