"""Run the challenge baseline case and print results and rule checks.

Run from the project folder:
    PYTHONPATH=../src python cases/run_baseline.py
"""

import json
from pathlib import Path

from gemini_simulator.project_loader import build_project

PROJECT_PATH = Path(__file__).parent / "baseline_challenge.json"

RHO = 1030.0  # kg/m3, challenge brine density
CP = 4100.0  # J/(kg.K), assumption, see the JSON file
MAX_BRINE_COOLING_C = 40.0
MIN_FLOW_M3H = 50.0
MAX_FLOW_M3H = 300.0
HEATING_SUPPLY_C = 100.0


def main():
    """Run the baseline case, then print results and rule checks."""
    project = json.loads(PROJECT_PATH.read_text(encoding="utf-8"))
    solver = build_project(project)
    solver.run()
    get = solver.get_output

    flow_m3h = get("producer_well", "flow_rate")
    flow_m3s = flow_m3h / 3600.0
    t_wellhead = get("producer_well", "temperature_out")
    t_hex_in = get("filter_a", "temperature_out")
    t_hex_out = get("heat_exchanger", "primary_temperature_out")
    t_injector = get("filter_b", "temperature_out")
    t_secondary_in = next(
        entry["value"]
        for entry in project["boundary_inputs"]
        if entry["key"] == "secondary_temperature_in"
    )
    t_hex_secondary_out = get("heat_exchanger", "secondary_temperature_out")
    t_supply = get("water_mixer", "temperature")
    secondary_flow_m3s = next(
        entry["value"]
        for entry in project["boundary_inputs"]
        if entry["component"] == "secondary_splitter"
    )

    heat_doublet_w = flow_m3s * RHO * CP * (t_hex_in - t_hex_out)
    heat_exchanger_w = get("heat_exchanger", "heat_duty")
    heat_boiler_w = get("boiler", "power_th")
    heat_chp_w = get("chp", "power_th")
    heat_delivered_w = secondary_flow_m3s * RHO * CP * (t_supply - t_secondary_in)
    heat_sources_w = heat_exchanger_w + heat_boiler_w + heat_chp_w

    esp_power_w = get("producer_well", "esp_power_el")
    esp_intake = get("producer_well", "esp_intake_pressure")
    esp_discharge = get("producer_well", "esp_discharge_pressure")
    esp_hydraulic_w = flow_m3s * (esp_discharge - esp_intake) * 1e5
    esp_efficiency = esp_hydraulic_w / esp_power_w
    esp_power_at_70_w = esp_hydraulic_w / 0.7
    injector_power_w = get("injector_well", "power_el")
    injector_wellhead = get("injector_well", "wellhead_pressure")
    gas_mass_kg_s = get("separator", "gas_mass_flow_rate")
    gas_emission_kg_s = get("boiler", "emission") + get("chp", "emission")
    brine_cooling = t_wellhead - t_injector

    print(f"Case: {PROJECT_PATH.name}")
    print()
    print("PRIMARY SIDE")
    print(f"  Flow:                     {flow_m3h:8.2f} m3/h")
    print(f"  Wellhead temperature:     {t_wellhead:8.2f} C")
    print(f"  Heat exchanger in / out:  {t_hex_in:8.2f} / {t_hex_out:.2f} C")
    print(f"  Injector temperature:     {t_injector:8.2f} C")
    print(f"  Brine cooling:            {brine_cooling:8.2f} C")
    print()
    print("HEAT")
    print(f"  From brine:               {heat_doublet_w / 1e6:8.3f} MW")
    print(f"  Heat exchanger duty:      {heat_exchanger_w / 1e6:8.3f} MW")
    print(f"  Boiler:                   {heat_boiler_w / 1e6:8.3f} MW")
    print(f"  CHP:                      {heat_chp_w / 1e6:8.3f} MW")
    print(f"  Delivered to network:     {heat_delivered_w / 1e6:8.3f} MW")
    print(f"  Network in / HEX out:     {t_secondary_in:8.2f} / {t_hex_secondary_out:.2f} C")
    print(f"  Supply temperature:       {t_supply:8.2f} C")
    print()
    print("PUMPS AND GAS")
    print(f"  ESP intake / discharge:   {esp_intake:8.2f} / {esp_discharge:.2f} bar")
    print(f"  ESP power, pump curve:    {esp_power_w / 1e6:8.3f} MW")
    print(f"  ESP implied efficiency:   {esp_efficiency * 100:8.1f} %")
    print(f"  ESP power at 70%:         {esp_power_at_70_w / 1e6:8.3f} MW")
    print(f"  Injector wellhead:        {injector_wellhead:8.2f} bar")
    print(f"  Injector pump power:      {injector_power_w / 1e6:8.3f} MW")
    print(f"  Gas burned:               {gas_mass_kg_s:8.3f} kg/s")
    print(f"  Gas CO2:                  {gas_emission_kg_s * 86.4:8.2f} t/day")
    print()
    print("CHECKS")
    balance_error = abs(heat_delivered_w - heat_sources_w) / heat_sources_w * 100
    checks = [
        ("Flow within 50-300 m3/h", MIN_FLOW_M3H <= flow_m3h <= MAX_FLOW_M3H),
        ("Brine cooling at most 40 C", brine_cooling <= MAX_BRINE_COOLING_C),
        ("Heating supply reaches 100 C", t_supply >= HEATING_SUPPLY_C),
        ("Network energy balance within 0.1%", balance_error <= 0.1),
    ]
    for name, passed in checks:
        print(f"  {'PASS' if passed else 'FAIL'}  {name}")
    print(f"  Balance error: {balance_error:.4f}%")


if __name__ == "__main__":
    main()
