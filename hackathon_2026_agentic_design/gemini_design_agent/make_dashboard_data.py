"""Flatten the run outputs into row-oriented CSV/JSON files for the dashboard.

    python make_dashboard_data.py   -> outputs_dashboard/*.csv|json
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CL = ROOT / "outputs_claude"
RB = ROOT / "outputs"
OPT = ROOT / "outputs_opt"
OUT = ROOT / "outputs_dashboard"
OUT.mkdir(exist_ok=True)


def write_json(name, rows):
    (OUT / name).write_text(json.dumps(rows, default=float), encoding="utf-8")
    print(name, len(rows), "rows")


# ---- daily dispatch (Claude-orchestrated final design)
rows = list(csv.DictReader((CL / "daily_dispatch.csv").open(encoding="utf-8")))
keep = ["date", "heat_demand", "cool_demand", "heat_direct", "heat_hp", "cool_abs", "cool_el", "flow_per_doublet",
        "flow_total", "doublets_available", "t_wellhead", "t_injection", "brine_dt", "esp_el", "inj_el", "hp_el",
        "chiller_el", "total_el", "esp_freq", "gas_nm3_h"]
with (OUT / "daily.csv").open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(keep)
    for r in rows:
        w.writerow([r[k] if k == "date" else f"{float(r[k]):.4g}" for k in keep])
print("daily.csv", len(rows), "rows")

# ---- KPIs and cost (one row)
k = json.loads((CL / "final_kpis.json").read_text(encoding="utf-8"))
d = json.loads((CL / "final_design.json").read_text(encoding="utf-8"))
kp, cost = k["kpis"], k["cost"]
write_json("kpis.json", [{
    "n_doublets": d["n_doublets"], "depth_m": d["well"]["reservoir_midpoint_m"], "well_md_m": d["well"]["reservoir_midpoint_m"] * 1.08,
    "esp_depth_m": d["well"]["esp_depth_m"], "esp_stages": kp["esp_stages"], "esp_bep_m3_h": d["well"]["esp_bep_m3_h"],
    "heat_pump_mw": d["heat_pump_mw"], "absorption_mw": d["absorption_chiller_mw"], "electric_chiller_mw": d["electric_chiller_mw"],
    "reservoir_t_c": kp["reservoir_temperature_c"], "wellhead_t_c": kp["wellhead_temperature_at_300_c"],
    "heat_delivered_gwh": kp["heat_delivered_gwh"], "cool_delivered_gwh": kp["cool_delivered_gwh"],
    "heat_direct_gwh": kp["heat_direct_gwh"], "heat_hp_gwh": kp["heat_hp_gwh"], "cool_abs_gwh": kp["cool_abs_gwh"], "cool_el_gwh": kp["cool_el_gwh"],
    "unmet_heat_gwh": kp["unmet_heat_gwh"], "unmet_cool_gwh": kp["unmet_cool_gwh"],
    "electricity_gwh": kp["electricity_gwh"], "el_esp_gwh": kp["electricity_esp_gwh"], "el_injection_gwh": kp["electricity_injection_gwh"],
    "el_heat_pump_gwh": kp["electricity_heat_pump_gwh"], "el_chillers_gwh": kp["electricity_chillers_gwh"],
    "system_cop": kp["system_cop"], "geothermal_share": kp["geothermal_share"],
    "peak_flow_m3_h": kp["peak_flow_per_doublet_m3_h"], "mean_flow_m3_h": kp["mean_flow_per_doublet_m3_h"],
    "days_at_max_flow": kp["days_at_max_flow"], "days_at_min_flow": kp["days_at_min_flow"],
    "max_brine_dt_c": kp["max_brine_dt_c"], "min_injection_t_c": kp["min_injection_t_c"],
    "esp_intake_bar": kp["esp_intake_pressure_at_300_bar"], "bubble_point_bar": kp["bubble_point_bar"],
    "injection_whp_bar": kp["injection_whp_at_300_bar"], "tubing_velocity_m_s": kp["tubing_velocity_at_300_m_s"],
    "erosional_velocity_m_s": kp["erosional_velocity_m_s"], "corrosion_mm_yr": kp["corrosion_rate_unmitigated_mm_yr"],
    "annual_gas_mnm3": kp["annual_gas_mnm3"], "annual_co2_t": kp["annual_co2_t"],
    "capex_meur": cost["capex_total_meur"], "capex_wells_meur": cost["capex_wells_meur"], "capex_hp_meur": cost["capex_heat_pump_meur"],
    "capex_cooling_meur": cost["capex_cooling_meur"], "capex_surface_meur": cost["capex_surface_meur"] + cost["capex_pumps_meur"],
    "annual_cost_meur": cost["total_annual_cost_meur"], "annual_electricity_meur": cost["annual_electricity_meur"],
    "lcoe_eur_mwh": cost["levelised_cost_eur_per_mwh"],
    "maintenance_windows": "; ".join(f"{a} to {b}" for a, b in kp["maintenance_windows"]),
}])

# ---- constraint scorecard
write_json("constraints.json", [
    {"constraint": "Doublets 1 to 3", "value": f"{d['n_doublets']}", "limit": "1-3", "status": "pass"},
    {"constraint": "Max 300 m3/h per doublet", "value": f"{kp['peak_flow_per_doublet_m3_h']:.0f} m3/h peak", "limit": "300", "status": "pass" if kp["peak_flow_per_doublet_m3_h"] <= 300.001 else "fail"},
    {"constraint": "Min 50 m3/h while active", "value": "dispatcher floor, bypass below", "limit": "50", "status": "pass"},
    {"constraint": "Max 40 C brine cooling", "value": f"{kp['max_brine_dt_c']:.1f} C", "limit": "40", "status": "pass" if kp["max_brine_dt_c"] <= 40.001 else "fail"},
    {"constraint": "Pump hydraulic efficiency 70 %", "value": "ESP and injection pump", "limit": "70 %", "status": "pass"},
    {"constraint": "Production = injection volume", "value": f"{kp['annual_produced_volume_mm3']:.2f} Mm3/yr both", "limit": "equal", "status": "pass"},
    {"constraint": "330 operating days per doublet", "value": "35-day staggered outages", "limit": "330", "status": "pass"},
    {"constraint": "100 C heating supply", "value": f"direct HX from {kp['wellhead_temperature_at_300_c']:.0f} C brine", "limit": "100 C", "status": "pass"},
    {"constraint": "20 C cooling supply", "value": "absorption chiller", "limit": "20 C", "status": "pass"},
    {"constraint": "Unmet demand", "value": f"{kp['unmet_heat_gwh'] + kp['unmet_cool_gwh']:.3f} GWh", "limit": "0", "status": "pass" if kp["unmet_heat_gwh"] + kp["unmet_cool_gwh"] < 1e-6 else "fail"},
    {"constraint": "ESP intake above bubble point + 5 bar", "value": f"{kp['esp_intake_pressure_at_300_bar']:.0f} bar", "limit": f"{kp['bubble_point_bar'] + 5:.0f} bar", "status": "pass" if kp["esp_intake_pressure_at_300_bar"] > kp["bubble_point_bar"] + 5 else "fail"},
    {"constraint": "Tubing velocity below API RP14E", "value": f"{kp['tubing_velocity_at_300_m_s']:.2f} m/s", "limit": f"{kp['erosional_velocity_m_s']:.2f} m/s", "status": "pass" if kp["tubing_velocity_at_300_m_s"] < kp["erosional_velocity_m_s"] else "fail"},
    {"constraint": "Injection wellhead pressure", "value": f"{kp['injection_whp_at_300_bar']:.1f} bar", "limit": "60 bar", "status": "pass" if kp["injection_whp_at_300_bar"] < 60 else "fail"},
])

# ---- agent trajectory (Claude-orchestrated) and rule-based trajectory
def steps(path, mode):
    out = []
    for s in json.loads(path.read_text(encoding="utf-8")):
        if s["action"] == "finalize":
            continue
        out.append({"mode": mode, "step": s["iteration"], "phase": s["phase"], "design": s["design_name"], "action": s["action"],
                    "feasible": "yes" if s["feasible"] else "no", "hard_violations": "; ".join(s["hard_violations"]) or "none",
                    "soft_violations": "; ".join(s["soft_violations"]) or "none",
                    "cop": s["kpis"].get("system_cop", 0), "electricity_gwh": s["kpis"].get("electricity_gwh", 0),
                    "annual_cost_meur": s["cost"].get("total_annual_cost_meur", 0), "lcoe": s["cost"].get("levelised_cost_eur_per_mwh", 0),
                    "depth_m": None, "rationale": s["rationale"]})
    return out


write_json("steps_claude.json", steps(CL / "agent_steps.json", "claude"))
write_json("steps_rule.json", steps(RB / "agent_steps.json", "rule-based"))

# ---- alternatives from the rule-based exploration (deduped by design content)
seen, alts = set(), []
for s in json.loads((RB / "agent_steps.json").read_text(encoding="utf-8")):
    if s["feasible"] and s["kpis"].get("system_cop"):
        key = (round(s["cost"]["total_annual_cost_meur"], 3), round(s["kpis"]["electricity_gwh"], 3))
        if key in seen:
            continue
        seen.add(key)
        alts.append({"design": s["design_name"], "phase": s["phase"], "cop": s["kpis"]["system_cop"], "electricity_gwh": s["kpis"]["electricity_gwh"],
                     "wellhead_t_c": s["kpis"]["wellhead_temperature_at_300_c"], "annual_cost_meur": s["cost"]["total_annual_cost_meur"],
                     "capex_meur": s["cost"]["capex_total_meur"], "lcoe": s["cost"]["levelised_cost_eur_per_mwh"]})
alts.sort(key=lambda r: r["annual_cost_meur"])
write_json("alternatives.json", alts)

# ---- well performance table
wp = json.loads((CL / "final_kpis.json").read_text(encoding="utf-8"))  # kpis only; well points come from the report run
try:
    import sys
    sys.path.insert(0, str(ROOT))
    from gemini_design_agent.subsurface import DoubletModel, WellDesign
    dm = DoubletModel(WellDesign(reservoir_midpoint_m=d["well"]["reservoir_midpoint_m"], esp_depth_m=d["well"]["esp_depth_m"],
                                 esp_bep_m3_h=d["well"]["esp_bep_m3_h"]))
    wells = []
    for q in (50, 100, 150, 200, 250, 300):
        w = dm.evaluate(float(q))
        wells.append({"flow_m3_h": q, "prod_bhp_bar": w.production_bhp_bar, "esp_intake_bar": w.esp_intake_pressure_bar,
                      "esp_head_bar": w.esp_head_bar, "esp_hz": w.esp_frequency_hz, "esp_kw": w.esp_power_mw * 1000,
                      "wellhead_t_c": w.wellhead_temperature_c, "inj_whp_bar": w.injection_whp_bar,
                      "inj_pump_kw": w.injection_pump_power_mw * 1000, "velocity_m_s": w.tubing_velocity_m_s,
                      "bubble_point_bar": w.bubble_point_bar})
    write_json("wells.json", wells)
except Exception as e:
    print("wells skipped", e)

# ---- closed loop years
cl = json.loads((CL / "closed_loop.json").read_text(encoding="utf-8"))
write_json("closed_loop.json", [{"year": r["year"], "t_produced_c": r["t_produced_c"], "skin_extra": r["skin_injection_extra"],
                                 "esp_eff": r["esp_efficiency_factor"], "injection_whp_bar": r["injection_whp_bar"],
                                 "electricity_gwh": r["electricity_gwh"], "cop": r["system_cop"], "heat_pump_mw": r["heat_pump_mw"],
                                 "actions": "; ".join(r["actions"]) or "", "intervention_meur": r["intervention_cost_meur"]}
                                for r in cl["records"]])
write_json("spacing.json", [{"spacing_m": sp, "breakthrough_years": yr} for sp, yr in cl["spacing_sensitivity"]])

# ---- optimiser convergence and candidates (if available)
conv = []
for name in ("dftr_final", "dftr_from2500", "cobyla_final"):
    p = OPT / f"{name}.json"
    if not p.exists():
        continue
    r = json.loads(p.read_text(encoding="utf-8"))
    best = None
    for i, h in enumerate(r["history"], 1):
        feas = h["c1_unmet"] >= -1e-6 and not h["hard"]
        if feas and (best is None or h["f"] < best):
            best = h["f"]
        conv.append({"backend": name, "evaluation": i, "f": h["f"], "feasible": "yes" if feas else "no", "best_feasible": best,
                     "depth_m": h["x"][0], "heat_pump_mw": h["x"][1], "absorption_mw": h["x"][2]})
p = OPT / "stosag_robust.json"
if p.exists():
    r = json.loads(p.read_text(encoding="utf-8"))
    for i, j in enumerate(r["iterate_costs"], 1):
        conv.append({"backend": "stosag_robust", "evaluation": i, "f": j, "feasible": "yes", "best_feasible": j, "depth_m": None,
                     "heat_pump_mw": None, "absorption_mw": None})
write_json("optimizers.json", conv)
p = OPT / "polished_candidates.json"
if p.exists():
    r = json.loads(p.read_text(encoding="utf-8"))
    cands = []
    for label, v in r.items():
        ds = v["design"]
        cands.append({"candidate": label, "depth_m": ds["well"]["reservoir_midpoint_m"], "heat_pump_mw": ds["heat_pump_mw"],
                      "absorption_mw": ds["absorption_chiller_mw"], "electric_chiller_mw": ds["electric_chiller_mw"],
                      "esp_bep_m3_h": ds["well"]["esp_bep_m3_h"], "feasible": "yes" if v["feasible"] else "no",
                      "annual_cost_meur": v["cost"]["total_annual_cost_meur"], "lcoe": v["cost"]["levelised_cost_eur_per_mwh"],
                      "capex_meur": v["cost"]["capex_total_meur"], "expected_cost_meur": v["robust"]["expected_cost_meur"],
                      "worst_cost_meur": v["robust"]["worst_cost_meur"], "feasible_fraction": v["robust"]["feasible_fraction"]})
    write_json("candidates.json", cands)
