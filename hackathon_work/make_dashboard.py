"""Results dashboard: one self-contained, offline HTML file plus 300 dpi panel PNGs.

Reads ONLY existing outputs (run run_candidates.py, design_agent.py and reference_case.py first):
  outputs/candidates/base/<C1..C3>/{daily.csv, summary.json}
  outputs/agent/final_design/{daily.csv, summary.json}, decision_log.jsonl, run_summary.json, designs/
  outputs/reference/summary.json
Writes:
  dashboard/index.html            (ECharts 5.5.1 from dashboard/vendor/ embedded inline, no CDN)
  outputs/figures/pN_<panel>.png  (each panel at 6.5 in x 300 dpi, via headless Edge/Chrome)

Run: $env:PYTHONPATH="src"; py -3.11 -m poetry run python hackathon_work/make_dashboard.py [--no-png]
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs"
DASH = ROOT / "dashboard"
FIGURES = OUT / "figures"
VENDOR_JS = DASH / "vendor" / "echarts.min.js"

DAILY_COLS = [
    "heating_demand_MW", "cooling_demand_MW", "heat_hex_MW", "heat_hp_MW", "heat_chp_MW",
    "heat_boiler_produced_gas_MW", "heat_boiler_external_gas_MW", "heat_unmet_MW", "heat_delivered_MW",
    "cool_absorption_MW", "cool_electric_MW", "cool_unmet_MW", "flow_per_doublet_m3h", "n_active", "brine_dT_K",
    "T_wellhead_C", "T_absorber_in_C", "T_hex_in_C", "T_injection_C", "T_after_hex_C", "T_after_hp_C", "T_supply_C",
    "hp_COP", "absorber_drive_MW",
]

# Export size per panel in CSS px; 960 px x 2.03125 = 1950 px = 6.5 in at 300 dpi.
PANELS = [("p1", "kpis", 330), ("p2", "heating", 520), ("p3", "cooling", 460), ("p4", "brine", 600),
          ("p5", "agent_path", 560), ("p6", "emissions", 460), ("p7", "schematic", 560),
          ("p8", "constraints", 640), ("p9", "judges_tests", 600),
          ("p10", "sensitivity_tornado", 600), ("p11", "resilience_gas", 560),
          ("p12", "energy_sankey", 600), ("p13", "monthly_supply", 600), ("p14", "agent_replay", 700), ("p15", "why_this_design", 520)]
EXPORT_WIDTH_PX, EXPORT_INCH, DPI = 960, 6.5, 300


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def num(x: str):
    if x in ("", "None", None):
        return None
    if x in ("True", "False"):
        return x == "True"
    return round(float(x), 4)


def read_daily(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    cols = {k: [num(r[k]) for r in rows] for k in DAILY_COLS}
    cols["date"] = [r["date"] for r in rows]
    cols["maintenance"] = [r["maintenance"] for r in rows]
    cols["active_doublets"] = [r["active_doublets"] for r in rows]
    return cols


def constraints(s: dict, d: dict) -> list[dict]:
    on = [i for i, n in enumerate(d["n_active"]) if n]
    flows = [d["flow_per_doublet_m3h"][i] for i in on]
    checks = {}
    for c in s["annual_checks"]:
        checks.setdefault(c["check"], []).append(c)
    t_min = min(d["T_supply_C"][i] for i in range(len(d["date"])) if d["heating_demand_MW"][i] > 0)

    def status(ok):
        return "PASS" if ok else "FAIL"

    def from_checks(name):
        return status(all(c["status"] == "PASS" for c in checks.get(name, [])) and name in checks)

    op_days = [c["value"] for c in checks.get("330_day_rule", [])]
    unmet_days = sum(1 for i in range(len(d["date"])) if d["heat_unmet_MW"][i] > 1e-3 or d["cool_unmet_MW"][i] > 1e-3)
    return [
        {"name": "Flow per doublet when on", "limit": "50 – 300 m³/h", "worst": f"{min(flows):.0f} – {max(flows):.0f} m³/h",
         "status": status(min(flows) >= 50 - 0.01 and max(flows) <= 300 + 0.01)},
        {"name": "Brine ΔT", "limit": "≤ 40 K", "worst": f"max {s['max_brine_dT_K']:.3f} K", "status": status(s["max_brine_dT_K"] <= 40.001)},
        {"name": "Heating supply 100 °C, every day", "limit": "unmet 0", "worst": f"min supply {t_min:.2f} °C; unmet {s['heat_unmet_GWh']:.3f} GWh",
         "status": status(s["heat_unmet_GWh"] <= 1e-3 and t_min >= 99.5)},
        {"name": "Cooling supply 20 °C, every day", "limit": "unmet 0", "worst": f"unmet {s['cool_unmet_GWh']:.3f} GWh",
         "status": status(s["cool_unmet_GWh"] <= 1e-3)},
        {"name": "Pump hydraulic efficiency", "limit": "70 %", "worst": "P = Q·Δp / 0.70 for ESP and injector pump (by construction)", "status": "PASS"},
        {"name": "330 operating days per doublet", "limit": "≤ 330 d, 35-day maintenance", "worst": f"max {max(op_days):.0f} d" if op_days else "-",
         "status": from_checks("330_day_rule")},
        # organizer clarification (Discord, 2026-11-01): the full system must meet demand on all 365 days; days with
        # every doublet off are allowed (design attribute, see no_geothermal_days). Older outputs lack the check.
        {"name": "Demand met all 365 days (full system)", "limit": "0 days unmet", "worst": f"{unmet_days} days",
         "status": from_checks("demand_met_365") if "demand_met_365" in checks else status(unmet_days == 0)},
        {"name": "Daily constraint checker", "limit": "0 failing days", "worst": f"{s['days_failing_daily_checks']} days", "status": from_checks("daily_constraints")},
        {"name": "ESP intake at max flow", "limit": "≥ 30 bar", "worst": f"{checks['esp_intake_pressure'][0]['value']:.2f} bar (ESP at {s['esp_setting_depth_m']:g} m)",
         "status": from_checks("esp_intake_pressure")},
        {"name": "Tubing velocity at max flow", "limit": "≤ 4 m/s", "worst": f"{checks['tubing_velocity'][0]['value']:.2f} m/s",
         "status": from_checks("tubing_velocity")},
    ] + ([{"name": "Reinjected gas dissolves", "limit": "margin ≥ 1 at reservoir; dip tube above reservoir",
           "worst": f"margin {gd['points']['wellhead@reservoir']['margin']:.1f} at the injector wellhead, "
                    f"{gd['points']['reservoir@reservoir']['margin']:.0f} at the reservoir",
           "status": from_checks("gas_dissolution")}] if (gd := s.get("gas_dissolution")) else [])


def design_point(d: dict, rho: float, cp: float, t_return: float) -> dict:
    """Schematic values: heat path on the peak-heating day, absorber on the peak-cooling day."""
    i = max(range(len(d["date"])), key=lambda k: d["heating_demand_MW"][k])
    j = max(range(len(d["date"])), key=lambda k: d["cooling_demand_MW"][k])
    v = {k: d[k][i] for k in DAILY_COLS}
    v["date"] = d["date"][i]
    v["heat_boiler_MW"] = v["heat_boiler_produced_gas_MW"] + v["heat_boiler_external_gas_MW"]
    v["district_flow_m3h"] = v["heat_delivered_MW"] * 1e6 / (rho * cp * (v["T_supply_C"] - t_return)) * 3600
    v["T_return_C"] = t_return
    v["cool_date"] = d["date"][j]
    for k in ("cooling_demand_MW", "cool_absorption_MW", "cool_electric_MW", "absorber_drive_MW", "T_absorber_in_C", "T_hex_in_C"):
        v[f"cool_{k}"] = d[k][j]
    return v


def agent_data() -> dict:
    entries = [json.loads(line) for line in (OUT / "agent" / "decision_log.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    b = [e for e in entries if e["scenario"] == "B_design"]
    verdicts = next(e["data"] for e in reversed(b) if e["phase"] == "rank")
    evaluations = []
    for e in (x for x in b if x["phase"] == "evaluate"):
        name = e["title"].split(": ", 1)[1]
        v, m = verdicts[name], e["data"]["metrics"]
        status = "failed" if not e["data"]["feasible"] else "accepted" if v["status"] == "ACCEPTED" else "marginal" if v.get("marginal") else "rejected"
        evaluations.append({"n": e["data"]["evaluation"], "id": name, "status": status, "reason": v["reason"], "emissions_t": m["emissions_t"],
                            "external_gas_GWh": m["external_gas_fuel_GWh"], "grid_import_GWh": m["grid_import_GWh"], "drilled_m": m["drilled_m"],
                            "T_res_C": m["reservoir_temperature_C"], "failing": e["data"]["failing"],
                            "depth_m": int(name.split("_z")[1].split("_")[0])})
    steps = [e["data"] for e in b if e["phase"] == "depth_step"]
    summary = load_json(OUT / "agent" / "run_summary.json")
    return {"evaluations": evaluations, "depth_steps": steps, "judges_tests": summary["judges_tests"],
            "gas_handling": summary.get("gas_handling"),
            "timing": summary["timing"], "pick": summary["pick"], "marginal_cases": summary.get("marginal_cases", []),
            "replay": agent_replay(b), "chat": agent_chat()}


def energy_flows(folder: Path, gas: str, rho: float, cp: float, x_co2: float) -> dict:
    """Annual energy balance (GWh) for the Sankey, from the full daily.csv. Brine heat = n * q * rho * cp * dT
    (producer wellhead -> injector wellhead); what the HEX, absorber and heat-pump source do not take is the
    surface-equipment temperature drop (separator, filters), shown as a loss."""
    with (folder / "daily.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    g = lambda k: sum(float(r[k] or 0) for r in rows) * 24 / 1000  # MW-days -> GWh
    brine = sum(float(r["n_active"]) * float(r["flow_per_doublet_m3h"]) / 3600 * rho * cp * float(r["brine_dT_K"] or 0)
                for r in rows) * 24 / 1e9
    hex_, hp, chp_h, hp_el = g("heat_hex_MW"), g("heat_hp_MW"), g("heat_chp_MW"), g("el_hp_MW")
    blr_pg, blr_xg = g("heat_boiler_produced_gas_MW"), g("heat_boiler_external_gas_MW")
    absorb, ab_cool, el_cool, ch_el = g("absorber_drive_MW"), g("cool_absorption_MW"), g("cool_electric_MW"), g("el_chiller_MW")
    pg_chp, pg_blr, pg_flare, xg = g("produced_gas_chp_MW"), g("produced_gas_boiler_MW"), g("produced_gas_flared_MW"), g("external_gas_fuel_MW")
    chp_el, imp, exp_ = g("el_chp_MW"), g("el_grid_import_MW"), g("el_grid_export_MW")
    pumps, gas_el = g("el_esp_MW") + g("el_injector_MW"), g("el_gas_handling_MW")
    co2_t = sum(float(r["produced_gas_Nm3_day"] or 0) for r in rows) * x_co2 * 1.9635 / 1000 if gas == "co2_reinject" else 0.0
    links = [
        ("Reservoir heat (brine)", "HEX", hex_), ("Reservoir heat (brine)", "Absorption chiller", absorb),
        ("Reservoir heat (brine)", "Heat pump", hp - hp_el), ("Reservoir heat (brine)", "Losses", max(0.0, brine - hex_ - absorb - (hp - hp_el))),
        ("Produced gas (CH₄)" if gas == "co2_reinject" else "Produced gas", "CHP", pg_chp),
        ("Produced gas (CH₄)" if gas == "co2_reinject" else "Produced gas", "Boiler", pg_blr),
        ("Produced gas (CH₄)" if gas == "co2_reinject" else "Produced gas", "Losses", pg_flare),
        ("External gas", "Boiler", xg),
        ("Grid electricity", "Electricity", imp), ("CHP", "Electricity", chp_el),
        ("Electricity", "Heat pump", hp_el), ("Electricity", "Electric chiller", ch_el),
        ("Electricity", "Injection & pumping", pumps), ("Electricity", "CO₂ to reinjection", gas_el), ("Electricity", "Grid export", exp_),
        ("CO₂ to reinjection", "Injection & pumping", gas_el),
        ("HEX", "District heating", hex_), ("Heat pump", "District heating", hp), ("CHP", "District heating", chp_h),
        ("CHP", "Losses", max(0.0, pg_chp - chp_h - chp_el)),
        ("Boiler", "District heating", blr_pg + blr_xg), ("Boiler", "Losses", max(0.0, pg_blr + xg - blr_pg - blr_xg)),
        ("Absorption chiller", "District cooling", ab_cool), ("Absorption chiller", "Losses", max(0.0, absorb - ab_cool)),
        ("Electric chiller", "District cooling", el_cool),
    ]
    links = [{"source": a, "target": b, "value": round(v, 4)} for a, b, v in links if v > 5e-4]
    names = list(dict.fromkeys(n for l in links for n in (l["source"], l["target"])))
    return {"nodes": names, "links": links, "brine_GWh": brine, "co2_reinjected_t": co2_t, "flared_GWh": pg_flare}


def monthly(folder: Path) -> dict:
    """Monthly heating and cooling supply by source (GWh)."""
    keys = {"HEX (direct)": "heat_hex_MW", "Heat pump": "heat_hp_MW", "CHP (produced gas)": "heat_chp_MW",
            "Boiler (produced gas)": "heat_boiler_produced_gas_MW", "Boiler (external gas)": "heat_boiler_external_gas_MW",
            "Absorption chiller": "cool_absorption_MW", "Electric chiller": "cool_electric_MW",
            "Heating demand": "heating_demand_MW", "Cooling demand": "cooling_demand_MW"}
    out = {k: [0.0] * 12 for k in keys}
    with (folder / "daily.csv").open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            m = int(r["date"][5:7]) - 1
            for k, col in keys.items():
                out[k][m] += float(r[col] or 0) * 24 / 1000
    return {k: [round(v, 4) for v in vals] for k, vals in out.items()}


def agent_replay(b: list[dict]) -> list[dict]:
    """One step per proposal: why it was proposed, pre-checks, the annual result and the ranking after it."""
    steps, cur = [], None
    for e in b:
        ph, why = e["phase"], (e.get("rationale") or "").strip()
        if ph == "propose":
            cur = {"proposed": e["title"].replace("Proposal ", ""), "why": why, "checks": [], "result": None, "verdict": None, "depth": None}
            steps.append(cur)
        elif cur is None:
            continue
        elif ph in ("validate", "revise"):
            cur["checks"].append(f"{e['title']}: {why}")
        elif ph == "well_check":
            cur["checks"].append(f"{e['title']}: {why}")
        elif ph == "evaluate":
            cur["candidate"], cur["result"] = e["title"].split(": ", 1)[1], why
            m = e["data"]["metrics"]
            cur.update(emissions_t=m["emissions_t"], external_gas_GWh=m["external_gas_fuel_GWh"], feasible=e["data"]["feasible"], n=e["data"]["evaluation"])
        elif ph == "rank":
            cur["verdict"] = why
        elif ph == "depth_step":
            cur["depth"] = why
    return [s for s in steps if s.get("candidate")]


def agent_chat() -> list[dict]:
    """Human-in-the-loop transcript of the interactive run (AGENT ASKED / USER ANSWERED)."""
    path = OUT / "agent" / "interactive" / "decision_log.jsonl"
    if not path.exists():
        return []
    chat = []
    for e in (json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()):
        if e["phase"] == "required_inputs":
            chat.append({"who": "agent", "tag": "AGENT", "text": e["rationale"]})
        elif e["phase"] == "ask":
            chat.append({"who": "agent", "tag": "AGENT ASKED", "text": e["rationale"]})
        elif e["phase"] == "answer":
            chat.append({"who": "user", "tag": "USER ANSWERED", "text": e["data"].get("raw", ""), "note": e["rationale"]})
        elif e["phase"] == "final":
            chat.append({"who": "agent", "tag": "AGENT (result)", "text": "Selected " + e["rationale"].split(". Versus")[0].split("Selected ", 1)[-1]})
    return chat


def thousands(x: float) -> str:
    return f"{x:,.0f}".replace(",", " ")


def why_this_design(summary: dict, evaluations: list[dict], steps: list[dict], designs: dict, ref: dict) -> list[dict]:
    """4-5 reasons for the pick, each taken from the agent's log (verdicts, depth steps, gas decision)."""
    pick = next(e for e in evaluations if e["status"] == "accepted")
    fin = designs["FINAL"]
    n_pass = sum(1 for c in fin["constraints"] if c["status"] == "PASS")
    reasons = [{"title": "Meets every hard constraint, every day",
                "text": f"{n_pass} / {len(fin['constraints'])} checks pass over 365 days: flow 50–300 m³/h, brine ΔT ≤ 40 K, 100 °C heating and "
                        f"20 °C cooling with zero unmet demand, the 330-day rule, ESP intake, tubing velocity and gas dissolution."}]
    reasons.append({"title": "Almost no external gas (ranked first)",
                    "text": f"{pick['external_gas_GWh']:.3f} GWh/yr vs {ref['gas_fuel_GWh']:.1f} GWh for the gas-boiler reference; "
                            f"emissions {thousands(pick['emissions_t'])} t/yr, {100 * (1 - pick['emissions_t'] / ref['emissions_t']):.1f} % lower."})
    by_id = {e["id"]: e for e in evaluations}
    n1 = [e for e in evaluations if e["id"].startswith("n1_")]
    n3 = [e for e in evaluations if e["id"].startswith("n3_")]
    if n1 or n3:
        parts = []
        if n1:
            worst = next((e for e in n1 if e["depth_m"] == pick["depth_m"]), n1[-1])
            parts.append(f"one doublet at {thousands(worst['depth_m'])} m still needs {worst['external_gas_GWh']:.1f} GWh of external gas (35 maintenance days on backup)")
        if n3:
            e3 = n3[0]
            parts.append(f"a third doublet cuts emissions only {100 * (1 - e3['emissions_t'] / pick['emissions_t']):.1f} % (the rule needs ≥ 5 %)")
        t = "; ".join(parts)
        reasons.append({"title": "Two doublets is the right count", "text": t[0].upper() + t[1:] + "."})
    kept = [st for st in steps if st["accepted"]]
    rej = [st for st in steps if not st["accepted"] and st["from_m"] == pick["depth_m"]]
    if kept:
        last = kept[-1]
        t = f"Each 250 m step was kept only if emissions fell ≥ 5 %: {thousands(last['from_m'])} → {thousands(last['to_m'])} m saved {abs(last['emissions_change']) * 100:.1f} %"
        if rej:
            t += f"; {thousands(rej[-1]['from_m'])} → {thousands(rej[-1]['to_m'])} m saves only {abs(rej[-1]['emissions_change']) * 100:.1f} %, so the ladder stops"
        reasons.append({"title": f"Depth {thousands(pick['depth_m'])} m from the parsimony ladder", "text": t + "."})
    g = summary.get("gas_handling") or {}
    opts = {o["gas_handling"]: o for o in g.get("options", [])}
    if g.get("chosen") == "co2_reinject" and "chp" in opts:
        t = f"Reinjecting the 20 mol% CO₂ and burning only CH₄ saves {thousands(opts['chp']['emissions_t'] - opts['co2_reinject']['emissions_t'])} t/yr vs CHP on all gas"
        d = opts["co2_reinject"].get("dissolution")
        if d:
            t += f"; the CO₂ dissolves with margin {d['wellhead_margin']:.1f} at the injector wellhead"
        if "reinject_all" in opts:
            t += f". Reinjecting all gas needs {opts['reinject_all']['external_gas_GWh']:.3f} GWh of external gas, so it ranks lower"
        reasons.append({"title": "CO₂ reinjected, CH₄ to CHP", "text": t + "."})
    return reasons[:5]


