"""Tests for the chiller menu, the ATES year plan and the well-integrity check."""

import pytest

from gemini_design import ates as cold_storage
from gemini_design import well_integrity
from gemini_design.annual import run_year
from gemini_design.challenge import ASSUMPTIONS, CHILLER_TYPES, load_demand
from gemini_design.climate import synthetic_year, wet_bulb_c, with_climate
from gemini_design.doublet import DoubletHydraulics
from gemini_design.economics import capital_cost_eur
from gemini_design.plant import Design, Plant
from gemini_model.corrosion.correlation.norsok_model import NORSOK

INPUTS = "simulator_examples/hackathon_inputs"


@pytest.fixture(scope="module")
def demand_weather():
    """Demand with a smooth synthetic year of weather."""
    return with_climate(load_demand(INPUTS), synthetic_year(), "max")


def _plant(**kw):
    """Two-doublet electric-cooling plant."""
    design = Design(2, 3100.0, "boiler", "electric", chiller_capacity_mw=12.0, **kw)
    return design, Plant(design, DoubletHydraulics(3100.0))


def test_wet_bulb():
    """Stull's wet-bulb matches a psychrometric chart value."""
    assert float(wet_bulb_c(20.0, 50.0)) == pytest.approx(13.7, abs=0.1)
    assert float(wet_bulb_c(30.0, 99.0)) == pytest.approx(30.0, abs=0.3)


def test_chiller_types_and_names():
    """Each chiller type builds, gets a short name, and an unknown one is refused."""
    for kind in CHILLER_TYPES:
        design, plant = _plant(chiller_type=kind)
        r = plant.evaluate(5e6, 8e6, 1, 200.0)
        assert r["cooling_delivered_w"] == pytest.approx(8e6)
        assert r["electric_chiller_cop"] > 1.0
    assert _plant(chiller_type="centrifugal_tower")[0].name.endswith("-tower")
    with pytest.raises(ValueError):
        Design(1, 3000.0, "boiler", "electric", chiller_type="magnetic")


def test_heat_sinks():
    """Tower follows the wet-bulb, air-cooled the dry-bulb, the dry cooler its loop."""
    _, tower = _plant(chiller_type="centrifugal_tower")
    r = tower.evaluate(5e6, 8e6, 1, 200.0, ambient_c=25.0, wet_bulb_c=18.0)
    assert r["electric_chiller_sink_c"] == pytest.approx(22.0)
    assert r["tower_water_m3_s"] > 0
    _, air = _plant(chiller_type="air_cooled_screw")
    r = air.evaluate(5e6, 8e6, 1, 200.0, ambient_c=25.0)
    assert r["electric_chiller_sink_c"] == pytest.approx(25.0)
    assert r["tower_water_m3_s"] == 0.0
    _, dry = _plant(chiller_type="screw_dry_cooler")
    r = dry.evaluate(5e6, 8e6, 1, 200.0, ambient_c=25.0)
    assert r["electric_chiller_sink_c"] == pytest.approx(
        25.0 + ASSUMPTIONS["dry_cooler_approach_k"]
    )


def test_calibrated_cop_at_ahri_conditions():
    """The calibrated chillers reproduce the ASHRAE 90.1 minimum full-load COP at AHRI."""
    from gemini_model.chiller.electric_chiller import ElectricChiller

    for kind, cop in (("centrifugal_tower", 6.28), ("air_cooled_screw", 2.96)):
        t = CHILLER_TYPES[kind]
        m = ElectricChiller()
        m.update_parameters(
            {
                "eta_carnot": t["eta_carnot"],
                "cop_max": t["cop_max"],
                "condenser_approach": t["condenser_approach_k"],
                "evaporator_approach": 4.0,
                "chilled_temperature_out_target": 6.7,
            }
        )
        sink = 29.4 if kind == "centrifugal_tower" else 35.0
        assert m.cop(sink) == pytest.approx(cop, rel=0.01)


def test_ates_cooling_reduces_the_chiller_load():
    """ATES pre-cooling lowers chiller power and is added to the electricity."""
    _, plant = _plant(chiller_type="centrifugal_tower")
    base = plant.evaluate(5e6, 8e6, 1, 200.0)
    with_ates = plant.evaluate(5e6, 8e6, 1, 200.0, ates_cooling_w=5e6, ates_power_w=1e5)
    assert with_ates["ates_cooling_w"] == pytest.approx(5e6)
    assert with_ates["cooling_delivered_w"] == pytest.approx(8e6)
    assert with_ates["chiller_power_w"] < base["chiller_power_w"]
    assert with_ates["electricity_w"] == pytest.approx(
        with_ates["esp_power_w"]
        + with_ates["injection_pump_power_w"]
        + with_ates["chiller_power_w"]
        + 1e5
    )


def test_ates_needs_weather():
    """An ATES design without outdoor temperatures stops with a clear error."""
    design, plant = _plant(ates_doublets=2)
    with pytest.raises(cold_storage.MissingWeatherError):
        cold_storage.plan(design, plant, load_demand(INPUTS))


