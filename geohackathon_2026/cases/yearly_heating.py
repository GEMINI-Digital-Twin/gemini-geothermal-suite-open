"""Run heating-only designs through the 365 daily demand values.

Uses GEMINI's well, heat exchanger and boiler models. Cooling is not included.
The geothermal source is limited to 330 days per doublet, and backup boilers
cover whatever remains, so backup capacity is a result of each run.

Each day, the doublet count and flow are chosen to minimize backup fuel plus
pump electricity, with electricity weighted by PRIMARY_ENERGY_FACTOR.

Run from the project folder:
    PYTHONPATH=../src python cases/yearly_heating.py
"""

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from gemini_model.boiler.boiler import Boiler
from gemini_model.heat_exchanger.heat_exchanger import HeatExchanger
from gemini_simulator.well_flow import _split_trajectory_at_depth
from pipe_size_study import RHO, CP, PUMP_EFFICIENCY, build_well, walk

ROOT = Path(__file__).parent.parent
HEATING_FILE = ROOT / "GEMINI_Heating_Demand_Daily_2027.csv"
COOLING_FILE = ROOT / "GEMINI_Cooling_Demand_Daily_2027.csv"
RESULTS_DIR = ROOT / "results"

# Challenge values
SUPPLY_C = 100.0
MIN_FLOW_M3H = 50.0
MAX_FLOW_M3H = 300.0
MAX_COOLING_C = 40.0
MAX_RUN_DAYS = 330
OUTAGE_DAYS = 35
SURFACE_C = 12.0
GRADIENT_C_PER_M = 0.030
G = 9.81

# Assumptions, not challenge values
PIPE_ID_M = 0.20
ROUGHNESS_M = 0.0001
INDEX_M3H_PER_BAR = 13.4
ESP_DEPTH_M = 650.0
WELLHEAD_PRESSURE_BAR = 3.0
INJECTOR_INLET_BAR = 1.45
WELL_LOSS_C = 1.0
HEX_UA_W_PER_K = 2.0e6
PRIMARY_ENERGY_FACTOR = 2.5
ASSUMED_COOLING_COP = 0.7  # only used to place outages in low-demand periods

# Surface temperature drops kept from GEMINI's example
SEPARATOR_DROP_C = 1.0
FILTER_A_DROP_C = 1.0
FILTER_B_DROP_C = 1.0

# Produced gas, from the challenge composition
GAS_NM3_PER_M3 = 0.8
GAS_DENSITY = 0.965
GAS_CALORIC_J_PER_KG = 29.66e6
GAS_EMISSION_KG_PER_GJ = 68.6
GAS_BOILER_EFFICIENCY = 0.8

# Backup natural gas boiler, assumed
BACKUP_CALORIC_J_PER_KG = 50.0e6
BACKUP_EMISSION_KG_PER_GJ = 56.6
BACKUP_BOILER_EFFICIENCY = 0.9

FLOW_GRID = np.arange(MIN_FLOW_M3H, MAX_FLOW_M3H + 0.1, 5.0)
C_VOL = RHO * CP


@dataclass(frozen=True)
class Design:
    """One heating design to evaluate."""

    doublets: int
    depth_m: float
    return_c: float
    staggered: bool = True

    @property
    def name(self):
        """Return a short design label."""
        outage = "staggered" if self.staggered else "together"
        return f"{self.doublets}x{self.depth_m:.0f}m_R{self.return_c:.0f}_{outage}"


def read_demand(path):
    """Return dates and demand values from a challenge CSV file."""
    with open(path, encoding="utf-8") as file:
        rows = list(csv.reader(file))[1:]
    return [row[0] for row in rows], np.array([float(row[1]) for row in rows])


