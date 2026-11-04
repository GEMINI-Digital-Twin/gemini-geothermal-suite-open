"""Agentic design workflow: propose -> evaluate with the digital twin -> detect violations ->
diagnose -> repair -> re-evaluate, then explore alternatives and refine the best design.

Two orchestration modes share the same tools:

* ``RuleBasedDesignAgent``  - deterministic engineering heuristics, fully offline (default).
* ``ClaudeDesignAgent``     - Claude (Anthropic API) drives the same tools and writes its own
                              rationale. Used when ``ANTHROPIC_API_KEY`` is available.

Every step is logged as an ``AgentStep`` with the reasoning, so the final report can explain
each major engineering decision.
"""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass, field, asdict

import numpy as np

from .demand import DemandProfile
from .spec import HackathonSpec, SPEC
from .subsurface import WELL_ID_OPTIONS, WellDesign
from .system import EvaluationResult, SystemDesign, evaluate_design


@dataclass
class AgentStep:
    iteration: int
    phase: str
    action: str
    rationale: str
    design_name: str
    feasible: bool | None = None
    hard_violations: list[str] = field(default_factory=list)
    soft_violations: list[str] = field(default_factory=list)
    kpis: dict = field(default_factory=dict)
    cost: dict = field(default_factory=dict)
    elapsed_s: float = 0.0


KPI_KEYS = ["heat_delivered_gwh", "cool_delivered_gwh", "electricity_gwh", "system_cop", "geothermal_share",
            "peak_flow_per_doublet_m3_h", "mean_flow_per_doublet_m3_h", "days_at_max_flow", "days_at_min_flow",
            "max_brine_dt_c", "min_injection_t_c", "wellhead_temperature_at_300_c", "esp_stages",
            "esp_power_at_300_mw", "esp_intake_pressure_at_300_bar", "bubble_point_bar", "injection_whp_at_300_bar",
            "unmet_heat_gwh", "unmet_cool_gwh", "peak_electricity_mw"]


def _kpi_subset(k: dict) -> dict:
    out = {}
    for x in KPI_KEYS:
        v = k.get(x)
        out[x] = round(float(v), 3) if isinstance(v, (int, float, np.floating)) else v
    return out


