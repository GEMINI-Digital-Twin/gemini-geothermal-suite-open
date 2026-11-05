"""Sized downhole pump (ESP): curve, drives, flow range, cost and the year model."""

import pytest

from gemini_agent.memory import ProjectNotes, RunLedger
from gemini_agent.physics_gate import check_energy_balance, check_run
from gemini_agent.tools import ToolBox
from gemini_design.annual import run_year
from gemini_design.challenge import ASSUMPTIONS, CHALLENGE, load_demand
from gemini_design.doublet import (
    DoubletHydraulics,
    esp_pumps,
    flow_limits_m3h,
    hydraulics_for,
)
from gemini_design.esp import EspPump
from gemini_design.plant import Design
from gemini_uncertainty.economics import capital_cost

INPUTS = "simulator_examples/hackathon_inputs"


@pytest.fixture(scope="module")
def demand():
    """The official 2027 demand."""
    return load_demand(INPUTS)


@pytest.fixture(scope="module")
def well():
    """One producer at 3.1 km with the ideal pump."""
    return DoubletHydraulics(3100.0)


def pump(well, rated, drive):
    """A pump sized for ``rated`` m3/h on ``well``."""
    return EspPump.sized_for(well, rated, drive, CHALLENGE, ASSUMPTIONS)


def test_default_design_keeps_the_ideal_pump():
    """No ESP fields in the design dict, no pump, the challenge's flow range."""
    design = Design(n_doublets=2, depth_m=3100)
    assert "esp_rated_flow_m3h" not in design.as_dict()
    hyd = hydraulics_for(design)
    assert hyd.pump is None and esp_pumps(hyd, design) == []
    assert flow_limits_m3h(hyd) == (50.0, 300.0)


def test_design_checks_and_name():
    """Rated flow 50-300 or 0; a drive only with a sized pump; name shows both."""
    d = Design(n_doublets=1, depth_m=3100, esp_rated_flow_m3h=200, esp_drive="fixed")
    assert d.name.endswith("-esp200f")
    assert d.as_dict()["esp_rated_flow_m3h"] == 200.0
    with pytest.raises(ValueError):
        Design(n_doublets=1, depth_m=3100, esp_rated_flow_m3h=30)
    with pytest.raises(ValueError):
        Design(n_doublets=1, depth_m=3100, esp_drive="fixed")
    with pytest.raises(ValueError):
        Design(n_doublets=1, depth_m=3100, esp_rated_flow_m3h=200, esp_drive="gas")


def test_vsd_pump_matches_the_well_head_and_costs_its_losses(well):
    """A VSD makes exactly the head needed; power is above the ideal pump's (drive, curve)."""
    p = pump(well, 200.0, "vsd")
    need = well.ideal_producer(200.0)["esp_dp_bar"]
    assert p.rated_head_bar == pytest.approx(need * ASSUMPTIONS["esp_head_margin"])
    duty = p.operate(200.0, need)
    assert duty["esp_in_range"] and duty["esp_choke_bar"] == pytest.approx(0.0, abs=1e-9)
    assert duty["esp_pump_dp_bar"] == pytest.approx(need)
    assert 0.9 < duty["esp_speed_ratio"] < 1.0
    ideal = 200.0 / 3600.0 * need * 1e5 / CHALLENGE["pump_efficiency"]
    assert ideal < duty["esp_power_w"] < 1.1 * ideal
    # far below the rated flow the pump slows down; under the minimum speed it chokes
    low = p.operate(60.0, well.ideal_producer(60.0)["esp_dp_bar"])
    assert low["esp_speed_ratio"] >= ASSUMPTIONS["esp_vsd_speed_min"] - 1e-12


