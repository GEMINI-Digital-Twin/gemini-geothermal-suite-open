"""Tests for the built-in seasonal pit thermal energy store."""

import numpy as np
import pytest

from gemini_agent.physics_gate import check_run
from gemini_agent.tools import ToolError, make_design
from gemini_design.annual import run_year
from gemini_design.challenge import ASSUMPTIONS, load_demand
from gemini_design.economics import capital_cost_eur
from gemini_design.pit_storage import (
    PitStore,
    PitStoreError,
    capital_cost_eur as pit_cost,
    pit_geometry,
    pit_layout,
)
from gemini_design.plant import Design

INPUTS = "simulator_examples/hackathon_inputs"


@pytest.fixture(scope="module")
def demand():
    """Load the official 365-day demand profile."""
    return load_demand(INPUTS)


def _design(volume=250_000.0, mw=15.0, n=1):
    return Design(
        n_doublets=n,
        depth_m=3100,
        upgrade="boiler",
        cooling="electric",
        chiller_type="screw_dry_cooler",
        chp_capacity_mw_el=0.55,
        pit_store_m3=volume,
        pit_store_mw=mw,
    )


def test_geometry_matches_dronninglund():
    """A 60,000 m3, 16 m deep pit at slope 1:2 has a ~91 m top side, like Dronninglund."""
    geo = pit_geometry(60_000.0)
    assert 88.0 < geo["top_side_m"] < 93.0
    assert geo["layer_volume_m3"].sum() == pytest.approx(60_000.0, rel=1e-9)
    assert geo["layer_volume_m3"][0] > geo["layer_volume_m3"][-1]  # wide at the top


def test_layout_splits_large_stores_and_rejects_small_ones():
    """Stores above the largest pit become equal pits; below the smallest pit are refused."""
    assert pit_layout(600_000.0) == (3, 200_000.0)
    assert pit_layout(250_000.0) == (1, 250_000.0)
    with pytest.raises(PitStoreError):
        pit_layout(10_000.0)


def test_cost_per_m3_falls_with_size_and_matches_the_built_pits():
    """About 40 EUR/m3 (2015) at 60,000 m3, less per m3 for larger pits."""
    small = pit_cost(_design(60_000.0))
    large = pit_cost(_design(250_000.0))
    assert small["eur_per_m3"] / ASSUMPTIONS["pit_store_price_index"] == pytest.approx(40.0)
    assert large["eur_per_m3"] < small["eur_per_m3"]
    # several pits do not get cheaper per m3 than the largest single pit
    assert pit_cost(_design(500_000.0))["eur_per_m3"] == pytest.approx(large["eur_per_m3"])
    assert capital_cost_eur(_design())["pit_store"] == pytest.approx(large["total"])


def test_day_balance_closes_and_temperatures_stay_in_limits():
    """Charge to the liner limit at most; the heat balance closes every day."""
    store = PitStore(100_000.0, 15.0)
    rng = np.random.default_rng(1)
    for day in range(400):
        soc0 = store.heat_above_return_mwh()
        if day < 200:
            out = store.step_day(charge_w=rng.uniform(0, 15e6), t_charge_c=120.0, ambient_c=15.0)
        else:
            out = store.step_day(stream_w=rng.uniform(0, 15e6), ambient_c=0.0)
        soc1 = store.heat_above_return_mwh()
        balance = soc0 + 24.0 * (out["charge_w"] - out["discharge_w"]) / 1e6 - out["loss_mwh"]
        assert balance == pytest.approx(soc1, abs=1e-6 * store.capacity_mwh)
        assert out["top_c"] <= ASSUMPTIONS["pit_store_top_max_c"] + 1e-9
        assert out["top_c"] >= out["bottom_c"] - 1e-9
        assert out["loss_mwh"] >= 0.0


def test_discharge_needs_a_boiler_top_up_and_stops_when_cold():
    """Discharged water is below 100 degC: the boiler tops it up; a cold store gives nothing."""
    store = PitStore(100_000.0, 15.0)
    for _ in range(120):
        store.step_day(charge_w=15e6, t_charge_c=95.0)
    out = store.step_day(stream_w=10e6)
    assert out["discharge_w"] + out["topup_w"] == pytest.approx(10e6, rel=1e-6)
    assert out["topup_w"] > 0.0
    cold = PitStore(100_000.0, 15.0)
    out = cold.step_day(stream_w=10e6)
    assert out["discharge_w"] == 0.0 and out["topup_w"] == 0.0


def test_larger_pits_lose_a_smaller_share():
    """Less surface per m3: the daily loss share falls with the pit size."""
    small = PitStore(50_000.0, 10.0).estimated_loss_fraction_per_day()
    large = PitStore(250_000.0, 10.0).estimated_loss_fraction_per_day()
    assert large < small


def test_pit_store_year_passes_the_physics_gate(demand):
    """1 doublet + 250,000 m3: demand met, balances close, top-up booked on the boiler."""
    daily, summary = run_year(_design(), demand)
    gate = check_run(summary, daily)
    assert gate["passed"], gate
    assert summary["checks"]["pit_store_within_temperature_limits"]
    assert summary["all_hard_constraints_met"]
    pit = summary["pit_store"]
    assert pit["pits"] == 1 and pit["charge_mwh"] > 0 and pit["discharge_mwh"] > 0
    assert 0.5 < pit["storage_efficiency"] < 1.0
    assert pit["boiler_topup_mwh"] > 0
    assert pit["max_top_c"] <= ASSUMPTIONS["pit_store_top_max_c"] + 1e-6
    assert (daily["storage_topup_w"] <= daily["boiler_heat_w"] + 1e-6).all()


def test_design_and_tool_validation():
    """A pit store needs a volume and a rating, and does not mix with the agent slot."""
    with pytest.raises(ValueError):
        Design(1, 3100, pit_store_m3=100_000.0)
    with pytest.raises(ValueError):
        Design(1, 3100, pit_store_m3=100_000.0, pit_store_mw=10.0, storage_mwh=1.0, storage_mw=1.0)
    assert _design().name.endswith("-pit250k")
    base = {"n_doublets": 1, "depth_m": 3100, "upgrade": "boiler", "cooling": "electric"}
    with pytest.raises(ToolError):
        make_design({**base, "pit_store_m3": 5_000, "pit_store_mw": 5}, 30.0, 10.0)
    with pytest.raises(ToolError):
        make_design({**base, "pit_store_m3": 100_000}, 30.0, 10.0)
    d = make_design({**base, "pit_store_m3": 100_000, "pit_store_mw": 10}, 30.0, 10.0)
    assert d.pit_store_m3 == 100_000.0 and d.pit_store_mw == 10.0
