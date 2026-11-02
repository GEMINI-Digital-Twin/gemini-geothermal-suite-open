"""Run heating and cooling designs through the 365 daily demand values.

Extends yearly_heating.py with absorption cooling. Brine is split between the
heating exchanger and the chiller's hot-water exchanger, in parallel. An
electric chiller covers any cooling the absorption chiller does not, so its
capacity is a result of each run, as for the backup boiler.

Run from the project folder:
    PYTHONPATH=../src python cases/yearly_energy.py
"""

import csv
from dataclasses import dataclass

import numpy as np
from absorption_chiller import AbsorptionChiller
from yearly_heating import (
    BACKUP_BOILER_EFFICIENCY,
    BACKUP_CALORIC_J_PER_KG,
    BACKUP_EMISSION_KG_PER_GJ,
    C_VOL,
    COOLING_FILE,
    FILTER_A_DROP_C,
    FILTER_B_DROP_C,
    FLOW_GRID,
    GAS_BOILER_EFFICIENCY,
    GAS_CALORIC_J_PER_KG,
    GAS_DENSITY,
    GAS_EMISSION_KG_PER_GJ,
    GAS_NM3_PER_M3,
    GRADIENT_C_PER_M,
    HEATING_FILE,
    ASSUMED_COOLING_COP,
    MAX_COOLING_C,
    MAX_FLOW_M3H,
    MAX_RUN_DAYS,
    MIN_FLOW_M3H,
    PRIMARY_ENERGY_FACTOR,
    RESULTS_DIR,
    SEPARATOR_DROP_C,
    SUPPLY_C,
    SURFACE_C,
    WELL_LOSS_C,
    Design,
    boiler_outlet,
    build_outages,
    exchange_heat,
    lowest_demand_windows,
    pump_power_mw,
    read_demand,
)

COOLING_SUPPLY_C = 20.0

# Assumptions, not challenge values
CHILLER_HEX_APPROACH_C = 5.0
ELECTRIC_CHILLER_COP = 5.0
ELECTRICITY_CO2_KG_PER_KWH = 0.3  # value in GEMINI's example
ABSORPTION_FRACTIONS = np.linspace(0.0, 1.0, 11)
DEFAULT_RETURN_C = 50.0


@dataclass(frozen=True)
class EnergyDesign:
    """One heating and cooling design to evaluate."""

    doublets: int
    depth_m: float
    staggered: bool = True
    cop_cap: float = 0.67
    return_c: float = DEFAULT_RETURN_C

    @property
    def name(self):
        """Return a short design label."""
        outage = "staggered" if self.staggered else "together"
        return (
            f"{self.doublets}x{self.depth_m:.0f}m_COP{self.cop_cap:.2f}_R{self.return_c:.0f}_{outage}"
        )


def evaluate_day(heating_w, cooling_w, active, flow, curves, conditions, chiller_cop, fraction):
    """Return the operation for one choice, or None if it cannot be done."""
    t_in, t_primary_min, t_chiller_out, return_c = conditions
    total_flow = active * flow
    absorption_w = fraction * cooling_w
    drive_w = absorption_w / chiller_cop if absorption_w > 0 else 0.0
    chiller_flow = drive_w / (C_VOL * (t_in - t_chiller_out)) * 3600.0 if drive_w > 0 else 0.0
    if chiller_flow > total_flow + 1e-9:
        return None

    secondary = heating_w / (C_VOL * (SUPPLY_C - return_c))
    heating_flow = total_flow - chiller_flow
    heat_w = 0.0
    t_heating_out = t_in
    if active and heating_flow > 1e-9:
        heat_each, t_heating_out = exchange_heat(
            heating_flow / active,
            secondary / active,
            t_in,
            return_c,
            heating_w / active,
            t_primary_min,
        )
        heat_w = heat_each * active

    gas_kg_s = total_flow / 3600.0 * GAS_NM3_PER_M3 * GAS_DENSITY
    gas_available_w = gas_kg_s * GAS_CALORIC_J_PER_KG * GAS_BOILER_EFFICIENCY
    gas_w = min(gas_available_w, heating_w - heat_w)
    backup_w = max(0.0, heating_w - heat_w - gas_w)

    electric_cooling_w = cooling_w - absorption_w
    electric_w = electric_cooling_w / ELECTRIC_CHILLER_COP
    parasitic_w = AbsorptionChiller.DEFAULTS["parasitic_fraction"] * absorption_w
    pump_w = active * (curves[flow][0] + curves[flow][1]) * 1e6 if active else 0.0
    electricity_w = electric_w + parasitic_w + pump_w
    score = backup_w / BACKUP_BOILER_EFFICIENCY + PRIMARY_ENERGY_FACTOR * electricity_w

    brine_out = None
    if active:
        brine_out = (
            chiller_flow * t_chiller_out + heating_flow * t_heating_out
        ) / total_flow
    return {
        "score": score,
        "active": active,
        "flow": flow,
        "heat_w": heat_w,
        "gas_available_w": gas_available_w,
        "gas_w": gas_w,
        "backup_w": backup_w,
        "absorption_w": absorption_w,
        "drive_w": drive_w,
        "electric_cooling_w": electric_cooling_w,
        "electric_w": electric_w,
        "parasitic_w": parasitic_w,
        "pump_w": pump_w,
        "brine_out": brine_out,
        "secondary": secondary,
    }


