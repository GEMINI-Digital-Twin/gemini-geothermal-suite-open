"""The report of a finished run and the comparison of reports."""

import json

import pytest

import gemini as gm
from gemini.evaluate.report import Comparison, Report
from gemini.units import SECONDS_PER_YEAR, Quantity
from gemini.units.shapes import measure
from tests.fixtures.cases import costed_economics, make_case, requirement
from tests.fixtures.costed_plants import day, heating_plant
from tests.fixtures.errors import raises
from tests.fixtures.result_tables import make_results
from tests.unit.evaluate.test_summary import boiler_plant, boiler_run

KEYS = {
    "heat_delivered",
    "cold_delivered",
    "boiler_heat",
    "electricity_bought",
    "gas_bought",
    "capacities",
    "capex",
    "opex",
    "lcts",
    "lcoh",
    "lcoc",
    "co2",
    "requirements",
    "verdict",
    "passed",
    "failed_steps",
    "failures",
    "services",
    "annualised_cost",
    "heating_coverage",
    "cooling_coverage",
    "cop",
    "heat_pump_cop",
    "peak_heat",
    "peak_cold",
}


def case(**parts):
    """Return a case with the economics of the costed plants and a limit on the unmet demand."""
    economics = costed_economics(
        energy={"electricity": Quantity(2e-8, "currency/J")},
        discount_rate=0.05,
        analysis_period=Quantity(20, "yr"),
    )
    limit = requirement("heating_supply", "unmet", max=Quantity(5.0, "W"))
    return make_case(
        economics=economics,
        requirements=[limit],
        utilities={"electricity": {"co2_intensity": Quantity(1e-7, "kg/J")}},
        **parts,
    )


def test_the_report_holds_the_energy_the_costs_the_checks_and_the_failed_steps():
    """Keys, quantities in Python and values of a day of 1000 W of heat."""
    report = gm.evaluate.report(heating_plant(), case(), day())
    assert set(report) == KEYS
    assert report["heat_delivered"].value == pytest.approx(1000.0 * 24 * 3600)
    assert report["capex"].value == 1000.0
    assert report["lcoh"].unit == "currency/J" and report["lcoh"].value > 0
    assert report["opex"].value == pytest.approx(10.0 + 2e-8 * 100.0 * SECONDS_PER_YEAR)
    assert report["co2"].value == pytest.approx(100.0 * 24 * 3600 * 1e-7)
    assert report["failed_steps"] == 0
    assert report["failures"].to_dict() == {"total": 0, "groups": []}
    assert report["boiler_heat"].value is None
    assert [item["name"] for item in report["requirements"]] == ["heating_supply_unmet"]
    assert report["passed"] is True


def test_a_cost_the_case_cannot_give_is_a_value_with_a_reason():
    """Without cooling the levelised cost of cold has no value, and the report still stands."""
    report = gm.evaluate.report(heating_plant(), case(), day())
    assert report["lcoc"].value is None and "no cold" in report["lcoc"].reason
    bare = gm.evaluate.report(heating_plant(), make_case(), day())
    assert bare["capex"].value is None and "economics" in bare["capex"].reason


def test_to_dict_is_plain_json():
    """Every quantity is ``{value, unit}`` and the whole report dumps."""
    report = gm.evaluate.report(heating_plant(), case(), day())
    plain = report.to_dict()
    json.dumps(plain, allow_nan=False)
    assert plain["capex"]["unit"] == "MEUR" and plain["capex"]["value"] == pytest.approx(1e-3)
    assert report["capex"].value == 1000.0
    assert plain["requirements"][0]["role"] == "heating_supply"
    assert plain["failed_steps"] == 0


def test_a_boiler_the_run_does_not_show_gives_no_heat_value():
    """Boilers without port columns in the run leave the heat of the boilers unknown, not zero."""
    plant = gm.Plant("Boiling")
    plant.add("Boiler", "boiler")
    plant.boiler.capacity = Quantity(1e6, "W")
    results = make_results({"boiler": {"power_in": [1.0, 1.0]}})
    heat = gm.evaluate.report(plant, make_case(), results)["boiler_heat"]
    assert heat.value is None and "boilers" in heat.reason


def test_the_report_lists_the_services_the_case_asks_for():
    """No demand, no service; a heating demand is one."""
    assert gm.evaluate.report(heating_plant(), case(), day())["services"] == []
    asked = make_case(supply={"heating": Quantity(60, "degC")})
    assert gm.evaluate.report(heating_plant(), asked, day())["services"] == ["heating"]


