"""365-day dispatch of a candidate design, KPIs and constraint checks.

A *design* fixes the hardware (depth, doublets, equipment sizes) and the
outage plan. ``evaluate_design`` runs every day of 2027 and returns:

    {"design", "kpis", "violations", "daily"}

``violations`` is the list the agent reads to revise a design. Each entry has
``severity`` ("hard" = brief constraint broken, "warning" = engineering
concern, "info").
"""

from dataclasses import dataclass, field, asdict, replace

import numpy as np
import pandas as pd

from . import subsurface as sub
from .config import load_config
from .surface import SurfaceParams, simulate_day

HOURS = 24.0


@dataclass
class Design:
    """Hardware and operating plan of one candidate system."""

    depth_m: float = 2500.0
    n_doublets: int = 2
    max_flow_m3h: float = 300.0
    outage: str = "staggered"            # staggered | simultaneous
    outage_starts: list = None           # day index (0-364) per doublet; None = auto
    heating_return_c: float = None       # None = config assumption
    surface: SurfaceParams = field(default_factory=SurfaceParams)

    def as_dict(self):
        d = asdict(self)
        return d


def load_demand(cfg):
    h = pd.read_csv(cfg.demand_path("heating"))
    c = pd.read_csv(cfg.demand_path("cooling"))
    df = pd.DataFrame({
        "date": pd.to_datetime(h["date"], dayfirst=True),
        "heat_mw": h["heating_demand_MWth"].astype(float),
        "cool_mw": c["cooling_demand_MWcool"].astype(float),
    })
    return df


def doublet_table(cfg, depth_m, max_flow_m3h, step=25.0):
    """Per-doublet performance on a flow grid from the brief's minimum to max flow."""
    flows = np.arange(cfg.q_min, max_flow_m3h + 1e-9, step)
    if flows[-1] < max_flow_m3h:
        flows = np.append(flows, max_flow_m3h)
    rows = [sub.doublet_performance(cfg, depth_m, float(q)) for q in flows]
    return pd.DataFrame(rows)


def auto_outage_starts(demand, n, mode, outage_days):
    """Place each doublet's outage window where combined demand is lowest."""
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
    """Run 365 days for ``design``; return design, KPIs, violations and daily table."""
    if cfg is None:
        over = {}
        if design.heating_return_c is not None:
            over["heating_return_c"] = design.heating_return_c
        cfg = load_config(overrides=over or None)
    if demand is None:
        demand = load_demand(cfg)
    p = design.surface
    outage_days = 365 - cfg.op_days
    starts = design.outage_starts or auto_outage_starts(
        demand, design.n_doublets, design.outage, outage_days)
    offline = np.zeros((design.n_doublets, 365), dtype=bool)
    for i, s in enumerate(starts[:design.n_doublets]):
        offline[i, s:s + outage_days] = True

    table = doublet_table(cfg, design.depth_m, design.max_flow_m3h)
    days = []
    for d in range(365):
        h, c = demand.at[d, "heat_mw"], demand.at[d, "cool_mw"]
        k = int((~offline[:, d]).sum())
        best = None
        if k == 0:
            best = (None, simulate_day(cfg, p, h, c, 0.0, 0.0, 0.0))
        else:
            cands = []
            for _, r in table.iterrows():
                o = simulate_day(cfg, p, h, c, k * r.brine_mass_flow_kg_s,
                                 r.wellhead_temperature_c, k * r.gas_ch4_fuel_mw)
                backup = (o["heat_unmet"] + o["cool_unmet"]) * 1e3 + o["heat_boiler_ng"] \
                    + o["cool_electric"]
                cands.append((backup, r, o))
            bmin = min(x[0] for x in cands)
            for backup, r, o in cands:  # lowest flow within 1% of the least backup
                if backup <= bmin * 1.01 + 1e-6:
                    best = (r, o)
                    break
        r, o = best
        row = {"day": d, "date": demand.at[d, "date"], "heat_demand_mw": h,
               "cool_demand_mw": c, "active_doublets": k, **o}
        if r is not None:
            row.update(flow_m3h=r.flow_m3h, wellhead_t_c=r.wellhead_temperature_c,
                       pump_elec=k * r.total_pump_power_mw,
                       brine_dt_k=r.wellhead_temperature_c - o["brine_out_c"])
        else:
            row.update(flow_m3h=0.0, wellhead_t_c=np.nan, pump_elec=0.0, brine_dt_k=0.0)
        days.append(row)
    daily = pd.DataFrame(days)
    kpis = _kpis(daily, design, cfg)
    violations = check_constraints(design, cfg, daily, table, starts, offline)
    return {"design": design.as_dict() | {"outage_starts": starts}, "kpis": kpis,
            "violations": violations, "daily": daily, "doublet_table": table}


