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
  A. inputs with one or more REQUIRED_INPUTS removed (--remove, default
     heating_return_T): the agent must stop and ask instead of inventing the
     value (deterministic input check, no backend call; --interactive asks in
     the terminal and continues with the answers);
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
import csv
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

# Inputs the design needs that are not in the organizers' data. The agent checks every one at
# startup and never invents a value: a missing one is asked for (--interactive) or the run stops
# with the full list. "targets" are the places the value lives: ("project"|"settings", path),
# where a dict in the path selects the matching list element; the first target is checked.
# Ranges are ASSUMED plausibility bounds for validating an answer, not design values.
def _bnd(component, key):
    return ("boundary_inputs", {"component": component, "key": key}, "value")


REQUIRED_INPUTS = [
    {"name": "heating_return_T", "label": "heating return temperature", "unit": "C", "min": 40.0, "max": 80.0, "provenance": "ASSUMED",
     "why": "sets district water flow = Q / (cp * (100 - T_return)) and the HEX/heat-pump lift",
     "range_reason": "a district heating return for a 100 C supply is typically 40-80 C: below 40 C is atypical for a 100 C "
                     "network, above 80 C leaves less than 20 K for the district water and the HEX/heat-pump lift",
     "targets": [("project", _bnd("heat_exchanger", "secondary_temperature_in")), ("project", _bnd("chp", "temperature_in"))]},
    {"name": "cooling_return_T", "label": "cooling return temperature", "unit": "C", "min": 21.0, "max": 35.0, "provenance": "ASSUMED",
     "why": "sets the chilled-water temperature glide (20 C OFFICIAL supply) and so the chiller duty",
     "range_reason": "it must be above the 20 C supply; district cooling returns are typically 24-30 C",
     "targets": [("settings", ("cooling_supply_return_C", 1))]},
    {"name": "brine_cp", "label": "brine specific heat", "unit": "J/(kg K)", "min": 3500.0, "max": 4300.0, "provenance": "ASSUMED",
     "why": "enters every heat balance (HEX, absorption drive, heat pump source, boiler, CHP)",
     "range_reason": "saline brines are slightly below pure water (4180-4217 J/(kg K)); below ~3500 would need a salinity not in the inputs",
     "targets": [("project", ("_brine_pvt_override", "CPL"))]
                + [("project", ("components", c, "parameters", "specific_heat")) for c in ("heat_exchanger", "boiler", "chp")]},
    {"name": "absorption_COP", "label": "absorption chiller COP (thermal)", "unit": "-", "min": 0.5, "max": 1.4, "provenance": "ASSUMED",
     "why": "sets the brine drive heat per MW of cooling at the hot end",
     "range_reason": "single-effect LiBr chillers reach 0.5-0.8, double-effect up to ~1.4",
     "targets": [("settings", ("absorption_chiller", "cop_th"))]},
    {"name": "absorption_drive_inlet_T", "label": "absorption chiller minimum drive inlet temperature", "unit": "C", "min": 65.0, "max": 100.0,
     "provenance": "ASSUMED", "why": "decides on which days the brine is hot enough to drive the absorption chiller",
     "range_reason": "single-effect hot-water-fired chillers need ~65-95 C; above 100 C the brine (<= ~105 C wellhead) could never drive it",
     "targets": [("settings", ("absorption_chiller", "min_drive_inlet_C"))]},
    {"name": "absorption_drive_outlet_T", "label": "absorption chiller minimum drive outlet temperature", "unit": "C", "min": 55.0, "max": 95.0,
     "provenance": "ASSUMED", "why": "limits how much drive heat the brine can give the chiller (drive-water glide)",
     "range_reason": "typical single-effect glides are 5-15 K below the drive inlet (e.g. 80/70 C)",
     "targets": [("settings", ("absorption_chiller", "min_drive_outlet_C"))]},
    {"name": "electric_chiller_COP", "label": "electric chiller COP", "unit": "-", "min": 2.5, "max": 8.0, "provenance": "ASSUMED",
     "why": "sets the electricity (and emissions) of the cooling the absorption chiller does not cover",
     "range_reason": "water-cooled electric chillers at a 20 C supply are typically COP 3-7",
     "targets": [("settings", ("electric_chiller_cop",))]},
    {"name": "hp_eta_lorenz", "label": "heat pump Lorenz efficiency", "unit": "-", "min": 0.3, "max": 0.7, "provenance": "ASSUMED",
     "why": "sets the heat pump COP for the lift to 100 C, and so its electricity",
     "range_reason": "industrial heat pumps reach 0.4-0.6 of the Lorenz COP",
     "targets": [("settings", ("heat_pump", "eta_lorenz"))]},
    {"name": "hp_cop_cap", "label": "heat pump COP cap", "unit": "-", "min": 3.0, "max": 10.0, "provenance": "ASSUMED",
     "why": "caps the heat pump COP at small lifts, where the Lorenz COP is unrealistically high",
     "range_reason": "real high-temperature heat pumps rarely exceed COP 6-8",
     "targets": [("settings", ("heat_pump", "cop_cap"))]},
    {"name": "produced_gas_EF", "label": "produced gas emission factor", "unit": "kg CO2/GJ", "min": 50.0, "max": 100.0, "provenance": "DERIVED",
     "why": "sets the CO2 of the produced gas burned in CHP/boiler or flared (combustion + CO2 pass-through)",
     "range_reason": "methane combustion alone is ~55 kg/GJ; the produced gas carries extra CO2, so higher values are plausible",
     "targets": [("project", ("components", c, "parameters", "gas_emission_factor")) for c in ("boiler", "chp")]},
    {"name": "external_gas_EF", "label": "external (pipeline) gas emission factor", "unit": "kg CO2/GJ", "min": 50.0, "max": 60.0,
     "provenance": "ASSUMED", "why": "sets the CO2 of the boiler top-up gas (external gas)",
     "range_reason": "pipeline natural gas is 55-57 kg CO2/GJ",
     "targets": [("settings", ("external_gas", "emission_factor_kg_per_GJ"))]},
    {"name": "electricity_EF", "label": "grid electricity emission factor", "unit": "kg CO2/kWh", "min": 0.0, "max": 1.0, "provenance": "ASSUMED",
     "why": "sets the CO2 of the ESP, heat pump and chiller electricity",
     "range_reason": "grid factors range from ~0 (renewable) to ~1 (coal)",
     "targets": [("project", ("components", "producer_well", "parameters", "esp", "electricity_emission_factor"))]},
]
REQUIRED_BY_NAME = {r["name"]: r for r in REQUIRED_INPUTS}


def unit_text(unit: str) -> str:
    """' C', ' kg CO2/GJ', or '' for a dimensionless input."""
    return "" if unit == "-" else f" {unit}"


