"""GEMINI on the challenge well, no pump: can it flow on its own, and how hot does it arrive?

Uses GEMINI's IPR (linear inflow) and DPDT (well pressure/temperature drop) directly.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np

from geo.common import (COLORS, MU_PA_S, P_RES_BAR, PERM_MD, Q_MAX_M3H, Q_MIN_M3H, RHO, THICKNESS_M, DEPTH_M,
                    T_SURFACE_C, fig_height, fig_width, plt, save, t_reservoir_c)
from gemini_model.fluid.pvt_water_stp import PVTConstantSTP
from gemini_model.reservoir.inflow_performance import IPR
from gemini_model.well.pressure_drop import DPDT

BAR = 1e5
TUBING_ID_M = 0.1778        # 7 inch tubing [A]
ROUGHNESS_M = 4.5e-5        # steel [A]
R_E_M, R_W_M = 1300.0, 0.108  # drainage radius = well spacing as in TNO DoubletCalc [L, research/03], wellbore radius [A]
CELL_M = 50.0

T_RES_C = t_reservoir_c()
k_m2 = PERM_MD * 9.869e-16
pi_m3s_pa = 2 * np.pi * k_m2 * THICKNESS_M / (MU_PA_S * np.log(R_E_M / R_W_M))
PI = pi_m3s_pa * 3600 * BAR    # m3/h/bar
print(f"T_res {T_RES_C:.1f} C, PI (Darcy, re {R_E_M:.0f} m, rw {R_W_M} m) = {PI:.1f} m3/h/bar [A]")

ipr = IPR()
ipr.update_parameters({"type": "production_reservoir", "reservoir_pressure": P_RES_BAR, "productivity_index": PI})

n = int(DEPTH_M / CELL_M)
well = DPDT()
well.PVT = PVTConstantSTP()
well.PVT.update_parameters({"RHOL": RHO, "VISL": MU_PA_S})
well.update_parameters({
    "length": np.full(n, CELL_M), "diameter": np.full(n, TUBING_ID_M), "angle": np.full(n, np.pi / 2),
    "roughness": [ROUGHNESS_M] * n, "friction_correlation": "darcy_weisbach",
    "friction_correlation_2p": "BeggsBrill", "correction_factors": [1, 0],
})
t_ambient_c = 0.5 * (T_SURFACE_C + T_RES_C)   # GEMINI takes one ambient T for the whole well [A]

q = np.linspace(Q_MIN_M3H, Q_MAX_M3H, 26)
p_bh, p_wh, t_wh = [], [], []
for qi in q:
    ipr.calculate_output({"flow": qi}, None)
    pbh = ipr.get_output()["bottomhole_pressure"]
    well.calculate_output({"pressure": pbh * BAR, "temperature": T_RES_C + 273.15, "flowrate": qi / 3600,
                           "temperature_ambient": t_ambient_c + 273.15, "direction": "up"}, None)
    y = well.get_output()
    p_bh.append(pbh)
    p_wh.append(y["pressure_output"] / BAR)
    t_wh.append(y["temperature_output"] - 273.15)
p_bh, p_wh, t_wh = map(np.array, (p_bh, p_wh, t_wh))
p_static = p_bh - RHO * 9.81 * DEPTH_M / BAR   # bottomhole minus the brine column, our arithmetic; DPDT clamps at 0

for qi, a, b, d, c in zip(q[::5], p_bh[::5], p_wh[::5], p_static[::5], t_wh[::5]):
    print(f"q {qi:5.0f} m3/h  p_bottomhole {a:6.1f} bar  p_wellhead GEMINI {b:5.1f} bar  "
          f"static column balance {d:6.1f} bar  T_wellhead {c:5.1f} C")
print("GEMINI's DPDT clamps the wellhead at 0 bar instead of reporting a negative value: the well cannot flow "
      "without a pump at any flow in range. The ESP must lift at least the deficit plus the wellhead pressure we want.")

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(2 * fig_width, fig_height))
ax1.plot(q, p_bh, color=COLORS[0], label="bottomhole (IPR)")
ax1.plot(q, p_wh, color=COLORS[1], label="wellhead, no pump (DPDT, clamped)")
ax1.plot(q, p_static, color=COLORS[2], ls="--", label="bottomhole minus brine column")
ax1.axhline(0, color=(0.55, 0.57, 0.62), lw=0.8)
ax1.set_xlabel(r"flow (m$^3$/h)")
ax1.set_ylabel("pressure (bar)")
ax1.legend()
ax2.plot(q, t_wh, color=COLORS[0])
ax2.axhline(T_RES_C, color=(0.55, 0.57, 0.62), lw=0.8, label="reservoir")
ax2.set_xlabel(r"flow (m$^3$/h)")
ax2.set_ylabel(r"wellhead temperature ($^\circ$C)")
ax2.legend()
fig.tight_layout()
save(fig, "02_gemini_well_nopump")