def test_to_dict_shows_display_units_or_the_ones_given_and_the_report_stays_si():
    """Energy in MWh, power in MW; units replace one metric; the print is the display dict."""
    report = gm.evaluate.report(heating_plant(), case(), day())
    plain = report.to_dict()
    assert plain["heat_delivered"]["unit"] == "MWh"
    assert plain["heat_delivered"]["value"] == pytest.approx(0.024)
    assert plain["capacities"] == {}
    sized = Report(
        capacities=gm.evaluate.capacities(boiler_plant(), make_case(count=3), boiler_run())
    )
    boiler = sized.to_dict()["capacities"]["boiler"]
    assert boiler["capacity"] == {"value": pytest.approx(0.01), "unit": "MW"}
    assert boiler["share"]["unit"] == "-"
    given = report.to_dict(units={"heat_delivered": "GWh", "capex": "EUR"})
    assert given["heat_delivered"]["unit"] == "GWh" and given["capex"]["unit"] == "EUR"
    assert given["capex"]["value"] == pytest.approx(1000.0)
    assert report["heat_delivered"].unit == "J" and report["capex"].unit == "currency"
    assert json.loads(str(report)) == plain
    with pytest.raises(gm.errors.ValidationError):
        report.to_dict(units={"heat_delivered": "kt"})


def test_every_part_of_a_report_has_a_display_unit():
    """Each ``{value, unit}`` of the dict, parts and nested dicts included, is in a display unit."""
    from gemini.units.display import by_si_unit

    shown = set(by_si_unit().values()) | {"-", "yr"}
    plain = gm.evaluate.report(heating_plant(), case(), day()).to_dict()
    found = []

    def walk(item):
        if isinstance(item, dict):
            if "unit" in item:
                found.append(item["unit"])
            for part in item.values():
                walk(part)
        elif isinstance(item, list):
            for part in item:
                walk(part)

    walk(plain)
    assert set(found) <= shown
    assert {"MEUR", "MEUR/yr", "MWh/yr", "kt", "d"} <= set(found)
    assert plain["opex"]["components"]["electricity"]["unit"] == "MEUR/yr"
    assert plain["co2"]["window"] == {"value": pytest.approx(1.0), "unit": "d"}


def test_the_units_override_reaches_the_parts():
    """A unit given for CO2 shows its mass parts in it; the report stays SI."""
    report = gm.evaluate.report(heating_plant(), case(), day())
    plain = report.to_dict(units={"co2": "t", "opex": "EUR/yr"})
    assert plain["co2"]["electricity"] == {"value": pytest.approx(8.64e-4), "unit": "t"}
    assert plain["opex"]["components"]["fixed"] == {"value": pytest.approx(10.0), "unit": "EUR/yr"}
    assert report["co2"].parts["electricity"].unit == "kg"


FEASIBLE = {"feasible": True, "reasons": []}


"""The verdict of a report that breaks nothing."""


def reports():
    """Return four designs by cost and emissions; the third is beaten by the first."""
    figures = [(10.0, 5.0), (8.0, 9.0), (12.0, 6.0), (20.0, 1.0)]
    return [
        {"lcts": measure(cost, "currency/J"), "co2": co2, "verdict": FEASIBLE}
        for cost, co2 in figures
    ]


def test_one_metric_ranks_the_reports_and_its_best_is_the_front():
    """The smaller cost is rank 1; with one metric the front is its best."""
    found = gm.evaluate.compare(reports(), "lcts")
    assert [entry["ranks"]["lcts"] for entry in found] == [2, 1, 3, 4]
    assert [entry["pareto"] for entry in found] == [False, True, False, False]


def test_two_metrics_mark_the_pareto_front():
    """Design 2 (12, 6) is beaten by design 0 (10, 5); the others trade cost for emissions."""
    found = gm.evaluate.compare(reports(), ["lcts", "co2"])
    assert [entry["pareto"] for entry in found] == [True, True, False, True]
    assert [entry["ranks"] for entry in found][2] == {"lcts": 3, "co2": 3}
    assert found[0]["values"] == {"lcts": Quantity(10.0, "currency/J"), "co2": 5.0}


def test_a_value_is_a_quantity_in_si_and_the_comparison_is_json():
    """A report value in a display unit is stored in SI; to_dict dumps and from_dict restores."""
    given = [
        {
            "lcts": Quantity(50.0, "EUR/MWh").to("EUR/MWh"),
            "co2": measure(2.0, "kg"),
            "verdict": FEASIBLE,
        }
    ]
    found = gm.evaluate.compare(given, ["lcts", "co2"])
    lcts = found[0]["values"]["lcts"]
    assert isinstance(lcts, Quantity) and str(lcts.unit) == "currency/J"
    assert lcts.value == pytest.approx(50.0 / 3.6e9)
    plain = found.to_dict()
    assert json.loads(json.dumps(plain, allow_nan=False)) == plain
    assert plain[0]["values"]["co2"] == {"value": 2.0, "unit": "kg"}
    again = Comparison.from_dict(plain)
    assert again[0]["values"] == found[0]["values"] and again[0]["ranks"] == found[0]["ranks"]