class DesignToolbox:
    """The tools both agents use. Keeps a registry of every evaluated design."""

    def __init__(self, demand: DemandProfile, spec: HackathonSpec = SPEC, log=print):
        self.demand = demand
        self.spec = spec
        self.log = log
        self.results: dict[str, EvaluationResult] = {}
        self._by_signature: dict[str, str] = {}
        self.steps: list[AgentStep] = []
        self._iter = 0
        self.dsum = demand.summary()

    # ---------------------------------------------------------------- tools
    @staticmethod
    def signature(ds: SystemDesign) -> str:
        d = ds.to_dict()
        d.pop("name"); d.pop("rationale"); d.pop("maintenance_start_days")
        return json.dumps(d, sort_keys=True, default=float)

    def evaluate(self, ds: SystemDesign, phase: str, action: str, rationale: str) -> EvaluationResult:
        self._iter += 1
        t0 = time.time()
        sig = self.signature(ds)
        prev = self._by_signature.get(sig)
        if prev is not None:
            res = self.results[prev]
            self.log(f"[{self._iter:02d}] {phase:<11} {ds.name:<28} identical to {prev} - reused")
            self.results[ds.name] = res
            self._iter -= 1
            return res
        res = evaluate_design(ds, self.demand, self.spec)
        self.results[ds.name] = res
        self._by_signature[sig] = ds.name
        step = AgentStep(
            iteration=self._iter, phase=phase, action=action, rationale=rationale, design_name=ds.name,
            feasible=res.feasible,
            hard_violations=[f"{v.code} ({v.days} d, worst {v.worst_value:.2f})" for v in res.violations if v.severity == "hard"],
            soft_violations=[f"{v.code} ({v.days} d, worst {v.worst_value:.2f})" for v in res.violations if v.severity == "soft"],
            kpis=_kpi_subset(res.kpis), cost={k: round(v, 3) for k, v in res.cost.items()},
            elapsed_s=time.time() - t0,
        )
        self.steps.append(step)
        self.log(f"[{self._iter:02d}] {phase:<11} {ds.name:<28} feasible={res.feasible!s:<5} "
                 f"hard={len(step.hard_violations)} soft={len(step.soft_violations)} "
                 f"COP={res.kpis['system_cop']:.1f} LCOE={res.cost['levelised_cost_eur_per_mwh']:.1f} EUR/MWh "
                 f"({step.elapsed_s:.0f}s) :: {action}")
        return res

    def describe_design(self, ds: SystemDesign) -> dict:
        return ds.to_dict()

    # ---------------------------------------------------------------- sizing heuristics
    def expected_wellhead_temperature(self, depth_m: float) -> float:
        """Reservoir T minus ~2-3 C wellbore loss at design flow (confirmed by the twin later)."""
        return self.spec.reservoir.temperature_at_depth(depth_m) - 2.5

    def archetype(self, name: str, n_doublets: int, depth_m: float, cooling: str,
                  production_id: float = 0.2168) -> SystemDesign:
        """Build a sized candidate from top-level choices; the twin then validates it."""
        c = self.spec.constraints
        t_wh = self.expected_wellhead_temperature(depth_m)
        peak_h, peak_c = self.dsum["heating_peak_mw"], self.dsum["cooling_peak_mw"]
        direct = t_wh - 3.0 >= c.heating_supply_temperature_c
        rationale = []
        if direct:
            hp = round(max(0.0, 0.25 * peak_h), 1)   # top-up only (ESP trips / cold spells)
            rationale.append(f"Brine ~{t_wh:.0f} C allows direct 100 C supply; heat pump kept small ({hp} MW) for top-up.")
        else:
            hp = round(peak_h * 1.05, 1)
            rationale.append(f"Brine ~{t_wh:.0f} C is below the 100 C supply: all heat is lifted by a {hp} MW high-temperature heat pump.")
        abs_mw = el_mw = 0.0
        if cooling == "absorption":
            abs_mw = round(peak_c, 1)
            if t_wh < 90.0:
                el_mw = round(peak_c, 1)
                rationale.append(f"Absorption chiller COP is poor at {t_wh:.0f} C driving temperature; electric chiller backup sized for the full peak.")
            else:
                rationale.append(f"Single-effect absorption chiller ({abs_mw} MW) driven by {t_wh:.0f} C brine covers the cooling peak.")
        elif cooling == "hybrid":
            abs_mw, el_mw = round(0.6 * peak_c, 1), round(0.5 * peak_c, 1)
            rationale.append("Hybrid cooling: absorption base-load with electric chiller peak-shaving.")
        else:
            el_mw = round(peak_c, 1)
            rationale.append(f"Electric chiller ({el_mw} MW) covers cooling; geothermal brine serves heating only.")
        well = WellDesign(reservoir_midpoint_m=depth_m, production_id_m=production_id, injection_id_m=production_id,
                          esp_depth_m=800.0 if depth_m <= 3000 else 1000.0, esp_bep_m3_h=220.0)
        ds = SystemDesign(name=name, n_doublets=n_doublets, well=well, heat_pump_mw=hp,
                          absorption_chiller_mw=abs_mw, electric_chiller_mw=el_mw, rationale=rationale)
        return ds

    # ---------------------------------------------------------------- diagnosis
    def diagnose(self, res: EvaluationResult) -> tuple[SystemDesign, str, str] | None:
        """Return (repaired design, action, rationale) for the most important violation, or None."""
        ds, k, c = res.design, res.kpis, self.spec.constraints
        codes = {v.code: v for v in res.violations}
        peak_h, peak_c = self.dsum["heating_peak_mw"], self.dsum["cooling_peak_mw"]
        t_wh = k["wellhead_temperature_at_300_c"]

        if "no_doublet_available" in codes:
            return (ds.copy(name=f"{ds.name}+dbl", n_doublets=ds.n_doublets + 1), "add doublet",
                    "Each doublet may only operate 330 days/year; a single doublet leaves 35 days with no supply. "
                    "A second doublet allows staggered maintenance with continuous supply.")
        if "esp_intake_below_bubble_point" in codes:
            v = codes["esp_intake_below_bubble_point"]
            return (ds.copy(name=f"{ds.name}+espdeep", **{"well.esp_depth_m": ds.well.esp_depth_m + 200}),
                    "set ESP deeper",
                    f"ESP intake pressure is {v.worst_value:.0f} bar short of the bubble point + 5 bar margin "
                    f"(GLR 0.8 Nm3/m3, CH4-rich); the pump is set 200 m deeper to keep gas in solution.")
        if "esp_head_shortfall" in codes:
            target = float(np.clip(k["peak_flow_per_doublet_m3_h"] / 1.3, 100.0, 300.0))
            if target <= ds.well.esp_bep_m3_h + 1:
                target = min(300.0, ds.well.esp_bep_m3_h * 1.25)
            return (ds.copy(name=f"{ds.name}+esp", **{"well.esp_bep_m3_h": round(target, 0)}), "larger ESP",
                    f"Selected ESP cannot deliver the head at 65 Hz on the peak-flow days; moved to a larger pump frame "
                    f"(BEP {target:.0f} m3/h = peak flow / 1.3).")
        if "erosional_velocity" in codes or "esp_power_above_envelope" in codes:
            ids = sorted(WELL_ID_OPTIONS.values())
            bigger = [i for i in ids if i > ds.well.production_id_m + 1e-6]
            if bigger:
                return (ds.copy(name=f"{ds.name}+id", **{"well.production_id_m": bigger[0], "well.injection_id_m": bigger[0]}),
                        "larger casing", "Tubing velocity above the API RP14E erosional limit or ESP power above envelope; "
                        f"production/injection casing increased to {bigger[0] * 1000:.0f} mm ID to cut velocity and friction.")
        if "injection_whp_above_limit" in codes:
            ids = sorted(WELL_ID_OPTIONS.values())
            bigger = [i for i in ids if i > ds.well.injection_id_m + 1e-6]
            if bigger:
                return (ds.copy(name=f"{ds.name}+injid", **{"well.injection_id_m": bigger[0]}), "larger injector",
                        "Injection wellhead pressure above limit; larger injection casing reduces friction losses.")
            if ds.n_doublets < c.max_doublets:
                return (ds.copy(name=f"{ds.name}+dbl", n_doublets=ds.n_doublets + 1), "add doublet",
                        "Injection pressure limit reached; an extra doublet reduces per-well injection rate.")
        if "unmet_heating" in codes:
            v = codes["unmet_heating"]
            direct_possible = t_wh - 3.0 >= c.heating_supply_temperature_c
            if not direct_possible and ds.heat_pump_mw < peak_h * 1.05 - 1e-6:
                return (ds.copy(name=f"{ds.name}+hp", heat_pump_mw=round(peak_h * 1.05, 1)), "size heat pump",
                        f"Wellhead brine is {t_wh:.0f} C, below the 100 C supply; heat pump capacity raised to cover the "
                        f"{peak_h:.0f} MW heating peak (+5 % margin).")
            if k["days_at_max_flow"] > 0 and ds.n_doublets < c.max_doublets:
                return (ds.copy(name=f"{ds.name}+dbl", n_doublets=ds.n_doublets + 1), "add doublet",
                        f"Heating unmet on {v.days} days while every available doublet runs at the 300 m3/h cap "
                        f"and the 40 C brine-cooling cap binds; an additional doublet raises extractable heat.")
            if direct_possible and ds.heat_pump_mw < peak_h * 0.5:
                return (ds.copy(name=f"{ds.name}+hp", heat_pump_mw=round(ds.heat_pump_mw + 0.25 * peak_h, 1)), "enlarge heat pump",
                        "Direct heat exchange is capped by the 40 C brine cooling limit; a larger heat pump top-up adds "
                        "deliverable heat from the same brine flow.")
            if ds.n_doublets >= c.max_doublets and ds.well.reservoir_midpoint_m < 4000:
                return (ds.copy(name=f"{ds.name}+deep", **{"well.reservoir_midpoint_m": ds.well.reservoir_midpoint_m + 500}),
                        "deepen wells", "All three doublets at cap; deeper (hotter) wells raise the heat-pump COP and "
                        "allow direct supply, increasing heat per m3 of brine.")
        if "unmet_cooling" in codes:
            v = codes["unmet_cooling"]
            if ds.absorption_chiller_mw > 0 and t_wh < 90 and ds.electric_chiller_mw < peak_c:
                return (ds.copy(name=f"{ds.name}+ech", electric_chiller_mw=round(peak_c, 1)), "electric chiller backup",
                        f"Absorption chiller is driving-temperature limited at {t_wh:.0f} C; electric chiller sized for the "
                        f"{peak_c:.0f} MW cooling peak.")
            if ds.absorption_chiller_mw > 0 and ds.absorption_chiller_mw < peak_c:
                return (ds.copy(name=f"{ds.name}+abs", absorption_chiller_mw=round(peak_c, 1)), "enlarge absorption chiller",
                        "Absorption chiller capacity below the cooling peak.")
            if ds.electric_chiller_mw < peak_c:
                return (ds.copy(name=f"{ds.name}+ech", electric_chiller_mw=round(peak_c, 1)), "electric chiller",
                        f"Cooling unmet on {v.days} days; electric chiller sized for the {peak_c:.0f} MW cooling peak.")
            if ds.n_doublets < c.max_doublets:
                return (ds.copy(name=f"{ds.name}+dbl", n_doublets=ds.n_doublets + 1), "add doublet",
                        "Cooling unmet because brine flow for the absorption generator is capped; extra doublet.")
        if "brine_cooling_above_max" in codes or "flow_above_max" in codes or "flow_below_min" in codes:
            return None  # the dispatcher already enforces these; reaching here means a modelling bug
        # ---- soft issues, repaired once
        if "esp_outside_operating_window" in codes:
            v = codes["esp_outside_operating_window"]
            target = float(np.clip(k["peak_flow_per_doublet_m3_h"] / 1.3, 100.0, 300.0))
            if abs(target - ds.well.esp_bep_m3_h) > 15:
                return (ds.copy(name=f"{ds.name}+bep", **{"well.esp_bep_m3_h": round(target, 0)}), "re-select ESP frame",
                        f"ESP ran outside 40-135 % of BEP on {v.days} days; pump frame re-selected with BEP "
                        f"{target:.0f} m3/h (peak flow / 1.3) so the peak sits inside the window and the VSD plus a "
                        f"recirculation line cover the low-flow days.")
        if "corrosion" in codes:
            return (ds.copy(name=f"{ds.name}+cra", corrosion_mitigation="inhibitor+GRE-lined tubing"), "corrosion mitigation",
                    "CO2 corrosion rate from the GEMINI de Waard-Milliams model exceeds 0.3 mm/yr; specify corrosion "
                    "inhibitor injection and GRE-lined production tubing.")
        return None

    # ---------------------------------------------------------------- refinement
    def trim(self, res: EvaluationResult) -> SystemDesign | None:
        """Right-size capacities to what the annual simulation actually used (with margin)."""
        ds, d = res.design, res.daily
        changes = {}
        hp_used = max(d["heat_hp"]) if ds.heat_pump_mw > 0 else 0.0
        if ds.heat_pump_mw > 0 and hp_used * 1.1 < ds.heat_pump_mw - 0.5:
            changes["heat_pump_mw"] = round(max(hp_used * 1.1, 0.0), 1)
        abs_used = max(d["cool_abs"]) if ds.absorption_chiller_mw > 0 else 0.0
        if ds.absorption_chiller_mw > 0 and abs_used * 1.1 < ds.absorption_chiller_mw - 0.5:
            changes["absorption_chiller_mw"] = round(abs_used * 1.1, 1)
        el_used = max(d["cool_el"]) if ds.electric_chiller_mw > 0 else 0.0
        if ds.electric_chiller_mw > 0 and el_used * 1.1 < ds.electric_chiller_mw - 0.5:
            changes["electric_chiller_mw"] = round(el_used * 1.1, 1)
        if not changes:
            return None
        return ds.copy(name=f"{ds.name}~trim", **changes)

    def rank(self) -> list[EvaluationResult]:
        seen, feas = set(), []
        for r in self.results.values():
            if r.feasible and id(r) not in seen:
                seen.add(id(r))
                feas.append(r)
        return sorted(feas, key=lambda r: (r.cost["total_annual_cost_meur"], -r.kpis["geothermal_share"]))


