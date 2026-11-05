"""The agent's tools: schemas, argument checks (gate 1) and execution.

Each tool returns a compact JSON-able dict (a few hundred tokens), not
365-row tables. Full results stay in the run ledger on disk and can be
fetched with ``get_run``.
"""

import itertools
import json
import time
import warnings
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from gemini_agent import acceptance, reservoir_slot, sandbox
from gemini_agent.fingerprint import code_hash, defaults_hash, demand_hash
from gemini_agent.knowledge import (
    ASSUMPTION_RANGES,
    CHALLENGE_RANGES,
    GAPS,
    assumptions_ledger,
    brief_summary,
)
from gemini_agent.memory import ExplorationLog, run_key
from gemini_agent.physics_gate import check_answer, check_run
from gemini_design.annual import dispatch_day, run_year
from gemini_design.challenge import ASSUMPTIONS, CHALLENGE
from gemini_design.doublet import hydraulics_for
from gemini_design.operations import OperatingRules
from gemini_design.challenge import CHILLER_TYPES
from gemini_design.plant import COOLING, UPGRADES, Design, Plant
from gemini_design.project_json import cross_check as solver_cross_check
from gemini_design.screening import chp_size_mw_el
from gemini_design.storage import STORAGE_TYPE
from gemini_simulator.registry import COMPONENT_REGISTRY

MAX_SCREEN_DESIGNS = 48
# Optional process-wide cache of year runs by run key, shared by every ToolBox. The
# benchmark turns it on so that repeats and backends do not re-simulate identical
# designs; each workspace still records its own runs and gate verdicts.
SHARED_YEAR_CACHE = None
SHARED_YEAR_CACHE_MAX = 400
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
    "free_cooling": {
        "type": "boolean",
        "description": "dry-cooler economizer ahead of an electric chiller; needs outdoor "
        "temperature data (has no effect without it)",
    },
    "chiller_type": {
        "type": "string",
        "enum": list(CHILLER_TYPES),
        "description": "electric chiller technology: legacy (simple fixed-efficiency "
        "model), screw_dry_cooler, centrifugal_tower (wet tower, uses wet-bulb) or "
        "air_cooled_screw",
    },
    "ates_doublets": {
        "type": "integer",
        "minimum": 0,
        "maximum": 8,
        "description": "shallow aquifer cold-store well pairs (150 m3/h each); charged by a dry "
        "cooler in winter, so it needs outdoor temperature data",
    },
    "orc_capacity_mw_el": {
        "type": "number",
        "minimum": 0,
        "maximum": 10,
        "description": "air-cooled ORC power unit (net MW_e) on the brine after the district "
        "HEX and heat pump, down to the 40 K cap; its power offsets plant electricity, the "
        "rest is exported (0 = none)",
    },
    "electric_boiler_mw": {
        "type": "number",
        "minimum": 0,
        "maximum": 40,
        "description": "electric boiler (MW heat) next to the gas boiler; each day the top-up "
        "uses the cheaper of bought gas and grid electricity, CO2 priced (0 = none)",
    },
    "boiler_units": {
        "type": "integer",
        "minimum": 1,
        "maximum": 6,
        "description": "number of equal gas boiler units (default 1); more units cost more per "
        "MW and keep part-load efficiency up (boiler_part_load assumption)",
    },
    "esp_rated_flow_m3h": {
        "type": "number",
        "minimum": 0,
        "maximum": 300,
        "description": "downhole pump (ESP) of each producer sized for this best-efficiency "
        "flow, 50-300 m3/h: it then has a pump curve, an operating flow range, efficiency "
        "falling away from the rated flow, and its own cost. 0 = ideal pump (any flow, fixed "
        "efficiency, cost inside the surface cost)",
    },
    "esp_drive": {
        "type": "string",
        "enum": ["vsd", "fixed"],
        "description": "drive of a sized ESP: vsd = variable speed (wider flow range, drive "
        "loss and cost); fixed = fixed speed, head the well does not need is choked",
    },
    "heat_recovery_hp_mw": {
        "type": "number",
        "minimum": 0,
        "maximum": 20,
        "description": "heat-recovery heat pump (MW of cooling): cools the chilled water and "
        "heats the district return line (up to 70 degC); run on days it is cheaper (0 = none)",
    },
    "doublet_depths_m": {
        "type": "array",
        "items": {"type": "number", "minimum": 1000, "maximum": 4500},
        "description": "depth of each doublet (m TVD), one per doublet, when they differ; "
        "replaces depth_m. The doublets share one surface plant: their brine mixes, is "
        "re-injected at one temperature, and the 40 K cap applies to every producer",
    },
    "heating_return_c": {
        "type": "number",
        "minimum": 25,
        "maximum": 70,
        "description": "district heating return temperature (degC). Not given: 40. Other "
        "values change the plant physics and are priced: customer substation plate area "
        "(the return must stay 2 K above the 30 degC building circuit return) and network "
        "pumping, relative to a 40 degC network",
    },
    "cooling_return_c": {
        "type": "number",
        "minimum": 21,
        "maximum": 32,
        "description": "district cooling return temperature (degC). Not given: 26. Priced like "
        "heating_return_c, relative to a 26 degC network (at most 2 K below the 32 degC "
        "building circuit return)",
    },
    "outage_start_days": {
        "type": "array",
        "items": {"type": "integer", "minimum": -1, "maximum": 330},
        "description": "first day (0 = 1 January) of each doublet's 35-day geothermal stop, "
        "one entry per doublet; -1 places that doublet's stop in the lowest-load free window. "
        "Not given: each doublet stops at a different time in the lowest-load windows",
    },
    "operating_rules": {
        "type": "boolean",
        "description": "link the days: minimum run and stop times and a cost per doublet "
        "start, and wellbore warm-up after a start (gemini_design.operations)",
    },
    "storage_mwh": {
        "type": "number",
        "minimum": 0,
        "maximum": 50000,
        "description": "seasonal heat store capacity (MWh_th); needs a registered "
        "'thermal_storage' model (GEMINI has none: write one with write_model first)",
    },
    "storage_mw": {
        "type": "number",
        "minimum": 0,
        "maximum": 40,
        "description": "heat store charge/discharge rating (MW_th); required with storage_mwh",
    },
    "pit_store_m3": {
        "type": "number",
        "minimum": 0,
        "maximum": 1500000,
        "description": "seasonal pit thermal energy store, water volume (m3); built-in "
        "stratified model (gemini_design.pit_storage): 30,000-250,000 m3 per pit (larger = "
        "several pits), top at most 90 degC, boiler top-up to the 100 degC supply, surface "
        "heat losses, size-dependent cost and land",
    },
    "pit_store_mw": {
        "type": "number",
        "minimum": 0,
        "maximum": 40,
        "description": "pit store charge/discharge rating (MW_th at 90 degC top, 40 degC "
        "return); required with pit_store_m3",
    },
    "assumptions": _ASSUMPTION_OVERRIDES,
}