def test_a_metric_can_be_preferred_larger():
    """With the cost to minimise and the emissions to maximise, the front changes."""
    found = gm.evaluate.compare(reports(), {"lcts": "min", "co2": "max"})
    assert [entry["pareto"] for entry in found] == [False, True, False, False]


def test_equal_values_share_a_rank_and_both_stay_on_the_front():
    """Two identical designs do not dominate each other."""
    twins = [{"x": x, "y": y, "verdict": FEASIBLE} for x, y in ((1.0, 2.0), (1.0, 2.0), (2.0, 3.0))]
    found = gm.evaluate.compare(twins, ["x", "y"])
    assert [entry["ranks"]["x"] for entry in found] == [1, 1, 3]
    assert [entry["pareto"] for entry in found] == [True, True, False]


def test_a_report_without_a_value_ranks_last_and_is_off_the_front():
    """A cost the case could not give."""
    mixed = reports() + [
        {"lcts": measure(None, "currency/J", "no cost"), "co2": 0.0, "verdict": FEASIBLE}
    ]
    found = gm.evaluate.compare(mixed, ["lcts", "co2"])
    assert found[4]["ranks"]["lcts"] == 5 and found[4]["values"]["lcts"] is None
    assert found[4]["pareto"] is False


def test_to_frame_has_a_row_per_report():
    """The metrics, their ranks and the front."""
    frame = gm.evaluate.compare(reports(), ["lcts", "co2"]).to_frame()
    assert list(frame.columns) == [
        "lcts [EUR/MWh]",
        "co2 [kt]",
        "rank_lcts",
        "rank_co2",
        "pareto",
        "feasible",
    ]
    assert frame.loc[1, "lcts [EUR/MWh]"] == pytest.approx(8.0 * 3.6e9)
    assert frame.loc[1, "co2 [kt]"] == pytest.approx(9e-6) and bool(frame.loc[3, "pareto"])


def test_to_frame_takes_the_units_given_and_keeps_a_metric_without_a_unit_in_si():
    """A unit replaces the display unit; the column carries it."""
    found = gm.evaluate.compare(
        reports() + [{"lcts": 1.0, "n": 3.0, "verdict": FEASIBLE}], ["lcts", "n"]
    )
    frame = found.to_frame({"lcts": "EUR/kWh"})
    assert frame.loc[1, "lcts [EUR/kWh]"] == pytest.approx(8.0 * 3.6e6)
    assert "n" in frame.columns


def test_to_frame_refuses_a_unit_that_does_not_fit():
    """An unknown metric, a unit of another dimension, an unknown unit."""
    found = gm.evaluate.compare(reports(), ["lcts", "co2"])
    with raises(gm.errors.ValidationError, "invalid_value", match="units.lct"):
        found.to_frame({"lct": "EUR/MWh"})
    with raises(gm.errors.ValidationError, "invalid_unit"):
        found.to_frame({"lcts": "kt"})
    with raises(gm.errors.ValidationError, "invalid_unit"):
        found.to_frame({"co2": "nothing"})


def reason(name, kind="requirement"):
    """Return a reason of a verdict."""
    return {"kind": kind, "name": name, "message": f"{name} failed"}


def served(cost, *reasons, **parts):
    """Return a report of a given cost whose verdict has the given reasons."""
    verdict = {"feasible": not reasons, "reasons": list(reasons)}
    return {"lcts": measure(cost, "currency/J"), "verdict": verdict} | parts


def test_an_infeasible_report_is_never_on_the_front_and_ranks_after_the_feasible():
    """The cheapest report has a reason: it is not feasible, with the reason as given."""
    item = reason("heat.unmet")
    cheap = served(1.0, item)
    found = gm.evaluate.compare([cheap, served(5.0), served(9.0)], "lcts")
    assert [entry["pareto"] for entry in found] == [False, True, False]
    assert [entry["ranks"]["lcts"] for entry in found] == [3, 1, 2]
    assert found[0]["feasible"] is False and found[0]["reasons"] == [item]
    assert found[1]["feasible"] is True and "reasons" not in found[1]


def test_a_report_without_a_verdict_is_refused_not_taken_as_feasible():
    """Only the verdict decides, so a dict of figures with none raises ``missing_value``."""
    with raises(gm.errors.ValidationError, "missing_value") as refused:
        gm.evaluate.compare([{"lcts": 3.0}, served(5.0)], "lcts")
    assert refused.value.path == "reports[0].verdict"


