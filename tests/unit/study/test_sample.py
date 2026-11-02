"""``gm.study.sample`` on the uncertainty declared in the case, with the run replaced by a cost."""

import importlib
import json

import numpy as np
import pytest

import gemini as gm
from gemini.evaluate.verdict import Verdict, reason
from gemini.study._utils import trial as trial_module
from tests.fixtures.errors import raises
from tests.unit.study.conftest import shallow_case, shallow_plant

sample_module = importlib.import_module("gemini.study.sample")
PRICE = "case.economics.energy.electricity"
PATH = "economics.energy.electricity"
DECLARED = {
    PATH: {"kind": "normal", "std": 10, "min": 90, "max": 150},
    "economics.energy.gas": {"kind": "triangular", "min": 40, "max": 90},
    "economics.discount_rate": {"kind": "uniform", "min": 0.02, "max": 0.08},
}


def declared_case(**uncertain):
    """Return the shallow case with ``DECLARED`` uncertainty, or the one given."""
    return shallow_case(uncertain=uncertain or DECLARED)


@pytest.fixture
def sampled(runs):
    """Return two samples of one seed over the declared values."""
    case = declared_case()
    return [gm.study.sample(shallow_plant(), case, ["lcts", "co2"], 6, 3) for _ in "ab"]


def test_sample_gives_the_same_summary_with_the_same_seed(sampled):
    """The summary holds the percentiles of each metric."""
    first, second = sampled
    assert first["summary"] == second["summary"] and len(first["samples"]) == 6
    spread = first["summary"]["co2"]
    assert set(spread) == {"mean", "p5", "p50", "p95", "failed"}
    numbers = [item["metrics"]["co2"].value for item in first["samples"]]
    assert spread["p50"].value == pytest.approx(np.median(numbers))
    assert spread["p5"].value <= spread["p50"].value <= spread["p95"].value


def test_only_the_declared_values_are_drawn_inside_their_ranges(sampled, runs):
    """Each draw has the three declared names, in SI, inside the declared bounds."""
    draws = sampled[0]["samples"]
    assert set(draws[0]["parameters"]) == {
        PRICE,
        "case.economics.energy.gas",
        "case.economics.discount_rate",
    }
    prices = [item["parameters"][PRICE] for item in draws]
    assert {item.unit for item in prices} == {"currency/J"}
    assert all(90 / 3.6e9 <= item.value <= 150 / 3.6e9 for item in prices)
    rates = [item["parameters"]["case.economics.discount_rate"].value for item in draws]
    assert all(0.02 <= number <= 0.08 for number in rates) and len(set(rates)) > 1
    seen = {given.economics.energy.electricity for _, given, _ in runs[:6]}
    assert seen == {item.value for item in prices}


def test_the_case_and_the_plant_are_left_unchanged(runs):
    """Each draw works on a copy: the case still holds its own values."""
    case, plant = declared_case(), shallow_plant()
    before = (case.to_dict(), plant.to_dict())
    gm.study.sample(plant, case, ["co2"], 3, 0)
    assert (case.to_dict(), plant.to_dict()) == before
    assert case.economics.energy.electricity == pytest.approx(120 / 3.6e9)
    assert all(given is not case for _, given, _ in runs)


def test_plant_parameters_are_not_drawn(sampled):
    """The depth of the plant is a design decision: it is never a parameter of a draw."""
    assert all("depth" not in item["parameters"] for item in sampled[0]["samples"])


def test_another_seed_gives_other_draws(runs):
    """The draws differ with the seed."""
    case = declared_case()
    one = gm.study.sample(shallow_plant(), case, ["co2"], 3, 1)
    two = gm.study.sample(shallow_plant(), case, ["co2"], 3, 2)
    assert [s["parameters"] for s in one["samples"]] != [s["parameters"] for s in two["samples"]]


