"""Heat pump and chiller models, integrated designs, and documented GEMINI component issues."""

import math
import tempfile

import numpy as np
import pytest

from agentic_design.annual import PlantDesign, run_year
from agentic_design.checks import check
from agentic_design.config import Assumptions
from agentic_design.surface import heat_pump_operate
from agentic_design.verify import verify_days
from agentic_design.wells import WellDesign
from gemini_model.chiller.absorption_chiller import AbsorptionChiller, absorption_performance
from gemini_model.chiller.electric_chiller import electric_chiller_cop
from gemini_model.heat_exchanger.heat_exchanger import HeatExchanger
from gemini_model.heatpump.heatpump_basic import HeatpumpBasic

A = Assumptions()
INTEGRATED = PlantDesign("2x2500m_HP12_ABS6_EC4", 2, heat_pump_mw=12, absorption_mw=6, electric_chiller_mw=4)


@pytest.fixture(scope="module")
def integrated():
    daily, k, _, _ = run_year(INTEGRATED, A)
    return daily, k


# ---------------------------------------------------------------- chillers
def test_absorption_nominal_and_limits():
    frac, cop, ddt = absorption_performance(85.0, 30.0, 7.0)
    assert ddt == pytest.approx(20.5) and frac == pytest.approx(1.0) and 0.65 < cop < 0.8
    assert absorption_performance(40.0, 30.0, 7.0)[1] == 0.0  # too cold to drive
    # warmer chilled water -> more capacity at the same drive temperature
    assert absorption_performance(70.0, 30.0, 23.0)[0] > absorption_performance(70.0, 30.0, 7.0)[0]


def test_absorption_energy_balance():
    ch = AbsorptionChiller()
    ch.update_parameters({"capacity_w": 6e6})
    ch.calculate_output({"cooling_load": 5e6, "drive_temperature_in": 84.0, "drive_flow_capacity": 0.343e6,
                         "cooling_water_temperature": 30.0, "chilled_water_supply_temperature": 20.0,
                         "chilled_water_return_temperature": 26.0})
    o = ch.get_output()
    assert o["heat_rejected"] == pytest.approx(o["cooling"] + o["drive_heat"])
    assert o["drive_temperature_out"] == pytest.approx(84.0 - o["drive_heat"] / 0.343e6)
    assert o["cooling"] == pytest.approx(o["cop"] * o["drive_heat"])


def test_electric_chiller_below_carnot_and_better_with_warm_chilled_water():
    cop20, cop7 = float(electric_chiller_cop(20, 30)), float(electric_chiller_cop(7, 30))
    carnot20 = (20 - 3 + 273.15) / ((30 + 5) - (20 - 3))
    assert cop7 < cop20 < carnot20


# ---------------------------------------------------------------- heat pump
def test_fast_heat_pump_matches_gemini_heatpumpbasic():
    c_snk, c_src = 30 / 45, 600 * 1030 * 4000 / 3600 / 1e6
    r = heat_pump_operate(15.0, 30 - 18.1, c_snk, 82.0, 58.0, np.array([c_src]), 85.7 - 40)
    hp = HeatpumpBasic()
    hp.update_parameters({"mode": "lorenz", "eta_lorenz": 0.5, "Th_out_target": float(r["sink_out_c"][0]),
                          "Ts_in_minimum": 45.6, "Cp_h": 4000, "Cp_s": 4000, "rho_h": 1030, "rho_s": 1030})
    # margin of 0.1 K below our brine floor (45.7): GEMINI's optimiser lands a hair below the exact floor and
    # then enters its broken constrained branch (see test_gemini_issue_heatpump_constrained_branch_nonsense)
    hp.calculate_output({"Th_in": 82.0, "Ts_in": 58.0, "hot_flow_rate": c_snk * 1e6 / (1030 * 4000),
                         "source_flow_rate": 600 / 3600})
    o = hp.get_output()
    assert o["COP"] == pytest.approx(float(r["cop"][0]), rel=1e-3)
    assert o["power_el"] / 1e6 == pytest.approx(float(r["power"][0]), rel=1e-3)


def test_heat_pump_respects_brine_floor():
    r = heat_pump_operate(50.0, 40.0, 0.6, 80.0, 50.0, np.array([0.3]), 45.0)
    assert float(r["source_out_c"][0]) >= 45.0 - 1e-6


# ---------------------------------------------------------------- integrated design
def test_integrated_design_meets_heating_and_cooling(integrated):
    daily, k = integrated
    codes = {f["code"] for f in check(daily, k, INTEGRATED, A) if f["severity"] == "violation"}
    assert codes == set()
    assert k["cooling_unmet_gwh"] == pytest.approx(0, abs=1e-6) and k["heating_unmet_gwh"] == pytest.approx(0, abs=1e-6)
    assert k["max_brine_cooling_c"] <= 40 + 1e-6


def test_integrated_balances(integrated):
    daily, _ = integrated
    heat = daily[["heat_geothermal_mw", "heat_pump_mw", "heat_assoc_gas_boiler_mw", "heat_ng_boiler_mw"]].sum(axis=1)
    assert np.allclose(heat, daily["heating_mw"], atol=1e-6)
    cool = daily[["cooling_absorption_mw", "cooling_electric_mw", "cooling_unmet_mw"]].sum(axis=1)
    assert np.allclose(cool, daily["cooling_mw"], atol=1e-6)


def test_integrated_design_verified_by_gemini(integrated):
    daily, k = integrated
    v = verify_days(INTEGRATED, daily, A, ua_mw_k=k["hx_ua_mw_k"])
    assert len(v) == 4 and v["pass"].all()


def test_deeper_wells_cut_purchased_gas():
    shallow = run_year(PlantDesign("s", 2, electric_chiller_mw=10), A)[1]
    deep = run_year(PlantDesign("d", 2, WellDesign(3000), electric_chiller_mw=10), A)[1]
    assert deep["heating_natural_gas_gwh"] < 0.1 * shallow["heating_natural_gas_gwh"]


# ---------------------------------------------------------------- GEMINI issues (these tests document the bugs;
# they will fail once GEMINI is fixed, which is the point)
def test_gemini_issue_hx_moves_heat_from_cold_to_hot():
    hx = HeatExchanger()
    hx.update_parameters({"flow_resistance": 0, "flow_configuration": "counter", "heat_transfer_coefficient": 5e6,
                          "fluid_density": 1030, "specific_heat": 4000})
    hx.calculate_output({"pressure_in": 7, "primary_flow_rate": 0.067, "secondary_flow_rate": 0.015,
                         "primary_temperature_in": 47.0, "secondary_temperature_in": 55.0})
    o = hx.get_output()
    assert o["primary_temperature_out"] < 47.0 and o["secondary_temperature_out"] > 55.0  # second law violated


def test_gemini_issue_heatpump_constrained_branch_nonsense():
    hp = HeatpumpBasic()
    hp.update_parameters({"mode": "lorenz", "eta_lorenz": 0.5, "Th_out_target": 80.0, "Ts_in_minimum": 43.1,
                          "Cp_h": 4000, "Cp_s": 4000, "rho_h": 1030, "rho_s": 1030})
    with np.errstate(all="ignore"):
        hp.calculate_output({"Th_in": 55.0, "Ts_in": 47.0, "hot_flow_rate": 0.015, "source_flow_rate": 0.067})
    o = hp.get_output()
    assert o["COP"] < 1.1 and o["Th_out"] > 500  # physically impossible output