def pump_power_mw(design, flow_m3h, index_m3h_per_bar=INDEX_M3H_PER_BAR):
    """Return production and injection pump power and pump intake pressure."""
    flow_m3s = flow_m3h / 3600.0
    reservoir_bar = RHO * G * design.depth_m / 1e5
    segment = {"angle": 90.0, "depth": design.depth_m, "diameter": PIPE_ID_M}
    top, bottom = _split_trajectory_at_depth([segment], ESP_DEPTH_M)

    bottomhole = reservoir_bar - flow_m3h / index_m3h_per_bar
    intake = walk(build_well(bottom, ROUGHNESS_M), bottomhole, flow_m3s, "up")
    discharge = walk(build_well(top, ROUGHNESS_M), WELLHEAD_PRESSURE_BAR, flow_m3s, "down")
    esp = flow_m3s * (discharge - intake) * 1e5 / PUMP_EFFICIENCY / 1e6

    required = reservoir_bar + flow_m3h / index_m3h_per_bar
    column = walk(build_well([segment], ROUGHNESS_M), 0.0, -flow_m3s, "down")
    boost = max(0.0, required - column - INJECTOR_INLET_BAR)
    injector = flow_m3s * boost * 1e5 / PUMP_EFFICIENCY / 1e6
    return esp, injector, intake


def exchange_heat(flow_m3h, secondary_m3s, t_primary_in, t_return, heat_needed_w, t_primary_min):
    """Return usable heat (W) and brine outlet temperature for one doublet.

    GEMINI's heat exchanger sets the maximum duty. Duty is then limited to the
    heat needed (brine bypass) and to the brine cooling cap.
    """
    exchanger = HeatExchanger()
    exchanger.update_parameters(
        {
            "flow_resistance": 0,
            "flow_configuration": "counter",
            "heat_transfer_coefficient": HEX_UA_W_PER_K,
            "fluid_density": RHO,
            "specific_heat": CP,
        }
    )
    flow_m3s = flow_m3h / 3600.0
    exchanger.calculate_output(
        {
            "pressure_in": 3.0,
            "primary_flow_rate": flow_m3s,
            "secondary_flow_rate": secondary_m3s,
            "primary_temperature_in": t_primary_in,
            "secondary_temperature_in": t_return,
        }
    )
    duty = exchanger.get_output()["heat_duty"]
    capacity = flow_m3s * C_VOL
    heat = min(duty, heat_needed_w, max(0.0, capacity * (t_primary_in - t_primary_min)))
    return heat, t_primary_in - heat / capacity


def boiler_outlet(heat_w, flow_m3s, t_in, caloric, efficiency, emission_factor):
    """Run GEMINI's boiler for a heat duty, returning outlet temperature and CO2."""
    boiler = Boiler()
    boiler.update_parameters(
        {
            "caloric_value": caloric,
            "efficiency_factor": efficiency,
            "gas_emission_factor": emission_factor,
            "fluid_density": RHO,
            "specific_heat": CP,
        }
    )
    boiler.calculate_output(
        {
            "temperature_in": t_in,
            "water_flow_rate": flow_m3s,
            "gas_flow_rate": heat_w / (efficiency * caloric),
        }
    )
    output = boiler.get_output()
    return output["temperature_out"], output["emission"]


def lowest_demand_windows(load):
    """Return two non-overlapping 35-day windows with the lowest load."""
    sums = np.convolve(load, np.ones(OUTAGE_DAYS), "valid")
    first = int(np.argmin(sums))
    allowed = [
        day
        for day in range(len(sums))
        if day + OUTAGE_DAYS <= first or day >= first + OUTAGE_DAYS
    ]
    second = min(allowed, key=lambda day: sums[day])
    return first, second


def build_outages(design, first, second):
    """Return a boolean outage array for each doublet."""
    outages = np.zeros((design.doublets, 365), dtype=bool)
    for index in range(design.doublets):
        start = second if design.staggered and index % 2 == 1 else first
        outages[index, start : start + OUTAGE_DAYS] = True
    return outages


