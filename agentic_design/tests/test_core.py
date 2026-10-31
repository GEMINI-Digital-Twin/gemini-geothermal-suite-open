"""Tests: hand-calculated values, constraint detection, GEMINI cross-check.

Run from the repository root:  pytest agentic_design/tests -q
(with PYTHONPATH=src;. on Windows or src:. on Linux/macOS)
"""

import math

import numpy as np
import pytest

from agentic_design.annual import PlantDesign, run_year
from agentic_design.checks import check
from agentic_design.config import (CHALLENGE, Assumptions, gas_properties, load_demand,
                                   reservoir_pressure_bar, reservoir_temperature_c)
from agentic_design.plant_json import build_project_dict, validate_project
from agentic_design.verify import operating_point, verify_days
from agentic_design.wells import WellDesign, check_injection_sign, injector, producer, productivity_index_m3h_per_bar

A = Assumptions()


@pytest.fixture(scope="module")
def base():
    d = PlantDesign("2x2500m", 2)
    daily, k, _, _ = run_year(d, A)
    return d, daily, k


# ---------------------------------------------------------------- inputs
def test_demand_matches_challenge_document():
    df = load_demand()
    assert len(df) == 365
    assert df["heating_mw"].sum() * 24 / 1e3 == pytest.approx(CHALLENGE["heating_annual_gwh"], abs=0.01)
    assert df["cooling_mw"].sum() * 24 / 1e3 == pytest.approx(CHALLENGE["cooling_annual_gwh"], abs=0.01)
    assert df["heating_mw"].max() == pytest.approx(30.0)
    assert str(df.loc[df["heating_mw"].idxmax(), "date"].date()) == "2027-01-28"
    assert str(df.loc[df["cooling_mw"].idxmax(), "date"].date()) == "2027-07-19"


def test_reservoir_conditions():
    assert reservoir_temperature_c(2500) == pytest.approx(87.0)  # 12 + 30 * 2.5 (bootcamp said ~75: wrong)
    assert reservoir_pressure_bar(2500) == pytest.approx(250.0)
    assert reservoir_pressure_bar(3500) - reservoir_pressure_bar(2500) == pytest.approx(1030 * 9.81 * 1000 / 1e5)


def test_associated_gas_properties():
    g = gas_properties()
    assert g["lhv_mj_nm3"] == pytest.approx(0.8 * 35.83)
    assert g["co2_kg_nm3_burned"] == pytest.approx(1.9768)  # 0.8 from CH4 + 0.2 passing through


# ---------------------------------------------------------------- wells (hand calcs)
def test_productivity_index_darcy():
    k = 200 * 9.869233e-16
    pi = 2 * math.pi * k * 100 / (0.4e-3 * (math.log(1000 / 0.108) - 0.75)) * 3600 * 1e5
    assert productivity_index_m3h_per_bar(A) == pytest.approx(pi)
    assert 12 < pi < 15


def test_static_injector_column_is_hydrostatic():
    r = check_injection_sign()
    assert r["bhp_static_bar"] - 100 == pytest.approx(1030 * 9.81 * 2500 / 1e5, rel=1e-6)


def test_injection_friction_sign_corrected():
    r = check_injection_sign()
    # corrected: friction lowers BHP when flowing down; GEMINI's positive-flow walk raises it
    assert r["bhp_corrected_negative_flow_bar"] < r["bhp_static_bar"] < r["bhp_gemini_positive_flow_bar"]
    assert r["bhp_gemini_positive_flow_bar"] - r["bhp_corrected_negative_flow_bar"] == pytest.approx(
        2 * r["friction_bar"], rel=1e-3)


def test_friction_hand_calc_300m3h():
    v = (300 / 3600) / (math.pi / 4 * 0.2 ** 2)
    re = 1030 * v * 0.2 / 0.4e-3
    f = 0.25 / math.log10(1e-4 / (3.7 * 0.2) + 5.74 / re ** 0.9) ** 2
    dp = f * 1030 * 2500 / 0.2 * v ** 2 / 2 / 1e5
    assert check_injection_sign(q_m3h=300)["friction_bar"] == pytest.approx(dp, rel=1e-3)


