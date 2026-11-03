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
from plant_year import run_year, save
from uncertainty import assess
from yearly_energy import (
    ASSUMED_COOLING_COP,
    COOLING_FILE,
    COOLING_OPTIONS,
    HEATING_TOP_UPS,
    HEATING_FILE,
    EnergyDesign,
    lowest_demand_windows,
    read_demand,
    run_design,
)
from yearly_heating import OUTAGE_DAYS

ROOT = Path(__file__).parent.parent
MEMORY_FILE = Path(__file__).parent / "memory.json"
# Change this whenever the models change, so results from older models are not reused.
MODEL_VERSION = "2026-11-03 layouts, flared gas CO2, GEMINI chiller"

DEPTH_RANGE_M = (1500.0, 4000.0)
RETURN_RANGE_C = (30.0, 70.0)
SECONDARY_RANGE_M3H = (20.0, 600.0)
PEAK_RANGE_MW = (1.0, 100.0)
RETURN_OPTIONS_MAX = 6
FAILURE_DAYS_RANGE = (1, 35)
SAME_COST_EUR_PER_MWH = 0.05
LAYOUTS = [f"{top_up}+{cooling}" for top_up in HEATING_TOP_UPS for cooling in COOLING_OPTIONS]
DEFAULT_LAYOUT = "boiler+absorption"


def _layout_error(layout):
    if layout not in LAYOUTS:
        return f"layout={layout} is not known. Use one of {', '.join(LAYOUTS)}."
    return None


def _load_memory():
    if MEMORY_FILE.exists():
        return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
    return {"runs": {}}


def _save_memory(memory):
    MEMORY_FILE.write_text(json.dumps(memory, indent=1), encoding="utf-8")


def _cached(tool, arguments, compute):
    """Return a cached result for these arguments, or compute and store it."""
    key = hashlib.sha1(json.dumps([MODEL_VERSION, tool, arguments], sort_keys=True).encode()).hexdigest()[:12]
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


def _demand(heating_peak_mw=None, cooling_peak_mw=None):
    """Return dates, heating and cooling in MW, and the two planned outage start days."""
    dates, heating = read_demand(HEATING_FILE)
    _, cooling = read_demand(COOLING_FILE)
    if heating_peak_mw is not None:
        heating = heating * (float(heating_peak_mw) / heating.max())
    if cooling_peak_mw is not None:
        cooling = cooling * (float(cooling_peak_mw) / cooling.max())
    first, second = lowest_demand_windows(heating + cooling / ASSUMED_COOLING_COP)
    return dates, heating, cooling, first, second


def unplanned_outages(doublets, failure_start, failure_days, first, second):
    """Return an outage schedule where doublet 1 fails unplanned, keeping 35 days in total.

    Doublet 1 loses ``failure_days`` from ``failure_start`` and its planned outage is
    shortened by the same amount. The other doublets keep their planned dates.
    """
    outages = np.zeros((doublets, 365), dtype=bool)
    outages[0, failure_start : failure_start + failure_days] = True
    outages[0, first : first + OUTAGE_DAYS - failure_days] = True
    for index in range(1, doublets):
        window = second if index % 2 == 1 else first
        outages[index, window : window + OUTAGE_DAYS] = True
    return outages


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
            "outage_scheduling": "our design choice (organizers, 1 Nov); doublets take their 35 days on different low-demand dates",
            "unplanned_failure": "not specified; test the chosen design with check_unplanned_outage",
            "prices": "not given; estimate_cost uses stated assumptions, see its 'basis'",
        },
        "layouts": {
            "boiler+absorption": "produced gas and backup gas boiler reach 100 C; absorption chiller driven by brine",
            "boiler+electric": "gas boilers reach 100 C; electric chillers only",
            "heat_pump+absorption": "a heat pump takes more heat from the brine (within the 40 C limit) and lifts water to 100 C; absorption chiller",
            "heat_pump+electric": "heat pump for heating; electric chillers only",
        },
        "tools": (
            "compare_designs screens doublet counts, depths and layouts; simulate_doublet checks one "
            "doublet in GEMINI; compare_return_temperatures and check_unplanned_outage test the chosen design."
        ),
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
    result = _cached("simulate_doublet", arguments, lambda: run_plant(**arguments))
    return {**result, **_doublet_next_step(arguments, result)}


