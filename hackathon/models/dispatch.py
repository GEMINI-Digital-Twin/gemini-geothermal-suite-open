"""Runs a design through all 365 days and checks it.

evaluate_design simulates each day of 2027 and returns the design, KPIs,
economics, violations and the daily table. Violations are "hard" (a rule from
the brief or the 30-year lifetime is broken), "warning" (something an engineer
should look at) or "info".

Our own modelling choices (see notes/decisions.md): flows are tried in steps
of 25 m3/h from the brief's minimum; each day we take the lowest flow that
needs no more than 1% extra backup compared with the best flow; all active
doublets run at the same flow.
"""

from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd

from . import subsurface as sub
from .config import load_config
from .economics import design_economics
from .surface import SurfaceParams, simulate_day

HOURS = 24.0
FLOW_STEP_M3H = 25.0


@dataclass
class Design:
    """One candidate system: wells, flows, outages and surface equipment."""

    depth_m: float = 2500.0
    n_doublets: int = 2
    max_flow_m3h: float = 300.0
    spacing_m: float = None             # None = config base value
    outage: str = "staggered"           # staggered | simultaneous
    outage_starts: list = None          # day index per doublet; None = auto
    heating_return_c: float = None      # None = config base value
    surface: SurfaceParams = field(default_factory=SurfaceParams)

    def as_dict(self):
        return asdict(self)


def load_demand(cfg):
    h = pd.read_csv(cfg.demand_path("heating"))
    c = pd.read_csv(cfg.demand_path("cooling"))
    return pd.DataFrame({
        "date": pd.to_datetime(h["date"], dayfirst=True),
        "heat_mw": h["heating_demand_MWth"].astype(float),
        "cool_mw": c["cooling_demand_MWcool"].astype(float),
    })


def doublet_table(cfg, depth_m, max_flow_m3h, spacing_m):
    """Performance of one doublet at each flow step, from the brief's minimum to max flow."""
    flows = np.arange(cfg.q_min, max_flow_m3h + 1e-9, FLOW_STEP_M3H)
    if flows[-1] < max_flow_m3h:
        flows = np.append(flows, max_flow_m3h)
    return pd.DataFrame([sub.doublet_performance(cfg, depth_m, float(q), spacing_m) for q in flows])


def auto_outage_starts(demand, n, mode, outage_days):
    """Put each doublet's 35-day outage where total demand is lowest."""
    load = (demand["heat_mw"] + demand["cool_mw"]).to_numpy()
    sums = np.array([load[s:s + outage_days].sum() for s in range(365 - outage_days + 1)])
    order = list(np.argsort(sums))
    if mode == "simultaneous":
        return [int(order[0])] * n
    starts = []
    for s in order:
        if all(abs(int(s) - t) >= outage_days for t in starts):
            starts.append(int(s))
        if len(starts) == n:
            break
    return starts


