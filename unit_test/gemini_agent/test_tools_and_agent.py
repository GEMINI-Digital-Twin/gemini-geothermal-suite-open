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
    """Build a tool box in a temporary workspace."""
    ws = tmp_path_factory.mktemp("ws")
    return ToolBox(load_demand(INPUTS), RunLedger(ws), ProjectNotes(ws), ws, workers=1)


def _agent(tmp_path, steps):
    cfg = AgentConfig.load(env={}, workspace=str(tmp_path), screen_workers=1)
    return DesignAgent(cfg, llm=ScriptedLLM(steps), inputs_dir=INPUTS, session_name="t")


def test_gate1_rejects_bad_arguments():
    """Test gate1 rejects bad arguments."""
    errors = validate_arguments("run_design", {"n_doublets": 4, "depth_m": 3100, "cooling": "x"})
    text = " ".join(errors)
    assert "above the maximum 3" in text and "missing argument 'upgrade'" in text
    assert "must be one of" in text
    assert validate_arguments("launch_rocket", {})[0].startswith("unknown tool")
    assert validate_arguments("run_design", {**PICK, "chp": "yes"})


def test_overrides_are_range_checked():
    """Test overrides are range checked."""
    challenge, assumptions, scale = split_overrides(
        {"heating_return_c": 50, "permeability_md": 100}
    )
    assert assumptions["heating_return_c"] == 50 and challenge["permeability_md"] == 100
    with pytest.raises(Exception):
        split_overrides({"heating_return_c": 120})
    with pytest.raises(Exception):
        split_overrides({"brine_density": 900})


def test_run_design_is_gated_logged_and_reused(toolbox):
    """Test run design is gated logged and reused."""
    first = toolbox.call("run_design", PICK)
    assert first["physics_gate"] == "pass" and first["meets_all_hard_rules"]
    assert first["unmet_heating_mwh"] == 0.0
    again = toolbox.call("run_design", PICK)
    assert again["run_id"] == first["run_id"] and again["reused_earlier_run"]
    entry = toolbox.ledger.get(first["run_id"])
    assert entry["gate"]["4_second_solver"]["agrees"]
    assert len(json.dumps(first)) < 1500  # compact result for the LLM


def test_run_design_with_operating_rules(toolbox):
    """Operating rules make another gated run that reports its doublet starts."""
    plain = toolbox.call("run_design", PICK)
    ruled = toolbox.call("run_design", {**PICK, "operating_rules": True})
    assert ruled["physics_gate"] == "pass" and ruled["meets_all_hard_rules"]
    assert ruled["run_id"] != plain["run_id"] and "doublet_starts" in ruled
    assert "doublet_starts" not in plain
    assert validate_arguments("run_design", {**PICK, "operating_rules": "yes"})


def test_cross_check_sensitivity_and_get_run(toolbox):
    """Test cross check sensitivity and get run."""
    run_id = toolbox.call("run_design", PICK)["run_id"]
    check = toolbox.call("cross_check", {"run_id": run_id, "day": "peak_heating"})
    assert check["agrees"] and check["date"] == "2027-01-28"
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
    """Test screen ranks feasible designs."""
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


def test_screen_varies_free_cooling_and_ates(toolbox):
    """free_cooling and ates_doublets can be gridded through screen's 'vary'."""
    grid = {
        "n_doublets": [1, 2, 3],
        "depths_m": [2500, 3100, 3500],
        "upgrades": ["boiler"],
        "coolings": ["electric"],
        "vary": {"free_cooling": [False, True], "ates_doublets": [0, 2, 4, 6]},
    }
    out = toolbox.call("screen", grid)
    assert out["error"] == "72 designs requested; the limit is 48"


def test_sandbox_blocks_unsafe_code():
    """Test sandbox blocks unsafe code."""
    assert static_check("import os\nos.remove('x')")
    assert static_check("x = eval('1+1')")
    assert static_check("import subprocess")
    assert not static_check(DRY_COOLER_CODE)
    # numpy / scipy file I/O, not only open()
    assert static_check("import numpy as np\nx = np.fromfile('secret')")
    assert static_check("import numpy\nnumpy.save('x', 1)")
    assert static_check("from numpy import loadtxt")
    assert static_check("from scipy import io\nio.loadmat('x')")
    assert not static_check("import numpy as np\nclass A:\n    load = 1.0\n    y = np.sum([load])")


def test_write_model_registers_tested_model(toolbox):
    """Test write model registers tested model."""
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
    """Test agent asks for missing input then answers."""
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
    """Test agent rejects invented number and recovers."""
    agent = _agent(tmp_path, scripted_steps("04_hallucination_caught"))
    reply = agent.ask("Is the two-doublet boiler design cheaper than heating with gas only?")
    assert reply.kind == "answer" and "55" not in reply.text
    kinds = [e["kind"] for e in agent.transcript.events]
    assert "gate_reject" in kinds and kinds.index("gate_reject") < kinds.index("gate_pass")


