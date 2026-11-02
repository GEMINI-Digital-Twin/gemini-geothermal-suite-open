"""Tools the agent can call. Every number comes from these functions, not the LLM.

Inputs are validated against the challenge limits before anything runs, and
results are cached in memory.json so repeated calls cost nothing.
"""

import hashlib
import json
from pathlib import Path

import numpy as np
from costs import design_costs
from plant_json import run_plant
from yearly_energy import (
    ASSUMED_COOLING_COP,
    COOLING_FILE,
    HEATING_FILE,
    EnergyDesign,
    lowest_demand_windows,
    read_demand,
    run_design,
)

ROOT = Path(__file__).parent.parent
MEMORY_FILE = Path(__file__).parent / "memory.json"

DEPTH_RANGE_M = (1500.0, 4000.0)
RETURN_RANGE_C = (30.0, 70.0)
SECONDARY_RANGE_M3H = (20.0, 600.0)
PEAK_RANGE_MW = (1.0, 100.0)


def _load_memory():
    if MEMORY_FILE.exists():
        return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
    return {"runs": {}}


def _save_memory(memory):
    MEMORY_FILE.write_text(json.dumps(memory, indent=1), encoding="utf-8")


def _cached(tool, arguments, compute):
    """Return a cached result for these arguments, or compute and store it."""
    key = hashlib.sha1(json.dumps([tool, arguments], sort_keys=True).encode()).hexdigest()[:12]
    memory = _load_memory()
    if key in memory["runs"]:
        return {**memory["runs"][key]["result"], "from_memory": True}
    result = compute()
    memory["runs"][key] = {"tool": tool, "arguments": arguments, "result": result}
    _save_memory(memory)
    return result


def _out_of_range(name, value, low, high, unit):
    if not low <= value <= high:
        return f"{name}={value} {unit} is outside the allowed range {low}-{high} {unit}."
    return None


def get_requirements():
    """Return the challenge requirements, demand summary and known missing inputs."""
    _, heating = read_demand(HEATING_FILE)
    _, cooling = read_demand(COOLING_FILE)
    return {
        "demand": {
            "heating_peak_mw": float(heating.max()),
            "heating_gwh_per_year": round(float(heating.sum()) * 24 / 1000, 2),
            "cooling_peak_mw": float(cooling.max()),
            "cooling_gwh_per_year": round(float(cooling.sum()) * 24 / 1000, 2),
            "data": "365 daily values for 2027",
        },
        "reservoir": "2,500 m midpoint, 100 m thick, 30 C/km from 12 C, 250 bar, 200 mD. Depth may change.",
        "brine": "1,030 kg/m3, 0.40 mPa.s, 0.8 Nm3 gas per m3 (80% CH4, 20% CO2)",
        "hard_limits": {
            "doublets": "1-3",
            "flow_per_doublet_m3h": "50-300",
            "brine_cooling_max_c": 40,
            "pump_efficiency": 0.7,
            "production_equals_injection": True,
            "geothermal_days_per_doublet_max": 330,
            "heating_supply_c": 100,
            "cooling_supply_c": 20,
            "demand_met_days": 365,
        },
        "missing_inputs": {
            "heating_return_c": "our design choice (organizers, 1 Nov), must not break any limit; working assumption 50; test others with return_c",
            "cooling_return_c": "not given; does not affect the chiller model",
            "outage_scheduling": "not confirmed whether doublets may take outages on different dates",
            "costs": "no prices given; not modelled yet",
        },
        "tools": "simulate_doublet checks one doublet in GEMINI; simulate_year runs a full design for 365 days.",
    }


def simulate_doublet(depth_m, design_flow_m3h, return_c=50.0, secondary_flow_m3h=None):
    """Write and run a one-doublet GEMINI plant file and check the limits."""
    secondary_flow_m3h = design_flow_m3h if secondary_flow_m3h is None else secondary_flow_m3h
    errors = [
        _out_of_range("depth_m", depth_m, *DEPTH_RANGE_M, "m"),
        _out_of_range("design_flow_m3h", design_flow_m3h, 50.0, 300.0, "m3/h"),
        _out_of_range("return_c", return_c, *RETURN_RANGE_C, "C"),
        _out_of_range("secondary_flow_m3h", secondary_flow_m3h, *SECONDARY_RANGE_M3H, "m3/h"),
    ]
    errors = [error for error in errors if error]
    if errors:
        return {"error": " ".join(errors), "nothing_was_run": True}
    arguments = {
        "depth_m": float(depth_m),
        "design_flow_m3h": float(design_flow_m3h),
        "return_c": float(return_c),
        "secondary_flow_m3h": float(secondary_flow_m3h),
    }
    return _cached("simulate_doublet", arguments, lambda: run_plant(**arguments))