def test_esp_power_is_q_dp_over_eta():
    p = producer(300, WellDesign(), A)
    assert p["esp_power_mw"] == pytest.approx(300 / 3600 * p["esp_dp_bar"] * 1e5 / 0.7 / 1e6)
    assert p["bottomhole_pressure_bar"] == pytest.approx(250 - 300 / productivity_index_m3h_per_bar(A))
    assert p["wellhead_pressure_check_bar"] == pytest.approx(A.producer_wellhead_pressure_bar, abs=1e-6)
    assert p["wellhead_temperature_c"] < 87.0


def test_lower_flow_loses_more_heat_up_the_well():
    t50 = producer(50, WellDesign(), A)["wellhead_temperature_c"]
    t300 = producer(300, WellDesign(), A)["wellhead_temperature_c"]
    assert t50 < t300 < 87.0


def test_injector_needs_more_pressure_at_higher_rate():
    assert injector(300, 50, WellDesign(), A)["required_wellhead_pressure_bar"] > \
        injector(100, 50, WellDesign(), A)["required_wellhead_pressure_bar"]


# ---------------------------------------------------------------- annual model
def test_daily_energy_and_volume_balance(base):
    _, daily, _ = base
    supplied = daily["heat_geothermal_mw"] + daily["heat_assoc_gas_boiler_mw"] + daily["heat_ng_boiler_mw"]
    assert np.allclose(supplied, daily["heating_mw"], atol=1e-9)
    assert (daily["production_m3h"] == daily["injection_m3h"]).all()


def test_geothermal_heat_equals_brine_heat(base):
    _, daily, _ = base
    on = daily["doublets_on"] > 0
    rho_cp = 1030 * A.brine_specific_heat_j_kgk / 3600 / 1e6
    brine = daily.loc[on, "q_total_m3h"] * rho_cp * (
        daily.loc[on, "t_wellhead_c"] - A.surface_temperature_loss_c - daily.loc[on, "t_injection_c"])
    assert np.allclose(brine, daily.loc[on, "heat_geothermal_mw"], rtol=1e-9)


def test_baseline_respects_hard_constraints(base):
    d, daily, k = base
    codes = {f["code"] for f in check(daily, k, d, A) if f["severity"] == "violation"}
    assert codes == {"C8_COOLING_UNMET"}  # cooling models come next
    assert max(k["operating_days_per_doublet"]) <= 330


def test_brine_cooling_cap_holds_for_deep_wells():
    d = PlantDesign("3x3500m", 3, WellDesign(depth_m=3500))
    daily, k, _, _ = run_year(d, A)
    assert k["max_brine_cooling_c"] <= 40.0 + 1e-6


# ---------------------------------------------------------------- checker
def test_checker_flags_doctored_violations(base):
    d, daily, k = base
    bad = daily.copy()
    i = bad.index[bad["doublets_on"] > 0][:3]
    bad.loc[i[0], "q_per_doublet_m3h"] = 320
    bad.loc[i[1], "q_per_doublet_m3h"] = 30
    bad.loc[i[2], "brine_cooling_c"] = 45
    bad.loc[i[2], "injection_m3h"] += 5
    k2 = dict(k, operating_days_per_doublet=[340, 100])
    codes = {f["code"] for f in check(bad, k2, PlantDesign("bad", 4), A)}
    assert {"C1_DOUBLET_COUNT", "C2_MAX_FLOW", "C3_MIN_FLOW", "C4_BRINE_COOLING",
            "C5_VOLUME_BALANCE", "C6_OPERATING_DAYS"} <= codes


def test_checker_flags_shallow_esp():
    d = PlantDesign("shallow", 1, WellDesign(esp_depth_m=300))
    daily, k, _, _ = run_year(d, A)
    assert "P3_ESP_INTAKE" in {f["code"] for f in check(daily, k, d, A)}


# ---------------------------------------------------------------- GEMINI project files
def test_validator_catches_typos_and_missing_inputs(base):
    d, daily, k = base
    p = build_project_dict(d, operating_point(daily.loc[27], A), A, hx_ua_w_k=k["hx_ua_mw_k"] * 1e6)
    assert validate_project(p) == []
    p["connections"][2]["successor"] = "seperator"
    p["boundary_inputs"] = p["boundary_inputs"][1:]
    errs = " ".join(validate_project(p))
    assert "seperator" in errs and "producer_well_1" in errs


def test_fast_model_matches_full_gemini_simulator(base):
    d, daily, k = base
    v = verify_days(d, daily, A, ua_mw_k=k["hx_ua_mw_k"])
    assert len(v) == 4 and v["pass"].all()  # peak heating, median, minimum, peak cooling