# ============================================================================================
# Rule-based agent
# ============================================================================================
class RuleBasedDesignAgent:
    def __init__(self, demand: DemandProfile, spec: HackathonSpec = SPEC, log=print, max_repairs: int = 12,
                 explore: bool = True):
        self.tb = DesignToolbox(demand, spec, log)
        self.max_repairs = max_repairs
        self.explore = explore
        self.log = log

    def repair_loop(self, ds: SystemDesign, phase: str) -> EvaluationResult:
        res = self.tb.evaluate(ds, phase, "evaluate", " ".join(ds.rationale) or "Initial candidate.")
        base_name, applied = ds.name, []
        for i in range(self.max_repairs):
            fix = self.tb.diagnose(res)
            if fix is None:
                break
            new_ds, action, why = fix
            if applied.count(action) >= 2:
                self.log(f"     repair '{action}' already applied twice for {base_name}; stopping to avoid oscillation")
                break
            applied.append(action)
            new_ds.name = f"{base_name}-r{i + 1}"
            new_ds.rationale = list(ds.rationale) + [why]
            res = self.tb.evaluate(new_ds, phase, action, why)
            ds = new_ds
        return res

    def run(self) -> dict:
        tb = self.tb
        s = tb.dsum
        self.log(f"Demand: heating peak {s['heating_peak_mw']:.1f} MW on {s['heating_peak_date']}, "
                 f"{s['heating_gwh']:.1f} GWh/yr; cooling peak {s['cooling_peak_mw']:.1f} MW on {s['cooling_peak_date']}, "
                 f"{s['cooling_gwh']:.1f} GWh/yr")
        # ---- Phase 1: start from the cheapest conceivable design and let the twin push back
        base = tb.archetype("baseline-1dbl-2500m", 1, 2500.0, "electric")
        base.heat_pump_mw = 0.0
        base.electric_chiller_mw = 0.0
        base.rationale = ["Deliberately minimal starting point: one doublet at the specified 2,500 m reservoir, "
                          "no heat pump and no chiller, so every added component is justified by a detected violation."]
        best = self.repair_loop(base, "repair")

        # ---- Phase 2: explore structurally different alternatives
        if self.explore:
            cands = []
            for depth in (2500.0, 3000.0, 3500.0, 4000.0):
                for n in (2, 3):
                    for cooling in ("absorption", "electric"):
                        cands.append((f"alt-{n}dbl-{int(depth)}m-{cooling}", n, depth, cooling))
            for name, n, depth, cooling in cands:
                ds = tb.archetype(name, n, depth, cooling)
                self.repair_loop(ds, "explore")

        # ---- Phase 3: refine the best feasible design(s)
        ranked = tb.rank()
        for res in ranked[:3]:
            trimmed = tb.trim(res)
            if trimmed is not None:
                trimmed.rationale = list(res.design.rationale) + ["Capacities trimmed to 110 % of the peak actually used in the annual simulation."]
                tb.evaluate(trimmed, "refine", "trim capacities", trimmed.rationale[-1])
                r2 = tb.results[trimmed.name]
                fix = tb.diagnose(r2)
                if fix is not None and not r2.feasible:
                    new_ds, action, why = fix
                    tb.evaluate(new_ds, "refine", action, why)
        ranked = tb.rank()
        final = ranked[0] if ranked else best
        return {"final": final, "ranked": ranked, "steps": tb.steps, "results": tb.results}


