"""Cost model: ThermoGIS well/plant costs, N-1 backup boilers, and the design selection rule."""

import pytest

from agentic_design.agent.memory import Memory
from agentic_design.agent.tools import ToolBox
from agentic_design.annual import PlantDesign, run_year
from agentic_design.config import Assumptions
from agentic_design.economics import CostAssumptions, economics, n_minus_1_boiler_mw, well_cost_eur
from agentic_design.wells import WellDesign


def test_thermogis_well_cost():
    # 1.3 x (0.25 MEUR + 700 EUR/m x z + 0.2 EUR/m2 x z^2)
    assert well_cost_eur(2500) == pytest.approx(1.3 * (0.25e6 + 700 * 2500 + 0.2 * 2500 ** 2))
    assert well_cost_eur(3500) > well_cost_eur(3000) > well_cost_eur(2500)


def test_crf():
    assert CostAssumptions(discount_rate=0.0, lifetime_yr=30).crf() == pytest.approx(1 / 30)
    assert CostAssumptions(discount_rate=0.06, lifetime_yr=30).crf() == pytest.approx(0.07265, abs=1e-4)


@pytest.mark.parametrize("n,boiler_lo,boiler_hi", [(1, 29.9, 30.1), (3, 0.0, 5.0)])
def test_n_minus_1_backup_boilers(n, boiler_lo, boiler_hi):
    """One doublet: an unplanned outage leaves nothing, so boilers must carry the whole 30 MW peak."""
    a = Assumptions()
    d = PlantDesign(f"{n}x3000m_EC10", n, WellDesign(3000), electric_chiller_mw=10)
    daily, k, _, _ = run_year(d, a)
    assert boiler_lo <= n_minus_1_boiler_mw(d, daily, a) <= boiler_hi


def test_economics_breakdown_adds_up():
    a = Assumptions()
    d = PlantDesign("2x3000m_EC10", 2, WellDesign(3000), electric_chiller_mw=10)
    daily, k, _, _ = run_year(d, a)
    e = economics(d, daily, k, a)
    assert sum(e["capex_breakdown_meur"].values()) == pytest.approx(e["capex_meur"])
    assert e["capex_breakdown_meur"]["wells"] == pytest.approx(4 * well_cost_eur(3000) / 1e6)
    assert 30 < e["lcoe_eur_per_mwh"] < 100 and e["lcoe_with_co2_eur_per_mwh"] > e["lcoe_eur_per_mwh"]


def test_selection_rule_lowest_cost_with_co2_value(tmp_path):
    tb = ToolBox(Memory(tmp_path / "m.json"))
    r = tb.sweep_designs([3000, 3500], [1, 2], electric_chiller_mw_options=[10], gas_reinjection_options=[False, True])
    feasible = [x for x in r["ranked_by_co2"] if not x["violations"]]
    best = min(x["cost_with_EIB_co2_value_EUR_per_MWh"] for x in feasible)
    rec = next(x for x in feasible if x["name"] == r["recommended_design"])
    assert rec["cost_with_EIB_co2_value_EUR_per_MWh"] <= best * 1.01
    # the cheapest plant without a CO2 value is a single doublet: reported, not recommended
    assert r["lowest_cost_design_meeting_all_constraints"]["name"].startswith("1x")
    assert r["recommended_design"].endswith("_RI")


def test_gas_reinjection_cuts_emissions():
    a = Assumptions()
    burn = PlantDesign("2x3500m_EC10", 2, WellDesign(3500), electric_chiller_mw=10)
    ri = PlantDesign("2x3500m_EC10_RI", 2, WellDesign(3500), electric_chiller_mw=10, gas_reinjection=True)
    db, kb, _, _ = run_year(burn, a)
    dr, kr, _, _ = run_year(ri, a)
    assert kr["co2_t_breakdown"]["associated_gas"] < 0.1 * kb["co2_t_breakdown"]["associated_gas"]
    assert kr["electricity_breakdown_gwh"]["gas_compressor"] > 0 and kr["assoc_gas_reinjected_mm3"] > 0
    # emitted gas only where the boilers burn it
    assert (dr["assoc_gas_emitted_fuel_mw"] <= dr["assoc_gas_fuel_mw"] + 1e-9).all()
    e = economics(ri, dr, kr, a)
    assert e["capex_breakdown_meur"]["gas_reinjection"] > 0
