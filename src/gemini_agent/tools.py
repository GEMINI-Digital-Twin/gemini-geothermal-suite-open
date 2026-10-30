"""The agent's tools: schemas, argument checks (gate 1) and execution.

Each tool returns a compact JSON-able dict (a few hundred tokens), not
365-row tables. Full results stay in the run ledger on disk and can be
fetched with ``get_run``.
"""

import json
import time
import warnings
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from gemini_agent import reservoir_slot, sandbox
from gemini_agent.knowledge import (
    ASSUMPTION_RANGES,
    CHALLENGE_RANGES,
    GAPS,
    assumptions_ledger,
    brief_summary,
)
from gemini_agent.memory import run_key
from gemini_agent.physics_gate import check_run
from gemini_design.annual import dispatch_day, run_year
from gemini_design.challenge import ASSUMPTIONS, CHALLENGE
from gemini_design.doublet import DoubletHydraulics
from gemini_design.plant import COOLING, UPGRADES, Design, Plant
from gemini_design.project_json import cross_check as solver_cross_check
from gemini_design.screening import chp_size_mw_el
from gemini_simulator.registry import COMPONENT_REGISTRY

MAX_SCREEN_DESIGNS = 48
MAX_SENSITIVITY_POINTS = 6


class ToolError(Exception):
    """Invalid tool call; the message goes back to the LLM."""


def _round(x, sig=4):
    if isinstance(x, (bool, np.bool_)):
        return bool(x)
    if isinstance(x, (int, np.integer)):
        return int(x)
    if isinstance(x, (float, np.floating)):
        x = float(x)
        if abs(x) < 1e-6 or not np.isfinite(x):
            return 0.0 if abs(x) < 1e-6 else x
        return float(f"{x:.{sig}g}")
    if isinstance(x, dict):
        return {k: _round(v, sig) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_round(v, sig) for v in x]
    return x


# ------------------------------------------------------------ schemas (gate 1)

_ASSUMPTION_OVERRIDES = {
    "type": "object",
    "description": "Optional what-if overrides of assumptions or reservoir data, "
    'e.g. {"heating_return_c": 50}. Allowed keys: '
    + ", ".join(sorted(ASSUMPTION_RANGES) + sorted(CHALLENGE_RANGES)),
}

_DESIGN_PROPS = {
    "n_doublets": {"type": "integer", "minimum": 1, "maximum": 3},
    "depth_m": {
        "type": "number",
        "minimum": 1000,
        "maximum": 4500,
        "description": "reservoir midpoint depth (TVD); temperature follows 30 degC/km",
    },
    "upgrade": {
        "type": "string",
        "enum": list(UPGRADES),
        "description": "how to lift to 100 degC",
    },
    "cooling": {"type": "string", "enum": list(COOLING)},
    "heat_pump_capacity_mw": {"type": "number", "minimum": 0, "maximum": 40},
    "boiler_capacity_mw": {"type": "number", "minimum": 0, "maximum": 40},
    "chiller_capacity_mw": {"type": "number", "minimum": 0, "maximum": 20},
    "electric_backup_mw": {"type": "number", "minimum": 0, "maximum": 20},
    "chp": {
        "type": "boolean",
        "description": "gas engine burning the co-produced gas (sized for all of it at full flow)",
    },
    "chp_capacity_mw_el": {"type": "number", "minimum": 0, "maximum": 5},
    "assumptions": _ASSUMPTION_OVERRIDES,
}

