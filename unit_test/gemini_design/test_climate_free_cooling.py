"""Tests for outdoor-temperature input and the free-cooling economizer."""

import pandas as pd
import pytest

from gemini_design.challenge import ASSUMPTIONS, load_demand
from gemini_design.climate import read_epw_daily, read_knmi_daily, with_climate
from gemini_design.doublet import DoubletHydraulics
from gemini_design.economics import capital_cost_eur
from gemini_design.plant import Design, Plant

INPUTS = "simulator_examples/hackathon_inputs"


def _plant(free_cooling):
    """plant."""
    design = Design(
        2, 3100.0, "boiler", "electric", chiller_capacity_mw=12.0, free_cooling=free_cooling
    )
    return design, Plant(design, DoubletHydraulics(3100.0))


def test_without_ambient_nothing_changes():
    """Without ambient nothing changes."""
    _, plant = _plant(False)
    _, plant_fc = _plant(True)
    a = plant.evaluate(5e6, 8e6, 1, 200.0)
    b = plant_fc.evaluate(5e6, 8e6, 1, 200.0)
    assert a["cooling_water_c"] == ASSUMPTIONS["cooling_water_c"]
    assert b["free_cooling_w"] == 0.0
    assert a["electricity_w"] == pytest.approx(b["electricity_w"])


def test_cool_air_raises_chiller_cop_and_hot_air_lowers_it():
    """Cool air raises chiller cop and hot air lowers it."""
    _, plant = _plant(False)
    base = plant.evaluate(5e6, 8e6, 1, 200.0)
    cool = plant.evaluate(5e6, 8e6, 1, 200.0, ambient_c=15.0)
    hot = plant.evaluate(5e6, 8e6, 1, 200.0, ambient_c=33.0)
    assert cool["cooling_water_c"] == ASSUMPTIONS["cooling_water_min_c"]
    assert hot["cooling_water_c"] == pytest.approx(33.0 + ASSUMPTIONS["dry_cooler_approach_k"])
    assert cool["electric_chiller_cop"] > base["electric_chiller_cop"] > hot["electric_chiller_cop"]


def test_free_cooling_covers_cold_days_and_part_of_mild_days():
    """Free cooling covers cold days and part of mild days."""
    _, plant = _plant(True)
    cold = plant.evaluate(5e6, 4e6, 1, 200.0, ambient_c=10.0)
    assert cold["free_cooling_w"] == pytest.approx(4e6)
    assert cold["cooling_delivered_w"] == pytest.approx(4e6)
    assert "electric_chiller_cop" not in cold  # the chiller stays off
    mild = plant.evaluate(5e6, 8e6, 1, 200.0, ambient_c=18.0)
    t_fc = 18.0 + ASSUMPTIONS["free_cooling_approach_k"]
    share = (26.0 - t_fc) / (26.0 - 20.0)
    assert mild["free_cooling_w"] == pytest.approx(share * 8e6, rel=1e-6)
    assert mild["cooling_delivered_w"] == pytest.approx(8e6, rel=1e-6)
    warm = plant.evaluate(5e6, 8e6, 1, 200.0, ambient_c=25.0)
    assert warm["free_cooling_w"] == 0.0


def test_free_cooling_needs_an_electric_chiller_and_costs_capex():
    """Free cooling needs an electric chiller and costs capex."""
    with pytest.raises(ValueError):
        Design(2, 3100.0, "boiler", "absorption", free_cooling=True)
    design, _ = _plant(True)
    assert design.name.endswith("-fc")
    assert capital_cost_eur(design)["free_cooling"] == pytest.approx(
        12.0 * ASSUMPTIONS["free_cooling_cost_eur_per_mw"]
    )


def test_with_climate_aligns_by_day_and_keeps_demand(tmp_path):
    """With climate aligns by day and keeps demand."""
    demand = load_demand(INPUTS)
    weather = pd.DataFrame(
        {
            "month": pd.to_datetime(demand["date"]).dt.month,
            "day": pd.to_datetime(demand["date"]).dt.day,
            "mean": 10.0,
            "max": 14.0,
            "min": 6.0,
        }
    )
    out = with_climate(demand, weather, "max")
    assert (out["ambient_c"] == 14.0).all()
    pd.testing.assert_frame_equal(out[demand.columns], demand)
    with pytest.raises(ValueError):
        with_climate(demand, weather.iloc[:300], "max")
    with pytest.raises(ValueError):
        with_climate(demand, weather, "median")


def test_readers(tmp_path):
    """EPW and KNMI readers return one row per day without 29 February."""
    epw = tmp_path / "x.epw"
    header = "\n".join(f"HEADER{i}" for i in range(8))
    rows = [
        f"2001,{m},{d},{h},60,x,{float(h % 10)},0"
        for m, d in [(1, 1), (2, 28), (2, 29)]
        for h in range(1, 25)
    ]
    epw.write_text(header + "\n" + "\n".join(rows))
    daily = read_epw_daily(epw)
    assert len(daily) == 2  # 29 February dropped
    assert daily.loc[0, "max"] == 9.0
    knmi = tmp_path / "etmgeg_240.txt"
    lines = ["# comment", "# STN,YYYYMMDD,   TG,   TN,   TX"]
    for date in pd.date_range("2023-01-01", "2023-12-31"):
        lines.append(f"  240,{date:%Y%m%d},  105,   50,  150")
    knmi.write_text("\n".join(lines))
    k = read_knmi_daily(knmi, 2023)
    assert len(k) == 365 and k.loc[0, "mean"] == 10.5 and k.loc[0, "max"] == 15.0