def test_agent_gives_up_rather_than_hallucinate(tmp_path):
    """Test agent gives up rather than hallucinate."""
    lie = {"content": "It costs 12345 EUR/MWh."}
    agent = _agent(tmp_path, [lie] * 5)
    agent.config.max_gate_retries = 2
    reply = agent.ask("What does it cost?")
    assert reply.kind == "failed" and "12345" not in reply.text


def test_offtopic_question_uses_no_tools(tmp_path):
    """Test offtopic question uses no tools."""
    agent = _agent(tmp_path, scripted_steps("02_offtopic_weather"))
    reply = agent.ask("What's the weather in Delft tomorrow?")
    assert reply.kind == "answer" and reply.llm_calls == 1
    assert not [e for e in agent.transcript.events if e["kind"] == "tool"]


def test_notes_persist_across_sessions(tmp_path):
    """Test notes persist across sessions."""
    ProjectNotes(tmp_path).add("decision", "Pick 2 doublets at 3.1 km")
    agent = _agent(tmp_path, [{"content": "ok"}])
    assert "Pick 2 doublets" in agent._messages()[0]["content"]


def test_behaviour_checks_flag_missing_question(tmp_path):
    """Test behaviour checks flag missing question."""
    from gemini_agent.agent import AgentReply
    from gemini_agent.scenarios import check_behaviour

    replies = [AgentReply(kind="answer", text="Here is a design.")]
    events = [{"kind": "tool", "name": "run_design", "result_preview": "{}"}]
    failed = check_behaviour("01_design_brief_incomplete", replies, events)
    assert failed == ["first reply should be a question, was answer"]
    assert check_behaviour("02_offtopic_weather", replies, events)


def test_orc_option_is_listed_and_runs_through_the_gate(toolbox):
    """The ORC is a neutral design option: listed, gated, priced and screenable."""
    listed = toolbox.call("list_models", {})
    assert "orc" in listed["gemini_components"]
    assert "orc_capacity_mw_el" in listed["design_options"]
    r = toolbox.call("run_design", {**PICK, "chp": True, "orc_capacity_mw_el": 1.0})
    assert r["physics_gate"] == "pass", r
    assert r["design"].endswith("-orc1") and r["orc_electricity_mwh"] > 0
    assert validate_arguments("run_design", {**PICK, "orc_capacity_mw_el": 20})
    s = toolbox.call(
        "screen",
        {
            "n_doublets": [2],
            "depths_m": [3100],
            "upgrades": ["boiler"],
            "coolings": ["electric"],
            "chp": [True],
            "orc_capacity_mw_el": [0, 1.0],
        },
    )
    assert s["designs_run"] == 2 and s["failed_physics_gate"] == 0


def test_describe_inputs_says_whether_weather_is_loaded(toolbox, tmp_path):
    """The agent is told when measured weather is loaded (free cooling and ATES need it)."""
    assert toolbox.tool_describe_inputs()["weather"]["loaded"] is False
    demand = load_demand(INPUTS).assign(ambient_c=10.0)
    box = ToolBox(demand, RunLedger(tmp_path), ProjectNotes(tmp_path), tmp_path, workers=1)
    weather = box.tool_describe_inputs()["weather"]
    assert weather["loaded"] is True and weather["outdoor_max_c"] == 10.0


def test_truncated_final_answer_is_rejected(tmp_path):
    """An answer cut off at the token limit does not pass the gate."""
    from gemini_agent.llm import LLMResponse

    class Cut:
        def __init__(self):
            self.calls = 0

        def chat(self, messages, tools):
            self.calls += 1
            text = "Peak heating is 30 MW and" if self.calls == 1 else "Peak heating is 30 MW."
            return LLMResponse(text, [], 10, 10, truncated=self.calls == 1)

    cfg = AgentConfig.load(env={}, workspace=str(tmp_path))
    agent = DesignAgent(cfg, llm=Cut())
    reply = agent.ask("What is the heating peak?")
    assert reply.kind == "answer" and reply.text == "Peak heating is 30 MW."
    assert any(
        e["kind"] == "gate_reject" and "cut off" in e["errors"][0] for e in agent.transcript.events
    )


def test_orc_that_never_runs_is_flagged(toolbox):
    """An installed ORC with no output is reported with its CAPEX and a plain note."""
    from gemini_agent.tools import _orc_headline

    energy = {"orc_electricity": 0.0, "grid_export": 10.0}
    econ = {"capex_eur": {"orc": 3.0e6}}
    out = _orc_headline({"orc_capacity_mw_el": 1.0}, energy, econ)
    assert out["orc_electricity_mwh"] == 0.0 and out["orc_capex_meur"] == 3.0
    assert "never ran" in out["orc_note"]
    assert _orc_headline({"orc_capacity_mw_el": 0.0}, energy, econ) == {}
    ran = _orc_headline({"orc_capacity_mw_el": 1.0}, {**energy, "orc_electricity": 2000.0}, econ)
    assert "orc_note" not in ran and ran["orc_full_load_hours"] == 2000.0
