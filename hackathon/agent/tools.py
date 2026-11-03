"""Tools the agent can call. Each returns a compact JSON-able dict.

The LLM decides *what* to run; every number comes from these tools, never from
the LLM. Tool results are rounded and trimmed to keep prompts small.

Gap handling is explicit: ``inspect_gemini_capabilities`` reads GEMINI's own
registry and model folders, and ``evaluate_design`` refuses to use a
non-GEMINI model (chillers, annual dispatch) until the agent has loaded it
with ``load_supplementary_model``. That makes "identify the missing model,
then connect one" a visible step in every transcript.
"""

import json
from pathlib import Path

from hackathon.models import gemini_project as gp
from hackathon.models import subsurface as sub
from hackathon.models.config import REPO_ROOT, load_config
from hackathon.models.dispatch import Design, evaluate_design, load_demand
from hackathon.models.surface import SurfaceParams


def _r(x, n=2):
    if isinstance(x, (bool, int, str)) or x is None:
        return x
    if isinstance(x, float):
        return round(x, n)
    if isinstance(x, dict):
        return {k: _r(v, n) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_r(v, n) for v in x]
    try:  # numpy scalars
        return round(float(x), n)
    except (TypeError, ValueError):
        return x


MODEL_CARDS = {
    "wellhead_temperature": {
        "covers": "wellhead temperature from reservoir T, depth and flow",
        "method": "GEMINI DPDT marched upward in 25 segments; formation T per segment as ambient",
        "why_needed": "GEMINI takes wellhead temperature as a fixed boundary input",
        "validity": "steady heat loss with GEMINI's fixed U = 10 W/m2K (conservative)",
    },
    "productivity_index": {
        "covers": "PI and injectivity from k, h, mu",
        "method": "Darcy radial steady state, r_e = half well spacing, skin from config",
        "why_needed": "GEMINI needs PI as an input",
        "validity": "homogeneous reservoir, single phase",
    },
    "brine_properties": {
        "covers": "brine density 1030, viscosity 0.40 mPa s, cp from config",
        "method": "subclass of GEMINI PVTConstantSTP swapped into the well models",
        "why_needed": "GEMINI uses pure-water constants",
        "validity": "constant properties, no gas in wellbore",
    },
    "injector_friction_fix": {
        "covers": "injector wellhead pressure with friction against the flow",
        "method": "GEMINI DPDT with negative flow so Darcy-Weisbach friction opposes injection",
        "why_needed": "GEMINI injector adds friction walking down with the flow (sign error)",
        "validity": "same as GEMINI DPDT",
    },
    "sorption_chiller": {
        "covers": "absorption (LiBr single effect) or adsorption cooling driven by brine",
        "method": "fixed COP, minimum drive inlet, max generator temperature drop",
        "why_needed": "GEMINI has no cooling model",
        "validity": "daily average; parameters DEFAULT until confirmed from references",
    },
    "electric_chiller": {
        "covers": "vapour-compression chiller for top-up and outage backup",
        "method": "COP = 0.5 x Carnot between chilled water and 38 C condenser, max 7",
        "why_needed": "GEMINI has no cooling model",
        "validity": "daily average",
    },
    "heat_pump": {
        "covers": "heat pump boosting the network to 100 C with brine as source",
        "method": "Lorenz COP (GEMINI HeatpumpBasic formula), cross-checked with GEMINI's model",
        "why_needed": "GEMINI's heat pump exists but is not registered in the simulator",
        "validity": "eta_lorenz 0.5, COP capped at 7",
    },
    "annual_dispatch": {
        "covers": "365 daily energy balances, outages, constraint checks",
        "method": "per day: chiller -> direct HX -> CHP -> heat pump -> boiler; lowest flow within 1% of least backup",
        "why_needed": "GEMINI solves one steady operating point; no time series",
        "validity": "daily averages; no intra-day peaks or storage",
    },
}
REQUIRES = {
    "annual_dispatch": "always",
    "heat_pump": "hp_capacity_mw > 0",
    "sorption_chiller": "chiller_type is absorption/adsorption and sorption_capacity_mw > 0",
    "electric_chiller": "elec_chiller_capacity_mw > 0",
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
        self.final = None

    # ----------------------------------------------------------------- tools
    def get_problem_brief(self):
        d, c = self.demand, self.cfg
        m = d.assign(month=d.date.dt.month).groupby("month")[["heat_mw", "cool_mw"]].mean()
        return _r({
            "objective": "Meet daily heating (100 C supply) and cooling (20 C supply) demand on all "
                         "365 days with deep geothermal as the main source; compare alternatives.",
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
                          "permeability_md": 200, "thickness_m": c.thickness_m},
            "brine": {"density": c.rho, "viscosity_mpas": c.mu * 1e3, "cp": c.cp,
                      "glr_nm3_m3": c.glr, "gas": "80% CH4 / 20% CO2"},
            "hard_constraints": {"doublets": [c.n_min, c.n_max], "flow_m3h_per_doublet": [c.q_min, c.q_max],
                                 "max_brine_cooling_k": c.dt_brine_max, "pump_efficiency": c.pump_eff,
                                 "geothermal_operating_days_per_doublet": c.op_days,
                                 "system_must_meet_demand_days": 365},
            "assumptions_status": c.assumption_status,
            "design_variables": c.raw["design_variables"],
        })

    def inspect_gemini_capabilities(self):
        import gemini_simulator.registry as reg
        models_dir = REPO_ROOT / "src" / "gemini_model"
        packages = sorted(p.name for p in models_dir.iterdir()
                          if p.is_dir() and not p.name.startswith("_"))
        registered = sorted(reg.COMPONENT_REGISTRY)
        needs = {
            "doublet_wells_and_reservoir": ["producer_well", "injector_well"],
            "heat_exchanger": ["heat_exchanger"],
            "heat_pump": ["heatpump"],
            "boiler_or_chp_on_associated_gas": ["boiler", "chp"],
            "cooling_absorption_or_adsorption": ["absorption_chiller", "adsorption_chiller"],
            "cooling_electric_chiller": ["chiller"],
            "thermal_storage": ["storage"],
            "annual_time_series_dispatch": ["dispatch"],
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
                                 "productivity index is an input",
                                 "injector friction sign error (understates injector pressure)",
                                 "example ESP curve saturates near 240 m3/h"],
                "supplementary_models_available": list(MODEL_CARDS)}

    def load_supplementary_model(self, name):
        if name not in MODEL_CARDS:
            return {"error": f"unknown model '{name}'", "available": list(MODEL_CARDS)}
        self.loaded.add(name)
        return {"loaded": name, **MODEL_CARDS[name], "now_loaded": sorted(self.loaded)}

    def assess_resource(self, depth_m):
        c = self.cfg
        out = {"depth_m": depth_m,
               "reservoir_temperature_c": sub.reservoir_temperature_c(c, depth_m),
               "reservoir_pressure_bar": sub.reservoir_pressure_bar(c, depth_m),
               "productivity_index_m3h_bar": sub.productivity_index_m3h_bar(c),
               "per_doublet": []}
        for q in (50, 150, 300):
            d = sub.doublet_performance(c, depth_m, q)
            out["per_doublet"].append({
                "flow_m3h": q, "wellhead_t_c": d["wellhead_temperature_c"],
                "heat_at_40K_mw": d["geothermal_heat_mw"], "pump_power_mw": d["total_pump_power_mw"],
                "injector_whp_bar": d["injector_wellhead_pressure_bar"],
                "assoc_gas_fuel_mw": d["gas_ch4_fuel_mw"]})
        if out["reservoir_temperature_c"] > 100:
            out["warning"] = "above GEMINI's 100 C PVT range; constant brine properties used"
        return _r(out)

    def run_gemini_project(self, depth_m, target_flow_m3h, esp_stages=15):
        try:
            res, proj = gp.tune_esp_for_flow(self.cfg, depth_m, target_flow_m3h, esp_stages=esp_stages)
        except ValueError as exc:
            return {"error": str(exc),
                    "hint": "GEMINI's example ESP saturates near 240 m3/h; use assess_resource "
                            "(generic 70% pump) for higher flows"}
        path = gp.save_project(proj, self.run_dir / f"gemini_project_{int(depth_m)}m_{int(target_flow_m3h)}.json")
        return _r({**res, "project_file": path,
                   "note": "native GEMINI project solve; injector uses GEMINI as-is (friction sign error)"})

    def evaluate_design(self, depth_m, n_doublets, max_flow_m3h=300, outage="staggered",
                        heating_return_c=None, hp_capacity_mw=0, chiller_type="absorption_single_effect",
                        sorption_capacity_mw=0, elec_chiller_capacity_mw=0, boiler_capacity_mw=0,
                        label=None):
        missing = []
        if "annual_dispatch" not in self.loaded:
            missing.append("annual_dispatch")
        if hp_capacity_mw > 0 and "heat_pump" not in self.loaded:
            missing.append("heat_pump")
        if chiller_type != "electric" and sorption_capacity_mw > 0 and "sorption_chiller" not in self.loaded:
            missing.append("sorption_chiller")
        if elec_chiller_capacity_mw > 0 and "electric_chiller" not in self.loaded:
            missing.append("electric_chiller")
        if missing:
            return {"error": "design uses models that are not in GEMINI and not loaded yet",
                    "load_first": missing}
        design = Design(depth_m=depth_m, n_doublets=int(n_doublets), max_flow_m3h=max_flow_m3h,
                        outage=outage, heating_return_c=heating_return_c,
                        surface=SurfaceParams(hp_capacity_mw=hp_capacity_mw, chiller_type=chiller_type,
                                              sorption_capacity_mw=sorption_capacity_mw,
                                              elec_chiller_capacity_mw=elec_chiller_capacity_mw,
                                              boiler_capacity_mw=boiler_capacity_mw))
        res = evaluate_design(design)
        cid = f"D{len(self.candidates) + 1}"
        self.candidates[cid] = {"label": label, **{k: res[k] for k in ("design", "kpis", "violations")}}
        res["daily"].to_csv(self.run_dir / f"{cid}_daily.csv", index=False)
        k = res["kpis"]
        keep = ["heat_direct_gwh", "heat_hp_gwh", "heat_chp_gwh", "heat_boiler_ng_gwh", "heat_unmet_gwh",
                "cool_sorption_gwh", "cool_electric_gwh", "cool_unmet_gwh", "net_electricity_gwh",
                "natural_gas_gwh", "heat_share_geothermal_direct_and_hp", "geothermal_cool_share",
                "max_hp_load_mw", "max_boiler_load_mw", "max_sorption_load_mw",
                "max_elec_chiller_load_mw", "mean_hp_cop"]
        return _r({"candidate_id": cid, "label": label, "kpis": {x: k[x] for x in keep},
                   "outage_starts_day_of_year": res["design"]["outage_starts"],
                   "violations": [{x: v[x] for x in ("severity", "constraint", "detail")}
                                  for v in res["violations"]]})

    def compare_candidates(self, candidate_ids=None):
        ids = candidate_ids or list(self.candidates)
        rows = []
        for cid in ids:
            c = self.candidates.get(cid)
            if not c:
                continue
            d, k = c["design"], c["kpis"]
            s = d["surface"]
            rows.append(_r({
                "id": cid, "label": c["label"], "depth_m": d["depth_m"], "doublets": d["n_doublets"],
                "hp_mw": s["hp_capacity_mw"], "sorption_mw": s["sorption_capacity_mw"],
                "chiller": s["chiller_type"], "elec_chiller_mw": s["elec_chiller_capacity_mw"],
                "boiler_mw": s["boiler_capacity_mw"],
                "hard_violations": sum(v["severity"] == "hard" for v in c["violations"]),
                "warnings": [v["constraint"] for v in c["violations"] if v["severity"] == "warning"],
                "net_elec_gwh": k["net_electricity_gwh"], "nat_gas_gwh": k["natural_gas_gwh"],
                "geo_heat_share": k["heat_share_geothermal_direct_and_hp"],
                "geo_cool_share": k["geothermal_cool_share"]}))
        return {"candidates": rows}

    def finish(self, candidate_id, justification):
        if candidate_id not in self.candidates:
            return {"error": f"unknown candidate {candidate_id}", "known": list(self.candidates)}
        hard = [v for v in self.candidates[candidate_id]["violations"] if v["severity"] == "hard"]
        if hard:
            return {"error": "final design still has hard violations", "violations": hard}
        if len(self.candidates) < 3:
            return {"error": "compare at least 3 alternatives before finishing",
                    "evaluated": len(self.candidates)}
        self.final = {"candidate_id": candidate_id, "justification": justification,
                      **self.candidates[candidate_id]}
        with open(self.run_dir / "final_design.json", "w", encoding="utf-8") as f:
            json.dump(self.final, f, indent=2, default=str)
        return {"accepted": candidate_id}