# run_design arguments that the screen can also vary (the grid arguments cover the rest)
SCREEN_VARY_KEYS = tuple(
    k
    for k in _DESIGN_PROPS
    if k
    not in (
        "n_doublets",
        "depth_m",
        "upgrade",
        "cooling",
        "chp",
        "chiller_type",
        "orc_capacity_mw_el",
        "assumptions",
    )
)

# Harder conditions for stress_test. Reservoir values are the P90 (low) ends of the
# gemini_uncertainty distributions: permeability log-normal P10-P90 100-400 mD around 200,
# gradient normal 30 +- 1.5 degC/km (P90 low = 30 - 1.28 x 1.5 = 28.1). Demand +10 % is
# about the P90 of the 6 % (heating) and 10 % (cooling) 1-sd demand spreads.
STRESS_CASES = {
    "reservoir_low": {
        "text": "permeability 100 mD and gradient 28.1 degC/km (low ends of their P10-P90 "
        "ranges)",
        "overrides": {"permeability_md": 100.0, "geothermal_gradient_c_per_km": 28.1},
    },
    "demand_high": {
        "text": "heating and cooling demand x1.10 every day",
        "overrides": {"demand_scale": 1.10},
    },
    "trip_at_peak": {
        "text": "one doublet's 35-day stop starts unplanned on the day of peak heating demand",
        "trip": True,
    },
    "boiler_unit_out": {
        "text": "one gas boiler unit unavailable all year (N-1; with one unit, no gas boiler)",
        "boiler_n_minus_1": True,
    },
    "combined": {
        "text": "low reservoir, high demand and the trip at peak at once",
        "overrides": {
            "permeability_md": 100.0,
            "geothermal_gradient_c_per_km": 28.1,
            "demand_scale": 1.10,
        },
        "trip": True,
    },
}

