"""Tests for the GeoHackathon challenge inputs and derived reservoir properties."""

from pathlib import Path

import pytest

from gemini_design.challenge import (
    CHALLENGE,
    associated_gas_properties,
    load_demand,
    productivity_index_m3h_per_bar,
    reservoir_at_depth,
)

INPUTS = Path(__file__).resolve().parents[2] / "simulator_examples" / "hackathon_inputs"


def test_reference_reservoir_matches_brief():
    """2.5 km: 12 + 30 * 2.5 = 87 degC and the given 250 bar."""
    temperature, pressure = reservoir_at_depth(2500.0)
    assert temperature == pytest.approx(87.0)
    assert pressure == pytest.approx(250.0)


def test_other_depths_are_hydrostatic():
    """Pressure changes by rho * g per metre with the challenge brine density."""
    _, p1 = reservoir_at_depth(2500.0)
    _, p2 = reservoir_at_depth(3500.0)
    assert p2 - p1 == pytest.approx(1030 * 9.80665 * 1000 / 1e5)


def test_productivity_index_from_darcy():
    """200 mD x 100 m with 0.4 mPa.s brine gives about 12 m3/h per bar."""
    assert productivity_index_m3h_per_bar() == pytest.approx(12.2, abs=0.1)


def test_associated_gas():
    """80/20 mol% CH4/CO2 mixture density and LHV."""
    gas = associated_gas_properties()
    assert gas["density"] == pytest.approx(0.965, abs=0.002)
    assert gas["ch4_mass_fraction"] + gas["co2_mass_fraction"] == pytest.approx(1.0)
    assert gas["lhv"] == pytest.approx(29.66e6, rel=1e-3)


def test_demand_files_match_brief():
    """365 days, 30 MW / 111.67 GWh heating, 10 MW / 23.74 GWh cooling."""
    demand = load_demand(INPUTS)
    assert len(demand) == 365
    assert demand["heating_mw"].max() == pytest.approx(30.0)
    assert demand["heating_mw"].sum() * 24 / 1000 == pytest.approx(111.67, abs=0.01)
    assert demand["cooling_mw"].max() == pytest.approx(10.0)
    assert demand["cooling_mw"].sum() * 24 / 1000 == pytest.approx(23.74, abs=0.01)
    assert CHALLENGE["operating_days"] == 330
