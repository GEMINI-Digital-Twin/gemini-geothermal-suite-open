"""GEMINI hackathon task 6: design agent with a pluggable decision backend.

Run in GEMINI repository root:
    $env:PYTHONPATH="src"; py -3.11 -m poetry run python hackathon_work/design_agent.py
    ... design_agent.py --backend claude_cli      # calls `claude -p` (prompt on stdin)

Loop: interpret inputs -> check required inputs -> assess source temperature ->
propose (backend) -> validate design against the hard limits -> build and
validate the GEMINI JSON -> run the 365-day model (cached) -> well/ESP sanity
checks -> constraint check -> rank (CLAUDE.md rule incl. parsimony) -> revise,
within a budget of annual evaluations.

Two scenarios are run:
  A. inputs with the heating return temperature removed: the agent must stop
     and ask instead of inventing the value (deterministic input check, no backend call);
  B. complete inputs: the design loop.

Backends share one interface (``propose`` / ``revise``): given the state and
the history of evaluated candidates with their check results, return the next
candidate and a written rationale (or ``None`` when done).
  - "rules" (default): deterministic heuristics, reproducible, no API.
  - "claude_cli": asks Claude Code for the next candidate as JSON (no tools,
    no session persistence); the agent still validates every proposal.

Logs (rules: outputs/agent/, claude_cli: outputs/agent/claude_cli/):
decision_log.jsonl (machine-readable) and agent_trace.md (readable, for the report).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from constraints import check_constraints, load_limits
from daily_model import CANDIDATES_PATH, Plant
from demand_baseline import load_demand
from doublet_model import CHALLENGE_PATH, PROJECT_PATH, REPO, ROOT, boundary, load_json
from gemini_simulator.project_loader import load_project
from gemini_simulator.registry import COMPONENT_REGISTRY
from reference_case import reference_summary
from run_candidates import annual_summary, rank

AGENT_OUT = ROOT / "outputs" / "agent"
CACHE = AGENT_OUT / "cache"

FLOW_ROUNDING_M3H = 50
HEX_APPROACH_ESTIMATE_K = 5.0  # ASSUMED, only for the direct-supply depth estimate in the temperature assessment
ESP_INTAKE_MARGIN_BAR = 5.0    # ASSUMED margin of ESP intake pressure above the brine vapour pressure
ESP_FREQ_MARGIN_HZ = 2.0


def design_space(settings: dict) -> dict:
    r = settings["ranking"]
    return {
        "n_doublets": [1, 2, 3],
        "flow_cap_m3h": [50, 300],          # continuous range, challenge hard limits
        "esp": sorted(settings["esp_options"]),
        "hex_ua_W_K": [250e3, 500e3, 1000e3],
        "depth_m": {"min": 2500, "max": r["max_depth_m"], "step": r["depth_step_m"]},
    }


def candidate_id(c: dict) -> str:
    return f"n{c['n_doublets']}_q{c['flow_cap_m3h']:g}_{c['esp']}_ua{c['hex_ua_W_K'] / 1e3:.0f}_z{c['depth_m']:g}"


def saturation_pressure_bar(t_c: float) -> float:
    """Water vapour pressure (Antoine; two coefficient sets, 1-374 C)."""
    a, b, c = (8.07131, 1730.63, 233.426) if t_c < 99 else (8.14019, 1810.94, 244.485)
    return 10 ** (a - b / (c + t_c)) * 0.00133322


# --- logging -------------------------------------------------------------------
class DecisionLog:
    """Append-only JSONL decision log; also keeps the entries for the Markdown trace."""

    def __init__(self, path, backend_name):
        self.path = path
        self.backend = backend_name
        self.entries = []
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("", encoding="utf-8")

    def event(self, scenario, phase, title, data=None, rationale=None):
        entry = {"step": len(self.entries) + 1, "time_utc": datetime.now(timezone.utc).isoformat(), "scenario": scenario,
                 "backend": self.backend, "phase": phase, "title": title, "rationale": rationale, "data": data}
        self.entries.append(entry)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")
        return entry


# --- backends --------------------------------------------------------------------
class RulesBackend:
    """Deterministic, explainable heuristics (no API)."""

    name = "rules"

    def __init__(self, out_dir=None):
        self.calls = []

    def propose(self, ctx: dict) -> dict | None:
        history, space = ctx["history"], ctx["design_space"]
        evaluated = {candidate_id(h["candidate"]) for h in history}
        if not history:
            n = space["n_doublets"][0]
            return self._baseline(ctx, n, f"Start with the fewest doublets ({n}): the ranking prefers fewer doublets, "
                                          f"so the smallest plant that passes the hard constraints is the target.")
        last, incumbent = history[-1], ctx["incumbent"]
        if not last["feasible"] and incumbent is None:
            n = last["candidate"]["n_doublets"] + 1
            if n > space["n_doublets"][-1]:
                return None
            failed = ", ".join(last["failing"]) or "hard constraints"
            return self._baseline(ctx, n, (
                f"Recovery: {candidate_id(last['candidate'])} failed ({failed}). With "
                f"{last['candidate']['n_doublets']} doublet(s) the 35-day maintenance window leaves the plant without "
                f"geothermal supply, which the 'never all off' interpretation forbids; add a doublet so maintenance can be staggered."))
        if incumbent is None:
            return None

        base = incumbent["candidate"]
        notes = []
        if last is not incumbent:
            outcome = (f"failed ({', '.join(last['failing'])})" if not last["feasible"]
                       else f"was ranked out ({last['verdict']['reason']})")
            notes.append(f"Previous candidate {candidate_id(last['candidate'])} {outcome}; keep incumbent {candidate_id(base)}.")
        depth = space["depth_m"]
        variants = [
            ("hex_ua_W_K", 500e3, "Smaller HEX (500 kW/K, lower cost): check whether the heat pump can absorb the lost HEX duty without external gas."),
            ("esp", "s1.0", "Smaller ESP (s = 1.0, the GEMINI example pump): cheaper, but capped at ~176 m3/h; check the effect on external gas."),
            ("depth_step", None, None),
            ("n_doublets", base["n_doublets"] + 1, "More doublets: accepted only if external gas or emissions improve by >= 5%."),
        ]
        tried = ctx["tried_variants"]
        for key, value, why in variants:
            if key in tried:
                continue
            if key == "depth_step":
                if last is not incumbent and last["candidate"]["depth_m"] > base["depth_m"]:
                    tried.add(key)
                    notes.append(f"Depth step to {last['candidate']['depth_m']:g} m failed the parsimony rule; stop exploring deeper "
                                 f"(accepted depth stays {base['depth_m']:g} m).")
                    continue
                d = base["depth_m"] + depth["step"]
                if d > depth["max"]:
                    tried.add(key)
                    notes.append(f"Depth ladder reached the {depth['max']:g} m limit of the design space.")
                    continue
                t_res = ctx["inputs"]["reservoir"]["surface_temperature_C"] + ctx["inputs"]["reservoir"]["gradient_C_per_km"] * d / 1000
                return {"candidate": {**base, "depth_m": d}, "rationale": " ".join(notes) + (
                    f" Depth ladder from incumbent {candidate_id(base)}: {base['depth_m']:g} -> {d:g} m (reservoir {t_res:.1f} C) to cut the "
                    f"heat-pump lift; accepted only if emissions improve >= 5% vs the {base['depth_m']:g} m design.")}
            candidate = {**base, key: value}
            tried.add(key)
            if (key == "n_doublets" and value > space["n_doublets"][-1]) or candidate_id(candidate) in evaluated:
                continue
            return {"candidate": candidate, "rationale": " ".join(notes + [f"Variant of incumbent {candidate_id(base)}: {why}"])}
        return None

    def _baseline(self, ctx, n, why):
        """Size each doublet's flow for its share of the heating peak by direct brine cooling at the 40 K cap."""
        need = ctx["inputs"]["heating_peak_MW"] * 1e6 / n
        brine = ctx["inputs"]["brine"]
        q = need / (brine["density_kg_m3"] * brine["cp_J_kg_K"] * ctx["limits"]["maximum_brine_delta_T_C"]) * 3600
        q_rounded = math.ceil(q / FLOW_ROUNDING_M3H) * FLOW_ROUNDING_M3H
        candidate = {"n_doublets": n, "flow_cap_m3h": q_rounded, "esp": "s1.8", "hex_ua_W_K": 1000e3, "depth_m": 2500}
        return {"candidate": candidate, "rationale": (
            f"{why} Flow sizing heuristic: peak {ctx['inputs']['heating_peak_MW']:.1f} MW / {n} doublet(s) at the 40 K brine cap "
            f"-> {q:.1f} m3/h per doublet, rounded up to {q_rounded} m3/h. Largest ESP (s = 1.8), HEX 1000 kW/K, official 2500 m reservoir.")}

    def revise(self, candidate: dict, violations: list[dict], ctx: dict) -> dict:
        revised, notes = dict(candidate), []
        for v in violations:
            key, lo, hi = v["variable"], v.get("min"), v.get("max")
            if lo is not None and revised[key] < lo:
                revised[key] = lo
            elif hi is not None and revised[key] > hi:
                revised[key] = hi
            elif key == "depth_m":
                d = ctx["design_space"]["depth_m"]
                revised[key] = d["min"] + round((revised[key] - d["min"]) / d["step"]) * d["step"]
            else:
                options = ctx["design_space"][key]
                revised[key] = min(options, key=lambda o: abs(o - candidate[key])) if isinstance(candidate[key], (int, float)) else options[-1]
            notes.append(f"{key} {candidate[key]} -> {revised[key]} ({v['reason']})")
        return {"candidate": revised, "rationale": "Clip to the nearest admissible value: " + "; ".join(notes) +
                ". The proposal's intent (largest admissible flow) is kept; the shortfall is left to the heat pump / CHP and to more doublets if needed."}