def _kpis(daily, design, cfg):
    e = lambda col: float(daily[col].sum() * HOURS / 1000)  # GWh
    heat_total = e("heat_demand_mw")
    elec = e("pump_elec") + e("hp_elec") + e("chiller_elec") + e("rejection_elec")
    k = {
        "heat_demand_gwh": heat_total,
        "cool_demand_gwh": e("cool_demand_mw"),
        "heat_direct_gwh": e("heat_direct"),
        "heat_hp_gwh": e("heat_hp"),
        "heat_chp_gwh": e("heat_chp"),
        "heat_boiler_assoc_gwh": e("heat_boiler_assoc"),
        "heat_boiler_ng_gwh": e("heat_boiler_ng"),
        "heat_unmet_gwh": e("heat_unmet"),
        "cool_sorption_gwh": e("cool_sorption"),
        "cool_electric_gwh": e("cool_electric"),
        "cool_unmet_gwh": e("cool_unmet"),
        "electricity_use_gwh": elec,
        "chp_electricity_gwh": e("chp_elec"),
        "net_electricity_gwh": elec - e("chp_elec"),
        "natural_gas_gwh": e("ng_used_mw"),
        "associated_gas_used_gwh": e("assoc_gas_used_mw"),
        "associated_gas_unused_gwh": e("assoc_gas_unused_mw"),
        "peak_heat_delivered_mw": float((daily.heat_direct + daily.heat_hp + daily.heat_chp
                                         + daily.heat_boiler_assoc + daily.heat_boiler_ng).max()),
        "peak_cool_delivered_mw": float((daily.cool_sorption + daily.cool_electric).max()),
        "max_hp_load_mw": float(daily.heat_hp.max()),
        "max_boiler_load_mw": float((daily.heat_boiler_assoc + daily.heat_boiler_ng).max()),
        "max_elec_chiller_load_mw": float(daily.cool_electric.max()),
        "max_sorption_load_mw": float(daily.cool_sorption.max()),
        "mean_hp_cop": float(daily.loc[daily.heat_hp > 0, "hp_cop"].mean())
        if (daily.heat_hp > 0).any() else None,
    }
    k["heat_share_geothermal_direct_and_hp"] = (k["heat_direct_gwh"] + k["heat_hp_gwh"]) / heat_total
    k["heat_share_no_purchased_fuel"] = (k["heat_direct_gwh"] + k["heat_hp_gwh"]
                                         + k["heat_chp_gwh"] + k["heat_boiler_assoc_gwh"]) / heat_total
    k["geothermal_cool_share"] = k["cool_sorption_gwh"] / k["cool_demand_gwh"]
    return {a: (round(b, 3) if isinstance(b, float) else b) for a, b in k.items()}


