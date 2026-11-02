"""The study on real runs of the shallow sample, over two days: no simulation is replaced."""

import pytest

import gemini as gm
from gemini.study._utils.resize import resized
from gemini.units import Quantity
from tests.unit.study.conftest import shallow_case, shallow_plant

PRICE = "case.economics.energy.electricity"
GAS = "case.economics.energy.gas"
UNCERTAIN = {
    "economics.energy.electricity": {"kind": "uniform", "min": 50, "max": 200},
    "economics.energy.gas": {"kind": "uniform", "min": 54, "max": 56},
}


@pytest.fixture(scope="module")
def case(tmp_path_factory):
    """Return the shallow case over its first two days."""
    return shallow_case(days=2, folder=tmp_path_factory.mktemp("case"), uncertain=UNCERTAIN)


def lcts(plant, case):
    """Return the LCTS of a real run of ``plant`` on ``case``, in SI."""
    results = gm.simulate(plant, case)
    return gm.evaluate.lcts(plant, case, results).si


def searching(**ranges):
    """Return the shallow plant that searches only ``ranges`` ``{path: (min, max)}``."""
    plant = shallow_plant()
    for path in plant.ranges:
        plant.set_range(path)
    for path, (low, high) in ranges.items():
        plant.set_range(path.replace("_", "."), min=low, max=high)
    return plant


def test_minimize_over_the_doublets_finds_the_cheapest_of_three_runs(case):
    """Each count run alone, then the search over the counts."""
    plant = searching(size_doublets=(1, 3))
    costs = {count: lcts(resized(plant, count), case) for count in (1, 2, 3)}
    found = gm.study.minimize(plant, case, "lcts", 5, 0)
    cheapest = min(costs, key=costs.get)
    assert found["evaluations"] == 3
    assert found["best"].parts["parameters"]["size.doublets"].value == cheapest
    assert found["best"].value == pytest.approx(costs[cheapest])
    assert found["best"]["plant"].size == {"doublets": cheapest}


def test_minimize_over_a_range_and_an_option_and_the_best_plant_round_trips(case, tmp_path):
    """A depth range and the arrangement of the exchanger; the best plant file gives its metrics."""
    plant = searching(depth=(Quantity(1000, "m"), Quantity(1800, "m")))
    plant.set_options("heat_exchanger.arrangement", ["counterflow", "parallel"])
    found = gm.study.minimize(plant, case, "lcts", 10, 0)
    best = found["best"]
    assert found["evaluations"] == 20 and found["feasible"]
    assert 1000 <= best.parts["parameters"]["depth"].value <= 1800
    assert best.parts["parameters"]["heat_exchanger.arrangement"] in ("counterflow", "parallel")
    best["plant"].to_json(tmp_path / "best.json")
    again = gm.Plant.from_json(tmp_path / "best.json")
    assert lcts(again, case) == pytest.approx(lcts(best["plant"], case), rel=1e-12)
    assert best.value == pytest.approx(lcts(best["plant"], case), rel=1e-9)


def test_a_two_plant_study_runs_every_plant_and_records_the_runs(case, tmp_path):
    """The same functions through a study file: verdicts, metrics, the comparison, the records."""
    case.to_json(tmp_path / "case.json")
    searching().to_json(tmp_path / "one.json")
    resized(searching(), 2).to_json(tmp_path / "two.json")
    study = {"format": 1, "kind": "study", "name": "two", "cases": ["case.json"]}
    study |= {"plants": ["one.json", "two.json"], "method": "run", "objective": "lcts"}
    study |= {"metrics": ["co2"]}
    result = gm.Study.from_dict(study, folder=tmp_path).run()
    assert [run.plant_name for run in result.runs] == ["one", "two"]
    for run, count in zip(result.runs, (1, 2)):
        plant = resized(searching(), count)
        assert run.metrics["lcts"].si == pytest.approx(lcts(plant, case), rel=1e-12)
        assert run.verdict["feasible"] in (True, False)
    assert set(result.comparison) == set(result.best) == {case.name}
    result.to_json(tmp_path / "results")
    record = tmp_path / "results" / case.name / "one"
    assert {path.name for path in record.iterdir()} >= {"plant.json", "report.json", "series.csv"}


def test_sensitivity_orders_the_prices_by_their_effect(case):
    """A range of 150 EUR/MWh in electricity moves more than 2 EUR/MWh of gas."""
    found = gm.study.sensitivity(shallow_plant(), case, ["lcts"])
    assert [row["parameter"] for row in found] == [PRICE, GAS]
    assert found[0]["at_high"].si > found[0]["at_low"].si
    assert found[0]["effect"].si == pytest.approx(
        abs(found[0]["at_high"].si - found[0]["at_low"].si)
    )


def test_sample_gives_a_spread_of_lcts_and_co2_over_case_and_plant_values(case):
    """Three draws of the two declared prices, each a real run."""
    found = gm.study.sample(shallow_plant(), case, ["lcts", "co2"], 3, 0)
    assert all("reason" not in item for item in found["samples"])
    for metric in ("lcts", "co2"):
        spread = found["summary"][metric]
        assert spread["p5"].si <= spread["p50"].si <= spread["p95"].si
    assert found["summary"]["lcts"]["p95"].si > found["summary"]["lcts"]["p5"].si