def test_a_draw_out_of_the_bounds_of_the_field_fails_and_is_left_out(runs):
    """A normal without bounds can draw a negative price; the case refuses it, the others count."""
    case = declared_case(**{PATH: {"kind": "normal", "std": 200}})
    result = gm.study.sample(shallow_plant(), case, ["co2"], 12, 0)
    failed = [item for item in result["samples"] if "reason" in item]
    assert failed and len(failed) < 12
    assert result["summary"]["co2"]["mean"].value is not None


def test_a_case_without_uncertainty_is_refused(runs):
    """There is nothing to draw."""
    with raises(gm.errors.ValidationError, "missing_value", match="uncertainty"):
        gm.study.sample(shallow_plant(), shallow_case(), ["co2"], 2, 0)
    assert runs == []


@pytest.mark.parametrize(
    ("arguments", "code"),
    [({"samples": 0}, "invalid_value"), ({"metrics": ["lcox"]}, "unknown_name")],
)
def test_a_sample_that_does_not_fit_is_refused(arguments, code, runs):
    """A wrong sample size or metric, before any run."""
    call = dict(metrics=["co2"], samples=2, seed=0) | arguments
    with raises(gm.errors.ValidationError, code):
        gm.study.sample(shallow_plant(), declared_case(), **call)
    assert runs == []


def test_the_seed_is_required(runs):
    """A seed is a reproducibility choice: no default."""
    with pytest.raises(TypeError):
        gm.study.sample(shallow_plant(), declared_case(), ["co2"], 2)


def test_the_result_round_trips_through_json(sampled):
    """to_dict is plain JSON and from_dict gives an equal result."""
    first = sampled[0]
    text = json.dumps(first.to_dict(), allow_nan=False)
    again = gm.study.Sample.from_dict(json.loads(text))
    assert isinstance(again, gm.study.Sample)
    for key, spread in first["summary"].items():
        for name in ("mean", "p5", "p50", "p95"):
            assert again["summary"][key][name].si == pytest.approx(spread[name].si)
    for one, other in zip(again["samples"], first["samples"]):
        assert one["parameters"].keys() == other["parameters"].keys()
        for name, found in other["parameters"].items():
            assert one["parameters"][name].si == pytest.approx(found.si)


def test_the_json_shows_the_display_units(sampled):
    """The prices are in EUR/MWh and the metrics in kt and EUR/MWh, not the SI of the run."""
    plain = sampled[0].to_dict()
    draw = plain["samples"][0]
    assert draw["parameters"][PRICE]["unit"] == "EUR/MWh"
    assert 90 <= draw["parameters"][PRICE]["value"] <= 150
    assert draw["metrics"]["co2"]["unit"] == "kt"
    assert plain["summary"]["lcts"]["p50"]["unit"] == "EUR/MWh"


def test_a_draw_with_failed_steps_gives_no_value_and_is_counted(failing_runs):
    """Its metrics are None with the count and the top failure; the summary leaves it out."""
    case = declared_case(**{PATH: {"kind": "uniform", "min": 100, "max": 300}})
    found = gm.study.sample(shallow_plant(), case, ["lcts"], 8, 1)
    bad = [item for item in found["samples"] if "reason" in item]
    good = [item for item in found["samples"] if "reason" not in item]
    assert bad and good
    for item in bad:
        metric = item["metrics"]["lcts"]
        assert metric.value is None and metric.reason == item["reason"]
        assert "2 steps failed" in metric.reason and "d0.esp out_of_range (2 rows)" in metric.reason
    spread = found["summary"]["lcts"]
    assert spread["failed"].value == len(bad)
    assert spread["mean"].value == pytest.approx(
        np.mean([i["metrics"]["lcts"].value for i in good])
    )
    again = gm.study.Sample.from_dict(json.loads(json.dumps(found.to_dict())))
    assert again["summary"]["lcts"]["failed"].value == len(bad)