# ============================================================================================
# Claude-driven agent (optional)
# ============================================================================================
CLAUDE_SYSTEM = """You are a senior geothermal and HVAC design engineer orchestrating the GEMINI geothermal
digital twin to design a deep-geothermal heating and cooling system. Use the tools: build candidate designs,
evaluate them with the twin, read the violations, repair the design, and compare alternatives. Hard caps:
1-3 doublets, 50-300 m3/h per doublet, max 40 C brine cooling, 330 operating days per doublet, 100 C heating
supply, 20 C cooling supply. Explain every major engineering decision. When satisfied, call finalize_design.
Prefer the design with the lowest total annual cost among feasible designs, and mention the trade-off against
geothermal share / electricity use."""

CLAUDE_TOOLS = [
    {"name": "get_context", "description": "Return the challenge specification and demand summary.",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}, "strict": True},
    {"name": "build_candidate", "description": "Build a sized candidate from top-level choices and evaluate it with the twin.",
     "input_schema": {"type": "object", "properties": {
         "name": {"type": "string"}, "n_doublets": {"type": "integer"}, "depth_m": {"type": "number"},
         "cooling": {"type": "string", "enum": ["absorption", "electric", "hybrid"]}},
         "required": ["name", "n_doublets", "depth_m", "cooling"], "additionalProperties": False}, "strict": True},
    {"name": "modify_and_evaluate", "description": "Copy an evaluated design, change fields (e.g. heat_pump_mw, "
     "absorption_chiller_mw, electric_chiller_mw, n_doublets, well.reservoir_midpoint_m, well.esp_depth_m, "
     "well.esp_bep_m3_h, well.production_id_m) and evaluate it.",
     "input_schema": {"type": "object", "properties": {
         "source_name": {"type": "string"}, "new_name": {"type": "string"},
         "changes_json": {"type": "string", "description": "JSON object of field -> value"},
         "rationale": {"type": "string"}},
         "required": ["source_name", "new_name", "changes_json", "rationale"], "additionalProperties": False}, "strict": True},
    {"name": "suggest_repair", "description": "Ask the rule-based diagnoser for a suggested repair of an evaluated design.",
     "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"],
                      "additionalProperties": False}, "strict": True},
    {"name": "rank_designs", "description": "List feasible designs ranked by total annual cost.",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}, "strict": True},
    {"name": "finalize_design", "description": "Select the final design and give the engineering summary.",
     "input_schema": {"type": "object", "properties": {"name": {"type": "string"}, "summary": {"type": "string"}},
                      "required": ["name", "summary"], "additionalProperties": False}, "strict": True},
]


