"""Run a design through all 365 days with GEMINI's own plant solver.

For each day the yearly model runs doublets, a one-doublet plant JSON is
generated for that day's operation and solved by GEMINI's nodal solver:
- the pump design point is adjusted until GEMINI's flow matches the day's flow,
  because GEMINI's well model uses water density and overshoots the flow;
- the district water flow through the heat exchanger is adjusted until
  GEMINI's heat duty matches the day's geothermal heat per doublet, from
  below, so a day the model runs at the 40 C limit is not pushed over it. The
  rest of the district water bypasses the exchanger.
GEMINI's results are then checked against the challenge limits and compared
with the yearly model. The absorption chiller is not a GEMINI component, so
only layouts with electric chillers send all brine through the plant.
"""

import csv
import json

from gemini_simulator.project_loader import build_project
from plant_json import MAX_COOLING_C, MAX_FLOW_M3H, MIN_FLOW_M3H, MIN_INTAKE_BAR, PLANTS_DIR, build_plant
from yearly_energy import run_design
from yearly_heating import Design, pump_power_mw

FLOW_TOLERANCE = 0.005
HEAT_TOLERANCE = 0.002
MAX_ITERATIONS = 40
SECONDARY_RANGE_M3H = (1.0, 3000.0)


def solve(plant):
    """Solve a plant dict with GEMINI and return the results needed for the checks."""
    solver = build_project(plant)
    solver.run()
    get = solver.get_output
    t_wellhead = get("producer_well", "temperature_out")
    return {
        "flow_m3h": get("producer_well", "flow_rate"),
        "injected_m3h": get("injector_well", "flow_rate_m3s") * 3600.0,
        "heat_w": get("heat_exchanger", "heat_duty"),
        "brine_cooling_c": t_wellhead - get("filter_b", "temperature_out"),
        "pump_w": get("producer_well", "esp_power_el") + get("injector_well", "power_el"),
        "intake_bar": get("producer_well", "esp_intake_pressure"),
    }


def match_flow(depth_m, return_c, target_m3h):
    """Return the pump design flow that makes GEMINI produce the target flow."""
    design = target_m3h
    for _ in range(MAX_ITERATIONS):
        actual = solve(build_plant(depth_m, design, return_c, target_m3h))["flow_m3h"]
        if abs(actual - target_m3h) <= FLOW_TOLERANCE * target_m3h:
            return design
        design *= target_m3h / actual
    return design


def match_heat(depth_m, design_flow, return_c, target_w):
    """Return the GEMINI result whose heat duty is just below the target, by bisection on district flow."""
    low, high = SECONDARY_RANGE_M3H
    best = None
    for _ in range(MAX_ITERATIONS):
        middle = (low + high) / 2.0
        result = {**solve(build_plant(depth_m, design_flow, return_c, middle)), "secondary_m3h": middle}
        if result["heat_w"] <= target_w:
            best = result
            if result["heat_w"] >= (1 - HEAT_TOLERANCE) * target_w:
                break
            low = middle
        else:
            high = middle
    return best