class BackendError(RuntimeError):
    pass


def find_claude_cli() -> str | None:
    """`claude` on PATH, $CLAUDE_CLI, or the newest binary bundled with the VS Code extension."""
    exe = os.environ.get("CLAUDE_CLI") or shutil.which("claude")
    if exe:
        return exe
    bundled = (Path.home() / ".vscode" / "extensions").glob("anthropic.claude-code-*/resources/native-binary/claude.exe")
    versions = sorted(bundled, key=lambda p: tuple(int(x) for x in re.findall(r"\d+", p.parts[-4].split("-", 2)[-1].split("-win")[0])))
    return str(versions[-1]) if versions else None


class ClaudeCliBackend:
    """Ask Claude Code (`claude -p`, JSON output, no tools) for the next candidate."""

    name = "claude_cli"

    def __init__(self, out_dir: Path, timeout_s: int = 300):
        self.exe = find_claude_cli()
        if self.exe is None:
            raise BackendError("claude CLI not found (PATH, $CLAUDE_CLI, VS Code extension); use --backend rules")
        self.timeout_s = timeout_s
        self.workdir = out_dir / "workdir"  # neutral cwd: no project CLAUDE.md is loaded into the backend
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.calls = []

    def _ask(self, purpose: str, prompt: str) -> dict:
        start = time.perf_counter()
        try:
            result = subprocess.run([self.exe, "-p", "--output-format", "json", "--tools", "", "--no-session-persistence"],
                                    input=prompt, capture_output=True, text=True, encoding="utf-8", timeout=self.timeout_s, cwd=self.workdir)
        except subprocess.TimeoutExpired as exc:
            raise BackendError(f"claude -p timed out after {self.timeout_s} s") from exc
        wall = time.perf_counter() - start
        call = {"purpose": purpose, "wall_s": wall, "returncode": result.returncode, "prompt_chars": len(prompt)}
        try:
            wrapper = json.loads(result.stdout)
        except json.JSONDecodeError:
            wrapper = {"result": result.stdout}
        call.update(usage=wrapper.get("usage"), total_cost_usd=wrapper.get("total_cost_usd"), duration_ms=wrapper.get("duration_ms"),
                    model_usage=wrapper.get("modelUsage"), is_error=wrapper.get("is_error"))
        self.calls.append(call)
        if result.returncode != 0 or wrapper.get("is_error"):
            raise BackendError(f"claude -p failed ({result.returncode}): {(result.stderr or str(wrapper.get('result')))[:500]}")
        text = wrapper.get("result") or ""
        call["reply"] = text
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise BackendError(f"no JSON object in claude reply: {text[:500]}")
        return json.loads(match.group(0))

    def _context_text(self, ctx: dict) -> str:
        history = [{"id": candidate_id(h["candidate"]), "candidate": h["candidate"], "feasible": h["feasible"], "failing": h["failing"],
                    "external_gas_GWh": h["metrics"]["external_gas_fuel_GWh"], "emissions_t": h["metrics"]["emissions_t"],
                    "grid_import_GWh": h["metrics"]["grid_import_GWh"], "drilled_m": h["metrics"]["drilled_m"],
                    "reservoir_temperature_C": h["metrics"]["reservoir_temperature_C"], "well_flags": h["well_flags"], "verdict": h["verdict"]}
                   for h in ctx["history"]]
        return json.dumps({"inputs": ctx["inputs"], "temperature_assessment": ctx["temperature_assessment"], "limits": ctx["limits"],
                           "design_space": ctx["design_space"], "ranking_rule": ctx["ranking_rule"], "budget_left": ctx["budget_left"],
                           "incumbent": candidate_id(ctx["incumbent"]["candidate"]) if ctx["incumbent"] else None, "history": history},
                          indent=1, default=str)

    def propose(self, ctx: dict) -> dict | None:
        reply = self._ask("propose",
            "You are the design-decision backend of a geothermal district heating/cooling design agent. "
            "Given the state below, choose the next candidate to evaluate with the 365-day model, or stop.\n"
            "Rules: stay inside design_space (depth_m = min + k*step, at most max); a candidate violating a hard limit is "
            "rejected before simulation; do not repeat an evaluated candidate; prefer the candidate most likely to change "
            "the ranking; respect the parsimony rules in ranking_rule; stop when further evaluations are unlikely to "
            "change the pick or the budget is nearly spent. Explain your reasoning briefly in the rationale.\n"
            "Reply with ONLY a JSON object: {\"done\": bool, \"candidate\": {\"n_doublets\": int, \"flow_cap_m3h\": number, "
            "\"esp\": string, \"hex_ua_W_K\": number, \"depth_m\": number}, \"rationale\": string}.\n\nSTATE:\n" + self._context_text(ctx))
        if reply.get("done"):
            self.stop_rationale = reply.get("rationale", "")
            return None
        return {"candidate": reply["candidate"], "rationale": reply.get("rationale", "")}

    def revise(self, candidate: dict, violations: list[dict], ctx: dict) -> dict:
        reply = self._ask("revise",
            "Your proposed geothermal design candidate violates hard limits or the design space. Revise it to the closest admissible design.\n"
            f"Candidate: {json.dumps(candidate)}\nViolations: {json.dumps(violations)}\n"
            "Reply with ONLY a JSON object: {\"candidate\": {...same keys...}, \"rationale\": string}.\n\nSTATE:\n" + self._context_text(ctx))
        return {"candidate": reply["candidate"], "rationale": reply.get("rationale", "")}