COMPARE_KEYS = (
    "lcoe_eur_per_mwh",
    "co2_t_per_year",
    "capex_meur",
    "geothermal_share_of_heat_pct",
    "purchased_gas_mwh",
    "grid_import_mwh",
    "unmet_heating_mwh",
    "unmet_cooling_mwh",
)

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
        "and return the best designs. At most 48 combinations. chiller_types applies to "
        "electric cooling only (default ['legacy']). Any other run_design argument can be "
        "varied with 'vary'.",
        "parameters": {
            "type": "object",
            "properties": {
                "n_doublets": {"type": "array", "items": {"type": "integer"}},
                "depths_m": {"type": "array", "items": {"type": "number"}},
                "upgrades": {"type": "array", "items": {"type": "string", "enum": list(UPGRADES)}},
                "coolings": {"type": "array", "items": {"type": "string", "enum": list(COOLING)}},
                "chp": {"type": "array", "items": {"type": "boolean"}},
                "chiller_types": {
                    "type": "array",
                    "items": {"type": "string", "enum": list(CHILLER_TYPES)},
                },
                "orc_capacity_mw_el": {
                    "type": "array",
                    "items": {"type": "number", "minimum": 0, "maximum": 10},
                    "description": "ORC power unit ratings to try (net MW_e, 0 = none; "
                    "default [0])",
                },
                "vary": {
                    "type": "object",
                    "description": "Other run_design arguments to vary, each a list of values, "
                    'e.g. {"boiler_capacity_mw": [20, 30], "ates_doublets": [0, 2]}. Allowed '
                    "keys: " + ", ".join(SCREEN_VARY_KEYS) + ". A key not given keeps the "
                    "run_design default. Combinations a design can not have are skipped and "
                    "reported.",
                },
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
    "stress_test": {
        "description": "Re-run a design (from a run id) in harder conditions and report whether "
        "it still meets every rule and all demand. Cases: "
        + "; ".join(f"{k}: {v['text']}" for k, v in STRESS_CASES.items())
        + ". Default: all cases.",
        "parameters": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
                "cases": {"type": "array", "items": {"type": "string", "enum": list(STRESS_CASES)}},
            },
            "required": ["run_id"],
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
        "description": "Add a missing component model: Python code for one StaticModel "
        "subclass (import it with 'from gemini_model.model_abstract import StaticModel'; "
        "call super().__init__() and set defaults in self.parameters; "
        "calculate_output(self, u, x=None) stores a dict in self.output, read with "
        "get_output()) plus pytest tests that import it by its module name "
        "('from <name> import <Class>'). Code is sandboxed. It is registered only if your "
        "tests pass AND the harness acceptance tests pass (energy balance, second law, limits, "
        "edge cases, written by the harness, not by you). For a type in list_models "
        "model_contracts (dry_cooler, thermal_storage) use exactly that contract's input and "
        "output names and units.",
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
    "compare_runs": {
        "description": "Compare a design run with a baseline run: both KPIs, the differences "
        "and whether it is better on cost and CO2 (dominates), worse on both (dominated), a "
        "trade-off, or infeasible.",
        "parameters": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
                "baseline_run_id": {"type": "string"},
            },
            "required": ["run_id", "baseline_run_id"],
        },
    },
    "log_option": {
        "description": "Record your verdict on a design option you explored against the "
        "baseline: accept (replaces the baseline), alternative (worth reporting) or reject, "
        "with a one-sentence reason. Numbers in the reason are checked against the two runs.",
        "parameters": {
            "type": "object",
            "properties": {
                "option": {"type": "string", "description": "short label, e.g. 'deeper wells'"},
                "run_id": {"type": "string"},
                "baseline_run_id": {"type": "string"},
                "verdict": {"type": "string", "enum": list(ExplorationLog.VERDICTS)},
                "reason": {"type": "string"},
            },
            "required": ["option", "run_id", "baseline_run_id", "verdict", "reason"],
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
        "description": "Project notes (decisions, assumptions, lessons), the latest runs and "
        "the design options explored so far with their verdicts.",
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
    storage_mwh, storage_mw = float(args.get("storage_mwh", 0)), float(args.get("storage_mw", 0))
    if (storage_mwh > 0) != (storage_mw > 0):
        raise ToolError("storage needs both storage_mwh and storage_mw above 0")
    pit_m3, pit_mw = float(args.get("pit_store_m3", 0)), float(args.get("pit_store_mw", 0))
    if (pit_m3 > 0) != (pit_mw > 0):
        raise ToolError("a pit store needs both pit_store_m3 and pit_store_mw above 0")
    if pit_m3 > 0 and storage_mwh > 0:
        raise ToolError("use either pit_store_m3 or storage_mwh, not both")
    if 0 < pit_m3 < ASSUMPTIONS["pit_store_volume_min_m3"]:
        raise ToolError(
            f"pit_store_m3 must be at least {ASSUMPTIONS['pit_store_volume_min_m3']:,.0f} m3"
        )
    return Design(
        n_doublets=int(args["n_doublets"]),
        depth_m=float(args["depth_m"]),
        upgrade=upgrade,
        cooling=cooling,
        free_cooling=bool(args.get("free_cooling", False)),
        chiller_type=str(args.get("chiller_type", "legacy")),
        ates_doublets=int(args.get("ates_doublets", 0)),
        orc_capacity_mw_el=float(args.get("orc_capacity_mw_el", 0.0)),
        outage_start_days=tuple(args.get("outage_start_days") or ()),
        doublet_depths_m=tuple(args.get("doublet_depths_m") or ()),
        electric_boiler_mw=float(args.get("electric_boiler_mw", 0.0)),
        heat_recovery_hp_mw=float(args.get("heat_recovery_hp_mw", 0.0)),
        boiler_units=int(args.get("boiler_units", 1)),
        esp_rated_flow_m3h=float(args.get("esp_rated_flow_m3h", 0.0)),
        esp_drive=str(args.get("esp_drive", "vsd")),
        heating_return_c=args.get("heating_return_c"),
        cooling_return_c=args.get("cooling_return_c"),
        storage_mwh=storage_mwh,
        storage_mw=storage_mw,
        pit_store_m3=pit_m3,
        pit_store_mw=pit_mw,
        **sizes,
    )


def _orc_headline(design, energy, econ):
    """ORC output for the agent; says so plainly when an installed unit never ran."""
    rating = float(design.get("orc_capacity_mw_el", 0.0) or 0.0)
    if rating <= 0:
        return {}
    out = {
        "orc_electricity_mwh": energy["orc_electricity"],
        "orc_full_load_hours": energy["orc_electricity"] / rating,
        "orc_capex_meur": econ["capex_eur"].get("orc", 0.0) / 1e6,
        "grid_export_mwh": energy["grid_export"],
    }
    if energy["orc_electricity"] < 1.0:
        out["orc_note"] = (
            "The ORC unit never ran: on every day the dispatcher found it cheaper not to pump "
            "the extra brine it needs, or the brine left after the district heating was below "
            "its outlet floor or minimum load. Its CAPEX is still charged, so the same design "
            "without the ORC is cheaper."
        )
    return out


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
            **_orc_headline(d, e, econ),
            "co2_t_per_year": k["co2_t_per_year"],
            "capex_meur": econ["capex_eur"]["total"] / 1e6,
            "lcoe_eur_per_mwh": econ["lcoe_eur_per_mwh"],
            "max_flow_per_doublet_m3h": k["max_flow_per_doublet_m3h"],
            "max_brine_cooling_k": k["max_brine_cooling_k"],
            "associated_gas_flared_mwh_fuel": k["associated_gas_unused_mwh"],
            **(
                {"doublet_starts": summary["operations"]["doublet_starts"]}
                if "operations" in summary
                else {}
            ),
            **(
                {
                    "storage_discharge_mwh": e["storage_discharge"],
                    "storage_loss_mwh": e["storage_loss"],
                    **(
                        {"storage_boiler_topup_mwh": summary["pit_store"]["boiler_topup_mwh"]}
                        if "pit_store" in summary
                        else {}
                    ),
                }
                if e.get("storage_discharge")
                else {}
            ),
            "physics_gate": "pass" if gate["passed"] else "FAIL",
        }
    )


