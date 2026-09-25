"""Run the parallel-heat-exchanger doublet plant example from a project JSON file.

Runs a plant (producer well -> degasser -> filter -> 3 parallel heat
exchangers -> filter -> injector well) from its native
``gemini_simulator`` JSON project file.

This is an independent topology demonstrating that the same generic Solver/JSON
schema can describe a different plant layout.

Run with:
    $env:PYTHONPATH="src"; python simulator_examples/run_parallel_hex_plant_example.py
"""

import json
from pathlib import Path

from gemini_simulator.project_loader import build_project

PROJECT_PATH = Path(__file__).parent / "projects" / "parallel_hex_plant.json"


def main():
    """Load, run, and print KPIs for the parallel-HEX plant example project."""
    with open(PROJECT_PATH, "r", encoding="utf-8") as file:
        project = json.load(file)

    solver = build_project(project)
    solver.run()

    primary_flow_m3h = solver.get_output("producer_well", "flow_rate")
    esp_power_w = solver.get_output("producer_well", "esp_power_el")

    print(f"Loaded plant:    {PROJECT_PATH}")
    print(f"Primary flow rate (well nodal balance): {primary_flow_m3h:.2f} m3/h")
    print(f"ESP power_el:    {esp_power_w / 1e6:.4f} MW")
    print(
        f"Degasser out:    P={solver.get_output('degasser', 'pressure_out'):.4f} bar, "
        f"T={solver.get_output('degasser', 'temperature_out'):.2f} C"
    )
    print(
        f"Filter_1 out:    P={solver.get_output('filter_1', 'pressure_out'):.4f} bar, "
        f"T={solver.get_output('filter_1', 'temperature_out'):.2f} C, "
        f"Q={solver.get_output('filter_1', 'flow_rate') * 3600:.2f} m3/h"
    )
    for name in ("hex_1", "hex_2", "hex_3"):
        print(
            f"{name}:          "
            f"Q_primary={solver.get_output(name, 'primary_flow_rate') * 3600:.2f} m3/h, "
            f"T_primary_out={solver.get_output(name, 'primary_temperature_out'):.2f} C, "
            f"T_secondary_out={solver.get_output(name, 'secondary_temperature_out'):.2f} C"
        )
    print(
        f"HEX mixer out:   Q={solver.get_output('hex_mixer', 'flow') * 3600:.2f} m3/h, "
        f"T={solver.get_output('hex_mixer', 'temperature'):.2f} C"
    )
    print(
        f"Filter_2 out:    P={solver.get_output('filter_2', 'pressure_out'):.4f} bar, "
        f"T={solver.get_output('filter_2', 'temperature_out'):.2f} C, "
        f"Q={solver.get_output('filter_2', 'flow_rate') * 3600:.2f} m3/h"
    )
    print(
        f"Injector well:   "
        f"P_wellhead={solver.get_output('injector_well', 'wellhead_pressure'):.4f} bar"
    )
    print(
        f"Injector pump:   power_el={solver.get_output('injector_well', 'power_el') / 1e6:.4f} MW, "
        f"emission={solver.get_output('injector_well', 'emission') * 86400:.2f} kg CO2/day"
    )


if __name__ == "__main__":
    main()
