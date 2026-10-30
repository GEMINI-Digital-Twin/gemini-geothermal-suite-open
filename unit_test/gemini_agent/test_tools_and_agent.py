"""Tests for the agent tools, model sandbox, memory and the agent loop (scripted LLM)."""

import json

import pytest

from gemini_agent.agent import DesignAgent
from gemini_agent.config import AgentConfig
from gemini_agent.llm import ScriptedLLM
from gemini_agent.memory import ProjectNotes, RunLedger
from gemini_agent.sandbox import static_check
from gemini_agent.scenarios import DRY_COOLER_CODE, DRY_COOLER_TESTS, SCENARIOS, scripted_steps
from gemini_agent.tools import ToolBox, split_overrides, validate_arguments
from gemini_design.challenge import load_demand
from gemini_simulator.registry import COMPONENT_REGISTRY

INPUTS = "simulator_examples/hackathon_inputs"
PICK = {"n_doublets": 2, "depth_m": 3100, "upgrade": "boiler", "cooling": "electric"}


@pytest.fixture(scope="module")
def toolbox(tmp_path_factory):
    ws = tmp_path_factory.mktemp("ws")
    return ToolBox(load_demand(INPUTS), RunLedger(ws), ProjectNotes(ws), ws, workers=1)


def _agent(tmp_path, steps):
    cfg = AgentConfig.load(env={}, workspace=str(tmp_path), screen_workers=1)
    return DesignAgent(cfg, llm=ScriptedLLM(steps), inputs_dir=INPUTS, session_name="t")


def test_gate1_rejects_bad_arguments():
    errors = validate_arguments("run_design", {"n_doublets": 4, "depth_m": 3100, "cooling": "x"})
    text = " ".join(errors)
    assert "above the maximum 3" in text and "missing argument 'upgrade'" in text
    assert "must be one of" in text
    assert validate_arguments("launch_rocket", {})[0].startswith("unknown tool")
    assert validate_arguments("run_design", {**PICK, "chp": "yes"})


def test_overrides_are_range_checked():
    challenge, assumptions, scale = split_overrides(
        {"heating_return_c": 50, "permeability_md": 100}
    )
    assert assumptions["heating_return_c"] == 50 and challenge["permeability_md"] == 100
    with pytest.raises(Exception):
        split_overrides({"heating_return_c": 120})
    with pytest.raises(Exception):
        split_overrides({"brine_density": 900})


def test_run_design_is_gated_logged_and_reused(toolbox):
    first = toolbox.call("run_design", PICK)
    assert first["physics_gate"] == "pass" and first["meets_all_hard_rules"]
    assert first["unmet_heating_mwh"] == 0.0
    again = toolbox.call("run_design", PICK)
    assert again["run_id"] == first["run_id"] and again["reused_earlier_run"]
    entry = toolbox.ledger.get(first["run_id"])
    assert entry["gate"]["4_second_solver"]["agrees"]
    assert len(json.dumps(first)) < 1500  # compact result for the LLM


def test_cross_check_sensitivity_and_get_run(toolbox):
    run_id = toolbox.call("run_design", PICK)["run_id"]
    check = toolbox.call("cross_check", {"run_id": run_id, "day": "peak_cooling"})
    assert check["agrees"] and check["date"] == "2027-07-19"
    sens = toolbox.call(
        "sensitivity", {"run_id": run_id, "parameter": "permeability_md", "values": [100, 200]}
    )
    lcoe = [r["lcoe_eur_per_mwh"] for r in sens["rows"]]
    assert lcoe[0] > lcoe[1]  # tighter rock, more pumping
    assert toolbox.call("get_run", {"run_id": run_id, "section": "checks"})["checks"]
    assert "error" in toolbox.call("cross_check", {"run_id": "R9999"})


