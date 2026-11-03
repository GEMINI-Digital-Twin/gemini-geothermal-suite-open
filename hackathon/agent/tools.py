"""Tools the agent can call. Each returns a compact JSON-able dict.

The LLM decides *what* to run and *which* design to choose; every number
comes from these tools. Tools return metrics, never a winner. ``finish``
verifies the agent's choice against the stated objective (autonomous
verification) and returns a finding the agent must address.

Usage guidance lives in the tool descriptions (the tools' documentation),
identical for every model; the system prompt states goals only.
"""

import json
from dataclasses import asdict
from pathlib import Path

from hackathon.models import gemini_project as gp
from hackathon.models import subsurface as sub
from hackathon.models.config import REPO_ROOT, load_config
from hackathon.models.dispatch import Design, evaluate_design, load_demand
from hackathon.models.robustness import return_temperature_sensitivity, run_robustness
from hackathon.models.surface import SOURCES, SurfaceParams


def _r(x, n=2):
    if isinstance(x, (bool, int, str)) or x is None:
        return x
    if isinstance(x, float):
        return round(x, n)
    if isinstance(x, dict):
        return {k: _r(v, n) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_r(v, n) for v in x]
    try:
        return round(float(x), n)
    except (TypeError, ValueError):
        return x


MODEL_CARDS = {
    "wellhead_temperature": {
        "covers": "wellhead temperature from reservoir temperature, depth and flow",
        "method": "GEMINI DPDT marched upward in 25 segments, formation temperature per segment",
        "why_needed": "GEMINI takes wellhead temperature as a fixed boundary input",
    },
    "reservoir_inflow": {
        "covers": "productivity and injectivity from k, h, mu, skin and well spacing",
        "method": "GEMINI bottomhole_skin_dp (Darcy radial + skin) with r_e = spacing (DoubletCalc 1.4, Eq. 7)",
        "why_needed": "GEMINI's simulator needs PI as an input",
    },
    "brine_properties": {
        "covers": "brine density 1030 kg/m3 and viscosity 0.40 mPa s in GEMINI well models",
        "method": "subclass of GEMINI PVTConstantSTP swapped into the well models",
        "why_needed": "GEMINI uses pure-water constants",
    },
    "injector_friction_fix": {
        "covers": "injector wellhead pressure with friction against the flow",
        "method": "GEMINI DPDT with negative flow so friction opposes injection",
        "why_needed": "GEMINI's injector adds friction walking down with the flow (sign error)",
    },
    "absorption_chiller": {
        "covers": "brine-driven LiBr absorption cooling: 'rated' (DOE) or 'district-heating type' (CIBSE)",
        "method": "fixed COP 0.70; rated: inlet >= 80 C, brine drop <= 10 K; DH type: inlet >= 70 C, outlet >= 50 C",
        "why_needed": "GEMINI has no cooling model",
        "sources": [SOURCES["absorption_rated"], SOURCES["absorption_dh"]],
    },
    "electric_chiller": {
        "covers": "vapour-compression chiller for top-up and outage backup",
        "method": "fixed COP 8.6 at elevated chilled-water temperature",
        "why_needed": "GEMINI has no cooling model",
        "sources": [SOURCES["electric_chiller_cop"]],
    },
    "heat_pump": {
        "covers": "heat pump boosting the network to 100 C with brine as source",
        "method": "Lorenz COP, GEMINI HeatpumpBasic formula, eta 0.5",
        "why_needed": "GEMINI's heat pump model exists but is not registered in the simulator",
        "sources": [SOURCES["hp_eta_lorenz"]],
    },
    "annual_dispatch": {
        "covers": "365 daily energy balances, outages, constraint checks, economics (ThermoGIS)",
        "method": "per day: absorption -> direct HX -> CHP -> heat pump -> boiler",
        "why_needed": "GEMINI solves one steady operating point; no time series, no economics",
    },
}


WARNING_KEYWORDS = {  # words that count as addressing a warning in the justification
    "pvt_validity": ["pvt", "100 c", "100°c", "property range", "properties"],
    "n_minus_1": ["n-1", "n_minus_1", "trip", "one doublet", "redundan", "backup"],
}