def evaluate_design(design, cfg=None, demand=None):
    """Simulate the design for 365 days and collect KPIs, costs and violations."""
    if cfg is None:
        over = {"heating_return_c": design.heating_return_c} if design.heating_return_c else None
        cfg = load_config(overrides=over)
    if demand is None:
        demand = load_demand(cfg)
    spacing = design.spacing_m or cfg.well_spacing_m
    p = design.surface
    outage_days = 365 - cfg.op_days
    starts = design.outage_starts or auto_outage_starts(
        demand, design.n_doublets, design.outage, outage_days)
    offline = np.zeros((design.n_doublets, 365), dtype=bool)
    for i, s in enumerate(starts[:design.n_doublets]):
        offline[i, s:s + outage_days] = True

    table = doublet_table(cfg, design.depth_m, design.max_flow_m3h, spacing)
    rows = []
    for d in range(365):
        h, c = demand.at[d, "heat_mw"], demand.at[d, "cool_mw"]
        k = int((~offline[:, d]).sum())
        if k == 0:
            r, o = None, simulate_day(cfg, p, h, c, 0.0, 0.0, 0.0)
        else:
            cands = []
            for _, r_ in table.iterrows():
                o_ = simulate_day(cfg, p, h, c, k * r_.brine_mass_flow_kg_s,
                                  r_.wellhead_temperature_c, k * r_.gas_ch4_fuel_mw)
                backup = (o_["heat_unmet"] + o_["cool_unmet"]) * 1e3 + o_["heat_boiler_ng"] \
                    + o_["cool_electric"]
                cands.append((backup, r_, o_))
            bmin = min(x[0] for x in cands)
            r, o = next((r_, o_) for b, r_, o_ in cands if b <= bmin * 1.01 + 1e-6)
        row = {"day": d, "date": demand.at[d, "date"], "heat_demand_mw": h,
               "cool_demand_mw": c, "active_doublets": k, **o}
        if r is not None:
            row.update(flow_m3h=r.flow_m3h, wellhead_t_c=r.wellhead_temperature_c,
                       pump_elec=k * r.total_pump_power_mw,
                       brine_dt_k=r.wellhead_temperature_c - o["brine_out_c"])
        else:
            row.update(flow_m3h=0.0, wellhead_t_c=np.nan, pump_elec=0.0, brine_dt_k=0.0)
        rows.append(row)
    daily = pd.DataFrame(rows)
    doublet_power = float(table.iloc[-1].geothermal_heat_mw)
    econ = design_economics(cfg, design, daily, doublet_power)
    kpis = _kpis(daily, cfg, econ, offline, spacing)
    violations = check_constraints(design, cfg, daily, table, offline, spacing, kpis)
    d = design.as_dict() | {"outage_starts": starts, "spacing_m": spacing,
                            "heating_return_c": cfg.t_heat_return}
    return {"design": d, "kpis": kpis, "economics": econ, "violations": violations,
            "daily": daily, "doublet_table": table}


def _kpis(daily, cfg, econ, offline, spacing):
    e = lambda col: float(daily[col].sum() * HOURS / 1000)  # GWh
    heat_total = e("heat_demand_mw")
    elec = e("pump_elec") + e("hp_elec") + e("chiller_elec")
    # annual average flow per doublet (zero on its outage days), for breakthrough
    flows = []
    for i in range(offline.shape[0]):
        f = np.where(offline[i], 0.0, daily.flow_m3h.to_numpy())
        flows.append(float(f.mean()))
    k = {
        "lcoh_eur_per_mwh": econ["lcoh_eur_per_mwh"],
        "capex_total_meur": econ["capex_total_meur"],
        "heat_demand_gwh": heat_total,
        "cool_demand_gwh": e("cool_demand_mw"),
        "heat_direct_gwh": e("heat_direct"),
        "heat_hp_gwh": e("heat_hp"),
        "heat_chp_gwh": e("heat_chp"),
        "heat_boiler_ng_gwh": e("heat_boiler_ng"),
        "heat_unmet_gwh": e("heat_unmet"),
        "cool_sorption_gwh": e("cool_sorption"),
        "cool_electric_gwh": e("cool_electric"),
        "cool_unmet_gwh": e("cool_unmet"),
        "electricity_use_gwh": elec,
        "chp_electricity_gwh": e("chp_elec"),
        "net_electricity_gwh": elec - e("chp_elec"),
        "natural_gas_gwh": e("ng_used_mw"),
        "peak_heat_delivered_mw": float((daily.heat_direct + daily.heat_hp + daily.heat_chp
                                         + daily.heat_boiler_ng).max()),
        "peak_cool_delivered_mw": float((daily.cool_sorption + daily.cool_electric).max()),
        "max_hp_load_mw": float(daily.heat_hp.max()),
        "max_boiler_load_mw": float(daily.heat_boiler_ng.max()),
        "max_elec_chiller_load_mw": float(daily.cool_electric.max()),
        "max_sorption_load_mw": float(daily.cool_sorption.max()),
        "mean_hp_cop": float(daily.loc[daily.heat_hp > 0, "hp_cop"].mean())
        if (daily.heat_hp > 0).any() else None,
        "annual_mean_flow_m3h_per_doublet": max(flows) if flows else 0.0,
        "breakthrough_years": sub.thermal_breakthrough_years(cfg, spacing, max(flows) if flows else 0),
    }
    k["heat_share_geothermal_direct_and_hp"] = (k["heat_direct_gwh"] + k["heat_hp_gwh"]) / heat_total
    k["heat_share_no_purchased_fuel"] = (k["heat_direct_gwh"] + k["heat_hp_gwh"]
                                         + k["heat_chp_gwh"]) / heat_total
    k["geothermal_cool_share"] = k["cool_sorption_gwh"] / k["cool_demand_gwh"]
    # CO2 in kt/yr (GWh x kg/kWh = kt). Negative net electricity (CHP export) counts as avoided.
    k["co2_grid_kt"] = k["net_electricity_gwh"] * cfg.elec_co2_kg_kwh
    k["co2_natural_gas_kt"] = k["natural_gas_gwh"] * cfg.ng_co2_kg_per_mwh / 1000
    k["co2_associated_gas_kt"] = e("assoc_gas_used_mw") * cfg.assoc_gas_co2_kg_per_mwh / 1000
    k["co2_total_kt"] = k["co2_grid_kt"] + k["co2_natural_gas_kt"] + k["co2_associated_gas_kt"]
    return {a: (round(b, 3) if isinstance(b, float) else b) for a, b in k.items()}


