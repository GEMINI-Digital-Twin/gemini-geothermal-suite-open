"""Tests for doublet operating memory (commitment, warm-up) and the gas bubble point."""

import math
from pathlib import Path

import pytest

from gemini_design.annual import run_year
from gemini_design.challenge import load_demand
from gemini_design.doublet import DoubletHydraulics
from gemini_design.gas_solubility import bubble_point_bar, henry_constant_bar
from gemini_design.operations import (
    OperatingRules,
    WellboreModel,
    WellboreThermalState,
    commit,
    time_function,
)
from gemini_design.plant import Design

INPUTS = Path(__file__).resolve().parents[2] / "simulator_examples" / "hackathon_inputs"


def test_henry_constant_matches_iapws_magnitude():
    """CH4 in water at 100 degC: kH about 6.4e4 bar (IAPWS G7-04); CO2 about 5e3 bar."""
    assert 5.0e4 < henry_constant_bar("ch4", 105.0) < 8.0e4
    assert 4.0e3 < henry_constant_bar("co2", 105.0) < 7.0e3


def test_bubble_point_is_above_the_old_esp_intake_floor():
    """0.8 Nm3/m3 of mostly methane bubbles out near 40 bar, above the 20 bar floor."""
    p = bubble_point_bar(105.0)["bubble_point_bar"]
    assert 35.0 < p < 50.0
    hyd = DoubletHydraulics(3100.0)
    prod = hyd.producer(150.0)
    assert hyd.esp_intake_min_bar == pytest.approx(p + 5.0, rel=1e-3)
    assert prod["esp_intake_ok"]
    assert 200.0 < prod["gas_breakout_depth_m"] < 400.0
    # the pump hangs deep enough that its intake sees the bubble point plus margin
    rho_g = 1030.0 * 9.80665
    intake = prod["bottomhole_pressure_bar"] - (3100.0 - prod["esp_depth_m"]) * rho_g / 1e5
    assert intake == pytest.approx(hyd.esp_intake_min_bar, abs=0.01)


def test_time_function_is_continuous_and_increasing():
    """Hasan-Kabir f(tD) branches meet within 3 % at tD = 1.5; f grows with time."""
    assert time_function(1.5 - 1e-9) == pytest.approx(time_function(1.5 + 1e-9), rel=0.03)
    values = [time_function(t) for t in (0.1, 1.0, 10.0, 100.0, 1000.0)]
    assert values == sorted(values)


def test_heat_loss_falls_with_time_and_recovers_after_a_stop():
    """A young well loses more heat; a long stop resets most of the warm-up."""
    m = WellboreModel()
    assert m.multiplier(0.5) > m.multiplier(7) > m.multiplier(365)
    short = m.restart_age_days(365.0, 1.0)
    long = m.restart_age_days(365.0, 60.0)
    assert long < short < 365.0
    assert m.restart_age_days(365.0, 0.0) == pytest.approx(365.0, rel=1e-3)


def test_thermal_state_counts_starts_and_prefers_running_doublets():
    """Running doublets keep running; a restart shows a larger heat loss."""
    state = WellboreThermalState(2, OperatingRules())
    day0 = state.step(1, [True, True])
    assert day0["running"] == [0] and day0["starts"] == 0
    for _ in range(30):
        state.step(1, [True, True])
    restart = state.step(2, [True, True])
    assert restart["starts"] == 1
    steady = WellboreModel().multiplier(365.0)
    assert restart["heat_loss_multiplier"] > steady


def test_commit_avoids_flip_flop():
    """A one-day saving does not pay for a start; min run/stop times hold."""
    inf = math.inf
    # running two doublets is a bit cheaper on alternating days only
    scores = [[inf, 100.0, 95.0 if i % 2 else 105.0] for i in range(30)]
    plan, breaks = commit(scores, [2] * 30, OperatingRules(start_cost_eur=50.0))
    changes = sum(1 for a, b in zip(plan, plan[1:]) if a != b)
    assert breaks == 0
    assert changes <= 1  # one free stop can pay; no start-stop cycling
    # without rules the daily optimum flips every day
    free, _ = commit(scores, [2] * 30, OperatingRules(0, 0, 0.0))
    assert sum(1 for a, b in zip(free, free[1:]) if a != b) > 20


def test_commit_allows_forced_outage_drop():
    """An outage forces a drop even inside the minimum run time."""
    inf = math.inf
    scores = [[inf, 10.0, 5.0]] * 3 + [[inf, 10.0, inf]] * 3
    plan, breaks = commit(scores, [2, 2, 2, 1, 1, 1], OperatingRules())
    assert plan == [2, 2, 2, 1, 1, 1]
    assert breaks == 0


def test_run_year_with_operations_reduces_starts():
    """The pick runs with few doublet starts and reports its operating KPIs."""
    demand = load_demand(INPUTS)
    design = Design(2, 3100.0, "boiler", "electric", chiller_capacity_mw=12.0)
    base, _ = run_year(design, demand)
    daily, summary = run_year(design, demand, operations=OperatingRules())
    base_changes = int((base["n_active"].diff().fillna(0) != 0).sum())
    ops = summary["operations"]
    assert ops["doublet_starts"] < base_changes
    assert ops["commitment_rule_breaks"] == 0
    assert summary["checks"]["min_run_stop_times_respected"]
    assert summary["all_hard_constraints_met"]
    assert summary["economics"]["annual_start_cost_eur"] == ops["doublet_starts"] * 10_000.0
    # a restart day shows a colder wellhead than the steady days around it
    restart = daily.index[daily["doublet_starts"] > 0]
    assert len(restart) > 0
    assert daily.loc[restart, "heat_loss_multiplier"].max() > ops["steady_heat_loss_multiplier"]
