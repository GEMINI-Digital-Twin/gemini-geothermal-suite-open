"""Tests for doublet arrangements (series / parallel) and the co-produced gas options."""

import pytest

from gemini_design import gas_handling as gh
from gemini_design import gas_solubility as gs
from gemini_design.arrangement import DoubletPair
from gemini_design.challenge import CHALLENGE, load_demand
from gemini_design.plant import Design

INPUTS = "simulator_examples/hackathon_inputs"


def test_equal_depths_header_and_split_agree():
    """With equal doublets one header and two split HEXs give the same heat."""
    a = DoubletPair([3100, 3100], "parallel_header").evaluate(25e6, (250.0, 250.0))
    b = DoubletPair([3100, 3100], "parallel_split").evaluate(25e6, (250.0, 250.0))
    assert a["geothermal_heat_w"] == pytest.approx(b["geothermal_heat_w"], rel=0.01)


def test_series_cascades_mixed_depths():
    """Mixed depths: series (coolest first) beats one mixed header, and no cap is broken."""
    series = DoubletPair([2500, 3700], "series").evaluate(28e6, (300.0, 300.0))
    header = DoubletPair([2500, 3700], "parallel_header").evaluate(28e6, (300.0, 300.0))
    assert series["geothermal_heat_w"] > header["geothermal_heat_w"]
    for r in (series, header):
        assert max(r["brine_cooling_k"]) <= CHALLENGE["brine_cooling_max_k"] + 1e-6
        assert r["district_after_geothermal_c"] <= CHALLENGE["heating_supply_c"] + 1e-6
        heat = r["geothermal_heat_w"] + r["boiler_heat_w"]
        assert heat == pytest.approx(28e6, rel=1e-6)


def test_bad_arrangement():
    """An unknown arrangement raises."""
    with pytest.raises(ValueError):
        DoubletPair([3000, 3000], "star")


def test_henry_constants_and_vapour_pressure():
    """IAPWS Henry's constants and the water vapour pressure match handbook values."""
    assert gs.water_vapour_pressure_mpa(100.0) * 10.0 == pytest.approx(1.014, rel=0.005)
    assert gs.henry_constant_bar("co2", 25.0) == pytest.approx(1650.0, rel=0.03)
    assert gs.henry_constant_bar("ch4", 25.0) == pytest.approx(40000.0, rel=0.03)


def test_bubble_point_scales_with_gas():
    """The bubble point is tens of bar for the brief's gas and grows with the GLR."""
    p = gh.bubble_point_bar(100.0)
    assert 20.0 < p < 80.0
    more = gh.bubble_point_bar(100.0, dict(CHALLENGE, gas_liquid_ratio=1.6))
    assert more > p


def test_compressor_power_matches_isentropic_work():
    """GEMINI's compressor (with the k factor) gives the textbook isentropic work."""
    w = gh.compressor_power_w(0.1, 10.0, 40.0, 30.0)
    m = 0.8 * 16.04 + 0.2 * 44.01
    r_spec = gh.R_GAS / (m / 1000.0)
    k, eta = 1.3, 0.75 * 0.97
    ideal = 0.1 * r_spec * 303.15 * k / (k - 1) * ((40.0 / 10.0) ** ((k - 1) / k) - 1)
    assert w == pytest.approx(ideal / eta, rel=1e-6)


def test_gas_options_compare():
    """Every gas option is priced, and re-injection saves more than the CO2 the gas holds."""
    design = Design(1, 3100.0, "boiler", "electric", chiller_capacity_mw=12.0)
    rows, info = gh.compare(design, load_demand(INPUTS))
    by = {r["option"]: r for r in rows}
    assert set(by) == {
        "burn",
        "keep_dissolved",
        "co_inject",
        "disposal_well",
        "disposal_well_co2_only",
        "export",
    }
    assert by["co_inject"]["co2_saved_t"] > info["co2_inherent_t"]
    assert by["disposal_well"]["annual_cost_eur"] > by["co_inject"]["annual_cost_eur"]
    assert by["export"]["global_co2_t"] > by["export"]["co2_t"]
