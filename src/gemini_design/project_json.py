"""Write a design operating point as a native ``gemini_simulator`` project JSON and run it.

The JSON follows the three-section schema of
``simulator_examples/projects/doublet_plant.json`` (``components``,
``boundary_inputs``, ``connections``) and describes ONE active doublet
carrying its equal share of the day's demand. Running it through
``gemini_simulator.project_loader.build_project`` and ``Solver.run`` gives
an independent check of the dispatcher's flowsheet: same GEMINI models,
but wired and executed by GEMINI's own connection solver.
"""

from gemini_design.challenge import ASSUMPTIONS, CHALLENGE, associated_gas_properties
from gemini_simulator.project_loader import build_project


def build_operating_point_project(
    design, hydraulics, day_result, challenge=CHALLENGE, assumptions=ASSUMPTIONS
):
    """Return a project dict for one doublet at a dispatched operating point.

    ``day_result`` is a dict returned by :meth:`gemini_design.plant.Plant.evaluate`
    with at least one active doublet.
    """
    n = day_result["n_active"]
    if n < 1:
        raise ValueError("The operating point has no active doublet; nothing to simulate.")
    a, c = assumptions, challenge
    gas = associated_gas_properties(challenge)
    rho, cp = c["brine_density"], a["brine_cp"]
    q_m3h = day_result["flow_per_doublet_m3h"]
    q = q_m3h / 3600.0
    prod = hydraulics.producer(q_m3h)

    heating_w = day_result["heating_demand_w"] / n
    secondary_flow = heating_w / (rho * cp * (c["heating_supply_c"] - a["heating_return_c"]))
    bypass = day_result.get("hex_bypass_fraction", 0.0)
    dt_chw = a["cooling_return_c"] - c["cooling_supply_c"]
    absorption_cooling_w = (
        day_result["cooling_delivered_w"] / n if design.cooling == "absorption" else 0.0
    )
    chilled_flow = absorption_cooling_w / (a["water_density"] * a["water_cp"] * dt_chw)

    # boiler fuel: associated gas used plus purchased gas, both as mass flow at the gas LHV
    boiler_fuel_w = (
        day_result["associated_gas_heat_w"] / a["boiler_efficiency"] + day_result["purchased_gas_w"]
    ) / n
    boiler_gas_kg_s = boiler_fuel_w / gas["lhv"]

    use_hp = design.upgrade == "heat_pump" and day_result.get("heat_pump_heat_w", 0.0) > 0
    components = {
        "separator": {
            "type": "separator",
            "parameters": {
                "flow_resistance": 0.0,
                "temperature_drop": a["separator_temperature_drop_k"],
                "gas_water_ratio": c["gas_liquid_ratio"],
                "gas_density": gas["density"],
            },
        },
        "absorption_chiller": {
            "type": "absorption_chiller",
            "parameters": {
                "capacity_nominal": design.chiller_capacity_mw * 1e6 / n,
                "eta_rev": a["absorption_eta_rev"],
                "cop_max": a["absorption_cop_max"],
                "chilled_temperature_out_target": c["cooling_supply_c"],
                "aux_power_fraction": a["chiller_aux_power_fraction"],
                "hot_temperature_drop_max": a["absorption_hot_dt_max_k"],
                "rho_hot": rho,
                "cp_hot": cp,
            },
        },
        "heat_exchanger": {
            "type": "heat_exchanger",
            "parameters": {
                "flow_resistance": 0.0,
                "flow_configuration": "counter",
                "heat_transfer_coefficient": a["hex_ua_per_doublet_w_per_k"],
                "fluid_density": rho,
                "specific_heat": cp,
            },
        },
        "bypass_mixer": {"type": "mixer", "parameters": {"num_inputs": 2}},
        "boiler": {
            "type": "boiler",
            "parameters": {
                "caloric_value": gas["lhv"],
                "efficiency_factor": a["boiler_efficiency"],
                "gas_emission_factor": a["natural_gas_emission_kg_per_gj"],
                "fluid_density": rho,
                "specific_heat": cp,
            },
        },
        "injector_well": {
            "type": "injector_well",
            "parameters": {
                **hydraulics.well_config,
                "injector_pump": {
                    "efficiency_factor": c["pump_efficiency"],
                    "electricity_emission_factor": a["electricity_emission_kg_per_kwh"],
                },
            },
        },
    }
    if use_hp:
        components["heat_pump"] = {
            "type": "heat_pump",
            "parameters": {
                "mode": "lorenz",
                "eta_lorenz": a["heat_pump_eta_lorenz"],
                "Cp_h": cp,
                "Cp_s": cp,
                "rho_h": rho,
                "rho_s": rho,
                "Th_out_target": min(
                    c["heating_supply_c"],
                    (
                        day_result["supply_temperature_c"]
                        if not day_result.get("boiler_heat_w")
                        else c["heating_supply_c"]
                    ),
                ),
                "Ts_in_minimum": prod["wellhead_temperature_c"] - c["brine_cooling_max_k"],
            },
        }

    boundary_inputs = [
        {"component": "separator", "key": "pressure", "value": prod["wellhead_pressure_bar"]},
        {"component": "separator", "key": "temperature", "value": prod["wellhead_temperature_c"]},
        {"component": "separator", "key": "flow_rate", "value": q},
        {
            "component": "absorption_chiller",
            "key": "chilled_temperature_in",
            "value": a["cooling_return_c"],
        },
        {"component": "absorption_chiller", "key": "chilled_flow_rate", "value": chilled_flow},
        {
            "component": "absorption_chiller",
            "key": "cooling_water_temperature",
            "value": a["cooling_water_c"],
        },
        {
            "component": "heat_exchanger",
            "key": "secondary_temperature_in",
            "value": a["heating_return_c"],
        },
        {
            "component": "heat_exchanger",
            "key": "secondary_flow_rate",
            "value": (1 - bypass) * secondary_flow,
        },
        {"component": "bypass_mixer", "key": "input_1_flow", "value": bypass * secondary_flow},
        {"component": "bypass_mixer", "key": "input_1_temperature", "value": a["heating_return_c"]},
        {"component": "boiler", "key": "gas_flow_rate", "value": boiler_gas_kg_s},
        {
            "component": "injector_well",
            "key": "pressure_in",
            "value": (a["producer_wellhead_pressure_bar"] - a["surface_pressure_loss_bar"]) * 1e5,
        },
    ]

    connections = [
        {
            "predecessor": "separator",
            "successor": "absorption_chiller",
            "ports": [["temperature_out", "hot_temperature_in"], ["flow_rate", "hot_flow_rate"]],
        },
        {
            "predecessor": "separator",
            "successor": "heat_exchanger",
            "ports": [["pressure_out", "pressure_in"]],
        },
        {
            "predecessor": "absorption_chiller",
            "successor": "heat_exchanger",
            "ports": [
                ["hot_temperature_out", "primary_temperature_in"],
                ["hot_flow_rate", "primary_flow_rate"],
            ],
        },
        {
            "predecessor": "heat_exchanger",
            "successor": "bypass_mixer",
            "ports": [
                ["secondary_flow_rate", "input_0_flow"],
                ["secondary_temperature_out", "input_0_temperature"],
            ],
        },
    ]
    if use_hp:
        connections += [
            {
                "predecessor": "bypass_mixer",
                "successor": "heat_pump",
                "ports": [["temperature", "Th_in"], ["flow", "hot_flow_rate"]],
            },
            {
                "predecessor": "heat_exchanger",
                "successor": "heat_pump",
                "ports": [
                    ["primary_temperature_out", "Ts_in"],
                    ["primary_flow_rate", "source_flow_rate"],
                ],
            },
            {
                "predecessor": "heat_pump",
                "successor": "boiler",
                "ports": [["Th_out", "temperature_in"], ["hot_flow_rate", "water_flow_rate"]],
            },
            {
                "predecessor": "separator",
                "successor": "injector_well",
                "ports": [["flow_rate_m3h", "flow_rate"]],
            },
            {
                "predecessor": "heat_pump",
                "successor": "injector_well",
                "ports": [["Ts_out", "wellhead_temperature"]],
            },
        ]
    else:
        connections += [
            {
                "predecessor": "bypass_mixer",
                "successor": "boiler",
                "ports": [["temperature", "temperature_in"], ["flow", "water_flow_rate"]],
            },
            {
                "predecessor": "separator",
                "successor": "injector_well",
                "ports": [["flow_rate_m3h", "flow_rate"]],
            },
            {
                "predecessor": "heat_exchanger",
                "successor": "injector_well",
                "ports": [["primary_temperature_out", "wellhead_temperature"]],
            },
        ]

    return {
        "_description": (
            f"GeoHackathon design '{design.name}', one of {n} active doublet(s) at "
            f"{q_m3h:.1f} m3/h, carrying {heating_w / 1e6:.2f} MW heating and "
            f"{absorption_cooling_w / 1e6:.2f} MW absorption cooling. Generated by gemini_design."
        ),
        "_units": (
            "flow m3/s (injector_well m3/h), pressure bar (injector pressure_in Pa), "
            "temperature degC"
        ),
        "components": components,
        "boundary_inputs": boundary_inputs,
        "connections": connections,
    }


