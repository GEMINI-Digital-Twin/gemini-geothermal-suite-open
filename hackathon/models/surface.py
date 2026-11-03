"""Surface plant models for one day of steady (daily-average) operation.

Layer C. All functions are pure: temperatures in C, powers in MW, flows in kg/s.

Brine cascade (hottest use first), all on the combined stream of the active
doublets:

    wellhead -> [absorption/adsorption generator] -> [direct heating HX]
             -> [heat pump evaporator] -> injection (>= wellhead T - 40 K)

Heating network (return T_r -> 100 C):  direct HX -> heat pump -> boiler
Cooling network (return 26 -> 20 C):    sorption chiller -> electric chiller

Parameters marked DEFAULT in ``SurfaceParams`` are proposals for the owner to
confirm from their references.
"""

import math
import sys
from dataclasses import dataclass, asdict

from .config import REPO_ROOT

_SRC = str(REPO_ROOT / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

CP_WATER = 4180.0  # J/kgK, network water
K0 = 273.15


@dataclass
class SurfaceParams:
    """Technology parameters (DEFAULT values: confirm from references)."""

    hx_approach_k: float = 3.0              # plate HX terminal approach
    hp_eta_lorenz: float = 0.5              # GEMINI HeatpumpBasic default
    hp_capacity_mw: float = 0.0             # design variable, sink side
    hp_min_source_out_c: float = 10.0       # GEMINI Ts_in_minimum
    hp_cop_max: float = 7.0                 # DEFAULT, practical compressor limit
    chiller_type: str = "absorption_single_effect"  # or adsorption, electric
    sorption_capacity_mw: float = 0.0       # design variable, cooling output
    sorption_cop: float = 0.70              # DEFAULT, single-effect LiBr at 20 C chilled supply
    sorption_min_drive_in_c: float = 75.0   # DEFAULT
    sorption_max_drive_dt_k: float = 15.0   # DEFAULT, generator brine temperature drop
    sorption_min_drive_out_c: float = 65.0  # DEFAULT
    adsorption_cop: float = 0.55            # DEFAULT
    adsorption_min_drive_in_c: float = 60.0
    adsorption_max_drive_dt_k: float = 20.0
    adsorption_min_drive_out_c: float = 50.0
    elec_chiller_capacity_mw: float = 0.0   # design variable (top-up and backup)
    elec_chiller_eta: float = 0.5           # fraction of Carnot
    elec_chiller_cop_max: float = 7.0
    condenser_c: float = 38.0               # heat rejection temperature
    rejection_aux_frac: float = 0.02        # tower fans/pumps, per MW rejected
    boiler_capacity_mw: float = 0.0         # design variable (peak and backup)
    assoc_gas_use: str = "chp"              # chp | boiler; flaring is not an option
    chp_elec_eff: float = 0.38              # DEFAULT, gas engine on LHV
    chp_heat_eff: float = 0.47              # DEFAULT

    def as_dict(self):
        return asdict(self)


def lorenz_cop(eta, t_sink_in, t_sink_out, t_src_in, t_src_out, cop_max=10.0):
    """Lorenz COP from log-mean sink and source temperatures (GEMINI's formula)."""
    def lm(a, b):
        a, b = a + K0, b + K0
        return (a - b) / math.log(a / b) if abs(a - b) > 1e-6 else a
    th, ts = lm(t_sink_out, t_sink_in), lm(t_src_in, t_src_out)
    if th <= ts:
        return cop_max
    return min(cop_max, eta * th / (th - ts))


def gemini_heatpump_cop(eta, t_sink_in, t_sink_out, t_src_in, sink_m3s, src_m3s):
    """Run GEMINI's own HeatpumpBasic (Lorenz) for cross-checking lorenz_cop."""
    from gemini_model.heatpump.heatpump_basic import HeatpumpBasic

    hp = HeatpumpBasic()
    hp.update_parameters({"mode": "lorenz", "eta_lorenz": eta, "Th_out_target": t_sink_out})
    hp.calculate_output({"Th_in": t_sink_in, "Ts_in": t_src_in,
                         "hot_flow_rate": sink_m3s, "source_flow_rate": src_m3s})
    return hp.output


def _sorption_limits(p):
    if p.chiller_type == "adsorption":
        return p.adsorption_cop, p.adsorption_min_drive_in_c, p.adsorption_max_drive_dt_k, \
            p.adsorption_min_drive_out_c
    return p.sorption_cop, p.sorption_min_drive_in_c, p.sorption_max_drive_dt_k, \
        p.sorption_min_drive_out_c


def electric_chiller_cop(p, t_chilled_c):
    t_ev, t_cd = t_chilled_c - 3 + K0, p.condenser_c + K0
    return min(p.elec_chiller_cop_max, p.elec_chiller_eta * t_ev / (t_cd - t_ev))


def simulate_day(cfg, p, heat_mw, cool_mw, brine_kg_s, t_wellhead_c, gas_fuel_mw=0.0):
    """Meet one day's heating and cooling demand. Returns a dict of flows of energy.

    ``brine_kg_s`` is the combined flow of active doublets (0 on outage days).
    ``gas_fuel_mw`` is associated-gas fuel available that day (burned first).
    """
    cpb = cfg.cp
    t_floor = t_wellhead_c - cfg.dt_brine_max          # injection floor (40 K cap)
    t_b = t_wellhead_c
    out = {k: 0.0 for k in (
        "cool_sorption", "cool_electric", "cool_unmet", "sorption_drive", "heat_direct",
        "heat_hp", "hp_elec", "heat_boiler_assoc", "heat_boiler_ng", "heat_unmet",
        "chiller_elec", "rejection_mw", "rejection_elec", "assoc_gas_used_mw", "ng_used_mw",
        "assoc_gas_unused_mw", "hp_cop", "brine_out_c", "t_after_direct_c",
        "heat_chp", "chp_elec", "chp_heat_dumped")}

    # 1. sorption chiller on the hottest brine
    cop_s, t_in_min, dt_max, t_out_min = _sorption_limits(p)
    if (p.chiller_type != "electric" and brine_kg_s > 0 and cool_mw > 0
            and p.sorption_capacity_mw > 0 and t_b >= t_in_min):
        t_gen_out = max(t_b - dt_max, t_out_min, t_floor)
        drive_max = brine_kg_s * cpb * (t_b - t_gen_out) / 1e6
        q = min(cool_mw, p.sorption_capacity_mw, drive_max * cop_s)
        drive = q / cop_s
        out.update(cool_sorption=q, sorption_drive=drive)
        t_b -= drive * 1e6 / (brine_kg_s * cpb)
        out["rejection_mw"] += q + drive

    # 2. electric chiller for the rest
    rest = cool_mw - out["cool_sorption"]
    q = min(rest, p.elec_chiller_capacity_mw)
    cop_e = electric_chiller_cop(p, cfg.t_cool_supply)
    out["cool_electric"] = q
    out["chiller_elec"] = q / cop_e if q > 0 else 0.0
    out["rejection_mw"] += q * (1 + 1 / cop_e) if q > 0 else 0.0
    out["cool_unmet"] = max(0.0, rest - q)

    # 3. heating: network flow from demand
    t_r, t_s = cfg.t_heat_return, cfg.t_heat_supply
    m_net = heat_mw * 1e6 / (CP_WATER * (t_s - t_r)) if heat_mw > 0 else 0.0
    t_n = t_r
    if m_net > 0 and brine_kg_s > 0:
        t_b_min = max(t_r + p.hx_approach_k, t_floor)
        q_brine = max(0.0, brine_kg_s * cpb * (t_b - t_b_min)) / 1e6
        q_net = max(0.0, m_net * CP_WATER * (min(t_s, t_b - p.hx_approach_k) - t_r)) / 1e6
        q = min(q_brine, q_net)
        out["heat_direct"] = q
        t_b -= q * 1e6 / (brine_kg_s * cpb)
        t_n = t_r + q * 1e6 / (m_net * CP_WATER)
    out["t_after_direct_c"] = t_n

    # 4. CHP on associated gas (runs whenever doublets produce: the gas has to go
    #    somewhere and flaring is excluded). Its heat tops up the network.
    if p.assoc_gas_use == "chp" and gas_fuel_mw > 0:
        chp_heat = gas_fuel_mw * p.chp_heat_eff
        need0 = max(0.0, heat_mw - out["heat_direct"])
        used = min(chp_heat, need0)
        out.update(heat_chp=used, chp_elec=gas_fuel_mw * p.chp_elec_eff,
                   chp_heat_dumped=chp_heat - used, assoc_gas_used_mw=gas_fuel_mw)
        if m_net > 0:
            t_n += used * 1e6 / (m_net * CP_WATER)
        gas_fuel_mw = 0.0

    # 5. heat pump: brine after direct HX as source, lifts network to supply T
    need = heat_mw - out["heat_direct"] - out["heat_chp"]
    if need > 1e-9 and p.hp_capacity_mw > 0 and brine_kg_s > 0:
        t_src_out_min = max(t_floor, p.hp_min_source_out_c)
        src_max = brine_kg_s * cpb * max(0.0, t_b - t_src_out_min) / 1e6
        q_sink = min(need, p.hp_capacity_mw)
        t_sink_out = t_n + q_sink * 1e6 / (m_net * CP_WATER)
        cop = 3.0
        for _ in range(30):  # fixed point on source outlet temperature
            q_src = q_sink * (1 - 1 / cop)
            if q_src > src_max:
                q_src = src_max
                q_sink = q_src / (1 - 1 / cop)
                t_sink_out = t_n + q_sink * 1e6 / (m_net * CP_WATER)
            t_src_out = t_b - q_src * 1e6 / (brine_kg_s * cpb)
            new = lorenz_cop(p.hp_eta_lorenz, t_n, t_sink_out, t_b, t_src_out, p.hp_cop_max)
            if abs(new - cop) < 1e-4:
                cop = new
                break
            cop = new
        q_src = q_sink * (1 - 1 / cop)
        if q_src > src_max:  # final COP update must not break the 40 C brine cap
            q_src = src_max
            q_sink = q_src / (1 - 1 / cop)
        out.update(heat_hp=q_sink, hp_elec=q_sink / cop, hp_cop=cop)
        t_b -= q_src * 1e6 / (brine_kg_s * cpb)
    out["brine_out_c"] = t_b if brine_kg_s > 0 else float("nan")

    # 6. boiler: any remaining associated gas first, then natural gas
    rest = heat_mw - out["heat_direct"] - out["heat_chp"] - out["heat_hp"]
    q = min(rest, p.boiler_capacity_mw)
    fuel = q / cfg.boiler_eff
    assoc = min(fuel, gas_fuel_mw)
    out["assoc_gas_used_mw"] += assoc
    out["ng_used_mw"] = fuel - assoc
    out["heat_boiler_assoc"] = assoc * cfg.boiler_eff
    out["heat_boiler_ng"] = q - out["heat_boiler_assoc"]
    out["assoc_gas_unused_mw"] = gas_fuel_mw - assoc
    out["heat_unmet"] = max(0.0, rest - q)

    out["rejection_elec"] = out["rejection_mw"] * p.rejection_aux_frac
    return out
