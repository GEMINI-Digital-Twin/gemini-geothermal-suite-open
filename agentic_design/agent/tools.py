"""Tools the agent can call. Every number the agent reports must come from here.

Design rules (they matter for grading and for a small local model):
* outputs are compact and already in report units (GWh, kt, %, degC, m3/h),
  so the model copies numbers instead of converting them (fewer errors,
  fewer tokens, and the claim checker can match them);
* every evaluation is logged to long-term memory;
* schemas carry bounds, so impossible arguments are rejected before running.
"""

import dataclasses
import re

import numpy as np

from agentic_design.annual import PlantDesign, run_year
from agentic_design.checks import check
from agentic_design.config import CHALLENGE, Assumptions, load_demand, reservoir_pressure_bar, reservoir_temperature_c
from agentic_design.verify import verify_days
from agentic_design.wells import WellDesign

# Assumptions the agent may change (with a reason and a source). Others are fixed in code.
EDITABLE_ASSUMPTIONS = {
    "heating_return_temperature_c": (35.0, 75.0, "District heating return temperature (not given by the challenge)"),
    "electricity_co2_kg_kwh": (0.0, 0.8, "Grid electricity CO2 factor"),
    "boiler_efficiency": (0.7, 1.0, "Gas boiler efficiency on LHV"),
    "maintenance_days_per_doublet": (0, 60, "Days each doublet is offline per year"),
    "well_heat_transfer_u_w_m2k": (1.0, 30.0, "Well heat-loss coefficient (GEMINI default 10)"),
    "cooling_return_temperature_c": (21.0, 32.0, "Cooling network return temperature (not given by the challenge)"),
    "cooling_water_temperature_c": (20.0, 40.0, "Chiller heat-rejection (dry cooler) water temperature"),
    "heat_pump_eta_lorenz": (0.3, 0.7, "Heat pump Lorenz efficiency (GEMINI default 0.5)"),
}


def _r(x, nd=2):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), nd)