def _fn(name, desc, props, required=()):
    return {"type": "function", "function": {
        "name": name, "description": desc,
        "parameters": {"type": "object", "properties": props, "required": list(required)}}}


NUM = {"type": "number"}
TOOL_SCHEMAS = [
    _fn("get_problem_brief", "Demand statistics, reservoir and brine data, hard constraints, "
        "design variable ranges and assumption status.", {}),
    _fn("inspect_gemini_capabilities", "List GEMINI's models and simulator registry and compare them "
        "with what this design needs. Use it to find missing modelling capabilities.", {}),
    _fn("load_supplementary_model", "Connect one model that GEMINI lacks. Returns its model card "
        "(method, why needed, validity).",
        {"name": {"type": "string", "enum": list(MODEL_CARDS)}}, ["name"]),
    _fn("assess_resource", "Reservoir T and P, PI, and per-doublet wellhead T, heat at the 40 K cap, "
        "pump power and associated gas at 50/150/300 m3/h for a well depth.",
        {"depth_m": NUM}, ["depth_m"]),
    _fn("run_gemini_project", "Configure and solve a native GEMINI project .json for one doublet at a "
        "target flow (ESP frequency tuned). For verification against GEMINI; max ~240 m3/h.",
        {"depth_m": NUM, "target_flow_m3h": NUM, "esp_stages": {"type": "integer"}},
        ["depth_m", "target_flow_m3h"]),
    _fn("evaluate_design", "Run a full design over 365 days. Returns KPIs and constraint violations.",
        {"depth_m": NUM, "n_doublets": {"type": "integer"}, "max_flow_m3h": NUM,
         "outage": {"type": "string", "enum": ["staggered", "simultaneous"]},
         "heating_return_c": NUM, "hp_capacity_mw": NUM,
         "chiller_type": {"type": "string", "enum": ["absorption_single_effect", "adsorption", "electric"]},
         "sorption_capacity_mw": NUM, "elec_chiller_capacity_mw": NUM, "boiler_capacity_mw": NUM,
         "label": {"type": "string"}},
        ["depth_m", "n_doublets"]),
    _fn("compare_candidates", "Side-by-side table of evaluated designs.",
        {"candidate_ids": {"type": "array", "items": {"type": "string"}}}),
    _fn("finish", "Submit the final design with the reasoning for choosing it over the alternatives.",
        {"candidate_id": {"type": "string"}, "justification": {"type": "string"}},
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
