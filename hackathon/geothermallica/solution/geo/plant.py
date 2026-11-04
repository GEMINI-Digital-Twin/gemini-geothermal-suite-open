"""Heat one doublet delivers at 100 C against flow, from the GEMINI well models: a heat exchanger then a heat-pump lift, or a boiler lift.

Parameter sources are in the inline comments.
doublet_at() returns a dict for one flow: heat by source (MW), heat-pump electricity and COP (coefficient of performance),
pump power, wellhead temperature. DoubletTable holds the same keys as arrays over flow; at_output() returns one operating point.
"""
import numpy as np

from geo.common import DEPTH_M, DT_BRINE_MAX_K, RHO, T_SUPPLY_HEAT_C
from geo.well import ESP_DEPTH_M, Producer

CP = 4.0          # brine heat capacity, kJ/kg/K; assumed
APPROACH_K = 3.0  # heat-exchanger approach (smallest brine-to-water temperature difference), K; assumed
# heat-pump Lorenz efficiency (real COP over ideal COP on log-mean temperatures); source: IEA Heat Pumping Technologies,
# Annex 58 Task 1 report HPT-AN58-2 (2023), range 35-59 %,
# https://heatpumpingtechnologies.org/content/uploads/sites/70/2023/09/annex-58-task-1-technologies-task-report.pdf
LORENZ_EFF = 0.50
Q_FLOOR_M3H = 160.0   # lowest flow inside the pump's operating range, m3/h (rounded up from the stretched example curve)
T_ABS_MIN_C = 78.0    # coldest brine a single-effect absorption chiller can use, C; assumed (such chillers want about 80 C)
Q_CAP_M3H = 300.0     # maximum flow per doublet, m3/h; from the challenge brief


def _tlm(a, b):
    """Log-mean of two temperatures given in C, returned in K."""
    a, b = a + 273.15, b + 273.15
    return (a - b) / np.log(a / b)


def doublet_at(w: Producer, q_m3h: float, t_return_c: float, heat_pump: bool = True) -> dict:
    """Dict of heat by source (MW), electricity and COP for one doublet at q_m3h with network return t_return_c."""
    f = w.freq_for_wellhead(q_m3h)
    r = w.run(q_m3h, f if f is not None else 60.0)
    t_wh = r["T_wellhead_C"]
    m = q_m3h / 3600 * RHO
    t_floor = t_wh - DT_BRINE_MAX_K
    t_net_hx = t_wh - APPROACH_K
    t_brine_hx = max(t_return_c + APPROACH_K, t_floor)
    q_hx = m * CP * (t_wh - t_brine_hx) / 1000
    q_evap = m * CP * (t_brine_hx - t_floor) / 1000 if heat_pump else 0.0   # heat-pump evaporator duty, MW; none with a boiler lift
    if q_evap > 0:
        # network water runs exchanger -> heat pump, so the exchanger outlet (the heat-pump inlet) depends on the COP: iterate
        for _ in range(8):
            cop = LORENZ_EFF * _tlm(T_SUPPLY_HEAT_C, t_net_hx) / (_tlm(T_SUPPLY_HEAT_C, t_net_hx) - _tlm(t_brine_hx, t_floor))
            q_hp, p_hp = q_evap * cop / (cop - 1), q_evap / (cop - 1)
            m_net = (q_hx + q_hp) * 1000 / (CP * (T_SUPPLY_HEAT_C - t_return_c))
            t_net_hx = min(t_wh - APPROACH_K, t_return_c + q_hx * 1000 / (m_net * CP))
    else:
        cop, q_hp, p_hp = np.nan, 0.0, 0.0
    # absorption drive: brine from T_wh down to the warmer of 78 C and what the exchanger still needs
    mcp = m * CP / 1000   # MW/K
    q_abs = max(0.0, mcp * (t_wh - max(T_ABS_MIN_C, t_return_c + APPROACH_K + q_hx / mcp)))
    m_net = q_hx * 1000 / (CP * (t_net_hx - t_return_c))
    q_boiler = max(0.0, m_net * CP * (T_SUPPLY_HEAT_C - t_net_hx) / 1000 - q_hp)
    return {"q_m3h": q_m3h, "freq_hz": r["freq_hz"], "T_wh_C": t_wh, "MW_hx": q_hx, "MW_hp": q_hp, "MW_el_hp": p_hp,
            "MW_boiler_lift": q_boiler, "MW_out": q_hx + q_hp + q_boiler, "kW_esp": r["esp_electric_kW"], "cop": cop,
            "MW_abs_drive": q_abs, "mcp_MW_per_K": mcp,
            "p_esp_intake_bar": r["p_esp_intake_bar"]}


class DoubletTable:
    """Output, electricity and boiler lift of one doublet against flow, interpolated from a sweep of the GEMINI well."""

    def __init__(self, t_return_c: float, stages: int = 24, n: int = 15, depth_m: float = DEPTH_M, heat_pump: bool = True,
                 esp_depth_m: float = ESP_DEPTH_M):
        """Run doublet_at at n flows from Q_FLOOR_M3H to Q_CAP_M3H and keep the columns."""
        self.t_return_c, self.depth_m, self.heat_pump = t_return_c, depth_m, heat_pump
        self.w = Producer(depth_m=depth_m, stages=stages, esp_depth_m=esp_depth_m)
        self.q = np.linspace(Q_FLOOR_M3H, Q_CAP_M3H, n)
        rows = [doublet_at(self.w, q, t_return_c, heat_pump) for q in self.q]
        self.cols = {k: np.array([r[k] for r in rows]) for k in rows[0]}
        self.out_min, self.out_max = self.cols["MW_out"][0], self.cols["MW_out"][-1]

    def at_output(self, mw_out: float) -> dict:
        """Operating-point dict for mw_out MW per doublet: below the floor output the flow stays at the floor and the lift modulates."""
        c = self.cols
        floor = {k: float(v[0]) for k, v in c.items()}
        brine_cap_floor = floor["MW_hx"] + floor["MW_hp"] - floor["MW_el_hp"]   # brine heat at the floor flow, cooled by 40 K
        t_ret = self.t_return_c
        if not self.heat_pump and mw_out <= floor["MW_out"]:
            # boiler lift below the floor output: the boiler's share of the output is constant
            share = floor["MW_boiler_lift"] / floor["MW_out"]
            hx = (1 - share) * mw_out
            pt = {**floor, "MW_hx": hx, "MW_hp": 0.0, "MW_el_hp": 0.0, "MW_boiler_lift": share * mw_out, "MW_out": mw_out}
            pt["MW_brine_left"] = floor["MW_hx"] - hx
            mcp = floor["mcp_MW_per_K"]
            pt["MW_abs_drive"] = max(0.0, mcp * (floor["T_wh_C"] - max(T_ABS_MIN_C, t_ret + APPROACH_K + hx / mcp)))
            return pt
        if mw_out <= floor["MW_hx"]:
            pt = {**floor, "MW_hx": mw_out, "MW_hp": 0.0, "MW_el_hp": 0.0, "MW_boiler_lift": 0.0, "MW_out": mw_out}
            pt["MW_brine_left"] = brine_cap_floor - mw_out
            mcp = floor["mcp_MW_per_K"]
            pt["MW_abs_drive"] = max(0.0, mcp * (floor["T_wh_C"] - max(T_ABS_MIN_C, t_ret + APPROACH_K + mw_out / mcp)))
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