def check_constraints(design, cfg, daily, table, offline, spacing, kpis):
    """Hard rules from the brief and lifetime, plus engineering warnings."""
    v = []
    dv = cfg.raw["design_variables"]

    def add(severity, constraint, detail, days=None):
        v.append({"severity": severity, "constraint": constraint, "detail": detail,
                  "n_days": len(days) if days else None})

    if not cfg.n_min <= design.n_doublets <= cfg.n_max:
        add("hard", "doublet_count", f"{design.n_doublets} doublets; allowed {cfg.n_min}-{cfg.n_max}")
    if not cfg.q_min <= design.max_flow_m3h <= cfg.q_max:
        add("hard", "flow_range", f"max flow {design.max_flow_m3h} m3/h outside {cfg.q_min}-{cfg.q_max}")
    act = daily[daily.active_doublets > 0]
    bad = act[(act.flow_m3h < cfg.q_min - 1e-6) | (act.flow_m3h > cfg.q_max + 1e-6)]
    if len(bad):
        add("hard", "flow_range", "active flow outside 50-300 m3/h", bad.day.tolist())
    bad = act[act.brine_dt_k > cfg.dt_brine_max + 1e-6]
    if len(bad):
        add("hard", "brine_cooling", f"brine cooled more than {cfg.dt_brine_max} C", bad.day.tolist())
    for i in range(design.n_doublets):
        on = int((~offline[i]).sum())
        if on > cfg.op_days:
            add("hard", "operating_days", f"doublet {i + 1} runs {on} days > {cfg.op_days}")
    s = design.surface  # we print installed capacities so a 0 MW chiller is obvious (run 1c)
    bad = daily[daily.heat_unmet > 1e-3]
    if len(bad):
        add("hard", "heating_demand", f"heating not met on {len(bad)} days, max shortfall "
            f"{bad.heat_unmet.max():.2f} MW (100 C supply); installed: heat pump "
            f"{s.hp_capacity_mw:g} MW, boiler {s.boiler_capacity_mw:g} MW", bad.day.tolist())
    bad = daily[daily.cool_unmet > 1e-3]
    if len(bad):
        add("hard", "cooling_demand", f"cooling not met on {len(bad)} days, max shortfall "
            f"{bad.cool_unmet.max():.2f} MW (20 C supply); installed: {s.chiller_type} chiller "
            f"{s.sorption_capacity_mw:g} MW, electric chiller {s.elec_chiller_capacity_mw:g} MW",
            bad.day.tolist())
    if kpis["breakthrough_years"] < cfg.lifetime_years:
        add("hard", "thermal_breakthrough",
            f"breakthrough after {kpis['breakthrough_years']:.1f} years < {cfg.lifetime_years} "
            f"(spacing {spacing:.0f} m, mean flow {kpis['annual_mean_flow_m3h_per_doublet']:.0f} m3/h)")
    lo, hi = dv["well_depth_m"]
    if not lo <= design.depth_m <= hi:
        add("hard", "depth_range", f"depth {design.depth_m} m outside {lo}-{hi} m")
    lo, hi = dv["well_spacing_m"]
    if not lo <= spacing <= hi:
        add("hard", "spacing_range", f"spacing {spacing} m outside {lo}-{hi} m")
    t_res = sub.reservoir_temperature_c(cfg, design.depth_m)
    if t_res > 100:
        add("warning", "pvt_validity", f"reservoir {t_res:.0f} C is above GEMINI's 100 C "
            "pure-water PVT range; constant brine properties used")
    dumped = daily[daily.chp_heat_dumped > 1e-3]
    if len(dumped):
        add("info", "chp_heat_dumped", f"CHP heat exceeds demand on {len(dumped)} days, up to "
            f"{dumped.chp_heat_dumped.max():.2f} MW rejected", dumped.day.tolist())
    peak = int(daily.heat_demand_mw.idxmax())
    k = max(0, int(daily.at[peak, "active_doublets"]) - 1)
    r = table.iloc[-1]
    o = simulate_day(cfg, design.surface, daily.at[peak, "heat_demand_mw"],
                     daily.at[peak, "cool_demand_mw"], k * r.brine_mass_flow_kg_s,
                     r.wellhead_temperature_c, k * r.gas_ch4_fuel_mw)
    if o["heat_unmet"] > 1e-3:
        add("warning", "n_minus_1", f"if one doublet trips on the peak day "
            f"({daily.at[peak, 'date']:%d %b}), {o['heat_unmet']:.1f} MW heat is unmet")
    return v


