"""Tests for the ORC power unit in the plant, the dispatcher and the physics gate."""

import warnings

import pandas as pd
import pytest

from gemini_agent.physics_gate import check_energy_balance, check_sanity
from gemini_design.annual import dispatch_day
from gemini_design.doublet import DoubletHydraulics
from gemini_design.plant import Design, Plant
from gemini_design.project_json import cross_check

ORC = Design(2, 3100.0, "boiler", "electric", chp_capacity_mw_el=1.1, orc_capacity_mw_el=1.0)
NO_ORC = Design(2, 3100.0, "boiler", "electric", chp_capacity_mw_el=1.1)


@pytest.fixture(autouse=True)
def _quiet():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        yield


def _day(design, heating, cooling=0.0, air=12.0):
    plant = Plant(design, DoubletHydraulics(design.depth_m))
    return dispatch_day(plant, heating, cooling, 2, ambient_c=air + 4, ambient_mean_c=air)


def test_name_and_validation():
    """The design name says ORC; a negative rating is refused."""
    assert ORC.name.endswith("-orc1")
    with pytest.raises(ValueError):
        Design(2, 3100.0, "boiler", "electric", orc_capacity_mw_el=-1.0)


def test_orc_runs_on_spare_summer_heat_within_caps():
    """Low heat demand: the ORC makes power, the brine stays within the 40 K cap."""
    r = _day(ORC, 3.5e6, 5e6)
    assert r["violations"] == []
    assert r["unmet_heat_w"] == pytest.approx(0.0, abs=1.0)
    assert r["orc_power_el_w"] > 0
    assert r["brine_cooling_k"] <= 40.0 + 1e-6
    assert r["orc_power_el_w"] <= 1.0e6 + 1.0
    # grid balance includes the ORC's power
    assert r["grid_import_w"] - r["grid_export_w"] == pytest.approx(
        r["electricity_w"] - r["chp_power_el_w"] - r["orc_power_el_w"], abs=1.0
    )


def test_district_heat_comes_first_at_peak():
    """On the 30 MW peak the district takes the whole 40 K: the ORC gets nothing."""
    r = _day(ORC, 30e6, air=-2.0)
    base = _day(NO_ORC, 30e6, air=-2.0)
    assert r["orc_power_el_w"] == pytest.approx(0.0, abs=1.0)
    assert r["boiler_heat_w"] == pytest.approx(base["boiler_heat_w"], rel=1e-6, abs=1.0)


def test_gate_balances_and_sanity_pass_with_orc():
    """Gate 3 (brine and grid balances with ORC terms) and gate 5 pass on ORC days."""
    rows = [_day(ORC, h, c) for h, c in ((3.5e6, 5e6), (12e6, 2e6), (28e6, 0.0))]
    for r in rows:
        r["violations"] = ""
    daily = pd.DataFrame(rows)
    assert check_energy_balance(daily) == []
    assert check_sanity(daily, 105.0) == []
    bad = daily.copy()
    bad.loc[bad["orc_power_el_w"] > 0, "orc_efficiency"] = 0.5
    assert any("ORC efficiency above Carnot" in e for e in check_sanity(bad, 105.0))
    bad = daily.copy()
    bad["orc_heat_w"] *= 1.2
    assert any("brine heat" in e for e in check_energy_balance(bad))


def test_solver_cross_check_with_orc():
    """GEMINI's Solver agrees on an ORC day (it is compared at the ORC inlet)."""
    hyd = DoubletHydraulics(ORC.depth_m)
    r = _day(ORC, 3.5e6, 5e6)
    _, check = cross_check(ORC, hyd, r)
    assert check["agrees"], check


def test_geothermal_share_excludes_orc_heat():
    """Brine heat the ORC turns into power is not district heat: the share stays <= 100 %."""
    import numpy as np

    from gemini_design.annual import run_year
    from gemini_design.challenge import load_demand

    demand = load_demand("simulator_examples/hackathon_inputs")
    demand["ambient_c"] = 15.0 + 8.0 * np.cos(2 * np.pi * (np.arange(365) - 200) / 365.0)
    deep = Design(2, 4000.0, "boiler", "electric", chp_capacity_mw_el=1.1, orc_capacity_mw_el=2.0)
    daily, summary = run_year(deep, demand)
    e = summary["energy_mwh"]
    district = e["heating_delivered"] + e["absorption_drive_heat"]
    assert e["geothermal_heat"] > district  # counting the ORC's heat would exceed 100 %
    assert summary["kpi"]["geothermal_share_of_heat"] <= 1.0
    assert summary["kpi"]["geothermal_share_of_heat"] == pytest.approx(
        (e["geothermal_heat"] - e["orc_heat"]) / district
    )
