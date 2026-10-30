"""Tests for the Fimbul.jl reservoir layer (no Julia needed: uses the committed table)."""

import json

import numpy as np
import pandas as pd
import pytest

from gemini_design.fimbul import simulate_doublet
from gemini_design.fimbul.lookup import load_table
from gemini_design.fimbul.runner import (
    _key,
    constant_schedule,
    default_inputs,
    mobility_factor,
    run_fimbul,
    schedule_from_daily,
)


def test_table_shape_and_physics():
    tab = load_table()
    n_s, n_q, n_y = len(tab["spacing_m"]), len(tab["flow_m3h"]), len(tab["years"])
    assert tab["theta"].shape == (n_s, n_q, n_y)
    # normalised temperature drop stays in [0, 1] and never recovers
    assert (tab["theta"] > -0.02).all() and (tab["theta"] < 1.0).all()
    assert (np.diff(tab["theta"], axis=2) > -1e-3).all()
    # closer wells and higher rates cool the producer at least as much
    assert (tab["theta"][0, -1, -1] >= tab["theta"][-1, -1, -1]).all()
    assert (tab["theta"][0, -1, -1] >= tab["theta"][0, 0, -1]).all()
    # pressures rise with rate
    assert (np.diff(tab["drawdown_bar"][:, :, 0], axis=1) > 0).all()


def test_simulate_doublet_defaults_are_json():
    res = simulate_doublet()
    json.dumps(res)
    assert res["source"] == "fimbul_table"
    assert len(res["production_temperature_c"]) == 30
    assert res["reservoir_temperature_c"] == pytest.approx(105.0)
    assert res["production_temperature_c"][0] == pytest.approx(105.0, abs=0.5)


def test_scalings():
    base = simulate_doublet(flow_m3h=200.0, well_spacing_m=900.0)
    half_k = simulate_doublet(flow_m3h=200.0, well_spacing_m=900.0, permeability_md=100.0)
    assert half_k["producer_drawdown_bar"][0] == pytest.approx(2 * base["producer_drawdown_bar"][0])
    assert half_k["production_temperature_c"] == base["production_temperature_c"]
    # a colder injection deepens the drop in proportion to (T_res - T_inj)
    cold = simulate_doublet(flow_m3h=200.0, well_spacing_m=900.0, injection_temperature_c=45.0)
    ratio = np.asarray(cold["temperature_drop_c"][-1]) / base["temperature_drop_c"][-1]
    assert ratio == pytest.approx((105.0 - 45.0) / (105.0 - 60.0), rel=1e-6)


def test_mobility_factor_matches_brine():
    # pure water at 105 degC is about 0.27 mPa.s against the brief's 0.40 mPa.s brine
    assert mobility_factor(3100.0) == pytest.approx(0.67, abs=0.03)


def test_schedule_from_daily_monthly_volumes():
    dates = pd.date_range("2027-01-01", periods=365, freq="D")
    daily = pd.DataFrame(
        {
            "date": dates,
            "n_active": [2] * 200 + [1] * 165,
            "flow_per_doublet_m3h": [200.0] * 365,
            "injection_temperature_c": [60.0] * 365,
        }
    )
    availability = np.ones((365, 2), dtype=bool)
    sched = schedule_from_daily(daily, availability, years=2)
    assert len(sched) == 24
    assert sum(p["duration_days"] for p in sched[:12]) == 365
    vol = sum(p["duration_days"] * np.asarray(p["flow_m3h"]) for p in sched[:12])
    assert vol.tolist() == pytest.approx([200.0 * 365, 200.0 * 200])


def test_run_fimbul_uses_cache(tmp_path):
    inputs = default_inputs(years=1)
    fake = {"time_days": [365.0], "wells": {}, "num_cells": 1, "wall_time_s": 0.0}
    (tmp_path / f"{_key(inputs)}.json").write_text(json.dumps(fake))
    assert run_fimbul(inputs, cache_dir=tmp_path, julia="no-such-julia")["num_cells"] == 1
    with pytest.raises(RuntimeError):
        run_fimbul(default_inputs(years=2), cache_dir=tmp_path, julia="no-such-julia")


def test_constant_schedule():
    sched = constant_schedule([100.0, 0.0], [60.0, 60.0], 3)
    assert len(sched) == 3 and sched[0]["flow_m3h"] == [100.0, 0.0]
