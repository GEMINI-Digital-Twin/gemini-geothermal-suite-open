"""Tests for the Model Forge (safety + test gate), weather mapping and break-even analysis."""

import copy

import pytest

from gemini_agent.forge import GEN_PKG, GEN_TESTS, ModelSpec, forge, run_model, validate
from gemini_agent.physics.design import DesignSpec
from gemini_agent.sensitivity import break_even
from gemini_agent.service import DesignService
from gemini_simulator.registry import COMPONENT_REGISTRY

BASE = {
    "name": "unit_heat_loss_demo",
    "description": "Pipe heat loss demo: Q = UA * (T - T_ground)",
    "inputs": {"t_fluid_c": {"unit": "C"}, "t_ground_c": {"unit": "C"}},
    "parameters": {"ua_w_per_k": {"value": 1000.0}},
    "outputs": {"loss_w": {"expr": "ua_w_per_k * max(0, t_fluid_c - t_ground_c)"}},
    "invariants": ["loss_w >= 0"],
    "tests": [{"inputs": {"t_fluid_c": 80, "t_ground_c": 10}, "expect": {"loss_w": 70000.0}}],
}


@pytest.fixture(autouse=True, scope="module")
def _clean_generated():
    """Forge tests write real files into the generated package; remove them afterwards."""
    yield
    for name in ("unit_heat_loss_demo", "unit_heat_loss_wrong"):
        (GEN_PKG / f"{name}.py").unlink(missing_ok=True)
        (GEN_TESTS / f"test_{name}.py").unlink(missing_ok=True)
        COMPONENT_REGISTRY.pop(name, None)


def test_forge_generates_tests_and_registers():
    rep = forge(BASE)
    assert rep["ok"] and rep["registered_in_gemini_registry"]
    assert (
        run_model("unit_heat_loss_demo", {"t_fluid_c": 50, "t_ground_c": 10})["loss_w"] == 40000.0
    )


def test_forge_rejects_code_injection_and_unknown_names():
    evil = copy.deepcopy(BASE)
    evil["outputs"]["loss_w"]["expr"] = "__import__('os').getcwd()"
    assert not validate(ModelSpec(**evil)) == []
    typo = copy.deepcopy(BASE)
    typo["outputs"]["loss_w"]["expr"] = "ua * 2"
    assert any("unknown name 'ua'" in p for p in validate(ModelSpec(**typo)))


def test_forge_does_not_register_model_failing_its_tests():
    bad = copy.deepcopy(BASE)
    bad["name"] = "unit_heat_loss_wrong"
    bad["tests"][0]["expect"]["loss_w"] = 1.0
    rep = forge(bad)
    assert not rep["ok"] and not rep["registered_in_gemini_registry"]
    assert not (GEN_PKG / "unit_heat_loss_wrong.py").exists()
    assert not (GEN_TESTS / "test_unit_heat_loss_wrong.py").exists()


def test_break_even_two_vs_one_doublet_flips_with_co2_price():
    svc = DesignService()
    two = DesignSpec(
        well_depth_m=3100, n_doublets=2, electric_chiller_mw=11.5, backup_boiler_mw=17.5
    )
    one = DesignSpec(
        well_depth_m=3100,
        n_doublets=1,
        electric_chiller_mw=11.5,
        backup_boiler_mw=32,
        gas_handling="separate_and_burn",
    )
    res = break_even(svc, two, one, "co2_eur_per_t", 0, 400)
    assert res["break_even"] is not None and 50 < res["break_even"] < 300