def summarize(result):
    """A few lines of text summarising a result."""
    k, v = result["kpis"], result["violations"]
    hard = [x for x in v if x["severity"] == "hard"]
    lines = [
        f"LCOH {k['lcoh_eur_per_mwh']:.1f} EUR/MWh (CAPEX {k['capex_total_meur']:.1f} M EUR)",
        f"Heat: direct {k['heat_direct_gwh']:.1f}, HP {k['heat_hp_gwh']:.1f}, CHP {k['heat_chp_gwh']:.1f}, "
        f"boiler {k['heat_boiler_ng_gwh']:.1f}, unmet {k['heat_unmet_gwh']:.2f} GWh of {k['heat_demand_gwh']:.1f}",
        f"Cool: absorption {k['cool_sorption_gwh']:.1f}, electric {k['cool_electric_gwh']:.1f}, "
        f"unmet {k['cool_unmet_gwh']:.2f} GWh of {k['cool_demand_gwh']:.1f}",
        f"Net electricity {k['net_electricity_gwh']:.1f} GWh, natural gas {k['natural_gas_gwh']:.1f} GWh, "
        f"breakthrough {k['breakthrough_years']:.0f} years",
        f"CO2 {k['co2_total_kt']:.1f} kt/yr (grid {k['co2_grid_kt']:.1f}, natural gas "
        f"{k['co2_natural_gas_kt']:.1f}, associated gas {k['co2_associated_gas_kt']:.1f})",
        f"Violations: {len(hard)} hard, {len(v) - len(hard)} other",
    ]
    lines += [f"  [{x['severity']}] {x['constraint']}: {x['detail']}" for x in v]
    return "\n".join(lines)