TOOL_SPECS = {
    "describe_inputs": {
        "description": "The brief, demand statistics, input gaps and low-confidence assumptions.",
        "parameters": {"type": "object", "properties": {}},
    },
    "list_models": {
        "description": "GEMINI component models available (registry) and design options.",
        "parameters": {"type": "object", "properties": {}},
    },
    "run_design": {
        "description": "Simulate one plant for 365 days with GEMINI models; checks hard rules, "
        "energy balance, physical bounds and GEMINI Solver agreement. Returns a run id + KPIs. "
        "Default sizes: boiler = heating peak, chiller = cooling peak, heat pump = 1/3 "
        "heating peak, absorption backup = 1/2 cooling peak.",
        "parameters": {
            "type": "object",
            "properties": _DESIGN_PROPS,
            "required": ["n_doublets", "depth_m", "upgrade", "cooling"],
        },
    },
    "screen": {
        "description": "Run every combination of the given options for a year (in parallel) "
        "and return the best designs. At most 48 combinations.",
        "parameters": {
            "type": "object",
            "properties": {
                "n_doublets": {"type": "array", "items": {"type": "integer"}},
                "depths_m": {"type": "array", "items": {"type": "number"}},
                "upgrades": {"type": "array", "items": {"type": "string", "enum": list(UPGRADES)}},
                "coolings": {"type": "array", "items": {"type": "string", "enum": list(COOLING)}},
                "chp": {"type": "array", "items": {"type": "boolean"}},
                "assumptions": _ASSUMPTION_OVERRIDES,
                "top": {"type": "integer", "minimum": 1, "maximum": 10},
            },
            "required": ["n_doublets", "depths_m", "upgrades", "coolings"],
        },
    },
    "sensitivity": {
        "description": "Re-run a design (from a run id) while varying one assumption, "
        "reservoir property, or demand_scale (multiplies heating and cooling demand).",
        "parameters": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
                "parameter": {"type": "string"},
                "values": {"type": "array", "items": {"type": "number"}},
            },
            "required": ["run_id", "parameter", "values"],
        },
    },
    "cross_check": {
        "description": "Rebuild one day of a run as a native GEMINI project and re-solve it with "
        "gemini_simulator.Solver; compare temperatures with the dispatcher.",
        "parameters": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
                "day": {
                    "type": "string",
                    "description": "'peak_heating', 'peak_cooling' or a day number 1-365",
                },
            },
            "required": ["run_id"],
        },
    },
    "get_run": {
        "description": "Details of an earlier run: energy, KPIs, costs, checks.",
        "parameters": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
                "section": {
                    "type": "string",
                    "enum": ["energy_mwh", "kpi", "economics", "checks", "reservoir", "all"],
                },
            },
            "required": ["run_id"],
        },
    },
    "reservoir_simulation": {
        "description": "Reservoir/well model at a depth: temperature, pressure, PI, pump powers; "
        "with the 'fimbul' provider also 30-year thermal decline.",
        "parameters": {
            "type": "object",
            "properties": {
                "depth_m": {"type": "number", "minimum": 1000, "maximum": 4500},
                "flow_m3h": {"type": "number", "minimum": 50, "maximum": 300},
                "permeability_md": {"type": "number", "minimum": 10, "maximum": 2000},
                "well_spacing_m": {"type": "number", "minimum": 500, "maximum": 4000},
                "years": {"type": "integer", "minimum": 1, "maximum": 50},
                "provider": {"type": "string", "description": "'auto', 'analytic' or 'fimbul'"},
            },
            "required": ["depth_m"],
        },
    },
    "write_model": {
        "description": "Add a missing component model: Python code for one gemini_model "
        "StaticModel subclass (update_parameters / calculate_output(u, x) / output dict) plus "
        "pytest tests. Code is sandboxed; only registered if its tests pass.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "snake_case module name"},
                "register_as": {"type": "string", "description": "component type name"},
                "code": {"type": "string"},
                "test_code": {"type": "string"},
            },
            "required": ["name", "register_as", "code", "test_code"],
        },
    },
    "ask_user": {
        "description": "Ask the user for a missing input. Ends your turn; the answer comes back "
        "as the next user message.",
        "parameters": {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "default_if_no_answer": {"type": "string"},
            },
            "required": ["question"],
        },
    },
    "memory_read": {
        "description": "Project notes (decisions, assumptions, lessons) and the latest runs.",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
    },
    "memory_write": {
        "description": "Save a decision, agreed assumption or lesson for future sessions.",
        "parameters": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["decision", "assumption", "lesson"]},
                "text": {"type": "string"},
            },
            "required": ["kind", "text"],
        },
    },
}


