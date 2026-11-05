"""Tests for the ESP smart-monitoring module (run: python -m pytest tests -q)."""

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gemini_design_agent.esp_monitoring import EspMonitor, EspTwin, FaultWindow, simulate_esp_telemetry  # noqa: E402
from gemini_design_agent.subsurface import DoubletModel, WellDesign  # noqa: E402


def _twin():
    model = DoubletModel(WellDesign(reservoir_midpoint_m=3500.0, esp_depth_m=1000.0, esp_bep_m3_h=170.0))
    return EspTwin(model, 180.0)


def _setpoints(days):
    rng = np.random.default_rng(1)
    return 180.0 + rng.normal(0, 8, days), 50.0 + rng.normal(0, 1.5, days)


def test_twin_expectation_is_consistent():
    tw = _twin()
    e = tw.expect(np.array([50.0, 55.0]), np.array([180.0, 180.0]))
    assert e["head_bar"].iloc[1] > e["head_bar"].iloc[0]           # affinity law
    assert e["p_intake_bar"].iloc[0] > tw.bubble_point_bar
    assert 50 < e["current_a"].iloc[0] < 400


def test_healthy_telemetry_raises_few_alarms():
    tw = _twin(); q, f = _setpoints(40)
    tele = simulate_esp_telemetry(tw, q, f, days=40, faults=[])
    res = EspMonitor(tw).run(tele)
    assert res.summary["anomalous_hours"] / res.summary["hours"] < 0.03
    assert res.health_now > 97
    assert res.rul_days is None


def test_faults_are_detected_and_labelled():
    tw = _twin(); q, f = _setpoints(60)
    faults = [FaultWindow("gas_interference", 20 * 24, 23 * 24), FaultWindow("wear", 30 * 24, 60 * 24),
              FaultWindow("trip", 55 * 24, 56 * 24)]
    tele = simulate_esp_telemetry(tw, q, f, days=60, faults=faults)
    res = EspMonitor(tw).run(tele)
    kinds = {a.kind for a in res.alerts}
    assert {"gas_interference", "wear", "trip"} <= kinds
    assert res.summary["recall"] > 0.8
    assert res.summary["false_alarm_rate"] < 0.03
    assert res.health_now < 95 and res.esp_efficiency_factor < 0.95
    # wear should produce a finite RUL somewhere after onset
    rul = res.frame["rul_days"].to_numpy()
    assert np.isfinite(rul[35 * 24:50 * 24]).any()