def test_fixed_speed_pump_chokes_and_has_a_narrow_range(well):
    """Fixed speed burns surplus head at the choke and cannot run far from its rating."""
    p = pump(well, 250.0, "fixed")
    lo, hi = p.flow_range_m3h()
    assert lo == pytest.approx(0.6 * 250.0) and hi == pytest.approx(1.25 * 250.0)
    need = well.ideal_producer(180.0)["esp_dp_bar"]
    duty = p.operate(180.0, need)
    assert duty["esp_in_range"] and duty["esp_choke_bar"] > 5.0
    ideal = 180.0 / 3600.0 * need * 1e5 / CHALLENGE["pump_efficiency"]
    assert duty["esp_power_w"] > 1.3 * ideal
    assert not p.operate(100.0, well.ideal_producer(100.0)["esp_dp_bar"])["esp_in_range"]
    # a head above the curve cannot be delivered
    assert not p.operate(250.0, 2.0 * p.rated_head_bar)["esp_in_range"]


def test_bigger_pump_costs_more(well):
    """Cost grows with the motor; the VSD adds its own cost."""
    small, big = pump(well, 150.0, "fixed"), pump(well, 300.0, "fixed")
    assert big.motor_kw > 2.0 * small.motor_kw
    assert big.capex_eur(ASSUMPTIONS) > small.capex_eur(ASSUMPTIONS)
    assert pump(well, 300.0, "vsd").capex_eur(ASSUMPTIONS) > big.capex_eur(ASSUMPTIONS)


def test_year_with_a_small_fixed_pump(demand):
    """The pump caps the flow, the boiler covers the rest; balances and gate still hold."""
    design = Design(
        n_doublets=2,
        depth_m=3100,
        cooling="electric",
        esp_rated_flow_m3h=150.0,
        esp_drive="fixed",
    )
    daily, summary = run_year(design, demand)
    active = daily[daily["n_active"] > 0]
    assert active["flow_per_doublet_m3h"].max() <= 1.25 * 150.0 + 1e-9
    assert active["flow_per_doublet_m3h"].min() >= 0.6 * 150.0 - 1e-9
    assert (active["esp_choke_bar"] >= 0.0).all()
    assert summary["all_hard_constraints_met"]
    assert summary["esp"]["days_out_of_range"] == 0
    capex = summary["economics"]["capex_eur"]
    assert capex["esp_vs_reference"] == pytest.approx(summary["esp"]["capex_vs_reference_eur"])
    assert capex["esp_vs_reference"] < 0.0  # smaller than the reference pump
    assert check_energy_balance(daily) == []
    assert check_run(summary, daily)["passed"]
    # the uncertainty study prices the same line
    assert capital_cost(design, ASSUMPTIONS, summary=summary)["esp_vs_reference"] == (
        pytest.approx(capex["esp_vs_reference"])
    )


def test_mixed_depths_get_one_pump_each(demand):
    """Each producer's pump is sized at its own depth."""
    design = Design(
        n_doublets=2, depth_m=3400, doublet_depths_m=(3400, 2800), esp_rated_flow_m3h=200.0
    )
    hyd = hydraulics_for(design)
    pumps = esp_pumps(hyd, design)
    assert len(pumps) == 2 and pumps[0].rated_head_bar != pumps[1].rated_head_bar
    prod = hyd.producer(200.0, active=(0, 1))
    assert prod["esp_in_range"]


def test_agent_can_size_the_pump(tmp_path):
    """run_design and screen 'vary' take the ESP options."""
    tb = ToolBox(
        load_demand(INPUTS), RunLedger(tmp_path), ProjectNotes(tmp_path), tmp_path, workers=1
    )
    args = {"n_doublets": 1, "depth_m": 3100, "upgrade": "boiler", "cooling": "electric"}
    out = tb.call("run_design", {**args, "esp_rated_flow_m3h": 250, "esp_drive": "vsd"})
    assert out["physics_gate"] == "pass", out
    summary = tb.ledger.summary(out["run_id"])
    assert summary["esp"]["pumps"][0]["drive"] == "vsd"
    screen = tb.call(
        "screen",
        {
            "n_doublets": [1],
            "depths_m": [3100],
            "upgrades": ["boiler"],
            "coolings": ["electric"],
            "vary": {"esp_rated_flow_m3h": [200, 300], "esp_drive": ["vsd", "fixed"]},
        },
    )
    assert "error" not in screen, screen
    assert screen["designs_run"] == 4