def run_year(design, dates, heating, cooling, first, second):
    """Run the yearly model, then every active day through GEMINI; return rows and a summary."""
    if design.cooling != "electric":
        return [], {"error": "Only layouts with electric chillers are run through GEMINI plant files."}
    rows, _ = run_design(design, dates, heating, cooling, first, second)
    well = Design(design.doublets, design.depth_m, design.return_c, design.staggered)
    design_flows, model_pumps = {}, {}
    days = []
    for row in rows:
        active = row["active_doublets"]
        if not active:
            continue
        flow = row["flow_m3h_each"]
        if flow not in design_flows:
            design_flows[flow] = match_flow(design.depth_m, design.return_c, flow)
            esp, injector, _ = pump_power_mw(well, flow)
            model_pumps[flow] = esp + injector
        heat_w = row["geothermal_heat_mw"] * 1e6 / active
        result = match_heat(design.depth_m, design_flows[flow], design.return_c, heat_w)
        checks = {
            "flow_within_50_300": MIN_FLOW_M3H <= result["flow_m3h"] <= MAX_FLOW_M3H * (1 + FLOW_TOLERANCE),
            "brine_cooling_max_40": result["brine_cooling_c"] <= MAX_COOLING_C,
            "equal_production_injection": abs(result["flow_m3h"] - result["injected_m3h"]) < 1e-6,
            "pump_intake_above_minimum": result["intake_bar"] is not None and result["intake_bar"] >= MIN_INTAKE_BAR,
        }
        days.append(
            {
                "date": row["date"],
                "active_doublets": active,
                "model_flow_m3h": flow,
                "gemini_flow_m3h": round(result["flow_m3h"], 2),
                "model_heat_mw": round(heat_w / 1e6, 4),
                "gemini_heat_mw": round(result["heat_w"] / 1e6, 4),
                "gemini_brine_cooling_c": round(result["brine_cooling_c"], 2),
                "model_pump_mw": round(model_pumps[flow], 4),
                "gemini_pump_mw": round(result["pump_w"] / 1e6, 4),
                "gemini_district_flow_m3h": round(result["secondary_m3h"], 1),
                "checks_failed": ";".join(name for name, passed in checks.items() if not passed),
            }
        )
    return days, summarize(days, design)


def summarize(days, design):
    """Return the yearly GEMINI validation summary."""
    failed = [day for day in days if day["checks_failed"]]
    heat_error = max(abs(day["gemini_heat_mw"] - day["model_heat_mw"]) / day["model_heat_mw"] for day in days)
    flow_error = max(abs(day["gemini_flow_m3h"] - day["model_flow_m3h"]) / day["model_flow_m3h"] for day in days)
    gemini_heat_gwh = sum(day["gemini_heat_mw"] * day["active_doublets"] for day in days) * 24 / 1000
    gemini_pump_gwh = sum(day["gemini_pump_mw"] * day["active_doublets"] for day in days) * 24 / 1000
    model_pump_gwh = sum(day["model_pump_mw"] * day["active_doublets"] for day in days) * 24 / 1000
    return {
        "doublets": design.doublets,
        "depth_m": design.depth_m,
        "layout": design.layout,
        "gemini_days_run": len(days),
        "gemini_doublet_days": sum(day["active_doublets"] for day in days),
        "days_failing_gemini_checks": len(failed),
        "failed_checks": sorted({name for day in failed for name in day["checks_failed"].split(";")}),
        "worst_brine_cooling_c": max(day["gemini_brine_cooling_c"] for day in days),
        "max_flow_difference_pct": round(100 * flow_error, 2),
        "max_heat_difference_pct": round(100 * heat_error, 2),
        "gemini_geothermal_heat_gwh": round(gemini_heat_gwh, 2),
        "gemini_pump_electricity_gwh": round(gemini_pump_gwh, 3),
        "model_pump_electricity_gwh": round(model_pump_gwh, 3),
    }


def save(days, summary, design):
    """Write the daily GEMINI results and the peak-day plant file; return their paths."""
    PLANTS_DIR.mkdir(parents=True, exist_ok=True)
    stem = f"year_{design.doublets}x{design.depth_m:.0f}m_{design.layout.replace('+', '_')}"
    daily = PLANTS_DIR / f"{stem}.csv"
    with open(daily, "w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=days[0].keys())
        writer.writeheader()
        writer.writerows(days)
    peak = max(days, key=lambda day: day["gemini_heat_mw"] * day["active_doublets"])
    design_flow = match_flow(design.depth_m, design.return_c, peak["model_flow_m3h"])
    plant = build_plant(design.depth_m, design_flow, design.return_c, peak["gemini_district_flow_m3h"])
    plant["_description"] += f" Peak day {peak['date']} of the year run."
    plant_file = PLANTS_DIR / f"{stem}_peak_day.json"
    plant_file.write_text(json.dumps(plant, indent=2), encoding="utf-8")
    return {"daily_results": str(daily.relative_to(PLANTS_DIR.parent.parent)), "peak_day_plant": str(plant_file.relative_to(PLANTS_DIR.parent.parent))}