def test_ates_plan_is_balanced(demand_weather):
    """The year plan keeps the aquifer heat balance within the permit tolerance."""
    design, plant = _plant(ates_doublets=3, chiller_type="centrifugal_tower")
    out = cold_storage.plan(design, plant, demand_weather)
    assert abs(out["imbalance"]) <= ASSUMPTIONS["ates_balance_tolerance"] + 1e-6
    assert out["cooling_w"].sum() > 0 and out["charge_w"].sum() > 0
    assert (out["cooling_w"] <= demand_weather["cooling_mw"].to_numpy() * 1e6 + 1).all()
    cooling_days = demand_weather["cooling_mw"].to_numpy() > 0
    assert (out["charge_w"][cooling_days] == 0).all()  # never charges on a cooling day


def test_ates_plan_balances_with_high_losses(demand_weather):
    """With large standing losses the plan throttles discharge but still gives cooling."""
    design, plant = _plant(ates_doublets=3, chiller_type="air_cooled_screw")
    plant.a = dict(ASSUMPTIONS, ates_loss_fraction_per_day=0.004)
    out = cold_storage.plan(design, plant, demand_weather, assumptions=plant.a)
    assert abs(out["imbalance"]) <= ASSUMPTIONS["ates_balance_tolerance"] + 1e-6
    assert out["discharge_flow_fraction"] < 1.0
    assert out["cooling_w"].sum() > 0


def test_ates_year_run(demand_weather):
    """A year with ATES meets demand, passes the checks and reports the store."""
    design = Design(
        2,
        3100.0,
        "boiler",
        "electric",
        chiller_capacity_mw=12.0,
        chiller_type="centrifugal_tower",
        ates_doublets=2,
    )
    daily, summary = run_year(design, demand_weather)
    assert summary["all_hard_constraints_met"]
    assert summary["ates"]["cooling_mwh"] == pytest.approx(
        summary["energy_mwh"]["ates_cooling"], rel=1e-6
    )
    assert summary["economics"]["capex_eur"]["ates"] > 0
    assert summary["economics"]["capex_eur"]["cooling_tower"] > 0
    assert summary["kpi"]["cooling_tower_water_m3_per_year"] > 0


def test_norsok_interpolates_between_table_temperatures():
    """Between table temperatures the NORSOK rate is interpolated, not f(pH) = 7."""
    m = NORSOK()
    m.update_parameters({"diameter": 0.2159, "roughness": 4.5e-5})
    u = {
        "co2_partial_pressure": 1.0,
        "pressure": 100.0,
        "water_density": 1030.0,
        "water_viscosity": 0.4,
        "water_flow_rate": 7200.0,
        "bicarb_concentration": 300.0,
        "ionic_strength": 45.0,
    }

    def rate(t):
        """Corrosion rate at temperature t."""
        return m.calculate_corrosion_rate({**u, "temperature": t})

    r90, r105, r120 = rate(90.0), rate(105.0), rate(120.0)
    assert min(r90, r120) <= r105 <= max(r90, r120)
    assert r105 == pytest.approx(0.5 * (r90 + r120))


def test_well_integrity_assessment():
    """CO2 partial pressure, corrosion, erosion and the chosen mitigation are consistent."""
    out = well_integrity.assess(3100.0)
    pts = out["points"]
    assert 1.0 < pts["producer_bottom"]["co2_partial_pressure_bar"] < 10.0
    assert (
        pts["injector"]["co2_partial_pressure_bar"]
        < pts["producer_bottom"]["co2_partial_pressure_bar"]
    )
    assert out["erosion"]["ok"] and 0 < out["erosion"]["ratio"] < 1
    m = out["mitigation"]
    assert m["life_wall_loss_mm"] <= ASSUMPTIONS["corrosion_allowance_mm"]
    low = well_integrity.choose_mitigation(0.05, 3100.0)
    assert low["option"] == "carbon steel"
    mid = well_integrity.choose_mitigation(0.8, 3100.0)
    assert mid["option"] == "carbon steel + inhibitor"


def test_well_integrity_cost_switch():
    """Mitigation is priced into CAPEX unless switched off."""
    design = Design(2, 3100.0, "boiler", "electric")
    capex, _ = well_integrity.mitigation_cost(design)
    assert capex > 0
    off = dict(ASSUMPTIONS, well_integrity_costs=False)
    assert well_integrity.mitigation_cost(design, off) == (0.0, 0.0)
    assert capital_cost_eur(design, well_integrity_capex=capex)["well_integrity"] == capex


def test_ates_year_with_operating_rules(demand_weather):
    """ATES and the doublet operating rules run together; starts are costed once."""
    from gemini_design.operations import OperatingRules

    design = Design(
        2,
        3100.0,
        "boiler",
        "electric",
        chiller_capacity_mw=6.0,
        chiller_type="air_cooled_screw",
        free_cooling=True,
        ates_doublets=3,
    )
    daily, summary = run_year(design, demand_weather, operations=OperatingRules())
    assert summary["all_hard_constraints_met"]
    assert summary["checks"]["min_run_stop_times_respected"]
    assert summary["ates"]["heat_balance_imbalance"] <= 0.10 + 1e-6
    assert (daily["ates_cooling_w"] > 0).any() and "heat_loss_multiplier" in daily
    starts = summary["operations"]["doublet_starts"]
    assert summary["economics"]["annual_start_cost_eur"] == pytest.approx(starts * 10_000.0)