def test_the_infeasible_are_ordered_by_their_number_of_reasons_then_by_the_metric():
    """Two reasons rank after one, whatever the cost."""
    one = reason("a")
    many = served(1.0, one, one)
    few = served(9.0, one)
    found = gm.evaluate.compare([many, few, served(7.0)], "lcts")
    assert [entry["ranks"]["lcts"] for entry in found] == [3, 2, 1]


def test_an_unknown_metric_or_sense_is_refused():
    """The names that exist are suggested."""
    with raises(gm.errors.ValidationError, "unknown_name", match="lcts"):
        gm.evaluate.compare(reports(), ["lct"])
    with raises(gm.errors.ValidationError, "invalid_value", match="by.lcts"):
        gm.evaluate.compare(reports(), {"lcts": "smallest"})
    with raises(gm.errors.ValidationError, "invalid_value"):
        gm.evaluate.compare(reports(), [])


def test_a_nan_metric_ranks_last_and_is_off_the_front():
    """A figure that is not a number is no better than a missing one."""
    mixed = reports() + [{"lcts": float("nan"), "co2": 0.0, "verdict": FEASIBLE}]
    found = gm.evaluate.compare(mixed, ["lcts", "co2"])
    assert found[4]["ranks"]["lcts"] == 5 and found[4]["pareto"] is False
    assert [entry["ranks"]["lcts"] for entry in gm.evaluate.compare(mixed, "lcts")] == [
        2,
        1,
        3,
        4,
        5,
    ]
    larger = gm.evaluate.compare(mixed, {"lcts": "max"})
    assert [entry["ranks"]["lcts"] for entry in larger] == [3, 4, 2, 1, 5]


def test_a_nan_metric_ranks_last_among_the_infeasible_of_the_same_reasons():
    """A run with failed steps that also has a NaN figure does not tie with the best."""
    lost = {"reasons": [{"kind": "failed_step", "name": "failed_steps", "message": "2 failed"}]}
    lost["feasible"] = False
    given = [
        {"x": float("nan"), "verdict": lost},
        {"x": 3.0, "verdict": lost},
        {"x": 1.0, "verdict": lost},
    ]
    found = gm.evaluate.compare(given, "x")
    assert [entry["ranks"]["x"] for entry in found] == [3, 2, 1]


def test_a_missing_value_and_the_reasons_survive_the_round_trip():
    """``None`` for a metric and the list of reasons of an infeasible report come back."""
    lost = {
        "feasible": False,
        "reasons": [{"kind": "failed_step", "name": "failed_steps", "message": "2 failed"}],
    }
    given = [
        {"lcts": measure(None, "currency/J", "no cost"), "verdict": lost},
        {"lcts": measure(2.0, "currency/J"), "verdict": FEASIBLE},
    ]
    found = gm.evaluate.compare(given, "lcts")
    again = Comparison.from_dict(json.loads(json.dumps(found.to_dict(), allow_nan=False)))
    assert again[0]["values"]["lcts"] is None
    assert again[0]["reasons"] == found[0]["reasons"] and again[0]["feasible"] is False
    assert [entry["ranks"] for entry in again] == [entry["ranks"] for entry in found]


def test_comparison_to_dict_shows_display_units_or_the_metrics_given():
    """SI by default; display units as ``to_frame``; a dict replaces one metric's unit."""
    found = gm.evaluate.compare(reports(), ["lcts", "co2"])
    assert found.to_dict()[0]["values"]["lcts"]["unit"] == "currency/J"
    shown = found.to_dict(units="display")
    assert shown[0]["values"]["lcts"] == {"value": pytest.approx(10.0 * 3.6e9), "unit": "EUR/MWh"}
    assert shown[0]["values"]["co2"] == 5.0
    assert found.to_dict(units={"lcts": "EUR/kWh"})[0]["values"]["lcts"]["unit"] == "EUR/kWh"
    assert found.to_dict(units="si") == found.to_dict()
    with raises(gm.errors.ValidationError, "invalid_value"):
        found.to_dict(units="field")


def test_reports_rank_by_a_coverage_the_study_offers():
    """Every metric of gm.study.metrics is a key of the report, so compare ranks by it.

    geomind QA-240: a sample study offered heating_coverage and failed in compare.
    """
    report = gm.evaluate.report(heating_plant(), case(), day())
    assert {item["name"] for item in gm.study.metrics()} <= set(report)
    assert report["heating_coverage"].value == pytest.approx(1.0)
    found = gm.evaluate.compare([report, report], {"heating_coverage": "max"})
    assert len(found) == 2