def test_screen_ranks_feasible_designs(toolbox):
    out = toolbox.call(
        "screen",
        {
            "n_doublets": [1, 2],
            "depths_m": [3100],
            "upgrades": ["boiler"],
            "coolings": ["electric"],
        },
    )
    assert out["designs_run"] == 2 and out["meet_all_rules"] >= 1
    assert out["best_by_lcoe"][0]["run_id"].startswith("R")


def test_sandbox_blocks_unsafe_code():
    assert static_check("import os\nos.remove('x')")
    assert static_check("x = eval('1+1')")
    assert static_check("import subprocess")
    assert not static_check(DRY_COOLER_CODE)


def test_write_model_registers_tested_model(toolbox):
    result = toolbox.call(
        "write_model",
        {
            "name": "dry_cooler",
            "register_as": "dry_cooler_test",
            "code": DRY_COOLER_CODE,
            "test_code": DRY_COOLER_TESTS,
        },
    )
    assert result["ok"], result
    assert "dry_cooler_test" in COMPONENT_REGISTRY
    bad = toolbox.call(
        "write_model",
        {
            "name": "bad_model",
            "register_as": "bad_model",
            "code": DRY_COOLER_CODE,
            "test_code": "def test_fails():\n    assert 1 == 2\n",
        },
    )
    assert not bad["ok"] and "bad_model" not in COMPONENT_REGISTRY
    COMPONENT_REGISTRY.pop("dry_cooler_test")


def test_agent_asks_for_missing_input_then_answers(tmp_path):
    steps = scripted_steps("03_incomplete_whatif")
    agent = _agent(tmp_path, steps)
    first = agent.ask(SCENARIOS["03_incomplete_whatif"]["turns"][0])
    assert first.kind == "question" and "return temperature" in first.text
    second = agent.ask("Try 50 degC.")
    assert second.kind == "answer" and len(second.run_ids) == 2
    assert agent.transcript.totals()["questions"] == 1
    _, md = agent.close()
    assert "Agent asks" in md.read_text()


def test_agent_rejects_invented_number_and_recovers(tmp_path):
    agent = _agent(tmp_path, scripted_steps("04_hallucination_caught"))
    reply = agent.ask("Is the two-doublet boiler design cheaper than heating with gas only?")
    assert reply.kind == "answer" and "55" not in reply.text
    kinds = [e["kind"] for e in agent.transcript.events]
    assert "gate_reject" in kinds and kinds.index("gate_reject") < kinds.index("gate_pass")


def test_agent_gives_up_rather_than_hallucinate(tmp_path):
    lie = {"content": "It costs 12345 EUR/MWh."}
    agent = _agent(tmp_path, [lie] * 5)
    agent.config.max_gate_retries = 2
    reply = agent.ask("What does it cost?")
    assert reply.kind == "failed" and "12345" not in reply.text


def test_offtopic_question_uses_no_tools(tmp_path):
    agent = _agent(tmp_path, scripted_steps("02_offtopic_weather"))
    reply = agent.ask("What's the weather in Delft tomorrow?")
    assert reply.kind == "answer" and reply.llm_calls == 1
    assert not [e for e in agent.transcript.events if e["kind"] == "tool"]


def test_notes_persist_across_sessions(tmp_path):
    ProjectNotes(tmp_path).add("decision", "Pick 2 doublets at 3.1 km")
    agent = _agent(tmp_path, [{"content": "ok"}])
    assert "Pick 2 doublets" in agent._messages()[0]["content"]


def test_behaviour_checks_flag_missing_question(tmp_path):
    from gemini_agent.agent import AgentReply
    from gemini_agent.scenarios import check_behaviour

    replies = [AgentReply(kind="answer", text="Here is a design.")]
    events = [{"kind": "tool", "name": "run_design", "result_preview": "{}"}]
    failed = check_behaviour("01_design_brief_incomplete", replies, events)
    assert failed == ["first reply should be a question, was answer"]
    assert check_behaviour("02_offtopic_weather", replies, events)
