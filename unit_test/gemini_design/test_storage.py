"""Tests for the seasonal heat-storage slot in the year run."""

import importlib.util

import pytest

from gemini_agent.physics_gate import check_run
from gemini_agent.scenarios import THERMAL_STORAGE_CODE
from gemini_design.annual import run_year
from gemini_design.challenge import load_demand
from gemini_design.plant import Design
from gemini_design.screening import chp_size_mw_el
from gemini_design.storage import STORAGE_TYPE, MissingModelError, build_model, check_model
from gemini_simulator.registry import COMPONENT_REGISTRY

INPUTS = "simulator_examples/hackathon_inputs"


@pytest.fixture(scope="module")
def demand():
    """Load the official 365-day demand profile."""
    return load_demand(INPUTS)


@pytest.fixture
def storage_model(tmp_path):
    """Register the agent's storage model for one test, then empty the slot again."""
    path = tmp_path / "thermal_storage.py"
    path.write_text(THERMAL_STORAGE_CODE, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("agent_generated.thermal_storage", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    COMPONENT_REGISTRY[STORAGE_TYPE] = module.ThermalStorage
    yield module.ThermalStorage
    COMPONENT_REGISTRY.pop(STORAGE_TYPE, None)


def _design(n=1, mwh=25000.0, mw=12.0):
    return Design(
        n_doublets=n,
        depth_m=3100,
        upgrade="boiler",
        cooling="electric",
        boiler_capacity_mw=30.0,
        chiller_capacity_mw=12.0,
        chp_capacity_mw_el=chp_size_mw_el(n),
        storage_mwh=mwh,
        storage_mw=mw,
    )


def test_storage_needs_capacity_and_rating():
    """A store needs both a capacity and a rating; its name shows the size."""
    with pytest.raises(ValueError):
        Design(1, 3100, storage_mwh=1000.0)
    assert _design().name.endswith("-tes25GWh")


def test_storage_design_without_a_model_stops(demand):
    """With the slot empty, a storage design stops and points to write_model."""
    COMPONENT_REGISTRY.pop(STORAGE_TYPE, None)
    with pytest.raises(MissingModelError, match="write_model"):
        run_year(_design(), demand)


def test_interface_check_catches_a_model_that_creates_heat(storage_model):
    """check_model rejects a store whose state of charge does not balance."""

    class Leaky(storage_model):
        def calculate_output(self, u, x=None):
            super().calculate_output(u, x)
            self.output["soc_mwh"] += 100.0  # heat from nowhere

    model = Leaky()
    model.update_parameters({"capacity_mwh": 1000.0, "power_mw": 10.0})
    assert any("does not balance" in p for p in check_model(model))
    assert check_model(build_model(_design())) == []


def test_store_shifts_summer_heat_to_winter_and_passes_the_gate(demand, storage_model):
    """A 25 GWh store charges in summer, discharges in winter and cuts purchased gas."""
    plain_daily, plain = run_year(_design(mwh=0.0, mw=0.0), demand)
    daily, summary = run_year(_design(), demand)
    e = summary["energy_mwh"]
    assert summary["all_hard_constraints_met"]
    assert check_run(summary, daily)["passed"]  # incl. the storage state-of-charge balance
    assert e["heating_delivered"] == pytest.approx(plain["energy_mwh"]["heating_delivered"])
    assert e["purchased_gas_fuel"] < 0.1 * plain["energy_mwh"]["purchased_gas_fuel"]
    assert e["storage_discharge"] > 0 and e["storage_loss"] > 0
    # charged in summer, discharged in winter
    month = daily["date"].dt.month
    assert daily.loc[month.isin([6, 7, 8]), "storage_charge_w"].sum() > 0
    assert daily.loc[month.isin([1, 2, 12]), "storage_discharge_w"].sum() > 0
    assert summary["economics"]["capex_eur"]["storage"] > 0


def test_store_is_not_charged_when_nothing_needs_it(demand, storage_model):
    """With staggered doublet stops the pick has no deficit, so a store is never charged.

    (With a whole-source outage the store does get used: it carries the 35 summer
    days without geothermal heat.)
    """
    daily, summary = run_year(_design(n=2, mwh=5000.0, mw=10.0), demand)
    assert summary["energy_mwh"]["storage_loss"] == pytest.approx(0.0, abs=1.0)