def collect() -> dict:
    ref = load_json(OUT / "reference" / "summary.json")
    design_files = sorted((OUT / "agent" / "designs").glob("*_brine_chain.json"))
    chain = load_json(design_files[0])
    hexp = chain["components"]["heat_exchanger"]["parameters"]
    t_return = next(bi["value"] for bi in chain["boundary_inputs"]
                    if bi["component"] == "heat_exchanger" and bi["key"] == "secondary_temperature_in")
    folders = [(p.name.split("_")[0], p) for p in sorted((OUT / "candidates" / "base").iterdir()) if p.is_dir() and p.name[:1] == "C"]
    folders.append(("FINAL", OUT / "agent" / "final_design"))
    challenge = load_json(ROOT / "inputs" / "challenge_inputs.json")
    rho_b, cp_b = challenge["fluid"]["density_kg_m3"], challenge["illustrative_assumptions_not_fixed_by_challenge"]["brine_cp_J_per_kg_K"]
    x_co2 = challenge["fluid"]["gas_carbon_dioxide_mol_percent"] / 100
    designs = {}
    for label, folder in folders:
        s = load_json(folder / "summary.json")
        d = read_daily(folder / "daily.csv")
        designs[label] = {"label": "Final design" if label == "FINAL" else label, "name": s["candidate"]["name"], "summary": s, "daily": d,
                          "constraints": constraints(s, d), "no_geothermal_days": sum(1 for a in d["active_doublets"] if not a),
                          "point": design_point(d, hexp["fluid_density"], hexp["specific_heat"], t_return),
                          "sankey": energy_flows(folder, s.get("gas_handling", "chp"), rho_b, cp_b, x_co2), "monthly": monthly(folder)}
    sens_path = OUT / "sensitivity" / "summary.json"
    agent = agent_data()
    agent["why"] = why_this_design(load_json(OUT / "agent" / "run_summary.json"), agent["evaluations"], agent["depth_steps"], designs, ref)
    return {"designs": designs, "order": [label for label, _ in folders], "reference": ref, "agent": agent,
            "sensitivity": load_json(sens_path) if sens_path.exists() else None,
            "sources": {"candidates": "outputs/candidates/base/", "final": "outputs/agent/final_design/", "reference": "outputs/reference/summary.json",
                        "agent": "outputs/agent/{decision_log.jsonl, run_summary.json}"}}


HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GEMINI 2027 Results</title>
<style>
:root {
  --page: #f9f9f7; --surface: #fcfcfb; --ink: #0b0b0b; --ink-2: #52514e; --muted: #898781;
  --grid: #e1e0d9; --axis: #c3c2b7; --border: rgba(11,11,11,0.10);
  --s1: #2a78d6; --s2: #eb6834; --s3: #1baf7a; --s4: #eda100;
  /* one colour per energy source, used by every chart (validated: all pairs pass CVD + normal-vision checks) */
  --geo: #2a78d6; --hp: #c2389a; --pgas: #119a6c; --pgas-2: #79c9a6; --xgas: #e0650c; --elec: #7d5a00;
  --dh: #a3243b; --dc: #4fa3dd; --loss: #b5b2a8; --inj: #5e6873;
  --good: #0ca30c; --good-text: #006300; --warning: #fab219; --critical: #d03b3b;
  --font: system-ui, -apple-system, "Segoe UI", sans-serif;
}
* { box-sizing: border-box; }
html, body { margin: 0; background: var(--page); color: var(--ink); font-family: var(--font); }
header { display: flex; flex-wrap: wrap; align-items: center; gap: 12px 32px; padding: 20px 28px 8px; }
h1 { font-size: 28px; margin: 0; font-weight: 650; }
.subtitle { color: var(--ink-2); font-size: 16px; margin: 4px 0 0; }
.selector { display: flex; gap: 0; border: 1px solid var(--axis); border-radius: 8px; overflow: hidden; margin-left: auto; }
.selector button { font: 600 16px var(--font); padding: 10px 18px; border: 0; background: var(--surface); color: var(--ink-2); cursor: pointer; border-left: 1px solid var(--axis); }
.selector button:first-child { border-left: 0; }
.selector button[aria-pressed="true"] { background: var(--ink); color: #fff; }
.verdict { width: 100%; color: var(--ink-2); font-size: 15px; margin: 0; }
main { display: grid; grid-template-columns: repeat(12, 1fr); gap: 16px; padding: 12px 28px 28px; }
.panel { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 16px 18px; display: flex; flex-direction: column; min-width: 0; }
.panel h2 { font-size: 19px; margin: 0; font-weight: 650; }
.panel .sub { color: var(--ink-2); font-size: 15px; margin: 4px 0 8px; }
.panel .note { color: var(--ink-2); font-size: 14px; margin: 6px 0 0; }
.panel .story { color: var(--ink); font-size: 15px; margin: 2px 0 0; font-weight: 500; }
.panel .story::before { content: "▸ "; color: var(--muted); }
.replay { display: grid; grid-template-columns: 5fr 4fr 3fr; gap: 16px; flex: 1; min-height: 0; }
.rp-left { display: flex; flex-direction: column; min-width: 0; }
.rp-controls { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.rp-controls button { font: 600 15px var(--font); padding: 6px 12px; border: 1px solid var(--axis); border-radius: 6px; background: var(--surface); color: var(--ink); cursor: pointer; min-width: 44px; }
.rp-controls button.primary { background: var(--ink); color: #fff; border-color: var(--ink); }
.rp-controls .stepno { color: var(--ink-2); font-size: 15px; margin-left: 6px; font-variant-numeric: tabular-nums; }
.rp-card { border: 1px solid var(--border); border-radius: 8px; padding: 12px 14px; background: var(--page); font-size: 14px; line-height: 1.45; overflow: auto; max-height: 560px; }
.rp-card h3 { margin: 0 0 6px; font-size: 16px; }
.rp-card .lab { color: var(--ink-2); font-weight: 650; font-size: 13px; text-transform: uppercase; letter-spacing: 0.03em; margin-top: 8px; }
.rp-card .verdict-in { color: var(--good-text); font-weight: 650; }
.chat { display: flex; flex-direction: column; gap: 10px; overflow: auto; max-height: 600px; }
.chat .hdr { color: var(--ink-2); font-size: 13px; }
.bubble { max-width: 92%; padding: 9px 12px; border-radius: 12px; font-size: 14px; line-height: 1.4; }
.bubble .tag { display: block; font-size: 12px; font-weight: 700; letter-spacing: 0.04em; margin-bottom: 3px; }
.bubble.agent { align-self: flex-start; background: var(--page); border: 1px solid var(--border); border-bottom-left-radius: 3px; }
.bubble.agent .tag { color: var(--geo); }
.bubble.user { align-self: flex-end; background: var(--ink); color: #fff; border-bottom-right-radius: 3px; }
.bubble.user .tag { color: #d9d8d2; }
.why { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-top: 8px; }
.why .card { border: 1px solid var(--border); border-left: 4px solid var(--good); border-radius: 8px; padding: 12px 14px; background: var(--page); }
.why .card .n { color: var(--good-text); font-weight: 700; font-size: 13px; }
.why .card h3 { margin: 2px 0 6px; font-size: 16px; }
.why .card p { margin: 0; font-size: 14px; line-height: 1.45; color: var(--ink-2); }
.span-12 { grid-column: span 12; } .span-6 { grid-column: span 6; } .span-7 { grid-column: span 7; } .span-5 { grid-column: span 5; }
.span-8 { grid-column: span 8; } .span-4 { grid-column: span 4; }
.chart { flex: 1; min-height: 380px; width: 100%; }
.chart.tall { min-height: 560px; }
.kpis { display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px; }
.tile { border: 1px solid var(--border); border-radius: 8px; padding: 12px 14px; background: var(--page); }
.tile .k { color: var(--ink-2); font-size: 14px; }
.tile .v { font-size: 30px; font-weight: 650; margin-top: 4px; white-space: nowrap; }
.tile .d { color: var(--ink-2); font-size: 14px; margin-top: 4px; }
.tile .d.good { color: var(--good-text); font-weight: 600; }
table { border-collapse: collapse; width: 100%; font-size: 15px; }
th, td { text-align: left; padding: 7px 8px; border-bottom: 1px solid var(--grid); vertical-align: top; }
th { color: var(--ink-2); font-weight: 600; font-size: 14px; }
td.num { font-variant-numeric: tabular-nums; }
.small { color: var(--ink-2); font-size: 13px; }
.panel h3 { font-size: 16px; margin: 18px 0 6px; }
.badge { display: inline-flex; align-items: center; gap: 6px; font-weight: 700; font-size: 14px; white-space: nowrap; }
.badge .dot { width: 18px; height: 18px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; color: #fff; font-size: 12px; }
.badge.pass { color: var(--good-text); } .badge.pass .dot { background: var(--good); }
.badge.fail { color: var(--critical); } .badge.fail .dot { background: var(--critical); }
.tests { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 12px; }
.tests li { display: grid; grid-template-columns: auto 1fr; gap: 4px 12px; font-size: 15px; }
.tests .t { font-weight: 650; }
.tests .e { grid-column: 2; color: var(--ink-2); font-size: 14px; font-family: ui-monospace, Consolas, monospace; line-height: 1.4; }
svg text { font-family: var(--font); }
.schem { flex: 1; width: 100%; min-height: 380px; }
@media (max-width: 1200px) { main > .panel { grid-column: span 12; } .kpis { grid-template-columns: repeat(3, 1fr); }
  .replay { grid-template-columns: 1fr; } .why { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 700px) { header, main { padding-left: 16px; padding-right: 16px; } .kpis { grid-template-columns: repeat(2, 1fr); } .selector { margin-left: 0; } }
body.export header { display: none; }
body.export main { display: block; padding: 0; }
body.export .panel { display: none; }
body.export .panel.target { display: flex; width: 100vw; height: 100vh; border: 0; border-radius: 0; }
body.export .chart, body.export .schem { min-height: 0; }
body.export .kpis { grid-template-columns: repeat(3, 1fr); }
body.export .replay { grid-template-columns: 1fr 1fr; } body.export .chat { display: none; }
body.export .why { grid-template-columns: repeat(2, 1fr); } body.export .rp-controls button { display: none; }
</style>
</head>
<body>
<header>
  <div>
    <h1>GEMINI 2027 geothermal heating &amp; cooling — results</h1>
    <p class="subtitle">365-day model (GEMINI brine chain + setpoint plant model) · agent-selected design vs candidates C1–C3 · SI units</p>
  </div>
  <div class="selector" role="group" aria-label="Design" id="selector"></div>
  <p class="verdict" id="verdict"></p>
</header>
<main>
  <section class="panel span-12" id="p1"><h2 id="p1-title">Final design — key results</h2><p class="story" id="p1-story"></p><p class="sub" id="p1-sub"></p><div class="kpis" id="kpis"></div></section>
  <section class="panel span-8" id="p12"><h2>Annual energy flows</h2><p class="story" id="p12-story"></p><p class="sub" id="p12-sub"></p><div class="chart" id="c-sankey"></div></section>
  <section class="panel span-4" id="p6"><h2>CO₂ emissions vs conventional reference</h2><p class="story" id="p6-story"></p><p class="sub" id="p6-sub"></p><div class="chart" id="c-em"></div></section>
  <section class="panel span-7" id="p2"><h2>Heating supply by source</h2><p class="story" id="p2-story"></p><p class="sub" id="p2-sub"></p><div class="chart" id="c-heat"></div></section>
  <section class="panel span-5" id="p3"><h2>Cooling supply by source</h2><p class="story" id="p3-story"></p><p class="sub" id="p3-sub"></p><div class="chart" id="c-cool"></div></section>
  <section class="panel span-12" id="p13"><h2>Monthly supply by source</h2><p class="story" id="p13-story"></p><p class="sub" id="p13-sub"></p><div class="chart tall" id="c-monthly"></div></section>
  <section class="panel span-5" id="p4"><h2>Brine: flow per doublet and ΔT</h2><p class="story" id="p4-story"></p><p class="sub" id="p4-sub"></p><div class="chart" id="c-brine"></div></section>
  <section class="panel span-7" id="p7"><h2>System schematic at the design point</h2><p class="story" id="p7-story"></p><p class="sub" id="p7-sub"></p><div class="schem" id="schem"></div></section>
  <section class="panel span-12" id="p14"><h2>Agent replay: how the design was found</h2><p class="story" id="p14-story"></p><p class="sub" id="p14-sub"></p>
    <div class="replay">
      <div class="rp-left">
        <div class="rp-controls" role="group" aria-label="Replay controls">
          <button type="button" id="rp-first" aria-label="First step">⏮</button><button type="button" id="rp-prev" aria-label="Previous step">◀</button>
          <button type="button" id="rp-play" class="primary" aria-label="Play">▶ Play</button><button type="button" id="rp-next" aria-label="Next step">▶|</button>
          <span class="stepno" id="rp-stepno"></span>
        </div>
        <div class="chart" id="c-replay"></div>
      </div>
      <div class="rp-card" id="rp-card" aria-live="polite"></div>
      <div class="chat" id="chat"></div>
    </div></section>
  <section class="panel span-7" id="p5"><h2>Agent path: every annual evaluation and the depth ladder</h2><p class="story" id="p5-story"></p><p class="sub" id="p5-sub"></p><div class="chart" id="c-agent"></div></section>
  <section class="panel span-5" id="p9"><h2>Judges' agent-reasoning tests</h2><p class="story" id="p9-story"></p><p class="sub" id="p9-sub"></p><ul class="tests" id="tests"></ul>
    <p class="note" id="p9-note"></p></section>
  <section class="panel span-6" id="p8"><h2>Hard-constraint checklist</h2><p class="story" id="p8-story"></p><p class="sub" id="p8-sub"></p><div id="checks"></div></section>
  <section class="panel span-6" id="p11"><h2>N-1 resilience and gas handling</h2><p class="story" id="p11-story"></p><p class="sub" id="p11-sub"></p><div id="resilience"></div></section>
  <section class="panel span-12" id="p10"><h2>Sensitivity of the final design (one input at a time)</h2><p class="story" id="p10-story"></p><p class="sub" id="p10-sub"></p><div class="chart" id="c-tornado"></div>
    <p class="note" id="p10-note"></p></section>
  <section class="panel span-12" id="p15"><h2>Why this design</h2><p class="story" id="p15-story"></p><div class="why" id="why"></div></section>
</main>
<script>__ECHARTS__</script>
<script id="data" type="application/json">__DATA__</script>
<script>
"use strict";
const D = JSON.parse(document.getElementById("data").textContent);
const V = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const C = { s1: V("--s1"), s2: V("--s2"), s3: V("--s3"), s4: V("--s4"), ink: V("--ink"), ink2: V("--ink-2"), muted: V("--muted"),
            geo: V("--geo"), hp: V("--hp"), pgas: V("--pgas"), pgas2: V("--pgas-2"), xgas: V("--xgas"), elec: V("--elec"),
            dh: V("--dh"), dc: V("--dc"), loss: V("--loss"), inj: V("--inj"),
            grid: V("--grid"), axis: V("--axis"), surface: V("--surface"), good: V("--good"), warning: V("--warning"), critical: V("--critical") };
const FONT = V("--font");
const hp = new URLSearchParams(location.hash.slice(1));
const EXPORT = hp.get("export");
let current = hp.get("design") || "FINAL";
if (EXPORT) { document.body.classList.add("export"); document.getElementById(EXPORT).classList.add("target"); }

const fmt = (x, d = 0) => x == null ? "–" : Number(x).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }).replace(/,/g, "\u202f");
const pct = x => (x > 0 ? "+" : x < 0 ? "−" : "") + fmt(Math.abs(x) * 100, 1) + " %";
const charts = {};
function chart(id) {
  if (!charts[id]) charts[id] = echarts.init(document.getElementById(id), null, { renderer: "canvas" });
  return charts[id];
}
window.addEventListener("resize", () => Object.values(charts).forEach(c => c.resize()));

const AXIS = { axisLine: { lineStyle: { color: C.axis } }, axisTick: { show: false }, axisLabel: { color: C.ink2, fontSize: 13 },
               splitLine: { lineStyle: { color: C.grid } }, nameTextStyle: { color: C.ink2, fontSize: 13 } };
const TIP = { backgroundColor: C.surface, borderColor: C.axis, textStyle: { color: C.ink, fontSize: 13, fontFamily: FONT }, confine: true };
const LEGEND = { top: 0, left: 0, itemWidth: 14, itemHeight: 10, textStyle: { color: C.ink2, fontSize: 13 } };
const base = () => ({ animation: !EXPORT, textStyle: { fontFamily: FONT }, tooltip: TIP, legend: LEGEND });
const timeAxis = (extra = {}) => Object.assign({ type: "time", ...AXIS, splitLine: { show: false },
  axisLabel: { color: C.ink2, fontSize: 13, formatter: "{MMM}" }, min: "2027-01-01", max: "2027-12-31" }, extra);
const valueAxis = (name, extra = {}) => Object.assign({ type: "value", name, nameLocation: "end", nameGap: 10, ...AXIS }, extra);
const series = (d, f) => d.daily.date.map((t, i) => [t, f(i)]);
const windows = d => d.summary.maintenance_windows.map(w => w.split(".."));
function axisTip(unit, digits) {
  return params => {
    const date = params[0].axisValueLabel || params[0].value[0];
    return `<b>${String(params[0].value[0]).slice(0, 10)}</b><br>` + params.map(p =>
      `${p.marker}${p.seriesName}: <b>${fmt(p.value[1], digits)}</b> ${unit}`).join("<br>");
  };
}

// ---------- 0. selector ----------
function renderSelector() {
  const el = document.getElementById("selector");
  el.innerHTML = D.order.map(k => `<button type="button" data-k="${k}" aria-pressed="${k === current}">${D.designs[k].label}</button>`).join("");
  el.querySelectorAll("button").forEach(b => b.onclick = () => { current = b.dataset.k; history.replaceState(null, "", "#design=" + current); render(); });
  const d = D.designs[current], r = d.summary.ranking;
  document.getElementById("verdict").textContent = `${d.label} = ${d.name}: ${r.status} — ${r.reason}`;
}

// ---------- 1. KPIs ----------
function renderKpis(d) {
  const s = d.summary, ref = D.reference;
  const red = (ref.emissions_t - s.emissions_t) / ref.emissions_t;
  document.getElementById("p1-title").textContent = `${d.label} — key results`;
  document.getElementById("p1-sub").textContent = `${d.name} · ${s.ranking.status} · reference = gas boiler (η 0.90) + electric chiller (COP 5.0), same 2027 loads`;
  const tiles = [
    ["CO₂ emissions", `${fmt(s.emissions_t)} t/a`, `−${fmt(red * 100, 1)} % vs reference ${fmt(ref.emissions_t)} t/a`, true],
    ["Unmet heat / cooling", `${fmt(s.heat_unmet_GWh, 3)} / ${fmt(s.cool_unmet_GWh, 3)}`, "GWh over 365 days", false],
    ["External natural gas", `${fmt(s.external_gas_fuel_GWh, 3)} GWh`, `reference ${fmt(ref.gas_fuel_GWh, 1)} GWh`, false],
    ["Net grid import", `${fmt(s.grid_import_GWh, 2)} GWh`, `reference ${fmt(ref.grid_import_GWh, 2)} GWh`, false],
    ["Doublets × depth", `${s.candidate.n_doublets} × ${fmt(s.depth_m)} m`, `${fmt(s.reservoir_temperature_C, 1)} °C reservoir · ${fmt(s.drilled_m)} m drilled`, false],
    ["Flow cap / ESP", `${fmt(s.flow_cap_m3h)} m³/h`, `ESP s=${s.esp.flow_scale ?? s.candidate.esp} at ${fmt(s.esp_setting_depth_m)} m · ${fmt(s.esp_intake_at_max_flow_bar, 1)} bar intake`, false],
  ];
  document.getElementById("kpis").innerHTML = tiles.map(([k, v, dd, good]) =>
    `<div class="tile"><div class="k">${k}</div><div class="v">${v}</div><div class="d${good ? " good" : ""}">${dd}</div></div>`).join("");
}

// ---------- 2. heating ----------
function renderHeating(d) {
  const s = d.summary, x = d.daily;
  const geo = (s.heat_hex_GWh + s.heat_hp_GWh) / s.heating_demand_GWh;
  document.getElementById("p2-sub").textContent =
    `${fmt(s.heating_demand_GWh, 1)} GWh demand · HEX ${fmt(s.heat_hex_GWh, 1)} · heat pump ${fmt(s.heat_hp_GWh, 1)} · CHP ${fmt(s.heat_chp_GWh, 1)} · ` +
    `boiler ${fmt(s.heat_boiler_produced_gas_GWh + s.heat_boiler_external_gas_GWh, 2)} GWh · HEX + HP share ${fmt(geo * 100, 0)} % · unmet ${fmt(s.heat_unmet_GWh, 3)} GWh`;
  const area = (name, color, f) => ({ name, type: "line", stack: "heat", symbol: "none", color, lineStyle: { width: 0 },
    areaStyle: { color, opacity: 0.92 }, emphasis: { focus: "series" }, data: series(d, f) });
  chart("c-heat").setOption({
    ...base(),
    grid: { left: 52, right: 18, top: 66, bottom: 32 },
    tooltip: { ...TIP, trigger: "axis", axisPointer: { type: "line", lineStyle: { color: C.muted } }, formatter: axisTip("MW", 2) },
    xAxis: timeAxis(), yAxis: valueAxis("MW"),
    series: [
      area("HEX (direct)", C.geo, i => x.heat_hex_MW[i]),
      area("Heat pump", C.hp, i => x.heat_hp_MW[i]),
      area("CHP (produced gas)", C.pgas, i => x.heat_chp_MW[i]),
      area("Boiler (produced gas)", C.pgas2, i => x.heat_boiler_produced_gas_MW[i]),
      area("Boiler (external gas)", C.xgas, i => x.heat_boiler_external_gas_MW[i]),
      { name: "Heating demand", type: "line", symbol: "none", color: C.ink, lineStyle: { width: 2, color: C.ink }, z: 5, data: series(d, i => x.heating_demand_MW[i]) },
    ],
  }, true);
}

// ---------- 3. cooling ----------
function renderCooling(d) {
  const s = d.summary, x = d.daily;
  document.getElementById("p3-sub").textContent =
    `${fmt(s.cooling_demand_GWh, 1)} GWh demand · absorption ${fmt(s.cool_absorption_GWh, 1)} GWh (brine-driven) · electric ${fmt(s.cool_electric_GWh, 2)} GWh · unmet ${fmt(s.cool_unmet_GWh, 3)} GWh`;
  const area = (name, color, f) => ({ name, type: "line", stack: "cool", symbol: "none", color, lineStyle: { width: 0 },
    areaStyle: { color, opacity: 0.92 }, emphasis: { focus: "series" }, data: series(d, f) });
  chart("c-cool").setOption({
    ...base(),
    grid: { left: 52, right: 18, top: 66, bottom: 32 },
    tooltip: { ...TIP, trigger: "axis", axisPointer: { type: "line", lineStyle: { color: C.muted } }, formatter: axisTip("MW", 2) },
    xAxis: timeAxis(), yAxis: valueAxis("MW"),
    series: [
      area("Absorption chiller", C.geo, i => x.cool_absorption_MW[i]),
      area("Electric chiller", C.elec, i => x.cool_electric_MW[i]),
      { name: "Cooling demand", type: "line", symbol: "none", color: C.ink, lineStyle: { width: 2, color: C.ink }, z: 5, data: series(d, i => x.cooling_demand_MW[i]) },
    ],
  }, true);
}

// ---------- 4. brine ----------
function renderBrine(d) {
  const s = d.summary, x = d.daily, w = windows(d);
  document.getElementById("p4-sub").textContent =
    `Flow when on ${fmt(s.flow_min_when_on_m3h)}–${fmt(s.flow_max_m3h)} m³/h per doublet (limits 50 / 300; 0 = off) · max ΔT ${fmt(s.max_brine_dT_K, 2)} K (cap 40 K) · shaded: maintenance windows (35 d each)`;
  const nd = s.candidate.n_doublets, dblColors = [C.geo, C.inj, C.muted], dblDash = ["solid", [7, 5], [2, 4]];
  const on = (i, k) => x.active_doublets[i].split(";").includes(`doublet_${k}`);
  const shade = w.map((p, k) => [{ name: `D${k + 1} maintenance`, xAxis: p[0] }, { xAxis: p[1] }]);
  const mArea = (label) => ({ silent: true, itemStyle: { color: "rgba(137,135,129,0.16)" },
    label: { show: label, color: C.ink2, fontSize: 12, position: "insideTop" }, data: shade });
  const limit = (y, text) => ({ yAxis: y, label: { formatter: text, position: "insideEndTop", color: C.ink2, fontSize: 12 },
    lineStyle: { color: C.critical, type: "dashed", width: 1.5 } });
  chart("c-brine").setOption({
    ...base(),
    axisPointer: { link: [{ xAxisIndex: "all" }] },
    tooltip: { ...TIP, trigger: "axis", axisPointer: { type: "line", lineStyle: { color: C.muted } },
      formatter: p => { const i = p[0].dataIndex; return `<b>${x.date[i]}</b><br>active doublets: <b>${x.n_active[i]}</b>` +
        (x.maintenance[i] ? ` (maintenance: ${x.maintenance[i].replace(/doublet_/g, "D")})` : "") +
        Array.from({ length: nd }, (_, k) => `<br>D${k + 1}: <b>${on(i, k + 1) ? fmt(x.flow_per_doublet_m3h[i], 0) + "</b> m³/h" : "off</b>"}`).join("") +
        `<br>brine ΔT: <b>${fmt(x.brine_dT_K[i], 2)}</b> K`; } },
    grid: [{ left: 60, right: 18, top: 70, height: "36%" }, { left: 60, right: 18, top: "64%", bottom: 32 }],
    xAxis: [timeAxis({ gridIndex: 0, axisLabel: { show: false } }), timeAxis({ gridIndex: 1 })],
    yAxis: [valueAxis("m³/h per doublet", { gridIndex: 0, min: 0, max: 360 }), valueAxis("ΔT (K)", { gridIndex: 1, min: 0, max: 45 })],
    legend: { ...LEGEND, data: [...Array.from({ length: nd }, (_, k) => `D${k + 1}`), "Brine ΔT"] },
    series: [
      ...Array.from({ length: nd }, (_, k) => ({ name: `D${k + 1}`, type: "line", step: "middle", symbol: "none", color: dblColors[k],
        lineStyle: { width: k ? 2 : 2.5, type: dblDash[k] }, xAxisIndex: 0, yAxisIndex: 0, z: 3 + k,
        data: series(d, i => on(i, k + 1) ? x.flow_per_doublet_m3h[i] : 0),
        ...(k ? {} : { markArea: mArea(true), markLine: { silent: true, symbol: "none", data: [limit(50, "min 50 m³/h"), limit(300, "max 300 m³/h")] } }) })),
      { name: "Brine ΔT", type: "line", symbol: "none", color: C.ink2, lineStyle: { width: 2 }, xAxisIndex: 1, yAxisIndex: 1,
        data: series(d, i => x.brine_dT_K[i]), markArea: mArea(false),
        markLine: { silent: true, symbol: "none", data: [limit(40, "cap 40 K")] } },
    ],
  }, true);
}

// ---------- 5. agent path ----------
const STATUS = {
  accepted: { label: "Accepted (final pick)", color: C.good, symbol: "circle", size: 18 },
  rejected: { label: "Rejected (ranked out)", color: C.muted, symbol: "circle", size: 13 },
  marginal: { label: "Marginal sensitivity case", color: C.warning, symbol: "diamond", size: 18 },
  failed: { label: "Failed hard constraint", color: C.critical, symbol: "triangle", size: 16 },
};
function shortId(id) {
  const m = id.match(/^n(\d+)_q(\d+)_s([\d.]+)_ua(\d+)_z(\d+)$/);
  return m ? `${m[1]} dbl · ${m[5]} m${m[3] !== "1.8" ? " · s" + m[3] : ""}${m[4] !== "1000" ? " · UA" + m[4] : ""}` : id;
}
function renderAgent() {
  const A = D.agent, ev = A.evaluations, steps = A.depth_steps;
  const pick = ev.find(e => e.status === "accepted");
  document.getElementById("p5-sub").textContent =
    `${ev.length} annual evaluations (rules backend, ${fmt(A.timing.wall_s_per_computed_evaluation_mean, 1)} s each, ${fmt(A.timing.scenario_runtime_s, 1)} s total) · ` +
    `depth step kept only if emissions fall ≥ 5 % beyond the tie tolerance · hover a point for the reason`;
  const byStatus = k => ev.filter(e => e.status === k).map(e => ({ value: [e.n, e.emissions_t], e,
    label: e.status === "accepted" ? { show: true, formatter: "final pick", position: "top", color: C.ink, fontWeight: 600, fontSize: 13 } :
           e.status === "marginal" ? { show: true, formatter: "marginal", position: "bottom", color: C.ink2, fontSize: 12 } : { show: false } }));
  const evalSeries = Object.entries(STATUS).map(([k, st]) => ({ name: st.label, type: "scatter", symbol: st.symbol, symbolSize: st.size, color: st.color,
    itemStyle: { borderColor: C.surface, borderWidth: 2 }, xAxisIndex: 0, yAxisIndex: 0, z: 4, data: byStatus(k) }));
  // ladder: one segment per depth step (kept / marginal / rejected). A step that does not start where an earlier
  // step ended starts a new branch after a gas-handling switch at that depth (drawn as a dotted connector).
  const KIND = { kept: { color: C.good, type: "solid" }, marginal: { color: C.warning, type: "dashed" }, rejected: { color: C.muted, type: "dashed" } };
  const near = (a, b) => Math.abs(a - b) < 1e-6;
  const ends = [], segs = [], switches = [];
  steps.forEach((st, k) => {
    const kind = st.accepted ? "kept" : st.marginal ? "marginal" : "rejected";
    if (k === 0) ends.push({ depth: st.from_m, em: st.emissions_from_t, kind: "kept", text: "start" });
    else if (!ends.some(e => e.depth === st.from_m && near(e.em, st.emissions_from_t))) {
      const prev = ends.filter(e => e.depth === st.from_m && e.kind === "kept").pop();
      const change = prev ? st.emissions_from_t / prev.em - 1 : null;
      if (prev) switches.push({ from: prev, to: { depth: st.from_m, em: st.emissions_from_t }, change });
      ends.push({ depth: st.from_m, em: st.emissions_from_t, kind: "kept", text: "switch", change });
    }
    const p = { depth: st.to_m, em: st.emissions_to_t, kind, st };
    ends.push(p); segs.push({ st, kind, p });
  });
  const gasName = { co2_reinject: "CO₂ reinjected", reinject_all: "all gas reinjected", chp: "CHP" }[(A.gas_handling || {}).chosen] || "gas option";
  const maxDepth = Math.max(3500, ...ends.map(e => e.depth));
  const ladderSeries = [
    ...segs.map((g, k) => ({ name: `ladder-${k}`, type: "line", xAxisIndex: 1, yAxisIndex: 1, symbol: "none", silent: true, tooltip: { show: false },
      lineStyle: { width: 2, color: KIND[g.kind].color, type: KIND[g.kind].type }, z: 2,
      data: [[g.st.from_m, g.st.emissions_from_t], [g.st.to_m, g.st.emissions_to_t]] })),
    ...switches.map((w, k) => ({ name: `switch-${k}`, type: "line", xAxisIndex: 1, yAxisIndex: 1, symbol: "none", silent: true, tooltip: { show: false },
      lineStyle: { width: 2, color: C.s1, type: "dotted" }, z: 2,
      data: [[w.from.depth, w.from.em], [w.to.depth, w.to.em]] })),
    ...Object.keys(KIND).map(kind => ({ name: `ladder-pts-${kind}`, type: "scatter", xAxisIndex: 1, yAxisIndex: 1, z: 4,
      symbol: kind === "kept" ? "circle" : "diamond", symbolSize: kind === "kept" ? 12 : 16, color: KIND[kind].color,
      itemStyle: { borderColor: C.surface, borderWidth: 2 },
      data: ends.filter(e => e.kind === kind).map(e => ({ value: [e.depth, e.em], p: e,
        label: { show: !!e.st || e.text === "switch", distance: 8, fontSize: 12, lineHeight: 16,
          position: e.text === "switch" ? "left" : kind === "kept" ? "top" : kind === "marginal" ? "right" : "bottom",
          color: e.text === "switch" ? C.s1 : kind === "kept" ? C.ink2 : C.ink,
          formatter: e.text === "switch" ? `${gasName} ${pct(e.change)}`
            : !e.st ? "" : `${pct(e.st.emissions_change)}` + (kind === "kept" ? "" : kind === "marginal" ? "\nmarginal" : "\nrejected") } })) })),
  ];
  const ladderTip = p => p.st ? `<b>${fmt(p.st.from_m)} → ${fmt(p.st.to_m)} m</b><br>emissions ${fmt(p.st.emissions_from_t)} → ${fmt(p.st.emissions_to_t)} t/a (${pct(p.st.emissions_change)})` +
    `<br>marginal abatement ${fmt(p.st.marginal_abatement_t_per_yr_per_m, 3)} t CO₂/a per extra metre<br>` +
    (p.kind === "kept" ? "kept (≥ 5 % beyond tie tolerance)" : p.kind === "marginal" ? "<b>marginal sensitivity case</b>: within the tie tolerance of the 5 % threshold → not taken (drilling cost and risk not modelled)" : "rejected")
    : `<b>${fmt(p.depth)} m</b>: ${p.text === "switch" ? "gas-handling option accepted at this depth, ladder re-opened" : "ladder start"}, ${fmt(p.em)} t/a`;
  chart("c-agent").setOption({
    ...base(),
    legend: { ...LEGEND, data: Object.keys(STATUS).filter(k => ev.some(e => e.status === k)).map(k => STATUS[k].label) },  // only statuses that occur
    grid: [{ left: 64, right: "52%", top: 76, bottom: 56 }, { left: "56%", right: 22, top: 76, bottom: 56 }],
    title: [{ text: "Evaluations in order (t CO₂/a)", left: 0, top: 36, textStyle: { fontSize: 14, fontWeight: 600, color: C.ink } },
            { text: "Depth ladder, 2 doublets (t CO₂/a; % = step change)", left: "50%", top: 36, textStyle: { fontSize: 14, fontWeight: 600, color: C.ink } }],
    tooltip: { ...TIP, trigger: "item", formatter: p => {
      if (p.data && p.data.e) { const e = p.data.e; return `<b>#${e.n} ${e.id}</b><br>${STATUS[e.status].label}<br>emissions <b>${fmt(e.emissions_t)}</b> t/a · ` +
        `external gas ${fmt(e.external_gas_GWh, 3)} GWh · grid ${fmt(e.grid_import_GWh, 2)} GWh · ${fmt(e.drilled_m)} m drilled<br>` +
        `<span style="display:inline-block;max-width:460px;white-space:normal">${e.reason}</span>`; }
      if (p.data && p.data.p) return ladderTip(p.data.p);
      return ""; } },
    xAxis: [{ type: "value", gridIndex: 0, min: 0, max: ev.length + 1, interval: 1, name: "evaluation #", nameLocation: "middle", nameGap: 30, ...AXIS,
              splitLine: { show: false }, axisLabel: { ...AXIS.axisLabel, formatter: v => v >= 1 && v <= ev.length ? v : "" } },
            { type: "value", gridIndex: 1, min: 2250, max: maxDepth + 250, interval: 250, name: "well depth (m)", nameLocation: "middle", nameGap: 30, ...AXIS, splitLine: { show: false },
              axisLabel: { ...AXIS.axisLabel, formatter: v => v % 500 === 0 && v >= 2500 && v <= maxDepth ? v : "" } }],
    yAxis: [valueAxis("", { gridIndex: 0, min: 0 }),
            valueAxis("", { gridIndex: 1, min: Math.max(0, Math.floor(Math.min(...ends.map(e => e.em)) / 1000 - 1) * 1000) })],
    series: [
      { name: "order", type: "line", xAxisIndex: 0, yAxisIndex: 0, symbol: "none", silent: true, lineStyle: { color: C.axis, width: 1.5 },
        data: ev.map(e => [e.n, e.emissions_t]), tooltip: { show: false }, legendHoverLink: false },
      ...evalSeries,
      ...ladderSeries,
    ],
  }, true);
}

// ---------- 6. emissions bars ----------
function renderEmissions() {
  const ref = D.reference, c1 = D.designs.C1 ? D.designs.C1.summary : null, fin = D.designs.FINAL.summary;
  const rows = [
    { name: "Reference", sub: "boiler + chiller", prod: 0, ext: ref.emissions_gas_t, el: ref.emissions_electricity_t },
    ...(c1 ? [{ name: "C1", sub: `2 dbl · ${fmt(c1.depth_m)} m`, prod: c1.emissions_produced_gas_t, ext: c1.emissions_external_gas_t, el: c1.emissions_electricity_t }] : []),
    { name: "Final design", sub: `${fin.candidate.n_doublets} dbl · ${fmt(fin.depth_m)} m`, prod: fin.emissions_produced_gas_t, ext: fin.emissions_external_gas_t, el: fin.emissions_electricity_t },
  ];
  const tot = r => r.prod + r.ext + r.el;
  const red = r => (tot(rows[0]) - tot(r)) / tot(rows[0]);
  document.getElementById("p6-sub").textContent = `Final design ${fmt(tot(rows[rows.length - 1]))} t/a, −${fmt(red(rows[rows.length - 1]) * 100, 1)} % vs reference` +
    (c1 ? ` (C1: −${fmt(red(rows[1]) * 100, 1)} %)` : "");
  const bar = (name, color, key, top) => ({ name, type: "bar", stack: "em", color, barWidth: "46%",
    itemStyle: { borderColor: C.surface, borderWidth: 1, borderRadius: top ? [4, 4, 0, 0] : 0 },
    data: rows.map(r => r[key]),
    label: top ? { show: true, position: "top", color: C.ink, fontSize: 14, fontWeight: 600,
      formatter: p => `${fmt(tot(rows[p.dataIndex]))} t` + (p.dataIndex ? `\n−${fmt(red(rows[p.dataIndex]) * 100, 1)} %` : "") } : { show: false } });
  chart("c-em").setOption({
    ...base(),
    grid: { left: 64, right: 12, top: 76, bottom: 52 },
    tooltip: { ...TIP, trigger: "axis", axisPointer: { type: "shadow" }, formatter: p => `<b>${rows[p[0].dataIndex].name}</b><br>` +
      p.map(q => `${q.marker}${q.seriesName}: <b>${fmt(q.value)}</b> t/a`).join("<br>") + `<br>total <b>${fmt(tot(rows[p[0].dataIndex]))}</b> t/a` },
    legend: { ...LEGEND, top: 0 },
    xAxis: { type: "category", data: rows.map(r => r.name), ...AXIS, splitLine: { show: false },
      axisLabel: { color: C.ink, fontSize: 13, interval: 0, formatter: (v, i) => `${v}\n{s|${rows[i].sub}}`, rich: { s: { color: C.ink2, fontSize: 12, lineHeight: 18 } } } },
    yAxis: valueAxis("t CO₂/a", { max: v => Math.ceil(v.max * 1.1 / 5000) * 5000 }),
    series: [bar("Produced gas (CHP/boiler/flare)", C.pgas, "prod"), bar("External natural gas", C.xgas, "ext"), bar("Grid electricity", C.elec, "el", true)],
  }, true);
}

// ---------- 7. schematic ----------
const GAS = { chp: ["gas → CHP", "produced gas (dashed) → CHP, then boiler"],
              co2_reinject: ["CO₂ reinjected", "CH₄ (dashed) → CHP, then boiler; CO₂ reinjected with the brine"],
              reinject_all: ["gas reinjected", "all produced gas reinjected with the brine, no combustion"] };
function renderSchematic(d) {
  const p = d.point, s = d.summary, n = s.candidate.n_doublets;
  document.getElementById("p7-sub").textContent =
    `Heat path on the peak-heating day ${p.date} (${fmt(p.heating_demand_MW, 1)} MW); absorption chiller on the peak-cooling day ${p.cool_date} (${fmt(p.cool_cooling_demand_MW, 1)} MW)`;
  const brine = C.geo, water = C.dh, chill = C.dc;
  const box = (x, y, w, h, title, lines, stroke) =>
    `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="8" fill="${C.surface}" stroke="${stroke || C.axis}" stroke-width="1.5"/>` +
    `<text x="${x + w / 2}" y="${y + 22}" text-anchor="middle" font-size="15" font-weight="650" fill="${C.ink}">${title}</text>` +
    lines.map((l, i) => `<text x="${x + w / 2}" y="${y + 42 + i * 18}" text-anchor="middle" font-size="13" fill="${C.ink2}">${l}</text>`).join("");
  const arrow = (x1, y1, x2, y2, color, label, dy = -8, dash = "") =>
    `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${color}" stroke-width="3" ${dash ? `stroke-dasharray="${dash}"` : ""} marker-end="url(#ah-${color.slice(1)})"/>` +
    (label ? `<text x="${(x1 + x2) / 2}" y="${(y1 + y2) / 2 + dy}" text-anchor="middle" font-size="13" font-weight="600" fill="${C.ink}">${label}</text>` : "");
  const marker = c => `<marker id="ah-${c.slice(1)}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="${c}"/></marker>`;
  const T = v => `${fmt(v, 1)} °C`;
  const q = p.flow_per_doublet_m3h * p.n_active;
  const gasMode = s.gas_handling || "chp";
  const svg = `<svg viewBox="0 0 1020 480" class="schem" role="img" aria-label="System schematic" preserveAspectRatio="xMidYMid meet">
  <defs>${marker(brine)}${marker(water)}${marker(chill)}${marker(C.muted)}</defs>
  ${box(10, 40, 140, 120, `${n} producer well${n > 1 ? "s" : ""}`, [`${fmt(s.depth_m)} m, ${fmt(s.reservoir_temperature_C, 1)} °C`, `ESP at ${fmt(s.esp_setting_depth_m)} m`, `${p.n_active} on × ${fmt(p.flow_per_doublet_m3h)} m³/h`], brine)}
  ${box(210, 40, 100, 120, "Separator", ["+ filters", GAS[gasMode][0], "GLR 0.8"])}
  ${box(370, 40, 130, 120, "Absorption", ["chiller (hot end)", `${fmt(p.cool_cool_absorption_MW, 1)} MW cool`, `drive ${fmt(p.cool_absorber_drive_MW, 1)} MWth`], chill)}
  ${box(560, 40, 100, 330, "HEX", [`UA ${fmt(s.candidate.hex_ua_W_K / 1000)} kW/K`, `${fmt(p.heat_hex_MW, 1)} MW`])}
  ${box(720, 40, 100, 330, "Heat pump", [`${fmt(p.heat_hp_MW, 1)} MWth`, `COP ${p.hp_COP == null ? "–" : fmt(p.hp_COP, 2)}`])}
  ${box(880, 40, 132, 120, "Injectors", [`${n} well${n > 1 ? "s" : ""}`, T(p.T_injection_C)], brine)}
  ${box(880, 250, 132, 120, "CHP + boiler", [`CHP ${fmt(p.heat_chp_MW, 2)} MW`, `boiler ${fmt(p.heat_boiler_MW, 2)} MW`])}
  ${box(370, 250, 130, 120, "District return", [T(p.T_return_C), `${fmt(p.district_flow_m3h)} m³/h`], water)}
  ${arrow(150, 120, 208, 120, brine, T(p.T_wellhead_C), -10)}
  ${arrow(310, 120, 368, 120, brine, T(p.T_absorber_in_C), -10)}
  ${arrow(500, 120, 558, 120, brine, T(p.T_hex_in_C), -10)}
  ${arrow(660, 120, 718, 120, brine, "", 0)}
  ${arrow(820, 120, 878, 120, brine, "", 0)}
  ${arrow(500, 330, 558, 330, water, T(p.T_return_C), -10)}
  ${arrow(660, 330, 718, 330, water, T(p.T_after_hex_C), -10)}
  ${arrow(820, 330, 878, 330, water, T(p.T_after_hp_C), -10)}
  ${arrow(946, 370, 946, 428, water, "", 0)}
  <text x="1012" y="456" text-anchor="end" font-size="15" font-weight="650" fill="${C.ink}">District heating ${T(p.T_supply_C)} · ${fmt(p.heat_delivered_MW, 1)} MW</text>
  ${arrow(435, 40, 435, 12, chill, "", 0)}
  <text x="445" y="22" font-size="13" font-weight="600" fill="${C.ink}">chilled water 20 °C to district cooling</text>
  <path d="M260 160 V 405 H 860 V 350 H 876" fill="none" stroke="${C.muted}" stroke-width="2" stroke-dasharray="6 5" marker-end="url(#ah-${C.muted.slice(1)})"/>
  <text x="270" y="424" font-size="13" fill="${C.ink2}">${GAS[gasMode][1]}</text>
  <text x="10" y="200" font-size="13" fill="${C.ink2}"><tspan x="10" dy="0" fill="${brine}" font-weight="650">━ brine</tspan><tspan x="10" dy="20" fill="${water}" font-weight="650">━ heating water</tspan><tspan x="10" dy="20" fill="${chill}" font-weight="650">━ chilled water</tspan><tspan x="10" dy="20">brine ${fmt(q)} m³/h total</tspan><tspan x="10" dy="20">HP source: brine</tspan><tspan x="10" dy="18">after the HEX</tspan></text>
</svg>`;
  document.getElementById("schem").innerHTML = svg;
}

// ---------- 8. constraints ----------
function badge(status) {
  return status === "PASS" ? `<span class="badge pass"><span class="dot">✓</span>PASS</span>` : `<span class="badge fail"><span class="dot">✕</span>${status}</span>`;
}
function renderChecks(d) {
  const rows = d.constraints, n = rows.filter(r => r.status === "PASS").length;
  document.getElementById("p8-sub").textContent = `${d.label}: ${n} / ${rows.length} pass · ${d.summary.feasible ? "feasible" : "INFEASIBLE"} · worst case over 365 days`;
  document.getElementById("checks").innerHTML = `<table><thead><tr><th>Constraint</th><th>Limit</th><th>Worst case</th><th>Status</th></tr></thead><tbody>` +
    rows.map(r => `<tr><td>${r.name}</td><td>${r.limit}</td><td class="num">${r.worst}</td><td>${badge(r.status)}</td></tr>`).join("") + `</tbody></table>` +
    `<p class="sub">Design attribute, not a constraint: ${d.no_geothermal_days} day(s) without geothermal supply (backup covers them). ` +
    `The 330-day rule limits the geothermal source; the full system must meet demand all 365 days (organizer clarification, Discord, 1 Nov 2026).</p>`;
}

// ---------- 9. judges' tests ----------
function renderTests() {
  const t = D.agent.judges_tests;
  document.getElementById("p9-sub").textContent = `${t.filter(x => x.pass).length} / ${t.length} pass · rules backend · excerpts from outputs/agent/agent_trace.md`;
  const esc = s => s.replace(/&/g, "&amp;").replace(/</g, "&lt;");
  document.getElementById("tests").innerHTML = t.map(x =>
    `<li>${badge(x.pass ? "PASS" : "FAIL")}<span class="t">${esc(x.test)}</span><span class="e">${esc(x.evidence).split("; also ").join("<br>")}</span></li>`).join("");
  document.getElementById("p9-note").textContent = "The claude_cli run predates gas handling as a design variable (it picked 2 doublets at 3 250 m with CHP); it never proposed an invalid flow or a failing design, so tests (ii) and (iv) were not triggered there.";
}

// ---------- 10. sensitivity tornado ----------
function renderTornado() {
  const S = D.sensitivity, el = document.getElementById("p10-sub");
  if (!S) { el.textContent = "Run hackathon_work/sensitivity.py to fill this panel."; return; }
  const params = [...new Set(S.cases.map(c => c.parameter))];
  const rows = params.map(p => {
    const low = S.cases.find(c => c.parameter === p && c.side === "low"), high = S.cases.find(c => c.parameter === p && c.side === "high");
    return { p, label: low.label, unit: low.unit, base: low.base, low, high, span: Math.abs(high.delta_emissions_t - low.delta_emissions_t) };
  }).sort((a, b) => a.span - b.span);  // largest spread on top
  const changed = S.cases.filter(c => c.pick_changed);
  el.textContent = `${S.base.candidate}: ${fmt(S.base.emissions_t)} t/a at base inputs · bars = change in the final design's emissions when one input moves (ASSUMED spread)`;
  const u = r => r.unit === "-" ? "" : ` ${r.unit}`;
  const num = v => fmt(v, v < 10 ? 2 : 0);
  const bar = (name, color, side) => ({ name, type: "bar", color, barWidth: 14, barGap: "30%",
    itemStyle: { borderRadius: 4, borderColor: C.surface, borderWidth: 1 },
    data: rows.map(r => ({ value: r[side].delta_emissions_t, c: r[side], r })),
    label: { show: true, position: "right", color: C.ink2, fontSize: 12,
      formatter: q => `${num(q.data.c.value)}${u(q.data.r)}: ${Math.abs(q.value) < 0.5 ? "" : q.value > 0 ? "+" : "−"}${fmt(Math.abs(q.value))} t` +
        (q.data.c.final_design.feasible ? "" : " (fails)") + (q.data.c.pick_changed ? " · pick changes" : "") } });
  chart("c-tornado").setOption({
    ...base(),
    grid: { left: 200, right: 190, top: 40, bottom: 48 },
    tooltip: { ...TIP, trigger: "item", formatter: q => { const c = q.data.c, r = q.data.r;
      return `<b>${r.label} = ${num(c.value)}${u(r)}</b> (base ${r.base}${u(r)})<br>` +
        `final design ${fmt(c.final_design.emissions_t)} t/a (${q.value > 0 ? "+" : "−"}${fmt(Math.abs(q.value))} t, ${pct(c.delta_emissions_pct)})<br>` +
        `hard constraints ${c.final_design.feasible ? "PASS" : "FAIL: " + c.final_design.failing.join(", ")}<br>` +
        `agent pick ${c.agent_pick}${c.pick_changed ? " (changed)" : ""}`; } },
    legend: { ...LEGEND, data: ["Low value", "High value"] },
    xAxis: valueAxis("Δ emissions of the final design (t CO₂/a)", { nameLocation: "middle", nameGap: 30,
      axisLabel: { color: C.ink2, fontSize: 13, formatter: v => (v > 0 ? "+" : v < 0 ? "−" : "") + fmt(Math.abs(v)) } }),
    yAxis: { type: "category", data: rows.map(r => `${r.label}\n{s|base ${r.base}${u(r)}}`), ...AXIS, splitLine: { show: false },
      axisLabel: { color: C.ink, fontSize: 13, rich: { s: { color: C.ink2, fontSize: 12, lineHeight: 18 } } } },
    series: [bar("Low value", C.inj, "low"), bar("High value", C.loss, "high")],
  }, true);
  const why = c => { const r = c.base_pick_verdict || "";
    return r.startsWith("not evaluated") ? "the reservoir temperature moves, so the depth ladder stops at another depth"
      : r.includes("extra doublet") ? "a third doublet cuts external gas by ≥ 5 %"
      : r.includes("within the tie tolerance of the threshold") ? "the 3 500 m step lands within the tie tolerance of the 5 % threshold"
      : r.includes("parsimony rule not met") ? "the 3 500 m step saves < 5 %" : "ranked lower"; };
  document.getElementById("p10-note").textContent = changed.length
    ? `The agent's pick changes in ${changed.length} of ${S.cases.length} cases: ${changed.map(c => `${c.label} = ${c.value} → ${shortId(c.agent_pick.replace(/_(co2ri|allri)$/, ""))} (${why(c)})`).join("; ")}. ` +
      `The other cases keep ${S.base.candidate}; every case passes all hard constraints.` +
      rows.filter(r => r.span < 0.5).map(r => ` ${r.label} does not change emissions at this design.`).join("")
    : `A fresh agent run with each changed input keeps ${S.base.candidate} in every case.`;
}

// ---------- 11. N-1 resilience and gas handling ----------
function renderResilience() {
  const rows = ["FINAL", "C1"].filter(k => D.designs[k] && D.designs[k].summary.n_minus_1).map(k => D.designs[k]);
  document.getElementById("p11-sub").textContent = "Unplanned outage of one doublet on the peak heating and peak cooling days (ASSUMED case); installed backup = max(planned peak, N-1)";
  const m = t => `<br><span class="small">${t}</span>`;
  let html = `<table><thead><tr><th>Design</th><th>Peak heating day: boiler</th><th>Peak cooling day: chiller</th><th>Installed backup</th></tr></thead><tbody>` +
    rows.map(d => { const n = d.summary.n_minus_1, ib = d.summary.installed_backup_MW;
      return `<tr><td>${d.label}${m(d.name)}</td>` +
        `<td class="num">${fmt(n[0].boiler_MWth, 1)} MWth${m(`${n[0].date}, ${n[0].n_active_normal} → ${n[0].n_active_n_minus_1} on`)}</td>` +
        `<td class="num">${fmt(n[1].electric_chiller_MWcool, 1)} MWcool${m(`${n[1].date}, ${n[1].n_active_normal} → ${n[1].n_active_n_minus_1} on`)}</td>` +
        `<td class="num">${fmt(ib.boiler_th, 1)} MWth boiler<br>${fmt(ib.electric_chiller_cool, 1)} MWcool chiller</td></tr>`; }).join("") +
    `</tbody></table>`;
  const g = D.agent.gas_handling;
  if (g && g.options && g.options.length) {
    const label = { chp: "a) CHP on all gas", co2_reinject: "b) CO₂ reinjected, CH₄ to CHP", reinject_all: "c) all gas reinjected" };
    html += `<h3>Gas handling at ${g.options[0].candidate.replace(/_(co2ri|allri)$/, "")}</h3>` +
      `<table><thead><tr><th>Option</th><th>External gas</th><th>Emissions</th><th>Grid import</th><th>Dissolution margin<br>wellhead / reservoir</th><th>Result</th></tr></thead><tbody>` +
      g.options.map(o => `<tr><td>${label[o.gas_handling] || o.gas_handling}</td><td class="num">${fmt(o.external_gas_GWh, 3)} GWh</td>` +
        `<td class="num">${fmt(o.emissions_t)} t</td><td class="num">${fmt(o.grid_import_GWh, 2)} GWh</td>` +
        `<td class="num">${o.dissolution ? `${fmt(o.dissolution.wellhead_margin, 2)} / ${fmt(o.dissolution.reservoir_margin, 1)}` +
          (o.dissolution.wellhead_margin < 1 ? m(`dip tube ≥ ${fmt(o.dissolution.dip_tube_depth_m)} m`) : "") : "burned"}</td>` +
        `<td>${o.gas_handling === g.chosen ? "<b>chosen</b>" : "ranked out"}</td></tr>`).join("") +
      `</tbody></table><p class="sub">Ranking: external gas first (ties within 0.1 GWh / 1 %), then emissions. Dissolution margin = gas the brine can hold / gas reinjected (≥ 1 dissolves; DERIVED, gas_solubility.py).` +
      (g.chosen === "co2_reinject" ? " Option (c) has the lowest emissions but needs more external gas on the coldest days, so it ranks below (b)." : "") + `</p>`;
  }
  document.getElementById("resilience").innerHTML = html;
}


// ---------- 12. annual energy Sankey ----------
const NODE_COLOR = n => n.startsWith("Reservoir") || n === "HEX" || n === "Absorption chiller" ? C.geo
  : n === "Heat pump" ? C.hp : n.startsWith("Produced gas") || n === "CHP" ? C.pgas : n === "CO₂ to reinjection" ? C.pgas2
  : n === "External gas" || n === "Boiler" ? C.xgas : n === "Grid electricity" || n === "Electricity" || n === "Electric chiller" || n === "Grid export" ? C.elec
  : n === "District heating" ? C.dh : n === "District cooling" ? C.dc : n === "Injection & pumping" ? C.inj : C.loss;
function renderSankey(d) {
  const S = d.sankey, s = d.summary;
  const tot = (pred) => S.links.filter(pred).reduce((a, l) => a + l.value, 0);
  const dh = tot(l => l.target === "District heating"), geoHeat = tot(l => l.target === "District heating" && (l.source === "HEX" || l.source === "Heat pump"));
  document.getElementById("p12-sub").textContent = `${d.label}, 2027, GWh · brine heat used ${fmt(S.brine_GWh, 1)} GWh` +
    (S.co2_reinjected_t ? ` · ${fmt(S.co2_reinjected_t)} t CO₂ reinjected` : "") + ` · flared ${fmt(S.flared_GWh, 2)} GWh (summer, no heat sink) · cooling shown as heat removed`;
  document.getElementById("p12-story").textContent = `${fmt(geoHeat / dh * 100, 0)} % of district heating comes from the reservoir (HEX + heat pump); ` +
    (s.gas_handling === "co2_reinject" ? "produced CH₄ runs the CHP and the CO₂ goes back into the reservoir." : "the produced gas runs the CHP.");
  chart("c-sankey").setOption({
    ...base(),
    tooltip: { ...TIP, trigger: "item", formatter: p => p.dataType === "edge" ? `${p.data.source} → ${p.data.target}: <b>${fmt(p.data.value, p.data.value < 1 ? 3 : 1)}</b> GWh`
      : `<b>${p.name}</b>: ${fmt(p.value, p.value < 1 ? 3 : 1)} GWh` },
    series: [{ type: "sankey", left: 8, right: 150, top: 12, bottom: 12, nodeGap: 14, nodeWidth: 14, layoutIterations: 64, draggable: !EXPORT,
      emphasis: { focus: "adjacency" },
      data: S.nodes.map(n => ({ name: n, itemStyle: { color: NODE_COLOR(n), borderColor: NODE_COLOR(n) } })),
      links: S.links.map(l => ({ ...l, lineStyle: { color: NODE_COLOR(l.source), opacity: 0.38 } })),
      label: { color: C.ink, fontSize: 13, formatter: p => `${p.name}  {v|${fmt(p.value, p.value < 1 ? 2 : 1)}}`, rich: { v: { color: C.ink2, fontSize: 12 } } },
      lineStyle: { curveness: 0.5 } }],
  }, true);
}

// ---------- 13. monthly supply ----------
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
function renderMonthly(d) {
  const M = d.monthly;
  const ext = M["Boiler (external gas)"].reduce((a, b) => a + b, 0), el = M["Electric chiller"].reduce((a, b) => a + b, 0);
  const peak = M["Heating demand"].indexOf(Math.max(...M["Heating demand"]));
  document.getElementById("p13-sub").textContent = `${d.label}, GWh per month · top: heating, bottom: cooling · line = demand`;
  document.getElementById("p13-story").textContent = `Demand is met in every month; external-gas boiler ${fmt(ext, 3)} GWh and electric chiller ${fmt(el, 2)} GWh over the whole year` +
    ` (heating peaks in ${MONTHS[peak]}).`;
  const bar = (name, color, key, grid, top) => ({ name, type: "bar", stack: grid ? "cool" : "heat", xAxisIndex: grid, yAxisIndex: grid, color, barWidth: "56%",
    itemStyle: { borderColor: C.surface, borderWidth: 1, borderRadius: top ? [4, 4, 0, 0] : 0 }, data: M[key] });
  const dem = (name, key, grid) => ({ name, type: "line", xAxisIndex: grid, yAxisIndex: grid, data: M[key], color: C.ink, symbol: "circle", symbolSize: 7,
    lineStyle: { width: 2, color: C.ink }, itemStyle: { color: C.ink, borderColor: C.surface, borderWidth: 2 }, z: 5 });
  const heatKeys = ["HEX (direct)", "Heat pump", "CHP (produced gas)", "Boiler (produced gas)", "Boiler (external gas)"].filter(k => M[k].some(v => v > 1e-3));
  const coolKeys = ["Absorption chiller", "Electric chiller"].filter(k => M[k].some(v => v > 1e-3));
  const col = { "HEX (direct)": C.geo, "Heat pump": C.hp, "CHP (produced gas)": C.pgas, "Boiler (produced gas)": C.pgas2, "Boiler (external gas)": C.xgas,
                "Absorption chiller": C.geo, "Electric chiller": C.elec };
  chart("c-monthly").setOption({
    ...base(),
    legend: { ...LEGEND, data: [...heatKeys, ...coolKeys.filter(k => k !== "Absorption chiller"), "Absorption chiller", "Heating demand", "Cooling demand"].filter((v, i, a) => a.indexOf(v) === i) },
    tooltip: { ...TIP, trigger: "axis", axisPointer: { type: "shadow" }, formatter: p => `<b>${MONTHS[p[0].dataIndex]}</b><br>` +
      p.filter(q => q.value > 1e-4).map(q => `${q.marker}${q.seriesName}: <b>${fmt(q.value, q.value < 1 ? 3 : 2)}</b> GWh`).join("<br>") },
    grid: [{ left: 64, right: 18, top: 70, height: "44%" }, { left: 64, right: 18, top: "68%", bottom: 30 }],
    xAxis: [{ type: "category", data: MONTHS, gridIndex: 0, ...AXIS, splitLine: { show: false }, axisLabel: { show: false } },
            { type: "category", data: MONTHS, gridIndex: 1, ...AXIS, splitLine: { show: false } }],
    yAxis: [valueAxis("heating GWh", { gridIndex: 0 }), valueAxis("cooling GWh", { gridIndex: 1, splitNumber: 3 })],
    series: [...heatKeys.map((k, i) => bar(k, col[k], k, 0, i === heatKeys.length - 1)), dem("Heating demand", "Heating demand", 0),
             ...coolKeys.map((k, i) => bar(k, col[k], k, 1, i === coolKeys.length - 1)), dem("Cooling demand", "Cooling demand", 1)],
  }, true);
}

// ---------- 14. agent replay + human-in-the-loop chat ----------
const RP = { i: 0, timer: null };
function rpIncumbent(k) {  // incumbent after step k, from the ranking text logged at that step
  const m = (D.agent.replay[k].verdict || "").match(/Incumbent: (\S+)/);
  return m ? m[1] : null;
}
function renderReplayStep() {
  const R = D.agent.replay, k = RP.i, st = R[k], inc = rpIncumbent(k);
  const esc = t => String(t || "").replace(/&/g, "&amp;").replace(/</g, "&lt;");
  document.getElementById("rp-stepno").textContent = `step ${k + 1} / ${R.length}`;
  const isInc = inc === st.candidate;
  document.getElementById("rp-card").innerHTML =
    `<h3>#${st.n} ${esc(st.candidate)}</h3>` +
    `<div class="lab">Why the agent proposed it</div><div>${esc(st.why)}</div>` +
    (st.checks.length ? `<div class="lab">Checks before the annual run</div><div>${st.checks.map(esc).join("<br>")}</div>` : "") +
    `<div class="lab">365-day result</div><div>${esc(st.result)}</div>` +
    (st.depth ? `<div class="lab">Depth step</div><div>${esc(st.depth)}</div>` : "") +
    `<div class="lab">Ranking after this step</div><div class="${isInc ? "verdict-in" : ""}">${isInc ? "New incumbent: " : "Incumbent stays: "}${esc(inc)}</div>`;
  const pts = R.map((r, j) => ({ value: [j + 1, r.emissions_t], r, j }));
  const incIds = new Set(R.slice(0, k + 1).map((_, j) => rpIncumbent(j)));
  chart("c-replay").setOption({
    ...base(), animation: !EXPORT, animationDurationUpdate: 500,
    grid: { left: 64, right: 16, top: 70, bottom: 48 },
    tooltip: { ...TIP, trigger: "item", formatter: p => p.data.r ? `<b>#${p.data.r.n} ${p.data.r.candidate}</b><br>${fmt(p.data.r.emissions_t)} t/a · external gas ${fmt(p.data.r.external_gas_GWh, 3)} GWh` : "" },
    legend: { ...LEGEND, data: ["Evaluated so far", "Incumbent (best so far)", "Current step"] },
    xAxis: { type: "value", min: 0, max: R.length + 1, interval: 1, name: "step", nameLocation: "middle", nameGap: 28, ...AXIS, splitLine: { show: false },
      axisLabel: { ...AXIS.axisLabel, formatter: v => v >= 1 && v <= R.length ? v : "" } },
    yAxis: valueAxis("t CO₂/a", { min: 0, max: v => Math.ceil(v.max * 1.1 / 3000) * 3000, interval: 3000 }),
    series: [
      { name: "Evaluated so far", type: "scatter", symbolSize: 12, color: C.muted, itemStyle: { borderColor: C.surface, borderWidth: 2 },
        data: pts.filter(q => q.j < k && !incIds.has(q.r.candidate)) },
      { name: "Incumbent (best so far)", type: "line", step: "end", symbol: "circle", symbolSize: 12, color: C.good, lineStyle: { width: 2, color: C.good },
        itemStyle: { borderColor: C.surface, borderWidth: 2 },
        data: R.slice(0, k + 1).map((_, j) => { const id = rpIncumbent(j), q = pts.find(z => z.r.candidate === id); return { value: [j + 1, q ? q.r.emissions_t : null], r: q && q.r }; }) },
      { name: "Current step", type: "effectScatter", symbolSize: 18, color: C.ink, rippleEffect: { scale: 2.2, brushType: "stroke" }, z: 6,
        data: [{ value: pts[k].value, r: st }], label: { show: true, position: "top", color: C.ink, fontSize: 13, fontWeight: 600,
          formatter: () => shortId(st.candidate.replace(/_(co2ri|allri)$/, "")) + (st.candidate.endsWith("_co2ri") ? " · CO₂ri" : st.candidate.endsWith("_allri") ? " · all ri" : "") } },
    ],
  }, false);
}
function rpGo(i) { RP.i = Math.max(0, Math.min(D.agent.replay.length - 1, i)); renderReplayStep(); }
function rpPlay(on) {
  const btn = document.getElementById("rp-play");
  if (RP.timer) { clearInterval(RP.timer); RP.timer = null; }
  if (on) {
    if (RP.i >= D.agent.replay.length - 1) rpGo(0);
    RP.timer = setInterval(() => { if (RP.i >= D.agent.replay.length - 1) rpPlay(false); else rpGo(RP.i + 1); }, 2600);
  }
  btn.textContent = on ? "⏸ Pause" : "▶ Play"; btn.setAttribute("aria-label", on ? "Pause" : "Play");
}
function renderReplay() {
  const R = D.agent.replay;
  document.getElementById("p14-sub").textContent = `${R.length} proposals from outputs/agent/decision_log.jsonl (rules backend) · play, or step with ◀ / ▶| · right: the interactive run's question to the user`;
  document.getElementById("rp-first").onclick = () => { rpPlay(false); rpGo(0); };
  document.getElementById("rp-prev").onclick = () => { rpPlay(false); rpGo(RP.i - 1); };
  document.getElementById("rp-next").onclick = () => { rpPlay(false); rpGo(RP.i + 1); };
  document.getElementById("rp-play").onclick = () => rpPlay(!RP.timer);
  // export / first view: the step where the final pick is found
  rpGo(EXPORT ? Math.max(0, R.findIndex(r => r.candidate === rpIncumbent(R.length - 1))) : 0);
  const chat = D.agent.chat, esc = t => String(t || "").replace(/&/g, "&amp;").replace(/</g, "&lt;");
  document.getElementById("chat").innerHTML = `<div class="hdr">Human-in-the-loop run (<code>--interactive --remove heating_return_T</code>, outputs/agent/interactive/). Recorded at an earlier model state; the user's 40 °C answer, not the 60 °C base, drives its result.</div>` +
    chat.map(c => `<div class="bubble ${c.who}"><span class="tag">${esc(c.tag)}</span>${esc(c.text)}${c.note ? `<br><span class="small" style="color:inherit;opacity:.8">${esc(c.note)}</span>` : ""}</div>`).join("") +
    (chat.length ? "" : `<div class="hdr">No interactive run found.</div>`);
}

// ---------- 15. why this design ----------
function renderWhy() {
  const W = D.agent.why;
  document.getElementById("p15-story").textContent = `${D.designs.FINAL.name}: the reasons below are taken from the agent's own log (verdicts, depth steps, gas decision).`;
  document.getElementById("why").innerHTML = W.map((w, i) => `<div class="card"><div class="n">${i + 1}</div><h3>${w.title}</h3><p>${w.text}</p></div>`).join("");
}

// ---------- story lines (what each panel proves) ----------
function renderStories(d) {
  const s = d.summary, ref = D.reference, set = (id, t) => { const el = document.getElementById(id + "-story"); if (el) el.textContent = t; };
  const red = (1 - s.emissions_t / ref.emissions_t) * 100, geo = (s.heat_hex_GWh + s.heat_hp_GWh) / s.heating_demand_GWh * 100;
  set("p1", `${d.label} serves all 2027 heating and cooling with ${fmt(red, 1)} % less CO₂ than a gas boiler + electric chiller.`);
  const parts = [["CH₄ burned in the CHP", s.emissions_produced_gas_t], ["grid electricity", s.emissions_electricity_t], ["external gas", s.emissions_external_gas_t]];
  const top = parts.reduce((a, b) => (b[1] > a[1] ? b : a));
  set("p6", `Emissions fall from ${fmt(ref.emissions_t)} to ${fmt(s.emissions_t)} t/a; the largest remaining share (${fmt(top[1] / s.emissions_t * 100, 0)} %) is ${top[0]}.`);
  set("p2", `100 °C is held every day: geothermal (HEX + heat pump) supplies ${fmt(geo, 0)} % of the heat, the CHP tops up in winter.`);
  set("p3", `Brine-driven absorption covers ${fmt(s.cool_absorption_GWh / s.cooling_demand_GWh * 100, 0)} % of cooling; the electric chiller is backup.`);
  set("p4", `Each doublet stays inside 50–300 m³/h and ΔT ≤ 40 K, and rests 35 days in summer.`);
  set("p7", `Temperatures and duties along the brine and district-water paths on the peak days.`);
  set("p14", `The agent proposes, pre-checks, simulates and ranks every candidate itself, and asks a person when an input is missing.`);
  set("p5", `Deeper wells pay off until the 5 % rule stops the ladder; the gas-handling switch re-opens it once.`);
  set("p9", `All four agent-reasoning behaviours the judges asked for, with evidence from the log.`);
  set("p8", `Every hard constraint passes on the worst day of the year.`);
  set("p11", `An unplanned doublet outage is covered by installed backup, and the reinjected gas dissolves.`);
  set("p10", `No plausible input change breaks a hard constraint; only depth or doublet count shifts.`);
}

function render() {
  const d = D.designs[current];
  renderSelector(); renderKpis(d); renderHeating(d); renderCooling(d); renderBrine(d); renderSchematic(d); renderChecks(d);
  renderSankey(d); renderMonthly(d); renderStories(d);
}
render(); renderAgent(); renderEmissions(); renderTests(); renderTornado(); renderResilience(); renderReplay(); renderWhy();
</script>
</body>
</html>
"""


def find_browser() -> str | None:
    for path in (os.environ.get("BROWSER_EXE"), r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                 r"C:\Program Files\Microsoft\Edge\Application\msedge.exe", r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                 shutil.which("msedge"), shutil.which("chrome"), shutil.which("chromium")):
        if path and Path(path).exists():
            return path
    return None


def export_pngs(index: Path, design: str = "FINAL"):
    from PIL import Image

    browser = find_browser()
    if browser is None:
        print("PNG export skipped: no Edge/Chrome found (set BROWSER_EXE)")
        return []
    FIGURES.mkdir(parents=True, exist_ok=True)
    scale = EXPORT_INCH * DPI / EXPORT_WIDTH_PX
    written = []
    with tempfile.TemporaryDirectory() as profile:
        for pid, name, height in PANELS:
            png = FIGURES / f"{pid}_{name}.png"
            url = index.resolve().as_uri() + f"#export={pid}&design={design}"
            subprocess.run([browser, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run", f"--user-data-dir={profile}",
                            f"--force-device-scale-factor={scale}", f"--window-size={EXPORT_WIDTH_PX},{height}", "--virtual-time-budget=10000",
                            f"--screenshot={png}", url], check=True, capture_output=True, timeout=120)
            with Image.open(png) as img:
                img.load()
                img.save(png, dpi=(DPI, DPI))
                written.append((png, img.size))
    return written


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--no-png", action="store_true", help="skip the PNG export")
    args = parser.parse_args()
    data = collect()
    html = HTML.replace("__ECHARTS__", VENDOR_JS.read_text(encoding="utf-8")).replace(
        "__DATA__", json.dumps(data, separators=(",", ":"), default=str).replace("</", "<\\/"))
    DASH.mkdir(exist_ok=True)
    index = DASH / "index.html"
    index.write_text(html, encoding="utf-8")
    print(f"DASHBOARD: {index.relative_to(ROOT.parent)} ({index.stat().st_size / 1e6:.1f} MB, designs {', '.join(data['order'])})")
    if not args.no_png:
        for png, size in export_pngs(index):
            print(f"  {png.relative_to(ROOT.parent)}  {size[0]}x{size[1]} px @ {DPI} dpi")


if __name__ == "__main__":
    main()