def simulate_year(
    doublets, depth_m, separate_outages=True, return_c=50.0, heating_peak_mw=None, cooling_peak_mw=None
):
    """Run a heating and cooling design for 365 days and check the limits.

    ``heating_peak_mw`` and ``cooling_peak_mw`` scale the supplied demand profiles to a
    different peak, for demand scenarios. Left out, the supplied profiles are used.
    """
    errors = [
        _out_of_range("depth_m", depth_m, *DEPTH_RANGE_M, "m"),
        _out_of_range("return_c", return_c, *RETURN_RANGE_C, "C"),
    ]
    if heating_peak_mw is not None:
        errors.append(_out_of_range("heating_peak_mw", heating_peak_mw, *PEAK_RANGE_MW, "MW"))
    if cooling_peak_mw is not None:
        errors.append(_out_of_range("cooling_peak_mw", cooling_peak_mw, *PEAK_RANGE_MW, "MW"))
    if int(doublets) != doublets or not 1 <= doublets <= 3:
        errors.append(f"doublets={doublets} is not allowed; the challenge allows 1-3.")
    errors = [error for error in errors if error]
    if errors:
        return {"error": " ".join(errors), "nothing_was_run": True}
    arguments = {
        "doublets": int(doublets),
        "depth_m": float(depth_m),
        "separate_outages": bool(separate_outages),
        "return_c": float(return_c),
        "heating_peak_mw": None if heating_peak_mw is None else float(heating_peak_mw),
        "cooling_peak_mw": None if cooling_peak_mw is None else float(cooling_peak_mw),
    }

    def compute():
        dates, heating = read_demand(HEATING_FILE)
        _, cooling = read_demand(COOLING_FILE)
        if heating_peak_mw is not None:
            heating = heating * (float(heating_peak_mw) / heating.max())
        if cooling_peak_mw is not None:
            cooling = cooling * (float(cooling_peak_mw) / cooling.max())
        first, second = lowest_demand_windows(heating + cooling / ASSUMED_COOLING_COP)
        design = EnergyDesign(
            int(doublets), float(depth_m), staggered=bool(separate_outages), return_c=float(return_c)
        )
        _, summary = run_design(design, dates, heating, cooling, first, second)
        rounded = {
            key: (round(value, 2) if isinstance(value, float) else value)
            for key, value in summary.items()
            if key not in ("checks", "min_intake_bar")
        }
        rounded["checks_failed"] = [name for name, passed in summary["checks"].items() if not passed]
        rounded["heating_peak_mw_used"] = round(float(heating.max()), 2)
        rounded["cooling_peak_mw_used"] = round(float(cooling.max()), 2)
        rounded["units"] = "energy in GWh per year, power in MW, CO2 in kt per year"
        return rounded

    return _cached("simulate_year", arguments, compute)


def estimate_cost(
    doublets, depth_m, separate_outages=True, return_c=50.0, heating_peak_mw=None, cooling_peak_mw=None
):
    """Return capital, yearly and levelised cost for a design, simulating it if needed."""
    year = simulate_year(
        doublets, depth_m, separate_outages, return_c, heating_peak_mw, cooling_peak_mw
    )
    if "error" in year:
        return year
    return {
        "doublets": int(doublets),
        "depth_m": float(depth_m),
        "return_c": float(return_c),
        "heating_peak_mw_used": year["heating_peak_mw_used"],
        **design_costs(int(doublets), float(depth_m), year),
    }


MAX_COMPARED_DESIGNS = 15


def compare_designs(doublet_options, depths_m, return_c=50.0, heating_peak_mw=None, cooling_peak_mw=None):
    """Simulate and cost every combination, then rank them with the selection rule."""
    combinations = [(count, depth) for count in doublet_options for depth in depths_m]
    if len(combinations) > MAX_COMPARED_DESIGNS:
        return {"error": f"{len(combinations)} designs requested; the limit is {MAX_COMPARED_DESIGNS}.", "nothing_was_run": True}
    rows = []
    for count, depth in combinations:
        scenario = {"return_c": return_c, "heating_peak_mw": heating_peak_mw, "cooling_peak_mw": cooling_peak_mw}
        cost = estimate_cost(count, depth, **scenario)
        if "error" in cost:
            rows.append({"doublets": count, "depth_m": depth, "error": cost["error"]})
            continue
        year = simulate_year(count, depth, **scenario)
        rows.append(
            {
                "doublets": int(count),
                "depth_m": float(depth),
                "return_c": float(return_c),
                "heating_peak_mw_used": year["heating_peak_mw_used"],
                "levelised_cost_eur_per_mwh": cost["levelised_cost_eur_per_mwh"],
                "bought_energy_share_pct": cost["bought_energy_share_pct"],
                "meets_geothermal_first": cost["meets_geothermal_first"],
                "co2_kt": year["co2_kt"],
                "backup_peak_mw": year["backup_peak_mw"],
                "capital_meur": cost["capital_meur"],
                "checks_failed": year["checks_failed"],
            }
        )
    valid = [row for row in rows if "error" not in row and not row["checks_failed"]]
    eligible = [row for row in valid if row["meets_geothermal_first"]]
    ineligible = [row for row in valid if not row["meets_geothermal_first"]]
    pick = lambda group: min(group, key=lambda row: row["levelised_cost_eur_per_mwh"]) if group else None  # noqa: E731
    return {
        "designs": rows,
        "lowest_cost_eligible": pick(eligible),
        "lowest_cost_ineligible": pick(ineligible),
        "rule": "eligible means bought gas heat plus electric cooling is at most 10% of energy delivered",
    }


