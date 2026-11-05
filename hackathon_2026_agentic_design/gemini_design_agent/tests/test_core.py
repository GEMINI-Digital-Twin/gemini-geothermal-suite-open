"""Unit tests for the design agent (run: python -m pytest tests -q)."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gemini_design_agent.components import AbsorptionChiller, HeatPump, brine_heat_capacity_mw_per_k  # noqa: E402
from gemini_design_agent.demand import DemandProfile, load_demand  # noqa: E402
from gemini_design_agent.spec import SPEC  # noqa: E402
from gemini_design_agent.subsurface import DoubletModel, WellDesign  # noqa: E402
from gemini_design_agent.system import Plant, SystemDesign, evaluate_design, schedule_maintenance  # noqa: E402

DATA = ROOT.parent


def _demand():
    h = DATA / "GEMINI_Heating_Demand_Daily_2027.csv"
    c = DATA / "GEMINI_Cooling_Demand_Daily_2027.csv"
    if h.exists() and c.exists():
        return load_demand(h, c)
    dates = pd.date_range("2027-01-01", periods=365, freq="D")
    x = np.arange(365)
    heat = 16 + 14 * np.cos(2 * np.pi * (x - 27) / 365)
    cool = np.clip(10 * np.cos(2 * np.pi * (x - 200) / 365) - 2, 0, None)
    return DemandProfile(dates, heat, cool)


def test_spec_temperature_and_pressure():
    assert SPEC.reservoir.temperature_at_depth(2500) == 87.0
    assert abs(SPEC.reservoir.pressure_at_depth(2500) - 250.0) < 1e-9
    assert SPEC.reservoir.pressure_at_depth(3500) > 250.0


def test_brine_capacity():
    # 300 m3/h x 1030 kg/m3 x 3.9 kJ/kgK x 40 K ~ 13.4 MW
    assert abs(brine_heat_capacity_mw_per_k(300) * 40 - 13.39) < 0.05


def test_heat_pump_cop_decreases_with_lift():
    hp = HeatPump(capacity_mw_th=10)
    assert hp.cop(80, 100) > hp.cop(50, 100) > 1.5


def test_absorption_cop_envelope():
    ab = AbsorptionChiller(capacity_mw_cool=10)
    assert ab.cop(60) == 0.0
    assert ab.cop(110) == ab.cop_nominal
    assert 0 < ab.cop(80) < ab.cop_nominal


def test_doublet_model_hard_caps():
    dm = DoubletModel(WellDesign())
    w = dm.evaluate(300.0)
    assert 80 < w.wellhead_temperature_c < 87
    assert w.esp_intake_pressure_bar > w.bubble_point_bar
    assert w.esp_head_bar > 0 and w.esp_power_mw > 0
    assert w.injection_whp_bar < SPEC.constraints.max_wellhead_pressure_bar
    assert w.tubing_velocity_m_s < w.erosional_velocity_m_s


def test_deeper_is_hotter():
    t1 = DoubletModel(WellDesign(reservoir_midpoint_m=2500)).evaluate(250).wellhead_temperature_c
    t2 = DoubletModel(WellDesign(reservoir_midpoint_m=3500)).evaluate(250).wellhead_temperature_c
    assert t2 > t1 + 20


def test_plant_respects_40c_cap():
    ds = SystemDesign(n_doublets=2, heat_pump_mw=40, absorption_chiller_mw=10)
    st = Plant(ds).dispatch(600, 113.0, 30.0, 10.0)
    assert st.brine_dt_c <= 40.0 + 1e-6
    assert st.unmet_heat_mw + st.unmet_cool_mw < 15.0


def test_maintenance_windows_do_not_overlap():
    d = _demand()
    starts = schedule_maintenance(d, 3, 35)
    assert len(starts) == 3
    for a, b in zip(starts, starts[1:]):
        assert b - a >= 35


def test_single_doublet_is_infeasible_because_of_330_days():
    d = _demand()
    r = evaluate_design(SystemDesign(n_doublets=1, heat_pump_mw=35, electric_chiller_mw=10), d, fast=True)
    assert not r.feasible
    assert any(v.code == "no_doublet_available" for v in r.violations)


def test_full_evaluation_feasible_design():
    d = _demand()
    ds = SystemDesign(n_doublets=3, well=WellDesign(reservoir_midpoint_m=3500), heat_pump_mw=8,
                      absorption_chiller_mw=10, electric_chiller_mw=0)
    r = evaluate_design(ds, d, fast=True)
    assert r.kpis["peak_flow_per_doublet_m3_h"] <= 300.0 + 1e-6
    assert r.kpis["max_brine_dt_c"] <= 40.0 + 1e-6
    assert r.kpis["unmet_heat_gwh"] < 1e-6 and r.kpis["unmet_cool_gwh"] < 1e-6
    assert r.feasible
    assert r.cost["levelised_cost_eur_per_mwh"] > 0
