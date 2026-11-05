"""Tests for the exploration tools (compare_runs, log_option) and scenario 09."""

import pytest

from gemini_agent.agent import DesignAgent
from gemini_agent.config import AgentConfig
from gemini_agent.llm import ScriptedLLM
from gemini_agent.memory import ProjectNotes, RunLedger
from gemini_agent.scenarios import (
    PICK_CHP,
    SCENARIOS,
    THERMAL_STORAGE_CODE,
    THERMAL_STORAGE_TESTS,
    check_behaviour,
    scripted_steps,
)
from gemini_agent.tools import ToolBox
from gemini_design.challenge import load_demand
from gemini_design.storage import STORAGE_TYPE
from gemini_simulator.registry import COMPONENT_REGISTRY

INPUTS = "simulator_examples/hackathon_inputs"


@pytest.fixture(scope="module")
def toolbox(tmp_path_factory):
    """One ToolBox (workspace, ledger, notes) shared by the tests in this module."""
    ws = tmp_path_factory.mktemp("ws")
    return ToolBox(load_demand(INPUTS), RunLedger(ws), ProjectNotes(ws), ws, workers=1)


@pytest.fixture(autouse=True)
def empty_storage_slot():
    """Start and end every test with no thermal_storage model registered."""
    COMPONENT_REGISTRY.pop(STORAGE_TYPE, None)
    yield
    COMPONENT_REGISTRY.pop(STORAGE_TYPE, None)


def test_compare_and_log_options(toolbox):
    """compare_runs labels a dominated option; log_option gates verdicts and reasons."""
    base = toolbox.call("run_design", PICK_CHP)["run_id"]
    three = toolbox.call("run_design", {**PICK_CHP, "n_doublets": 3})["run_id"]
    cmp = toolbox.call("compare_runs", {"run_id": three, "baseline_run_id": base})
    assert cmp["pareto"].startswith("dominated") and cmp["delta"]["capex_meur"] > 0

    log = {"option": "three doublets", "run_id": three, "baseline_run_id": base}
    refused = toolbox.call("log_option", {**log, "verdict": "accept", "reason": "More is better."})
    assert "cannot accept" in refused["error"]
    invented = toolbox.call(
        "log_option", {**log, "verdict": "reject", "reason": "It costs 77.7 EUR/MWh more."}
    )
    assert "physics gate 6" in invented["error"]
    d = cmp["delta"]["lcoe_eur_per_mwh"]
    ok = toolbox.call(
        "log_option", {**log, "verdict": "reject", "reason": f"LCOE {d:+.2f} EUR/MWh, no gain."}
    )
    assert ok["logged"] == 1
    assert (toolbox.workspace / "exploration.md").read_text().count("three doublets") == 1
    assert toolbox.call("memory_read", {})["exploration"][0]["verdict"] == "reject"


def test_storage_option_needs_the_agent_written_model(toolbox):
    """A storage design fails until the agent writes the model, then runs and passes the gate."""
    args = {**PICK_CHP, "n_doublets": 1, "storage_mwh": 25000, "storage_mw": 12}
    missing = toolbox.call("run_design", args)
    assert "MissingModelError" in missing["error"] and "write_model" in missing["error"]
    assert "EMPTY" in toolbox.call("list_models", {})["model_slots"][STORAGE_TYPE]
    written = toolbox.call(
        "write_model",
        {
            "name": "thermal_storage",
            "register_as": "thermal_storage",
            "code": THERMAL_STORAGE_CODE,
            "test_code": THERMAL_STORAGE_TESTS,
        },
    )
    assert written["ok"]
    run = toolbox.call("run_design", args)
    assert run["physics_gate"] == "pass" and run["meets_all_hard_rules"]
    assert run["storage_discharge_mwh"] > 0


def test_scripted_exploration_scenario(tmp_path):
    """Scenario 09 runs end to end: options logged, model written, no gate rejections."""
    cfg = AgentConfig.load(env={}, workspace=str(tmp_path), screen_workers=1)
    agent = DesignAgent(
        cfg, llm=ScriptedLLM(scripted_steps("09_explore_ambitious")), inputs_dir=INPUTS
    )
    replies = [agent.ask(t) for t in SCENARIOS["09_explore_ambitious"]["turns"]]
    assert check_behaviour("09_explore_ambitious", replies, agent.transcript.events) == []
    assert not any(e["kind"] == "gate_reject" for e in agent.transcript.events)
    log = agent.tools.exploration.entries
    assert len(log) == 9 and {e["verdict"] for e in log} <= {"accept", "alternative", "reject"}
    assert "exploration log" in replies[-1].text