def check_constraints(design, cfg, daily, table, starts, offline):
    """Brief constraints (hard) and engineering checks (warning/info)."""
    v = []

    def add(severity, constraint, detail, days=None):
        v.append({"severity": severity, "constraint": constraint, "detail": detail,
                  "days": days[:10] if days else None,
                  "n_days": len(days) if days else None})

    if not cfg.n_min <= design.n_doublets <= cfg.n_max:
        add("hard", "doublet_count", f"{design.n_doublets} doublets; allowed {cfg.n_min}-{cfg.n_max}")
    if design.max_flow_m3h > cfg.q_max or design.max_flow_m3h < cfg.q_min:
        add("hard", "flow_range", f"max flow {design.max_flow_m3h} m3/h outside "
            f"{cfg.q_min}-{cfg.q_max}")
    act = daily[daily.active_doublets > 0]
    bad = act[(act.flow_m3h < cfg.q_min - 1e-6) | (act.flow_m3h > cfg.q_max + 1e-6)]
    if len(bad):
        add("hard", "flow_range", "active flow outside 50-300 m3/h", bad.day.tolist())
    bad = act[act.brine_dt_k > cfg.dt_brine_max + 1e-6]
    if len(bad):
        add("hard", "brine_cooling", f"brine cooled more than {cfg.dt_brine_max} K",
            bad.day.tolist())
    for i in range(design.n_doublets):
        on = int((~offline[i]).sum())
        if on > cfg.op_days:
            add("hard", "operating_days", f"doublet {i + 1} runs {on} days > {cfg.op_days}")
    bad = daily[daily.heat_unmet > 1e-3]
    if len(bad):
        add("hard", "heating_demand", f"heating not met on {len(bad)} days, max shortfall "
            f"{bad.heat_unmet.max():.2f} MW (100 C supply)", bad.day.tolist())
    bad = daily[daily.cool_unmet > 1e-3]
    if len(bad):
        add("hard", "cooling_demand", f"cooling not met on {len(bad)} days, max shortfall "
            f"{bad.cool_unmet.max():.2f} MW (20 C supply)", bad.day.tolist())
    t_res = sub.reservoir_temperature_c(cfg, design.depth_m)
    if t_res > 100:
        add("warning", "pvt_validity", f"reservoir {t_res:.0f} C is above GEMINI's 100 C "
            "pure-water PVT range; constant brine properties used")
    if not 2000 <= design.depth_m <= 4000:
        add("warning", "depth_range", f"depth {design.depth_m} m outside 2,000-4,000 m study range")
    unused = daily[daily.assoc_gas_unused_mw > 1e-3]
    if len(unused):
        add("warning", "associated_gas", "associated gas not used (would be flared)",
            unused.day.tolist())
    dumped = daily[daily.chp_heat_dumped > 1e-3]
    if len(dumped):
        add("info", "chp_heat_dumped", f"CHP heat exceeds demand on {len(dumped)} days, "
            f"up to {dumped.chp_heat_dumped.max():.2f} MW rejected", dumped.day.tolist())
    # N-1: one doublet trips unplanned on the peak heating day
    peak = int(daily.heat_demand_mw.idxmax())
    if design.n_doublets >= 1:
        p = design.surface
        r = table.iloc[-1]
        k = max(0, int(daily.at[peak, "active_doublets"]) - 1)
        o = simulate_day(cfg, p, daily.at[peak, "heat_demand_mw"], daily.at[peak, "cool_demand_mw"],
                         k * r.brine_mass_flow_kg_s, r.wellhead_temperature_c,
                         k * r.gas_ch4_fuel_mw)
        if o["heat_unmet"] > 1e-3:
            add("warning", "n_minus_1", f"if one doublet trips on the peak day "
                f"({daily.at[peak, 'date']:%d %b}), {o['heat_unmet']:.1f} MW heat is unmet")
    return v


def summarize(result):
    """Short text summary for logs and for the agent's context."""
    k, v = result["kpis"], result["violations"]
    hard = [x for x in v if x["severity"] == "hard"]
    lines = [
        f"Heat: direct {k['heat_direct_gwh']:.1f}, HP {k['heat_hp_gwh']:.1f}, CHP {k['heat_chp_gwh']:.1f}, "
        f"boiler(NG) {k['heat_boiler_ng_gwh']:.1f}, unmet {k['heat_unmet_gwh']:.2f} GWh "
        f"of {k['heat_demand_gwh']:.1f}",
        f"Cool: sorption {k['cool_sorption_gwh']:.1f}, electric {k['cool_electric_gwh']:.1f}, "
        f"unmet {k['cool_unmet_gwh']:.2f} GWh of {k['cool_demand_gwh']:.1f}",
        f"Electricity net {k['net_electricity_gwh']:.1f} GWh, natural gas {k['natural_gas_gwh']:.1f} GWh, "
        f"heat from geothermal (direct+HP) {k['heat_share_geothermal_direct_and_hp']:.0%}, "
        f"without purchased fuel {k['heat_share_no_purchased_fuel']:.0%}",
        f"Violations: {len(hard)} hard, {len(v) - len(hard)} other",
    ]
    lines += [f"  [{x['severity']}] {x['constraint']}: {x['detail']}" for x in v]
    return "\n".join(lines)
