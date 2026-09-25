"""Validate injector-side additions against a reference doublet-A run.

Validates the injector-side additions (``gemini_simulator.well_flow``'s
``producer_esp_power_w``/``solve_injector_wellhead_pressure_bar`` and
``gemini_simulator.kpi``'s ESP/injector-pump-aware emission/power KPIs)
against a real reference run of the same doublet-A plant configuration.

The reference run (``controls.init`` = ``[Pwh_prod=3, T_s_in=20,
Q_s=140, f_esp=65, u=80, v=80]``) reports, among other things::

    ESP            power_el=174444.715702 W   emission=0.011748 kg/s
    Boiler         emission=0.028412 kg/s
    CHP            emission=0.007103 kg/s
    InjectorPump   Pout~=1e-08 bar (effectively no boost needed)

-> total emissions = (0.011748 + 0.028412 + 0.007103) * 86400
= 4083.08 kg CO2/day.
"""

import json
from pathlib import Path

import pytest

from gemini_simulator import kpi
from gemini_simulator.project_loader import build_project
from gemini_simulator.well_flow import producer_esp_power_w, solve_injector_wellhead_pressure_bar

PROJECT_PATH = (
    Path(__file__).resolve().parents[2] / "simulator_examples" / "projects" / "doublet_plant.json"
)

# Reference doublet-A run output (controls.init, f_esp=65).
REFERENCE_ESP_POWER_W = 174444.715702
REFERENCE_EMISSION_TOTAL_KG_DAY = (0.011748 + 0.028412 + 0.007103) * 86400.0

SECONDARY_TEMPERATURE_IN_C = 20.0
SECONDARY_FLOW_M3H = 140.0


def _load_project():
    with open(PROJECT_PATH, "r", encoding="utf-8") as file:
        return json.load(file)


def test_producer_esp_power_matches_reference_within_correlation_tolerance():
    """Producer ESP power should match the reference run within tolerance."""
    project = _load_project()
    solver = build_project(project)
    solver.run()

    flow_m3h = solver.get_output("producer_well", "flow_rate")
    esp_power_w = producer_esp_power_w(
        project["components"]["producer_well"]["parameters"], flow_m3h
    )

    assert esp_power_w == pytest.approx(REFERENCE_ESP_POWER_W, rel=0.01)


def test_injector_wellhead_pressure_floors_near_zero():
    """Injector wellhead pressure floors near zero.

    ``Pout~=1e-08 bar``: the injector well's hydrostatic column (2500 m+
    of brine) alone over-delivers the bottomhole pressure the reservoir
    needs, so no injector pump boost is actually required.
    """
    project = _load_project()

    wellhead_pressure_bar = solve_injector_wellhead_pressure_bar(
        project["components"]["injector_well"]["parameters"],
        flow_m3h=129.02,
        wellhead_temperature_c=20.0,
    )

    assert wellhead_pressure_bar == pytest.approx(0.001, abs=1e-6)


def test_emission_total_with_esp_and_injector_pump_matches_reference():
    """Total emissions with ESP + injector pump should match the reference."""
    project = _load_project()
    solver = build_project(project)
    solver.run()

    esp_power_w = solver.get_output("producer_well", "esp_power_el")
    chp_power_el_w = solver.get_output("chp", "power_el")
    esp_emission_kg_s = kpi.esp_emission_kg_s(
        esp_power_w,
        chp_power_el_w,
        project["components"]["producer_well"]["parameters"]["esp"]["electricity_emission_factor"],
    )

    injector_pump_emission_kg_s = solver.get_output("injector_well", "emission")

    emission_kg_s = kpi.total_emission_kg_s(
        solver,
        esp_emission_kg_s=esp_emission_kg_s,
        injector_pump_emission_kg_s=injector_pump_emission_kg_s,
    )

    assert emission_kg_s * 86400.0 == pytest.approx(REFERENCE_EMISSION_TOTAL_KG_DAY, rel=0.01)
