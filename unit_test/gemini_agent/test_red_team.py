"""Tests for the physics-gate red team and the unit-binding check (gate 6b)."""

import pytest

from gemini_agent.memory import ProjectNotes, RunLedger
from gemini_agent.physics_gate import check_answer, check_units, unit_claims
from gemini_agent.red_team import (
    brief_sources,
    clean_answer,
    run_answer_trials,
    run_arg_trials,
    run_daily_trials,
    score,
)
from gemini_agent.tools import ToolBox
from gemini_design.challenge import load_demand

INPUTS = "simulator_examples/hackathon_inputs"


def test_unit_claims_parse_units_and_scale():
    """Unit claims parse units and scale."""
    claims = unit_claims("LCOE 33.8 EUR/MWh, 5.4 kt CO2, 4,675 MWh, 0.04 EUR/kWh, 300 m3/h")
    fams = [(f, round(x, 3)) for f, x, _ in claims]
    assert ("eur_per_mwh", 33.8) in fams
    assert ("t", 5400.0) in fams
    assert ("mwh", 4675.0) in fams
    assert ("eur_per_mwh", 40.0) in fams
    assert ("m3h", 300.0) in fams
    assert unit_claims("at 5 /MWh") == []  # no currency, not a price


def test_unit_binding_catches_a_number_moved_to_the_wrong_quantity():
    """Unit binding catches a number moved to the wrong quantity."""
    evidence = [{"lcoe_eur_per_mwh": 33.85, "max_brine_cooling_k": 40.0, "co2_t_per_year": 5363}]
    assert check_units("LCOE 33.9 EUR/MWh and 40.0 K [R0001]", evidence, []) == []
    assert check_units("LCOE 40.0 EUR/MWh and 33.9 K [R0001]", evidence, [])
    assert check_units("CO2 5,363 kt/yr [R0001]", evidence, [])


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    """Run two designs through the ToolBox and plant one gate-failed ledger entry."""
    ws = tmp_path_factory.mktemp("rt")
    ledger, notes = RunLedger(ws), ProjectNotes(ws)
    tb = ToolBox(load_demand(INPUTS), ledger, notes, ws, workers=1)
    out = []
    for d in (
        {"n_doublets": 2, "depth_m": 3100, "upgrade": "boiler", "cooling": "electric", "chp": True},
        {"n_doublets": 1, "depth_m": 2800, "upgrade": "boiler", "cooling": "electric"},
    ):
        head = tb.call("run_design", d)
        assert head["physics_gate"] == "pass"
        out.append((head["run_id"], {k: v for k, v in head.items() if k != "run_id"}))
    failed = ledger.add("design", "planted", {}, {"design": "x"}, {"passed": False})
    return out, ledger, failed, tb


def test_clean_answers_pass_and_faults_are_caught(runs):
    """Clean answers pass and faults are caught."""
    out, ledger, failed, _ = runs
    for run_id, head in out:
        assert (
            check_answer(
                clean_answer(run_id, head),
                [head, ledger.summary(run_id)],
                brief_sources("design it"),
                ledger,
            )
            == []
        )
    res = run_answer_trials(out, ledger, failed, trials=20, seed=1)
    assert res["clean"]["rejected"] == 0
    for name in ("unknown_run_cited", "gate_failed_run_cited", "no_run_cited"):
        assert res[name]["rejected"] == res[name]["n"] > 0
    t = score(res)
    assert t["designed_caught"] >= 0.9 * t["designed_faults"]


def test_daily_and_argument_faults(runs):
    """Daily and argument faults."""
    out, ledger, _, tb = runs
    res = run_daily_trials(out, ledger, trials=10, seed=1)
    assert res["clean"]["rejected"] == 0
    for name in ("chiller_cop_above_carnot", "flow_320_m3h", "supply_above_100C"):
        assert res[name]["rejected"] == res[name]["n"] > 0
    args = run_arg_trials(tb)
    assert args["clean"]["rejected"] == 0
    assert all(r["rejected"] for k, r in args.items() if k != "clean")