def _doublet_next_step(arguments, result):
    """Return whether a doublet run passed and, if not, the one input to change next."""
    failed = result["checks_failed"]
    if not failed:
        return {"passed": True, "next_step": "All checks passed. This operating point is valid."}
    if "flow_within_50_300" in failed and result["flow_m3h"] > 300.0:
        design = 5 * int(arguments["design_flow_m3h"] * 295.0 / result["flow_m3h"] // 5)
        return {
            "passed": False,
            "next_step": (
                f"GEMINI flow {result['flow_m3h']} m3/h is above the 300 m3/h limit. Run again with "
                f"design_flow_m3h={design}."
            ),
        }
    if "brine_cooling_max_40" in failed:
        secondary = 10 * int(arguments["secondary_flow_m3h"] * 38.0 / result["brine_cooling_c"] // 10)
        return {
            "passed": False,
            "next_step": (
                f"Brine cooling {result['brine_cooling_c']} C is above the 40 C limit. Run again with "
                f"secondary_flow_m3h={secondary}."
            ),
        }
    return {"passed": False, "next_step": f"Failed checks: {', '.join(failed)}. Change one input and run again."}


def simulate_year(
    doublets,
    depth_m,
    separate_outages=True,
    return_c=50.0,
    heating_peak_mw=None,
    cooling_peak_mw=None,
    layout=DEFAULT_LAYOUT,
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
    errors.append(_layout_error(layout))
    errors = [error for error in errors if error]
    if errors:
        return {"error": " ".join(errors), "nothing_was_run": True}
    arguments = {
        "doublets": int(doublets),
        "depth_m": float(depth_m),
        "layout": layout,
        "separate_outages": bool(separate_outages),
        "return_c": float(return_c),
        "heating_peak_mw": None if heating_peak_mw is None else float(heating_peak_mw),
        "cooling_peak_mw": None if cooling_peak_mw is None else float(cooling_peak_mw),
    }

    def compute():
        dates, heating, cooling, first, second = _demand(heating_peak_mw, cooling_peak_mw)
        top_up, cooling_option = layout.split("+")
        design = EnergyDesign(
            int(doublets),
            float(depth_m),
            staggered=bool(separate_outages),
            return_c=float(return_c),
            heating_top_up=top_up,
            cooling=cooling_option,
        )
        _, summary = run_design(design, dates, heating, cooling, first, second)
        rounded = {
            key: (round(value, 2) if isinstance(value, float) else value)
            for key, value in summary.items()
            if key not in ("checks", "min_intake_bar")
        }
        rounded["layout"] = layout
        rounded["checks_failed"] = [name for name, passed in summary["checks"].items() if not passed]
        rounded["heating_peak_mw_used"] = round(float(heating.max()), 2)
        rounded["cooling_peak_mw_used"] = round(float(cooling.max()), 2)
        rounded["units"] = "energy in GWh per year, power in MW, CO2 in kt per year"
        return rounded

    return _cached("simulate_year", arguments, compute)


def estimate_cost(
    doublets,
    depth_m,
    separate_outages=True,
    return_c=50.0,
    heating_peak_mw=None,
    cooling_peak_mw=None,
    layout=DEFAULT_LAYOUT,
):
    """Return capital, yearly and levelised cost for a design, simulating it if needed."""
    year = simulate_year(
        doublets, depth_m, separate_outages, return_c, heating_peak_mw, cooling_peak_mw, layout
    )
    if "error" in year:
        return year
    return {
        "doublets": int(doublets),
        "depth_m": float(depth_m),
        "layout": layout,
        "return_c": float(return_c),
        "heating_peak_mw_used": year["heating_peak_mw_used"],
        **design_costs(int(doublets), float(depth_m), year),
    }


MAX_COMPARED_DESIGNS = 36
BRACKET_STEP_M = 500.0
MAX_BRACKET_STEPS = 3


def _design_row(count, depth, layout, scenario):
    """Simulate and cost one design and return its short comparison row."""
    cost = estimate_cost(count, depth, layout=layout, **scenario)
    if "error" in cost:
        return {"doublets": count, "depth_m": depth, "layout": layout, "error": cost["error"]}
    year = simulate_year(count, depth, layout=layout, **scenario)
    row = {
        "doublets": int(count),
        "depth_m": float(depth),
        "layout": layout,
        "levelised_cost_eur_per_mwh": cost["levelised_cost_eur_per_mwh"],
        "bought_energy_share_pct": cost["bought_energy_share_pct"],
        "meets_geothermal_first": cost["meets_geothermal_first"],
        "co2_kt": year["co2_kt"],
        "checks_failed": year["checks_failed"],
    }
    if layout.startswith("heat_pump") and year["heat_pump_gwh"] == 0:
        row["same_as"] = layout.replace("heat_pump", "boiler")
    return row


def _ranked(rows):
    """Return eligible and ineligible valid rows, each sorted by levelised cost."""
    valid = [row for row in rows if "error" not in row and not row["checks_failed"] and "same_as" not in row]
    by_cost = lambda row: row["levelised_cost_eur_per_mwh"]  # noqa: E731
    eligible = sorted((row for row in valid if row["meets_geothermal_first"]), key=by_cost)
    ineligible = sorted((row for row in valid if not row["meets_geothermal_first"]), key=by_cost)
    return eligible, ineligible


def _trade_off(eligible, ineligible):
    """Return one sentence comparing the best eligible design with its two alternatives."""
    if not eligible:
        return "No design meets the geothermal-first rule."
    best = eligible[0]
    name = lambda row: f"{row['doublets']} x {row['depth_m']:.0f} m with {row['layout']}"  # noqa: E731
    parts = [
        f"{name(best)} is the lowest-cost eligible design at {best['levelised_cost_eur_per_mwh']} EUR/MWh "
        f"and {best['co2_kt']} kt CO2, buying {best['bought_energy_share_pct']}% of its energy."
    ]
    if ineligible:
        cheap = ineligible[0]
        extra = round(best["levelised_cost_eur_per_mwh"] - cheap["levelised_cost_eur_per_mwh"], 1)
        saved = round(cheap["co2_kt"] - best["co2_kt"], 2)
        parts.append(
            f"{name(cheap)} is cheaper at {cheap['levelised_cost_eur_per_mwh']} EUR/MWh but buys "
            f"{cheap['bought_energy_share_pct']}% of its energy and emits {cheap['co2_kt']} kt CO2, so the "
            f"chosen design costs {extra} EUR/MWh more and saves {saved} kt CO2 per year."
        )
    if len(eligible) > 1:
        runner = eligible[1]
        parts.append(
            f"The next eligible design, {name(runner)}, costs {runner['levelised_cost_eur_per_mwh']} EUR/MWh "
            f"and emits {runner['co2_kt']} kt CO2."
        )
    by_cost = lambda row: row["levelised_cost_eur_per_mwh"]  # noqa: E731
    for layout in LAYOUTS:
        if layout == best["layout"]:
            continue
        group = [row for row in eligible if row["layout"] == layout] or [
            row for row in ineligible if row["layout"] == layout
        ]
        if group:
            row = min(group, key=by_cost)
            status = "eligible" if row["meets_geothermal_first"] else f"not eligible, buys {row['bought_energy_share_pct']}%"
            parts.append(
                f"Best with {layout}: {row['doublets']} x {row['depth_m']:.0f} m at "
                f"{row['levelised_cost_eur_per_mwh']} EUR/MWh and {row['co2_kt']} kt CO2 ({status})."
            )
    return " ".join(parts)


def compare_designs(
    doublet_options, depths_m, layouts=None, return_c=50.0, heating_peak_mw=None, cooling_peak_mw=None
):
    """Simulate and cost every combination, then rank them with the selection rule.

    ``layouts`` defaults to all four layouts. If the best eligible design sits at the
    shallowest or deepest depth tried, the next depth beyond it is added, so the best
    depth is always bracketed on both sides.
    """
    layouts = list(layouts or LAYOUTS)
    unknown = [error for error in map(_layout_error, layouts) if error]
    if unknown:
        return {"error": " ".join(unknown), "nothing_was_run": True}
    combinations = [
        (count, depth, layout) for count in doublet_options for depth in depths_m for layout in layouts
    ]
    if len(combinations) > MAX_COMPARED_DESIGNS:
        return {"error": f"{len(combinations)} designs requested; the limit is {MAX_COMPARED_DESIGNS}.", "nothing_was_run": True}
    scenario = {"return_c": return_c, "heating_peak_mw": heating_peak_mw, "cooling_peak_mw": cooling_peak_mw}
    rows = [_design_row(count, depth, layout, scenario) for count, depth, layout in combinations]
    step = min((b - a for a, b in zip(sorted(depths_m), sorted(depths_m)[1:])), default=BRACKET_STEP_M)
    added = []
    for _ in range(MAX_BRACKET_STEPS):
        eligible, _ = _ranked(rows)
        if not eligible:
            break
        best = eligible[0]
        tried = sorted(
            row["depth_m"]
            for row in rows
            if row["doublets"] == best["doublets"] and row["layout"] == best["layout"]
        )
        if best["depth_m"] == tried[-1] and best["depth_m"] + step <= DEPTH_RANGE_M[1]:
            depth = best["depth_m"] + step
        elif best["depth_m"] == tried[0] and best["depth_m"] - step >= DEPTH_RANGE_M[0]:
            depth = best["depth_m"] - step
        else:
            break
        rows.append(_design_row(best["doublets"], depth, best["layout"], scenario))
        added.append({"doublets": best["doublets"], "depth_m": depth, "layout": best["layout"]})
    eligible, ineligible = _ranked(rows)
    alternative = None
    if len(eligible) > 1:
        runner = eligible[1]
        alternative = {
            "alternative_doublets": runner["doublets"],
            "alternative_depth_m": runner["depth_m"],
            "alternative_layout": runner["layout"],
        }
    return {
        "trade_off": _trade_off(eligible, ineligible),
        "alternative_for_verify_design": alternative,
        "designs": rows,
        "lowest_cost_eligible": eligible[0] if eligible else None,
        "next_lowest_cost_eligible": eligible[1] if len(eligible) > 1 else None,
        "lowest_cost_ineligible": ineligible[0] if ineligible else None,
        "depths_added_to_bracket_best": added,
        "same_as": "a heat_pump row marked same_as never runs its heat pump, so it equals that boiler layout and is not ranked",
        "rule": (
            "eligible means energy bought to make heat or cooling (backup gas, electricity for heat "
            "pumps and electric chillers) is at most 10% of energy delivered"
        ),
    }


def compare_return_temperatures(
    doublets, depth_m, return_options, heating_peak_mw=None, cooling_peak_mw=None, layout=DEFAULT_LAYOUT
):
    """Simulate and cost one design at several heating return temperatures."""
    options = sorted({float(value) for value in return_options})
    if not 2 <= len(options) <= RETURN_OPTIONS_MAX:
        return {"error": f"Give 2-{RETURN_OPTIONS_MAX} different return temperatures.", "nothing_was_run": True}
    rows = []
    for return_c in options:
        scenario = {
            "return_c": return_c,
            "heating_peak_mw": heating_peak_mw,
            "cooling_peak_mw": cooling_peak_mw,
            "layout": layout,
        }
        cost = estimate_cost(doublets, depth_m, **scenario)
        if "error" in cost:
            return cost
        year = simulate_year(doublets, depth_m, **scenario)
        rows.append(
            {
                "return_c": return_c,
                "levelised_cost_eur_per_mwh": cost["levelised_cost_eur_per_mwh"],
                "bought_energy_share_pct": cost["bought_energy_share_pct"],
                "meets_geothermal_first": cost["meets_geothermal_first"],
                "co2_kt": year["co2_kt"],
                "backup_peak_mw": year["backup_peak_mw"],
                "checks_failed": year["checks_failed"],
            }
        )
    valid = [row for row in rows if not row["checks_failed"]]
    if not valid:
        return {"doublets": int(doublets), "depth_m": float(depth_m), "heating_peak_mw_used": year["heating_peak_mw_used"], "options": rows, "best_return_c": None}
    lowest = min(row["levelised_cost_eur_per_mwh"] for row in valid)
    same_cost = [row["return_c"] for row in valid if row["levelised_cost_eur_per_mwh"] - lowest <= SAME_COST_EUR_PER_MWH]
    return {
        "doublets": int(doublets),
        "depth_m": float(depth_m),
        "layout": layout,
        "heating_peak_mw_used": year["heating_peak_mw_used"],
        "options": rows,
        "lowest_cost_eur_per_mwh": lowest,
        "returns_with_lowest_cost_c": same_cost,
        "best_return_c": max(same_cost),
        "why": (
            "Below a certain return temperature the cost stops falling, because the 40 C brine "
            "cooling limit, not the return temperature, caps the heat taken from the brine. "
            "best_return_c is the highest return with the lowest cost, which keeps the most "
            "margin for the network."
        ),
    }


def check_unplanned_outage(
    doublets,
    depth_m,
    return_c=50.0,
    failure_days=7,
    heating_peak_mw=None,
    cooling_peak_mw=None,
    layout=DEFAULT_LAYOUT,
):
    """Fail doublet 1 over the heating peak and return the backup needed and its cost."""
    errors = [
        _out_of_range("failure_days", failure_days, *FAILURE_DAYS_RANGE, "days"),
        _out_of_range("depth_m", depth_m, *DEPTH_RANGE_M, "m"),
        _out_of_range("return_c", return_c, *RETURN_RANGE_C, "C"),
    ]
    if int(doublets) != doublets or not 1 <= doublets <= 3:
        errors.append(f"doublets={doublets} is not allowed; the challenge allows 1-3.")
    errors.append(_layout_error(layout))
    errors = [error for error in errors if error]
    if errors:
        return {"error": " ".join(errors), "nothing_was_run": True}
    scenario = {
        "return_c": return_c,
        "heating_peak_mw": heating_peak_mw,
        "cooling_peak_mw": cooling_peak_mw,
        "layout": layout,
    }
    planned = estimate_cost(doublets, depth_m, **scenario)
    if "error" in planned:
        return planned
    planned_year = simulate_year(doublets, depth_m, **scenario)
    arguments = {
        "doublets": int(doublets),
        "depth_m": float(depth_m),
        "layout": layout,
        "return_c": float(return_c),
        "failure_days": int(failure_days),
        "heating_peak_mw": None if heating_peak_mw is None else float(heating_peak_mw),
        "cooling_peak_mw": None if cooling_peak_mw is None else float(cooling_peak_mw),
    }

    def compute():
        dates, heating, cooling, first, second = _demand(heating_peak_mw, cooling_peak_mw)
        start = max(0, int(np.argmax(heating)) - int(failure_days) // 2)
        outages = unplanned_outages(int(doublets), start, int(failure_days), first, second)
        top_up, cooling_option = layout.split("+")
        design = EnergyDesign(
            int(doublets), float(depth_m), return_c=float(return_c), heating_top_up=top_up, cooling=cooling_option
        )
        _, summary = run_design(design, dates, heating, cooling, first, second, outages=outages)
        cost = design_costs(int(doublets), float(depth_m), summary)
        return {
            "doublets": int(doublets),
            "depth_m": float(depth_m),
            "layout": layout,
            "failure": f"doublet 1 out for {int(failure_days)} days from {dates[start]}, over the heating peak",
            "backup_peak_mw_planned_only": planned_year["backup_peak_mw"],
            "backup_peak_mw_with_failure": round(float(summary["backup_peak_mw"]), 2),
            "electric_cooling_peak_mw_with_failure": round(float(summary["electric_cooling_peak_mw"]), 2),
            "levelised_cost_planned_only": planned["levelised_cost_eur_per_mwh"],
            "levelised_cost_with_backup_for_failure": cost["levelised_cost_eur_per_mwh"],
            "checks_failed": [name for name, passed in summary["checks"].items() if not passed],
            "meaning": (
                "backup_peak_mw_with_failure is the boiler size needed to still meet demand on "
                "every day if this failure happens; the cost includes that larger boiler."
            ),
        }

    return _cached("check_unplanned_outage", arguments, compute)


def assess_uncertainty(
    doublets,
    depth_m,
    layout=DEFAULT_LAYOUT,
    alternative_doublets=None,
    alternative_depth_m=None,
    alternative_layout=None,
    heating_peak_mw=None,
    cooling_peak_mw=None,
):
    """Sample subsurface, demand and grid uncertainty for a design, against an optional alternative."""
    errors = [_out_of_range("depth_m", depth_m, *DEPTH_RANGE_M, "m"), _layout_error(layout)]
    if int(doublets) != doublets or not 1 <= doublets <= 3:
        errors.append(f"doublets={doublets} is not allowed; the challenge allows 1-3.")
    alternative = None
    if alternative_doublets is not None or alternative_depth_m is not None or alternative_layout is not None:
        alternative = (
            int(alternative_doublets if alternative_doublets is not None else doublets),
            float(alternative_depth_m if alternative_depth_m is not None else depth_m),
            alternative_layout or layout,
        )
        errors += [_out_of_range("alternative_depth_m", alternative[1], *DEPTH_RANGE_M, "m"), _layout_error(alternative[2])]
        if not 1 <= alternative[0] <= 3:
            errors.append(f"alternative_doublets={alternative[0]} is not allowed; the challenge allows 1-3.")
    design = (int(doublets), float(depth_m), layout)
    if alternative == design:
        errors.append(
            "The alternative is the same design. Use next_lowest_cost_eligible from compare_designs "
            "as the alternative."
        )
    errors = [error for error in errors if error]
    if errors:
        return {"error": " ".join(errors), "nothing_was_run": True}
    arguments = {
        "design": list(design),
        "alternative": None if alternative is None else list(alternative),
        "heating_peak_mw": heating_peak_mw,
        "cooling_peak_mw": cooling_peak_mw,
    }

    def compute():
        result = assess(design, alternative, _demand(heating_peak_mw, cooling_peak_mw))
        return {"doublets": design[0], "depth_m": design[1], "layout": design[2], **result}

    return _cached("assess_uncertainty", arguments, compute)


def validate_year_in_gemini(doublets, depth_m, layout, heating_peak_mw=None, cooling_peak_mw=None):
    """Run every operating day of a design through a generated GEMINI plant file and check it."""
    errors = [_out_of_range("depth_m", depth_m, *DEPTH_RANGE_M, "m"), _layout_error(layout)]
    if int(doublets) != doublets or not 1 <= doublets <= 3:
        errors.append(f"doublets={doublets} is not allowed; the challenge allows 1-3.")
    errors = [error for error in errors if error]
    if errors:
        return {"error": " ".join(errors), "nothing_was_run": True}
    if not layout.endswith("+electric"):
        return {
            "error": "The absorption chiller is not a GEMINI component, so only layouts with electric "
            "chillers can be run through GEMINI plant files for the whole year.",
            "nothing_was_run": True,
        }
    arguments = {
        "doublets": int(doublets),
        "depth_m": float(depth_m),
        "layout": layout,
        "heating_peak_mw": heating_peak_mw,
        "cooling_peak_mw": cooling_peak_mw,
    }

    def compute():
        top_up, cooling_option = layout.split("+")
        design = EnergyDesign(int(doublets), float(depth_m), heating_top_up=top_up, cooling=cooling_option)
        days, summary = run_year(design, *_demand(heating_peak_mw, cooling_peak_mw))
        return {**summary, **save(days, summary, design)}

    return _cached("validate_year_in_gemini", arguments, compute)


RETURN_OPTIONS_C = [40.0, 50.0, 60.0]


def verify_design(
    doublets,
    depth_m,
    layout,
    alternative_doublets=None,
    alternative_depth_m=None,
    alternative_layout=None,
    heating_peak_mw=None,
    cooling_peak_mw=None,
):
    """Run the four checks on a chosen design in one call and return a short combined result.

    Return temperature comparison, unplanned failure over the peak, uncertainty against
    the alternative, and the full year in GEMINI plant files (electric chillers only).
    """
    scenario = {"heating_peak_mw": heating_peak_mw, "cooling_peak_mw": cooling_peak_mw}
    returns = compare_return_temperatures(doublets, depth_m, RETURN_OPTIONS_C, layout=layout, **scenario)
    if "error" in returns:
        return returns
    outage = check_unplanned_outage(doublets, depth_m, layout=layout, **scenario)
    uncertainty = assess_uncertainty(
        doublets, depth_m, layout, alternative_doublets, alternative_depth_m, alternative_layout, **scenario
    )
    if "error" in uncertainty:
        return uncertainty
    keep = lambda result, keys: {key: result[key] for key in keys if key in result}  # noqa: E731
    combined = {
        "doublets": int(doublets),
        "depth_m": float(depth_m),
        "layout": layout,
        "return_temperature": keep(returns, ["best_return_c", "returns_with_lowest_cost_c", "lowest_cost_eur_per_mwh", "why"]),
        "unplanned_failure": keep(
            outage,
            ["failure", "backup_peak_mw_planned_only", "backup_peak_mw_with_failure",
             "levelised_cost_planned_only", "levelised_cost_with_backup_for_failure", "checks_failed"],
        ),
        "uncertainty": keep(
            uncertainty,
            ["levelised_cost_eur_per_mwh", "co2_kt", "meets_geothermal_first_pct", "all_checks_pass_pct",
             "cost_driver_rank_correlation", "versus_alternative"],
        ),
    }
    if layout.endswith("+electric"):
        year = validate_year_in_gemini(doublets, depth_m, layout, **scenario)
        combined["gemini_year"] = keep(
            year,
            ["gemini_days_run", "days_failing_gemini_checks", "worst_brine_cooling_c",
             "max_flow_difference_pct", "max_heat_difference_pct", "daily_results", "peak_day_plant"],
        )
    else:
        combined["gemini_year"] = "not run: the absorption chiller branch is not in the GEMINI plant file"
    return combined


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
    "compare_return_temperatures": compare_return_temperatures,
    "check_unplanned_outage": check_unplanned_outage,
    "assess_uncertainty": assess_uncertainty,
    "validate_year_in_gemini": validate_year_in_gemini,
    "verify_design": verify_design,
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
                    "layout": {"type": "string", "enum": LAYOUTS, "description": "Heating top-up and cooling layout (default boiler+absorption)"},
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
                    "layout": {"type": "string", "enum": LAYOUTS, "description": "Heating top-up and cooling layout (default boiler+absorption)"},
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
                "Simulate and cost every combination of doublet counts, depths and layouts (at most "
                "36), then return each design, the lowest-cost eligible and ineligible designs under "
                "the geothermal-first rule, and a trade_off sentence. Use this to screen options."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "doublet_options": {"type": "array", "items": {"type": "integer"}, "description": "Doublet counts to compare, e.g. [1, 2, 3]"},
                    "depths_m": {"type": "array", "items": {"type": "number"}, "description": "Depths to compare in m, e.g. [2000, 2500, 3000]"},
                    "layouts": {"type": "array", "items": {"type": "string", "enum": LAYOUTS}, "description": "Layouts to compare; leave out to compare all four"},
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
            "name": "compare_return_temperatures",
            "description": (
                "Simulate and cost one design at 2-6 district heating return temperatures. Returns "
                "each option and best_return_c, the highest return with the lowest cost."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "layout": {"type": "string", "enum": LAYOUTS, "description": "Heating top-up and cooling layout (default boiler+absorption)"},
                    "doublets": {"type": "integer", "description": "Number of doublets"},
                    "depth_m": {"type": "number", "description": "Reservoir depth in m"},
                    "return_options": {"type": "array", "items": {"type": "number"}, "description": "Return temperatures in C, e.g. [40, 50, 60]"},
                    "heating_peak_mw": {"type": "number", "description": "Only for a demand scenario: scale the heating profile to this peak in MW"},
                    "cooling_peak_mw": {"type": "number", "description": "Only for a demand scenario: scale the cooling profile to this peak in MW"},
                },
                "required": ["doublets", "depth_m", "return_options"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_unplanned_outage",
            "description": (
                "Test a design against an unplanned failure: doublet 1 is out for failure_days over "
                "the coldest days. Returns the backup boiler size needed to still meet demand and "
                "the levelised cost with that backup."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "layout": {"type": "string", "enum": LAYOUTS, "description": "Heating top-up and cooling layout (default boiler+absorption)"},
                    "doublets": {"type": "integer", "description": "Number of doublets"},
                    "depth_m": {"type": "number", "description": "Reservoir depth in m"},
                    "return_c": {"type": "number", "description": "District heating return temperature in C (default 50)"},
                    "failure_days": {"type": "integer", "description": "Length of the failure in days (default 7)"},
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
            "name": "assess_uncertainty",
            "description": (
                "Sample uncertain geothermal gradient (27-33 C/km), permeability (100-300 mD), demand "
                "(90-110%) and grid CO2 factor (0.15-0.45 kg/kWh) for a design, and optionally compare "
                "it with an alternative design under the same samples. Returns P10/P50/P90 cost and CO2, "
                "how often the design meets the geothermal-first rule, and the main cost drivers."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "doublets": {"type": "integer", "description": "Number of doublets"},
                    "depth_m": {"type": "number", "description": "Reservoir depth in m"},
                    "layout": {"type": "string", "enum": LAYOUTS, "description": "Layout of the design"},
                    "alternative_doublets": {"type": "integer", "description": "Alternative design: number of doublets"},
                    "alternative_depth_m": {"type": "number", "description": "Alternative design: depth in m"},
                    "alternative_layout": {"type": "string", "enum": LAYOUTS, "description": "Alternative design: layout"},
                    "heating_peak_mw": {"type": "number", "description": "Only for a demand scenario: scale the heating profile to this peak in MW"},
                    "cooling_peak_mw": {"type": "number", "description": "Only for a demand scenario: scale the cooling profile to this peak in MW"},
                },
                "required": ["doublets", "depth_m", "layout"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "validate_year_in_gemini",
            "description": (
                "For every day a design runs, generate a one-doublet GEMINI plant JSON at that day's "
                "flow and heat, solve it with GEMINI's nodal solver and check the limits. Returns days "
                "run, days failing checks, worst brine cooling, and differences from the yearly model."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "doublets": {"type": "integer", "description": "Number of doublets"},
                    "depth_m": {"type": "number", "description": "Reservoir depth in m"},
                    "layout": {"type": "string", "enum": LAYOUTS, "description": "Layout of the design; must use electric chillers"},
                    "heating_peak_mw": {"type": "number", "description": "Only for a demand scenario: scale the heating profile to this peak in MW"},
                    "cooling_peak_mw": {"type": "number", "description": "Only for a demand scenario: scale the cooling profile to this peak in MW"},
                },
                "required": ["doublets", "depth_m", "layout"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "verify_design",
            "description": (
                "Check a chosen design in one call: compare return temperatures, test an unplanned "
                "failure over the peak, sample subsurface, demand and grid uncertainty against the "
                "alternative, and run every operating day through GEMINI plant files."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "doublets": {"type": "integer", "description": "Number of doublets"},
                    "depth_m": {"type": "number", "description": "Reservoir depth in m"},
                    "layout": {"type": "string", "enum": LAYOUTS, "description": "Layout of the design"},
                    "alternative_doublets": {"type": "integer", "description": "From alternative_for_verify_design"},
                    "alternative_depth_m": {"type": "number", "description": "From alternative_for_verify_design"},
                    "alternative_layout": {"type": "string", "enum": LAYOUTS, "description": "From alternative_for_verify_design"},
                    "heating_peak_mw": {"type": "number", "description": "Only for a demand scenario: scale the heating profile to this peak in MW"},
                    "cooling_peak_mw": {"type": "number", "description": "Only for a demand scenario: scale the cooling profile to this peak in MW"},
                },
                "required": ["doublets", "depth_m", "layout"],
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