def _walk(root, path, create=False):
    """Follow ``path`` in nested dicts/lists; a dict step selects the matching list element."""
    for step in path:
        if isinstance(step, dict):
            match = next((x for x in root if all(x.get(k) == v for k, v in step.items())), None)
            if match is None:
                if not create:
                    raise KeyError(step)
                match = dict(step)
                root.append(match)
            root = match
        else:
            root = root[step]
    return root


def get_input(roots: dict, spec: dict):
    where, path = spec["targets"][0]
    try:
        return _walk(roots[where], path)
    except (KeyError, IndexError, TypeError):
        raise KeyError(spec["name"]) from None


def remove_input(roots: dict, spec: dict):
    """Delete every place the value lives (demo of a missing input)."""
    for where, path in spec["targets"]:
        try:
            parent = _walk(roots[where], path[:-1])
        except (KeyError, IndexError, TypeError):
            continue
        last = path[-1]
        if len(path) > 1 and isinstance(path[-2], dict) and last == "value":  # a boundary input: drop the whole entry
            _walk(roots[where], path[:-2]).remove(parent)
        elif isinstance(parent, list) and last < len(parent):
            parent.pop(last)
        elif isinstance(parent, dict):
            parent.pop(last, None)


def set_input(roots: dict, spec: dict, value: float):
    for where, path in spec["targets"]:
        parent = _walk(roots[where], path[:-1], create=True)
        if isinstance(parent, list) and path[-1] >= len(parent):
            parent.append(value)
        else:
            parent[path[-1]] = value


def design_space(settings: dict) -> dict:
    r = settings["ranking"]
    return {
        "n_doublets": [1, 2, 3],
        "flow_cap_m3h": [50, 300],          # continuous range, challenge hard limits
        "esp": sorted(settings["esp_options"]),
        "hex_ua_W_K": [250e3, 500e3, 1000e3],
        "depth_m": {"min": 2500, "max": r["max_depth_m"], "step": r["depth_step_m"]},
        "gas_handling": settings["gas_handling"]["options"],
    }


GAS_TAGS = {"co2_reinject": "co2ri", "reinject_all": "allri"}  # chp (the default) keeps the plain id


def candidate_id(c: dict) -> str:
    gas = GAS_TAGS.get(c.get("gas_handling", "chp"), "")
    return f"n{c['n_doublets']}_q{c['flow_cap_m3h']:g}_{c['esp']}_ua{c['hex_ua_W_K'] / 1e3:.0f}_z{c['depth_m']:g}" + (f"_{gas}" if gas else "")


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
                f"Recovery: {candidate_id(last['candidate'])} failed ({failed}); add a doublet to share the load."))
        if incumbent is None:
            return None
        # External gas is the first ranking criterion: a feasible plant that leans on gas backup is compared
        # with n + 1 doublets (staggered maintenance) before its other design variables are refined.
        s, n = incumbent["summary"], incumbent["candidate"]["n_doublets"]
        if (len(history) == 1 and n < space["n_doublets"][-1]
                and s["external_gas_fuel_GWh"] > max(0.01, 0.01 * s["heating_demand_GWh"])):
            cap = s["capacity_MW"]
            return self._baseline(ctx, n + 1, (
                f"{candidate_id(incumbent['candidate'])} is feasible (the 330-day rule limits the geothermal source; backup may "
                f"cover the outage - organizer clarification 2026-11-01), but it has {s['days_without_geothermal']} day(s) "
                f"without geothermal supply and needs {s['external_gas_fuel_GWh']:.1f} GWh of external gas with a "
                f"{cap['boiler_th']:.1f} MWth backup boiler and a {cap['electric_chiller_cool']:.1f} MWcool electric chiller. "
                f"External gas ranks first, so compare {n + 1} doublets with staggered maintenance before refining "
                f"the {n}-doublet design."))

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
            # Gas handling is compared at the accepted depth; if one is accepted the depth ladder re-opens
            # (its token is per gas mode), because it shifts the emissions baseline of the 5% depth rule.
            ("gas_handling", "co2_reinject", "Gas handling (b): separate the 20 mol% CO2 and reinject it with the brine, CH4 to CHP. Only CH4 "
                                             "combustion CO2 counts (54.9 vs 68.6 kg/GJ, DERIVED); costs ~0.1 kWh/kg CO2 separation + compression "
                                             "(ASSUMED). If accepted, the depth ladder re-opens: the lower emissions baseline changes the 5% depth rule."),
            ("gas_handling", "reinject_all", "Gas handling (c): reinject all produced gas, no combustion: no produced-gas CO2, but no CHP heat "
                                             "or electricity, so the heat pump must cover the whole lift (external gas if it cannot)."),
            ("n_doublets", base["n_doublets"] + 1, "More doublets: accepted only if external gas or emissions improve by >= 5%."),
            ("n_doublets", 1, "Single doublet at the accepted depth and settings: check whether depth rescues one doublet; it still needs "
                              "backup on its 35 maintenance days, so the ranking decides on external gas."),
        ]
        tried = ctx["tried_variants"]
        for key, value, why in variants:
            token = key if key in ("hex_ua_W_K", "esp") else f"{key}={value}"
            if key == "depth_step":
                token = f"depth_step@{base.get('gas_handling', 'chp')}"
            if key == "n_doublets" and value == base["n_doublets"] + 1:
                token = "n_doublets+1"
            if token in tried:
                continue
            if key == "depth_step":
                if last is not incumbent and last["candidate"]["depth_m"] > base["depth_m"]:
                    tried.add(token)
                    notes.append(f"Depth step to {last['candidate']['depth_m']:g} m failed the parsimony rule; stop exploring deeper "
                                 f"(accepted depth stays {base['depth_m']:g} m).")
                    continue
                d = base["depth_m"] + depth["step"]
                if d > depth["max"]:
                    tried.add(token)
                    notes.append(f"Depth ladder reached the {depth['max']:g} m limit of the design space.")
                    continue
                if candidate_id({**base, "depth_m": d}) in evaluated:
                    tried.add(token)
                    continue
                t_res = ctx["inputs"]["reservoir"]["surface_temperature_C"] + ctx["inputs"]["reservoir"]["gradient_C_per_km"] * d / 1000
                return {"candidate": {**base, "depth_m": d}, "rationale": " ".join(notes) + (
                    f" Depth ladder from incumbent {candidate_id(base)}: {base['depth_m']:g} -> {d:g} m (reservoir {t_res:.1f} C) to cut the "
                    f"heat-pump lift; accepted only if emissions improve >= 5% vs the {base['depth_m']:g} m design.")}
            candidate = {**base, key: value}
            tried.add(token)
            if (key == "n_doublets" and not space["n_doublets"][0] <= value <= space["n_doublets"][-1]) or candidate_id(candidate) in evaluated:
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
            "\"esp\": string, \"hex_ua_W_K\": number, \"depth_m\": number, \"gas_handling\": string (one of design_space.gas_handling)}, "
            "\"rationale\": string}.\n\nSTATE:\n" + self._context_text(ctx))
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