def openai_tool_schemas(names=None):
    """Return the tools in OpenAI ``tools`` format."""
    return [
        {"type": "function", "function": {"name": n, **spec}}
        for n, spec in TOOL_SPECS.items()
        if names is None or n in names
    ]


_TYPES = {
    "boolean": (bool,),
    "integer": (int,),
    "number": (int, float),
    "string": (str,),
    "array": (list,),
    "object": (dict,),
}


def validate_arguments(name, args):
    """Gate 1: check tool arguments against the schema; return a list of errors."""
    if name not in TOOL_SPECS:
        return [f"unknown tool '{name}'. Tools: {', '.join(TOOL_SPECS)}"]
    if not isinstance(args, dict):
        return ["arguments must be a JSON object"]
    schema = TOOL_SPECS[name]["parameters"]
    props = schema.get("properties", {})
    errors = [f"missing argument '{r}'" for r in schema.get("required", []) if r not in args]
    for key, value in args.items():
        if key not in props:
            errors.append(f"unknown argument '{key}' (allowed: {', '.join(props) or 'none'})")
            continue
        errors.extend(_check_value(key, value, props[key]))
    return errors


def _check_value(key, value, prop):
    types = _TYPES.get(prop.get("type"), (object,))
    is_bool = isinstance(value, bool)
    if (is_bool != (prop.get("type") == "boolean")) or not isinstance(value, types):
        if not (prop.get("type") == "integer" and isinstance(value, float) and value.is_integer()):
            return [f"'{key}' must be {prop.get('type')}, got {value!r}"]
    errors = []
    if "enum" in prop and value not in prop["enum"]:
        errors.append(f"'{key}' must be one of {prop['enum']}, got {value!r}")
    if "minimum" in prop and value < prop["minimum"]:
        errors.append(f"'{key}' = {value} is below the minimum {prop['minimum']}")
    if "maximum" in prop and value > prop["maximum"]:
        errors.append(f"'{key}' = {value} is above the maximum {prop['maximum']}")
    if prop.get("type") == "array" and "items" in prop:
        for item in value:
            errors.extend(_check_value(f"{key}[]", item, prop["items"]))
    return errors


def split_overrides(overrides):
    """Validate what-if overrides; return (challenge, assumptions, demand_scale)."""
    overrides = dict(overrides or {})
    demand_scale = float(overrides.pop("demand_scale", 1.0))
    if not 0.5 <= demand_scale <= 2.0:
        raise ToolError("demand_scale must be within 0.5-2.0")
    challenge, assumptions = dict(CHALLENGE), dict(ASSUMPTIONS)
    for key, value in overrides.items():
        ranges = ASSUMPTION_RANGES if key in ASSUMPTION_RANGES else CHALLENGE_RANGES
        if key not in ranges:
            raise ToolError(
                f"'{key}' can not be overridden. Allowed: "
                + ", ".join(sorted(ASSUMPTION_RANGES) + sorted(CHALLENGE_RANGES) + ["demand_scale"])
            )
        lo, hi = ranges[key]
        if not isinstance(value, (int, float)) or not lo <= value <= hi:
            raise ToolError(f"'{key}' must be a number within {lo}-{hi}, got {value!r}")
        target = assumptions if key in ASSUMPTION_RANGES else challenge
        target[key] = float(value)
    if assumptions["cooling_return_c"] <= challenge["cooling_supply_c"]:
        raise ToolError("cooling_return_c must be above the 20 degC cooling supply")
    if assumptions["heating_return_c"] >= challenge["heating_supply_c"]:
        raise ToolError("heating_return_c must be below the 100 degC heating supply")
    return challenge, assumptions, demand_scale


