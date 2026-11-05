"""Our numbers for one doublet on one day of the dispatch, GEMINI's matching outputs from the solved project, and the row that
sets them side by side. ours() also gives the day values the generated project needs (exchanger UA, water flow, floors).
"""
import math

import numpy as np

from geo import gas, lifetime
from geo.common import RHO, T_SUPPLY_HEAT_C
from geo.cost import BOILER_EFF, GCV_LHV
from geo.plant import APPROACH_K, CP
from geo.year import COP_ABSORPTION

COMPARED = ("q_m3h", "p_esp_intake_bar", "esp_head_bar", "p_injection_wellhead_bar", "T_brine_out_C", "T_injection_C",
            "T_supply_C", "MW_exchanger", "MW_boiler_gas", "MW_heat_pump", "cop_heat_pump", "MW_abs_drive", "MW_abs_cold",
            "p_bubble_bar", "MW_methane_LHV", "t_breakthrough_yr", "interference_bar")


def _ua(t_hot_in, t_cold_in, c_hot, c_cold, duty_w):
    """Heat-transfer coefficient UA (W/K) of a counter-flow exchanger with this duty, inverted NTU-effectiveness method."""
    c_min, c_max = min(c_hot, c_cold), max(c_hot, c_cold)
    eff, cr = duty_w / (c_min * (t_hot_in - t_cold_in)), c_min / c_max
    ntu = eff / (1 - eff) if cr > 0.999 else np.log((1 - eff * cr) / (1 - eff)) / (1 - cr)
    return float(ntu * c_min)


def _network_water_kg_s(pt, t_hot_in, t_return_c):
    """Network water through the exchanger, kg/s: what exchanger and heat pump together heat to the supply temperature, but
    at least the flow that leaves the exchanger APPROACH_K below the brine entering it. On part-load days (heat pump cut back
    or off) the second term wins and the water leaves below the supply temperature: the dispatch counts MW, not temperature."""
    to_supply = (pt["MW_hx"] + pt["MW_hp"]) * 1e3 / (CP * (T_SUPPLY_HEAT_C - t_return_c))
    feasible = pt["MW_hx"] * 1e3 / (CP * (t_hot_in - APPROACH_K - t_return_c))
    return max(to_supply, feasible)


def ours(w, inj, pt, t_return_c, n):
    """Our numbers for one of n doublets at the dispatch point pt (DoubletTable.at_output), plus the project's day values."""
    q, mcp = pt["q_m3h"], pt["mcp_MW_per_K"]                  # flow m3/h, brine heat capacity flow MW/K
    f = w.freq_for_wellhead(q)
    r = w.run(q, f if f is not None else 60.0)                 # the well as in plant.doublet_at
    t_wh = pt["T_wh_C"]
    t_hx_in = t_wh - pt["MW_abs_drive"] / mcp                  # brine leaving the absorption chiller, C
    t_hx_out = t_hx_in - pt["MW_hx"] / mcp                     # brine leaving the exchanger, C
    t_out = t_hx_out - (pt["MW_hp"] - pt["MW_el_hp"]) / mcp     # brine leaving the heat-pump evaporator, C
    hp_on = pt["MW_hp"] > 0
    m_net = _network_water_kg_s(pt, t_hx_in, t_return_c)
    i = inj.run(q, t_out)                                       # brine as the day's chain leaves it
    g = gas.gas_at(q, w.depth_m)
    return {"q_m3h": q, "freq_hz": r["freq_hz"], "T_wellhead_C": t_wh, "p_esp_intake_bar": r["p_esp_intake_bar"],
            "esp_head_bar": r["esp_head_bar"], "p_injection_wellhead_bar": i["p_wh_bar"], "T_brine_out_C": t_hx_out,
            "T_injection_C": t_out, "T_supply_C": T_SUPPLY_HEAT_C, "MW_exchanger": pt["MW_hx"],
            "MW_boiler_gas": g["CH4_MW_LHV"] * BOILER_EFF * GCV_LHV, "MW_heat_pump": pt["MW_hp"],   # BOILER_EFF is on GCV, gas on LHV
            "cop_heat_pump": pt["cop"] if hp_on else math.nan, "MW_abs_drive": pt["MW_abs_drive"], "MW_abs_cold": COP_ABSORPTION * pt["MW_abs_drive"],
            "p_bubble_bar": g["p_bubble_bar"], "MW_methane_LHV": g["CH4_MW_LHV"],
            "t_breakthrough_yr": lifetime.t_bt_yr(q), "interference_bar": max(lifetime.interference_bar(n, q)),
            # day values of the project: the chiller may cool the brine only to where our dispatch hands it to the exchanger
            # (the wellhead temperature when the chiller is off); the heat pump may cool the brine to what our dispatch
            # implies (a floor above its inlet when the heat pump is off)
            "T_chiller_floor_C": t_hx_in, "T_hp_floor_C": t_out if hp_on else t_wh,
            "secondary_m3s": m_net / RHO, "ii_m3h_bar": i["II"],
            "ua_w_per_k": _ua(t_hx_in, t_return_c, mcp * 1e6, m_net * CP * 1e3, pt["MW_hx"] * 1e6)}


def theirs(s):
    """GEMINI's outputs of the solved project s, in the keys and units of ours()."""
    g = s.get_output
    return {"q_m3h": g("producer_well", "flow_rate"), "p_esp_intake_bar": g("producer_well", "esp_intake_pressure"),
            "esp_head_bar": g("producer_well", "esp_discharge_pressure") - g("producer_well", "esp_intake_pressure"),
            "p_injection_wellhead_bar": g("injector_well", "wellhead_pressure"),
            "T_brine_out_C": g("heat_exchanger", "primary_temperature_out"), "T_injection_C": g("heat_pump", "Ts_out"),
            "T_supply_C": g("heat_pump", "Th_out"),
            "MW_exchanger": g("heat_exchanger", "heat_duty") / 1e6, "MW_boiler_gas": g("boiler", "power_th") / 1e6,
            "MW_heat_pump": g("heat_pump", "Thermal_production") / 1e6, "cop_heat_pump": g("heat_pump", "COP"),
            "MW_abs_drive": g("absorption_chiller", "drive_heat") / 1e6,
            "MW_abs_cold": g("absorption_chiller", "cooling_power") / 1e6,
            "p_bubble_bar": g("gas", "bubble_point_pressure") / 1e5, "MW_methane_LHV": g("gas", "methane_power") / 1e6,
            "t_breakthrough_yr": g("breakthrough", "breakthrough_time") / lifetime.YEAR_S,
            "interference_bar": g("breakthrough", "interference_pressure_max") / 1e5}


def _diff_pct(a, b):
    """(b - a) / a in percent; None when a is 0 or not a number, or b is missing."""
    if b is None or a == 0 or math.isnan(a):
        return None
    return 100 * (b - a) / a


def compare(o, t):
    """Row of COMPARED keys: _ours, _gemini and _diff_pct for each; t empty when GEMINI could not reach our flow."""
    row = {}
    for k in COMPARED:
        row[k + "_ours"], row[k + "_gemini"] = o[k], t.get(k)
        row[k + "_diff_pct"] = _diff_pct(o[k], t.get(k))
    return row