def best_day(heating_w, cooling_w, available, curves, conditions, chiller_cop):
    """Return the lowest-score operation for one day."""
    best = None
    fractions = ABSORPTION_FRACTIONS if cooling_w > 0 and chiller_cop > 0 else [0.0]
    for active in range(0, available + 1):
        for flow in FLOW_GRID if active else [0.0]:
            for fraction in fractions if active else [0.0]:
                option = evaluate_day(
                    heating_w,
                    cooling_w,
                    active,
                    float(flow),
                    curves,
                    conditions,
                    chiller_cop,
                    fraction,
                )
                if option and (best is None or option["score"] < best["score"] - 1e-6):
                    best = option
    return best


def run_design(design, dates, heating_mw, cooling_mw, first, second, outages=None):
    """Run one design through all 365 days, returning rows and a summary.

    ``outages`` optionally replaces the planned outage schedule with a boolean
    array of shape (doublets, 365), for unplanned outage scenarios.
    """
    t_wellhead = SURFACE_C + GRADIENT_C_PER_M * design.depth_m - WELL_LOSS_C
    t_in = t_wellhead - SEPARATOR_DROP_C - FILTER_A_DROP_C
    t_primary_min = t_wellhead - MAX_COOLING_C + FILTER_B_DROP_C

    chiller = AbsorptionChiller()
    chiller.update_parameters({"cop_cap": design.cop_cap})
    hot_water_c = t_in - CHILLER_HEX_APPROACH_C
    chiller_cop = chiller.calculate_cop(hot_water_c, COOLING_SUPPLY_C)
    t_chiller_out = max(
        t_primary_min, chiller.parameters["hot_water_outlet_c"] + CHILLER_HEX_APPROACH_C
    )
    if t_chiller_out >= t_in:
        chiller_cop = 0.0
    conditions = (t_in, t_primary_min, t_chiller_out, design.return_c)

    well_design = Design(design.doublets, design.depth_m, design.return_c, design.staggered)
    curves = {float(flow): pump_power_mw(well_design, float(flow)) for flow in FLOW_GRID}
    if outages is None:
        outages = build_outages(well_design, first, second)
    run_days = np.zeros(design.doublets, dtype=int)
    rows = []
    for day, (heat_mw, cool_mw) in enumerate(zip(heating_mw, cooling_mw)):
        candidates = [
            index
            for index in np.argsort(run_days)
            if not outages[index, day] and run_days[index] < MAX_RUN_DAYS
        ]
        result = best_day(
            heat_mw * 1e6, cool_mw * 1e6, len(candidates), curves, conditions, chiller_cop
        )
        for index in candidates[: result["active"]]:
            run_days[index] += 1

        secondary = result["secondary"]
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
        electricity_w = result["electric_w"] + result["parasitic_w"] + result["pump_w"]
        electricity_co2_t = electricity_w / 1e3 * 24 * ELECTRICITY_CO2_KG_PER_KWH / 1000.0
        rows.append(
            {
                "date": dates[day],
                "heating_mw": heat_mw,
                "cooling_mw": cool_mw,
                "active_doublets": result["active"],
                "flow_m3h_each": result["flow"],
                "geothermal_heat_mw": result["heat_w"] / 1e6,
                "chiller_drive_mw": result["drive_w"] / 1e6,
                "produced_gas_heat_mw": result["gas_w"] / 1e6,
                "backup_heat_mw": result["backup_w"] / 1e6,
                "absorption_cooling_mw": result["absorption_w"] / 1e6,
                "electric_cooling_mw": result["electric_cooling_w"] / 1e6,
                "electricity_mw": electricity_w / 1e6,
                "t_supply_c": t_supply,
                "brine_injected_c": (
                    None if result["brine_out"] is None else result["brine_out"] - FILTER_B_DROP_C
                ),
                "gas_unused_mw": (result["gas_available_w"] - result["gas_w"]) / 1e6,
                "co2_t": (gas_co2 + backup_co2) * 86.4 + electricity_co2_t,
            }
        )
    return rows, summarize(rows, run_days, t_wellhead, chiller_cop, curves)