class ToolBox:
    def __init__(self, memory, assumptions: Assumptions = None):
        self.memory = memory
        self.a = assumptions or Assumptions()
        for k, v in memory.assumption_overrides().items():  # long-term memory applied at start
            if k in EDITABLE_ASSUMPTIONS:
                setattr(self.a, k, type(getattr(self.a, k))(v))
        self.demand = load_demand()
        self._daily = {}  # name -> daily DataFrame (session cache)

    # ------------------------------------------------------------------ info
    def get_challenge_inputs(self):
        c = CHALLENGE
        return {
            "reservoir": {"midpoint_depth_m": c["reservoir_midpoint_depth_m"], "thickness_m": c["reservoir_gross_thickness_m"],
                          "gradient_C_per_km": c["geothermal_gradient_c_per_km"], "surface_temperature_C": c["surface_temperature_c"],
                          "pressure_bar": c["reservoir_pressure_bar"], "permeability_mD": c["permeability_md"],
                          "temperature_at_2500m_C": reservoir_temperature_c(2500)},
            "brine": {"density_kg_m3": c["brine_density_kg_m3"], "viscosity_mPa_s": c["brine_viscosity_pa_s"] * 1e3,
                      "gas_liquid_ratio_Nm3_per_m3": c["gas_liquid_ratio_nm3_per_m3"], "gas_CH4_pct": 80, "gas_CO2_pct": 20},
            "constraints": {"doublets": "1-3", "flow_m3h_per_doublet_min": c["min_flow_m3h_per_doublet"],
                            "flow_m3h_per_doublet_max": c["max_flow_m3h_per_doublet"], "max_brine_cooling_C": c["max_brine_cooling_c"],
                            "pump_efficiency_pct": 70, "max_operating_days_per_doublet": c["max_operating_days_per_doublet"],
                            "production_equals_injection": True},
            "supply_temperature_C": {"heating": c["heating_supply_temperature_c"], "cooling": c["cooling_supply_temperature_c"]},
            "not_given_by_challenge": ["heating return temperature", "cooling network return temperature", "costs"],
        }

    def get_demand_summary(self):
        d = self.demand
        h, c = d["heating_mw"], d["cooling_mw"]
        m = d.groupby(d["date"].dt.month)[["heating_mw", "cooling_mw"]].mean()
        return {
            "heating": {"annual_GWh": _r(h.sum() * 24 / 1e3), "peak_MW": _r(h.max()), "peak_date": str(d.loc[h.idxmax(), "date"].date()),
                        "min_MW": _r(h.min()), "monthly_mean_MW": [_r(x, 1) for x in m["heating_mw"]]},
            "cooling": {"annual_GWh": _r(c.sum() * 24 / 1e3), "peak_MW": _r(c.max()), "peak_date": str(d.loc[c.idxmax(), "date"].date()),
                        "days_with_demand": int((c > 0).sum()), "monthly_mean_MW": [_r(x, 1) for x in m["cooling_mw"]]},
            "resolution": "daily averages, 365 days of 2027",
        }

    def list_assumptions(self):
        return {k: {"value": getattr(self.a, k), "meaning": EDITABLE_ASSUMPTIONS[k][2],
                    "allowed_range": list(EDITABLE_ASSUMPTIONS[k][:2])} for k in EDITABLE_ASSUMPTIONS}

    def set_assumption(self, name, value, reason, source):
        if name not in EDITABLE_ASSUMPTIONS:
            return {"error": f"'{name}' is not editable. Editable: {sorted(EDITABLE_ASSUMPTIONS)}"}
        lo, hi, meaning = EDITABLE_ASSUMPTIONS[name]
        if source == "organisers":
            return {"error": f"The organisers did NOT specify '{meaning}' (see get_challenge_inputs: not_given_by_challenge). "
                             "Do not attribute a value to them. Ask the user for the value, or propose a typical value "
                             "with source='literature' and state clearly that it is an assumption."}
        if source == "literature" and len(str(reason).strip()) < 15:
            return {"error": "source='literature' needs a reason that says where the typical value comes from."}
        if not lo <= float(value) <= hi:
            return {"error": f"{name}={value} outside allowed range {lo}-{hi}"}
        old = getattr(self.a, name)
        setattr(self.a, name, type(old)(value))
        self.memory.record_assumption(name, old, value, reason, source)
        self._daily.clear()
        out = {"ok": True, "name": name, "old": old, "new": value,
               "note": "Earlier design results used the old value. Re-evaluate designs: evaluate_design then reports "
                       "the change per KPI for the same design."}
        if source == "literature":
            out["disclose"] = f"{name}={value} is an ASSUMPTION, not given by the organisers or the user. Say so in the answer."
        return out

    def list_models(self):
        return {
            "available_from_GEMINI": ["reservoir inflow (IPR)", "well pressure/temperature (DPDT)", "separator/degasser",
                                       "filter", "heat exchanger (effectiveness-NTU)", "gas boiler", "CHP",
                                       "heat pump (Lorenz; GEMINI's HeatpumpBasic equations)", "injection pump", "mixer/splitter"],
            "added_by_us": ["absorption chiller (characteristic equation, new GEMINI model)",
                            "electric chiller (Carnot fraction, new GEMINI model)", "producer at fixed flow",
                            "injector with corrected friction sign", "annual daily dispatch (brine order chosen daily)",
                            "constraint checker", "GEMINI cross-check"],
            "design_options_in_evaluate_design": ["doublets 1-3", "depth", "well diameter", "ESP depth", "heat_pump_mw",
                                                   "absorption_chiller_mw", "electric_chiller_mw"],
            "missing": {"thermal storage": "no model", "costs": "no model (CO2 is the objective)",
                        "free cooling with ambient air": "no model (no ambient temperature data given)"},
        }

    # ------------------------------------------------------------------ design evaluation
    @staticmethod
    def canonical_name(n_doublets, depth_m, well_inner_diameter_m=0.20, esp_depth_m=650.0,
                       heat_pump_mw=0.0, absorption_chiller_mw=0.0, electric_chiller_mw=0.0):
        """Name encodes every non-default parameter, so a changed design can never reuse an old name."""
        name = f"{int(n_doublets)}x{int(round(depth_m))}m"
        if abs(float(well_inner_diameter_m) - 0.20) > 1e-9:
            name += f"_ID{float(well_inner_diameter_m):.2f}"
        if abs(float(esp_depth_m) - 650.0) > 1e-9:
            name += f"_ESP{int(round(esp_depth_m))}"
        for tag, v in (("HP", heat_pump_mw), ("ABS", absorption_chiller_mw), ("EC", electric_chiller_mw)):
            if float(v) > 0:
                name += f"_{tag}{float(v):g}"
        return name

    @staticmethod
    def parse_name(name):
        m = re.match(r"^([1-3])x(\d+)m(?:_ID([\d.]+))?(?:_ESP(\d+))?(?:_HP([\d.]+))?(?:_ABS([\d.]+))?(?:_EC([\d.]+))?$",
                     name.strip())
        if not m:
            return None
        return (int(m[1]), float(m[2]), float(m[3] or 0.20), float(m[4] or 650.0),
                float(m[5] or 0.0), float(m[6] or 0.0), float(m[7] or 0.0))

    def _design(self, n_doublets, depth_m, well_inner_diameter_m=0.20, esp_depth_m=650.0,
                heat_pump_mw=0.0, absorption_chiller_mw=0.0, electric_chiller_mw=0.0):
        name = self.canonical_name(n_doublets, depth_m, well_inner_diameter_m, esp_depth_m,
                                   heat_pump_mw, absorption_chiller_mw, electric_chiller_mw)
        return PlantDesign(name, int(n_doublets), WellDesign(float(depth_m), float(well_inner_diameter_m), float(esp_depth_m)),
                           heat_pump_mw=float(heat_pump_mw), absorption_mw=float(absorption_chiller_mw),
                           electric_chiller_mw=float(electric_chiller_mw))

    def _summarise(self, design, daily, k, findings, verified):
        viol = [f"{f['code']}: {f['message']}" for f in findings if f["severity"] == "violation"]
        warn = [f"{f['code']}: {f['message']}" for f in findings if f["severity"] == "warning"]
        on = daily["doublets_on"] > 0
        peak = int(daily["heating_mw"].idxmax())
        return {
            "name": design.name,
            "design": self._design_text(design),
            "meets_all_constraints": not viol,
            "violations": viol,
            "warnings": warn,
            "kpi": {
                "reservoir_temperature_C": _r(reservoir_temperature_c(design.well.depth_m), 1),
                "reservoir_pressure_bar": _r(reservoir_pressure_bar(design.well.depth_m), 1),
                "heating_geothermal_share_pct": _r(100 * k["geothermal_share_of_heating"], 1),
                "heating_geothermal_GWh": _r(k["heating_geothermal_gwh"], 1),
                "heating_assoc_gas_GWh": _r(k["heating_assoc_gas_gwh"], 1),
                "heating_heat_pump_GWh": _r(k["heating_heat_pump_gwh"], 1),
                "heat_pump_mean_COP": _r(k["heat_pump_mean_cop"], 2),
                "heating_natural_gas_GWh": _r(k["heating_natural_gas_gwh"], 1),
                "heating_unmet_GWh": _r(k["heating_unmet_gwh"], 2),
                "cooling_absorption_GWh": _r(k["cooling_absorption_gwh"], 1),
                "cooling_electric_chiller_GWh": _r(k["cooling_electric_gwh"], 1),
                "cooling_unmet_GWh": _r(k["cooling_unmet_gwh"], 2),
                "electricity_total_GWh": _r(k["electricity_gwh"], 2),
                "pump_electricity_GWh": _r(k["pump_electricity_gwh"], 2),
                "co2_kt_per_year": _r(k["co2_t"] / 1e3, 2),
                "co2_kg_per_MWh_heat": _r(k["co2_kg_per_mwh_heat"], 0),
                "flow_min_m3h_per_doublet": _r(k["min_active_q_per_doublet_m3h"], 0),
                "flow_max_m3h_per_doublet": _r(k["max_q_per_doublet_m3h"], 0),
                "max_brine_cooling_C": _r(k["max_brine_cooling_c"], 1),
                "peak_day_wellhead_temperature_C": _r(daily.loc[peak, "t_wellhead_c"], 1),
                "peak_day_network_after_HX_C": _r(daily.loc[peak, "t_network_after_hx_c"], 1),
                "operating_days_per_doublet": k["operating_days_per_doublet"],
                "days_with_some_doublet_on": int(on.sum()),
            },
            "heating_limit_on_peak_day": self._heating_limit(design, daily, peak),
            "gemini_cross_check": "PASS" if verified else "MISMATCH",
        }

    @staticmethod
    def _design_text(d):
        inc = [f"{d.n_doublets} doublet(s), wells {d.well.depth_m:.0f} m, ID {d.well.inner_diameter_m:.2f} m, "
               f"ESP at {d.well.esp_depth_m:.0f} m", "heating heat exchanger"]
        missing = []
        for label, v in (("heat pump", d.heat_pump_mw), ("absorption chiller", d.absorption_mw),
                         ("electric chiller", d.electric_chiller_mw)):
            (inc if v > 0 else missing).append(f"{label} {v:g} MW" if v > 0 else label)
        inc.append("gas boiler top-up (associated gas first)")
        missing.append("thermal storage")
        return "; ".join(inc) + ". NOT included: " + ", ".join(missing) + "."

    def _heating_limit(self, design, daily, peak):
        """What stops geothermal from covering the peak: computed, not guessed."""
        r = daily.loc[peak]
        t_brine = r["t_wellhead_c"] - self.a.surface_temperature_loss_c
        hot_end = t_brine - r["t_network_after_hx_c"]
        all_full = r["doublets_on"] == r["doublets_available"] and r["q_per_doublet_m3h"] >= CHALLENGE["max_flow_m3h_per_doublet"] - 1
        if r["t_network_after_hx_c"] >= CHALLENGE["heating_supply_temperature_c"] - 0.01:
            return "none: geothermal reaches the 100 C supply on the peak day"
        if hot_end <= self.a.hx_min_approach_c + 0.5:
            return (f"TEMPERATURE: brine reaches the heat exchanger at {t_brine:.1f} C, so the network can only be heated to "
                    f"{r['t_network_after_hx_c']:.1f} C of the 100 C needed (heat exchanger at its {self.a.hx_min_approach_c:.0f} C "
                    "design approach). More flow or more doublets cannot raise this; deeper wells (hotter brine) or a heat pump can.")
        if all_full:
            return (f"FLOW: all {int(r['doublets_on'])} doublet(s) at the {CHALLENGE['max_flow_m3h_per_doublet']:.0f} m3/h cap "
                    f"on the peak day and the network reaches only {r['t_network_after_hx_c']:.1f} C; more doublets would add heat.")
        if r["brine_cooling_c"] >= CHALLENGE["max_brine_cooling_c"] - 0.1:
            return (f"BRINE COOLING CAP: brine already cooled by the maximum {CHALLENGE['max_brine_cooling_c']:.0f} C on the peak day; "
                    "more heat needs more flow or hotter brine.")
        return f"HEAT EXCHANGER SIZE: hot-end approach {hot_end:.1f} C on the peak day; a larger exchanger would add heat."

    def evaluate_design(self, n_doublets, depth_m, well_inner_diameter_m=0.20, esp_depth_m=650.0,
                        heat_pump_mw=0.0, absorption_chiller_mw=0.0, electric_chiller_mw=0.0):
        d = self._design(n_doublets, depth_m, well_inner_diameter_m, esp_depth_m, heat_pump_mw, absorption_chiller_mw,
                         electric_chiller_mw)
        daily, k, _, _ = run_year(d, self.a, self.demand)
        findings = check(daily, k, d, self.a)
        v = verify_days(d, daily, self.a, ua_mw_k=k["hx_ua_mw_k"])
        res = self._summarise(d, daily, k, findings, bool(v["pass"].all()))
        nondef = {k2: v2 for k2, v2 in (("well_inner_diameter_m", d.well.inner_diameter_m), ("esp_depth_m", d.well.esp_depth_m))
                  if abs(v2 - {"well_inner_diameter_m": 0.20, "esp_depth_m": 650.0}[k2]) > 1e-9}
        if nondef:
            res["non_default_parameters"] = {**nondef, "note": "changed from default (ID 0.20 m, ESP 650 m); "
                                             "only change geometry when the user asks or you state why"}
        prev = self.memory.design(d.name)
        if prev and prev.get("assumptions") and prev["assumptions"] != self._assumption_state():
            old_k, new_k = prev["result"]["kpi"], res["kpi"]
            res["changes_vs_previous_evaluation_of_this_design"] = {
                "assumptions_then": prev["assumptions"], "assumptions_now": self._assumption_state(),
                **{kk: [old_k.get(kk), new_k[kk]] for kk in ("heating_geothermal_share_pct", "heating_natural_gas_GWh",
                                                             "co2_kt_per_year", "pump_electricity_GWh")}}
        self._daily[d.name] = daily
        self.memory.record_design(d.name, dataclasses.asdict(d), res, self._assumption_state())
        return res

    def _assumption_state(self):
        return {k: getattr(self.a, k) for k in EDITABLE_ASSUMPTIONS}

    def sweep_designs(self, depths_m, n_doublets_options, heat_pump_mw_options=(0.0,), absorption_chiller_mw_options=(0.0,),
                      electric_chiller_mw_options=(0.0,)):
        """Evaluate a grid in one call (saves tokens vs one call per design); ranked by CO2."""
        import itertools
        grid = list(itertools.product(depths_m, n_doublets_options, heat_pump_mw_options, absorption_chiller_mw_options,
                                      electric_chiller_mw_options))
        if len(grid) > 36:
            return {"error": f"{len(grid)} combinations requested; max 36 per sweep. Narrow the options."}
        rows = []
        for z, n, hp, ab, ec in grid:
                r = self.evaluate_design(n, z, heat_pump_mw=hp, absorption_chiller_mw=ab, electric_chiller_mw=ec)
                k = r["kpi"]
                rows.append({"name": r["name"], "violations": [x.split(":")[0] for x in r["violations"]],
                             "heating_geothermal_share_pct": k["heating_geothermal_share_pct"],
                             "heating_natural_gas_GWh": k["heating_natural_gas_GWh"],
                             "cooling_unmet_GWh": k["cooling_unmet_GWh"], "electricity_total_GWh": k["electricity_total_GWh"],
                             "pump_electricity_GWh": k["pump_electricity_GWh"], "co2_kt_per_year": k["co2_kt_per_year"],
                             "heating_limit": r["heating_limit_on_peak_day"].split(":")[0],
                             "gemini_cross_check": r["gemini_cross_check"]})
        rows.sort(key=lambda r: r["co2_kt_per_year"])
        feasible = [r for r in rows if not r["violations"]]
        return {"lowest_co2_design": {"name": rows[0]["name"], "co2_kt_per_year": rows[0]["co2_kt_per_year"]},
                "lowest_co2_design_meeting_all_constraints": (
                    {"name": feasible[0]["name"], "co2_kt_per_year": feasible[0]["co2_kt_per_year"]} if feasible
                    else "none: every design violates at least one constraint"),
                "ranked_by_co2": rows, "assumptions": self._assumption_state(),
                "note": "costs (e.g. deeper drilling, heat pump and chiller capital) are not included"}

    def compare_designs(self, names):
        """Current results for the named designs: stale ones (older assumptions) are re-run, unknown
        canonical names (e.g. '3x2500m') are evaluated, so comparisons are always like for like."""
        out, unknown = [], []
        for n in names:
            stored = self.memory.design(n)
            parsed = self.parse_name(n)
            if stored is not None and stored.get("assumptions") == self._assumption_state():
                r, refreshed = stored["result"], False
            elif parsed:
                r, refreshed = self.evaluate_design(*parsed), stored is not None
            else:
                unknown.append(n)
                continue
            out.append({"name": r["name"], **r["kpi"], "heating_limit_on_peak_day": r["heating_limit_on_peak_day"],
                        "violations": [x.split(":")[0] for x in r["violations"]],
                        "meets_all_constraints": r["meets_all_constraints"], "refreshed_for_current_assumptions": refreshed})
        res = {"assumptions": self._assumption_state(), "designs": out}
        if unknown:
            res["unknown_names"] = unknown
            res["hint"] = "use names like '2x2500m' (doublets x depth) or evaluate_design first"
        return res

    def get_day_operation(self, name, date):
        """How a design runs on one day (to explain behaviour)."""
        if name not in self._daily:
            d = self.memory.design(name)
            if d is None:
                return {"error": f"design '{name}' not evaluated yet; call evaluate_design first"}
            p = d["params"]
            self.evaluate_design(p["n_doublets"], p["well"]["depth_m"], p["well"]["inner_diameter_m"], p["well"]["esp_depth_m"],
                                 p.get("heat_pump_mw", 0.0), p.get("absorption_mw", 0.0), p.get("electric_chiller_mw", 0.0))
        daily = self._daily[name]
        row = daily[daily["date"].dt.strftime("%Y-%m-%d") == date]
        if row.empty:
            return {"error": f"date {date} not in 2027 (use YYYY-MM-DD)"}
        r = row.iloc[0]
        return {"date": date, "heating_demand_MW": _r(r["heating_mw"]), "cooling_demand_MW": _r(r["cooling_mw"]),
                "doublets_on": int(r["doublets_on"]), "flow_m3h_per_doublet": _r(r["q_per_doublet_m3h"], 0),
                "wellhead_temperature_C": _r(r["t_wellhead_c"], 1), "injection_temperature_C": _r(r["t_injection_c"], 1),
                "network_after_HX_C": _r(r["t_network_after_hx_c"], 1), "heat_geothermal_MW": _r(r["heat_geothermal_mw"]),
                "heat_assoc_gas_MW": _r(r["heat_assoc_gas_boiler_mw"]), "heat_natural_gas_MW": _r(r["heat_ng_boiler_mw"]),
                "heat_pump_MW": _r(r["heat_pump_mw"]), "heat_pump_COP": _r(r["heat_pump_cop"]),
                "cooling_absorption_MW": _r(r["cooling_absorption_mw"]), "cooling_electric_chiller_MW": _r(r["cooling_electric_mw"]),
                "cooling_unmet_MW": _r(r["cooling_unmet_mw"]), "brine_order": r["brine_order"],
                "esp_power_MW": _r(r["esp_power_mw"], 3), "injection_pump_MW": _r(r["injection_pump_power_mw"], 3)}

    def record_decision(self, decision, based_on_designs):
        missing = [n for n in based_on_designs if self.memory.design(n) is None]
        if missing:
            return {"error": f"cannot base a decision on designs never evaluated: {missing}"}
        self.memory.record_decision(decision, based_on_designs)
        return {"ok": True}


