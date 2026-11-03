"""Regression tests for the hackathon models (run: PYTHONPATH=. pytest hackathon/tests -q)."""

import math

import pytest

from hackathon.models import subsurface as sub
from hackathon.models import surface as sf
from hackathon.models.config import load_config
from hackathon.models.dispatch import Design, evaluate_design, load_demand
from hackathon.validation.validate_doublet import quick_estimate


@pytest.fixture(scope="module")
def cfg():
    return load_config()


def test_demand_matches_fact_sheet(cfg):
    d = load_demand(cfg)
    assert len(d) == 365
    assert d.heat_mw.sum() * 24 / 1000 == pytest.approx(111.67, abs=0.01)
    assert d.cool_mw.sum() * 24 / 1000 == pytest.approx(23.74, abs=0.01)
    assert d.heat_mw.max() == 30.0 and d.cool_mw.max() == 10.0


def test_reservoir_at_reference_depth(cfg):
    assert sub.reservoir_temperature_c(cfg, 2500) == pytest.approx(87.0)
    assert sub.reservoir_pressure_bar(cfg, 2500) == pytest.approx(250.0)


@pytest.mark.parametrize("q", [100, 200, 300])
def test_design_mode_matches_hand_estimate(cfg, q):
    d = sub.doublet_performance(cfg, 2500, q)
    c = quick_estimate(cfg, q)
    assert d["pump_power_mw"] == pytest.approx(c["producer_pump_mw"], rel=0.02)
    assert d["injector_wellhead_pressure_corrected_bar"] == pytest.approx(c["injector_whp_bar"], rel=0.02)


def test_gemini_injector_friction_sign_gap(cfg):
    """GEMINI as-is understates injector WHP by about 2x friction (gap 11)."""
    d = sub.doublet_performance(cfg, 2500, 300)
    fric = quick_estimate(cfg, 300)["friction_bar"]
    gap = d["injector_wellhead_pressure_corrected_bar"] - d["injector_wellhead_pressure_gemini_as_is_bar"]
    assert gap == pytest.approx(2 * fric, rel=0.05)


def test_heat_pump_cop_close_to_gemini(cfg):
    m_net = 30e6 / (4180 * 40)
    g = sf.gemini_heatpump_cop(0.5, 82.18, 100, 62.5, m_net / 1000, 2 * 300 / 3600)
    ours = sf.lorenz_cop(0.5, 82.18, 100, 62.5, g["Ts_out"])
    assert ours == pytest.approx(g["COP"], rel=0.05)


def test_brine_cooling_cap_respected(cfg):
    p = sf.SurfaceParams(hp_capacity_mw=30, sorption_capacity_mw=10, boiler_capacity_mw=30)
    o = sf.simulate_day(cfg, p, 30, 0, 2 * 1030 * 300 / 3600, 85.18)
    assert 85.18 - o["brine_out_c"] <= cfg.dt_brine_max + 1e-6


def test_hand_picked_design_meets_demand():
    r = evaluate_design(Design(surface=sf.SurfaceParams(
        hp_capacity_mw=15, sorption_capacity_mw=8, elec_chiller_capacity_mw=6, boiler_capacity_mw=10)))
    assert not [v for v in r["violations"] if v["severity"] == "hard"]
    assert r["kpis"]["heat_unmet_gwh"] == 0 and r["kpis"]["cool_unmet_gwh"] == 0


def test_scripted_agent_run(tmp_path):
    """The loop, tools, gap gating and token log work end to end offline."""
    from hackathon.agent.agent import run
    from hackathon.agent.demo_script import demo_script
    from hackathon.agent.llm_client import ScriptedLLM, TokenLog

    log = TokenLog(tmp_path / "llm_log.jsonl")
    session, out = run({"api": ScriptedLLM(demo_script(), log)}, routing="api_only", run_dir=tmp_path)
    assert session.final is not None
    assert len(session.candidates) >= 3
    assert (tmp_path / "transcript.md").exists() and log.totals["calls"] >= 10


def test_evaluate_requires_loaded_models(tmp_path):
    from hackathon.agent.tools import Session

    s = Session(tmp_path)
    r = s.evaluate_design(depth_m=2500, n_doublets=2, hp_capacity_mw=10)
    assert r["load_first"] == ["annual_dispatch", "heat_pump"]
