"""The daily coverage of a run."""

import json

import pytest

import gemini as gm
from gemini._utils.jsonable import to_plain
from gemini.errors.base import problem
from tests.fixtures.result_tables import cold_ports, heat_ports, make_results
from tests.unit.evaluate.test_summary import boiler_plant

HOURS = 72
"""Three days of hourly steps."""


def plant_of_boiler():
    """Return a plant with a heat consumer, a cold consumer and a boiler."""
    plant = boiler_plant()
    plant.add("CoolingGrid", "cool")
    return plant


def run(boiler, unmet, failed=(), cold=1000.0):
    """Return three days: 5 kW delivered, ``unmet`` W short and ``boiler`` W from the boiler.

    ``boiler`` and ``unmet`` are functions of the hour; ``failed`` lists hours with no value.
    """
    hours = range(HOURS)
    heat = [float("nan") if hour in failed else 5000.0 for hour in hours]
    short = [float("nan") if hour in failed else unmet(hour) for hour in hours]
    columns = {
        "heat": heat_ports(heat) | {"unmet_demand": short},
        "cool": cold_ports([cold] * HOURS)
        | {"unmet_sensible": [100.0] * HOURS, "unmet_latent": [0.0] * HOURS},
        "boiler": {
            "operating": [1.0] * HOURS,
            "fluid_in.enthalpy_flow": [1e6] * HOURS,
            "fluid_out.enthalpy_flow": [1e6 + boiler(hour) for hour in hours],
        },
    }
    errors = [(hour, problem("boiler", "out_of_range", "no")) for hour in failed]
    return make_results(columns, errors=errors)


def by_hour(values):
    """Return a function of the hour that gives the value of its day."""
    return lambda hour: values[hour // 24]


@pytest.fixture(scope="module")
def found():
    """Return the coverage of a run: day 1 geothermal only, day 2 with backup, day 3 short."""
    results = run(by_hour([0.0, 2000.0, 2000.0]), by_hour([0.0, 0.0, 500.0]), failed=(60,))
    return gm.evaluate.daily_coverage(plant_of_boiler(), None, results), results


def test_each_day_has_its_source_and_its_energies_in_display_units(found):
    """Geothermal, then backup, then short; MWh as the display table says."""
    heating = found[0]["heating"]
    assert [day["date"] for day in heating] == ["2024-01-01", "2024-01-02", "2024-01-03"]
    assert [day["source"] for day in heating] == ["geothermal", "backup", "short"]
    first, second = heating[:2]
    assert to_plain(first["demand"]) == {"value": pytest.approx(24 * 5000 / 1e6), "unit": "MWh"}
    assert first["backup"].value == 0.0
    assert second["backup"].value == pytest.approx(24 * 2000 / 1e6)
    assert second["geothermal"].value == pytest.approx(24 * 3000 / 1e6)


def test_a_failed_step_is_counted_and_makes_the_day_short(found):
    """Hour 60 is on day 3: no energy for the step, a failed step, and the day is short."""
    first, _, third = found[0]["heating"]
    assert third["failed_steps"].value == 1 and third["source"] == "short"
    assert third["short"].value == pytest.approx(23 * 500 / 1e6)
    assert first["failed_steps"].value == 0


def test_the_days_add_up_to_the_totals_of_the_run(found):
    """Useful heat, the coverage and the cold are the totals' own numbers."""
    coverage, results = found
    totals = gm.evaluate.totals(plant_of_boiler(), None, results)
    for service, useful, ratio in (
        ("heating", "heat_useful", "heating_coverage"),
        ("cooling", "cold_useful", "cooling_coverage"),
    ):
        days = coverage[service]
        given = sum(day["geothermal"].value + day["backup"].value for day in days)
        assert given == pytest.approx(totals[useful].si / 3.6e9, rel=1e-12)
        demand = sum(day["demand"].value for day in days)
        assert given / demand == pytest.approx(totals[ratio].value)
        assert all(
            day["demand"].value
            == pytest.approx(day["geothermal"].value + day["backup"].value + day["short"].value)
            for day in days
        )


def test_a_plant_without_a_service_leaves_it_out_and_the_answer_is_json():
    """Only the heating grid: no cooling entry; the dict dumps as it is."""
    plant = boiler_plant()
    results = run(by_hour([0.0] * 3), by_hour([0.0] * 3))
    found = gm.evaluate.daily_coverage(plant, None, results)
    assert list(found) == ["heating"]
    assert json.loads(json.dumps(to_plain(found))) == to_plain(found)


def test_no_role_is_a_backup_of_cooling(found):
    """All the cold delivered is the geothermal plant's."""
    days = found[0]["cooling"]
    assert {day["backup"].value for day in days} == {0.0} and days[0]["short"].value > 0


def test_an_electric_boiler_s_heat_is_backup():
    """An ElectricBoiler has no role but backs up the heating: its heat is not geothermal."""
    from tests.unit.evaluate.test_summary import heating_plant

    plant = heating_plant(costed=False)
    plant.add("ElectricBoiler", name="boiler", params={"capacity": {"value": 10, "unit": "kW"}})
    plant.add("CoolingGrid", "cool")
    results = run(by_hour([2000.0, 2000.0, 2000.0]), by_hour([0.0, 0.0, 0.0]))
    first = gm.evaluate.daily_coverage(plant, None, results)["heating"][0]
    assert first["source"] == "backup"
    assert first["backup"].value == pytest.approx(24 * 2000 / 1e6)
    assert first["geothermal"].value == pytest.approx(24 * 3000 / 1e6)
