"""Heat exchanger pinch and the 40 K cap against the network return temperature.

Two layouts for reaching 100 C:
  A  exchanger only, then a boiler tops up from (T_wh - approach) to 100 C
  B  exchanger, then a heat pump whose evaporator cools the brine further down to the 40 K cap, condensing at 100 C
In B the condenser serves two streams: it lifts the exchanger stream from 82.6 to 100 C and heats a small bypass of
return water to 100 C.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np

from geo.common import COLORS, DT_BRINE_MAX_K, Q_MAX_M3H, RHO, T_SUPPLY_HEAT_C, fig_height, fig_width, plt, save
from geo.well import Producer

CP = 4.0            # kJ/kg/K brine [A]
APPROACH_K = 3.0    # exchanger pinch [A]
LORENZ_EFF = 0.50   # real COP / Lorenz COP, mid of the 0.35-0.60 range in IEA HPT Annex 58 [L, research/01]
GREY = (0.55, 0.57, 0.62)

w = Producer(stages=24)
f = w.freq_for_wellhead(Q_MAX_M3H)
t_wh = w.run(Q_MAX_M3H, f)["T_wellhead_C"]
m = Q_MAX_M3H / 3600 * RHO                      # kg/s
t_brine_floor = t_wh - DT_BRINE_MAX_K           # coldest the brine may leave (40 K cap)
print(f"brine at wellhead {t_wh:.1f} C at {Q_MAX_M3H:.0f} m3/h, may be cooled to {t_brine_floor:.1f} C")


def lorenz_cop(t_sink_in, t_sink_out, t_src_in, t_src_out):
    """Ideal COP of a heat pump between two gliding streams (log-mean temperatures, K)."""
    def tlm(a, b):
        a, b = a + 273.15, b + 273.15
        return (a - b) / np.log(a / b)
    ts, tq = tlm(t_sink_out, t_sink_in), tlm(t_src_in, t_src_out)
    return ts / (ts - tq)


rows = []
for t_ret in np.arange(30, 71, 5):
    t_net_hx = t_wh - APPROACH_K                         # network water leaving the exchanger
    t_brine_hx = max(t_ret + APPROACH_K, t_brine_floor)  # brine leaving the exchanger
    q_hx = m * CP * (t_wh - t_brine_hx) / 1000           # MW from the exchanger
    # layout A: boiler lifts the network water from t_net_hx to 100 C; its share of delivered heat
    share_boiler = (T_SUPPLY_HEAT_C - t_net_hx) / (T_SUPPLY_HEAT_C - t_ret)
    q_total_a = q_hx / (1 - share_boiler)
    # layout B: the heat pump evaporator takes the brine from t_brine_hx down to the 40 K floor
    q_evap = m * CP * (t_brine_hx - t_brine_floor) / 1000
    cop = LORENZ_EFF * lorenz_cop(t_net_hx, T_SUPPLY_HEAT_C, t_brine_hx, t_brine_floor) if q_evap > 0 else np.nan
    q_hp = q_evap * cop / (cop - 1) if q_evap > 0 else 0.0   # condenser heat at 100 C
    p_el = q_evap / (cop - 1) if q_evap > 0 else 0.0
    # does the heat pump alone reach 100 C for the whole network flow? network flow set by the exchanger duty
    m_net = q_hx * 1000 / (CP * (t_net_hx - t_ret))
    q_lift_needed = m_net * CP * (T_SUPPLY_HEAT_C - t_net_hx) / 1000
    q_boiler_b = max(0.0, q_lift_needed - q_hp)
    rows.append(dict(t_ret=t_ret, t_brine_hx=t_brine_hx, q_hx=q_hx, share_boiler=share_boiler, q_total_a=q_total_a,
                     q_evap=q_evap, cop=cop, q_hp=q_hp, p_el=p_el, q_total_b=q_hx + q_hp, q_boiler_b=q_boiler_b,
                     brine_dt_a=t_wh - t_brine_hx))

print(f"{'return':>6} {'brine out A':>11} {'dT_A':>5} {'HX MW':>6} {'boiler share A':>14} | {'evap MW':>7} {'COP':>5} {'HP MW':>6} {'el MW':>6} {'total B':>7} {'boiler B':>8}")
for r in rows:
    print(f"{r['t_ret']:6.0f} {r['t_brine_hx']:11.1f} {r['brine_dt_a']:5.1f} {r['q_hx']:6.2f} {100 * r['share_boiler']:13.0f}% | "
          f"{r['q_evap']:7.2f} {r['cop']:5.2f} {r['q_hp']:6.2f} {r['p_el']:6.2f} {r['q_total_b']:7.2f} {r['q_boiler_b']:8.2f}")

t = np.array([r["t_ret"] for r in rows])
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(2 * fig_width, fig_height))
ax1.plot(t, [r["q_hx"] for r in rows], color=COLORS[0], label="A: exchanger only (geothermal MW)")
ax1.plot(t, [r["q_total_b"] for r in rows], color=COLORS[1], label="B: exchanger + brine heat pump (MW at 100 C)")
ax1.axhline(m * CP * DT_BRINE_MAX_K / 1000, color=GREY, lw=0.8, label="40 K cap")
ax1.set_xlabel(r"network return ($^\circ$C)")
ax1.set_ylabel("per doublet (MW)")
ax1.legend(fontsize=7)
ax2.plot(t, [100 * r["share_boiler"] for r in rows], color=COLORS[0], label="A: boiler share of delivered heat")
ax2.plot(t, [100 * r["q_boiler_b"] / r["q_total_b"] for r in rows], color=COLORS[1], label="B: boiler share")
ax2.plot(t, [100 * r["p_el"] / r["q_total_b"] for r in rows], color=COLORS[2], ls="--", label="B: electricity / heat")
ax2.set_xlabel(r"network return ($^\circ$C)")
ax2.set_ylabel(r"share (\%)")
ax2.legend(fontsize=7)
fig.tight_layout()
save(fig, "04_exchanger_return")

# sensitivity: Lorenz efficiency at a 60 C return, layout B [L, research/01 range]
t_ret = 60.0
t_brine_hx, t_net_hx = max(t_ret + APPROACH_K, t_brine_floor), t_wh - APPROACH_K
q_hx = m * CP * (t_wh - t_brine_hx) / 1000
q_evap = m * CP * (t_brine_hx - t_brine_floor) / 1000
print(f"Lorenz efficiency at a {t_ret:.0f} C return, {Q_MAX_M3H:.0f} m3/h (exchanger {q_hx:.2f} MW) [C]:")
for eff in (0.35, 0.50, 0.60):
    cop = eff * lorenz_cop(t_net_hx, T_SUPPLY_HEAT_C, t_brine_hx, t_brine_floor)
    print(f"  eff {eff:.2f}: COP {cop:.2f}, heat pump {q_evap * cop / (cop - 1):.2f} MW, electricity {q_evap / (cop - 1):.2f} MW, "
          f"total {q_hx + q_evap * cop / (cop - 1):.2f} MW per doublet")