class Session:
    """State shared by the tools during one agent run."""

    def __init__(self, run_dir):
        self.cfg = load_config()
        self.demand = load_demand(self.cfg)
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.loaded = set()
        self.candidates = {}
        self.designs = {}
        self.robustness = {}
        self.sensitivity = {}
        self.final = None
        self.verification_shown = set()

    # ----------------------------------------------------------------- tools
    def get_problem_brief(self):
        d, c = self.demand, self.cfg
        m = d.assign(month=d.date.dt.month).groupby("month")[["heat_mw", "cool_mw"]].mean()
        return _r({
            "objective": "Meet daily heating (100 C supply) and cooling (20 C supply) demand on all 365 "
                         "days at the lowest expected (P50) levelised cost, robust in >= 90% of "
                         "uncertainty samples; report P10/P50/P90 with P90 as the conservative case.",
            "demand": {
                "heat_peak_mw": float(d.heat_mw.max()), "heat_peak_date": f"{d.date[d.heat_mw.idxmax()]:%d %b}",
                "heat_gwh": float(d.heat_mw.sum() * 24 / 1000), "heat_min_mw": float(d.heat_mw.min()),
                "cool_peak_mw": float(d.cool_mw.max()), "cool_peak_date": f"{d.date[d.cool_mw.idxmax()]:%d %b}",
                "cool_gwh": float(d.cool_mw.sum() * 24 / 1000),
                "monthly_mean_heat_mw": [round(x, 1) for x in m.heat_mw],
                "monthly_mean_cool_mw": [round(x, 1) for x in m.cool_mw],
            },
            "reservoir": {"ref_depth_m": c.ref_depth_m, "gradient_c_per_km": c.gradient_c_per_m * 1000,
                          "surface_c": c.surface_temp_c, "ref_pressure_bar": c.ref_pressure_bar,
                          "permeability_md": c.raw["fact_sheet"]["reservoir"]["permeability_md"],
                          "thickness_m": c.thickness_m},
            "brine": {"density": c.rho, "viscosity_mpas": c.mu * 1e3, "cp": c.cp,
                      "glr_nm3_m3": c.glr, "gas": "80% CH4 / 20% CO2"},
            "hard_constraints": {"doublets": [c.n_min, c.n_max], "flow_m3h_per_doublet": [c.q_min, c.q_max],
                                 "max_brine_cooling_c": c.dt_brine_max, "pump_efficiency": c.pump_eff,
                                 "geothermal_operating_days_per_doublet": c.op_days,
                                 "system_must_meet_demand_days": 365,
                                 "thermal_breakthrough_min_years": c.lifetime_years},
            "design_variables": c.raw["design_variables"],
            "economics_note": "TNO ThermoGIS defaults used as they are; for comparing designs, not a forecast",
        })

    def inspect_gemini_capabilities(self):
        import gemini_simulator.registry as reg
        models_dir = REPO_ROOT / "src" / "gemini_model"
        packages = sorted(p.name for p in models_dir.iterdir()
                          if p.is_dir() and not p.name.startswith("_"))
        registered = sorted(reg.COMPONENT_REGISTRY)
        needs = {
            "doublet_wells_and_reservoir": ["producer_well", "injector_well"],
            "reservoir_inflow_with_skin": ["reservoir_bottomhole_skin"],
            "heat_exchanger": ["heat_exchanger"],
            "heat_pump": ["heatpump"],
            "boiler_and_chp_on_associated_gas": ["boiler", "chp"],
            "absorption_cooling": ["absorption_chiller"],
            "electric_chiller": ["chiller"],
            "annual_time_series_dispatch": ["dispatch"],
            "economics": ["economics"],
            "wellhead_temperature_from_reservoir": ["wellbore_heat_loss"],
        }
        status = {}
        for need, names in needs.items():
            in_reg = [n for n in names if n in registered]
            in_pkg = [n for n in names if n in packages]
            status[need] = ("registered in simulator" if in_reg else
                            "model exists, not registered" if in_pkg else "missing")
        return {"gemini_model_packages": packages, "simulator_registry": registered,
                "needs_vs_gemini": status,
                "known_issues": ["wellhead temperature is a boundary input",
                                 "pure-water PVT valid to 100 C",
                                 "simulator needs PI as input",
                                 "injector friction sign error (understates injector pressure)",
                                 "example ESP curve saturates near 240 m3/h",
                                 "template filters invalid above ~200 m3/h"],
                "supplementary_models_available": list(MODEL_CARDS)}

    def load_supplementary_model(self, name):
        if name not in MODEL_CARDS:
            return {"error": f"unknown model '{name}'", "available": list(MODEL_CARDS)}
        self.loaded.add(name)
        return {"loaded": name, **MODEL_CARDS[name], "now_loaded": sorted(self.loaded)}

    def assess_resource(self, depth_m, spacing_m=None):
        c = self.cfg
        spacing_m = spacing_m or c.well_spacing_m
        out = {"depth_m": depth_m, "spacing_m": spacing_m,
               "reservoir_temperature_c": sub.reservoir_temperature_c(c, depth_m),
               "reservoir_pressure_bar": sub.reservoir_pressure_bar(c, depth_m),
               "productivity_index_m3h_bar": sub.productivity_index_m3h_bar(c, spacing_m, c.skin_producer),
               "injectivity_index_m3h_bar": sub.productivity_index_m3h_bar(c, spacing_m, c.skin_injector),
               "per_doublet": []}
        for q in (50, 150, 300):
            d = sub.doublet_performance(c, depth_m, q, spacing_m)
            out["per_doublet"].append({
                "flow_m3h": q, "wellhead_t_c": d["wellhead_temperature_c"],
                "heat_at_40C_drop_mw": d["geothermal_heat_mw"], "pump_power_mw": d["total_pump_power_mw"],
                "assoc_gas_fuel_mw": d["gas_ch4_fuel_mw"],
                "breakthrough_years_at_this_flow": sub.thermal_breakthrough_years(c, spacing_m, q)})
        if out["reservoir_temperature_c"] > 100:
            out["warning"] = "above GEMINI's 100 C PVT range; constant brine properties used"
        return _r(out)

    def run_gemini_project(self, depth_m, target_flow_m3h, esp_stages=15):
        try:
            res, proj = gp.tune_esp_for_flow(self.cfg, depth_m, target_flow_m3h, esp_stages=esp_stages)
        except ValueError as exc:
            return {"error": str(exc),
                    "hint": "GEMINI's example ESP saturates near 240 m3/h; assess_resource uses "
                            "the brief's 70% pump for higher flows"}
        path = gp.save_project(proj, self.run_dir / f"gemini_project_{int(depth_m)}m_{int(target_flow_m3h)}.json")
        return _r({**res, "project_file": path,
                   "note": "native GEMINI project solve; injector uses GEMINI as-is (friction sign error)"})

    def evaluate_design(self, depth_m, n_doublets, spacing_m=None, max_flow_m3h=300,
                        outage="staggered", heating_return_c=None, hp_capacity_mw=0,
                        chiller_type="absorption_rated", sorption_capacity_mw=0,
                        elec_chiller_capacity_mw=0, boiler_capacity_mw=0, label=None):
        missing = []
        if "annual_dispatch" not in self.loaded:
            missing.append("annual_dispatch")
        if hp_capacity_mw > 0 and "heat_pump" not in self.loaded:
            missing.append("heat_pump")
        if chiller_type.startswith("absorption") and sorption_capacity_mw > 0 \
                and "absorption_chiller" not in self.loaded:
            missing.append("absorption_chiller")
        if elec_chiller_capacity_mw > 0 and "electric_chiller" not in self.loaded:
            missing.append("electric_chiller")
        if missing:
            return {"error": "design uses models that are not in GEMINI and not loaded yet",
                    "load_first": missing}
        design = Design(depth_m=depth_m, n_doublets=int(n_doublets), max_flow_m3h=max_flow_m3h,
                        spacing_m=spacing_m, outage=outage, heating_return_c=heating_return_c,
                        surface=SurfaceParams(hp_capacity_mw=hp_capacity_mw, chiller_type=chiller_type,
                                              sorption_capacity_mw=sorption_capacity_mw,
                                              elec_chiller_capacity_mw=elec_chiller_capacity_mw,
                                              boiler_capacity_mw=boiler_capacity_mw))
        res = evaluate_design(design)
        cid = f"D{len(self.candidates) + 1}"
        self.designs[cid] = design
        self.candidates[cid] = {"label": label, **{k: res[k] for k in ("design", "kpis", "economics",
                                                                      "violations")}}
        res["daily"].to_csv(self.run_dir / f"{cid}_daily.csv", index=False)
        k = res["kpis"]
        # compact result (P3): key KPIs only, short names, 1 decimal, to keep prompts small
        keep = {"lcoh": "lcoh_eur_per_mwh", "capex_meur": "capex_total_meur",
                "heat_direct": "heat_direct_gwh", "heat_hp": "heat_hp_gwh", "heat_chp": "heat_chp_gwh",
                "heat_boiler": "heat_boiler_ng_gwh", "heat_unmet": "heat_unmet_gwh",
                "cool_absorption": "cool_sorption_gwh", "cool_electric": "cool_electric_gwh",
                "cool_unmet": "cool_unmet_gwh", "net_elec": "net_electricity_gwh",
                "breakthrough_yr": "breakthrough_years"}
        return _r({"id": cid, "kpis_gwh_eur_mwh": {a: k[b] for a, b in keep.items()},
                   "violations": [f"{v['severity']}:{v['constraint']}: {v['detail']}"
                                  for v in res["violations"] if v["severity"] != "info"]}, 1)

    def robustness_check(self, candidate_id, n_samples=100):
        if candidate_id not in self.designs:
            return {"error": f"unknown candidate {candidate_id}", "known": list(self.designs)}
        r = run_robustness(self.designs[candidate_id], n_samples=int(n_samples))
        self.robustness[candidate_id] = r
        p = lambda d: [d["P10"], d["P50"], d["P90"]]
        return _r({"id": candidate_id, "feasible_share": r["feasible_share"], "robust": r["robust"],
                   "failures": r["failure_counts"], "P10_P50_P90 (P90 conservative)": {
                       "lcoh": p(r["lcoh_eur_per_mwh"]), "net_elec_gwh": p(r["net_electricity_gwh"]),
                       "geo_heat_share_pct": [100 * x for x in p(r["heat_share_geothermal"])],
                       "breakthrough_yr": p(r["breakthrough_years"])}}, 1)

    def return_temperature_sensitivity(self, candidate_id):
        if candidate_id not in self.designs:
            return {"error": f"unknown candidate {candidate_id}", "known": list(self.designs)}
        r = return_temperature_sensitivity(self.designs[candidate_id])
        self.sensitivity[candidate_id] = r
        return _r({"id": candidate_id, "return_c: [lcoh, net_elec_gwh, hard_violations]": {
            x["heating_return_c"]: [x["lcoh_eur_per_mwh"], x["net_electricity_gwh"],
                                    x["hard_violations"]] for x in r}}, 1)

    def compare_candidates(self, candidate_ids=None):
        ids = candidate_ids or list(self.candidates)
        rows = []
        for cid in ids:
            c = self.candidates.get(cid)
            if not c:
                continue
            d, k, s = c["design"], c["kpis"], c["design"]["surface"]
            rb = self.robustness.get(cid)
            rows.append(_r({
                "id": cid, "label": c["label"], "depth_m": d["depth_m"], "doublets": d["n_doublets"],
                "spacing_m": d["spacing_m"], "heating_return_c": d["heating_return_c"],
                "hp_mw": s["hp_capacity_mw"], "chiller": s["chiller_type"],
                "sorption_mw": s["sorption_capacity_mw"], "elec_chiller_mw": s["elec_chiller_capacity_mw"],
                "boiler_mw": s["boiler_capacity_mw"],
                "hard_violations": sum(v["severity"] == "hard" for v in c["violations"]),
                "warnings": [v["constraint"] for v in c["violations"] if v["severity"] == "warning"],
                "lcoh_base": k["lcoh_eur_per_mwh"],
                "lcoh_P10_P50_P90": [rb["lcoh_eur_per_mwh"][p] for p in ("P10", "P50", "P90")] if rb else None,
                "feasible_share": rb["feasible_share"] if rb else None,
                "net_elec_gwh": k["net_electricity_gwh"], "nat_gas_gwh": k["natural_gas_gwh"],
                "geo_heat_share": k["heat_share_geothermal_direct_and_hp"],
                "geo_cool_share": k["geothermal_cool_share"]}))
        return {"candidates": rows,
                "note": "metrics only; the choice and its justification are yours"}

    def finish(self, candidate_id, justification, acknowledge_verification=False):
        if candidate_id not in self.candidates:
            return {"error": f"unknown candidate {candidate_id}", "known": list(self.candidates)}
        hard = [v for v in self.candidates[candidate_id]["violations"] if v["severity"] == "hard"]
        problems = []
        if hard:
            problems.append(f"chosen design has hard violations: {[v['constraint'] for v in hard]}")
        if len(self.candidates) < 3:
            problems.append(f"only {len(self.candidates)} alternatives evaluated; at least 3 required")
        if candidate_id not in self.robustness:
            problems.append("run robustness_check on the chosen design first")
        elif not self.robustness[candidate_id]["robust"]:
            problems.append(f"chosen design is feasible in only "
                            f"{self.robustness[candidate_id]['feasible_share']:.0%} of samples (< 90%)")
        if candidate_id not in self.sensitivity:
            problems.append("run return_temperature_sensitivity on the chosen design first")
        if not any(ch.isdigit() for ch in justification) or "D" not in justification:
            problems.append("justification must cite candidate ids and numbers from the tools")
        # F2: every warning on the chosen design must be addressed in the justification
        text = justification.lower()
        for v in self.candidates[candidate_id]["violations"]:
            if v["severity"] == "warning":
                words = WARNING_KEYWORDS.get(v["constraint"], [v["constraint"]])
                if not any(w.lower() in text for w in words):
                    problems.append(f"justification does not address the warning "
                                    f"'{v['constraint']}': {v['detail']}")
        if problems:
            return {"accepted": False, "problems": problems}

        # verification against the objective
        findings = []
        chosen_base = self.candidates[candidate_id]["kpis"]["lcoh_eur_per_mwh"]
        # F1: cheaper feasible candidates that were never robustness-checked
        unchecked = sorted(
            (c["kpis"]["lcoh_eur_per_mwh"], cid) for cid, c in self.candidates.items()
            if cid != candidate_id and cid not in self.robustness
            and not any(v["severity"] == "hard" for v in c["violations"])
            and c["kpis"]["lcoh_eur_per_mwh"] < chosen_base)
        if unchecked:
            findings.append(
                "verification: feasible candidates with a lower base LCOH than "
                f"{candidate_id} ({chosen_base:.1f} EUR/MWh) were not robustness-checked: "
                + ", ".join(f"{cid} ({l:.1f})" for l, cid in unchecked))
        # lowest P50 LCOH among robust, feasible candidates
        robust = {cid: r["lcoh_eur_per_mwh"]["P50"] for cid, r in self.robustness.items()
                  if r["robust"] and not any(v["severity"] == "hard"
                                             for v in self.candidates[cid]["violations"])}
        best = min(robust, key=robust.get)
        if best != candidate_id:
            findings.append(f"verification: {best} has a lower P50 LCOH ({robust[best]:.1f} EUR/MWh) "
                            f"than {candidate_id} ({robust[candidate_id]:.1f}) among robust candidates")
        finding = "; ".join(findings) or None
        if findings and not acknowledge_verification:
            return {"accepted": False, "verification_findings": findings,
                    "next": "run robustness_check on the listed candidates and revise your choice if "
                            "needed, or call finish again with acknowledge_verification=true and "
                            "explain why your choice is better"}
        self.final = {"candidate_id": candidate_id, "justification": justification,
                      "verification_finding": finding,
                      "robustness": self.robustness[candidate_id],
                      "return_temperature_sensitivity": self.sensitivity[candidate_id],
                      **self.candidates[candidate_id]}
        with open(self.run_dir / "final_design.json", "w", encoding="utf-8") as f:
            json.dump(self.final, f, indent=2, default=str)
        return {"accepted": candidate_id, "verification_finding": finding}


