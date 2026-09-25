"""Validate gemini_simulator.well_flow's producer-well nodal solve.

Validates it against a real reference solved primary flow rate for the
doublet-A configuration (reservoir/well/ESP parameters transcribed
directly from ``component_parameter.json``).
"""

import json
from pathlib import Path

import pytest

from gemini_simulator.well_flow import solve_primary_flow_m3h

PROJECT_PATH = (
    Path(__file__).resolve().parents[2] / "simulator_examples" / "projects" / "doublet_plant.json"
)

# Reference simulator's own solved flow rate for the doublet-A
# configuration at Pwh_prod=3 bar, Twh_prod=80 C, f_esp=69 Hz.
REFERENCE_SOLVED_FLOW_M3H = 135.92584228893725


def test_producer_well_flow_rate_matches_reference_within_correlation_tolerance():
    """Producer well flow rate should match the reference within tolerance."""
    with open(PROJECT_PATH, "r", encoding="utf-8") as file:
        project = json.load(file)

    well_config = dict(project["components"]["producer_well"]["parameters"])
    well_config["esp_freq_hz"] = 69.0
    wellhead_pressure_bar = 3.0
    wellhead_temperature_c = 80.0

    flow_m3h = solve_primary_flow_m3h(
        well_config,
        wellhead_pressure_bar=wellhead_pressure_bar,
        wellhead_temperature_c=wellhead_temperature_c,
        ambient_temperature_c=well_config.get("ambient_temperature_c", 20.0),
    )

    # Different well-friction correlations (Beggs-Brill/Darcy-Weisbach vs.
    # the reference simulator's own VLP code) -- expect agreement within
    # ~1%, not exact.
    assert flow_m3h == pytest.approx(REFERENCE_SOLVED_FLOW_M3H, rel=0.01)