# ---------------------------------------------------------------------- schemas
def _fn(name, desc, props=None, required=None):
    return {"type": "function", "function": {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props or {}, "required": required or []}}}


SCHEMAS = [
    _fn("get_challenge_inputs", "Fixed challenge data: reservoir, brine, constraints, supply temperatures, and what the challenge does NOT give."),
    _fn("get_demand_summary", "Heating and cooling demand: annual totals, peaks with dates, monthly means."),
    _fn("list_assumptions", "Assumptions the model uses that the challenge does not specify, with allowed ranges."),
    _fn("set_assumption", "Change an assumption. Only with a value the user gave or a cited source.",
        {"name": {"type": "string", "enum": list(EDITABLE_ASSUMPTIONS)}, "value": {"type": "number"},
         "reason": {"type": "string"}, "source": {"type": "string", "enum": ["user", "organisers", "literature"]}},
        ["name", "value", "reason", "source"]),
    _fn("list_models", "Which component models exist (GEMINI and ours) and which are missing."),
    _fn("evaluate_design", "Simulate a full year of one plant design and check every constraint. Returns KPIs, violations and a GEMINI cross-check.",
        {"n_doublets": {"type": "integer", "minimum": 1, "maximum": 3},
         "depth_m": {"type": "number", "minimum": 1500, "maximum": 4000, "description": "well depth in metres"},
         "well_inner_diameter_m": {"type": "number", "minimum": 0.12, "maximum": 0.35},
         "esp_depth_m": {"type": "number", "minimum": 200, "maximum": 1500},
         "heat_pump_mw": {"type": "number", "minimum": 0, "maximum": 30, "description": "heat pump heating capacity"},
         "absorption_chiller_mw": {"type": "number", "minimum": 0, "maximum": 15, "description": "brine-driven cooling capacity"},
         "electric_chiller_mw": {"type": "number", "minimum": 0, "maximum": 15, "description": "electric cooling capacity"}},
        ["n_doublets", "depth_m"]),
    _fn("sweep_designs", "Evaluate a grid (depths x doublets x optional component sizes, max 36 combinations) in one "
        "call, ranked by CO2.",
        {"depths_m": {"type": "array", "items": {"type": "number", "minimum": 1500, "maximum": 4000}},
         "n_doublets_options": {"type": "array", "items": {"type": "integer", "minimum": 1, "maximum": 3}},
         "heat_pump_mw_options": {"type": "array", "items": {"type": "number", "minimum": 0, "maximum": 30}},
         "absorption_chiller_mw_options": {"type": "array", "items": {"type": "number", "minimum": 0, "maximum": 15}},
         "electric_chiller_mw_options": {"type": "array", "items": {"type": "number", "minimum": 0, "maximum": 15}}},
        ["depths_m", "n_doublets_options"]),
    _fn("compare_designs", "Like-for-like comparison under the CURRENT assumptions (re-runs stale results; accepts names "
        "like '2x2500m'). Call it before comparing or explaining designs.",
        {"names": {"type": "array", "items": {"type": "string"}}}, ["names"]),
    _fn("get_day_operation", "How an evaluated design operates on one date (YYYY-MM-DD).",
        {"name": {"type": "string"}, "date": {"type": "string"}}, ["name", "date"]),
    _fn("record_decision", "Store an engineering decision and the evaluated designs it is based on.",
        {"decision": {"type": "string"}, "based_on_designs": {"type": "array", "items": {"type": "string"}}},
        ["decision", "based_on_designs"]),
]
SCHEMA_BY_NAME = {s["function"]["name"]: s for s in SCHEMAS}
