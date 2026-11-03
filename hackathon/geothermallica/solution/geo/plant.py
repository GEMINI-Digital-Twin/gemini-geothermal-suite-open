"""Per-doublet heat delivery at 100 C as a function of flow, tabulated once from GEMINI: layout B of script 04 (heat-pump lift,
the default) or layout A (heat_pump=False: exchanger only, a boiler lifts the network water from T_wh - approach to 100 C)."""
import numpy as np

from geo.common import DEPTH_M, DT_BRINE_MAX_K, RHO, T_SUPPLY_HEAT_C
from geo.well import Producer

CP = 4.0          # kJ/kg/K [A]
APPROACH_K = 3.0  # [A]
LORENZ_EFF = 0.50  # [L, research/01]
Q_FLOOR_M3H = 160.0   # pump envelope floor, script 03 [C]
T_ABS_MIN_C = 78.0    # coldest brine a single-effect absorption chiller can use, hot water in >= 80 C less margin [L, A]
Q_CAP_M3H = 300.0     # brief [D]


def _tlm(a, b):
    a, b = a + 273.15, b + 273.15
    return (a - b) / np.log(a / b)


def doublet_at(w: Producer, q_m3h: float, t_return_c: float, heat_pump: bool = True) -> dict:
    f = w.freq_for_wellhead(q_m3h)
    r = w.run(q_m3h, f if f is not None else 60.0)
    t_wh = r["T_wellhead_C"]
    m = q_m3h / 3600 * RHO
    t_floor = t_wh - DT_BRINE_MAX_K
    t_net_hx = t_wh - APPROACH_K
    t_brine_hx = max(t_return_c + APPROACH_K, t_floor)
    q_hx = m * CP * (t_wh - t_brine_hx) / 1000
    q_evap = m * CP * (t_brine_hx - t_floor) / 1000 if heat_pump else 0.0   # layout A: no evaporator, brine leaves at t_brine_hx
    if q_evap > 0:
        # water balance: all network water goes return -> exchanger -> heat pump -> 100 C, so the exchanger outlet
        # t_net_hx falls below t_wh - approach once the heat pump adds heat; iterate COP on that sink (review, 2 Nov)
        for _ in range(8):
            cop = LORENZ_EFF * _tlm(T_SUPPLY_HEAT_C, t_net_hx) / (_tlm(T_SUPPLY_HEAT_C, t_net_hx) - _tlm(t_brine_hx, t_floor))
            q_hp, p_hp = q_evap * cop / (cop - 1), q_evap / (cop - 1)
            m_net = (q_hx + q_hp) * 1000 / (CP * (T_SUPPLY_HEAT_C - t_return_c))
            t_net_hx = min(t_wh - APPROACH_K, t_return_c + q_hx * 1000 / (m_net * CP))
    else:
        cop, q_hp, p_hp = np.nan, 0.0, 0.0
    # absorption drive: brine from T_wh down to the warmer of 78 C and what the heating exchanger still needs
    mcp = m * CP / 1000   # MW/K
    q_abs = max(0.0, mcp * (t_wh - max(T_ABS_MIN_C, t_return_c + APPROACH_K + q_hx / mcp)))
    m_net = q_hx * 1000 / (CP * (t_net_hx - t_return_c))
    q_boiler = max(0.0, m_net * CP * (T_SUPPLY_HEAT_C - t_net_hx) / 1000 - q_hp)
    return {"q_m3h": q_m3h, "freq_hz": r["freq_hz"], "T_wh_C": t_wh, "MW_hx": q_hx, "MW_hp": q_hp, "MW_el_hp": p_hp,
            "MW_boiler_lift": q_boiler, "MW_out": q_hx + q_hp + q_boiler, "kW_esp": r["esp_electric_kW"], "cop": cop,
            "MW_abs_drive": q_abs, "mcp_MW_per_K": mcp}


class DoubletTable:
    """Output, electricity and boiler lift of one doublet against flow, interpolated from a GEMINI sweep."""

    def __init__(self, t_return_c: float, stages: int = 24, n: int = 15, depth_m: float = DEPTH_M, heat_pump: bool = True):
        self.t_return_c, self.depth_m, self.heat_pump = t_return_c, depth_m, heat_pump
        self.w = Producer(depth_m=depth_m, stages=stages)   # 24 stages were sized at 2 500 m (script 03); kept at other depths [A]
        self.q = np.linspace(Q_FLOOR_M3H, Q_CAP_M3H, n)
        rows = [doublet_at(self.w, q, t_return_c, heat_pump) for q in self.q]
        self.cols = {k: np.array([r[k] for r in rows]) for k in rows[0]}
        self.out_min, self.out_max = self.cols["MW_out"][0], self.cols["MW_out"][-1]

    def at_output(self, mw_out: float) -> dict:
        """Operating point for a demand of mw_out per doublet.

        Below the exchanger's floor output: pump at the floor, exchanger meets the demand, heat pump off.
        Between exchanger floor and full floor output: pump at the floor, heat pump modulates.
        Above: flow rises along the table. `MW_brine_left` is brine heat (within the 40 K cap) not used for heating.
        """
        c = self.cols
        floor = {k: float(v[0]) for k, v in c.items()}
        brine_cap_floor = floor["MW_hx"] + floor["MW_hp"] - floor["MW_el_hp"]   # brine heat at the floor, 40 K
        t_ret = self.t_return_c
        if not self.heat_pump and mw_out <= floor["MW_out"]:
            # layout A below the floor output: pump at the floor, the boiler's share of the lift is constant [C]
            share = floor["MW_boiler_lift"] / floor["MW_out"]
            hx = (1 - share) * mw_out
            pt = {**floor, "MW_hx": hx, "MW_hp": 0.0, "MW_el_hp": 0.0, "MW_boiler_lift": share * mw_out, "MW_out": mw_out}
            pt["MW_brine_left"] = floor["MW_hx"] - hx
            pt["MW_abs_drive"] = max(0.0, floor["mcp_MW_per_K"] * (floor["T_wh_C"] - max(T_ABS_MIN_C, t_ret + APPROACH_K + hx / floor["mcp_MW_per_K"])))
            return pt
        if mw_out <= floor["MW_hx"]:
            pt = {**floor, "MW_hx": mw_out, "MW_hp": 0.0, "MW_el_hp": 0.0, "MW_boiler_lift": 0.0, "MW_out": mw_out}
            pt["MW_brine_left"] = brine_cap_floor - mw_out
            pt["MW_abs_drive"] = max(0.0, floor["mcp_MW_per_K"] * (floor["T_wh_C"] - max(T_ABS_MIN_C, t_ret + APPROACH_K + mw_out / floor["mcp_MW_per_K"])))
            return pt
        if mw_out <= floor["MW_out"]:
            hp = max(0.0, mw_out - floor["MW_hx"] - floor["MW_boiler_lift"])   # never negative
            frac = hp / floor["MW_hp"] if floor["MW_hp"] > 0 else 0.0
            boiler = floor["MW_boiler_lift"] if hp > 0 else mw_out - floor["MW_hx"]   # the rest, >= 0 since mw_out > MW_hx
            pt = {**floor, "MW_hp": hp, "MW_el_hp": frac * floor["MW_el_hp"], "MW_boiler_lift": boiler, "MW_out": mw_out}
            pt["MW_brine_left"] = (1 - frac) * (floor["MW_hp"] - floor["MW_el_hp"])
            return pt
        mw = float(min(mw_out, self.out_max))
        pt = {k: float(np.interp(mw, c["MW_out"], v)) for k, v in c.items()}
        pt["MW_brine_left"] = 0.0
        return pt
