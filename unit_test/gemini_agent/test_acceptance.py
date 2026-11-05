"""Tests for the harness acceptance tests on agent-written models and their red team."""

import pytest

from gemini_agent.acceptance import CONTRACTS, describe_contracts, run_acceptance
from gemini_agent.model_red_team import (
    MODEL_FAULTS,
    harness_fails,
    mutate,
    run_model_trials,
    score_models,
)
from gemini_agent.sandbox import static_check
from gemini_agent.scenarios import DRY_COOLER_CODE, DRY_COOLER_TESTS, THERMAL_STORAGE_CODE
from gemini_agent.memory import ProjectNotes, RunLedger
from gemini_agent.tools import ToolBox
from gemini_design.challenge import load_demand
from gemini_model.model_abstract import StaticModel
from gemini_simulator.registry import COMPONENT_REGISTRY

INPUTS = "simulator_examples/hackathon_inputs"


@pytest.fixture(scope="module")
def toolbox(tmp_path_factory):
    """Build a tool box in a temporary workspace."""
    ws = tmp_path_factory.mktemp("ws")
    return ToolBox(load_demand(INPUTS), RunLedger(ws), ProjectNotes(ws), ws, workers=1)


def test_reference_models_pass_the_harness():
    """The demo dry cooler and heat store meet their contracts."""
    assert harness_fails("dry_cooler", DRY_COOLER_CODE, "dry_cooler") == []
    assert harness_fails("thermal_storage", THERMAL_STORAGE_CODE, "thermal_storage") == []


def test_type_without_contract_gets_interface_checks_only():
    """A model for an unknown slot is only checked for the GEMINI interface."""

    class Bare(StaticModel):
        """Model with no contract."""

        def calculate_output(self, u, x=None):
            """Echo."""
            self.output = dict(u)

    problems, level = run_acceptance(Bare, "something_new")
    assert problems == [] and "interface only" in level

    class NoInit(StaticModel):
        """Model that needs constructor arguments."""

        def __init__(self, ua):
            """Needs ua."""
            super().__init__()

        def calculate_output(self, u, x=None):
            """Nothing."""

    problems, _ = run_acceptance(NoInit, "something_new")
    assert "NoInit() raised TypeError" in problems[0]


def test_every_contract_is_described():
    """list_models shows each contract with the checks behind it."""
    described = describe_contracts()
    assert set(described) == set(CONTRACTS)
    assert all(d["harness_checks"] for d in described.values())


def test_wrong_base_class_import_gets_a_hint():
    """The import both live models got wrong in A5 now gets a precise message."""
    problems = static_check("from gemini_model import StaticModel\n")
    assert any("gemini_model.model_abstract" in p for p in problems)


def test_write_model_rejects_a_model_that_passes_its_own_tests(toolbox):
    """A 25 % fan-power model passes the agent's tests but not the harness."""
    _, _, old, new, _ = MODEL_FAULTS["dc_fan_power_high"]
    result = toolbox.call(
        "write_model",
        {
            "name": "dry_cooler",
            "register_as": "dry_cooler",
            "code": mutate("dry_cooler", old, new),
            "test_code": DRY_COOLER_TESTS,
        },
    )
    assert not result["ok"] and "harness" in result["error"]
    assert "passed" in result["pytest"]
    assert any("fan power" in p for p in result["harness_problems"])
    assert result["contract"]["inputs"]
    assert "dry_cooler" not in COMPONENT_REGISTRY
    ok = toolbox.call(
        "write_model",
        {
            "name": "dry_cooler",
            "register_as": "dry_cooler",
            "code": DRY_COOLER_CODE,
            "test_code": DRY_COOLER_TESTS,
        },
    )
    assert ok["ok"] and ok["harness_tests"].startswith("pass: interface + dry_cooler physics")
    COMPONENT_REGISTRY.pop("dry_cooler")


def test_model_red_team_scores():
    """The harness catches every designed fault, with no false alarm."""
    rows = run_model_trials()
    t = score_models(rows)
    assert t["false_alarms"] == 0
    assert t["harness_caught_designed"] == t["designed"]
    assert t["agent_tests_caught"] < t["harness_caught"]
    blind = [r for r in rows if r["expected"] == "blind"]
    assert blind and not any(r["harness_rejects"] for r in blind)


def test_write_model_works_with_a_relative_workspace(tmp_path, monkeypatch):
    """The harness check finds the model file when the workspace path is relative."""
    from gemini_agent.sandbox import write_model

    monkeypatch.chdir(tmp_path)
    result = write_model(
        "dry_cooler", DRY_COOLER_CODE, DRY_COOLER_TESTS, "dry_cooler_rel", "relative_ws"
    )
    assert result["ok"], result
    assert result["harness_tests"].startswith("pass: interface")
    COMPONENT_REGISTRY.pop("dry_cooler_rel")