def _fn(name, desc, props, required=()):
    return {"type": "function", "function": {
        "name": name, "description": desc,
        "parameters": {"type": "object", "properties": props, "required": list(required)}}}


NUM = {"type": "number"}
TOOL_SCHEMAS = [
    _fn("get_problem_brief", "Objective, demand statistics, reservoir and brine data, hard constraints and "
        "the design variables you may choose (with bounds). A good first call.", {}),
    _fn("inspect_gemini_capabilities", "Lists GEMINI's models and simulator registry and compares them with "
        "what this design needs. Use it to find which modelling capabilities are missing before evaluating "
        "designs.", {}),
    _fn("load_supplementary_model", "Connects one model that GEMINI lacks and returns its model card (method, "
        "why needed, sources). evaluate_design refuses to run until every model it needs is loaded.",
        {"name": {"type": "string", "enum": list(MODEL_CARDS)}}, ["name"]),
    _fn("assess_resource", "Reservoir temperature and pressure, productivity and injectivity, and per-doublet "
        "wellhead temperature, heat at the 40 C brine drop, pump power, associated gas and breakthrough "
        "time at 50/150/300 m3/h, for a depth and (optional) well spacing.",
        {"depth_m": NUM, "spacing_m": NUM}, ["depth_m"]),
    _fn("run_gemini_project", "Configures and solves a native GEMINI project .json for one doublet at a target "
        "flow (ESP frequency tuned). Use it to verify a doublet against the GEMINI simulator; max ~240 m3/h.",
        {"depth_m": NUM, "target_flow_m3h": NUM, "esp_stages": {"type": "integer"}},
        ["depth_m", "target_flow_m3h"]),
    _fn("evaluate_design", "Runs a full design over 365 days: KPIs, LCOH (ThermoGIS economics), breakthrough "
        "time and constraint violations. Returns which supplementary models to load if any are missing.",
        {"depth_m": NUM, "n_doublets": {"type": "integer"}, "spacing_m": NUM, "max_flow_m3h": NUM,
         "outage": {"type": "string", "enum": ["staggered", "simultaneous"]},
         "heating_return_c": NUM, "hp_capacity_mw": NUM,
         "chiller_type": {"type": "string", "enum": ["absorption_rated", "absorption_dh", "electric"]},
         "sorption_capacity_mw": NUM, "elec_chiller_capacity_mw": NUM, "boiler_capacity_mw": NUM,
         "label": {"type": "string"}},
        ["depth_m", "n_doublets"]),
    _fn("robustness_check", "Monte Carlo over the sourced uncertainty ranges for one evaluated candidate. "
        "Returns feasible share (robust if >= 90%) and P10/P50/P90 (P90 = conservative) for LCOH, net "
        "electricity, gas, geothermal share and breakthrough. Takes about a minute for 100 samples.",
        {"candidate_id": {"type": "string"}, "n_samples": {"type": "integer"}}, ["candidate_id"]),
    _fn("return_temperature_sensitivity", "Re-runs one candidate at heating return temperatures 45-70 C and "
        "reports LCOH, electricity and violations for each.",
        {"candidate_id": {"type": "string"}}, ["candidate_id"]),
    _fn("compare_candidates", "Side-by-side metrics of evaluated candidates (and their robustness, if run). "
        "Returns metrics only, not a recommendation.",
        {"candidate_ids": {"type": "array", "items": {"type": "string"}}}),
    _fn("finish", "Submits the final design with your justification. Accepted only if: at least 3 alternatives "
        "were evaluated, the chosen design has no hard violation, robustness_check shows >= 90% feasible, "
        "return_temperature_sensitivity was run on it, the justification cites candidate ids and numbers, and "
        "it addresses every warning on the chosen design. Then verifies the choice against the objective: it "
        "flags robust candidates with a lower P50 LCOH and feasible candidates with a lower base LCOH that "
        "were never robustness-checked, and asks you to check them and revise, or explain.",
        {"candidate_id": {"type": "string"}, "justification": {"type": "string"},
         "acknowledge_verification": {"type": "boolean"}},
        ["candidate_id", "justification"]),
]


def call_tool(session, name, args):
    """Dispatch a tool call; errors come back as data so the agent can recover."""
    fn = getattr(session, name, None)
    if fn is None or name.startswith("_"):
        return {"error": f"unknown tool {name}"}
    try:
        return fn(**(args or {}))
    except TypeError as exc:
        return {"error": f"bad arguments for {name}: {exc}"}
    except Exception as exc:  # keep the loop alive; the agent sees the error
        return {"error": f"{type(exc).__name__}: {exc}"}
