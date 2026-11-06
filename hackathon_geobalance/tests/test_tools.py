"""Tests for tools.py (author: Misghana).

Each test compares a tool with a result we know is correct: numbers given in
the challenge document, or simple hand calculations. Run from the
hackathon_geobalance folder with:  python -m pytest tests   (or: python tests/test_tools.py)
"""
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import tools  # noqa: E402

DATA = os.path.join(ROOT, "data")


def _read(name, col):
    with open(os.path.join(DATA, name), newline="") as f:
        return [float(r[col]) for r in csv.DictReader(f)]


# --- Known results from the challenge document -------------------------------

def test_heating_demand_matches_document():
    heat = _read("gemini_heating_demand_daily_2027.csv", "heating_demand_MWth")
    assert len(heat) == 365
    assert abs(max(heat) - 30.0) < 0.01                 # peak 30.0 MWth
    assert abs(sum(heat) * 24 / 1000 - 111.67) < 0.05   # 111.67 GWh/yr


def test_cooling_demand_matches_document():
    cool = _read("gemini_cooling_demand_daily_2027.csv", "cooling_demand_MWcool")
    assert len(cool) == 365
    assert abs(max(cool) - 10.0) < 0.01                 # peak 10.0 MWcool
    assert abs(sum(cool) * 24 / 1000 - 23.74) < 0.05    # 23.74 GWh/yr


def test_reservoir_temperature_from_gradient():
    assert tools.reservoir_temperature_c(2500)["temperature_c"] == 87.0   # 12 + 30 x 2.5
    assert tools.reservoir_temperature_c(3400)["temperature_c"] == 114.0  # 12 + 30 x 3.4


# --- Hand calculations ---------------------------------------------------------

def test_doublet_heat_hand_calc():
    # 300 m3/h x 1030 kg/m3 x 4000 J/kgK x 40 K = 13.73 MW
    r = tools.doublet_heat_mw(300, 40)
    assert abs(r["heat_mw"] - 13.733) < 0.01
    assert r["warnings"] == []


def test_heat_pump_energy_balance():
    r = tools.heat_pump(30, cop=3.0)
    assert abs(r["electricity_mw"] - 10.0) < 1e-9
    assert abs(r["geothermal_heat_mw"] + r["electricity_mw"] - 30.0) < 1e-9


def test_absorption_chiller_needs_735_m3h_for_10_mw():
    r = tools.absorption_chiller(10)
    assert abs(r["geothermal_heat_mw"] - 14.286) < 0.01
    assert abs(r["brine_flow_m3h"] - 734) < 2


def test_pressure_check_300_m3h_is_within_limits():
    r = tools.doublet_pressure_and_pump(300)
    assert 50 < r["total_dp_bar"] < 55        # about 52 bar
    assert r["warnings"] == []                # inside the limits from P. Andersen


def test_gas_engine_returns_expected_keys():
    r = tools.gas_engine(300)
    for key in ("electricity_mw", "heat_mw", "co2_t_per_h", "warnings"):
        assert key in r
    assert r["electricity_mw"] > 0 and r["co2_t_per_h"] > 0


# --- Limits must give warnings, never silent caps ----------------------------------

def test_flow_above_max_gives_warning():
    assert tools.doublet_heat_mw(350)["warnings"]


def test_flow_below_min_gives_warning():
    assert tools.doublet_heat_mw(30)["warnings"]


def test_brine_cooling_above_40_gives_warning():
    assert tools.doublet_heat_mw(300, 45)["warnings"]


def test_low_permeability_breaks_pressure_limits():
    assert tools.doublet_pressure_and_pump(300, perm_md=50)["warnings"]


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
    print(f"All {len(tests)} tests passed")
