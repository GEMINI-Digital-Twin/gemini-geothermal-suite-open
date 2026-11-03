"""Regression tests for the hackathon models (run: PYTHONPATH=. pytest hackathon/tests -q)."""

import math

import pytest

from hackathon.models import subsurface as sub
from hackathon.models import surface as sf
from hackathon.models.config import load_config
from hackathon.models.dispatch import Design, evaluate_design, load_demand
from hackathon.models.robustness import run_robustness
from hackathon.validation.validate_doublet import quick_estimate


@pytest.fixture(scope="module")
def cfg():
    return load_config()


def _dh_design():
    return Design(depth_m=2500, n_doublets=2, spacing_m=1600, surface=sf.SurfaceParams(
        hp_capacity_mw=15, chiller_type="absorption_dh", sorption_capacity_mw=10,
        elec_chiller_capacity_mw=4, boiler_capacity_mw=10))


def test_every_assumption_has_a_source(cfg):
    for name, a in cfg.raw["assumptions"].items():
        assert a.get("source"), f"{name} has no source"
        assert a["status"] == "confirmed", f"{name} not confirmed"


def test_demand_matches_fact_sheet(cfg):
    d = load_demand(cfg)
    assert len(d) == 365
    assert d.heat_mw.sum() * 24 / 1000 == pytest.approx(111.67, abs=0.01)
    assert d.cool_mw.sum() * 24 / 1000 == pytest.approx(23.74, abs=0.01)
    assert d.heat_mw.max() == 30.0 and d.cool_mw.max() == 10.0


def test_reservoir_at_reference_depth(cfg):
    assert sub.reservoir_temperature_c(cfg, 2500) == pytest.approx(87.0)
    assert sub.reservoir_pressure_bar(cfg, 2500) == pytest.approx(250.0)


def test_gemini_pi_matches_hand_darcy(cfg):
    """GEMINI bottomhole_skin_dp with r_e = L equals the Thiem/DoubletCalc formula."""
    assert sub.productivity_index_m3h_bar(cfg) == pytest.approx(quick_estimate(cfg, 100)["pi_producer"],
                                                                rel=1e-6)


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


def test_heat_pump_cop_close_to_gemini():
    m_net = 30e6 / (4217 * 40)
    g = sf.gemini_heatpump_cop(0.5, 82.18, 100, 62.5, m_net / 1000, 2 * 300 / 3600)
    ours = sf.lorenz_cop(0.5, 82.18, 100, 62.5, g["Ts_out"])
    assert ours == pytest.approx(g["COP"], rel=0.05)


def test_brine_cooling_cap_respected(cfg):
    p = sf.SurfaceParams(hp_capacity_mw=30, chiller_type="absorption_dh", sorption_capacity_mw=10,
                         boiler_capacity_mw=30)
    for heat, cool in ((30, 0), (3, 10)):
        o = sf.simulate_day(cfg, p, heat, cool, 2 * 1030 * 300 / 3600, 85.57, 3.8)
        assert 85.57 - o["brine_out_c"] <= cfg.dt_brine_max + 1e-6


def test_breakthrough_limits_short_spacing(cfg):
    assert sub.thermal_breakthrough_years(cfg, 1000, 300) < cfg.lifetime_years
    assert sub.thermal_breakthrough_years(cfg, 1600, 300) > cfg.lifetime_years


def test_dh_design_feasible_and_lcoh_plausible():
    r = evaluate_design(_dh_design())
    assert not [v for v in r["violations"] if v["severity"] == "hard"]
    assert r["kpis"]["heat_unmet_gwh"] == 0 and r["kpis"]["cool_unmet_gwh"] == 0
    assert 20 < r["kpis"]["lcoh_eur_per_mwh"] < 200


def test_robustness_percentiles_ordered():
    r = run_robustness(_dh_design(), n_samples=6)
    l = r["lcoh_eur_per_mwh"]
    assert l["P10"] <= l["P50"] <= l["P90"]           # less is better: P90 is the high (conservative) side
    s = r["heat_share_geothermal"]
    assert s["P10"] >= s["P50"] >= s["P90"]           # more is better: P90 is the low (conservative) side


def test_scripted_agent_run(tmp_path):
    """The loop, tools, gap gating, verification and token log work end to end offline."""
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


def test_finish_verification_flags_non_best_choice(tmp_path):
    from hackathon.agent.tools import Session

    s = Session(tmp_path)
    for m in ("annual_dispatch", "heat_pump", "absorption_chiller", "electric_chiller"):
        s.load_supplementary_model(m)
    common = dict(n_doublets=2, spacing_m=1600, hp_capacity_mw=15, chiller_type="absorption_dh",
                  sorption_capacity_mw=10, elec_chiller_capacity_mw=4, boiler_capacity_mw=10)
    s.evaluate_design(depth_m=2500, **common)                      # D1
    s.evaluate_design(depth_m=3300, **{**common, "hp_capacity_mw": 4})  # D2 (cheaper)
    s.evaluate_design(depth_m=2500, n_doublets=3, spacing_m=1600, hp_capacity_mw=12,
                      chiller_type="absorption_dh", sorption_capacity_mw=10,
                      elec_chiller_capacity_mw=4, boiler_capacity_mw=10)  # D3
    s.robustness_check("D1", n_samples=4)
    s.return_temperature_sensitivity("D1")
    # F2: D1 carries an N-1 warning that the justification must address
    r = s.finish("D1", "Choose D1: 2 doublets at 2500 m, LCOH 60 EUR/MWh, better than D3.")
    assert r["accepted"] is False and any("n_minus_1" in p for p in r["problems"])
    # F1: D2 is feasible, cheaper and was never robustness-checked
    why = "D1: 2 doublets at 2500 m, LCOH 60 EUR/MWh; N-1 risk covered by the 10 MW backup boiler."
    r = s.finish("D1", why)
    assert r["accepted"] is False and any("not robustness-checked" in f for f in r["verification_findings"])
    s.robustness_check("D2", n_samples=4)
    r = s.finish("D1", why)
    assert r["accepted"] is False and any("lower P50" in f for f in r["verification_findings"])
    r = s.finish("D1", why + " D1 avoids the PVT warning of D2 at 3300 m; LCOH 60 vs 57.",
                 acknowledge_verification=True)
    assert r["accepted"] == "D1"


def test_loop_guard_detects_repeats_and_stops(tmp_path):
    """P4: identical calls are not re-run (L1) and three all-repeat steps stop the run (L3)."""
    from hackathon.agent.agent import run
    from hackathon.agent.llm_client import ScriptedLLM, TokenLog, tool_call

    brief = tool_call("get_problem_brief", {})
    log = TokenLog(tmp_path / "llm_log.jsonl")
    session, _ = run({"api": ScriptedLLM([brief] * 6, log)}, routing="api_only", run_dir=tmp_path)
    text = (tmp_path / "transcript.md").read_text()
    assert '"repeat":true' in text and "loop detected" in text
    assert log.totals["calls"] == 4  # 1 real call + 3 repeat steps, then stop
