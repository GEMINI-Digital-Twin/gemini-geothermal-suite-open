"""GEMINI hackathon: validate the organizers' 2027 daily loads.

Run in GEMINI repository root:
    py -3.11 -m poetry run python hackathon_work/demand_baseline.py

No external libraries are required. This is DATA QA + a preliminary
upper-bound calculation, NOT a validated GEMINI geothermal plant design.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INPUTS = ROOT / "inputs"
OUTPUTS = ROOT / "outputs"
OUTPUTS.mkdir(parents=True, exist_ok=True)


def load_demand(filename: str, power_column: str) -> dict[date, float]:
    path = INPUTS / filename
    demand: dict[date, float] = {}
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        expected = {"date", power_column}
        if not reader.fieldnames or not expected.issubset(set(reader.fieldnames)):
            raise ValueError(f"{filename}: expected columns {sorted(expected)}, got {reader.fieldnames}")
        for row in reader:
            day = date.fromisoformat(row["date"].strip())
            value_mw = float(row[power_column])
            if day in demand:
                raise ValueError(f"{filename}: duplicate day {day}")
            if value_mw < 0:
                raise ValueError(f"{filename}: negative demand for {day}")
            demand[day] = value_mw
    expected_days = {date(2027, 1, 1) + timedelta(days=i) for i in range(365)}
    if set(demand) != expected_days:
        missing = sorted(expected_days - set(demand))
        extras = sorted(set(demand) - expected_days)
        raise ValueError(f"{filename}: invalid 2027 coverage; missing={missing[:4]}, extras={extras[:4]}")
    return demand


def demand_summary(loads: dict[date, float]) -> dict:
    peak_day, peak_mw = max(loads.items(), key=lambda p: p[1])
    return {
        "n_days": len(loads),
        "peak_MW": round(peak_mw, 3),
        "peak_date": str(peak_day),
        "annual_GWh": round(sum(loads.values()) * 24 / 1000, 6),
        "positive_demand_days": sum(v > 0 for v in loads.values()),
    }


def main():
    with (INPUTS / "challenge_inputs.json").open(encoding="utf-8") as f:
        challenge = json.load(f)
    heating = load_demand("GEMINI_Heating_Demand_Daily_2027.csv", "heating_demand_MWth")
    cooling = load_demand("GEMINI_Cooling_Demand_Daily_2027.csv", "cooling_demand_MWcool")

    heat_stats = demand_summary(heating)
    cool_stats = demand_summary(cooling)
    r = challenge["reservoir"]
    b = challenge["fluid"]
    c = challenge["constraints"]
    cp = challenge["illustrative_assumptions_not_fixed_by_challenge"]["brine_cp_J_per_kg_K"]
    T_reservoir = r["surface_temperature_C"] + r["gradient_C_per_km"] * r["midpoint_depth_m_TVD"] / 1000
    max_per_doublet_MW = (b["density_kg_m3"] * c["flow_max_m3_per_h_per_doublet"] / 3600 * cp * c["maximum_brine_delta_T_C"] / 1e6)

    # Daily energy figures are derived from daily-average power, i.e. MW * 24 h.
    month_totals = defaultdict(lambda: [0., 0.])
    with (OUTPUTS / "daily_demand_checked.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "heating_MWth", "cooling_MWcool", "heating_MWh", "cooling_MWh"])
        for day in sorted(heating):
            h, q = heating[day], cooling[day]
            writer.writerow([day.isoformat(), f"{h:.3f}", f"{q:.3f}", f"{h*24:.3f}", f"{q*24:.3f}"])
            month_totals[day.month][0] += h * 24
            month_totals[day.month][1] += q * 24

    with (OUTPUTS / "monthly_energy_GWh.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["month", "heating_GWh", "cooling_GWh"])
        for month in range(1, 13):
            mh, mc = month_totals[month]
            writer.writerow([month, f"{mh/1000:.6f}", f"{mc/1000:.6f}"])

    # Illustrative heat-extraction upper bound, assuming every doublet runs at
    # its maximum flow and maximum thermal drawdown, 365 days, 100% uptime.
    # Do not interpret as a GEMINI-simulated result or a valid supply at 100 C.
    theoretical = {}
    for n in range(c["minimum_doublets"], c["maximum_doublets"] + 1):
        capacity = n * max_per_doublet_MW
        theoretical[str(n)] = {
            "maximum_extracted_heat_MW": round(capacity, 3),
            "heating_peak_MW_exceeds_this_bound": heat_stats["peak_MW"] > capacity,
            "days_heating_MW_exceeds_this_bound": sum(p > capacity for p in heating.values()),
        }

    result = {
        "heating": heat_stats,
        "cooling": cool_stats,
        "estimated_reservoir_temperature_C": round(T_reservoir, 3),
        "required_district_heating_supply_temperature_C": c["heating_supply_temperature_C"],
        "illustrative_max_heat_extraction_per_doublet_MW": round(max_per_doublet_MW, 3),
        "illustrative_heat_extraction_bounds": theoretical,
        "operating_days_rule": {
            "annual_demand_days": len(heating),
            "specified_geothermal_operating_days": c["geothermal_operating_days"],
            "remaining_days_need_separate_strategy": len(heating) - c["geothermal_operating_days"],
        },
        "caveats": [
            "The theoretical bounds are not GEMINI simulation results.",
            "Thermal power does not establish 100 C supply-temperature feasibility.",
            "No hydraulics, well losses, heat-pump COP, cooling equipment or actual 330-day schedule modeled.",
            "Heat capacity 4100 J/(kg K) is illustrative, not a fixed challenge input.",
        ],
    }
    (OUTPUTS / "baseline_summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")

    print("=== GEMINI 2027 HACKATHON: INPUT DATA BASELINE ===")
    print(f"Heating: {heat_stats['annual_GWh']:.3f} GWh, peak {heat_stats['peak_MW']:.1f} MW on {heat_stats['peak_date']}")
    print(f"Cooling: {cool_stats['annual_GWh']:.3f} GWh, peak {cool_stats['peak_MW']:.1f} MW on {cool_stats['peak_date']}")
    print(f"Reservoir temperature estimate: {T_reservoir:.1f} C (supply target {c['heating_supply_temperature_C']} C)")
    print(f"Illustrative maximum heat extraction per doublet: {max_per_doublet_MW:.2f} MW")
    for n, d in theoretical.items():
        print(f"  {n} doublet(s): {d['maximum_extracted_heat_MW']:.2f} MW upper bound; {d['days_heating_MW_exceeds_this_bound']} days above bound")
    print(f"Operating-day discrepancy: {len(heating)} demand days vs {c['geothermal_operating_days']} doublet operating days")
    print("OUTPUTS: hackathon_work/outputs/*.csv and baseline_summary.json")
    print("CAUTION: upper-bound screening only; no hydraulic validation or heating/cooling design yet.")


if __name__ == "__main__":
    main()