def make_design(args, peak_heating_mw, peak_cooling_mw):
    """Build a Design with the stated default sizing rules."""
    upgrade, cooling = args["upgrade"], args["cooling"]
    defaults = {
        "heat_pump_capacity_mw": peak_heating_mw / 3 if upgrade == "heat_pump" else 0.0,
        "boiler_capacity_mw": peak_heating_mw,
        "chiller_capacity_mw": peak_cooling_mw,
        "electric_backup_mw": peak_cooling_mw / 2 if cooling == "absorption" else 0.0,
    }
    sizes = {k: float(args.get(k, v)) for k, v in defaults.items()}
    chp = args.get("chp_capacity_mw_el")
    if chp is None:
        chp = chp_size_mw_el(int(args["n_doublets"])) if args.get("chp") else 0.0
    sizes["chp_capacity_mw_el"] = float(chp)
    return Design(
        n_doublets=int(args["n_doublets"]),
        depth_m=float(args["depth_m"]),
        upgrade=upgrade,
        cooling=cooling,
        **sizes,
    )


def headline(summary, gate):
    """Compact KPIs of one year run, as the agent sees them."""
    d, e, k, econ = summary["design"], summary["energy_mwh"], summary["kpi"], summary["economics"]
    failed = [n for n, ok in summary["checks"].items() if not ok]
    return _round(
        {
            "design": d["name"],
            "reservoir_temperature_c": summary["reservoir"]["temperature_c"],
            "meets_all_hard_rules": summary["all_hard_constraints_met"],
            "failed_rules": failed,
            "unmet_heating_mwh": e["unmet_heating"],
            "unmet_cooling_mwh": e["unmet_cooling"],
            "geothermal_share_of_heat_pct": 100.0 * k["geothermal_share_of_heat"],
            "purchased_gas_mwh": e["purchased_gas_fuel"],
            "electricity_mwh": e["electricity"],
            "grid_import_mwh": e.get("grid_import", e["electricity"]),
            "chp_electricity_mwh": e.get("chp_electricity", 0.0),
            "co2_t_per_year": k["co2_t_per_year"],
            "capex_meur": econ["capex_eur"]["total"] / 1e6,
            "lcoe_eur_per_mwh": econ["lcoe_eur_per_mwh"],
            "max_flow_per_doublet_m3h": k["max_flow_per_doublet_m3h"],
            "max_brine_cooling_k": k["max_brine_cooling_k"],
            "associated_gas_flared_mwh_fuel": k["associated_gas_unused_mwh"],
            "physics_gate": "pass" if gate["passed"] else "FAIL",
        }
    )


def _year_worker(args):
    design, demand, challenge, assumptions = args
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        daily, summary = run_year(design, demand, challenge, assumptions)
    return summary, daily


