"""Surface plant models for one day of steady (daily-average) operation.

Layer C. Pure functions: temperatures in C, powers in MW, flows in kg/s.

Brine cascade (hottest use first), on the combined stream of active doublets:

    wellhead -> [absorption generator] -> [direct heating HX]
             -> [CHP heat from associated gas, network side]
             -> [heat pump evaporator] -> injection (>= wellhead T - 40 C)

Heating network (return -> 100 C): direct HX -> CHP -> heat pump -> boiler
Cooling network (-> 20 C):          absorption chiller -> electric chiller

Every parameter has a source; see SOURCES below and notes/decisions.md.
"""

import math
import sys
from dataclasses import asdict, dataclass

from .config import REPO_ROOT

_SRC = str(REPO_ROOT / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

CP_WATER = 4217.0  # J/kgK network water: GEMINI PVTConstantSTP CPL
K0 = 273.15

SOURCES = {
    "hx_approach_k": "Slihte, Krizmane & Dzelzitis (2016), CLIMA 2016: flow approach 3-5 C (lower end)",
    "hp_eta_lorenz": "GEMINI HeatpumpBasic default 0.5; Pieper et al. (2020) Energy 205, p.12: 'a value used in literature'",
    "hp_min_source_out_c": "GEMINI HeatpumpBasic Ts_in_minimum = 10 C",
    "absorption_rated": "US DOE (2017) Absorption Chillers for CHP Systems, p.4 Table 2: COP 0.70, hot water 88->83 C (5 K) and 98->88 C (10 K); CIBSE Journal Module 91 (2016): single-stage minimum 80 C",
    "absorption_dh": "CIBSE Journal Module 91 (2016): evolved designs 'requiring only 70C hot water'; district-heating units with 'outlet hot water temperature as low as 50C'; COP as DOE (2017)",
    "electric_chiller_cop": "NRCan chiller regulations: min full-load COP 6.286 (water-cooled, >= 2110 kW, AHRI 550/590) x 1.37 (Thu et al. 2017, Appl. Therm. Eng. 123: +37-40% COP at 17 C chilled water vs AHRI)",
    "chp": "US EPA (2015) Catalog of CHP Technologies, Sec. 2, Table 2-2 pp.2-10/2-11, system 2 (633 kW): 34.5% el, 44.4% heat (HHV), x1.10 (HHV ~10% above LHV, p.2-5 fn.10)",
    "boiler_efficiency": "GEMINI doublet_plant.json boiler efficiency_factor 0.8 (in config)",
}


@dataclass
class SurfaceParams:
    """Technology parameters (sources in SOURCES) and design capacities."""

    hx_approach_k: float = 3.0
    hp_eta_lorenz: float = 0.5
    hp_capacity_mw: float = 0.0              # design variable, sink side
    hp_min_source_out_c: float = 10.0
    chiller_type: str = "absorption_rated"   # absorption_rated | absorption_dh | electric
    sorption_capacity_mw: float = 0.0        # design variable, cooling output
    absorption_cop: float = 0.70
    elec_chiller_capacity_mw: float = 0.0    # design variable (top-up and backup)
    elec_chiller_cop: float = 6.286 * 1.37
    boiler_capacity_mw: float = 0.0          # design variable (peak and backup)
    chp_elec_eff: float = 0.345 * 1.10
    chp_heat_eff: float = 0.444 * 1.10

    def as_dict(self):
        return asdict(self)


ABSORPTION_LIMITS = {  # (min drive inlet C, max brine drop K, min drive outlet C)
    "absorption_rated": (80.0, 10.0, None),   # DOE rated drops 5-10 K; CIBSE min 80 C
    "absorption_dh": (70.0, None, 50.0),      # CIBSE: 70 C evolved, outlet down to 50 C
}


def lorenz_cop(eta, t_sink_in, t_sink_out, t_src_in, t_src_out):
    """Lorenz COP from log-mean sink/source temperatures (GEMINI's formula, no cap).

    Numerical guard only: the log-mean lift is floored at 1 K so the formula
    stays finite when sink and source temperatures cross (method choice).
    """
    def lm(a, b):
        a, b = a + K0, b + K0
        return (a - b) / math.log(a / b) if abs(a - b) > 1e-6 else a
    th, ts = lm(t_sink_out, t_sink_in), lm(t_src_in, t_src_out)
    return eta * th / max(th - ts, 1.0)


def gemini_heatpump_cop(eta, t_sink_in, t_sink_out, t_src_in, sink_m3s, src_m3s):
    """Run GEMINI's own HeatpumpBasic (Lorenz) for cross-checking lorenz_cop."""
    from gemini_model.heatpump.heatpump_basic import HeatpumpBasic

    hp = HeatpumpBasic()
    hp.update_parameters({"mode": "lorenz", "eta_lorenz": eta, "Th_out_target": t_sink_out})
    hp.calculate_output({"Th_in": t_sink_in, "Ts_in": t_src_in,
                         "hot_flow_rate": sink_m3s, "source_flow_rate": src_m3s})
    return hp.output


def simulate_day(cfg, p, heat_mw, cool_mw, brine_kg_s, t_wellhead_c, gas_fuel_mw=0.0):
    """Meet one day's heating and cooling demand. Returns energy flows in MW.

    ``brine_kg_s`` is the combined flow of active doublets (0 on outage days).
    ``gas_fuel_mw`` is associated-gas fuel available that day; it runs a CHP
    whenever doublets produce (flaring is excluded).
    """
    cpb = cfg.cp
    t_floor = t_wellhead_c - cfg.dt_brine_max          # 40 C cap, producer -> injector
    t_b = t_wellhead_c
    keys = ("cool_sorption", "cool_electric", "cool_unmet", "sorption_drive", "heat_direct",
            "heat_chp", "chp_elec", "chp_heat_dumped", "heat_hp", "hp_elec", "hp_cop",
            "heat_boiler_ng", "ng_used_mw", "heat_unmet", "chiller_elec", "assoc_gas_used_mw",
            "brine_out_c", "t_after_direct_c")
    out = {k: 0.0 for k in keys}

    # 1. absorption chiller on the hottest brine
    if p.chiller_type in ABSORPTION_LIMITS and brine_kg_s > 0 and cool_mw > 0 \
            and p.sorption_capacity_mw > 0:
        t_in_min, dt_max, t_out_min = ABSORPTION_LIMITS[p.chiller_type]
        if t_b >= t_in_min:
            t_gen_out = t_floor
            if dt_max is not None:
                t_gen_out = max(t_gen_out, t_b - dt_max)
            if t_out_min is not None:
                t_gen_out = max(t_gen_out, t_out_min)
            drive_max = max(0.0, brine_kg_s * cpb * (t_b - t_gen_out) / 1e6)
            q = min(cool_mw, p.sorption_capacity_mw, drive_max * p.absorption_cop)
            drive = q / p.absorption_cop
            out.update(cool_sorption=q, sorption_drive=drive)
            t_b -= drive * 1e6 / (brine_kg_s * cpb)

    # 2. electric chiller for the rest
    rest = cool_mw - out["cool_sorption"]
    q = min(rest, p.elec_chiller_capacity_mw)
    out["cool_electric"] = q
    out["chiller_elec"] = q / p.elec_chiller_cop if q > 0 else 0.0
    out["cool_unmet"] = max(0.0, rest - q)

    # 3. direct heating: network flow from demand
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

    # 4. CHP on associated gas (runs whenever doublets produce)
    if gas_fuel_mw > 0:
        chp_heat = gas_fuel_mw * p.chp_heat_eff
        used = min(chp_heat, max(0.0, heat_mw - out["heat_direct"]))
        out.update(heat_chp=used, chp_elec=gas_fuel_mw * p.chp_elec_eff,
                   chp_heat_dumped=chp_heat - used, assoc_gas_used_mw=gas_fuel_mw)
        if m_net > 0:
            t_n += used * 1e6 / (m_net * CP_WATER)

    # 5. heat pump: brine after direct HX as source, lifts network to supply T
    need = heat_mw - out["heat_direct"] - out["heat_chp"]
    if need > 1e-9 and p.hp_capacity_mw > 0 and brine_kg_s > 0:
        src_max = brine_kg_s * cpb * max(0.0, t_b - max(t_floor, p.hp_min_source_out_c)) / 1e6
        q_sink = min(need, p.hp_capacity_mw)
        cop = 3.0
        for _ in range(50):  # fixed point on the source outlet temperature
            q_src = q_sink * (1 - 1 / cop)
            if q_src > src_max:
                q_src = src_max
                q_sink = q_src / (1 - 1 / cop)
            t_sink_out = t_n + q_sink * 1e6 / (m_net * CP_WATER)
            t_src_out = t_b - q_src * 1e6 / (brine_kg_s * cpb)
            new = lorenz_cop(p.hp_eta_lorenz, t_n, t_sink_out, t_b, t_src_out)
            if abs(new - cop) < 1e-5:
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

    # 6. natural gas boiler for the rest
    rest = heat_mw - out["heat_direct"] - out["heat_chp"] - out["heat_hp"]
    q = min(max(0.0, rest), p.boiler_capacity_mw)
    out["heat_boiler_ng"] = q
    out["ng_used_mw"] = q / cfg.boiler_eff
    out["heat_unmet"] = max(0.0, rest - q)
    return out
