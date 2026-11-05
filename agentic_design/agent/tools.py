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
from agentic_design.economics import CostAssumptions, economics, well_cost_eur
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


MAX_SWEEP = 48


class ToolBox:
    def __init__(self, memory, assumptions: Assumptions = None):
        self.memory = memory
        self.a = assumptions or Assumptions()
        for k, v in memory.assumption_overrides().items():  # long-term memory applied at start
            if k in EDITABLE_ASSUMPTIONS:
                setattr(self.a, k, type(getattr(self.a, k))(v))
        self.demand = load_demand()
        self._daily = {}  # name -> daily DataFrame (session cache)
        self._last_designs = {}  # name -> PlantDesign
        self._last_changes = {}  # name -> before/after of its latest re-evaluation
        self.costs = CostAssumptions()

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
                            "production_equals_injection": True,
                            "geothermal_availability": "330 days/yr per doublet; the 35 shut-in days are a design choice "
                                                       "(staggered across doublets, or backup equipment); the full "
                                                       "system must meet demand all 365 days (organisers, 1-2 Nov)",
                            "well_depth": "free design variable; hydrostatic pressure and the gradient give reservoir "
                                          "pressure and temperature (organisers, 1 Nov)"},
            "supply_temperature_C": {"heating": c["heating_supply_temperature_c"], "cooling": c["cooling_supply_temperature_c"]},
            "not_given_by_challenge": ["heating return temperature", "cooling network return temperature", "costs"],
            "note_on_return_temperatures": "not given; the team chooses and justifies them as long as the constraints "
                                           "hold (organisers, 2 Nov). Current choice: see list_assumptions.",
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
            "supply_temperature_C": {"heating": CHALLENGE["heating_supply_temperature_c"],
                                     "cooling": CHALLENGE["cooling_supply_temperature_c"]},
            "limits": self.get_challenge_inputs()["constraints"],
        }

    def list_assumptions(self):
        out = {k: {"value": getattr(self.a, k), "meaning": EDITABLE_ASSUMPTIONS[k][2],
                   "allowed_range": list(EDITABLE_ASSUMPTIONS[k][:2])} for k in EDITABLE_ASSUMPTIONS}
        c = self.costs
        out["costs"] = {"well_cost_MEUR_per_well": {z: _r(well_cost_eur(z, c) / 1e6, 2) for z in (2500, 3000, 3500)},
                        "electricity_EUR_per_MWh": c.electricity_eur_per_mwh, "natural_gas_EUR_per_MWh": c.natural_gas_eur_per_mwh,
                        "co2_price_EUR_per_t": c.co2_eur_per_t, "discount_rate": c.discount_rate, "lifetime_years": c.lifetime_yr,
                        "electric_chiller_EUR_per_kW": c.electric_chiller_eur_per_kw,
                        "absorption_chiller_EUR_per_kW": c.absorption_chiller_eur_per_kw,
                        "heat_pump_EUR_per_kW": c.heat_pump_eur_per_kw, "boiler_EUR_per_kW": c.boiler_eur_per_kw,
                        "sources": c.sources}
        out["costs"]["co2_value_for_design_choice_EUR_per_t"] = c.co2_shadow_eur_per_t
        return out

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
                       heat_pump_mw=0.0, absorption_chiller_mw=0.0, electric_chiller_mw=0.0, gas_reinjection=False):
        """Name encodes every non-default parameter, so a changed design can never reuse an old name."""
        name = f"{int(n_doublets)}x{int(round(depth_m))}m"
        if abs(float(well_inner_diameter_m) - 0.20) > 1e-9:
            name += f"_ID{float(well_inner_diameter_m):.2f}"
        if abs(float(esp_depth_m) - 650.0) > 1e-9:
            name += f"_ESP{int(round(esp_depth_m))}"
        for tag, v in (("HP", heat_pump_mw), ("ABS", absorption_chiller_mw), ("EC", electric_chiller_mw)):
            if float(v) > 0:
                name += f"_{tag}{float(v):g}"
        if gas_reinjection:
            name += "_RI"
        return name

    @staticmethod
    def parse_name(name):
        m = re.match(r"^([1-3])x(\d+)m(?:_ID([\d.]+))?(?:_ESP(\d+))?(?:_HP([\d.]+))?(?:_ABS([\d.]+))?(?:_EC([\d.]+))?(_RI)?$",
                     name.strip())
        if not m:
            return None
        return (int(m[1]), float(m[2]), float(m[3] or 0.20), float(m[4] or 650.0),
                float(m[5] or 0.0), float(m[6] or 0.0), float(m[7] or 0.0), bool(m[8]))

    def _design(self, n_doublets, depth_m, well_inner_diameter_m=0.20, esp_depth_m=650.0,
                heat_pump_mw=0.0, absorption_chiller_mw=0.0, electric_chiller_mw=0.0, gas_reinjection=False):
        name = self.canonical_name(n_doublets, depth_m, well_inner_diameter_m, esp_depth_m,
                                   heat_pump_mw, absorption_chiller_mw, electric_chiller_mw, gas_reinjection)
        return PlantDesign(name, int(n_doublets), WellDesign(float(depth_m), float(well_inner_diameter_m), float(esp_depth_m)),
                           heat_pump_mw=float(heat_pump_mw), absorption_mw=float(absorption_chiller_mw),
                           electric_chiller_mw=float(electric_chiller_mw), gas_reinjection=bool(gas_reinjection))

    def _summarise(self, design, daily, k, findings, verified):
        e = economics(design, daily, k, self.a, self.costs)
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
                "capex_MEUR": _r(e["capex_meur"], 1),
                "capex_wells_MEUR": _r(e["capex_breakdown_meur"]["wells"], 1),
                "cost_EUR_per_MWh": _r(e["lcoe_eur_per_mwh"], 1),
                "cost_with_co2_price_EUR_per_MWh": _r(e["lcoe_with_co2_eur_per_mwh"], 1),
                "cost_with_EIB_co2_value_EUR_per_MWh": _r(e["lcoe_with_shadow_co2_eur_per_mwh"], 1),
                "associated_gas": ("burned when the boilers need it, rest reinjected" if design.gas_reinjection
                                   else "burned in the boilers, surplus flared"),
                "backup_boiler_MW": _r(e["boiler_capacity_mw"], 1),
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
        (inc if d.gas_reinjection else missing).append("associated-gas compression and reinjection")
        missing.append("thermal storage")
        return "; ".join(inc) + ". NOT included: " + ", ".join(missing) + "."

    def _heating_limit(self, design, daily, peak):
        """What stops geothermal from covering the peak: computed, not guessed."""
        text = self._heating_limit_core(design, daily, peak)
        r = daily.loc[peak]
        topup = float(r["heat_assoc_gas_boiler_mw"] + r["heat_ng_boiler_mw"] + r["heat_pump_mw"])
        short = float(r["heating_mw"] - r["heat_geothermal_mw"] - topup)
        if not text.startswith("none") and short < self.a.demand_tolerance_mw:
            # demo 11: the model read "network reaches only 94.7 C" as "demand not met"
            src = [f"{lab} {v:.1f} MW" for lab, v in (("associated-gas boiler", r["heat_assoc_gas_boiler_mw"]),
                                                       ("natural-gas boiler", r["heat_ng_boiler_mw"]),
                                                       ("heat pump", r["heat_pump_mw"])) if v > 0.05]
            text += f" Demand is still met: on that day {' and '.join(src)} top up to the 100 C supply."
        return text

    def _heating_limit_core(self, design, daily, peak):
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
                        heat_pump_mw=0.0, absorption_chiller_mw=0.0, electric_chiller_mw=0.0, gas_reinjection=False):
        d = self._design(n_doublets, depth_m, well_inner_diameter_m, esp_depth_m, heat_pump_mw, absorption_chiller_mw,
                         electric_chiller_mw, gas_reinjection)
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
            changed = {k_: (prev["assumptions"].get(k_), v_) for k_, v_ in self._assumption_state().items()
                       if prev["assumptions"].get(k_) != v_}

            def delta(kk):  # explicit before/after/direction: demo 7 read a [old, new] list backwards
                b, a_ = old_k.get(kk), new_k[kk]
                if b is None or a_ is None:
                    return {"before": b, "after": a_}
                return {"before": b, "after": a_, "change": _r(a_ - b),
                        "direction": "increased" if a_ > b else "decreased" if a_ < b else "unchanged"}
            res["changes_vs_previous_evaluation_of_this_design"] = {
                "assumptions_changed": {k_: {"before": b_, "after": a_} for k_, (b_, a_) in changed.items()},
                **{kk: delta(kk) for kk in ("heating_geothermal_share_pct", "heating_natural_gas_GWh",
                                            "co2_kt_per_year", "pump_electricity_GWh", "heat_pump_mean_COP")}}
            # the cause, computed: which energy flows moved (demo 12 blamed a heat pump the design does not have)
            flows = {"pump_electricity_GWh": "pump electricity", "heating_assoc_gas_GWh": "associated gas burned for heat",
                     "heating_natural_gas_GWh": "natural gas burned", "heating_heat_pump_GWh": "heat pump heat",
                     "cooling_electric_chiller_GWh": "electric chiller cooling",
                     "cooling_absorption_GWh": "absorption chiller cooling"}
            moved = [f"{label} {old_k[kk]} -> {new_k[kk]} GWh" for kk, label in flows.items()
                     if old_k.get(kk) is not None and new_k.get(kk) is not None and abs(new_k[kk] - old_k[kk]) >= 0.05]
            self._last_changes[d.name] = res["changes_vs_previous_evaluation_of_this_design"]
            res["changes_vs_previous_evaluation_of_this_design"]["cause"] = (
                "Flows that changed: " + "; ".join(moved) + ". Explain the change only with these flows."
                if moved else "No energy flow changed by 0.05 GWh or more; the change is negligible.")
        self._daily[d.name] = daily
        self._last_designs[d.name] = d
        self.memory.record_design(d.name, dataclasses.asdict(d), res, self._assumption_state())
        return res

    def _change_note(self, name):
        ch = self._last_changes.get(name)
        if not ch:
            return ""
        parts = [f"{k} {v['before']} -> {v['after']}" for k, v in ch.items()
                 if isinstance(v, dict) and "before" in v and k != "assumptions_changed" and v.get("direction") != "unchanged"]
        ass = "; ".join(f"{k} {v['before']} -> {v['after']}" for k, v in ch.get("assumptions_changed", {}).items())
        return (f" Change for {name} after the assumption change ({ass}): " + "; ".join(parts) + ". " + ch.get("cause", "")
                if parts else "")

    def _assumption_state(self):
        return {k: getattr(self.a, k) for k in EDITABLE_ASSUMPTIONS}

    @staticmethod
    def _suggest_grid(options, limit=None):
        limit = limit or MAX_SWEEP
        """Drop middle options until the grid fits: a ready-to-use smaller call. Component sizes are thinned
        before depths and doublet counts, which matter more."""
        opts = {k: list(v) for k, v in options.items()}
        size = lambda: int(np.prod([len(v) for v in opts.values()]))
        # thin in this order: heat pump sizes first (right-sizing shrinks them anyway), then the other units
        comps = ["heat_pump_mw_options", "absorption_chiller_mw_options", "electric_chiller_mw_options",
                 "gas_reinjection_options"]
        while size() > limit:
            pool = [k for k in comps if len(opts[k]) > 1] or list(opts)
            k = pool[0] if pool[0] == "heat_pump_mw_options" else max(pool, key=lambda kk: len(opts[kk]))
            v = opts[k]
            if len(v) <= 1:
                break
            if k == "electric_chiller_mw_options":  # keep the larger chiller (cooling must be met)
                v.remove(min(v))
            elif k in comps:  # keep "without" and the smallest sizes: drop the largest
                v.remove(max(v))
            else:
                del v[len(v) // 2 if len(v) > 2 else 1]
        return opts

    def _oversized(self, name):
        """Components used at < 50 % of their size: {field: (size, peak use MW)}."""
        d, daily = self._last_designs[name], self._daily[name]
        out = {}
        for field, cap, col in (("heat_pump_mw", d.heat_pump_mw, "heat_pump_mw"),
                                ("absorption_chiller_mw", d.absorption_mw, "cooling_absorption_mw"),
                                ("electric_chiller_mw", d.electric_chiller_mw, "cooling_electric_mw")):
            if cap > 0 and daily[col].max() < 0.5 * cap:
                out[field] = (cap, float(daily[col].max()))
        return out

    def _right_size(self, name):
        """Re-evaluate a design with each oversized component cut to its peak use (0.5 MW steps) or removed;
        oversized units only add cost, so the cheapest variant (CO2 valued at the carbon value) is kept."""
        over = self._oversized(name)
        if not over:
            return None
        d = self._last_designs[name]
        base = dict(n_doublets=d.n_doublets, depth_m=d.well.depth_m, well_inner_diameter_m=d.well.inner_diameter_m,
                    esp_depth_m=d.well.esp_depth_m, heat_pump_mw=d.heat_pump_mw, absorption_chiller_mw=d.absorption_mw,
                    electric_chiller_mw=d.electric_chiller_mw, gas_reinjection=d.gas_reinjection)
        tried = []
        for mode in ("resize", "remove"):
            args = dict(base)
            for field, (cap, peak) in over.items():
                args[field] = 0.0 if mode == "remove" or peak < 0.05 else float(np.ceil(peak * 1.05 / 0.5) * 0.5)
            if args == base or any(t[0] == args for t in tried):
                continue
            r = self.evaluate_design(**args)
            tried.append((args, r))
        ok = [r for _, r in tried if r["meets_all_constraints"]]
        if not ok:
            return None
        best = min(ok, key=lambda r: (r["kpi"]["cost_with_EIB_co2_value_EUR_per_MWh"], r["kpi"]["co2_kt_per_year"]))
        return {"name": best["name"], "co2_kt_per_year": best["kpi"]["co2_kt_per_year"],
                "cost_with_EIB_co2_value_EUR_per_MWh": best["kpi"]["cost_with_EIB_co2_value_EUR_per_MWh"],
                "replaces": name, "oversized_in_original": {k: f"{c:g} MW installed, peak use {p:.2f} MW"
                                                             for k, (c, p) in over.items()}}

    def sweep_designs(self, depths_m, n_doublets_options, heat_pump_mw_options=(0.0,), absorption_chiller_mw_options=(0.0,),
                      electric_chiller_mw_options=(0.0,), gas_reinjection_options=(False,)):
        """Evaluate a grid in one call (saves tokens vs one call per design); ranked by CO2."""
        import itertools
        options = {"depths_m": list(depths_m), "n_doublets_options": list(n_doublets_options),
                   "heat_pump_mw_options": list(heat_pump_mw_options),
                   "absorption_chiller_mw_options": list(absorption_chiller_mw_options),
                   "electric_chiller_mw_options": list(electric_chiller_mw_options),
                   "gas_reinjection_options": [bool(x) for x in gas_reinjection_options]}
        for k in ("heat_pump_mw_options", "absorption_chiller_mw_options"):  # "without" is always a candidate
            if 0.0 not in [float(x) for x in options[k]]:
                options[k] = [0.0] + list(options[k])
        grid = list(itertools.product(*options.values()))
        narrowed = None
        if len(grid) > MAX_SWEEP:  # run the narrowed grid instead of failing (demo 8: 12 identical rejected calls)
            narrowed = {"requested_combinations": len(grid), "ran_instead": self._suggest_grid(options)}
            options = narrowed["ran_instead"]
            grid = list(itertools.product(*options.values()))
        rows = []
        for z, n, hp, ab, ec, ri in grid:
                r = self.evaluate_design(n, z, heat_pump_mw=hp, absorption_chiller_mw=ab, electric_chiller_mw=ec,
                                         gas_reinjection=ri)
                k = r["kpi"]
                rows.append({"name": r["name"], "violations": [x.split(":")[0] for x in r["violations"]],
                             "warnings": [x.split(":")[0] + (":" + x.split(":")[1] if x.startswith("P8") else "")
                                          for x in r["warnings"]],
                             "heating_geothermal_share_pct": k["heating_geothermal_share_pct"],
                             "heating_natural_gas_GWh": k["heating_natural_gas_GWh"],
                             "cooling_unmet_GWh": k["cooling_unmet_GWh"], "electricity_total_GWh": k["electricity_total_GWh"],
                             "pump_electricity_GWh": k["pump_electricity_GWh"], "co2_kt_per_year": k["co2_kt_per_year"],
                             "capex_MEUR": k["capex_MEUR"], "cost_EUR_per_MWh": k["cost_EUR_per_MWh"],
                             "cost_with_EIB_co2_value_EUR_per_MWh": k["cost_with_EIB_co2_value_EUR_per_MWh"],
                             "heating_limit": r["heating_limit_on_peak_day"].split(":")[0],
                             "gemini_cross_check": r["gemini_cross_check"]})
        rows.sort(key=lambda r: r["co2_kt_per_year"])
        feasible = [r for r in rows if not r["violations"]]
        out = {**({"narrowed_automatically": narrowed} if narrowed else {}),
               "lowest_co2_design": {"name": rows[0]["name"], "co2_kt_per_year": rows[0]["co2_kt_per_year"]},
               "lowest_co2_design_meeting_all_constraints": (
                   {"name": feasible[0]["name"], "co2_kt_per_year": feasible[0]["co2_kt_per_year"]} if feasible
                   else "none: every design violates at least one constraint")}
        if feasible:
            cv = self.costs.co2_shadow_eur_per_t
            best_cost = min(r["cost_with_EIB_co2_value_EUR_per_MWh"] for r in feasible)
            # within 1 % of the best cost the designs are equal given the cost uncertainty: take the simplest
            # (fewest unit types: heat pump, absorption chiller, electric chiller, gas reinjection), then lowest CO2
            near = [r for r in feasible if r["cost_with_EIB_co2_value_EUR_per_MWh"] <= best_cost * 1.01 + 1e-9]
            n_units = lambda r: sum(1 for x in self.parse_name(r["name"])[4:7] if x > 0) + int(r["name"].endswith("_RI"))  # noqa: E731
            pick = min(near, key=lambda r: (n_units(r), r["co2_kt_per_year"], r["cost_with_EIB_co2_value_EUR_per_MWh"]))
            out["lowest_cost_design_meeting_all_constraints"] = min(
                ({"name": r["name"], "cost_EUR_per_MWh": r["cost_EUR_per_MWh"], "co2_kt_per_year": r["co2_kt_per_year"]}
                 for r in feasible), key=lambda x: x["cost_EUR_per_MWh"])
            rs = self._right_size(pick["name"])
            if rs:
                out["right_sized_design"] = rs
            out["recommended_design"] = rs["name"] if rs else pick["name"]
            rec_name = rs["name"] if rs else pick["name"]
            rec = next((r for r in rows if r["name"] == rec_name), None)
            low = feasible[0]
            cheap = out["lowest_cost_design_meeting_all_constraints"]

            def line(r):
                return (f"{r['name']}: CO2 {r['co2_kt_per_year']} kt/yr, geothermal heating {r['heating_geothermal_share_pct']} %, "
                        f"cost {r['cost_EUR_per_MWh']} EUR/MWh ({r['cost_with_EIB_co2_value_EUR_per_MWh']} with CO2 at {cv:.0f} EUR/t)")
            out["answer_summary"] = (
                f"Recommended: {line(rec) if rec else rec_name + ' (right-sized version of ' + pick['name'] + ', CO2 ' + str(rs['co2_kt_per_year']) + ' kt/yr, ' + str(rs['cost_with_EIB_co2_value_EUR_per_MWh']) + ' EUR/MWh with CO2 value)'}. "
                f"Lowest CO2 meeting all constraints: {line(low)}. "
                f"Cheapest meeting all constraints (CO2 not valued): {cheap['name']}, {cheap['cost_EUR_per_MWh']} EUR/MWh, "
                f"CO2 {cheap['co2_kt_per_year']} kt/yr. Designs with violations are excluded."
                + self._change_note(rec_name))
            out["recommendation_rule"] = (f"meets all constraints; lowest cost per MWh with CO2 valued at {cv:.0f} EUR/t "
                                          "(EIB shadow cost of carbon, plant-life average); designs within 1 % of that "
                                          "cost count as equal, so the simplest (fewest unit types), then lowest CO2, "
                                          "is chosen; oversized components right-sized")
        out.update({"ranked_by_co2": rows, "assumptions": self._assumption_state(),
                    "note": "cost = levelised cost of delivered heat+cooling (ThermoGIS well/plant costs, Eurostat "
                            "prices, EU ETS CO2 price); see list_assumptions for sources"})
        return out

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
                        "violations": [x[:220] for x in r["violations"]],
                        **({"changes_vs_previous_evaluation_of_this_design": r["changes_vs_previous_evaluation_of_this_design"]}
                           if r.get("changes_vs_previous_evaluation_of_this_design") else {}),
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
                "esp_power_MW": _r(r["esp_power_mw"], 3), "injection_pump_MW": _r(r["injection_pump_power_mw"], 3),
                **({"note": "heat pump idle on this day; for the design's heat pump COP use heat_pump_mean_COP "
                            "(evaluate_design / compare_designs)"} if r["heat_pump_mw"] <= 1e-6 and
                   self._last_designs.get(name) is not None and self._last_designs[name].heat_pump_mw > 0 else {})}

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
         "electric_chiller_mw": {"type": "number", "minimum": 0, "maximum": 15, "description": "electric cooling capacity"},
         "gas_reinjection": {"type": "boolean", "description": "true: burn associated gas only when boilers need it and "
                                                              "reinject the rest (no emission); false: surplus is flared"}},
        ["n_doublets", "depth_m"]),
    _fn("sweep_designs", "Evaluate a grid (depths x doublets x component sizes x gas reinjection, max 48 combinations; "
        "larger grids are narrowed automatically) in one call. Returns recommended_design and rankings. Good first call: "
        "depths [3000, 3500], doublets [1, 2, 3], heat pump [0], absorption [0, 5], electric [5, 10], gas_reinjection [false, true] "
        "(48). Answer from answer_summary.",
        {"depths_m": {"type": "array", "items": {"type": "number", "minimum": 1500, "maximum": 4000}},
         "n_doublets_options": {"type": "array", "items": {"type": "integer", "minimum": 1, "maximum": 3}},
         "heat_pump_mw_options": {"type": "array", "items": {"type": "number", "minimum": 0, "maximum": 30}},
         "absorption_chiller_mw_options": {"type": "array", "items": {"type": "number", "minimum": 0, "maximum": 15}},
         "electric_chiller_mw_options": {"type": "array", "items": {"type": "number", "minimum": 0, "maximum": 15}},
         "gas_reinjection_options": {"type": "array", "items": {"type": "boolean"}}},
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
