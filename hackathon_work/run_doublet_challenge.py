"""GEMINI hackathon tasks 1-2: challenge doublet, one time step, checked against the constraints.

Run in GEMINI repository root:
    $env:PYTHONPATH="src"; py -3.11 -m poetry run python hackathon_work/run_doublet_challenge.py
    ... run_doublet_challenge.py --flow 300 161.6 --ua 250000 --date 2027-01-28

For each target brine flow: solves the ESP frequency / wellhead pressure,
sizes the district secondary flow from the day's heating demand
(demand / (rho*cp*(100 - 60 C))), runs one GEMINI time step, reports our own
KPIs and the constraint-checker verdict, and logs everything to
outputs/runs/. gemini_simulator.kpi is not used.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import date, datetime, timezone

from constraints import check_constraints, format_report, load_limits
from demand_baseline import load_demand
from doublet_model import PROJECT_PATH, REPO, ROOT, checker_case, run_case

RUNS = ROOT / "outputs" / "runs"


def git_commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def print_case(run: dict, report: dict, day: date, log_path):
    k, c, w, d = run["kpis"], run["controls"], run["wellhead_temperature"], run["design"]
    eta = run["pump_efficiency"]
    print(f"--- target Q = {d['target_flow_m3h']:.1f} m3/h, HEX UA = {d['hex_ua_W_K'] / 1e3:.0f} kW/K, {d['n_doublets']} doublet(s), day {day} ---")
    print(f"Heating demand:  {d['heating_demand_W'] / 1e6:.3f} MW ({d['heating_demand_per_doublet_W'] / 1e6:.3f} MW per doublet)")
    status = "reached" if c["reached"] else "NOT REACHED"
    print(
        f"Controls:        {c['mode']} -> {status}: {c['achieved_m3h']:.2f} m3/h at {c['esp_freq_hz']:.2f} Hz, "
        f"wellhead {c['wellhead_pressure_bar']:.2f} bar (surface-pressure floor {c['wellhead_pressure_floor_bar']:.2f} bar at this flow, "
        f"{c['wellhead_pressure_floor_at_target_bar']:.2f} bar at target)"
    )
    print(
        f"                 flow range at {c['flow_range_wellhead_pressure_bar']:.2f} bar wellhead: "
        f"{c['flow_at_fmin_m3h']:.1f}-{c['flow_at_fmax_m3h']:.1f} m3/h "
        f"over {c['esp_freq_range_hz'][0]}-{c['esp_freq_range_hz'][1]} Hz; ESP head <= 0 above {c['esp_zero_head_flow_m3h']} m3/h"
    )
    if not c["reached"]:
        print(f"                 REASON: {c['reason']}")
    print(f"Wellhead T:      {w['used_C']:.2f} C derived (T_res {w['T_reservoir_C']:.1f} C, wellbore loss {w['wellbore_loss_W'] / 1e6:.3f} MW)")
    print(f"Primary flow:    {k['primary_flow_m3h']:.2f} m3/h produced, {k['injection_flow_m3h']:.2f} m3/h injected")
    print(
        f"Brine T:         wellhead {k['T_wellhead_C']:.2f} -> HEX in {k['T_hex_primary_in_C']:.2f} -> "
        f"HEX out {k['T_hex_primary_out_C']:.2f} -> injection {k['T_injection_C']:.2f} C (dT {k['brine_dT_K']:.2f} K)"
    )
    print(
        f"Brine heat:      {k['brine_heat_extracted_W'] / 1e6:.3f} MW extracted, HEX duty {k['hex_heat_duty_W'] / 1e6:.3f} MW, "
        f"separator/filter losses {k['surface_brine_losses_W'] / 1e6:.3f} MW"
    )
    print(
        f"ESP:             intake {k['esp_intake_bar']:.2f} bar, discharge {k['esp_discharge_bar']:.2f} bar, dp {k['esp_dp_pa'] / 1e5:.2f} bar; "
        f"power {k['esp_power_W_at_pump_eff'] / 1e6:.4f} MW at eta={eta:.2f} "
        f"(curve: {k['esp_power_W_curve_reference'] / 1e6:.4f} MW, eta {k['esp_curve_efficiency'] * 100:.1f}%)"
    )
    print(
        f"Injector:        wellhead {k['injector_wellhead_bar']:.2f} bar, inlet {k['injector_inlet_bar']:.2f} bar, dp {k['injector_pump_dp_pa'] / 1e5:.2f} bar; "
        f"pump {k['injector_pump_power_W_at_pump_eff'] / 1e6:.4f} MW (GEMINI: {k['injector_pump_power_W_gemini'] / 1e6:.4f} MW)"
    )
    print(
        f"Secondary:       {k['secondary_flow_m3h']:.1f} m3/h, in {k['T_secondary_in_C']:.1f} C, HEX out {k['T_hex_secondary_out_C']:.2f} C, "
        f"boiler out {k['T_boiler_out_C']:.2f} C, CHP out {k['T_chp_out_C']:.2f} C"
    )
    print(
        f"District heat:   {k['district_heat_W'] / 1e6:.3f} MW delivered at {k['T_supply_C']:.2f} C = HEX {k['hex_heat_duty_W'] / 1e6:.3f} + "
        f"boiler {k['boiler_heat_W'] / 1e6:.3f} + CHP {k['chp_heat_W'] / 1e6:.3f} MW (residual {k['heat_balance_residual_W']:.1f} W)"
    )
    print(f"Gas:             {k['gas_Nm3h']:.1f} Nm3/h, fuel {k['gas_fuel_power_W'] / 1e6:.3f} MW; CHP electricity {k['chp_electricity_W'] / 1e6:.4f} MW")
    print(f"Emissions:       {k['emission_total_kg_CO2_day']:.1f} kg CO2/day (gas {k['emission_gas_kg_CO2_day']:.1f}, electricity {k['emission_electricity_kg_CO2_day']:.1f})")
    print("Constraint check:")
    print(format_report(report))
    print(f"LOG: {log_path.relative_to(REPO)}")
    print()


def main():
    heating = load_demand("GEMINI_Heating_Demand_Daily_2027.csv", "heating_demand_MWth")
    peak_day = max(heating, key=heating.get)

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--flow", type=float, nargs="+", default=[300.0, 161.6], help="target brine flow per doublet, m3/h")
    parser.add_argument("--ua", type=float, default=250e3, help="HEX UA, W/K")
    parser.add_argument("--date", type=date.fromisoformat, default=peak_day, help=f"demand day (default: heating peak {peak_day})")
    parser.add_argument("--n-doublets", type=int, default=1)
    args = parser.parse_args()

    limits = load_limits()
    commit = git_commit()
    print("=== GEMINI HACKATHON TASK 2: CHALLENGE DOUBLET + CONSTRAINT CHECK, ONE TIME STEP ===")
    print(f"Project: {PROJECT_PATH.relative_to(REPO)}  (git {commit or 'n/a'})")
    print()
    RUNS.mkdir(parents=True, exist_ok=True)
    for flow in args.flow:
        run = run_case(flow, args.ua, heating[args.date] * 1e6, n_doublets=args.n_doublets)
        report = check_constraints(checker_case(run["kpis"], args.n_doublets), limits)
        run_time = datetime.now(timezone.utc)
        solver = run.pop("solver")
        log = {
            "run_utc": run_time.isoformat(),
            "git_commit": commit,
            "project_file": str(PROJECT_PATH.relative_to(REPO)),
            "demand_day": str(args.date),
            **run,
            "component_io": {
                name: {"input": hist["input"][-1], "output": hist["output"][-1]} for name, hist in solver.history.items()
            },
            "constraint_check": report,
        }
        log_path = RUNS / f"doublet_challenge_Q{flow:g}_{run_time:%Y%m%dT%H%M%S%fZ}.json"
        log_path.write_text(json.dumps(log, indent=2, default=float), encoding="utf-8")
        print_case(run, report, args.date, log_path)
    print("CAUTION: one time step, one doublet; no 365-day loop, heat pump or cooling yet.")


if __name__ == "__main__":
    main()