def best_operation(design, demand_w, available, curves, t_wellhead):
    """Return the best doublet count and flow for one day."""
    t_primary_in = t_wellhead - SEPARATOR_DROP_C - FILTER_A_DROP_C
    t_primary_min = t_wellhead - MAX_COOLING_C + FILTER_B_DROP_C
    secondary_m3s = demand_w / (C_VOL * (SUPPLY_C - design.return_c))
    best = None
    for active in range(0, available + 1):
        flows = FLOW_GRID if active else [0.0]
        for flow in flows:
            heat_w, gas_w, t_out = 0.0, 0.0, None
            pump_mw = 0.0
            if active:
                need_each = demand_w / active
                heat_each, t_out = exchange_heat(
                    flow,
                    secondary_m3s / active,
                    t_primary_in,
                    design.return_c,
                    need_each,
                    t_primary_min,
                )
                heat_w = heat_each * active
                gas_kg_s = flow / 3600.0 * GAS_NM3_PER_M3 * GAS_DENSITY * active
                gas_w = gas_kg_s * GAS_CALORIC_J_PER_KG * GAS_BOILER_EFFICIENCY
                pump_mw = curves[flow][0] + curves[flow][1]
            produced_gas_w = min(gas_w, demand_w - heat_w)
            backup_w = max(0.0, demand_w - heat_w - produced_gas_w)
            pump_w = active * pump_mw * 1e6
            score = backup_w / BACKUP_BOILER_EFFICIENCY + PRIMARY_ENERGY_FACTOR * pump_w
            if best is None or score < best["score"] - 1e-6:
                best = {
                    "score": score,
                    "active": active,
                    "flow": flow,
                    "heat_w": heat_w,
                    "gas_available_w": gas_w,
                    "gas_w": produced_gas_w,
                    "backup_w": backup_w,
                    "pump_w": pump_w,
                    "t_primary_out": t_out,
                    "secondary_m3s": secondary_m3s,
                }
    return best


def run_design(design, dates, heating_mw, first, second):
    """Run one design through all 365 days, returning rows and a summary."""
    t_reservoir = SURFACE_C + GRADIENT_C_PER_M * design.depth_m
    t_wellhead = t_reservoir - WELL_LOSS_C
    curves = {float(flow): pump_power_mw(design, float(flow)) for flow in FLOW_GRID}
    outages = build_outages(design, first, second)
    run_days = np.zeros(design.doublets, dtype=int)
    rows = []
    for day, demand_mw in enumerate(heating_mw):
        demand_w = demand_mw * 1e6
        candidates = [
            index
            for index in np.argsort(run_days)
            if not outages[index, day] and run_days[index] < MAX_RUN_DAYS
        ]
        result = best_operation(design, demand_w, len(candidates), curves, t_wellhead)
        for index in candidates[: result["active"]]:
            run_days[index] += 1

        secondary = result["secondary_m3s"]
        t_after_hex = design.return_c + result["heat_w"] / (secondary * C_VOL)
        t_after_gas, gas_co2 = boiler_outlet(
            result["gas_w"],
            secondary,
            t_after_hex,
            GAS_CALORIC_J_PER_KG,
            GAS_BOILER_EFFICIENCY,
            GAS_EMISSION_KG_PER_GJ,
        )
        t_supply, backup_co2 = boiler_outlet(
            result["backup_w"],
            secondary,
            t_after_gas,
            BACKUP_CALORIC_J_PER_KG,
            BACKUP_BOILER_EFFICIENCY,
            BACKUP_EMISSION_KG_PER_GJ,
        )
        rows.append(
            {
                "date": dates[day],
                "demand_mw": demand_mw,
                "active_doublets": result["active"],
                "flow_m3h_each": result["flow"],
                "geothermal_mw": result["heat_w"] / 1e6,
                "produced_gas_heat_mw": result["gas_w"] / 1e6,
                "backup_heat_mw": result["backup_w"] / 1e6,
                "pump_mw": result["pump_w"] / 1e6,
                "t_after_hex_c": t_after_hex,
                "t_supply_c": t_supply,
                "brine_injected_c": (
                    None
                    if result["t_primary_out"] is None
                    else result["t_primary_out"] - FILTER_B_DROP_C
                ),
                "gas_unused_mw": (result["gas_available_w"] - result["gas_w"]) / 1e6,
                "co2_t": (gas_co2 + backup_co2) * 86.4,
            }
        )
    return rows, summarize(design, rows, run_days, t_wellhead, curves)


