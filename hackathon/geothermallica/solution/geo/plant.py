"""Heat one doublet delivers at 100 C against flow: exchanger then heat-pump lift (or boiler lift), on the GEMINI well models.

doublet_at() gives one flow; DoubletTable holds the same keys over flow and at_output() one operating point.
"""
import numpy as np

from geo.common import DEPTH_M, DT_BRINE_MAX_K, RHO, T_SUPPLY_HEAT_C
from geo.well import ESP_DEPTH_M, Producer

CP = 4.0          # brine heat capacity, kJ/kg/K; assumed
APPROACH_K = 3.0  # heat-exchanger approach (smallest brine-to-water temperature difference), K; assumed
LORENZ_EFF = 0.50    # heat-pump COP over Lorenz COP; IEA HPT Annex 58 2023 (35-59 %), see SOURCES.md
COP_MAX = 8.0        # heat-pump COP cap at small lifts; Arpagaus 2018 (COP 6-8), cap assumed
Q_FLOOR_M3H = 160.0   # lowest flow inside the pump's operating range, m3/h
T_ABS_MIN_C = 78.0    # coldest brine a single-effect absorption chiller can use, C; assumed
Q_CAP_M3H = 300.0     # maximum flow per doublet, m3/h; challenge input


def _abs_drive(t_wh, mcp, t_return_c, hx):
    """Brine heat above T_ABS_MIN_C left for absorption chillers, MW (mcp in MW/K, hx = exchanger MW)."""
    return max(0.0, mcp * (t_wh - max(T_ABS_MIN_C, t_return_c + APPROACH_K + hx / mcp)))


def _tlm(a, b):
    """Log-mean of two temperatures given in C, returned in K."""
    a, b = a + 273.15, b + 273.15
    return a if abs(a - b) < 1e-9 else (a - b) / np.log(a / b)


def _t_hx(pt, t_return_c):
    """Network water temperature leaving the exchanger, C: its share of the heat on the way from the return to the supply."""
    out = pt["MW_hx"] + pt["MW_hp"] + pt["MW_boiler_lift"]
    return t_return_c + pt["MW_hx"] / out * (T_SUPPLY_HEAT_C - t_return_c) if out > 0 else t_return_c


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
        # water runs exchanger -> heat pump, so the heat-pump inlet depends on the COP: iterate
        for _ in range(8):
            cop = min(COP_MAX, LORENZ_EFF * _tlm(T_SUPPLY_HEAT_C, t_net_hx)
                      / (_tlm(T_SUPPLY_HEAT_C, t_net_hx) - _tlm(t_brine_hx, t_floor)))
            q_hp, p_hp = q_evap * cop / (cop - 1), q_evap / (cop - 1)
            m_net = (q_hx + q_hp) * 1000 / (CP * (T_SUPPLY_HEAT_C - t_return_c))
            t_net_hx = min(t_wh - APPROACH_K, t_return_c + q_hx * 1000 / (m_net * CP))
    else:
        cop, q_hp, p_hp = np.nan, 0.0, 0.0
    mcp = m * CP / 1000   # MW/K
    q_abs = _abs_drive(t_wh, mcp, t_return_c, q_hx)
    m_net = q_hx * 1000 / (CP * (t_net_hx - t_return_c))
    q_boiler = max(0.0, m_net * CP * (T_SUPPLY_HEAT_C - t_net_hx) / 1000 - q_hp)
    return {"q_m3h": q_m3h, "freq_hz": r["freq_hz"], "T_wh_C": t_wh, "MW_hx": q_hx, "MW_hp": q_hp, "MW_el_hp": p_hp,
            "MW_boiler_lift": q_boiler, "MW_out": q_hx + q_hp + q_boiler, "kW_esp": r["esp_electric_kW"], "cop": cop,
            "MW_abs_drive": q_abs, "mcp_MW_per_K": mcp,
            "p_esp_intake_bar": r["p_esp_intake_bar"]}


def _lift_cop(t_hx, t_evap_in, t_evap_out):
    """Lorenz COP (capped at COP_MAX) lifting water from t_hx to the supply on brine from t_evap_in to t_evap_out, C."""
    t_sink = _tlm(T_SUPPLY_HEAT_C, t_hx)
    return min(COP_MAX, LORENZ_EFF * t_sink / (t_sink - _tlm(t_evap_in, t_evap_out)))