BACKENDS = {"rules": RulesBackend, "claude_cli": ClaudeCliBackend}


# --- agent -------------------------------------------------------------------------
class DesignAgent:
    def __init__(self, backend, log: DecisionLog, out_dir: Path, budget: int = 14):
        self.backend = backend
        self.log = log
        self.out_dir = out_dir
        self.budget = budget
        self.settings = load_json(CANDIDATES_PATH)
        self.space = design_space(self.settings)
        self.limits = load_limits()
        self.evaluations = 0
        self.eval_times = []

    # 1. interpret inputs
    def interpret_inputs(self, scenario, project, challenge) -> dict:
        heating = load_demand("GEMINI_Heating_Demand_Daily_2027.csv", "heating_demand_MWth")
        cooling = load_demand("GEMINI_Cooling_Demand_Daily_2027.csv", "cooling_demand_MWcool")
        peak_day = max(heating, key=heating.get)
        inputs = {
            "heating_days": len(heating), "cooling_days": len(cooling),
            "heating_peak_MW": heating[peak_day], "heating_peak_date": str(peak_day),
            "heating_annual_GWh": sum(heating.values()) * 24 / 1000,
            "cooling_peak_MW": max(cooling.values()), "cooling_annual_GWh": sum(cooling.values()) * 24 / 1000,
            "reservoir": challenge["reservoir"],
            "brine": {**challenge["fluid"], "cp_J_kg_K": project.get("_brine_pvt_override", {}).get("CPL")},
        }
        self.log.event(scenario, "interpret", "Interpret demand profiles and fixed inputs", data=inputs, rationale=(
            f"365-day heating ({inputs['heating_annual_GWh']:.2f} GWh, peak {inputs['heating_peak_MW']:.1f} MW on {peak_day}) and "
            f"cooling ({inputs['cooling_annual_GWh']:.2f} GWh, peak {inputs['cooling_peak_MW']:.1f} MW) must be served every day."))
        self.heating, self.cooling = heating, cooling
        return inputs

    # 2. required inputs
    def check_required_inputs(self, scenario, project, challenge) -> list[dict]:
        def get(fn):
            try:
                return fn()
            except (KeyError, IndexError, TypeError):
                return None

        s = self.settings
        items = [
            ("heating demand profile (365 days)", lambda: len(self.heating) == 365 or None, "OFFICIAL CSV", "sets daily heat to deliver"),
            ("cooling demand profile (365 days)", lambda: len(self.cooling) == 365 or None, "OFFICIAL CSV", "sets daily cooling to deliver"),
            ("reservoir depth / gradient / surface T / pressure / permeability",
             lambda: [challenge["reservoir"][k] for k in ("midpoint_depth_m_TVD", "gradient_C_per_km", "surface_temperature_C", "pressure_bar_g", "permeability_mD")],
             "OFFICIAL", "source temperature and well inflow"),
            ("brine density / viscosity / GLR / gas composition",
             lambda: [challenge["fluid"][k] for k in ("density_kg_m3", "dynamic_viscosity_mPa_s", "gas_liquid_ratio_Nm3_per_m3", "gas_methane_mol_percent")],
             "OFFICIAL", "hydraulics, produced gas"),
            ("hard constraints (flow, brine dT, pump eta, 330 days, supply temperatures)",
             lambda: [self.limits[k] for k in ("flow_max_m3_per_h_per_doublet", "maximum_brine_delta_T_C", "pump_efficiency", "geothermal_operating_days", "heating_supply_temperature_C", "cooling_supply_temperature_C")],
             "OFFICIAL", "feasibility checks"),
            ("heating return temperature", lambda: boundary(project, "heat_exchanger", "secondary_temperature_in")["value"],
             "ASSUMED, user-approved (60 C)", "sets district water flow = Q / (cp * (100 - T_return)) and the HEX/heat-pump lift"),
            ("cooling supply / return temperature", lambda: s["cooling_supply_return_C"], "OFFICIAL 20 C / ASSUMED 26 C", "chiller duty"),
            ("brine specific heat", lambda: project["_brine_pvt_override"]["CPL"], "ASSUMED, user-approved (4100)", "all heat balances"),
            ("well inner diameter / roughness", lambda: [project["components"]["producer_well"]["parameters"]["trajectory_table"][-1]["ID"],
                                                         project["components"]["producer_well"]["parameters"]["roughness_m"]],
             "ASSUMED, user-approved", "friction, pump power"),
            ("heat pump / chiller performance", lambda: [s["heat_pump"]["eta_lorenz"], s["absorption_chiller"]["cop_th"], s["electric_chiller_cop"]],
             "ASSUMED, user-approved", "electricity, cooling supply"),
            ("emission factors", lambda: [project["components"]["boiler"]["parameters"]["gas_emission_factor"], s["external_gas"]["emission_factor_kg_per_GJ"],
                                          project["components"]["producer_well"]["parameters"]["esp"]["electricity_emission_factor"]],
             "DERIVED / ASSUMED", "emissions ranking"),
        ]
        checked = [{"input": name, "present": get(fn) is not None, "value": get(fn), "source": src, "needed_for": why} for name, fn, src, why in items]
        missing = [c for c in checked if not c["present"]]
        self.log.event(scenario, "required_inputs", "Check required inputs",
                       data={"checked": checked, "missing": [m["input"] for m in missing]},
                       rationale="All required inputs present." if not missing else
                       f"{len(missing)} required input(s) missing: {', '.join(m['input'] for m in missing)}.")
        return missing

    # 3. temperature assessment (judges' test iii)
    def assess_temperature(self, scenario, inputs) -> dict:
        r = inputs["reservoir"]
        t_supply = self.limits["heating_supply_temperature_C"]
        t_res = r["surface_temperature_C"] + r["gradient_C_per_km"] * r["midpoint_depth_m_TVD"] / 1000
        depth_100 = (t_supply - r["surface_temperature_C"]) / r["gradient_C_per_km"] * 1000
        project = load_json(PROJECT_PATH)
        drops = sum(project["components"][n]["parameters"]["temperature_drop"] for n in ("separator", "filter_a"))
        loss_k = 2.0  # wellbore loss at ~300 m3/h from the derived wellhead model (0.44 MW)
        t_needed = t_supply + HEX_APPROACH_ESTIMATE_K + drops + loss_k
        depth_direct = (t_needed - r["surface_temperature_C"]) / r["gradient_C_per_km"] * 1000
        d = self.space["depth_m"]
        data = {"T_reservoir_C": t_res, "T_supply_C": t_supply, "shortfall_K": t_supply - t_res, "depth_for_T_res_100_m": depth_100,
                "T_reservoir_needed_for_direct_HEX_supply_C": t_needed, "depth_for_direct_supply_m": depth_direct, "depth_ladder": d}
        self.log.event(scenario, "temperature_assessment", "Source temperature vs 100 C supply", data=data, rationale=(
            f"Reservoir at {r['midpoint_depth_m_TVD']} m is {t_res:.1f} C, {t_supply - t_res:.1f} K below the fixed {t_supply:.0f} C supply before any "
            f"losses, so a HEX alone cannot supply 100 C. Options: (a) deeper well - T_res = 100 C needs {depth_100:.0f} m, and direct HEX supply "
            f"(T_res >= {t_needed:.1f} C incl. {HEX_APPROACH_ESTIMATE_K:.0f} K approach, {drops:.1f} K surface drops, ~{loss_k:.0f} K wellbore loss) needs "
            f"~{depth_direct:.0f} m; (b) surface upgrade - heat pump on the brine leaving the HEX plus CHP on the produced gas. Decision: start with "
            f"(b) at the official {d['min']} m (no extrapolated reservoir data, least drilling), then climb a {d['step']} m depth ladder (max "
            f"{d['max']} m) and keep each step only if emissions fall >= 5%; the ranking decides with numbers."))
        return data

    # 4. design-time validation (judges' test ii)
    def validate_design(self, candidate: dict) -> list[dict]:
        violations = []
        for key in ("n_doublets", "flow_cap_m3h", "esp", "hex_ua_W_K", "depth_m"):
            if key not in candidate:
                violations.append({"variable": key, "reason": "missing design variable"})
        if violations:
            return violations
        lo, hi = self.space["flow_cap_m3h"]
        # The challenge checker itself rejects the design point (each doublet at its flow cap).
        case = {"n_doublets": candidate["n_doublets"], "heating_supply_C": None, "cooling_supply_C": None,
                "doublets": [{"name": f"doublet_{i + 1}", "active": True, "production_m3h": candidate["flow_cap_m3h"],
                              "injection_m3h": candidate["flow_cap_m3h"], "T_production_C": 0.0, "T_injection_C": 0.0, "pumps": []}
                             for i in range(max(1, int(candidate["n_doublets"])))]}
        for r in check_constraints(case, self.limits)["results"]:
            if r["check"] == "doublet_count" and r["status"] != "PASS":
                violations.append({"variable": "n_doublets", "value": candidate["n_doublets"], "min": self.space["n_doublets"][0],
                                   "max": self.space["n_doublets"][-1], "reason": r["reason"], "check": "doublet_count"})
            if r["check"] == "flow_range" and r["status"] != "PASS" and r["scope"] == "doublet_1":
                violations.append({"variable": "flow_cap_m3h", "value": candidate["flow_cap_m3h"], "min": lo, "max": hi,
                                   "reason": r["reason"], "check": "flow_range"})
        for key in ("esp", "hex_ua_W_K"):
            if candidate[key] not in self.space[key]:
                violations.append({"variable": key, "value": candidate[key], "reason": f"{candidate[key]} not in design space {self.space[key]}"})
        d = self.space["depth_m"]
        z = candidate["depth_m"]
        if not (d["min"] <= z <= d["max"]) or (z - d["min"]) % d["step"]:
            violations.append({"variable": "depth_m", "value": z, "min": d["min"], "max": d["max"],
                               "reason": f"{z} m not on the depth ladder {d['min']}..{d['max']} m in {d['step']} m steps"})
        return violations

    # 5. build + validate GEMINI JSON
    def build_and_validate_json(self, candidate: dict, plant: Plant) -> dict:
        designs = self.out_dir / "designs"
        designs.mkdir(parents=True, exist_ok=True)
        path = designs / f"{candidate_id(candidate)}_brine_chain.json"
        path.write_text(json.dumps(plant.chain, indent=2), encoding="utf-8")
        components = plant.chain["components"]
        problems = [f"unknown type {spec['type']} for {name}" for name, spec in components.items() if spec["type"] not in COMPONENT_REGISTRY]
        for c in plant.chain["connections"]:
            for end in ("predecessor", "successor"):
                if c[end] not in components:
                    problems.append(f"connection {end} '{c[end]}' is not a component")
        problems += [f"boundary input for unknown component {b['component']}" for b in plant.chain["boundary_inputs"] if b["component"] not in components]
        load_project(path)  # GEMINI's own loader must accept the file
        return {"path": str(path.relative_to(REPO)), "components": len(components), "connections": len(plant.chain["connections"]), "problems": problems}

    # 6. well / ESP sanity checks (deeper wells)
    def well_checks(self, plant: Plant) -> dict:
        points, flags = [], []
        f_max = self.settings["dispatch"].get("esp_freq_hz_max", 70)
        v_max = self.settings["well_checks"]["max_tubing_velocity_m_s"]
        for q in (plant.flow_grid[0], plant.flow_grid[-1]):
            chain = plant.run_gemini_chain(q, 0.01, 0.0)
            t_wh, p_wh = chain["T_wellhead_C"], chain["wellhead_pressure_bar"]
            p_sat = saturation_pressure_bar(t_wh)
            tubing_id = plant.producer_params["trajectory_table"][-1]["ID"]
            area = math.pi / 4 * tubing_id ** 2
            p = {"flow_m3h": chain["production_m3h"], "esp_freq_hz": chain["controls"]["esp_freq_hz"], "control_mode": chain["controls"]["mode"],
                 "wellhead_pressure_bar": p_wh, "T_wellhead_C": t_wh, "p_sat_at_T_wellhead_bar": p_sat,
                 "esp_intake_bar": chain["esp_intake_bar"], "esp_discharge_bar": chain["esp_discharge_bar"],
                 "esp_head_bar": chain["esp_discharge_bar"] - chain["esp_intake_bar"], "esp_power_MW": chain["pumps"][0]["power_w"] / 1e6,
                 "esp_setting_depth_m": plant.producer_params["esp_depth_m"],
                 "bottomhole_pressure_bar": plant.reservoir_pressure_bar - q / plant.producer_params["productivity_index_m3h_per_bar"],
                 "injector_wellhead_bar": chain["injector_wellhead_bar"], "tubing_velocity_m_s": q / 3600 / area}
            points.append(p)
            if t_wh > 100:
                flags.append(f"{q:g} m3/h: wellhead {t_wh:.1f} C exceeds PVTConstantSTP temperature_max (100 C) - constant brine properties extrapolated")
            if p_wh < p_sat + 0.5:
                flags.append(f"{q:g} m3/h: wellhead pressure {p_wh:.2f} bar is not above the {p_sat:.2f} bar vapour pressure at {t_wh:.1f} C - flashing risk")
            if p["esp_intake_bar"] < p_sat + ESP_INTAKE_MARGIN_BAR:
                flags.append(f"{q:g} m3/h: ESP intake {p['esp_intake_bar']:.1f} bar < vapour pressure + {ESP_INTAKE_MARGIN_BAR:.0f} bar - cavitation risk")
            if p["tubing_velocity_m_s"] > v_max:
                flags.append(f"{q:g} m3/h: tubing velocity {p['tubing_velocity_m_s']:.2f} m/s > {v_max:g} m/s in the {tubing_id:g} m ID")
            if chain["controls"]["esp_freq_hz"] > f_max - ESP_FREQ_MARGIN_HZ:
                flags.append(f"{q:g} m3/h: ESP at {chain['controls']['esp_freq_hz']:.1f} Hz, within {ESP_FREQ_MARGIN_HZ:.0f} Hz of the drive limit")
        if plant.max_flow_m3h < plant.flow_cap_m3h:
            flags.append(f"ESP reaches only {plant.max_flow_m3h:.0f} of the {plant.flow_cap_m3h:g} m3/h cap at this depth")
        if plant.unreachable_flows_m3h:
            flags.append(f"flows {plant.unreachable_flows_m3h} m3/h cannot be held (min dispatchable {plant.flow_grid[0]:g} m3/h)")
        for c in plant.engineering:
            if c["status"] != "PASS":
                flags.append(f"HARD CHECK {c['check']} FAILS: {c['reason']} (limit {c['limit']})")
        return {"points": points, "flags": flags, "esp_placement": plant.esp_placement, "engineering_checks": plant.engineering, "not_modelled": "free gas at the ESP intake (GLR 0.8 brine, gas mass fraction 0 in the well model)"}

    # 7. evaluate (cached)
    def evaluate(self, candidate: dict) -> dict:
        key = hashlib.sha1(json.dumps({"candidate": candidate, "settings": self.settings}, sort_keys=True, default=str).encode()).hexdigest()[:16]
        cache_path = CACHE / f"{key}.json"
        start = time.perf_counter()
        plant = Plant({"name": candidate_id(candidate), **candidate}, self.settings)
        json_check = self.build_and_validate_json(candidate, plant)
        checks = self.well_checks(plant)
        cached = cache_path.exists()
        if cached:
            summary = json.loads(cache_path.read_text(encoding="utf-8"))
        else:
            summary = annual_summary({"name": candidate_id(candidate), **candidate}, plant, plant.simulate_year(self.heating, self.cooling))
            CACHE.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        wall = time.perf_counter() - start
        self.eval_times.append({"candidate": candidate_id(candidate), "wall_s": wall, "cached": cached})
        return {"summary": summary, "json_check": json_check, "well_checks": checks, "cached": cached, "wall_s": wall}

    def run(self, scenario: str, project: dict | None = None) -> dict:
        run_start = time.perf_counter()
        project = project if project is not None else load_json(PROJECT_PATH)
        challenge = load_json(CHALLENGE_PATH)
        self.log.event(scenario, "start", f"Scenario {scenario}: start", data={"backend": self.backend.name, "budget": self.budget, "design_space": self.space})
        inputs = self.interpret_inputs(scenario, project, challenge)
        missing = self.check_required_inputs(scenario, project, challenge)
        if missing:
            question = (f"I cannot size the plant without: {', '.join(m['input'] for m in missing)}. "
                        + " ".join(f"'{m['input']}' is needed because it {m['needed_for']}." for m in missing)
                        + " It is not in the organizers' inputs and I will not invent it. Please provide a value (previously approved: 60 C).")
            self.log.event(scenario, "halt", "Stop and ask for the missing input", data={"status": "needs_input", "missing": [m["input"] for m in missing]},
                           rationale=question)
            return {"status": "needs_input", "question": question, "runtime_s": time.perf_counter() - run_start}

        assessment = self.assess_temperature(scenario, inputs)
        history, tried_variants = [], set()
        incumbent = None
        repeats = 0
        ranking_rule = ("hard constraints pass/fail; then minimize external gas -> emissions -> net grid import -> doublets -> drilled metres "
                        "(values within 1% / 0.01 GWh / 10 t are ties); an extra doublet is kept only if external gas or emissions improve >= 5%; "
                        "a deeper well (250 m ladder from 2500 m) is kept only if emissions improve >= 5% vs the previous accepted depth; "
                        "an improvement within the tie tolerance of the 5% threshold counts as NOT meeting it (drilling cost and risk not modelled)")
        while self.evaluations < self.budget:
            ctx = {"inputs": inputs, "temperature_assessment": assessment, "limits": self.limits, "design_space": self.space,
                   "history": history, "incumbent": incumbent, "tried_variants": tried_variants,
                   "budget_left": self.budget - self.evaluations, "ranking_rule": ranking_rule}
            n_calls = len(self.backend.calls)
            proposal = self.backend.propose(ctx)
            calls = self.backend.calls[n_calls:]
            if proposal is None:
                self.log.event(scenario, "stop", "Backend stops proposing", data={"backend_calls": calls},
                               rationale=getattr(self.backend, "stop_rationale", None)
                               or "No untried variant can change the pick within the design space and the parsimony rules.")
                break
            candidate = proposal["candidate"]
            self.log.event(scenario, "propose", f"Proposal {candidate_id(candidate)}", data={"candidate": candidate, "backend_calls": calls},
                           rationale=proposal["rationale"])

            violations = self.validate_design(candidate)
            while violations:
                self.log.event(scenario, "validate", f"Rejected before simulation: {candidate_id(candidate)}", data={"violations": violations},
                               rationale="; ".join(v["reason"] for v in violations))
                n_calls = len(self.backend.calls)
                revision = self.backend.revise(candidate, violations, ctx)
                candidate = revision["candidate"]
                self.log.event(scenario, "revise", f"Revised to {candidate_id(candidate)}",
                               data={"candidate": candidate, "backend_calls": self.backend.calls[n_calls:]}, rationale=revision["rationale"])
                violations = self.validate_design(candidate)
            if any(candidate_id(h["candidate"]) == candidate_id(candidate) for h in history):
                repeats += 1
                self.log.event(scenario, "skip", f"Already evaluated: {candidate_id(candidate)}", rationale="Result already in the history; no new evaluation.")
                if repeats >= 3:
                    self.log.event(scenario, "stop", "Backend keeps repeating evaluated candidates", rationale="Stopping after 3 repeated proposals.")
                    break
                continue
            repeats = 0

            self.evaluations += 1
            result = self.evaluate(candidate)
            s = result["summary"]
            self.log.event(scenario, "build_json", f"GEMINI JSON for {candidate_id(candidate)}", data=result["json_check"],
                           rationale="GEMINI load_project accepted the brine-chain file; all connections and boundary inputs reference declared components."
                           if not result["json_check"]["problems"] else "Problems: " + "; ".join(result["json_check"]["problems"]))
            self.log.event(scenario, "well_check", f"Well / ESP sanity check at {candidate['depth_m']:g} m", data=result["well_checks"],
                           rationale=("No flags. " if not result["well_checks"]["flags"] else "Flags: " + "; ".join(result["well_checks"]["flags"]) + ". ")
                           + f"Not modelled: {result['well_checks']['not_modelled']}.")
            metrics = {k: s[k] for k in ("external_gas_fuel_GWh", "emissions_t", "grid_import_GWh", "drilled_m", "geothermal_heat_share",
                                         "max_brine_dT_K", "flow_max_m3h", "esp_max_flow_m3h", "reservoir_temperature_C", "heat_hp_GWh", "el_hp_GWh",
                                         "el_esp_GWh", "esp_setting_depth_m", "esp_intake_at_max_flow_bar", "tubing_velocity_at_max_flow_m_s", "days_hex_bypass", "days_failing_daily_checks", "capacity_MW")}
            failing = sorted(set([c["check"] for c in s["annual_checks"] if c["status"] != "PASS"] + s["failing_checks"]))
            self.log.event(scenario, "evaluate", f"Annual model + constraint check: {candidate_id(candidate)}",
                           data={"evaluation": self.evaluations, "cached": result["cached"], "wall_s": result["wall_s"], "feasible": s["feasible"],
                                 "failing": failing, "annual_checks": s["annual_checks"], "metrics": metrics},
                           rationale=(f"{'FEASIBLE' if s['feasible'] else 'INFEASIBLE'}: external gas {s['external_gas_fuel_GWh']:.3f} GWh, "
                                      f"emissions {s['emissions_t']:.0f} t, grid import {s['grid_import_GWh']:.2f} GWh, drilled {s['drilled_m']:.0f} m"
                                      + (f"; fails {', '.join(failing)}" if failing else "")
                                      + f" ({result['wall_s']:.1f} s{', cached' if result['cached'] else ''})"))
            history.append({"candidate": candidate, "summary": s, "feasible": s["feasible"], "failing": failing, "metrics": metrics,
                            "well_flags": result["well_checks"]["flags"], "well_points": result["well_checks"]["points"], "verdict": None, "wall_s": result["wall_s"], "cached": result["cached"]})

            verdicts = rank([dict(h["summary"], candidate={"name": candidate_id(h["candidate"]), **h["candidate"]}) for h in history],
                            self.settings["ranking"]["extra_doublet_min_improvement"], self.settings["ranking"]["depth_step_min_improvement"])
            for h in history:
                h["verdict"] = verdicts[candidate_id(h["candidate"])]
            accepted = [h for h in history if h["verdict"]["status"] == "ACCEPTED"]
            previous = incumbent
            incumbent = accepted[0] if accepted else None
            self.log.event(scenario, "rank", "Ranking after evaluation", data={candidate_id(h["candidate"]): h["verdict"] for h in history},
                           rationale=("Incumbent: " + candidate_id(incumbent["candidate"]) if incumbent else "No feasible candidate yet.")
                           + (f" (was {candidate_id(previous['candidate'])})" if previous and incumbent and previous is not incumbent else ""))
            if previous is not None and s["feasible"] and candidate["depth_m"] > previous["candidate"]["depth_m"] \
                    and candidate["n_doublets"] == previous["candidate"]["n_doublets"]:
                p = previous["summary"]
                extra_m = s["drilled_m"] - p["drilled_m"]
                gain = (p["emissions_t"] - s["emissions_t"]) / p["emissions_t"]
                self.log.event(scenario, "depth_step", f"Depth step {previous['candidate']['depth_m']:g} -> {candidate['depth_m']:g} m",
                               data={"from_m": previous["candidate"]["depth_m"], "to_m": candidate["depth_m"], "emissions_from_t": p["emissions_t"],
                                     "emissions_to_t": s["emissions_t"], "emissions_change": -gain, "extra_drilled_m": extra_m,
                                     "marginal_abatement_t_per_yr_per_m": (p["emissions_t"] - s["emissions_t"]) / extra_m,
                                     "accepted": incumbent is history[-1], "marginal": history[-1]["verdict"].get("marginal", False)},
                               rationale=(f"Emissions {p['emissions_t']:.0f} -> {s['emissions_t']:.0f} t ({-gain * 100:+.1f}%) for {extra_m:+.0f} m drilled: "
                                          f"{(p['emissions_t'] - s['emissions_t']) / extra_m:.3f} t CO2/yr per extra metre. "
                                          + ("ACCEPTED (>= 5% beyond the tie tolerance)." if incumbent is history[-1]
                                             else "REJECTED: within the tie tolerance of the 5% threshold, which counts as not met (conservative: "
                                             "drilling cost and risk are not modelled); recorded as a marginal sensitivity case."
                                             if history[-1]["verdict"].get("marginal") else "REJECTED by the depth parsimony rule (< 5%).")))

        runtime = time.perf_counter() - run_start
        if incumbent is None:
            self.log.event(scenario, "final", "No feasible design found", rationale="Budget or design space exhausted without a feasible candidate.")
            return {"status": "no_feasible_design", "history": history, "runtime_s": runtime}
        final = self.conclude(scenario, history, incumbent, runtime)
        return {"status": "selected", "pick": incumbent, "history": history, "runtime_s": runtime, **final}

    def conclude(self, scenario, history, incumbent, runtime):
        steps = [e for e in self.log.entries if e["scenario"] == scenario and e["phase"] == "depth_step"]
        ladder = "; ".join(f"{e['data']['from_m']:g}->{e['data']['to_m']:g} m: {e['data']['emissions_change'] * 100:+.1f}%, "
                           f"{e['data']['marginal_abatement_t_per_yr_per_m']:.3f} t/yr/m "
                           f"({'kept' if e['data']['accepted'] else 'rejected, marginal' if e['data'].get('marginal') else 'rejected'})" for e in steps)
        marginal_cases = [self.marginal_case(h, history) for h in history if h["verdict"].get("marginal")]
        ref = reference_summary()
        s = incumbent["summary"]
        reduction = (ref["emissions_t"] - s["emissions_t"]) / ref["emissions_t"]
        computed = [t["wall_s"] for t in self.eval_times if not t["cached"]]
        timing = {"evaluations": len(self.eval_times), "computed": len(computed), "cached": len(self.eval_times) - len(computed),
                  "wall_s_per_computed_evaluation_mean": sum(computed) / len(computed) if computed else None,
                  "wall_s_per_computed_evaluation_max": max(computed) if computed else None,
                  "scenario_runtime_s": runtime,
                  "backend_calls": len(self.backend.calls), "backend_wall_s": sum(c["wall_s"] for c in self.backend.calls)}
        text = (f"Depth ladder: {ladder or 'not explored'}. Selected {candidate_id(incumbent['candidate'])} "
                f"({s['reservoir_temperature_C']:.0f} C reservoir): {incumbent['verdict']['reason']}. Versus the conventional reference "
                f"(gas boiler eta 0.90 + electric chiller COP 5.0, {ref['emissions_t']:.0f} t): {reduction * 100:.1f}% lower emissions, "
                f"external gas {s['external_gas_fuel_GWh']:.3f} vs {ref['gas_fuel_GWh']:.1f} GWh, grid import {s['grid_import_GWh']:.2f} vs "
                f"{ref['grid_import_GWh']:.2f} GWh. Well checks at the pick: "
                + ("; ".join(incumbent["well_flags"]) if incumbent["well_flags"] else "no flags")
                + ". Drilling cost is not modeled; deeper steps are limited by the 5% parsimony rule."
                + "".join(f" Marginal sensitivity case: {m['text']}" for m in marginal_cases))
        self.log.event(scenario, "final", f"Final pick: {candidate_id(incumbent['candidate'])}",
                       data={"pick": incumbent["candidate"], "verdict": incumbent["verdict"], "reference": ref, "emissions_reduction_vs_reference": reduction,
                             "capacity_MW": s["capacity_MW"], "timing": timing, "marginal_cases": marginal_cases}, rationale=text)
        return {"reference": ref, "emissions_reduction": reduction, "conclusion": text, "timing": timing, "marginal_cases": marginal_cases}

    def marginal_case(self, h: dict, history: list[dict]) -> dict:
        """A candidate rejected only because its step improvement is within the tie tolerance of the threshold."""
        c = h["candidate"]
        base = max((x for x in history if x["feasible"] and x["candidate"]["n_doublets"] == c["n_doublets"]
                    and x["candidate"]["depth_m"] < c["depth_m"]), key=lambda x: x["candidate"]["depth_m"], default=None)
        t_wh = max(p["T_wellhead_C"] for p in h["well_points"])
        case = {"candidate": candidate_id(c), "depth_m": c["depth_m"], "emissions_t": h["summary"]["emissions_t"],
                "T_wellhead_max_C": t_wh, "pvt_temperature_max_C": 100.0, "reason": h["verdict"]["reason"]}
        if base is not None:
            b = base["summary"]
            case.update(from_depth_m=base["candidate"]["depth_m"],
                        emissions_change=(h["summary"]["emissions_t"] - b["emissions_t"]) / b["emissions_t"],
                        marginal_abatement_t_per_yr_per_m=(b["emissions_t"] - h["summary"]["emissions_t"]) / (h["summary"]["drilled_m"] - b["drilled_m"]),
                        T_wellhead_max_from_C=max(p["T_wellhead_C"] for p in base["well_points"]))
            case["text"] = (f"{case['candidate']} ({c['depth_m']:g} m) changes emissions {case['emissions_change'] * 100:+.3f}% vs "
                            f"{case['from_depth_m']:g} m ({case['marginal_abatement_t_per_yr_per_m']:.2f} t CO2/yr per extra metre), within the "
                            f"tie tolerance of the 5% threshold, so it is not taken (drilling cost and risk not modelled); its wellhead reaches "
                            f"{t_wh:.1f} C vs {case['T_wellhead_max_from_C']:.1f} C at {case['from_depth_m']:g} m, further above the 100 C "
                            f"brine-property (PVTConstantSTP) range.")
        else:
            case["text"] = f"{case['candidate']}: {case['reason']}."
        return case


