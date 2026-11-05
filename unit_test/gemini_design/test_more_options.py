"""Electric boiler, heat-recovery heat pump, daily electricity prices and boiler units."""

import numpy as np
import pytest

from gemini_agent.physics_gate import check_energy_balance
from gemini_design.annual import run_year
from gemini_design.challenge import ASSUMPTIONS, load_demand
from gemini_design.plant import Design
from gemini_design.prices import daily_prices

INPUTS = "simulator_examples/hackathon_inputs"


@pytest.fixture(scope="module")
def demand():
    """The official 2027 demand."""
    return load_demand(INPUTS)


def test_daily_prices_keep_the_annual_means(demand):
    """Import is shifted and export scaled so their annual means stay the flat prices."""
    assert daily_prices(demand, {**ASSUMPTIONS, "electricity_daily_prices": 0}) is None
    imp, exp = daily_prices(demand, ASSUMPTIONS)  # on by default
    assert len(imp) == 365 and imp.std() > 10.0
    assert imp.mean() == pytest.approx(ASSUMPTIONS["electricity_price_eur_per_mwh"])
    assert exp.mean() == pytest.approx(ASSUMPTIONS["electricity_export_price_eur_per_mwh"])


def test_electric_boiler_takes_the_top_up_when_cheaper(demand):
    """With dear gas the electric boiler carries the top-up; the balances still close."""
    a = {**ASSUMPTIONS, "gas_price_eur_per_mwh": 150.0}
    design = Design(n_doublets=1, depth_m=3100, cooling="electric", electric_boiler_mw=15.0)
    daily, summary = run_year(design, demand, assumptions=a)
    assert summary["energy_mwh"]["electric_boiler_heat"] > 1000.0
    assert summary["all_hard_constraints_met"]
    assert check_energy_balance(daily, assumptions=a) == []
    assert summary["economics"]["capex_eur"]["electric_boiler"] == pytest.approx(1.5e6)


def test_heat_recovery_heat_pump_closes_its_balance(demand):
    """Heat = cooling + power on every day it runs; it never runs when it costs more."""
    design = Design(n_doublets=2, depth_m=3100, cooling="electric", heat_recovery_hp_mw=4.0)
    daily, summary = run_year(design, demand)
    ran = daily[daily["heat_recovery_cooling_w"] > 0]
    assert len(ran) > 0
    assert np.allclose(
        ran["heat_recovery_heat_w"],
        ran["heat_recovery_cooling_w"] + ran["heat_recovery_power_w"],
    )
    assert (ran["heat_recovery_cop_heating"] > 1.0).all()
    assert check_energy_balance(daily) == []


def test_boiler_part_load_and_units(demand):
    """Part load is on by default (0 = rated efficiency); more units keep efficiency up."""
    from gemini_design.doublet import DoubletHydraulics
    from gemini_design.plant import Plant

    one = Design(n_doublets=1, depth_m=3100, boiler_capacity_mw=30.0)
    three = Design(n_doublets=1, depth_m=3100, boiler_capacity_mw=30.0, boiler_units=3)
    hyd = DoubletHydraulics(3100.0)
    off = {**ASSUMPTIONS, "boiler_part_load": 0}
    assert Plant(one, hyd, assumptions=off).boiler_part_load_ratio(3e6) == 1.0
    on = ASSUMPTIONS
    r1, r3 = Plant(one, hyd, assumptions=on), Plant(three, hyd, assumptions=on)
    assert r1.boiler_part_load_ratio(3e6) < r3.boiler_part_load_ratio(3e6) < 1.0
    assert r3.boiler_part_load_ratio(30e6) == pytest.approx(1.0)
    assert three.name.endswith("-3xB") and "boiler_units" not in one.as_dict()
    daily, _ = run_year(one, demand, assumptions=on)
    assert check_energy_balance(daily, assumptions=on) == []