def dissolution_row(d: dict | None) -> dict | None:
    """Compact gas_solubility result for logs and tables (conservative salinity)."""
    if not d:
        return None
    wh, res = d["points"]["wellhead@reservoir"], d["points"]["reservoir@reservoir"]
    return {"status": d["check"]["status"], "wellhead_margin": wh["margin"], "reservoir_margin": res["margin"],
            "wellhead_bar_g": wh["p_bar_g"], "wellhead_T_C": wh["t_c"], "bubble_point_wellhead_bar_g": wh["bubble_point_bar_g"],
            "dip_tube_depth_m": d["dip_tube_depth_m"], "compression_kWh_per_kg_derived": d["compression_kWh_per_kg_derived"],
            "compression_kWh_per_kg_assumed": d["compression_kWh_per_kg_assumed"], "reason": d["check"]["reason"]}


# --- agent -------------------------------------------------------------------------
class DesignAgent:
    def __init__(self, backend, log: DecisionLog, out_dir: Path, budget: int = 16, interactive: bool = False):
        self.backend = backend
        self.log = log
        self.out_dir = out_dir
        self.budget = budget
        self.interactive = interactive
        self.project_path = PROJECT_PATH  # replaced by the completed project once the user answers
        self.challenge_path = CHALLENGE_PATH  # replaced only by sensitivity runs (e.g. the geothermal gradient)
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
            ("cooling supply temperature", lambda: self.settings["cooling_supply_return_C"][0], "OFFICIAL (20 C)", "chilled-water supply"),
            ("well inner diameter / roughness", lambda: [project["components"]["producer_well"]["parameters"]["trajectory_table"][-1]["ID"],
                                                         project["components"]["producer_well"]["parameters"]["roughness_m"]],
             "ASSUMED, user-approved", "friction, pump power"),
        ]
        checked = [{"input": name, "present": get(fn) is not None, "value": get(fn), "source": src, "needed_for": why} for name, fn, src, why in items]
        roots = {"project": project, "settings": self.settings}
        for r in REQUIRED_INPUTS:
            value = get(lambda: get_input(roots, r))
            checked.append({"input": r["name"], "label": r["label"], "present": value is not None, "value": value, "unit": r["unit"],
                            "source": r["provenance"], "needed_for": r["why"], "range": [r["min"], r["max"]]})
        missing = [c for c in checked if not c["present"]]
        self.log.event(scenario, "required_inputs", "Check required inputs",
                       data={"checked": checked, "missing": [m["input"] for m in missing]},
                       rationale="All required inputs present." if not missing else
                       f"{len(missing)} required input(s) missing: {', '.join(m['input'] for m in missing)}.")
        return missing

    def project_key(self):
        """Cache-key part for the project / challenge files: None for the official ones, else their content hashes."""
        if self.project_path == PROJECT_PATH and self.challenge_path == CHALLENGE_PATH:
            return None
        return [hashlib.sha1(path.read_bytes()).hexdigest()[:16] for path in (self.project_path, self.challenge_path)]

    # 2b. human in the loop (--interactive): ask for missing inputs instead of halting
    def ask_user(self, scenario, missing, project) -> bool:
        """Ask in the terminal for each missing required input, validate it, write the completed
        project / settings files and use them for every evaluation. Returns False if nothing was answered."""
        answered = set()
        roots = {"project": project, "settings": self.settings}
        for m in missing:
            spec = REQUIRED_BY_NAME.get(m["input"])
            if spec is None:
                continue
            question = (f"I cannot size the plant without the {spec['label']} ({spec['name']}, {spec['provenance']}). "
                        f"It is needed because it {spec['why']}. "
                        f"It is not in the organizers' inputs and I will not invent it. "
                        f"Please type a value{' in ' + spec['unit'] if spec['unit'] != '-' else ''} (plausible range {spec['min']:g}-{spec['max']:g}{unit_text(spec['unit'])}), or 'q' to stop.")
            attempt = 0
            while True:
                attempt += 1
                self.log.event(scenario, "ask", "AGENT ASKED", rationale=question,
                               data={"input": m["input"], "attempt": attempt, "range": [spec["min"], spec["max"]], "unit": spec["unit"]})
                print(f"\nAGENT ASKED: {question}", flush=True)
                try:
                    raw = input(f"USER ANSWER ({m['input']}, {spec['unit']}) > ").strip().lstrip("﻿")  # BOM from a PowerShell pipe
                except EOFError:
                    raw = "q"
                value, reason = self.validate_answer(raw, spec)
                if raw.lower() in ("q", "quit", "stop"):
                    self.log.event(scenario, "answer", "USER ANSWERED", rationale=f"'{raw}': the user stopped the run; the agent halts without the value.",
                                   data={"input": m["input"], "raw": raw, "valid": False, "stopped": True})
                    print("AGENT: stopping without the value, as asked.", flush=True)
                    return False
                self.log.event(scenario, "answer", "USER ANSWERED", rationale=f"'{raw}': " + (f"accepted, {value:g}{unit_text(spec['unit'])}." if value is not None else f"rejected - {reason}"),
                               data={"input": m["input"], "raw": raw, "valid": value is not None, "value": value, "reason": reason})
                if value is not None:
                    print(f"AGENT: thank you - using {spec['name']} = {value:g}{unit_text(spec['unit'])}.", flush=True)
                    break
                print(f"AGENT: I cannot use '{raw}': {reason}. Let me ask again.", flush=True)
            set_input(roots, spec, value)
            stamp = f"USER ANSWER (interactive, {datetime.now(timezone.utc).isoformat()})"
            for where in {w for w, _ in spec["targets"]}:
                roots[where].setdefault("_user_answers", {})[spec["name"]] = {"value": value, "unit": spec["unit"], "source": stamp}
                answered.add(where)
        if "project" in answered:
            self.project_path = self.out_dir / "project_with_user_answers.json"
            self.project_path.write_text(json.dumps(project, indent=2), encoding="utf-8")
        if "settings" in answered:  # self.settings is used directly (and is part of the cache key); saved for the record
            (self.out_dir / "settings_with_user_answers.json").write_text(json.dumps(self.settings, indent=2), encoding="utf-8")
        if answered:
            print("AGENT: all missing inputs answered - continuing the design loop.", flush=True)
        return bool(answered)

    @staticmethod
    def validate_answer(raw: str, spec: dict):
        """(value, None) for a number inside the plausible range, else (None, reason)."""
        match = re.fullmatch(r"\s*([-+]?\d+(?:[.,]\d+)?)\s*(.*?)\s*", raw)
        unit = re.sub(r"[\s°]", "", spec["unit"]).lower()
        if not match or match.group(2) and re.sub(r"[\s°]", "", match.group(2)).lower() not in (unit, "-"):
            example = f"{(spec['min'] + spec['max']) / 2:.3g}"
            return None, f"it is not a number{' in ' + spec['unit'] if spec['unit'] != '-' else ''} (expected e.g. {example}{unit_text(spec['unit'])})"
        value = float(match.group(1).replace(",", "."))
        if not spec["min"] <= value <= spec["max"]:
            return None, (f"{value:g}{unit_text(spec['unit'])} is outside the plausible {spec['min']:g}-{spec['max']:g}{unit_text(spec['unit'])} range "
                          f"({spec['range_reason']})")
        return value, None

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
        if candidate.get("gas_handling", "chp") not in self.space["gas_handling"]:
            violations.append({"variable": "gas_handling", "value": candidate["gas_handling"],
                               "reason": f"{candidate['gas_handling']} not in design space {self.space['gas_handling']}"})
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
        key = hashlib.sha1(json.dumps({"candidate": candidate, "settings": self.settings, "project": self.project_key()},
                                      sort_keys=True, default=str).encode()).hexdigest()[:16]
        cache_path = CACHE / f"{key}.json"
        start = time.perf_counter()
        plant = Plant({"name": candidate_id(candidate), **candidate}, self.settings, self.project_path, self.challenge_path)
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

    def run(self, scenario: str, project: dict | None = None, settings: dict | None = None, removed: list[str] | None = None) -> dict:
        run_start = time.perf_counter()
        project = project if project is not None else load_json(self.project_path)
        if settings is not None:
            self.settings = settings
        challenge = load_json(self.challenge_path)
        self.log.event(scenario, "start", f"Scenario {scenario}: start", data={"backend": self.backend.name, "budget": self.budget, "design_space": self.space,
                                                                            **({"removed_inputs": removed} if removed else {})})
        inputs = self.interpret_inputs(scenario, project, challenge)
        missing = self.check_required_inputs(scenario, project, challenge)
        if missing and self.interactive:
            if self.ask_user(scenario, missing, project):
                inputs = self.interpret_inputs(scenario, project, challenge)  # with the answered values (e.g. brine cp)
            missing = self.check_required_inputs(scenario, project, challenge)
        if missing:
            def describe(m):
                if "range" not in m:
                    return f"'{m['input']}' ({m['source']}) is needed for {m['needed_for']}."
                return (f"'{m['input']}' ({m['label']}{',' + unit_text(m['unit']) if m['unit'] != '-' else ''}, {m['source']}) is needed because it "
                        f"{m['needed_for']}; plausible range {m['range'][0]:g}-{m['range'][1]:g}{unit_text(m['unit'])}.")
            question = (f"I cannot size the plant without {len(missing)} input(s): {', '.join(m['input'] for m in missing)}. "
                        + " ".join(describe(m) for m in missing)
                        + f" {'They are' if len(missing) > 1 else 'It is'} not in the organizers' inputs and I will not invent "
                        f"{'them' if len(missing) > 1 else 'it'}. Please provide {'values' if len(missing) > 1 else 'a value'} "
                        "(or rerun with --interactive to answer in the terminal).")
            self.log.event(scenario, "halt", "Stop and ask for the missing input", data={"status": "needs_input", "missing": [m["input"] for m in missing]},
                           rationale=question)
            return {"status": "needs_input", "question": question, "runtime_s": time.perf_counter() - run_start}

        assessment = self.assess_temperature(scenario, inputs)
        history, tried_variants = [], set()
        incumbent = None
        repeats = 0
        ranking_rule = ("hard constraints pass/fail; then minimize external gas -> emissions -> net grid import -> doublets -> drilled metres "
                        "(values within 1% / 0.1 GWh external gas / 10 t / 0.01 GWh grid are ties); an extra doublet is kept only if external gas or emissions improve >= 5%; "
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
                                         "el_esp_GWh", "esp_setting_depth_m", "esp_intake_at_max_flow_bar", "tubing_velocity_at_max_flow_m_s", "days_hex_bypass", "days_failing_daily_checks", "capacity_MW",
                                         "days_without_geothermal", "days_all_doublets_in_maintenance")}
            failing = sorted(set([c["check"] for c in s["annual_checks"] if c["status"] != "PASS"] + s["failing_checks"]))
            self.log.event(scenario, "evaluate", f"Annual model + constraint check: {candidate_id(candidate)}",
                           data={"evaluation": self.evaluations, "cached": result["cached"], "wall_s": result["wall_s"], "feasible": s["feasible"],
                                 "failing": failing, "annual_checks": s["annual_checks"], "metrics": metrics},
                           rationale=(f"{'FEASIBLE' if s['feasible'] else 'INFEASIBLE'}: external gas {s['external_gas_fuel_GWh']:.3f} GWh, "
                                      f"emissions {s['emissions_t']:.0f} t, grid import {s['grid_import_GWh']:.2f} GWh, drilled {s['drilled_m']:.0f} m"
                                      + (f"; fails {', '.join(failing)}" if failing else "")
                                      + (f"; {s['days_without_geothermal']} day(s) without geothermal supply, covered by backup "
                                         f"(boiler {s['capacity_MW']['boiler_th']:.1f} MWth, electric chiller {s['capacity_MW']['electric_chiller_cool']:.1f} MWcool peak)"
                                         if s["days_without_geothermal"] else "")
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
        self.write_final_design(incumbent)
        return {"status": "selected", "pick": incumbent, "history": history, "runtime_s": runtime, **final}

    def conclude(self, scenario, history, incumbent, runtime):
        steps = [e for e in self.log.entries if e["scenario"] == scenario and e["phase"] == "depth_step"]
        ladder = "; ".join(f"{e['data']['from_m']:g}->{e['data']['to_m']:g} m: {e['data']['emissions_change'] * 100:+.1f}%, "
                           f"{e['data']['marginal_abatement_t_per_yr_per_m']:.3f} t/yr/m "
                           f"({'kept' if e['data']['accepted'] else 'rejected, marginal' if e['data'].get('marginal') else 'rejected'})" for e in steps)
        marginal_cases = [self.marginal_case(h, history) for h in history if h["verdict"].get("marginal")]
        backup = [{"candidate": candidate_id(h["candidate"]), "n_doublets": h["candidate"]["n_doublets"], "status": h["verdict"]["status"],
                   "days_without_geothermal": h["summary"]["days_without_geothermal"],
                   "boiler_peak_MWth": h["summary"]["capacity_MW"]["boiler_th"],
                   "boiler_external_gas_peak_MWth": h["summary"]["capacity_MW"]["boiler_external_gas_th"],
                   "electric_chiller_peak_MWcool": h["summary"]["capacity_MW"]["electric_chiller_cool"],
                   "chp_peak_MWth": h["summary"]["capacity_MW"]["chp_th"],
                   "n_minus_1_boiler_MWth": h["summary"]["n_minus_1"][0]["boiler_MWth"],
                   "n_minus_1_electric_chiller_MWcool": h["summary"]["n_minus_1"][1]["electric_chiller_MWcool"],
                   "installed_boiler_MWth": h["summary"]["installed_backup_MW"]["boiler_th"],
                   "installed_electric_chiller_MWcool": h["summary"]["installed_backup_MW"]["electric_chiller_cool"],
                   "external_gas_GWh": h["summary"]["external_gas_fuel_GWh"], "emissions_t": h["summary"]["emissions_t"]}
                  for h in history if h["feasible"]]
        singles = [b for b in backup if b["n_doublets"] == 1]
        gas = self.gas_decision(scenario, history, incumbent)
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
                + "".join(f" Marginal sensitivity case: {m['text']}" for m in marginal_cases)
                + f" Gas handling: {gas['text']}"
                + f" N-1 (unplanned outage of one doublet, ASSUMED): " + "; ".join(
                    f"{c['case']} {c['date']}: boiler {c['boiler_MWth']:.1f} MWth, electric chiller {c['electric_chiller_MWcool']:.1f} MWcool"
                    for c in s["n_minus_1"])
                + f"; installed backup {s['installed_backup_MW']['boiler_th']:.1f} MWth boiler + {s['installed_backup_MW']['electric_chiller_cool']:.1f} "
                  f"MWcool electric chiller covers it."
                + "".join(f" One-doublet alternative {x['candidate']} (valid per the organizer clarification of 2026-11-01, backup covers the "
                          f"source outage): feasible with {x['days_without_geothermal']} day(s) without geothermal supply, installed backup "
                          f"{x['installed_boiler_MWth']:.1f} MWth boiler + {x['installed_electric_chiller_MWcool']:.1f} MWcool chiller, but "
                          f"{x['external_gas_GWh']:.1f} GWh external gas and {x['emissions_t']:.0f} t, so it is ranked out." for x in singles))
        self.log.event(scenario, "final", f"Final pick: {candidate_id(incumbent['candidate'])}",
                       data={"pick": incumbent["candidate"], "verdict": incumbent["verdict"], "reference": ref, "emissions_reduction_vs_reference": reduction,
                             "capacity_MW": s["capacity_MW"], "timing": timing, "marginal_cases": marginal_cases,
                             "backup_sizing": backup, "n_minus_1": s["n_minus_1"], "installed_backup_MW": s["installed_backup_MW"],
                             "gas_handling": gas}, rationale=text)
        return {"reference": ref, "emissions_reduction": reduction, "conclusion": text, "timing": timing, "marginal_cases": marginal_cases,
                "backup_sizing": backup, "n_minus_1": s["n_minus_1"], "installed_backup_MW": s["installed_backup_MW"], "gas_handling": gas}

    def gas_decision(self, scenario, history, incumbent) -> dict:
        """Compare the gas-handling options evaluated at the same doublets/depth/HEX/ESP and log the ranking reason."""
        groups = {}
        for h in history:
            c = h["candidate"]
            groups.setdefault(tuple(c[k] for k in ("n_doublets", "flow_cap_m3h", "esp", "hex_ua_W_K", "depth_m")), []).append(h)
        compared = max((g for g in groups.values() if len({x["candidate"].get("gas_handling", "chp") for x in g}) > 1), key=len, default=[])
        rows = [{"candidate": candidate_id(h["candidate"]), "gas_handling": h["candidate"].get("gas_handling", "chp"), "feasible": h["feasible"],
                 "external_gas_GWh": h["summary"]["external_gas_fuel_GWh"], "emissions_t": h["summary"]["emissions_t"],
                 "emissions_produced_gas_t": h["summary"]["emissions_produced_gas_t"], "grid_import_GWh": h["summary"]["grid_import_GWh"],
                 "el_gas_handling_GWh": h["summary"]["el_gas_handling_GWh"], "heat_chp_GWh": h["summary"]["heat_chp_GWh"],
                 "verdict": h["verdict"]["status"], "rank": h["verdict"]["rank"], "reason": h["verdict"]["reason"],
                 "dissolution": dissolution_row(h["summary"].get("gas_dissolution"))} for h in compared]
        chosen = incumbent["candidate"].get("gas_handling", "chp")
        if rows:
            best = min((r for r in rows if r["feasible"]), key=lambda r: r["rank"])  # the ranking rule's choice at this design
            lowest = min(rows, key=lambda r: r["emissions_t"])
            why = (" (without CHP heat the heat pump cannot cover the whole lift on the coldest days)"
                   if lowest["gas_handling"] == "reinject_all" else "")
            text = (f"options compared at {candidate_id({**compared[0]['candidate'], 'gas_handling': 'chp'})}: "
                    + "; ".join(f"{r['gas_handling']} external gas {r['external_gas_GWh']:.3f} GWh, {r['emissions_t']:.0f} t, grid "
                                f"{r['grid_import_GWh']:.2f} GWh" for r in rows)
                    + f". The ranking keeps {best['gas_handling']} at that design (external gas first, then emissions)"
                    + (f"; {lowest['gas_handling']} has the lowest emissions but needs more external gas "
                       f"({lowest['external_gas_GWh']:.3f} vs {best['external_gas_GWh']:.3f} GWh{why}), and external gas ranks first."
                       if lowest is not best and lowest["external_gas_GWh"] > best["external_gas_GWh"] else ".")
                    + f" Final pick uses {chosen}."
                    + "".join(f" Dissolution check ({r['gas_handling']}): {r['dissolution']['reason']}." for r in rows if r["dissolution"]))
        else:
            text = f"{chosen} (no alternative evaluated)."
        self.log.event(scenario, "gas_decision", f"Gas handling: {chosen}", data={"chosen": chosen, "options": rows}, rationale=text)
        return {"chosen": chosen, "options": rows, "text": text}

    def write_final_design(self, incumbent: dict):
        """Daily rows + summary of the pick in <out_dir>/final_design/ (the annual cache keeps summaries only)."""
        folder = self.out_dir / "final_design"
        folder.mkdir(parents=True, exist_ok=True)
        candidate = {"name": candidate_id(incumbent["candidate"]), **incumbent["candidate"]}
        plant = Plant(candidate, self.settings, self.project_path, self.challenge_path)
        result = plant.simulate_year(self.heating, self.cooling)
        with (folder / "daily.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(result["rows"][0]))
            writer.writeheader()
            writer.writerows(result["rows"])
        summary = dict(annual_summary(candidate, plant, result), ranking=incumbent["verdict"])
        (folder / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

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
def judges_tests(entries: list[dict], design_scenario: str = "B_design") -> list[dict]:
    a = [e for e in entries if e["scenario"] == "A_missing_input"]
    b = [e for e in entries if e["scenario"] == design_scenario]
    start = next((e for e in a if e["phase"] == "start"), None)
    removed = (start["data"] if start else {}).get("removed_inputs", ["heating_return_T"])
    halt = next((e for e in a if e["phase"] == "halt"), None)
    # logs written before REQUIRED_INPUTS name inputs by their label
    halted_for = {REQUIRED_BY_NAME.get(x, {}).get("name", x) for x in (halt["data"]["missing"] if halt else [])} \
        | {r["name"] for r in REQUIRED_INPUTS if halt and r["label"] in halt["data"]["missing"]}
    asked = [e for e in a if e["phase"] == "ask"]
    answers = {e["data"]["input"]: e for e in a if e["phase"] == "answer" and e["data"].get("valid")}
    def answered(r):
        return any(q["data"]["input"] in (r, REQUIRED_BY_NAME[r]["label"]) for q in asked) and (r in answers or REQUIRED_BY_NAME[r]["label"] in answers)
    answered_all = all(answered(r) for r in removed)
    # every >= 350 m3/h rejection with its revision; the one closest to 350 m3/h (the judges' example) first
    flow_rejections = []
    for e in b:
        values = [v.get("value", 0) for v in (e["data"] or {}).get("violations", []) if e["phase"] == "validate" and v.get("check") == "flow_range"]
        revise = next((r for r in b if r["phase"] == "revise" and r["step"] == e["step"] + 1), None)
        if values and max(values) >= 350 and revise is not None:
            flow_rejections.append((max(values), e, revise))
    flow_rejections.sort(key=lambda t: t[0])
    temp = next((e for e in b if e["phase"] == "temperature_assessment"), None)
    depths = sorted({e["data"]["metrics"]["reservoir_temperature_C"] for e in b if e["phase"] == "evaluate"})
    final = next((e for e in b if e["phase"] == "final"), None)
    evals = [e for e in b if e["phase"] == "evaluate"]
    # (iv) a real hard failure and its recovery: an infeasible annual run, or a design rejected at validation
    # (hard limit) -> revised -> evaluated feasible; plus the feasible candidates the ranking rejected
    failed = next((e for e in evals if not e["data"]["feasible"]), None)
    recovered = next((e for e in evals if failed and e["step"] > failed["step"] and e["data"]["feasible"]), None)
    hard = []
    if failed and recovered:
        hard.append(f"step {failed['step']}: {failed['title'].split(': ', 1)[1]} infeasible ({', '.join(failed['data']['failing'])}) -> "
                    f"step {recovered['step']}: {recovered['title'].split(': ', 1)[1]} feasible")
    for _, v, r in sorted(flow_rejections, key=lambda t: t[1]["step"])[:1]:
        ok = next((e for e in evals if e["step"] > r["step"]), None)
        if ok and ok["data"]["feasible"]:
            hard.append(f"step {v['step']}: {v['rationale']} (hard limit) -> step {r['step']}: {r['title']} -> "
                        f"step {ok['step']}: {ok['title'].split(': ', 1)[1]} feasible")
    ranks = next((e["data"] for e in reversed(b) if e["phase"] == "rank"), {})
    feasible_names = {e["title"].split(": ", 1)[1] for e in evals if e["data"]["feasible"]}
    ranked_out = sorted(((name, v) for name, v in ranks.items() if v["status"] == "REJECTED" and name in feasible_names),
                        key=lambda kv: (not kv[0].startswith("n1_"), kv[1]["rank"]))
    ranked_text = [f"{name} feasible but ranked out (rank {v['rank']}): {v['reason']}" for name, v in ranked_out if name.startswith("n1_")]
    if len(ranked_out) > len(ranked_text):
        ranked_text.append(f"{len(ranked_out) - len(ranked_text)} more feasible candidate(s) ranked out: "
                           + ", ".join(name for name, _ in ranked_out if not name.startswith("n1_")))
    return [
        {"test": "(i) missing physical quantity -> stop and ask",
         "pass": (halt is not None or answered_all) and all(r in halted_for or answered(r) for r in removed),
         "evidence": (f"removed: {', '.join(removed)}; " if start and "removed_inputs" in start["data"] else "")
                     + (f"step {halt['step']}: {halt['rationale']}" if halt else
                        "; also ".join(f"step {q['step']} AGENT ASKED: {q['rationale']} -> step {answers[q['data']['input']]['step']} USER ANSWERED "
                                       f"{answers[q['data']['input']]['rationale']}"
                                       for q in asked if q["data"]["input"] in answers and q is next(x for x in reversed(asked) if x["data"]["input"] == q["data"]["input"]))
                        if answered_all else "no halt / question")},
        {"test": "(ii) >= 350 m3/h per doublet -> rejected with reason, revised", "pass": bool(flow_rejections),
         "evidence": "; also ".join(f"step {e['step']}: {e['rationale']} -> step {r['step']}: {r['title']}" for _, e, r in flow_rejections)
                     or "not triggered"},
        {"test": "(iii) 87 C reservoir vs 100 C supply -> shortfall stated, deeper well vs surface upgrade decided",
         "pass": temp is not None and len(depths) > 1 and final is not None,
         "evidence": (f"step {temp['step']} (assessment); candidates evaluated at reservoir temperatures {depths} C; step {final['step']} (decision)") if temp and final else "missing"},
        {"test": "(iv) recovery after a failed / ranked-out candidate", "pass": bool(hard) or bool(ranked_out),
         "evidence": "; also ".join(hard + ranked_text) or "not triggered"},
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


def required_input_row(c: dict) -> str:
    present = "yes" if c["present"] else "**MISSING**"
    if "range" not in c:  # official / fixed items
        return f"| {c['input']} | {present} | - | - | {c['source']} | {c['needed_for']} |"
    value = f"{c['value']:g}{unit_text(c['unit'])}" if c["present"] else "-"
    return (f"| {c['input']} ({c['label']}) | {present} | {value} | {c['range'][0]:g}-{c['range'][1]:g}{unit_text(c['unit'])} | "
            f"{c['source']} | {c['needed_for']} |")


def write_trace(path, entries, backend, results, note=None, design_scenario="B_design"):
    lines = [f"# Design agent trace ({backend} backend{', interactive' if design_scenario != 'B_design' else ''})", "",
             f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC from `decision_log.jsonl` ({len(entries)} logged steps). "
             f"Rerun: `$env:PYTHONPATH=\"src\"; py -3.11 -m poetry run python hackathon_work/design_agent.py --backend {backend}`.", ""]
    if note:
        lines += [f"> **Note:** {note}", ""]
    tests = judges_tests(entries, design_scenario)
    lines += ["## Judges' agent-reasoning tests", "", "| Test | Result | Evidence |", "|---|---|---|"]
    lines += [f"| {t['test']} | {'PASS' if t['pass'] else 'FAIL'} | {t['evidence']} |" for t in tests]
    b = results.get(design_scenario, {})
    lines += ["", f"## Evaluations (scenario {design_scenario[0]})", ""] + evaluation_table(entries, design_scenario)
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
        final = next((e for e in reversed(entries) if e["scenario"] == design_scenario and e["phase"] == "final"), None)
        if final and final["data"].get("backup_sizing"):
            fd = final["data"]
            lines += ["## Backup equipment sizing (feasible candidates)", "",
                      "Peak daily duties the backup must be built for, in planned operation and in the N-1 case (UNPLANNED outage of one "
                      "doublet on the peak heating and peak cooling days, ASSUMED). Installed backup = max of the two, so a 1-doublet design "
                      "(backup covers its maintenance window) and a staggered multi-doublet design are compared on equal terms. Organizer "
                      "clarification (Discord, 2026-11-01): the 330-day rule limits the geothermal source; the full system must meet demand "
                      "on all 365 days.", "",
                      "| Candidate | Verdict | Days without geothermal | Boiler peak (MWth) | N-1 boiler (MWth) | Installed boiler (MWth) | "
                      "Chiller peak (MWcool) | N-1 chiller (MWcool) | Installed chiller (MWcool) | External gas (GWh) | Emissions (t) |",
                      "|---|---|---|---|---|---|---|---|---|---|---|"]
            lines += [f"| {x['candidate']} | {x['status']} | {x['days_without_geothermal']} | {x['boiler_peak_MWth']:.2f} | "
                      f"{x.get('n_minus_1_boiler_MWth', float('nan')):.2f} | {x.get('installed_boiler_MWth', float('nan')):.2f} | "
                      f"{x['electric_chiller_peak_MWcool']:.2f} | {x.get('n_minus_1_electric_chiller_MWcool', float('nan')):.2f} | "
                      f"{x.get('installed_electric_chiller_MWcool', float('nan')):.2f} | {x['external_gas_GWh']:.3f} | {x['emissions_t']:.0f} |"
                      for x in fd["backup_sizing"]]
            lines.append("")
            if fd.get("n_minus_1"):
                lines += ["## N-1 resilience at the final pick", "",
                          "| Case | Date | Doublet out | Doublets on (normal -> N-1) | Boiler (MWth): normal -> N-1 | of which external gas | "
                          "Electric chiller (MWcool): normal -> N-1 | Unmet heat / cool (MW) |", "|---|---|---|---|---|---|---|---|"]
                lines += [f"| {c['case']} | {c['date']} | {c['doublet_out']} | {c['n_active_normal']} -> {c['n_active_n_minus_1']} | "
                          f"{c['boiler_MWth_normal']:.2f} -> {c['boiler_MWth']:.2f} | {c['boiler_external_gas_MWth']:.2f} | "
                          f"{c['electric_chiller_MWcool_normal']:.2f} -> {c['electric_chiller_MWcool']:.2f} | {c['heat_unmet_MW']:.3f} / {c['cool_unmet_MW']:.3f} |"
                          for c in fd["n_minus_1"]]
                ib = fd["installed_backup_MW"]
                lines += ["", f"Installed backup at the pick: {ib['boiler_th']:.2f} MWth boiler, {ib['electric_chiller_cool']:.2f} MWcool electric chiller.", ""]
            if fd.get("gas_handling", {}).get("options"):
                lines += ["## Gas handling (design variable)", "", fd["gas_handling"]["text"], "",
                          "| Candidate | Gas handling | External gas (GWh) | Emissions (t) | of which produced gas (t) | Grid import (GWh) | "
                          "Gas-handling el. (GWh) | CHP heat (GWh) | Dissolution margin wellhead / reservoir | Verdict (rank) |",
                          "|---|---|---|---|---|---|---|---|---|---|"]
                lines += [f"| {r['candidate']} | {r['gas_handling']} | {r['external_gas_GWh']:.3f} | {r['emissions_t']:.0f} | {r['emissions_produced_gas_t']:.0f} | "
                          f"{r['grid_import_GWh']:.2f} | {r['el_gas_handling_GWh']:.3f} | {r['heat_chp_GWh']:.1f} | "
                          + (f"{r['dissolution']['wellhead_margin']:.2f} / {r['dissolution']['reservoir_margin']:.1f} ({r['dissolution']['status']})"
                             if r.get("dissolution") else "n/a (burned)")
                          + f" | {r['verdict']} ({r['rank']}) |" for r in fd["gas_handling"]["options"]]
                lines += ["", "Dissolution margin = brine's gas capacity / gas to reinject per m3 (bubble point at the available pressure; "
                          "IAPWS G7-04 Henry constants, Weisenberger-Schumpe salting-out, Peng-Robinson; `gas_solubility.py`). Wellhead: "
                          "lowest injector wellhead pressure of the year at the hottest injection temperature; reservoir: reservoir P and T; "
                          "conservative salinity (1030 kg/m3 read at reservoir temperature).", ""]
                lines.append("")
        lines += ["## Runtime", "",
                  f"- Annual evaluations: {t['evaluations']} ({t['computed']} computed, {t['cached']} from cache); "
                  f"computed wall time mean {t['wall_s_per_computed_evaluation_mean'] or 0:.1f} s, max {t['wall_s_per_computed_evaluation_max'] or 0:.1f} s",
                  f"- Scenario B runtime: {t['scenario_runtime_s']:.1f} s; scenario A runtime: "
                  + (f"{results['A_missing_input']['runtime_s']:.1f} s" if results.get("A_missing_input", {}).get("runtime_s") is not None else "not logged"),
                  f"- Backend calls: {t['backend_calls']} ({t['backend_wall_s']:.1f} s)"]
        calls = [c for e in entries for c in (e["data"] or {}).get("backend_calls", []) if isinstance(e["data"], dict)]
        if calls:
            lines += ["", "| Call | Purpose | Wall (s) | Input tokens | Cache write | Cache read | Output tokens | Cost (USD) |", "|---|---|---|---|---|---|---|---|"]
            for i, c in enumerate(calls, 1):
                u = c.get("usage") or {}
                cost = f"{c['total_cost_usd']:.3f}" if c.get("total_cost_usd") is not None else "-"
                lines.append(f"| {i} | {c['purpose']} | {c['wall_s']:.1f} | {u.get('input_tokens', '-')} | {u.get('cache_creation_input_tokens', '-')} | "
                             f"{u.get('cache_read_input_tokens', '-')} | {u.get('output_tokens', '-')} | {cost} |")
            used = {k: sum((c.get("usage") or {}).get(k) or 0 for c in calls)
                    for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")}
            cost = sum(c.get("total_cost_usd") or 0 for c in calls)
            lines.append(f"| total | {len(calls)} calls | {sum(c['wall_s'] for c in calls):.1f} | {used['input_tokens']} | {used['cache_creation_input_tokens']} | "
                         f"{used['cache_read_input_tokens']} | {used['output_tokens']} | {cost:.2f} |")
    start_a = next((e for e in entries if e["scenario"] == "A_missing_input" and e["phase"] == "start"), None)
    removed = ", ".join((start_a["data"] if start_a else {}).get("removed_inputs", ["heating return temperature"]))
    scenario_titles = {"A_missing_input": f"Scenario A: {removed} removed from the inputs"
                                          + (" (interactive: the agent asks, the user answers, the design loop continues)" if design_scenario != "B_design" else ""),
                       "B_design": "Scenario B: complete inputs, design loop"}
    for scenario, title in scenario_titles.items():
        lines += ["", f"## {title}", ""]
        for e in (x for x in entries if x["scenario"] == scenario):
            if e["phase"] in ("ask", "answer"):
                lines.append(f"**{e['step']}. {e['title']}** ({e['time_utc'][:19].replace('T', ' ')} UTC)")
            else:
                lines.append(f"**{e['step']}. [{e['phase']}] {e['title']}**")
            rationale = e["rationale"]
            if e["phase"] == "stop" and (model_reason := stop_reasoning(e)) and model_reason != rationale:
                rationale = f"Backend's own stop reasoning: {model_reason}"
            if rationale:
                lines.append(f"> {rationale}")
            if e["phase"] == "required_inputs":
                lines += ["", "| Input | Present | Value | Plausible range | Provenance | Needed for |", "|---|---|---|---|---|---|"]
                lines += [required_input_row(c) for c in e["data"]["checked"]]
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
    parser.add_argument("--budget", type=int, default=16, help="maximum annual evaluations in scenario B")
    parser.add_argument("--clear-cache", action="store_true", help="recompute every annual evaluation (honest timings)")
    parser.add_argument("--interactive", action="store_true",
                        help="human-in-the-loop demo: scenario A (inputs from --remove missing); the agent asks in the terminal, "
                             "validates each answer and continues the design loop with them (outputs in <out>/interactive/)")
    parser.add_argument("--remove", action="append", metavar="NAME[,NAME...]",
                        help=f"required input(s) removed in scenario A (judges' test i), default heating_return_T; 'all' removes every one. "
                             f"Names: {', '.join(REQUIRED_BY_NAME)}")
    parser.add_argument("--retrace", metavar="NOTE", help="only rebuild agent_trace.md from the saved decision_log.jsonl, with this note")
    args = parser.parse_args()
    removed = [n.strip() for arg in (args.remove or ["heating_return_T"]) for n in arg.split(",") if n.strip()]
    if "all" in removed:
        removed = list(REQUIRED_BY_NAME)
    unknown = [n for n in removed if n not in REQUIRED_BY_NAME]
    if unknown:
        parser.error(f"unknown input(s) for --remove: {', '.join(unknown)}; choose from {', '.join(REQUIRED_BY_NAME)}")
    removed = list(dict.fromkeys(removed))

    out_dir = AGENT_OUT if args.backend == "rules" else AGENT_OUT / args.backend
    if args.interactive:
        out_dir = out_dir / "interactive"
    if args.retrace:
        retrace(out_dir, args.backend, args.retrace)
        return
    if args.clear_cache and CACHE.exists():
        shutil.rmtree(CACHE)
    start = time.perf_counter()
    backend = BACKENDS[args.backend](out_dir)
    log = DecisionLog(out_dir / "decision_log.jsonl", backend.name)
    results = {}

    roots_missing = {"project": load_json(PROJECT_PATH), "settings": load_json(CANDIDATES_PATH)}
    for name in removed:
        remove_input(roots_missing, REQUIRED_BY_NAME[name])
    design_scenario = "A_missing_input" if args.interactive else "B_design"
    results["A_missing_input"] = DesignAgent(backend, log, out_dir, args.budget, interactive=args.interactive).run(
        "A_missing_input", roots_missing["project"], roots_missing["settings"], removed)
    if not args.interactive:
        results["B_design"] = DesignAgent(backend, log, out_dir, args.budget).run("B_design")
    total = time.perf_counter() - start

    tests = write_trace(out_dir / "agent_trace.md", log.entries, backend.name, results, design_scenario=design_scenario)
    b = results[design_scenario]
    summary = {"backend": backend.name, "total_runtime_s": total, "status": b["status"], "timing": b.get("timing"),
               "pick": b["pick"]["candidate"] if b.get("pick") else None, "pick_summary": {k: b["pick"]["summary"][k] for k in
               ("external_gas_fuel_GWh", "emissions_t", "grid_import_GWh", "drilled_m", "reservoir_temperature_C")} if b.get("pick") else None,
               "evaluated": [{"candidate": h["candidate"], "feasible": h["feasible"], "verdict": h["verdict"]} for h in b.get("history", [])],
               "marginal_cases": b.get("marginal_cases", []), "backup_sizing": b.get("backup_sizing", []),
               "n_minus_1": b.get("n_minus_1"), "installed_backup_MW": b.get("installed_backup_MW"), "gas_handling": b.get("gas_handling"),
               "judges_tests": tests, "backend_calls": backend.calls}
    (out_dir / "run_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    if not args.interactive:
        print(f"[{backend.name}] Scenario A: {results['A_missing_input']['status']}")
    print(f"[{backend.name}] Scenario {design_scenario[0]}: {b['status']}, {len(b.get('history', []))} annual evaluations, total runtime {total:.1f} s")
    print("\n".join(evaluation_table(log.entries, design_scenario)))
    if b.get("status") == "selected":
        print(f"FINAL: {b['conclusion']}")
        print(f"TIMING: {json.dumps(b['timing'])}")
    for t in tests:
        print(f"  {'PASS' if t['pass'] else 'FAIL'} {t['test']}")
    print(f"LOGS: {(out_dir / 'decision_log.jsonl').relative_to(REPO)}, {(out_dir / 'agent_trace.md').relative_to(REPO)}")


if __name__ == "__main__":
    main()