def summarize(rows, run_days, t_wellhead, chiller_cop, curves):
    """Return annual results and rule checks for one design."""
    to_gwh = 24.0 / 1000.0
    total = lambda key: sum(row[key] for row in rows) * to_gwh  # noqa: E731
    active_rows = [row for row in rows if row["active_doublets"]]
    worst_cooling = max(t_wellhead - row["brine_injected_c"] for row in active_rows)
    heat_gap = max(
        abs(
            row["geothermal_heat_mw"]
            + row["produced_gas_heat_mw"]
            + row["backup_heat_mw"]
            - row["heating_mw"]
        )
        for row in rows
    )
    cool_gap = max(
        abs(row["absorption_cooling_mw"] + row["electric_cooling_mw"] - row["cooling_mw"])
        for row in rows
    )
    return {
        "chiller_cop": chiller_cop,
        "geothermal_heat_gwh": total("geothermal_heat_mw"),
        "drive_gwh": total("chiller_drive_mw"),
        "gas_gwh": total("produced_gas_heat_mw"),
        "backup_gwh": total("backup_heat_mw"),
        "backup_peak_mw": max(row["backup_heat_mw"] for row in rows),
        "absorption_gwh": total("absorption_cooling_mw"),
        "absorption_peak_mw": max(row["absorption_cooling_mw"] for row in rows),
        "geothermal_heat_peak_mw": max(
            row["geothermal_heat_mw"] + row["chiller_drive_mw"] for row in rows
        ),
        "electric_cooling_gwh": total("electric_cooling_mw"),
        "electric_cooling_peak_mw": max(row["electric_cooling_mw"] for row in rows),
        "electricity_gwh": total("electricity_mw"),
        "co2_kt": sum(row["co2_t"] for row in rows) / 1000.0,
        "gas_unused_gwh": total("gas_unused_mw"),
        "min_intake_bar": min(curve[2] for curve in curves.values()),
        "run_days": [int(value) for value in run_days],
        "worst_cooling_c": worst_cooling,
        "checks": {
            "flow_50_300": all(
                MIN_FLOW_M3H <= row["flow_m3h_each"] <= MAX_FLOW_M3H for row in active_rows
            ),
            "cooling_max_40": worst_cooling <= MAX_COOLING_C + 1e-6,
            "run_days_max_330": all(value <= MAX_RUN_DAYS for value in run_days),
            "supply_100": all(abs(row["t_supply_c"] - SUPPLY_C) < 1e-6 for row in rows),
            "heat_balance": heat_gap < 1e-6,
            "cooling_balance": cool_gap < 1e-6,
        },
    }


def main():
    """Run the designs, save daily results and print a summary table."""
    dates, heating_mw = read_demand(HEATING_FILE)
    _, cooling_mw = read_demand(COOLING_FILE)
    first, second = lowest_demand_windows(heating_mw + cooling_mw / ASSUMED_COOLING_COP)
    print(f"Outage windows start: {dates[first]} and {dates[second]}")

    designs = [
        EnergyDesign(doublets, depth)
        for doublets in (1, 2, 3)
        for depth in (2500.0, 2800.0, 3200.0, 3500.0)
    ]
    designs += [
        EnergyDesign(2, 3200.0, staggered=False),
        EnergyDesign(2, 3200.0, cop_cap=0.60),
        EnergyDesign(2, 3200.0, cop_cap=0.75),
    ]

    RESULTS_DIR.mkdir(exist_ok=True)
    print(
        "design                      COP   geoHeat drive gas  bkp bkpPk absCool elecCool elecPk "
        "elecGWh CO2kt unusedGas runDays checks worstCool"
    )
    for design in designs:
        rows, s = run_design(design, dates, heating_mw, cooling_mw, first, second)
        with open(RESULTS_DIR / f"energy_{design.name}.csv", "w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        failed = [name for name, passed in s["checks"].items() if not passed]
        print(
            f"{design.name:27s} {s['chiller_cop']:4.2f} {s['geothermal_heat_gwh']:7.1f} "
            f"{s['drive_gwh']:5.1f} {s['gas_gwh']:4.1f} {s['backup_gwh']:4.1f} "
            f"{s['backup_peak_mw']:5.1f} {s['absorption_gwh']:7.1f} "
            f"{s['electric_cooling_gwh']:8.1f} {s['electric_cooling_peak_mw']:6.1f} "
            f"{s['electricity_gwh']:7.2f} {s['co2_kt']:5.1f} {s['gas_unused_gwh']:9.1f} "
            f"{'/'.join(map(str, s['run_days'])):11s} "
            f"{'PASS' if not failed else 'FAIL:' + ','.join(failed)} {s['worst_cooling_c']:6.1f}"
        )


if __name__ == "__main__":
    main()