# --- trace -------------------------------------------------------------------------------
def judges_tests(entries: list[dict]) -> list[dict]:
    a = [e for e in entries if e["scenario"] == "A_missing_input"]
    b = [e for e in entries if e["scenario"] == "B_design"]
    halt = next((e for e in a if e["phase"] == "halt"), None)
    rejected = next((e for e in b if e["phase"] == "validate" and any(v.get("check") == "flow_range" and v.get("value", 0) >= 350 for v in e["data"]["violations"])), None)
    revise_after = next((e for e in b if rejected and e["phase"] == "revise" and e["step"] == rejected["step"] + 1), None)
    temp = next((e for e in b if e["phase"] == "temperature_assessment"), None)
    depths = sorted({e["data"]["metrics"]["reservoir_temperature_C"] for e in b if e["phase"] == "evaluate"})
    final = next((e for e in b if e["phase"] == "final"), None)
    evals = [e for e in b if e["phase"] == "evaluate"]
    failed = next((e for e in evals if not e["data"]["feasible"]), None)
    ranked_out = [e for e in b if e["phase"] == "propose" and "ranked out" in (e["rationale"] or "")]
    recovered = next((e for e in evals if failed and e["step"] > failed["step"] and e["data"]["feasible"]), None)
    return [
        {"test": "(i) missing physical quantity -> stop and ask", "pass": halt is not None and "heating return temperature" in halt["data"]["missing"],
         "evidence": f"step {halt['step']}: {halt['rationale']}" if halt else "no halt"},
        {"test": "(ii) >= 350 m3/h per doublet -> rejected with reason, revised", "pass": rejected is not None and revise_after is not None,
         "evidence": (f"step {rejected['step']}: {rejected['rationale']} -> step {revise_after['step']}: {revise_after['title']}") if rejected and revise_after else "not triggered"},
        {"test": "(iii) 87 C reservoir vs 100 C supply -> shortfall stated, deeper well vs surface upgrade decided",
         "pass": temp is not None and len(depths) > 1 and final is not None,
         "evidence": (f"step {temp['step']} (assessment); candidates evaluated at reservoir temperatures {depths} C; step {final['step']} (decision)") if temp and final else "missing"},
        {"test": "(iv) recovery after a failed / ranked-out candidate", "pass": (failed is not None and recovered is not None) or bool(ranked_out),
         "evidence": ((f"step {failed['step']}: {failed['title']} infeasible ({', '.join(failed['data']['failing'])}) -> step {recovered['step']}: {recovered['title']} feasible")
                      if failed and recovered else "") + (f"; ranked-out recoveries at steps {[e['step'] for e in ranked_out]}" if ranked_out else "") or "not triggered"},
    ]