def summarize(design, rows, run_days, t_wellhead, curves):
    """Return annual results and rule checks for one design."""
    to_gwh = 24.0 / 1000.0
    total = lambda key: sum(row[key] for row in rows) * to_gwh  # noqa: E731
    active_rows = [row for row in rows if row["active_doublets"]]
    worst_cooling = max(
        (t_wellhead - row["brine_injected_c"] for row in active_rows), default=0.0
    )
    balance = max(
        abs(row["geothermal_mw"] + row["produced_gas_heat_mw"] + row["backup_heat_mw"]
            - row["demand_mw"])
        for row in rows
    )
    return {
        "design": design.name,
        "t_wellhead_c": t_wellhead,
        "geothermal_gwh": total("geothermal_mw"),
        "gas_gwh": total("produced_gas_heat_mw"),
        "backup_gwh": total("backup_heat_mw"),
        "geo_share_pct": total("geothermal_mw") / total("demand_mw") * 100,
        "backup_peak_mw": max(row["backup_heat_mw"] for row in rows),
        "pump_gwh": total("pump_mw"),
        "co2_kt": sum(row["co2_t"] for row in rows) / 1000.0,
        "gas_unused_gwh": total("gas_unused_mw"),
        "min_intake_bar": min(curve[2] for curve in curves.values()),
        "run_days": [int(value) for value in run_days],
        "checks": {
            "flow_50_300": all(
                MIN_FLOW_M3H <= row["flow_m3h_each"] <= MAX_FLOW_M3H for row in active_rows
            ),
            "cooling_max_40": worst_cooling <= MAX_COOLING_C + 1e-6,
            "run_days_max_330": all(value <= MAX_RUN_DAYS for value in run_days),
            "supply_100": all(abs(row["t_supply_c"] - SUPPLY_C) < 1e-6 for row in rows),
            "energy_balance": balance < 1e-6,
        },
        "worst_cooling_c": worst_cooling,
    }


def main():
    """Run the designs, save daily results and print a summary table."""
    dates, heating_mw = read_demand(HEATING_FILE)
    _, cooling_mw = read_demand(COOLING_FILE)
    first, second = lowest_demand_windows(heating_mw + cooling_mw / ASSUMED_COOLING_COP)
    print(f"Outage windows start: {dates[first]} and {dates[second]}")

    designs = [
        Design(doublets, depth, return_c)
        for doublets in (1, 2, 3)
        for depth in (2500.0, 3200.0)
        for return_c in (40.0, 50.0, 60.0)
    ]
    designs += [Design(2, 3200.0, 50.0, staggered=False), Design(2, 2500.0, 50.0, staggered=False)]

    RESULTS_DIR.mkdir(exist_ok=True)
    print(
        "design                      T_wh  geoGWh gasGWh bkpGWh geo%  bkpPeakMW pumpGWh "
        "CO2kt unusedGasGWh runDays checks worstCool"
    )
    for design in designs:
        rows, summary = run_design(design, dates, heating_mw, first, second)
        with open(RESULTS_DIR / f"heating_{design.name}.csv", "w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        failed = [name for name, passed in summary["checks"].items() if not passed]
        print(
            f"{summary['design']:27s} {summary['t_wellhead_c']:5.0f} "
            f"{summary['geothermal_gwh']:6.1f} {summary['gas_gwh']:6.1f} "
            f"{summary['backup_gwh']:6.1f} {summary['geo_share_pct']:4.0f} "
            f"{summary['backup_peak_mw']:9.1f} {summary['pump_gwh']:7.2f} "
            f"{summary['co2_kt']:5.1f} {summary['gas_unused_gwh']:12.1f} "
            f"{'/'.join(map(str, summary['run_days'])):11s} "
            f"{'PASS' if not failed else 'FAIL:' + ','.join(failed)} "
            f"{summary['worst_cooling_c']:6.1f}"
        )


if __name__ == "__main__":
    main()
