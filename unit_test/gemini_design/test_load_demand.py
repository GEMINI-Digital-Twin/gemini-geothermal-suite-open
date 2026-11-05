"""Tests for loading other demand files (a judge's own profiles)."""

import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from gemini_design.challenge import default_inputs_dir, load_demand

INPUTS = Path(__file__).resolve().parents[2] / "simulator_examples" / "hackathon_inputs"


@pytest.fixture(scope="module")
def official():
    """The official 2027 profiles."""
    return load_demand(INPUTS)


def _write(folder, year, official, heat_name, cool_name, drop=(), sep=",", dayfirst=False):
    days = pd.date_range(f"{year}-01-01", f"{year}-12-31")
    x = np.arange(len(days)) * 365 / len(days)
    heat = np.interp(x, np.arange(365), official["heating_mw"])
    cool = np.interp(x, np.arange(365), official["cooling_mw"])
    dates = days.strftime("%d/%m/%Y") if dayfirst else days.strftime("%Y-%m-%d")
    h = pd.DataFrame({"Datum": dates, "Heat load [MW]": heat})
    c = pd.DataFrame({"date": dates, "cooling_kW": cool * 1000}).drop(index=list(drop))
    h.to_csv(folder / heat_name, sep=sep, index=False)
    c.to_csv(folder / cool_name, index=False)


def test_official_files_load_unchanged(official):
    """The official files give 365 rows with the published values."""
    raw = pd.read_csv(INPUTS / "GEMINI_Heating_Demand_Daily_2027.csv")
    assert len(official) == 365
    assert list(official.columns) == ["date", "heating_mw", "cooling_mw"]
    assert np.array_equal(official["heating_mw"].to_numpy(), raw["heating_demand_MWth"].to_numpy())


def test_leap_year_renamed_columns_kw_and_gaps(tmp_path, official):
    """A 2028 profile with 29 Feb, other names, kW, ';' and day-first dates loads."""
    _write(
        tmp_path,
        2028,
        official,
        "heat_2028.csv",
        "Cooling_2028.csv",
        drop=(40,),
        sep=";",
        dayfirst=True,
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        demand = load_demand(tmp_path)
    text = " ".join(str(w.message) for w in caught)
    assert len(demand) == 365 and "29 February dropped" in text and "interpolation" in text
    assert not ((demand["date"].dt.month == 2) & (demand["date"].dt.day == 29)).any()
    assert demand["cooling_mw"].max() == pytest.approx(official["cooling_mw"].max(), rel=0.05)
    assert demand["heating_mw"].notna().all() and demand["cooling_mw"].notna().all()


def test_long_gap_and_ambiguous_files_raise(tmp_path, official):
    """Gaps longer than a few days, or two heating files, are errors."""
    _write(tmp_path, 2030, official, "heating.csv", "cooling.csv", drop=range(100, 110))
    with pytest.raises(ValueError, match="missing"):
        load_demand(tmp_path)
    (tmp_path / "heating_copy.csv").write_text((tmp_path / "heating.csv").read_text())
    with pytest.raises(ValueError, match="exactly one heating"):
        load_demand(tmp_path)


def test_gemini_inputs_environment_variable(tmp_path, monkeypatch, official):
    """$GEMINI_INPUTS sets the default folder."""
    _write(tmp_path, 2030, official, "heat.csv", "cool.csv")
    monkeypatch.setenv("GEMINI_INPUTS", str(tmp_path))
    assert default_inputs_dir() == tmp_path
    assert load_demand()["date"].iloc[0].year == 2030