def _chiller_first(floor, mw_out, t_return_c):
    """Part load: chiller to T_ABS_MIN_C, exchanger, then heat pump; None when the approach or the 40 K cap breaks."""
    t_wh, mcp = floor["T_wh_C"], floor["mcp_MW_per_K"]
    if t_wh - APPROACH_K <= T_ABS_MIN_C:
        return None
    t_hx = T_ABS_MIN_C - APPROACH_K                                  # water leaving the exchanger, C
    m_net = mw_out * 1e3 / (CP * (T_SUPPLY_HEAT_C - t_return_c))      # network water, kg/s
    hx = m_net * CP * (t_hx - t_return_c) / 1e3
    hp = m_net * CP * (T_SUPPLY_HEAT_C - t_hx) / 1e3
    t_evap_in = T_ABS_MIN_C - hx / mcp                                # brine leaving the exchanger, C
    if t_evap_in < t_return_c + APPROACH_K:
        return None
    t_evap_out = t_evap_in - hp / mcp
    for _ in range(4):
        cop = _lift_cop(t_hx, t_evap_in, t_evap_out)
        t_evap_out = t_evap_in - hp * (cop - 1) / cop / mcp          # evaporator heat = output minus compressor work
    if t_evap_out < t_wh - DT_BRINE_MAX_K:
        return None
    pt = {**floor, "MW_hx": hx, "MW_hp": hp, "MW_el_hp": hp / cop, "MW_boiler_lift": 0.0, "MW_out": mw_out, "cop": cop,
          "MW_abs_drive": mcp * (t_wh - T_ABS_MIN_C), "part_load": "chiller-first"}
    pt["MW_brine_left"] = mcp * (t_evap_out - (t_wh - DT_BRINE_MAX_K))   # brine heat above the 40 K floor not used
    return pt


def _hold_split(floor, mw_out, t_return_c):
    """Part load holding the floor point's split of exchanger, heat pump and boiler; COP recomputed at the smaller lift."""
    f = mw_out / floor["MW_out"]
    hx, hp, mcp = f * floor["MW_hx"], f * floor["MW_hp"], floor["mcp_MW_per_K"]
    pt = {**floor, "MW_hx": hx, "MW_hp": hp, "MW_el_hp": f * floor["MW_el_hp"], "MW_boiler_lift": f * floor["MW_boiler_lift"],
          "MW_out": mw_out, "MW_abs_drive": 0.0, "part_load": "exchanger-first"}
    if hp > 0:
        t_hx, t_evap_in = _t_hx(pt, t_return_c), floor["T_wh_C"] - hx / mcp
        t_evap_out = t_evap_in - hp / mcp
        for _ in range(4):
            cop = _lift_cop(t_hx, t_evap_in, t_evap_out)
            t_evap_out = t_evap_in - hp * (cop - 1) / cop / mcp
        pt["cop"], pt["MW_el_hp"] = cop, hp / cop
    pt["MW_brine_left"] = (floor["MW_hx"] + floor["MW_hp"] - floor["MW_el_hp"]) - (hx + hp - pt["MW_el_hp"])
    return pt


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
        """Operating point for mw_out MW per doublet: part load at the floor flow below out_min, else interpolated."""
        c = self.cols
        floor = {k: float(v[0]) for k, v in c.items()}
        t_ret = self.t_return_c
        if mw_out <= floor["MW_out"] and not self.heat_pump:
            pt = _hold_split(floor, mw_out, t_ret)
            pt["MW_abs_drive"] = _abs_drive(floor["T_wh_C"], floor["mcp_MW_per_K"], t_ret, pt["MW_hx"])
        elif mw_out <= floor["MW_out"]:
            pt = _chiller_first(floor, mw_out, t_ret) or _hold_split(floor, mw_out, t_ret)
        else:
            mw = float(min(mw_out, self.out_max))
            pt = {k: float(np.interp(mw, c["MW_out"], v)) for k, v in c.items()}
            pt["MW_brine_left"], pt["part_load"] = 0.0, "full"
        pt["t_hx_C"] = _t_hx(pt, t_ret)
        return pt