def _year_worker(args):
    design, demand, challenge, assumptions, *rest = args
    operations = rest[0] if rest else None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        daily, summary = run_year(design, demand, challenge, assumptions, operations=operations)
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
        self.exploration = ExplorationLog(workspace)

    def _years(self, jobs, keys):
        """Year runs for ``jobs`` (in parallel), served from the shared cache when on."""
        cache = SHARED_YEAR_CACHE
        todo = [i for i, k in enumerate(keys) if cache is None or k not in cache]
        fresh = [jobs[i] for i in todo]
        if self.workers > 1 and len(fresh) > 1:
            with ProcessPoolExecutor(max_workers=self.workers) as pool:
                done = list(pool.map(_year_worker, fresh))
        else:
            done = [_year_worker(j) for j in fresh]
        out = {i: r for i, r in zip(todo, done)}
        if cache is not None:
            out.update({i: cache[k] for i, k in enumerate(keys) if i not in out})
            for i in todo:
                cache[keys[i]] = out[i]
            while len(cache) > SHARED_YEAR_CACHE_MAX:  # keep memory bounded (oldest first)
                cache.pop(next(iter(cache)))
        return [out[i] for i in range(len(jobs))]

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
                "weather": (
                    {
                        "loaded": True,
                        "outdoor_min_c": dem["ambient_c"].min(),
                        "outdoor_max_c": dem["ambient_c"].max(),
                        "note": "measured daily outdoor temperature: free_cooling and "
                        "ates_doublets use it",
                    }
                    if "ambient_c" in dem
                    else {
                        "loaded": False,
                        "note": "no outdoor temperature: free cooling gives 0 and ATES "
                        "designs fail with MissingWeatherError",
                    }
                ),
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
            "design_options": {
                "upgrade": list(UPGRADES),
                "cooling": list(COOLING),
                "chiller_type": list(CHILLER_TYPES),
                "free_cooling": "dry-cooler economizer ahead of an electric chiller "
                "(needs weather)",
                "ates_doublets": "0-8 shallow aquifer cold-store well pairs (needs weather)",
                "chp": "gas engine on the co-produced gas",
                "operating_rules": "minimum run/stop times, start cost and well warm-up",
                "orc_capacity_mw_el": "0 = none, or the net rating of an ORC power unit",
                "electric_boiler_mw": "electric boiler next to the gas boiler (MW heat)",
                "boiler_units": "gas boiler split into equal units",
                "esp_rated_flow_m3h / esp_drive": "sized downhole pump per producer "
                "(rating, curve, flow range, cost) and its drive (vsd or fixed)",
                "heat_recovery_hp_mw": "heat pump from the chilled water to the heating "
                "return line (MW cooling)",
                "doublet_depths_m": "one depth per doublet when they differ (shared surface "
                "plant, brine mixed, 40 K cap on every producer)",
                "heating_return_c / cooling_return_c": "district return temperatures, "
                "priced against a 40 / 26 degC network (substation area, network pumping)",
                "outage_start_days": "start day of each doublet's 35-day geothermal stop "
                "(one per doublet, -1 = automatic in the lowest-load window)",
                "pit_store": "built-in seasonal pit thermal energy store (pit_store_m3, "
                "pit_store_mw): stratified water pit, 90 degC top, boiler top-up to 100 degC, "
                "lid and ground losses, 30,000-250,000 m3 per pit",
            },
            "reservoir_providers": reservoir_slot.available_providers(),
            "model_slots": {
                STORAGE_TYPE: (
                    "registered" if STORAGE_TYPE in COMPONENT_REGISTRY else "EMPTY (write it)"
                )
                + ": another seasonal heat store model (energy only, your own), used by "
                "designs with storage_mwh > 0",
                "dry_cooler": (
                    "registered" if "dry_cooler" in COMPONENT_REGISTRY else "EMPTY (write it)"
                )
                + ": standalone dry cooler component (the screw_dry_cooler chiller option "
                "uses a fixed condenser approach, not this model)",
            },
            "model_contracts": acceptance.describe_contracts(),
            "missing_models_ideas": [
                "other heat store types, e.g. borehole or tank stores (thermal_storage slot)",
                "dry cooler with hourly weather",
                "thermal breakthrough over 30 years",
            ],
        }

    def _run_key(self, design, overrides, kind="design", operations=None):
        """Ledger key of a year run: the same design and inputs give the same key."""
        spec = {"design": design.as_dict(), "overrides": overrides or {}}
        if operations is not None:  # runs with operating rules are other runs
            spec["operating_rules"] = operations.as_dict()
        if design.storage_mwh > 0:  # runs with another storage model are other runs
            cls = COMPONENT_REGISTRY.get(STORAGE_TYPE)
            spec["storage_model"] = getattr(cls, "_source_hash", getattr(cls, "__name__", None))
        # runs on other demand or weather, other code or other defaults are other runs:
        # a reused workspace must never hand back numbers made from different inputs
        spec["inputs"] = {
            "demand": demand_hash(self.demand),
            "code": code_hash(),
            "defaults": defaults_hash(),
        }
        return run_key(kind, spec)

    def _run(self, design, overrides, request, kind="design", operations=None):
        challenge, assumptions, demand_scale = split_overrides(overrides)
        key = self._run_key(design, overrides, kind, operations)
        existing = self.ledger.find(key)
        if existing:
            entry = self.ledger.get(existing)
            return {"run_id": existing, "reused_earlier_run": True, **entry["headline"]}
        demand = self.demand
        if demand_scale != 1.0:
            demand = demand.copy()
            demand[["heating_mw", "cooling_mw"]] *= demand_scale
        job = (design, demand, challenge, assumptions, operations)
        summary, daily = self._years([job], [key])[0]
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
        if design.doublet_depths_m:
            return {
                "agrees": None,
                "note": "not run: GEMINI's project schema holds one producer per flowsheet, and "
                "this design mixes brine from doublets at different depths",
            }
        hyd = hydraulics_for(design, challenge, assumptions)
        plant = Plant(design, hyd, challenge, assumptions)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            load = "plant_heating_load_w" if "plant_heating_load_w" in daily else "heating_demand_w"
            point = dispatch_day(
                plant,
                float(daily.loc[i, load]),
                float(daily.loc[i, "cooling_demand_w"]),
                int(daily.loc[i, "n_available"]),
                challenge,
                ambient_c=float(demand.loc[i, "ambient_c"]) if "ambient_c" in demand else None,
                wet_bulb_c=float(demand.loc[i, "wet_bulb_c"]) if "wet_bulb_c" in demand else None,
                ambient_mean_c=(
                    float(demand.loc[i, "ambient_mean_c"]) if "ambient_mean_c" in demand else None
                ),
                ates_cooling_w=(
                    float(daily.loc[i, "ates_cooling_w"]) if "ates_cooling_w" in daily else 0.0
                ),
                ates_power_w=(
                    float(daily.loc[i, "ates_power_w"]) if "ates_power_w" in daily else 0.0
                ),
            )
        if point["n_active"] < 1:
            return {
                "day": i + 1,
                "date": str(demand.loc[i, "date"].date()),
                "agrees": None,
                "note": "no doublet running that day (geothermal outage or no heat needed)",
            }
        _, check = solver_cross_check(
            design, hyd, point, challenge=challenge, assumptions=assumptions
        )
        out = {"day": i + 1, "date": str(demand.loc[i, "date"].date())}
        out.update(_round(check))
        return out

    def tool_run_design(self, assumptions=None, **args):
        """Simulate one design for a year."""
        operations = OperatingRules() if args.get("operating_rules") else None
        design = make_design(args, self.peak_heating_mw, self.peak_cooling_mw)
        return self._run(
            design, assumptions, {**args, "assumptions": assumptions or {}}, operations=operations
        )

    def tool_screen(
        self,
        n_doublets,
        depths_m,
        upgrades,
        coolings,
        chp=(False,),
        chiller_types=("legacy",),
        orc_capacity_mw_el=(0.0,),
        vary=None,
        assumptions=None,
        top=5,
    ):
        """Run a grid of designs in parallel and rank them."""
        chiller_types = list(dict.fromkeys(chiller_types or ["legacy"]))
        orcs = list(dict.fromkeys(float(x) for x in (orc_capacity_mw_el or [0.0])))
        vary = dict(vary or {})
        for key, values in vary.items():
            if key not in SCREEN_VARY_KEYS:
                allowed = ", ".join(SCREEN_VARY_KEYS)
                raise ToolError(f"'{key}' can not be varied. Allowed: {allowed}")
            if not isinstance(values, list) or not values:
                raise ToolError(f"vary['{key}'] must be a non-empty list of values")
            errors = [e for v in values for e in _check_value(key, v, _DESIGN_PROPS[key])]
            if errors:
                raise ToolError("; ".join(errors))
            vary[key] = list(dict.fromkeys(values))
        extra = [dict(zip(vary, combo)) for combo in itertools.product(*vary.values())] or [{}]
        combos = [
            (n, d, u, c, h, t, o, x)
            for n in n_doublets
            for d in depths_m
            for u in upgrades
            for c in coolings
            for h in dict.fromkeys(chp)
            for t in (chiller_types if c == "electric" else ["legacy"])
            for o in orcs
            for x in extra
        ]
        if not combos:
            raise ToolError("empty grid")
        if len(combos) > MAX_SCREEN_DESIGNS:
            raise ToolError(f"{len(combos)} designs requested; the limit is {MAX_SCREEN_DESIGNS}")
        for n, d, *_, t, _o, _x in combos:
            if t not in CHILLER_TYPES:
                raise ToolError(f"chiller type must be one of {list(CHILLER_TYPES)}")
            if not 1 <= n <= 3 or not 1000 <= d <= 4500:
                raise ToolError("n_doublets must be 1-3 and depths 1000-4500 m")
        challenge, assumptions_d, demand_scale = split_overrides(assumptions)
        demand = self.demand
        if demand_scale != 1.0:
            demand = demand.copy()
            demand[["heating_mw", "cooling_mw"]] *= demand_scale
        designs, skipped, seen = [], {}, set()
        for n, d, u, c, h, t, o, x in combos:
            args = {
                "n_doublets": n,
                "depth_m": d,
                "upgrade": u,
                "cooling": c,
                "chp": h,
                "chiller_type": t,
                "orc_capacity_mw_el": o,
                **x,
            }
            ops = OperatingRules() if args.pop("operating_rules", False) else None
            try:
                design = make_design(args, self.peak_heating_mw, self.peak_cooling_mw)
            except (ToolError, ValueError) as exc:
                skipped[str(exc)] = skipped.get(str(exc), 0) + 1
                continue
            sig = (repr(sorted(design.as_dict().items())), ops is not None)
            if sig not in seen:  # e.g. chiller sizes varied on designs without that chiller
                seen.add(sig)
                designs.append((design, ops))
        if not designs:
            raise ToolError(f"no valid design in the grid: {skipped}")
        if any(design.storage_mwh > 0 for design, _ in designs) and (
            STORAGE_TYPE not in COMPONENT_REGISTRY
        ):
            raise ToolError("storage_mwh needs a registered 'thermal_storage' model")
        rows, todo = [], []
        for design, ops in designs:
            key = self._run_key(design, assumptions, operations=ops)
            found = self.ledger.find(key)
            if found:
                rows.append({"run_id": found, **self.ledger.get(found)["headline"]})
            else:
                todo.append((design, ops, key))
        if todo:
            jobs = [(d, demand, challenge, assumptions_d, ops) for d, ops, _ in todo]
            results = self._years(jobs, [k for *_, k in todo])
            for (design, ops, key), (summary, daily) in zip(todo, results):
                request = {**design.as_dict(), "assumptions": assumptions or {}}
                if ops is not None:
                    request["operating_rules"] = True
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
        if skipped:
            out["skipped_combinations"] = skipped
        out["screen_id"] = self.ledger.add(
            "screen",
            None,
            {"grid": [c[:7] for c in combos], "vary": vary, "assumptions": assumptions or {}},
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

    def tool_stress_test(self, run_id, cases=None):
        """Re-run an earlier design in harder conditions (STRESS_CASES)."""
        if run_id not in self.ledger.entries or self.ledger.get(run_id)["kind"] != "design":
            raise ToolError(f"unknown design run '{run_id}'")
        entry = self.ledger.get(run_id)
        request = dict(entry["request"])
        base_overrides = dict(request.pop("assumptions", {}) or {})
        for k in ("name", "notes"):
            request.pop(k, None)
        operations = OperatingRules() if request.get("operating_rules") else None
        n_days = len(self.demand)
        outage = max(0, n_days - int(CHALLENGE["operating_days"]))
        peak_day = min(int(np.argmax(self.demand["heating_mw"].to_numpy())), n_days - outage)
        rows = []
        for case in list(dict.fromkeys(cases or STRESS_CASES)):
            spec = STRESS_CASES[case]
            overrides = dict(base_overrides)
            for k, v in spec.get("overrides", {}).items():
                if k == "demand_scale":
                    overrides[k] = float(overrides.get(k, 1.0)) * v
                elif k in ("permeability_md", "geothermal_gradient_c_per_km"):
                    overrides[k] = min(float(overrides.get(k, v)), v)
                else:
                    overrides[k] = v
            args = dict(request)
            if spec.get("trip"):
                n = int(args["n_doublets"])
                starts = list(args.get("outage_start_days") or [-1] * n)
                starts[0] = peak_day
                args["outage_start_days"] = starts
            if spec.get("boiler_n_minus_1"):
                full = make_design(args, self.peak_heating_mw, self.peak_cooling_mw)
                units = full.boiler_units
                args["boiler_capacity_mw"] = full.boiler_capacity_mw * (units - 1) / units
                args["boiler_units"] = max(1, units - 1)
            design = make_design(args, self.peak_heating_mw, self.peak_cooling_mw)
            request_i = {**args, "assumptions": overrides}
            r = self._run(design, overrides, request_i, operations=operations)
            rows.append(
                {
                    "case": case,
                    "run_id": r["run_id"],
                    "meets_all_hard_rules": r["meets_all_hard_rules"],
                    "unmet_heating_mwh": r["unmet_heating_mwh"],
                    "unmet_cooling_mwh": r["unmet_cooling_mwh"],
                    "failed_rules": r["failed_rules"],
                    "lcoe_eur_per_mwh": r["lcoe_eur_per_mwh"],
                    "co2_t_per_year": r["co2_t_per_year"],
                    "physics_gate": r["physics_gate"],
                }
            )
        return {
            "base_run": run_id,
            "design": entry["headline"]["design"],
            "peak_heating_day": peak_day + 1,
            "cases": rows,
        }

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

    def _design_entry(self, run_id):
        if run_id not in self.ledger.entries or self.ledger.get(run_id)["kind"] != "design":
            raise ToolError(f"unknown design run '{run_id}'")
        return self.ledger.get(run_id)

    def tool_compare_runs(self, run_id, baseline_run_id):
        """Compare a run with a baseline: both KPIs, their differences and a Pareto label."""
        new, base = self._design_entry(run_id), self._design_entry(baseline_run_id)
        h, b = new["headline"], base["headline"]
        if not (new["valid"] and base["valid"]):
            raise ToolError("both runs must pass the physics gate before they are compared")
        delta = {k: _round(h.get(k, 0.0) - b.get(k, 0.0)) for k in COMPARE_KEYS}
        if not h["meets_all_hard_rules"]:
            label = "infeasible (fails: " + ", ".join(h["failed_rules"]) + ")"
        else:
            cheaper = delta["lcoe_eur_per_mwh"] < 0
            cleaner = delta["co2_t_per_year"] < 0
            if cheaper and cleaner:
                label = "dominates the baseline (cheaper and lower CO2)"
            elif not cheaper and not cleaner:
                label = "dominated by the baseline (no cheaper, no lower CO2)"
            else:
                label = "trade-off: " + (
                    "cheaper but more CO2" if cheaper else "lower CO2 but dearer"
                )
        return {
            "run_id": run_id,
            "design": h["design"],
            "baseline_run_id": baseline_run_id,
            "baseline_design": b["design"],
            "run": {k: h.get(k) for k in COMPARE_KEYS},
            "baseline": {k: b.get(k) for k in COMPARE_KEYS},
            "delta": delta,
            "lcoe_change_pct": _round(100.0 * delta["lcoe_eur_per_mwh"] / b["lcoe_eur_per_mwh"]),
            "co2_change_pct": _round(100.0 * delta["co2_t_per_year"] / b["co2_t_per_year"]),
            "pareto": label,
        }

    def tool_log_option(self, option, run_id, baseline_run_id, verdict, reason):
        """Record a verdict on an explored option; the reason's numbers must trace to runs."""
        comparison = self.tool_compare_runs(run_id, baseline_run_id)
        if verdict == "accept" and not comparison["pareto"].startswith(("dominates", "trade")):
            raise ToolError(
                f"cannot accept {comparison['design']}: it is {comparison['pareto']}. "
                "Use 'reject', or 'alternative' if it is worth reporting."
            )
        new, base = self.ledger.get(run_id), self.ledger.get(baseline_run_id)
        evidence = [comparison, new["headline"], base["headline"]]
        for rid in (run_id, baseline_run_id):
            summary = self.ledger.summary(rid)
            if summary is not None:
                evidence.append(summary)
        errors = check_answer(reason, evidence, [brief_summary(), CHALLENGE], self.ledger)
        errors = [e for e in errors if "cites no run id" not in e]
        if errors:
            return {"error": "reason rejected (physics gate 6)", "details": errors}
        entry = self.exploration.add(
            {
                "option": option,
                "design": comparison["design"],
                "run_id": run_id,
                "baseline_run_id": baseline_run_id,
                "verdict": verdict,
                "reason": reason.strip(),
                "lcoe_eur_per_mwh": comparison["run"]["lcoe_eur_per_mwh"],
                "co2_t_per_year": comparison["run"]["co2_t_per_year"],
                "delta": comparison["delta"],
                "pareto": comparison["pareto"],
            }
        )
        if verdict != "reject":
            self.notes.add(
                "decision" if verdict == "accept" else "lesson",
                f"{option} ({comparison['design']}, {run_id}): {verdict}. {reason.strip()}",
                "agent",
            )
        return {
            "logged": len(self.exploration.entries),
            "option": option,
            "verdict": verdict,
            "pareto": entry["pareto"],
        }

    def tool_reservoir_simulation(self, depth_m, provider="auto", **kwargs):
        """Reservoir provider call (analytic now, Fimbul when installed)."""
        return _round(reservoir_slot.simulate(provider=provider, depth_m=depth_m, **kwargs))

    def tool_write_model(self, name, register_as, code, test_code):
        """Sandboxed model writing."""
        result = sandbox.write_model(name, code, test_code, register_as, self.workspace)
        if result.get("ok"):
            self.notes.add(
                "model",
                f"agent wrote '{register_as}' ({result['class']}); own and harness tests pass",
                "agent",
            )
        return result

    def tool_memory_read(self, query=""):
        """Project notes plus the latest runs."""
        out = {"notes": self.notes.search(query)[-12:], "recent_runs": self.ledger.table(8)}
        if self.exploration.entries:
            keep = ("option", "design", "run_id", "verdict", "lcoe_eur_per_mwh", "co2_t_per_year")
            out["exploration"] = [
                {**{k: e[k] for k in keep}, "reason": e["reason"][:160]}
                for e in self.exploration.entries[-12:]
            ]
        return out

    def tool_memory_write(self, kind, text):
        """Save a note."""
        return {"saved": self.notes.add(kind, text, "agent")}

    def tool_ask_user(self, question, default_if_no_answer=""):
        """Do nothing: the agent loop handles ask_user, so this never runs."""
        return {"asked": question}


def compact_json(result):
    """Serialise a tool result compactly for the LLM context."""
    return json.dumps(result, separators=(",", ":"), default=str)