def recall_runs():
    """Return a short list of earlier runs stored in memory."""
    memory = _load_memory()
    return {
        "runs": [
            {"tool": run["tool"], "arguments": run["arguments"], "checks_failed": run["result"].get("checks_failed")}
            for run in memory["runs"].values()
        ][-15:]
    }


TOOLS = {
    "get_requirements": get_requirements,
    "simulate_doublet": simulate_doublet,
    "simulate_year": simulate_year,
    "estimate_cost": estimate_cost,
    "compare_designs": compare_designs,
    "recall_runs": recall_runs,
}

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_requirements",
            "description": "Get the challenge demand, hard limits and inputs that are still missing.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "simulate_doublet",
            "description": (
                "Generate a GEMINI plant JSON file for ONE doublet at its design point, run GEMINI, "
                "and check flow, brine cooling, pump intake and energy balance. GEMINI solves the "
                "actual flow, which can differ from design_flow_m3h. Lower secondary_flow_m3h "
                "means less brine cooling and a hotter supply."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "depth_m": {"type": "number", "description": "Reservoir depth in m"},
                    "design_flow_m3h": {"type": "number", "description": "Design brine flow, 50-300 m3/h"},
                    "return_c": {"type": "number", "description": "District heating return temperature in C"},
                    "secondary_flow_m3h": {"type": "number", "description": "District water flow through the heat exchanger in m3/h"},
                },
                "required": ["depth_m", "design_flow_m3h"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "simulate_year",
            "description": (
                "Run a full design (doublets, depth) for 365 days of heating and cooling. Returns "
                "geothermal, backup and cooling energy, peaks, electricity, CO2 and failed checks."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "doublets": {"type": "integer", "description": "Number of doublets"},
                    "depth_m": {"type": "number", "description": "Reservoir depth in m"},
                    "separate_outages": {"type": "boolean", "description": "Doublets take their 35 outage days on different dates"},
                    "return_c": {"type": "number", "description": "District heating return temperature in C, our design choice (default 50)"},
                    "heating_peak_mw": {"type": "number", "description": "Only for a demand scenario: scale the heating profile to this peak in MW"},
                    "cooling_peak_mw": {"type": "number", "description": "Only for a demand scenario: scale the cooling profile to this peak in MW"},
                },
                "required": ["doublets", "depth_m"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "estimate_cost",
            "description": (
                "Estimate capital cost, yearly cost and levelised cost of energy (EUR/MWh of heat "
                "and cooling delivered) for a design. Prices partly assumed; see 'basis'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "doublets": {"type": "integer", "description": "Number of doublets"},
                    "depth_m": {"type": "number", "description": "Reservoir depth in m"},
                    "separate_outages": {"type": "boolean", "description": "Doublets take their 35 outage days on different dates"},
                    "return_c": {"type": "number", "description": "District heating return temperature in C, our design choice (default 50)"},
                    "heating_peak_mw": {"type": "number", "description": "Only for a demand scenario: scale the heating profile to this peak in MW"},
                    "cooling_peak_mw": {"type": "number", "description": "Only for a demand scenario: scale the cooling profile to this peak in MW"},
                },
                "required": ["doublets", "depth_m"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_designs",
            "description": (
                "Simulate and cost every combination of doublet counts and depths (at most 15), "
                "then return each design and the lowest-cost eligible and ineligible designs "
                "under the geothermal-first rule. Use this to screen options."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "doublet_options": {"type": "array", "items": {"type": "integer"}, "description": "Doublet counts to compare, e.g. [1, 2, 3]"},
                    "depths_m": {"type": "array", "items": {"type": "number"}, "description": "Depths to compare in m, e.g. [2500, 3000, 3500]"},
                    "return_c": {"type": "number", "description": "District heating return temperature in C, our design choice (default 50)"},
                    "heating_peak_mw": {"type": "number", "description": "Only for a demand scenario: scale the heating profile to this peak in MW"},
                    "cooling_peak_mw": {"type": "number", "description": "Only for a demand scenario: scale the cooling profile to this peak in MW"},
                },
                "required": ["doublet_options", "depths_m"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recall_runs",
            "description": "List earlier runs stored in memory, from this and previous sessions.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


def call_tool(name, arguments):
    """Run a tool by name, returning a JSON-serialisable result."""
    if name not in TOOLS:
        return {"error": f"Unknown tool {name}. Available: {', '.join(TOOLS)}."}
    try:
        result = TOOLS[name](**(arguments or {}))
    except TypeError as error:
        return {"error": f"Bad arguments for {name}: {error}"}
    return json.loads(json.dumps(result, default=lambda value: float(value) if isinstance(value, np.floating) else str(value)))
