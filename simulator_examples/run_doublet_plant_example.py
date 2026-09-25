"""Run a geothermal doublet plant example from a project JSON file.

Runs a doublet plant (producer well -> surface -> secondary network ->
injector well) directly from a native ``gemini_simulator`` JSON project
file.

Run with:
    $env:PYTHONPATH="src"; python simulator_examples/run_doublet_plant_example.py
"""

import json
from pathlib import Path

from gemini_simulator import kpi
from gemini_simulator.project_loader import build_project

PROJECT_PATH = Path(__file__).parent / "projects" / "doublet_plant.json"

# Secondary-side KPI inputs (T_s_in, Q_s, v); duplicated here (rather
# than re-parsed from the JSON) because kpi.py's functions take them as
# plain arguments, not read from the solver.
SECONDARY_TEMPERATURE_IN_C = 20.0
SECONDARY_FLOW_M3H = 140.0


def main():
    """Load, run, and print KPIs for the doublet plant example project."""
    with open(PROJECT_PATH, "r", encoding="utf-8") as file:
        project = json.load(file)

    # --- Producer well nodal solve, surface + secondary chain, and
    # injector well nodal solve are all wired into the same Solver
    # graph now -- one solver.run() drives the whole plant.
    solver = build_project(project)
    solver.run()

    primary_flow_m3h = solver.get_output("producer_well", "flow_rate")
    primary_flow_m3s = solver.get_output("producer_well", "flow_rate_m3s")
    injector_wellhead_pressure_bar = solver.get_output("injector_well", "wellhead_pressure")

    t_s_out = kpi.secondary_outlet_temperature(solver)
    power_plant_w = kpi.plant_thermal_power_w(
        solver,
        secondary_flow_m3s=SECONDARY_FLOW_M3H / 3600,
        secondary_temperature_in=SECONDARY_TEMPERATURE_IN_C,
    )
    power_doublet_w = kpi.doublet_thermal_power_w(solver, primary_flow_m3s=primary_flow_m3s)

    # --- Injector pump: boosts the surface network's return water
    # (FilterB's outlet) up to the pressure the injector well +
    # reservoir require to accept the same flow rate back (mass
    # balance: what's produced is re-injected). Computed inside
    # InjectorWell itself (mirroring how the ESP is embedded in
    # ProducerWell), since its required outlet pressure is the well's
    # own solved wellhead pressure.
    surface_pressure_bar = solver.get_output("filter_b", "pressure_out")
    injector_pump_power_w = solver.get_output("injector_well", "power_el")
    injector_pump_emission_kg_s = solver.get_output("injector_well", "emission")

    # --- ESP electrical power/emission, net of on-site CHP generation
    # used to offset it first.
    esp_power_w = solver.get_output("producer_well", "esp_power_el")
    chp_power_el_w = solver.get_output("chp", "power_el")
    esp_emission_kg_s = kpi.esp_emission_kg_s(
        esp_power_w,
        chp_power_el_w,
        project["components"]["producer_well"]["parameters"]["esp"]["electricity_emission_factor"],
    )

    emission_kg_s = kpi.total_emission_kg_s(
        solver,
        esp_emission_kg_s=esp_emission_kg_s,
        injector_pump_emission_kg_s=injector_pump_emission_kg_s,
    )
    electricity_surplus_w = kpi.electricity_surplus_w(solver, esp_power_w, injector_pump_power_w)
    power_total_w = kpi.power_total_w(power_plant_w, solver, esp_power_w, injector_pump_power_w)

    print(f"Loaded plant:    {PROJECT_PATH}")
    print(f"Solved primary flow rate (well nodal balance): {primary_flow_m3h:.2f} m3/h")
    print(
        f"Separator out:   P={solver.get_output('separator', 'pressure_out'):.4f} bar, "
        f"T={solver.get_output('separator', 'temperature_out'):.2f} C"
    )
    print(
        f"Heat exch. out:  T_primary="
        f"{solver.get_output('heat_exchanger', 'primary_temperature_out'):.2f} C, "
        f"T_secondary={solver.get_output('heat_exchanger', 'secondary_temperature_out'):.2f} C"
    )
    print(
        f"Boiler:          T_out={solver.get_output('boiler', 'temperature_out'):.2f} C, "
        f"power_th={solver.get_output('boiler', 'power_th') / 1e6:.3f} MW"
    )
    print(
        f"CHP:             T_out={solver.get_output('chp', 'temperature_out'):.2f} C, "
        f"power_el={solver.get_output('chp', 'power_el') / 1e6:.3f} MW, "
        f"power_th={solver.get_output('chp', 'power_th') / 1e6:.3f} MW"
    )
    secondary_gas_power_mw = (
        solver.get_output("boiler", "power_th") + solver.get_output("chp", "power_th")
    ) / 1e6
    print(f"Secondary gas power (boiler.power_th + chp.power_th): {secondary_gas_power_mw:.3f} MW")
    print(f"ESP (producer):  power_el={esp_power_w / 1e6:.4f} MW")
    print(
        f"Injector well:   P_wellhead={injector_wellhead_pressure_bar:.4f} bar "
        f"(surface P={surface_pressure_bar:.4f} bar)"
    )
    print(f"Injector pump:   power_el={injector_pump_power_w / 1e6:.4f} MW")
    print()
    print(f"T_s_out:         {t_s_out:.2f} C   (flow-weighted mix of boiler/CHP outlets)")
    print(f"power_plant:     {power_plant_w / 1e6:.3f} MW  (secondary-network thermal power)")
    print(
        f"power_doublet:   {power_doublet_w / 1e6:.3f} MW  (primary-side thermal power extracted)"
    )
    print(
        f"power_total:     {power_total_w / 1e6:.3f} MW  "
        f"(power_plant - ESP - InjectorPump + CHP)"
    )
    print(
        f"electricity_surplus: {electricity_surplus_w / 1e6:.4f} MW  " f"(CHP - ESP - InjectorPump)"
    )
    print(
        f"emission_total:  {emission_kg_s * 86400:.2f} kg CO2/day  "
        f"(boiler + CHP gas, ESP + InjectorPump electricity)"
    )

    # --- Additional output (Pres_P, Pres_I, ESP_in, ESP_out, Q): reservoir
    # pressures are plant parameters (not solved), ESP intake/discharge
    # pressures come from the same nodal solve used for the primary flow
    # rate above.
    esp_intake_bar = solver.get_output("producer_well", "esp_intake_pressure")
    esp_discharge_bar = solver.get_output("producer_well", "esp_discharge_pressure")
    reservoir_pressure_p_bar = project["components"]["producer_well"]["parameters"][
        "reservoir_pressure_bar"
    ]
    reservoir_pressure_i_bar = project["components"]["injector_well"]["parameters"][
        "reservoir_pressure_bar"
    ]
    print()
    print("----------------------------------------------------------")
    print(f"Q (primary flow rate):        {primary_flow_m3h:.2f} m3/h")
    print(f"Pres_P (producer reservoir):  {reservoir_pressure_p_bar:.2f} bar")
    print(f"Pres_I (injector reservoir):  {reservoir_pressure_i_bar:.2f} bar")
    if esp_intake_bar is not None:
        print(f"ESP_in (intake pressure):     {esp_intake_bar:.4f} bar")
        print(f"ESP_out (discharge pressure): {esp_discharge_bar:.4f} bar")
    print(f"T_s_out:                      {t_s_out:.2f} C")
    print(f"power_plant:                  {power_plant_w / 1e6:.3f} MW")
    print(f"emission_total:               {emission_kg_s * 86400:.2f} kg CO2/day")


if __name__ == "__main__":
    main()
