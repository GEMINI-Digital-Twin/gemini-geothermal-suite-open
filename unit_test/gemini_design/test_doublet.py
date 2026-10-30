"""Tests for doublet hydraulics built on GEMINI's IPR and DPDT models."""

import pytest

from gemini_design.doublet import DoubletHydraulics


@pytest.fixture(scope="module")
def doublet():
    """Reference-depth doublet."""
    return DoubletHydraulics(2500.0)


def test_drawdown_follows_productivity_index(doublet):
    """Drawdown = Q / PI."""
    r = doublet.producer(300.0)
    assert r["drawdown_bar"] == pytest.approx(300.0 / doublet.pi_m3h_per_bar)


def test_esp_and_injection_grow_with_flow(doublet):
    """More flow needs more ESP lift, ESP power and injection pressure."""
    low, high = doublet.producer(100.0), doublet.producer(300.0)
    assert high["esp_dp_bar"] > low["esp_dp_bar"] > 0
    assert high["esp_power_w"] > low["esp_power_w"]
    assert (
        doublet.injector(300.0, 50.0)["wellhead_pressure_bar"]
        > doublet.injector(100.0, 50.0)["wellhead_pressure_bar"]
    )


def test_esp_power_uses_70_percent_efficiency(doublet):
    """P = Q * dP / 0.7."""
    r = doublet.producer(200.0)
    assert r["esp_power_w"] == pytest.approx(200 / 3600 * r["esp_dp_bar"] * 1e5 / 0.7)


def test_wellhead_cooler_than_reservoir(doublet):
    """Brine loses some heat on the way up, less at higher rates."""
    t50 = doublet.producer(50.0)["wellhead_temperature_c"]
    t300 = doublet.producer(300.0)["wellhead_temperature_c"]
    assert t50 < t300 < doublet.reservoir_temperature_c