def esp_cell(m: dict) -> str:
    if m.get("esp_setting_depth_m") is None:
        return "650 (fixed) / -"
    return f"{m['esp_setting_depth_m']:g} / {m['esp_intake_at_max_flow_bar']:.1f}"


def stop_reasoning(e: dict) -> str | None:
    """The backend's own stop rationale, from the logged reply (logs written before it was stored on the event)."""
    for c in (e.get("data") or {}).get("backend_calls", []):
        match = re.search(r"\{.*\}", c.get("reply") or "", re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0)).get("rationale")
            except json.JSONDecodeError:
                pass
    return None


def evaluation_table(entries, scenario="B_design") -> list[str]:
    rows = ["| # | Candidate | T_res (C) | ESP set (m) / intake (bar) | Feasible | External gas (GWh) | Emissions (t) | Grid import (GWh) | Drilled (m) | Wall (s) | Final verdict |",
            "|---|---|---|---|---|---|---|---|---|---|---|"]
    ranks = next((e["data"] for e in reversed(entries) if e["scenario"] == scenario and e["phase"] == "rank"), {})
    for e in (x for x in entries if x["scenario"] == scenario and x["phase"] == "evaluate"):
        m, name = e["data"]["metrics"], e["title"].split(": ", 1)[1]
        v = ranks.get(name, {})
        rows.append(f"| {e['data']['evaluation']} | {name} | {m['reservoir_temperature_C']:.0f} | {esp_cell(m)} | {'yes' if e['data']['feasible'] else 'no (' + ', '.join(e['data']['failing']) + ')'} | "
                    f"{m['external_gas_fuel_GWh']:.3f} | {m['emissions_t']:.0f} | {m['grid_import_GWh']:.2f} | {m['drilled_m']:.0f} | "
                    f"{e['data']['wall_s']:.1f}{' (cached)' if e['data']['cached'] else ''} | {v.get('status', '-')} (rank {v.get('rank', '-')}) |")
    return rows


