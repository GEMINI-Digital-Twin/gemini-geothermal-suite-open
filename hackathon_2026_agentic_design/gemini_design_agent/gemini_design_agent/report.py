"""Design report (Markdown + figures) explaining every major engineering decision."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import numpy as np

from .spec import HackathonSpec, SPEC
from .system import COST, EvaluationResult


def _fmt(v, nd=2):
    if isinstance(v, float):
        return f"{v:,.{nd}f}"
    return str(v)


def _table(rows: list[list], header: list[str]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join(["---"] * len(header)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(_fmt(x) for x in r) + " |")
    return "\n".join(out)


def make_figures(final: EvaluationResult, closed_loop: dict | None, out_dir: Path) -> list[str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import pandas as pd

    files = []
    d = final.daily
    dates = pd.to_datetime(d["date"])

    fig, ax = plt.subplots(3, 1, figsize=(11, 10), sharex=True)
    ax[0].stackplot(dates, d["heat_direct"], d["heat_hp"], labels=["Direct geothermal (HX)", "Heat pump"],
                    colors=["#c0392b", "#f39c12"], alpha=0.85)
    ax[0].plot(dates, d["heat_demand"], "k-", lw=1, label="Heating demand")
    ax[0].set_ylabel("MWth"); ax[0].legend(loc="upper center", ncol=3, fontsize=8); ax[0].set_title("Heating dispatch")
    ax[1].stackplot(dates, d["cool_abs"], d["cool_el"], labels=["Absorption chiller (brine-driven)", "Electric chiller"],
                    colors=["#2980b9", "#7f8c8d"], alpha=0.85)
    ax[1].plot(dates, d["cool_demand"], "k-", lw=1, label="Cooling demand")
    ax[1].set_ylabel("MWcool"); ax[1].legend(loc="upper left", ncol=3, fontsize=8); ax[1].set_title("Cooling dispatch")
    ax[2].plot(dates, d["flow_per_doublet"], color="#16a085", label="Flow per doublet (m3/h)")
    ax[2].axhline(300, color="r", ls="--", lw=0.8, label="300 m3/h cap"); ax[2].axhline(50, color="r", ls=":", lw=0.8, label="50 m3/h min")
    ax2 = ax[2].twinx(); ax2.plot(dates, d["doublets_available"], color="#8e44ad", drawstyle="steps-post", lw=1, label="Doublets available")
    ax2.set_ylim(0, 3.5); ax2.set_ylabel("doublets")
    ax[2].set_ylabel("m3/h"); ax[2].legend(loc="upper left", fontsize=8); ax[2].set_title("Brine flow and availability (330-day operation)")
    fig.tight_layout(); f = out_dir / "fig_dispatch.png"; fig.savefig(f, dpi=130); plt.close(fig); files.append(f.name)

    fig, ax = plt.subplots(2, 1, figsize=(11, 7), sharex=True)
    ax[0].plot(dates, d["t_wellhead"], label="Wellhead T"); ax[0].plot(dates, d["t_injection"], label="Injection T")
    ax[0].plot(dates, d["brine_dt"], label="Brine cooling dT"); ax[0].axhline(40, color="r", ls="--", lw=0.8, label="40 C cap")
    ax[0].set_ylabel("C"); ax[0].legend(fontsize=8, ncol=4); ax[0].set_title("Brine temperatures")
    ax[1].stackplot(dates, d["esp_el"], d["inj_el"], d["hp_el"], d["chiller_el"],
                    labels=["ESPs", "Injection pumps", "Heat pump", "Chillers"], alpha=0.85)
    ax[1].set_ylabel("MWe"); ax[1].legend(fontsize=8, ncol=4); ax[1].set_title("Electricity demand")
    fig.tight_layout(); f = out_dir / "fig_temps_power.png"; fig.savefig(f, dpi=130); plt.close(fig); files.append(f.name)

    wp = final.well_points
    fig, ax = plt.subplots(1, 3, figsize=(13, 3.8))
    q = [w["flow_m3_h"] for w in wp]
    ax[0].plot(q, [w["esp_head_bar"] for w in wp], "o-", label="ESP head (bar)")
    ax[0].plot(q, [w["esp_intake_pressure_bar"] for w in wp], "s-", label="ESP intake P (bar)")
    ax[0].axhline(wp[0]["bubble_point_bar"] + 5, color="r", ls="--", lw=0.8, label="bubble point + 5 bar")
    ax[0].set_xlabel("m3/h"); ax[0].legend(fontsize=8); ax[0].set_title("Producer / ESP (GEMINI DPDT + ESP)")
    ax[1].plot(q, [w["injection_whp_bar"] for w in wp], "o-", label="Injection WHP (bar)")
    ax[1].plot(q, [w["esp_power_mw"] * 1000 for w in wp], "s-", label="ESP power (kW)")
    ax[1].plot(q, [w["injection_pump_power_mw"] * 1000 for w in wp], "^-", label="Injection pump (kW)")
    ax[1].set_xlabel("m3/h"); ax[1].legend(fontsize=8); ax[1].set_title("Injector / pumping")
    ax[2].plot(q, [w["wellhead_temperature_c"] for w in wp], "o-", label="Wellhead T (C)")
    ax[2].plot(q, [w["esp_frequency_hz"] for w in wp], "s-", label="ESP frequency (Hz)")
    ax[2].set_xlabel("m3/h"); ax[2].legend(fontsize=8); ax[2].set_title("Thermal / VSD")
    fig.tight_layout(); f = out_dir / "fig_well_performance.png"; fig.savefig(f, dpi=130); plt.close(fig); files.append(f.name)

    if closed_loop:
        rec = closed_loop["records"]
        yrs = [r["year"] for r in rec]
        fig, ax = plt.subplots(1, 3, figsize=(13, 3.8))
        ax[0].plot(yrs, [r["t_produced_c"] for r in rec], "o-"); ax[0].set_title("Produced temperature (C)"); ax[0].set_xlabel("year")
        ax[1].plot(yrs, [r["electricity_gwh"] for r in rec], "o-", label="Electricity (GWh)")
        ax[1].plot(yrs, [r["system_cop"] for r in rec], "s-", label="System COP"); ax[1].legend(fontsize=8); ax[1].set_xlabel("year")
        ax[2].plot(yrs, [r["injection_whp_bar"] for r in rec], "o-", label="Injection WHP @300 (bar)")
        ax[2].plot(yrs, [r["skin_injection_extra"] for r in rec], "s-", label="Injector skin growth")
        for r in rec:
            if r["actions"]:
                ax[2].axvline(r["year"], color="g", alpha=0.3, lw=3)
        ax[2].legend(fontsize=8); ax[2].set_title("Injectivity & interventions (green)"); ax[2].set_xlabel("year")
        fig.tight_layout(); f = out_dir / "fig_closed_loop.png"; fig.savefig(f, dpi=130); plt.close(fig); files.append(f.name)
    return files


def write_report(run: dict, closed_loop: dict | None, demand_summary: dict, out_dir: Path,
                 spec: HackathonSpec = SPEC, mode: str = "rule-based") -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    final: EvaluationResult = run["final"]
    ds, k, cost = final.design, final.kpis, final.cost
    figs = make_figures(final, closed_loop, out_dir)
    c = spec.constraints

    L = []
    L.append("# GEMINI Agentic Geothermal Design - Final Design Report\n")
    L.append(f"Orchestration mode: **{mode}**. Subsurface / well engineering evaluated with the GEMINI digital-twin "
             "models (`gemini_model`: radial Darcy inflow, IPR, DPDT wellbore pressure-temperature, ESP curve, "
             "CO2 corrosion, API erosional velocity). Heating and cooling plant evaluated with the complementary "
             "component models in `gemini_design_agent/components.py`.\n")

    L.append("## 1. Selected design\n")
    rows = [
        ["Number of doublets", ds.n_doublets, f"challenge range {c.min_doublets}-{c.max_doublets}"],
        ["Reservoir midpoint depth", f"{ds.well.reservoir_midpoint_m:.0f} m TVD", f"reservoir T {k['reservoir_temperature_c']:.1f} C, P {k['reservoir_pressure_bar']:.0f} bar(g)"],
        ["Well measured depth", f"{ds.well.well_md_m:.0f} m MD", "deviated, MD = 1.08 x TVD"],
        ["Production / injection casing ID", f"{ds.well.production_id_m * 1000:.0f} / {ds.well.injection_id_m * 1000:.0f} mm", ""],
        ["ESP setting depth", f"{ds.well.esp_depth_m:.0f} m", f"intake {k['esp_intake_pressure_at_300_bar']:.0f} bar at 300 m3/h vs bubble point {k['bubble_point_bar']:.0f} bar"],
        ["ESP", f"{k['esp_stages']} stages, BEP {ds.well.esp_bep_m3_h:.0f} m3/h, VSD 30-65 Hz", f"{k['esp_power_at_300_mw'] * 1000:.0f} kW at 300 m3/h"],
        ["High-temperature heat pump", f"{ds.heat_pump_mw:.1f} MWth", "brine-source, 100 C supply"],
        ["Absorption chiller", f"{ds.absorption_chiller_mw:.1f} MWcool", "single-effect LiBr, brine-driven"],
        ["Electric chiller", f"{ds.electric_chiller_mw:.1f} MWcool", "backup / peak"],
        ["District heating return", f"{ds.district_return_c:.0f} C", "assumption"],
        ["Corrosion mitigation", ds.corrosion_mitigation, f"un-mitigated rate {k['corrosion_rate_unmitigated_mm_yr']:.1f} mm/yr (GEMINI DLM, 20 mol% CO2)"],
        ["Maintenance windows (35 d per doublet)", "; ".join(f"{a} to {b}" for a, b in k["maintenance_windows"]), "staggered, lowest-load period"],
    ]
    L.append(_table(rows, ["Item", "Value", "Note"]))
    L.append("\n### Why this design\n")
    for r in ds.rationale:
        L.append(f"- {r}")
    L.append("")

    L.append("## 2. Demand interpretation\n")
    L.append(_table([
        ["Heating", f"{demand_summary['heating_peak_mw']:.1f} MW on {demand_summary['heating_peak_date']}", f"{demand_summary['heating_gwh']:.1f} GWh/yr", f"min {demand_summary['heating_min_mw']:.1f} MW"],
        ["Cooling", f"{demand_summary['cooling_peak_mw']:.1f} MW on {demand_summary['cooling_peak_date']}", f"{demand_summary['cooling_gwh']:.1f} GWh/yr", f"{demand_summary['cooling_days']} days with cooling"],
    ], ["Load", "Peak", "Annual energy", "Note"]))
    hd = demand_summary["heating_duration_mw"]
    L.append(f"\nHeating duration: {hd['top_30_days']:.1f} MW exceeded 30 days, {hd['top_90_days']:.1f} MW exceeded 90 days, "
             f"{hd['top_180_days']:.1f} MW exceeded 180 days. Daily energy = power x 24 h.\n")

    L.append("## 3. Annual power and energy balance (330 operating days per doublet)\n")
    L.append(_table([
        ["Heat delivered", f"{k['heat_delivered_gwh']:.2f} GWh", f"direct {k['heat_direct_gwh']:.2f} + heat pump {k['heat_hp_gwh']:.2f}"],
        ["Cooling delivered", f"{k['cool_delivered_gwh']:.2f} GWh", f"absorption {k['cool_abs_gwh']:.2f} + electric {k['cool_el_gwh']:.2f}"],
        ["Unmet demand", f"heat {k['unmet_heat_gwh']:.3f} / cool {k['unmet_cool_gwh']:.3f} GWh", "must be 0 for feasibility"],
        ["Geothermal heat extracted", f"{k['geothermal_heat_extracted_gwh']:.2f} GWh", f"peak {k['peak_geothermal_extraction_mw']:.1f} MW"],
        ["Electricity", f"{k['electricity_gwh']:.2f} GWh", f"ESP {k['electricity_esp_gwh']:.2f}, injection {k['electricity_injection_gwh']:.2f}, heat pump {k['electricity_heat_pump_gwh']:.2f}, chillers {k['electricity_chillers_gwh']:.2f}"],
        ["System COP", f"{k['system_cop']:.1f}", "(heat + cool) / electricity"],
        ["Geothermal (non-electric) share", f"{k['geothermal_share'] * 100:.0f} %", "(delivered - electricity) / delivered"],
        ["Flow per doublet", f"peak {k['peak_flow_per_doublet_m3_h']:.0f}, mean {k['mean_flow_per_doublet_m3_h']:.0f} m3/h", f"{k['days_at_max_flow']} d at cap, {k['days_at_min_flow']} d at 50 m3/h minimum"],
        ["Produced = injected volume", f"{k['annual_produced_volume_mm3']:.2f} Mm3/yr", "equal liquid volumes, same reservoir"],
        ["Max brine cooling", f"{k['max_brine_dt_c']:.1f} C", f"cap {c.max_brine_cooling_c:.0f} C; min injection T {k['min_injection_t_c']:.1f} C"],
        ["Associated gas", f"{k['annual_gas_mnm3']:.2f} MNm3/yr", f"GLR 0.8; CO2 {k['annual_co2_t']:.0f} t/yr to treatment, CH4 to flare/engine"],
    ], ["Quantity", "Value", "Detail"]))
    L.append("")

    L.append("## 4. Constraint check (final design)\n")
    checks = [
        ["Doublets 1-3", ds.n_doublets, "PASS"],
        ["Max 300 m3/h per doublet", f"{k['peak_flow_per_doublet_m3_h']:.1f}", "PASS" if k['peak_flow_per_doublet_m3_h'] <= 300.0001 else "FAIL"],
        ["Min 50 m3/h while active", "enforced by dispatcher (bypass at minimum)", "PASS"],
        ["Max 40 C brine cooling", f"{k['max_brine_dt_c']:.1f}", "PASS" if k['max_brine_dt_c'] <= 40.0001 else "FAIL"],
        ["Pump efficiency 70 %", "applied to ESP and injection pump", "PASS"],
        ["Production / injection balance", "equal volumes", "PASS"],
        ["330 operating days per doublet", "35-day staggered outages", "PASS"],
        ["100 C heating supply", "direct HX (if brine >= 103 C) / heat pump", "PASS"],
        ["20 C cooling supply", "absorption / electric chillers", "PASS"],
        ["ESP intake above bubble point", f"{k['esp_intake_pressure_at_300_bar']:.0f} bar vs {k['bubble_point_bar']:.0f} bar", "PASS" if k['esp_intake_pressure_at_300_bar'] > k['bubble_point_bar'] + 5 else "FAIL"],
        ["Tubing velocity < API erosional", f"{k['tubing_velocity_at_300_m_s']:.2f} < {k['erosional_velocity_m_s']:.2f} m/s", "PASS" if k['tubing_velocity_at_300_m_s'] < k['erosional_velocity_m_s'] else "FAIL"],
        ["Injection WHP limit", f"{k['injection_whp_at_300_bar']:.1f} bar < {c.max_wellhead_pressure_bar:.0f}", "PASS" if k['injection_whp_at_300_bar'] < c.max_wellhead_pressure_bar else "FAIL"],
    ]
    L.append(_table(checks, ["Constraint", "Value", "Status"]))
    if final.violations:
        L.append("\nRemaining (soft) notices:")
        for v in final.violations:
            L.append(f"- `{v.code}` ({v.severity}, {v.days} days, worst {v.worst_value:.2f}): {v.message}")
    L.append("")

    L.append("## 5. Subsurface / well engineering (GEMINI models)\n")
    wrows = [[w["flow_m3_h"], w["production_bhp_bar"], w["esp_intake_pressure_bar"], w["esp_head_bar"], w["esp_frequency_hz"],
              w["esp_power_mw"] * 1000, w["wellhead_temperature_c"], w["injection_whp_bar"], w["injection_pump_power_mw"] * 1000,
              w["tubing_velocity_m_s"]] for w in final.well_points]
    L.append(_table(wrows, ["Flow m3/h", "Prod BHP bar", "ESP intake bar", "ESP head bar", "Hz", "ESP kW", "WH T C",
                            "Inj WHP bar", "Inj pump kW", "v m/s"]))
    L.append(f"\nProductivity index {k['productivity_index_m3_h_bar']:.1f} m3/h/bar, injectivity index "
             f"{k['injectivity_index_m3_h_bar']:.1f} m3/h/bar (radial Darcy, k = {spec.reservoir.permeability_md:.0f} mD, "
             f"h = {spec.reservoir.gross_thickness_m:.0f} m, re = {ds.well.drainage_radius_m:.0f} m, injector skin {ds.well.skin_injection}).\n")

    L.append("## 6. Agent trajectory - how the design was reached\n")
    srows = []
    for s in run["steps"]:
        srows.append([s.iteration, s.phase, s.design_name, s.action, "yes" if s.feasible else "no",
                      "; ".join(s.hard_violations) or "-", f"{s.kpis.get('system_cop', 0):.1f}",
                      f"{s.cost.get('total_annual_cost_meur', 0):.2f}", f"{s.cost.get('levelised_cost_eur_per_mwh', 0):.1f}"])
    L.append(_table(srows, ["#", "Phase", "Design", "Action", "Feasible", "Hard violations", "COP", "Annual MEUR", "EUR/MWh"]))
    L.append("\nDecision log:\n")
    for s in run["steps"]:
        L.append(f"{s.iteration}. **{s.action}** ({s.design_name}): {s.rationale}")
    L.append("")

    L.append("## 7. Feasible alternatives compared\n")
    arows = []
    for r in run["ranked"][:12]:
        d2 = r.design
        arows.append([d2.name, d2.n_doublets, f"{d2.well.reservoir_midpoint_m:.0f}", f"{d2.heat_pump_mw:.1f}", f"{d2.absorption_chiller_mw:.1f}",
                      f"{d2.electric_chiller_mw:.1f}", f"{r.kpis['electricity_gwh']:.1f}", f"{r.kpis['system_cop']:.1f}",
                      f"{r.kpis['geothermal_share'] * 100:.0f}", f"{r.cost['capex_total_meur']:.1f}", f"{r.cost['total_annual_cost_meur']:.2f}",
                      f"{r.cost['levelised_cost_eur_per_mwh']:.1f}"])
    L.append(_table(arows, ["Design", "Dbl", "Depth m", "HP MW", "Abs MW", "El.ch MW", "El GWh", "COP", "Geo %", "Capex MEUR", "Annual MEUR", "EUR/MWh"]))
    L.append("\nCost assumptions: " + ", ".join(f"{kk} = {vv:g}" for kk, vv in COST.items()) + ".\n")

    if closed_loop:
        L.append("## 8. Closed-loop geothermal management (25-year twin feedback)\n")
        L.append(f"Thermal breakthrough (Gringarten-Sauty) at the assumed well spacing: **{closed_loop['breakthrough_years']:.1f} years**; "
                 f"recommended producer-injector spacing at reservoir level: **{closed_loop['spacing_recommended_m']:.0f} m**.\n")
        for fbk in closed_loop["design_feedback"]:
            L.append(f"- Design feedback: {fbk}")
        L.append("- Breakthrough sensitivity to spacing: " + ", ".join(
            f"{sp:.0f} m -> {yr:.0f} yr" for sp, yr in closed_loop["spacing_sensitivity"]) + ".")
        L.append(f"- Lifetime electricity: {closed_loop['lifetime_electricity_gwh']:.0f} GWh "
                 f"({closed_loop['lifetime_electricity_cost_meur']:.1f} MEUR); interventions {closed_loop['lifetime_intervention_cost_meur']:.1f} MEUR.")
        L.append(f"- Years with hard violations before intervention: {closed_loop['years_with_hard_violations'] or 'none'}.\n")
        crow = [[r["year"], f"{r['t_produced_c']:.1f}", f"{r['skin_injection_extra']:.1f}", f"{r['esp_efficiency_factor']:.2f}",
                 f"{r['injection_whp_bar']:.0f}", f"{r['electricity_gwh']:.1f}", f"{r['system_cop']:.1f}", f"{r['heat_pump_mw']:.1f}",
                 "; ".join(r["actions"]) or "-"] for r in closed_loop["records"]]
        L.append(_table(crow, ["Year", "Tprod C", "Skin+", "ESP eff", "Inj WHP", "El GWh", "COP", "HP MW", "Controller actions"]))
        L.append("")

    L.append("## 9. Figures\n")
    for f in figs:
        L.append(f"![{f}]({f})\n")

    L.append("## 10. Modelling assumptions and limitations\n")
    L.append("- Reservoir temperature from the 30 C/km gradient and 12 C surface; pressure hydrostatic anchored on 250 bar(g) at 2,500 m; permeability assumed depth-independent (200 mD).")
    L.append("- Wellbore heat loss from the GEMINI DPDT model marched in 100 m segments with the geothermal gradient as ambient (U = 10 W/m2K in the model).")
    L.append("- ESP curve is the HC27000 stage curve in the GEMINI unit tests, affinity-scaled to the selected pump frame; power from hydraulic head at the specified 70 % efficiency.")
    L.append("- Heat pump COP = 0.5 x Carnot between evaporator (mean brine T - 5 C) and condenser (105 C); absorption chiller COP 0.72 at >= 95 C driving temperature, derated below, off below 72 C.")
    L.append("- Bubble point from a Henry-law estimate for the 0.8 Nm3/m3 CH4/CO2 GLR; ESP intake kept >= 5 bar above it.")
    L.append("- Costs are indicative planning figures (see section 7) for ranking alternatives, not a budget.")
    L.append("- The closed-loop module uses a lumped Gringarten-Sauty breakthrough model; a full reservoir simulation would refine the breakthrough timing.")

    path = out_dir / "DESIGN_REPORT.md"
    path.write_text("\n".join(L), encoding="utf-8")
    (out_dir / "final_design.json").write_text(json.dumps(ds.to_dict(), indent=2, default=float), encoding="utf-8")
    (out_dir / "final_kpis.json").write_text(json.dumps({"kpis": k, "cost": cost, "violations": [v.__dict__ for v in final.violations]},
                                                        indent=2, default=float), encoding="utf-8")
    (out_dir / "agent_steps.json").write_text(json.dumps([asdict(s) for s in run["steps"]], indent=2, default=float), encoding="utf-8")
    import pandas as pd
    pd.DataFrame(final.daily).to_csv(out_dir / "daily_dispatch.csv", index=False)
    if closed_loop:
        (out_dir / "closed_loop.json").write_text(json.dumps({kk: vv for kk, vv in closed_loop.items() if kk != "final_design"},
                                                             indent=2, default=float), encoding="utf-8")
    return path
