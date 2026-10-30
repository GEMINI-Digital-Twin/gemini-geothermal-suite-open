"""Tests for the physics gate (checks 2-6)."""

import warnings

import pytest

from gemini_agent.memory import RunLedger
from gemini_agent.physics_gate import (
    check_answer,
    check_energy_balance,
    check_run,
    check_sanity,
    extract_numbers,
)
from gemini_design.annual import run_year
from gemini_design.challenge import load_demand
from gemini_design.plant import Design

INPUTS = "simulator_examples/hackathon_inputs"


@pytest.fixture(scope="module")
def year():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        demand = load_demand(INPUTS)
        daily, summary = run_year(Design(2, 3100.0, "boiler", "electric"), demand)
    return daily, summary


def test_valid_run_passes(year):
    daily, summary = year
    gate = check_run(summary, daily)
    assert gate["passed"], gate
    assert gate["2_hard_rules"] == "pass"


def test_broken_energy_balance_is_caught(year):
    daily, _ = year
    bad = daily.copy()
    bad.loc[10, "hex_heat_w"] *= 1.05  # 5 % heat from nowhere
    errors = check_energy_balance(bad)
    assert errors and "day 11" in errors[0]


def test_cop_above_carnot_is_caught(year):
    daily, summary = year
    bad = daily.copy()
    bad.loc[200, "electric_chiller_cop"] = 40.0  # Carnot at 20/30 degC is ~29
    errors = check_sanity(bad, summary["reservoir"]["temperature_c"])
    assert any("Carnot" in e for e in errors)


def test_heat_created_in_the_brine_is_caught(year):
    daily, summary = year
    bad = daily.copy()
    i = bad.index[bad["n_active"] > 0][0]
    bad.loc[i, "injection_temperature_c"] = bad.loc[i, "wellhead_temperature_c"] + 5
    assert any("heat created" in e for e in check_sanity(bad, 105.0))


def test_extract_numbers_skips_ids_and_formulas():
    nums = [v for v, _ in extract_numbers("2 doublets [R0012] emit 5,824 t CO2 in m3 at 36.17")]
    assert nums == [2.0, 5824.0, 36.17]


def test_answer_numbers_must_trace_to_runs(tmp_path):
    ledger = RunLedger(tmp_path)
    run_id = ledger.add("design", "k", {}, {"lcoe_eur_per_mwh": 36.17}, {"passed": True})
    evidence = ['{"run_id":"%s","lcoe_eur_per_mwh":36.17,"co2_t_per_year":5824.0}' % run_id]
    brief = ["heating peak 30.0 MW"]
    ok = f"It costs 36.2 EUR/MWh and emits 5.8 kt CO2 [{run_id}]."
    assert check_answer(ok, evidence, brief, ledger) == []
    invented = f"It costs 36.2 EUR/MWh, gas only would be 55 EUR/MWh [{run_id}]."
    assert "55" in check_answer(invented, evidence, brief, ledger)[0]
    uncited = "It costs 36.2 EUR/MWh."
    assert "cites no run id" in check_answer(uncited, evidence, brief, ledger)[0]
    assert check_answer("Peak heating is 30 MW.", evidence, brief, ledger) == []
    assert "unknown run" in check_answer("See [R0999].", evidence, brief, ledger)[0]


def test_invalid_run_can_not_be_cited(tmp_path):
    ledger = RunLedger(tmp_path)
    run_id = ledger.add("design", "k", {}, {}, {"passed": False})
    errors = check_answer(f"See [{run_id}].", [], [], ledger)
    assert "failed the physics gate" in errors[0]