def write_trace(path, entries, backend, results, note=None):
    lines = [f"# Design agent trace ({backend} backend)", "",
             f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC from `decision_log.jsonl` ({len(entries)} logged steps). "
             f"Rerun: `$env:PYTHONPATH=\"src\"; py -3.11 -m poetry run python hackathon_work/design_agent.py --backend {backend}`.", ""]
    if note:
        lines += [f"> **Note:** {note}", ""]
    tests = judges_tests(entries)
    lines += ["## Judges' agent-reasoning tests", "", "| Test | Result | Evidence |", "|---|---|---|"]
    lines += [f"| {t['test']} | {'PASS' if t['pass'] else 'FAIL'} | {t['evidence']} |" for t in tests]
    b = results.get("B_design", {})
    lines += ["", "## Evaluations (scenario B)", ""] + evaluation_table(entries)
    if b.get("status") == "selected":
        t = b["timing"]
        lines += ["", "## Final pick", "", b["conclusion"], ""]
        if b.get("marginal_cases"):
            lines += ["## Marginal sensitivity cases", "",
                      "Rejected only because the step improvement is within the tie tolerance of the 5% threshold, which counts as not met "
                      "(conservative: drilling cost and risk are not modelled).", "",
                      "| Candidate | Step | Emissions change | Abatement (t/yr per m) | Wellhead T max (C) |", "|---|---|---|---|---|"]
            lines += [f"| {m['candidate']} | {m.get('from_depth_m', float('nan')):g} -> {m['depth_m']:g} m | {m.get('emissions_change', float('nan')) * 100:+.3f}% | "
                      f"{m.get('marginal_abatement_t_per_yr_per_m', float('nan')):.2f} | {m['T_wellhead_max_C']:.1f} "
                      f"(vs {m.get('T_wellhead_max_from_C', float('nan')):.1f}; PVT range <= 100) |" for m in b["marginal_cases"]]
            lines.append("")
        lines += ["## Runtime", "",
                  f"- Annual evaluations: {t['evaluations']} ({t['computed']} computed, {t['cached']} from cache); "
                  f"computed wall time mean {t['wall_s_per_computed_evaluation_mean'] or 0:.1f} s, max {t['wall_s_per_computed_evaluation_max'] or 0:.1f} s",
                  f"- Scenario B runtime: {t['scenario_runtime_s']:.1f} s; scenario A runtime: "
                  + (f"{results['A_missing_input']['runtime_s']:.1f} s" if results.get("A_missing_input", {}).get("runtime_s") is not None else "not logged"),
                  f"- Backend calls: {t['backend_calls']} ({t['backend_wall_s']:.1f} s)"]
        calls = [c for e in entries for c in (e["data"] or {}).get("backend_calls", []) if isinstance(e["data"], dict)]
        if calls:
            lines += ["", "| Call | Purpose | Wall (s) | Input tokens | Cache read | Output tokens | Cost (USD) |", "|---|---|---|---|---|---|---|"]
            for i, c in enumerate(calls, 1):
                u = c.get("usage") or {}
                lines.append(f"| {i} | {c['purpose']} | {c['wall_s']:.1f} | {u.get('input_tokens', '-')} | {u.get('cache_read_input_tokens', '-')} | "
                             f"{u.get('output_tokens', '-')} | {c.get('total_cost_usd') if c.get('total_cost_usd') is not None else '-'} |")
    scenario_titles = {"A_missing_input": "Scenario A: heating return temperature removed from the inputs",
                       "B_design": "Scenario B: complete inputs, design loop"}
    for scenario, title in scenario_titles.items():
        lines += ["", f"## {title}", ""]
        for e in (x for x in entries if x["scenario"] == scenario):
            lines.append(f"**{e['step']}. [{e['phase']}] {e['title']}**")
            rationale = e["rationale"]
            if e["phase"] == "stop" and (model_reason := stop_reasoning(e)) and model_reason != rationale:
                rationale = f"Backend's own stop reasoning: {model_reason}"
            if rationale:
                lines.append(f"> {rationale}")
            if e["phase"] == "required_inputs":
                lines += ["", "| Input | Present | Source | Needed for |", "|---|---|---|---|"]
                lines += [f"| {c['input']} | {'yes' if c['present'] else '**MISSING**'} | {c['source']} | {c['needed_for']} |" for c in e["data"]["checked"]]
            if e["phase"] == "well_check":
                lines += ["", "| Flow (m3/h) | ESP Hz | Wellhead (bar / C) | p_sat (bar) | ESP intake / discharge (bar) | ESP power (MW) | BHP (bar) | Tubing v (m/s) |",
                          "|---|---|---|---|---|---|---|---|"]
                lines += [f"| {p['flow_m3h']:.0f} | {p['esp_freq_hz']:.1f} | {p['wellhead_pressure_bar']:.2f} / {p['T_wellhead_C']:.1f} | {p['p_sat_at_T_wellhead_bar']:.2f} | "
                          f"{p['esp_intake_bar']:.1f} / {p['esp_discharge_bar']:.1f} | {p['esp_power_MW']:.3f} | {p['bottomhole_pressure_bar']:.1f} | {p['tubing_velocity_m_s']:.1f} |"
                          for p in e["data"]["points"]]
            if e["phase"] == "rank":
                lines += ["", "| Candidate | Rank | Verdict | Reason |", "|---|---|---|---|"]
                lines += [f"| {name} | {v['rank']} | {v['status']} | {v['reason']} |" for name, v in sorted(e["data"].items(), key=lambda kv: kv[1]["rank"])]
            lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return tests