def test_the_draws_of_a_call_are_one_batch(monkeypatch, runs):
    """All the draws run together; the batch is the draw set, not a setting."""
    sizes = []
    real = trial_module.run_trials

    def counting(shared, case, plan, valued, names, judge):
        sizes.append(len(valued))
        return real(shared, case, plan, valued, names, judge)

    monkeypatch.setattr(trial_module, "run_trials", counting)
    gm.study.sample(shallow_plant(), declared_case(), ["co2"], 6, 3)
    assert sizes == [6]


def test_the_percentiles_are_the_linear_ones_of_the_draws():
    """Five hand numbers: p5, p50 and p95 by linear interpolation, the mean, the unit."""
    draws = [
        {"parameters": {}, "metrics": {"x": gm.units.shapes.measure(number, "kg")}}
        for number in (4.0, 1.0, 5.0, 2.0, 3.0)
    ]
    spread = sample_module._spread(draws, "x")
    assert spread["p5"].value == pytest.approx(1.2)
    assert spread["p50"].value == 3.0 and spread["p95"].value == pytest.approx(4.8)
    assert spread["mean"].value == 3.0 and spread["p50"].unit == "kg"
    assert spread["failed"].value == 0


def test_a_draw_with_a_nan_metric_is_left_out_of_the_summary(runs, monkeypatch):
    """A figure that is not a number would turn the mean and the percentiles into NaN."""
    real = trial_module.metric

    def lost_above(plant, case, results, name):
        if case.economics.energy.electricity * 3.6e9 > 120:
            return gm.units.shapes.measure(float("nan"), "currency/J")
        return real(plant, case, results, name)

    monkeypatch.setattr(trial_module, "metric", lost_above)
    found = gm.study.sample(shallow_plant(), declared_case(), ["lcts"], 8, 3)
    nan = [i for i in found["samples"] if np.isnan(i["metrics"]["lcts"].value)]
    good = [i["metrics"]["lcts"].value for i in found["samples"] if i not in nan]
    assert nan and good
    spread = found["summary"]["lcts"]
    assert spread["mean"].value == pytest.approx(np.mean(good))
    json.dumps(found.to_dict()["summary"], allow_nan=False)


def test_a_negative_seed_is_refused_as_a_value(runs):
    """Numpy refuses it with a bare ValueError; the call names the argument."""
    with raises(gm.errors.ValidationError, "invalid_value", match="seed"):
        gm.study.sample(shallow_plant(), declared_case(), ["co2"], 2, -1)
    assert runs == []


def test_a_difference_of_temperature_stays_in_kelvin_through_the_round_trip():
    """The flag that keeps K in the JSON survives ``from_dict``."""
    name = "case.site.surface_temperature_difference"
    drawn = {name: gm.units.Quantity(5.0, "K")}
    given = gm.study.Sample(samples=[{"parameters": drawn, "metrics": {}}], summary={})
    given["differences"] = [name]
    plain = given.to_dict()
    assert plain["differences"] == [name]
    assert plain["samples"][0]["parameters"][name] == {"value": 5.0, "unit": "K"}
    again = gm.study.Sample.from_dict(json.loads(json.dumps(plain)))
    assert again["differences"] == [name] and again["samples"][0]["parameters"][name].unit == "K"
    assert again.to_dict() == plain


def test_a_draw_that_breaks_a_requirement_is_a_plain_number_in_the_summary(runs, monkeypatch):
    """Pinned for the owner (t2.md): the draws run unjudged: no feasible count."""
    broken = reason("requirement", "heating_supply_unmet", "unmet demand above its limit")
    monkeypatch.setattr(
        trial_module, "verdict", lambda *a: Verdict(feasible=False, reasons=[broken])
    )
    found = gm.study.sample(shallow_plant(), declared_case(), ["lcts"], 4, 3)
    assert all(item["metrics"]["lcts"].value is not None for item in found["samples"])
    assert set(found["summary"]["lcts"]) == {"mean", "p5", "p50", "p95", "failed"}
    assert found["summary"]["lcts"]["failed"].value == 0
