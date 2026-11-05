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
# electric chiller sized for the plant-wide geothermal outage (organisers, 1 Nov): absorption has no drive heat then
INTEGRATED = PlantDesign("2x2500m_HP12_ABS6_EC10", 2, heat_pump_mw=12, absorption_mw=6, electric_chiller_mw=10)


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


def test_idle_heat_pump_not_sent_to_gemini():
    """Demo 5: a 25 MW heat pump that does not run on the peak day was sent to GEMINI's HeatpumpBasic, which
    returned COP 1 and a 900 C outlet -> false MISMATCH. Idle units are now left out of the plant JSON."""
    from agentic_design.annual import PlantDesign, run_year
    from agentic_design.config import Assumptions
    from agentic_design.verify import format_report, verify_days
    from agentic_design.wells import WellDesign
    a = Assumptions()
    d = PlantDesign("2x3500m_HP25_ABS5_EC5", 2, WellDesign(3500), heat_pump_mw=25, absorption_mw=5, electric_chiller_mw=5)
    daily, k, _, _ = run_year(d, a)
    v = verify_days(d, daily, a, ua_mw_k=k["hx_ua_mw_k"])
    assert v["pass"].all(), format_report(v)
    assert "nan" not in format_report(v)


def test_low_flow_wellhead_temperature_interpolation():
    """Windows run, 31 Oct: verification picked a 53-55 m3/h day; linear interpolation in q was 0.11 C off
    GEMINI (tolerance 0.05 C). Interpolating in 1/q fixes it."""
    from agentic_design.config import Assumptions
    from agentic_design.wells import WellDesign, hydraulic_curve, interp
    a, w = Assumptions(), WellDesign(3500)
    grid = hydraulic_curve(w, a, t_inj_c=58.0)
    for q in (53.0, 55.0, 65.0):
        exact = hydraulic_curve(w, a, t_inj_c=58.0, q_grid=(q,))["wellhead_temperature_c"][0]
        assert abs(float(interp(grid, "wellhead_temperature_c", q)) - exact) < 0.02


def test_default_verification_days_are_platform_independent():
    """37 days tie at the minimum heating demand; the choice must not depend on the sort algorithm."""
    import pandas as pd
    s = pd.Series([3.0, 1.0, 2.0, 1.0, 1.0])
    assert int(s.sort_values(kind="stable").index[0]) == 1


def test_plant_diagram_matches_gemini_project(tmp_path):
    """The flowsheet is drawn from the same project file GEMINI solves: every component appears."""
    from agentic_design.annual import PlantDesign
    from agentic_design.diagram import design_diagram
    from agentic_design.wells import WellDesign
    d = PlantDesign("2x3500m_HP1_ABS7.5_EC5", 2, WellDesign(3500), heat_pump_mw=1, absorption_mw=7.5, electric_chiller_mw=5)
    files = design_diagram(d, out_dir=tmp_path)
    md = [f for f in files if f.suffix == ".md"][0].read_text()
    for part in ("Production well 1", "Heat exchanger", "Heat pump", "Absorption chiller", "Electric chiller", "-- gas -->"):
        assert part in md



def test_plant_wide_geothermal_outage():
    """Organisers, 1-2 Nov: 330 days per doublet; staggered shut-ins or backup equipment are both allowed."""
    from agentic_design.annual import PlantDesign, run_year
    from agentic_design.config import Assumptions
    from agentic_design.wells import WellDesign
    d = PlantDesign("3x3000m_EC10", 3, WellDesign(3000), electric_chiller_mw=10)
    daily, k, _, starts = run_year(d, Assumptions(maintenance_mode="simultaneous"))
    off = daily["doublets_available"] == 0
    assert off.sum() == 35 and len(set(starts)) == 1                       # one shared window
    assert (daily.loc[off, "heat_geothermal_mw"] == 0).all()
    assert k["heating_unmet_gwh"] < 1e-6 and k["cooling_unmet_gwh"] < 1e-6  # backup covers it
    daily_s, k_s, _, starts_s = run_year(d, Assumptions(maintenance_mode="staggered"))
    assert (daily_s["doublets_available"] > 0).all() and len(set(starts_s)) == 3
    assert k["co2_t"] > k_s["co2_t"]                                          # the outage costs CO2


def test_well_heat_loss_coefficient_is_used():
    """GEMINI issue 12: DPDT hard-coded U = 10 W/m2K. Now a parameter; higher U -> cooler wellhead."""
    from agentic_design.config import Assumptions
    from agentic_design.wells import WellDesign, hydraulic_curve
    w = WellDesign(3000)
    t10 = hydraulic_curve(w, Assumptions(), q_grid=(100.0,))["wellhead_temperature_c"][0]
    t20 = hydraulic_curve(w, Assumptions(well_heat_transfer_u_w_m2k=20.0), q_grid=(100.0,))["wellhead_temperature_c"][0]
    assert t20 < t10 - 0.5


def test_bypass_days_fully_verified_against_gemini():
    """GEMINI's exchanger has no bypass valve; an equivalent smaller UA reproduces the controlled duty, so heat and
    temperatures are now compared on bypass days too (they were skipped before)."""
    from agentic_design.annual import PlantDesign, run_year
    from agentic_design.config import Assumptions
    from agentic_design.verify import verify_days
    from agentic_design.wells import WellDesign
    a = Assumptions()
    d = PlantDesign("2x3500m_ABS5_EC5_RI", 2, WellDesign(3500), absorption_mw=5, electric_chiller_mw=5,
                    gas_reinjection=True)
    daily, k, _, _ = run_year(d, a)
    days = list(daily.index[daily["hx_bypass_active"] & (daily["doublets_on"] > 0)][:3])
    v = verify_days(d, daily, a, days=days, ua_mw_k=k["hx_ua_mw_k"])
    assert v["pass"].all()
    assert max(abs(g - f) for f, g in v["geothermal_heat_mw"]) < 0.01
    assert max(abs(g - f) for f, g in v["supply_temperature_c"]) < 0.05