def retrace(out_dir: Path, backend: str, note: str):
    """Rebuild agent_trace.md from a saved run (no backend calls, no simulation)."""
    entries = [json.loads(line) for line in (out_dir / "decision_log.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    final = next((e for e in reversed(entries) if e["scenario"] == "B_design" and e["phase"] == "final"), None)
    results = {"A_missing_input": {}, "B_design": {"status": "selected", "timing": final["data"]["timing"], "conclusion": final["rationale"]}
               if final and final["data"].get("timing") else {}}
    write_trace(out_dir / "agent_trace.md", entries, backend, results, note=note)
    print(f"rebuilt {(out_dir / 'agent_trace.md').relative_to(REPO)} from {len(entries)} logged steps")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--backend", choices=sorted(BACKENDS), default="rules")
    parser.add_argument("--budget", type=int, default=14, help="maximum annual evaluations in scenario B")
    parser.add_argument("--clear-cache", action="store_true", help="recompute every annual evaluation (honest timings)")
    parser.add_argument("--retrace", metavar="NOTE", help="only rebuild agent_trace.md from the saved decision_log.jsonl, with this note")
    args = parser.parse_args()

    out_dir = AGENT_OUT if args.backend == "rules" else AGENT_OUT / args.backend
    if args.retrace:
        retrace(out_dir, args.backend, args.retrace)
        return
    if args.clear_cache and CACHE.exists():
        shutil.rmtree(CACHE)
    start = time.perf_counter()
    backend = BACKENDS[args.backend](out_dir)
    log = DecisionLog(out_dir / "decision_log.jsonl", backend.name)
    results = {}

    project_missing = load_json(PROJECT_PATH)
    project_missing["boundary_inputs"] = [b for b in project_missing["boundary_inputs"]
                                          if not (b["component"] == "heat_exchanger" and b["key"] == "secondary_temperature_in")]
    results["A_missing_input"] = DesignAgent(backend, log, out_dir, args.budget).run("A_missing_input", project_missing)
    results["B_design"] = DesignAgent(backend, log, out_dir, args.budget).run("B_design")
    total = time.perf_counter() - start

    tests = write_trace(out_dir / "agent_trace.md", log.entries, backend.name, results)
    b = results["B_design"]
    summary = {"backend": backend.name, "total_runtime_s": total, "status": b["status"], "timing": b.get("timing"),
               "pick": b["pick"]["candidate"] if b.get("pick") else None, "pick_summary": {k: b["pick"]["summary"][k] for k in
               ("external_gas_fuel_GWh", "emissions_t", "grid_import_GWh", "drilled_m", "reservoir_temperature_C")} if b.get("pick") else None,
               "evaluated": [{"candidate": h["candidate"], "feasible": h["feasible"], "verdict": h["verdict"]} for h in b.get("history", [])],
               "marginal_cases": b.get("marginal_cases", []), "judges_tests": tests, "backend_calls": backend.calls}
    (out_dir / "run_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    print(f"[{backend.name}] Scenario A: {results['A_missing_input']['status']}")
    print(f"[{backend.name}] Scenario B: {b['status']}, {len(b.get('history', []))} annual evaluations, total runtime {total:.1f} s")
    print("\n".join(evaluation_table(log.entries)))
    if b.get("status") == "selected":
        print(f"FINAL: {b['conclusion']}")
        print(f"TIMING: {json.dumps(b['timing'])}")
    for t in tests:
        print(f"  {'PASS' if t['pass'] else 'FAIL'} {t['test']}")
    print(f"LOGS: {(out_dir / 'decision_log.jsonl').relative_to(REPO)}, {(out_dir / 'agent_trace.md').relative_to(REPO)}")


if __name__ == "__main__":
    main()
