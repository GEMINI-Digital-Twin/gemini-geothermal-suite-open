"""Unit tests for the AbsorptionChiller model.

Reference values are hand calculations of the ideal three-temperature COP,
COP_ideal = (1 - T_rej / T_gen) * T_evap / (T_rej - T_evap), times the
second-law fraction 0.5.
"""

import pytest

from gemini_model.absorption_chiller.absorption_chiller import AbsorptionChiller
from gemini_simulator.project_loader import build_project


def test_calibration_point_matches_published_cop():
    """At 85 C generator, 6 C evaporator and 35 C rejection, COP should be about 0.67."""
    chiller = AbsorptionChiller()
    chiller.update_parameters({"cop_cap": 1.0, "evaporator_approach_c": 0.0, "hot_water_outlet_c": 80.0})
    # Hot water 90 -> 80 C gives an 85 C mean generator: 0.5 * (1 - 308.15 / 358.15) * 279.15 / 29 = 0.672
    assert chiller.calculate_cop(90.0, 6.0) == pytest.approx(0.672, abs=0.001)


def test_warm_chilled_water_reaches_the_cap():
    """A 20 C chilled supply should reach the capped COP with 100 C hot water."""
    assert AbsorptionChiller().calculate_cop(100.0, 20.0) == pytest.approx(0.67)


def test_too_cold_hot_water_gives_zero_cop():
    """Below the Duhring limit (mean generator under 2*35 - 15 + 10 = 65 C) COP is zero."""
    assert AbsorptionChiller().calculate_cop(59.0, 20.0) == 0.0


def test_demand_driven_energy_balance():
    """Rejected heat should equal cooling plus drive heat."""
    chiller = AbsorptionChiller()
    chiller.calculate_output({"cooling_w": 10e6, "hot_water_in_c": 100.0, "chilled_supply_c": 20.0})
    output = chiller.get_output()
    assert output["drive_heat_w"] == pytest.approx(10e6 / 0.67)
    assert output["heat_rejected_w"] == pytest.approx(10e6 + 10e6 / 0.67)
    assert output["power_el"] == pytest.approx(0.4e6)


def test_demand_driven_rejects_cold_hot_water():
    with pytest.raises(ValueError):
        AbsorptionChiller().calculate_output({"cooling_w": 1e6, "hot_water_in_c": 55.0})


def test_flow_driven_cooling_from_hot_water_stream():
    """100 m3/h of water cooled from 95 to 70 C gives 2.904 MW drive heat and 1.946 MW cooling."""
    chiller = AbsorptionChiller()
    chiller.calculate_output({"temperature_in": 95.0, "water_flow_rate": 100.0 / 3600.0})
    output = chiller.get_output()
    drive = 1000.0 * 100.0 / 3600.0 * 4181.0 * 25.0
    assert output["temperature_out"] == pytest.approx(70.0)
    assert output["drive_heat_w"] == pytest.approx(drive)
    assert output["cooling_w"] == pytest.approx(0.67 * drive)


def test_flow_driven_cold_water_passes_through():
    chiller = AbsorptionChiller()
    chiller.calculate_output({"temperature_in": 60.0, "water_flow_rate": 0.01})
    output = chiller.get_output()
    assert output["temperature_out"] == 60.0
    assert output["cooling_w"] == 0.0


def test_chiller_runs_in_a_plant_project():
    """A plant JSON can split hot water to the chiller through the simulator."""
    project = {
        "components": {
            "hot_water_splitter": {"type": "splitter", "parameters": {"split_fractions": [0.4, 0.6]}},
            "absorption_chiller": {"type": "absorption_chiller", "parameters": {"chilled_supply_c": 20.0}},
        },
        "boundary_inputs": [
            {"component": "hot_water_splitter", "key": "input", "value": 0.05},
            {"component": "absorption_chiller", "key": "temperature_in", "value": 95.0},
        ],
        "connections": [
            {
                "predecessor": "hot_water_splitter",
                "successor": "absorption_chiller",
                "predecessor_output": "output_0",
                "successor_input": "water_flow_rate",
            }
        ],
    }
    solver = build_project(project)
    solver.run()
    drive = 1000.0 * 0.02 * 4181.0 * 25.0
    assert solver.get_output("absorption_chiller", "cooling_w") == pytest.approx(0.67 * drive)