class ToolBox:
    """Executes tool calls against GEMINI and records every run in the ledger."""

    def __init__(self, demand, ledger, notes, workspace, workers=4):
        """Hold the demand profile, memory stores and workspace path."""
        self.demand = demand
        self.ledger = ledger
        self.notes = notes
        self.workspace = workspace
        self.workers = workers
        self.peak_heating_mw = float(demand["heating_mw"].max())
        self.peak_cooling_mw = float(demand["cooling_mw"].max())

    # -------------------------------------------------------------- dispatch
    def call(self, name, args):
        """Validate and run one tool; return a JSON-able dict (errors included)."""
        errors = validate_arguments(name, args)
        if errors:
            return {"error": "invalid arguments (physics gate 1)", "details": errors}
        t0 = time.time()
        try:
            result = getattr(self, f"tool_{name}")(**args)
        except ToolError as exc:
            return {"error": str(exc)}
        except Exception as exc:  # a crash inside a model goes back to the LLM, not the user
            return {"error": f"{type(exc).__name__}: {exc}"}
        if isinstance(result, dict):
            result.setdefault("seconds", round(time.time() - t0, 2))
        return result

    # -------------------------------------------------------------- tools
    def tool_describe_inputs(self):
        """Brief, demand statistics, gaps and low-confidence assumptions."""
        dem = self.demand
        low = {k: v["value"] for k, v in assumptions_ledger().items() if v["confidence"] == "low"}
        return _round(
            {
                "brief": brief_summary(),
                "demand": {
                    "heating_peak_mw": dem["heating_mw"].max(),
                    "heating_peak_date": str(dem.loc[dem["heating_mw"].idxmax(), "date"].date()),
                    "heating_min_mw": dem["heating_mw"].min(),
                    "heating_gwh_per_year": dem["heating_mw"].sum() * 24 / 1e3,
                    "cooling_peak_mw": dem["cooling_mw"].max(),
                    "cooling_peak_date": str(dem.loc[dem["cooling_mw"].idxmax(), "date"].date()),
                    "cooling_gwh_per_year": dem["cooling_mw"].sum() * 24 / 1e3,
                    "cooling_days": int((dem["cooling_mw"] > 0).sum()),
                },
                "gaps_assumed": GAPS,
                "low_confidence_assumptions": low,
            }
        )

    def tool_list_models(self):
        """Registry models (with first docstring line) and design options."""
        models = {}
        for key, cls in COMPONENT_REGISTRY.items():
            doc = (cls.__doc__ or "").strip().splitlines()
            models[key] = (doc[0] if doc else cls.__name__)[:90]
        return {
            "gemini_components": models,
            "design_options": {"upgrade": list(UPGRADES), "cooling": list(COOLING)},
            "reservoir_providers": reservoir_slot.available_providers(),
            "missing_models_ideas": [
                "dry cooler with hourly weather",
                "aquifer thermal energy storage",
                "CHP on co-produced gas",
                "thermal breakthrough over 30 years",
            ],
        }

    def _run(self, design, overrides, request, kind="design"):
        challenge, assumptions, demand_scale = split_overrides(overrides)
        key = run_key(kind, {"design": design.as_dict(), "overrides": overrides or {}})
        existing = self.ledger.find(key)
        if existing:
            entry = self.ledger.get(existing)
            return {"run_id": existing, "reused_earlier_run": True, **entry["headline"]}
        demand = self.demand
        if demand_scale != 1.0:
            demand = demand.copy()
            demand[["heating_mw", "cooling_mw"]] *= demand_scale
        summary, daily = _year_worker((design, demand, challenge, assumptions))
        return self._record(design, summary, daily, overrides, request, key, challenge, assumptions)

    def _record(self, design, summary, daily, overrides, request, key, challenge, assumptions):
        gate = check_run(summary, daily, challenge, assumptions)
        gate["4_second_solver"] = self._solver_check(
            design, daily, "peak_heating", challenge, assumptions
        )
        if gate["4_second_solver"].get("agrees") is False:
            gate["passed"] = False
        head = headline(summary, gate)
        run_id = self.ledger.add(
            "design",
            key,
            request,
            head,
            gate,
            summary=summary,
            daily=daily,
            extra={"overrides": overrides or {}},
        )
        out = {"run_id": run_id, **head}
        if not gate["passed"]:
            out["gate_errors"] = {
                k: v for k, v in gate.items() if k[0].isdigit() and v not in ("pass",)
            }
            out["note"] = "This run failed the physics gate; do not quote its numbers."
        return out

    def _solver_check(self, design, daily, day, challenge, assumptions):
        """Gate 4: re-solve one day with GEMINI's Solver."""
        demand = self.demand
        if day == "peak_heating":
            i = int(daily["heating_demand_w"].idxmax())
        elif day == "peak_cooling":
            i = int(daily["cooling_demand_w"].idxmax())
        else:
            i = int(day) - 1
            if not 0 <= i < len(daily):
                raise ToolError("day must be 1-365")
        hyd = DoubletHydraulics(design.depth_m, challenge, assumptions)
        plant = Plant(design, hyd, challenge, assumptions)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            point = dispatch_day(
                plant,
                float(daily.loc[i, "heating_demand_w"]),
                float(daily.loc[i, "cooling_demand_w"]),
                int(daily.loc[i, "n_available"]),
                challenge,
            )
        if point["n_active"] < 1:
            return {"day": i + 1, "agrees": None, "note": "no doublet running that day"}
        _, check = solver_cross_check(
            design, hyd, point, challenge=challenge, assumptions=assumptions
        )
        out = {"day": i + 1, "date": str(demand.loc[i, "date"].date())}
        out.update(_round(check))
        return out

    def tool_run_design(self, assumptions=None, **args):
        """Simulate one design for a year."""
        design = make_design(args, self.peak_heating_mw, self.peak_cooling_mw)
        return self._run(design, assumptions, {**args, "assumptions": assumptions or {}})

    def tool_screen(
        self, n_doublets, depths_m, upgrades, coolings, chp=(False,), assumptions=None, top=5
    ):
        """Run a grid of designs in parallel and rank them."""
        combos = [
            (n, d, u, c, h)
            for n in n_doublets
            for d in depths_m
            for u in upgrades
            for c in coolings
            for h in dict.fromkeys(chp)
        ]
        if not combos:
            raise ToolError("empty grid")
        if len(combos) > MAX_SCREEN_DESIGNS:
            raise ToolError(f"{len(combos)} designs requested; the limit is {MAX_SCREEN_DESIGNS}")
        for n, d, *_ in combos:
            if not 1 <= n <= 3 or not 1000 <= d <= 4500:
                raise ToolError("n_doublets must be 1-3 and depths 1000-4500 m")
        challenge, assumptions_d, demand_scale = split_overrides(assumptions)
        demand = self.demand
        if demand_scale != 1.0:
            demand = demand.copy()
            demand[["heating_mw", "cooling_mw"]] *= demand_scale
        designs = [
            make_design(
                {"n_doublets": n, "depth_m": d, "upgrade": u, "cooling": c, "chp": h},
                self.peak_heating_mw,
                self.peak_cooling_mw,
            )
            for n, d, u, c, h in combos
        ]
        rows, todo = [], []
        for design in designs:
            key = run_key("design", {"design": design.as_dict(), "overrides": assumptions or {}})
            found = self.ledger.find(key)
            if found:
                rows.append({"run_id": found, **self.ledger.get(found)["headline"]})
            else:
                todo.append((design, key))
        if todo:
            jobs = [(d, demand, challenge, assumptions_d) for d, _ in todo]
            if self.workers > 1 and len(jobs) > 1:
                with ProcessPoolExecutor(max_workers=self.workers) as pool:
                    results = list(pool.map(_year_worker, jobs))
            else:
                results = [_year_worker(j) for j in jobs]
            for (design, key), (summary, daily) in zip(todo, results):
                request = {**design.as_dict(), "assumptions": assumptions or {}}
                rows.append(
                    self._record(
                        design, summary, daily, assumptions, request, key, challenge, assumptions_d
                    )
                )
        valid = [r for r in rows if r["physics_gate"] == "pass"]
        feasible = [r for r in valid if r["meets_all_hard_rules"]]
        feasible.sort(key=lambda r: r["lcoe_eur_per_mwh"])
        failing = {}
        for r in valid:
            if not r["meets_all_hard_rules"]:
                failing[r["design"]] = r["failed_rules"]
        keep = (
            "run_id",
            "design",
            "lcoe_eur_per_mwh",
            "co2_t_per_year",
            "geothermal_share_of_heat_pct",
            "purchased_gas_mwh",
            "capex_meur",
        )
        best = [{k: r[k] for k in keep} for r in feasible[:top]]
        lowest_co2 = min(feasible, key=lambda r: r["co2_t_per_year"]) if feasible else None
        out = {
            "designs_run": len(rows),
            "meet_all_rules": len(feasible),
            "failed_physics_gate": len(rows) - len(valid),
            "best_by_lcoe": best,
            "lowest_co2": {k: lowest_co2[k] for k in keep} if lowest_co2 else None,
            "failing_designs": dict(list(failing.items())[:8]),
        }
        out["screen_id"] = self.ledger.add(
            "screen",
            None,
            {"grid": combos, "assumptions": assumptions or {}},
            {"designs_run": len(rows), "meet_all_rules": len(feasible)},
            {"passed": True},
            extra={"members": [r["run_id"] for r in rows]},
        )
        return out

    def tool_sensitivity(self, run_id, parameter, values):
        """Vary one parameter around an earlier design run."""
        if run_id not in self.ledger.entries or self.ledger.get(run_id)["kind"] != "design":
            raise ToolError(f"unknown design run '{run_id}'")
        if len(values) > MAX_SENSITIVITY_POINTS:
            raise ToolError(f"at most {MAX_SENSITIVITY_POINTS} values")
        entry = self.ledger.get(run_id)
        request = dict(entry["request"])
        base_overrides = dict(request.pop("assumptions", {}) or {})
        for k in ("name", "notes"):
            request.pop(k, None)
        design = make_design(request, self.peak_heating_mw, self.peak_cooling_mw)
        rows = []
        for v in values:
            overrides = {**base_overrides, parameter: v}
            r = self._run(design, overrides, {**request, "assumptions": overrides})
            rows.append(
                {
                    parameter: v,
                    "run_id": r["run_id"],
                    "meets_all_hard_rules": r["meets_all_hard_rules"],
                    "lcoe_eur_per_mwh": r["lcoe_eur_per_mwh"],
                    "co2_t_per_year": r["co2_t_per_year"],
                    "electricity_mwh": r["electricity_mwh"],
                    "purchased_gas_mwh": r["purchased_gas_mwh"],
                    "unmet_heating_mwh": r["unmet_heating_mwh"],
                    "unmet_cooling_mwh": r["unmet_cooling_mwh"],
                    "physics_gate": r["physics_gate"],
                }
            )
        return {"base_run": run_id, "design": entry["headline"]["design"], "rows": rows}

    def tool_cross_check(self, run_id, day="peak_heating"):
        """Re-solve one day of a run with GEMINI's Solver."""
        if run_id not in self.ledger.entries or self.ledger.get(run_id)["kind"] != "design":
            raise ToolError(f"unknown design run '{run_id}'")
        entry = self.ledger.get(run_id)
        request = dict(entry["request"])
        overrides = request.pop("assumptions", {}) or {}
        for k in ("name", "notes"):
            request.pop(k, None)
        design = make_design(request, self.peak_heating_mw, self.peak_cooling_mw)
        challenge, assumptions, _ = split_overrides(overrides)
        daily = self.ledger.daily(run_id)
        if daily is None:
            raise ToolError(f"daily results of {run_id} are not on disk")
        result = self._solver_check(design, daily, day, challenge, assumptions)
        result["run_id"] = run_id
        return result

    def tool_get_run(self, run_id, section="kpi"):
        """Return one section of an earlier run's summary."""
        if run_id not in self.ledger.entries:
            raise ToolError(f"unknown run '{run_id}'")
        entry = self.ledger.get(run_id)
        summary = self.ledger.summary(run_id)
        if summary is None:
            return {"run_id": run_id, **entry["headline"], "members": entry.get("members")}
        if section == "all":
            data = {k: summary[k] for k in ("energy_mwh", "kpi", "checks", "reservoir")}
            data["economics"] = {k: v for k, v in summary["economics"].items() if k != "capex_eur"}
        elif section == "economics":
            data = summary["economics"]
        else:
            data = summary[section]
        return _round({"run_id": run_id, "design": summary["design"]["name"], section: data})

    def tool_reservoir_simulation(self, depth_m, provider="auto", **kwargs):
        """Reservoir provider call (analytic now, Fimbul when installed)."""
        return _round(reservoir_slot.simulate(provider=provider, depth_m=depth_m, **kwargs))

    def tool_write_model(self, name, register_as, code, test_code):
        """Sandboxed model writing."""
        result = sandbox.write_model(name, code, test_code, register_as, self.workspace)
        if result.get("ok"):
            self.notes.add(
                "model", f"agent wrote '{register_as}' ({result['class']}); tests pass", "agent"
            )
        return result

    def tool_memory_read(self, query=""):
        """Project notes plus the latest runs."""
        return {"notes": self.notes.search(query)[-12:], "recent_runs": self.ledger.table(8)}

    def tool_memory_write(self, kind, text):
        """Save a note."""
        return {"saved": self.notes.add(kind, text, "agent")}

    def tool_ask_user(self, question, default_if_no_answer=""):
        """Handled by the agent loop; never executed here."""
        return {"asked": question}


def compact_json(result):
    """Serialise a tool result compactly for the LLM context."""
    return json.dumps(result, separators=(",", ":"), default=str)