def run_operating_point_project(project):
    """Build and run a project dict with GEMINI's Solver; return the solver."""
    solver = build_project(project)
    solver.run()
    return solver


def cross_check(
    design, hydraulics, day_result, tolerance_k=0.5, challenge=CHALLENGE, assumptions=ASSUMPTIONS
):
    """Run the operating point through GEMINI's Solver and compare with the dispatcher.

    Returns a dict with the solver's supply/injection temperatures, the
    dispatcher's values and ``agrees`` (both within ``tolerance_k``).
    """
    project = build_operating_point_project(design, hydraulics, day_result, challenge, assumptions)
    solver = run_operating_point_project(project)
    supply = solver.get_output("boiler", "temperature_out")
    last_primary = "heat_pump" if "heat_pump" in project["components"] else "heat_exchanger"
    key = "Ts_out" if last_primary == "heat_pump" else "primary_temperature_out"
    injection = solver.get_output(last_primary, key)
    expected_supply = (
        challenge["heating_supply_c"]
        if day_result["unmet_heat_w"] < 1.0
        else day_result["supply_temperature_c"]
    )
    result = {
        "solver_supply_temperature_c": supply,
        "dispatcher_supply_temperature_c": expected_supply,
        "solver_injection_temperature_c": injection,
        "dispatcher_injection_temperature_c": day_result["injection_temperature_c"],
        "solver_injector_wellhead_pressure_bar": solver.get_output(
            "injector_well", "wellhead_pressure"
        ),
        "solver_absorption_cooling_w": solver.get_output("absorption_chiller", "cooling_power"),
    }
    result["agrees"] = (
        abs(supply - expected_supply) <= tolerance_k
        and abs(injection - day_result["injection_temperature_c"]) <= tolerance_k
    )
    return project, result
