"""Tests for the daily flowsheet, dispatch, outage schedule and GEMINI cross-check."""

import warnings

import pandas as pd
import pytest

from gemini_design.annual import dispatch_day, run_year, schedule_outages
from gemini_design.doublet import DoubletHydraulics
from gemini_design.plant import Design, Plant
from gemini_design.project_json import cross_check

DESIGNS = [
    Design(2, 2500.0, "boiler", "absorption", boiler_capacity_mw=30, electric_backup_mw=5),
    Design(2, 2500.0, "heat_pump", "absorption", heat_pump_capacity_mw=10, electric_backup_mw=5),
    Design(2, 3100.0, "boiler", "electric"),
]
DAYS = [(30e6, 0.0), (3e6, 10e6), (15e6, 3e6)]


@pytest.fixture(autouse=True)
def _quiet():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        yield


@pytest.mark.parametrize("design", DESIGNS, ids=lambda d: d.name)
def test_dispatch_meets_demand_within_hard_caps(design):
    """Every dispatched day meets demand, stays in 50-300 m3/h and cools brine <= 40 K."""
    plant = Plant(design, DoubletHydraulics(design.depth_m))
    for heating, cooling in DAYS:
        r = dispatch_day(plant, heating, cooling, design.n_doublets)
        assert r["violations"] == []
        assert r["unmet_heat_w"] == pytest.approx(0.0, abs=1.0)
        assert r["unmet_cooling_w"] == pytest.approx(0.0, abs=1.0)
        if r["n_active"]:
            assert 50.0 <= r["flow_per_doublet_m3h"] <= 300.0
            assert r["brine_cooling_k"] <= 40.0 + 1e-6
        # district heating energy balance: HEX + heat pump + boiler = delivered heat
        supplied = r["hex_heat_w"] + r["heat_pump_heat_w"] + r["boiler_heat_w"]
        assert supplied == pytest.approx(r["heat_delivered_w"], rel=1e-3)


@pytest.mark.parametrize("design", DESIGNS, ids=lambda d: d.name)
def test_gemini_solver_cross_check(design):
    """The dispatched peak day, rebuilt as project JSON and run by GEMINI's Solver, agrees."""
    hydraulics = DoubletHydraulics(design.depth_m)
    plant = Plant(design, hydraulics)
    r = dispatch_day(plant, 30e6, 0.0, design.n_doublets)
    _, check = cross_check(design, hydraulics, r)
    assert check["agrees"], check


def test_outages_respect_330_days_and_do_not_overlap():
    """Each doublet is off 35 contiguous days, never two at once."""
    demand = pd.DataFrame(
        {
            "date": pd.date_range("2027-01-01", periods=365),
            "heating_mw": [10.0 + (i % 50) for i in range(365)],
            "cooling_mw": [0.0] * 365,
        }
    )
    available = schedule_outages(demand, Design(3, 2500.0))
    assert (available.sum(axis=0) == 330).all()
    assert (available.sum(axis=1) >= 2).all()


def test_short_year_runs_and_reports_checks():
    """A 365-day run on a flat demand reports every check as met."""
    demand = pd.DataFrame(
        {
            "date": pd.date_range("2027-01-01", periods=365),
            "heating_mw": [12.0] * 365,
            "cooling_mw": [2.0] * 365,
        }
    )
    design = Design(2, 2500.0, "boiler", "electric", boiler_capacity_mw=15, chiller_capacity_mw=3)
    daily, summary = run_year(design, demand)
    assert len(daily) == 365
    assert summary["all_hard_constraints_met"], summary["checks"]
    assert summary["kpi"]["doublet_operating_days"] == [330, 330]
