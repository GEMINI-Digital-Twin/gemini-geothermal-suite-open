"""Acceptance tests for the GeoDesign physics layer, verifier, ledger and GEMINI export.

Hand calculations from the brief are the test oracle.
"""

import pytest

from gemini_agent.ledger import FactLedger, provenance_check
from gemini_agent.physics.design import DesignSpec
from gemini_agent.physics.gemini_project import verify_day
from gemini_agent.physics.site import Brief, gas_properties, reservoir_state
from gemini_agent.physics.wells import injector_point, producer_point, thermal_breakthrough_years
from gemini_agent.service import DesignService


@pytest.fixture(scope="module")
def svc():
    return DesignService()


def test_brief_demand_matches_challenge_document(svc):
    s = svc.demand.summary()
    assert s["heating_peak_mw"] == pytest.approx(30.0)
    assert s["heating_energy_gwh"] == pytest.approx(111.67, abs=0.01)
    assert s["cooling_peak_mw"] == pytest.approx(10.0)
    assert s["cooling_energy_gwh"] == pytest.approx(23.74, abs=0.01)
    assert s["heating_peak_date"] == "2027-01-28" and s["cooling_peak_date"] == "2027-07-19"


def test_reservoir_state_at_reference_depth():
    rs = reservoir_state(Brief.load(), 2500)
    assert rs.temperature_c == pytest.approx(87.0)
    assert rs.pressure_bar == pytest.approx(250.0)
    # PI = 2 pi k h / (mu ln(L/rw)) with k = 200 mD, h = 100 m, mu = 0.4 mPa s
    assert rs.productivity_index_m3h_per_bar == pytest.approx(11.7, abs=0.1)


def test_gas_properties_per_m3_brine():
    g = gas_properties(Brief.load())
    assert g.ch4_nm3_per_m3 == pytest.approx(0.64)
    assert g.co2_if_burned_kg_per_m3 == pytest.approx(0.8 * 1.9768, rel=1e-3)


def test_injector_pressure_balances_hydrostatic_friction_and_injectivity():
    b = Brief.load()
    p = producer_point(b, 2500, 300)
    i = injector_point(b, 2500, 300, 45.0)
    rho_g_h = b.brine["density_kg_m3"] * 9.81 * 2500 / 1e5
    expected = 250 + 300 / p.productivity_index_m3h_per_bar - rho_g_h + p.friction_loss_bar
    assert i.required_wellhead_pressure_bar == pytest.approx(expected, abs=0.3)


def test_thermal_breakthrough_beyond_lifetime_at_design_spacing():
    assert thermal_breakthrough_years(Brief.load(), 300, 1500) > 30


def test_annual_design_meets_demand_within_hard_limits(svc):
    ev = svc.evaluate(
        DesignSpec(
            n_doublets=2,
            heat_pump_mw=10,
            electric_chiller_mw=10,
            backup_boiler_mw=12,
            gas_handling="keep_in_solution_reinject",
        )
    )
    assert ev.checks["passed"], ev.checks["violations"]
    assert ev.kpis["max_brine_dt_k"] <= 40.0 + 1e-6
    assert all(n <= 330 for n in ev.kpis["doublet_operating_days"])
    delivered = ev.kpis["heat_hex_gwh"] + ev.kpis["heat_hp_gwh"] + ev.kpis["heat_boiler_gwh"]
    assert delivered == pytest.approx(ev.kpis["heat_demand_gwh"], rel=1e-6)


def test_undersized_design_is_rejected_by_verifier(svc):
    ev = svc.evaluate(DesignSpec(n_doublets=1, electric_chiller_mw=5, backup_boiler_mw=0))
    names = {v["check"] for v in ev.checks["violations"]}
    assert "heating_demand_met_all_365_days" in names and "cooling_demand_met_all_365_days" in names


def test_gemini_solver_reproduces_screening_dispatch(svc):
    ev = svc.evaluate(
        DesignSpec(well_depth_m=3100, n_doublets=2, electric_chiller_mw=10, backup_boiler_mw=18)
    )
    v = verify_day(ev, 27, svc.brief)
    assert v["consistent"], v["deviation"]


def test_provenance_check_flags_invented_numbers():
    led = FactLedger()
    led.record("t", {}, {"lcoe": 43.18, "co2_t": 6189.9})
    assert provenance_check("LCOE 43.2 EUR/MWh, 6,190 t CO2 [F1]", led)["passed"]
    out = provenance_check("LCOE 43.2 EUR/MWh and 77.7 MW", led)
    assert out["unsupported"] == [77.7]