class ClaudeDesignAgent:
    """Claude orchestrates the same toolbox. Requires the ``anthropic`` package and an API key."""

    def __init__(self, demand: DemandProfile, spec: HackathonSpec = SPEC, log=print,
                 model: str = "claude-opus-5-5", max_turns: int = 40):
        import anthropic  # local import so the offline agent never needs it
        self.client = anthropic.Anthropic()
        self.anthropic = anthropic
        self.tb = DesignToolbox(demand, spec, log)
        self.model = model
        self.max_turns = max_turns
        self.log = log
        self.final_name: str | None = None
        self.final_summary = ""

    def _call_tool(self, name: str, inp: dict) -> str:
        tb = self.tb
        try:
            if name == "get_context":
                return json.dumps({"spec": tb.spec.to_dict(), "demand": tb.dsum}, default=float)
            if name == "build_candidate":
                ds = tb.archetype(inp["name"], int(inp["n_doublets"]), float(inp["depth_m"]), inp["cooling"])
                res = tb.evaluate(ds, "claude", "build candidate", " ".join(ds.rationale))
                return json.dumps(res.summary(), default=float)
            if name == "modify_and_evaluate":
                src = tb.results[inp["source_name"]].design
                changes = json.loads(inp["changes_json"])
                ds = src.copy(name=inp["new_name"], **changes)
                ds.rationale = list(src.rationale) + [inp["rationale"]]
                res = tb.evaluate(ds, "claude", f"modify {list(changes)}", inp["rationale"])
                return json.dumps(res.summary(), default=float)
            if name == "suggest_repair":
                fix = tb.diagnose(tb.results[inp["name"]])
                if fix is None:
                    return json.dumps({"suggestion": None})
                ds, action, why = fix
                return json.dumps({"action": action, "rationale": why, "design": ds.to_dict()}, default=float)
            if name == "rank_designs":
                return json.dumps([{"name": r.design.name, "cost": r.cost, "kpis": _kpi_subset(r.kpis)} for r in tb.rank()],
                                  default=float)
            if name == "finalize_design":
                self.final_name, self.final_summary = inp["name"], inp["summary"]
                return "final design recorded"
        except Exception as e:  # report tool errors back to the model
            return json.dumps({"error": repr(e)})
        return json.dumps({"error": f"unknown tool {name}"})

    def run(self) -> dict:
        messages = [{"role": "user", "content": "Design the system for the supplied 2027 heating and cooling "
                     "demand. Start by getting the context, then iterate until you have a validated design."}]
        for _ in range(self.max_turns):
            with self.client.beta.messages.stream(
                model=self.model, max_tokens=16000, system=CLAUDE_SYSTEM, tools=CLAUDE_TOOLS,
                messages=messages, betas=["server-side-fallback-2026-07-01"], fallbacks="default",
                thinking={"type": "adaptive"},
            ) as stream:
                resp = stream.get_final_message()
            messages.append({"role": "assistant", "content": resp.content})
            if resp.stop_reason == "refusal":
                self.log("Claude declined the request; falling back to the rule-based agent.")
                break
            tool_uses = [b for b in resp.content if b.type == "tool_use"]
            for b in resp.content:
                if b.type == "text" and b.text.strip():
                    self.log(f"[claude] {b.text.strip()[:500]}")
            if not tool_uses:
                break
            results = []
            for tu in tool_uses:
                out = self._call_tool(tu.name, dict(tu.input))
                results.append({"type": "tool_result", "tool_use_id": tu.id, "content": out})
            messages.append({"role": "user", "content": results})
            if self.final_name:
                break
        ranked = self.tb.rank()
        final = self.tb.results.get(self.final_name) if self.final_name else None
        if final is None or not final.feasible:
            final = ranked[0] if ranked else None
        if final is None:
            raise RuntimeError("Claude agent produced no feasible design")
        self.tb.steps.append(AgentStep(len(self.tb.steps) + 1, "claude", "finalize", self.final_summary,
                                       final.design.name, final.feasible))
        return {"final": final, "ranked": ranked, "steps": self.tb.steps, "results": self.tb.results}


def make_agent(demand: DemandProfile, spec: HackathonSpec = SPEC, log=print, mode: str = "auto", **kw):
    if mode in ("auto", "claude") and os.environ.get("ANTHROPIC_API_KEY"):
        try:
            return ClaudeDesignAgent(demand, spec, log, **{k: v for k, v in kw.items() if k in ("model", "max_turns")})
        except Exception as e:  # missing package etc.
            log(f"Claude agent unavailable ({e!r}); using rule-based agent")
    elif mode == "claude":
        log("ANTHROPIC_API_KEY not set; using rule-based agent")
    return RuleBasedDesignAgent(demand, spec, log, **{k: v for k, v in kw.items() if k in ("max_repairs", "explore")})
