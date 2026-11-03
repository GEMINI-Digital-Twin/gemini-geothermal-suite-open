"""``gm.study.evolve`` on a small superstructure, with the run replaced by a known cost."""

import importlib
import json

import numpy as np
import pytest

import gemini as gm
from gemini.errors import ValidationError
from gemini.study._utils import trial
from gemini.study.study import REQUIRED
from gemini.units.shapes import measure
from tests.fixtures.errors import raises
from tests.unit.plants._utils.test_superstructure import loop, superplant, valued
from tests.unit.study.conftest import shallow_case

evolve_module = importlib.import_module("gemini.study.evolve")
minimize_module = importlib.import_module("gemini.study.minimize")


def names_of(plant):
    """Return the names of the modules of ``plant``."""
    return {name for name, _ in plant.named_modules() if name}


def known_cost(plant, case, results, name):
    """Return a metric known by hand from the modules of ``plant`` and two of its values.

    ``lcts`` is 5, less 2 with the pump ``x`` plus the square of its flow off 3 kg/s, plus 1 with
    the valve ``y``: the best is the pump at 3 kg/s without the valve, 3. ``co2`` is 2 with the
    pump, plus the rangeability of ``a`` over 50: it is against the pump, so the two conflict.
    """
    names = names_of(plant)
    pump = "x" in names
    if name == "lcts":
        cost = 5.0 + (-2.0 + (plant.x.flow - 3.0) ** 2 if pump else 0.0) + ("y" in names)
        return measure(cost, "currency/J")
    return measure((2.0 if pump else 0.0) + plant.a.rangeability / 50, "kg")


@pytest.fixture(scope="module")
def case():
    """Return the shallow case: the run is replaced, it only has to be a case."""
    return shallow_case()


@pytest.fixture
def evolving(runs, monkeypatch):
    """Replace the run by ``known_cost`` and the check of the plant on the case by none.

    The small plant has no value a real run needs, which ``gm.check`` would report. The value is
    the list of ``(plant, case, plan)`` of every simulation.
    """
    monkeypatch.setattr(trial, "metric", known_cost)
    for module in (evolve_module, minimize_module):
        monkeypatch.setattr(module, "check", lambda plant, case: [])
    return runs


def evolved(case, plant=None, objectives="lcts", evaluations=12, seed=0, **keywords):
    """Return ``gm.study.evolve`` of ``plant`` (the superplant) with a population of 4."""
    keywords = {"population": 4, "polish": 0} | keywords
    plant = superplant() if plant is None else plant
    return gm.study.evolve(plant, case, objectives, evaluations, seed, **keywords)


def dominates(one, other, names):
    """Return whether the design ``one`` is no worse on every objective and better on one."""
    a = [one["metrics"][name].value for name in names]
    b = [other["metrics"][name].value for name in names]
    return all(x <= y for x, y in zip(a, b)) and any(x < y for x, y in zip(a, b))


@pytest.mark.parametrize(
    "objectives", [3, [], ["lcts", 1], ["lcts", "lcts"], ["lcts", "-lcts"], ("co2", "co2")]
)
def test_the_objectives_are_a_metric_or_a_list_of_distinct_ones(evolving, case, objectives):
    """A number, an empty list or a metric twice is refused with ``invalid_value``."""
    with raises(ValidationError, "invalid_value"):
        evolved(case, objectives=objectives)


def test_an_unknown_metric_is_refused(evolving, case):
    """``lcox`` is no metric."""
    with pytest.raises(ValidationError, match="lcox"):
        evolved(case, objectives=["lcts", "lcox"])


@pytest.mark.parametrize(
    "settings",
    [
        {"population": 1},
        {"population": 2.0},
        {"population": True},
        {"evaluations": 3},
        {"polish": -1},
        {"seed": "0"},
        {"seed": True},
        {"seed": 1.5},
    ],
)
def test_the_settings_are_whole_numbers_in_their_range(evolving, case, settings):
    """At least two candidates, a budget of a generation, a polish of none or more, a seed."""
    with raises(ValidationError, "invalid_value"):
        evolved(case, **settings)
    assert evolving == []


def test_polish_needs_the_population_minimize_needs(evolving, case):
    """Five candidates per variable: the superplant has two, so ten."""
    with raises(ValidationError, "invalid_value", match="minimize"):
        evolved(case, polish=1, population=9, evaluations=9)


def test_a_plant_with_nothing_to_search_is_refused(evolving, case):
    """No optional module, no choice, no range, no options."""
    with raises(ValidationError, "invalid_design", match="nothing|no optional"):
        evolved(case, plant=loop())


def test_a_superstructure_without_a_valid_structure_is_refused(evolving, case):
    """Every structure leaves a gas grid unconnected."""
    plant = superplant()
    plant.add("GasGrid", "spare_gas")
    with raises(ValidationError, "invalid_design", match="no structure"):
        evolved(case, plant=plant)
    assert evolving == []


def test_the_plant_is_checked_on_the_case_first(runs, case):
    """Without the stand-in check, the small plant lacks the values a run needs."""
    with pytest.raises(ValidationError):
        evolved(case)
    assert runs == []


def test_the_same_seed_gives_the_same_search_and_another_seed_another(evolving, case):
    """The history, the front and every design are the same for one seed."""
    one, two = (evolved(case, objectives=["lcts", "co2"], evaluations=8) for _ in "ab")
    assert one.to_dict() == two.to_dict()
    other = evolved(case, objectives=["lcts", "co2"], evaluations=8, seed=1)
    assert other.to_dict() != one.to_dict()


def test_the_budget_is_never_exceeded_and_the_progress_reaches_it(evolving, case):
    """At most ``evaluations`` simulations, each one a run; the progress ends at the total."""
    seen = []
    found = evolved(case, evaluations=9, on_progress=lambda done, total: seen.append((done, total)))
    assert found["evaluations"] <= 9 and len(evolving) == found["evaluations"]
    assert seen[-1] == (9, 9) and all(total == 9 for _, total in seen)
    assert [done for done, _ in seen] == sorted(done for done, _ in seen)
    history = found["history"]
    assert [item["generation"] for item in history] == list(range(len(history)))
    assert [item["evaluations"] for item in history][-1] == found["evaluations"]


def test_a_small_space_is_seen_whole_and_the_search_stops_early(evolving, case):
    """Four structures and no value to search: four runs of a budget of 40, then a stall."""
    plant = valued(loop()).set_range("x.flow").set_range("a.rangeability")
    plant.set_optional("x").set_choice("trim", {"valve": ["y"], "none": []})
    found = evolved(case, plant=plant, evaluations=40)
    assert found["evaluations"] == len(evolving) == 4
    assert len(found["history"]) > evolve_module.STALL
    assert found["best"]["structure"] == {"x": True, "trim": "none"}
    assert found["best"]["metrics"]["lcts"].value == pytest.approx(3.0)


def test_an_invalid_structure_is_counted_and_never_simulated(evolving, case):
    """The boiler off leaves the gas unconnected: refused before a run."""
    found = evolved(case, evaluations=16, seed=3)
    assert found["invalid"] > 0
    assert all("boiler" in names_of(plant) for plant, _, _ in evolving)
    assert all(item["structure"]["boiler"] for item in found["front"])


def test_one_objective_gives_one_design_the_best(evolving, case):
    """The front is the best alone, a feasible design of the structure and values it states."""
    found = evolved(case, evaluations=16)
    assert len(found["front"]) == 1 and found["front"][0] is found["best"]
    best = found["best"]
    assert best["feasible"] and best["reason"] is None and best["violation"] == 0.0
    assert best["structure"]["x"] and best["structure"]["trim"] == "none"
    plant = best["plant"]
    assert type(plant) is gm.Plant and plant.optional == [] and "y" not in names_of(plant)
    assert best["parameters"]["x.flow"].value == pytest.approx(plant.x.flow)
    lcts = known_cost(plant, case, None, "lcts").value
    assert best["metrics"]["lcts"].value == pytest.approx(lcts)
    values = [item["best"]["lcts"] for item in found["history"]]
    assert values == sorted(values, reverse=True) and values[-1] == pytest.approx(lcts)


def test_a_module_off_has_no_parameter_in_its_design(evolving, case):
    """A design without the pump reports no flow of the pump."""
    plant = superplant()
    found = evolved(case, plant=plant, objectives=["co2", "lcts"], evaluations=16)
    assert not found["best"]["structure"]["x"]
    assert "x.flow" not in found["best"]["parameters"]
    assert "a.rangeability" in found["best"]["parameters"]


def test_two_objectives_give_a_front_no_member_of_which_dominates_another(evolving, case):
    """The pump is cheaper and emits more: the front holds both sides, ordered by cost."""
    found = evolved(case, objectives=["lcts", "co2"], evaluations=16)
    front = found["front"]
    assert len(front) > 1 and all(item["feasible"] for item in front)
    assert not any(dominates(a, b, ["lcts", "co2"]) for a in front for b in front if a is not b)
    costs = [item["metrics"]["lcts"].value for item in front]
    assert costs == sorted(costs) and found["best"]["metrics"]["lcts"].value == costs[0]
    assert {item["structure"]["x"] for item in front} == {True, False}
    assert all(item["front"] >= 1 for item in found["history"])


def test_a_leading_minus_maximises(evolving, case):
    """``-co2`` seeks the most emissions: the pump on and the largest rangeability."""
    found = evolved(case, objectives="-co2", evaluations=16)
    assert found["best"]["structure"]["x"]
    co2 = [item["best"]["co2"] for item in found["history"]]
    assert co2 == sorted(co2) and found["best"]["metrics"]["co2"].value == co2[-1]


def test_the_result_is_plain_json(evolving, case):
    """``to_dict`` dumps as it is, with each plant as its plant dict."""
    found = evolved(case, objectives=["lcts", "co2"])
    plain = json.loads(json.dumps(found.to_dict(), allow_nan=False))
    assert set(plain) == {
        "best",
        "front",
        "history",
        "evaluations",
        "invalid",
        "structures",
        "rejected",
        "objectives",
        "budget",
    }
    assert plain["best"]["plant"] == found["best"]["plant"].to_dict()
    assert plain["best"]["metrics"]["lcts"].keys() == {"value", "unit"}
    assert plain["best"]["parameters"]["x"] is found["best"]["structure"]["x"]
    assert len(plain["front"]) == len(found["front"])


def test_the_search_leaves_the_plant_alone(evolving, case):
    """Every run is of another plant; the superstructure stays."""
    plant = superplant()
    before = plant.to_dict()
    evolved(case, plant=plant)
    assert plant.to_dict() == before and all(item is not plant for item, _, _ in evolving)


def test_polish_searches_the_best_design_again_on_top_of_the_budget(evolving, case):
    """``minimize`` of the best design adds its runs and a design at least as good."""
    plain = evolved(case, population=10, evaluations=10)
    polished = evolved(case, population=10, evaluations=10, polish=1)
    assert polished["evaluations"] > plain["evaluations"]
    assert len(evolving) == plain["evaluations"] + polished["evaluations"]
    assert polished["best"]["metrics"]["lcts"].value <= plain["best"]["metrics"]["lcts"].value
    assert np.isfinite(polished["best"]["metrics"]["lcts"].value)


def evolve_settings(**changes):
    """Return the dict of a study file of the method ``evolve``, with ``changes``."""
    data = {"format": 1, "kind": "study", "name": "test", "cases": ["case.json"]}
    data |= {"plants": ["one.json"], "method": "evolve", "objectives": ["lcts", "co2"]}
    data |= {"evaluations": 12, "population": 4, "seed": 0, "polish": 0}
    return data | changes


def issues_of(data):
    """Return ``{path: kind}`` of the issues ``Study.from_dict`` raises for ``data``."""
    with pytest.raises(ValidationError) as refused:
        gm.Study.from_dict(data)
    return {item.path: item.kind for item in refused.value.issues}


def test_a_study_of_evolve_reads_and_round_trips():
    """The settings are read as given, ``objectives`` as a tuple; one metric is a list of one."""
    study = gm.Study.from_dict(evolve_settings())
    assert study.to_dict() == evolve_settings()
    assert study.method == "evolve" and study.objectives == ("lcts", "co2")
    assert (study.evaluations, study.population, study.seed, study.polish) == (12, 4, 0, 0)
    assert gm.Study.from_dict(evolve_settings(objectives="lcts")).objectives == ("lcts",)


def test_a_study_of_evolve_needs_every_setting_and_refuses_objective():
    """Each of the five settings is missing alone; ``objective`` belongs to ``minimize``."""
    for key in REQUIRED["evolve"]:
        data = {k: v for k, v in evolve_settings().items() if k != key}
        assert issues_of(data) == {key: "missing"}
    assert issues_of(evolve_settings(objective="lcts")) == {"objective": "incompatible"}
    assert issues_of(evolve_settings(objectives=["lcox"])) == {"objectives[0]": "not_allowed"}
    assert issues_of(evolve_settings(polish=-1)) == {"polish": "incompatible"}


def test_another_method_refuses_the_settings_of_evolve():
    """``minimize`` reads none of ``objectives``, ``population`` and ``polish``."""
    data = evolve_settings(method="minimize", objective="lcts")
    assert issues_of(data) == {
        "objectives": "incompatible",
        "population": "incompatible",
        "polish": "incompatible",
    }


def test_a_study_of_evolve_refuses_a_population_of_one():
    """The schema of ``study.json`` asks for two candidates at least; the reader should too."""
    assert gm.Study.schema()["properties"]["population"]["minimum"] == 2
    assert issues_of(evolve_settings(population=1)) == {"population": "incompatible"}


def test_the_kinds_list_evolve_with_its_settings():
    """A title, a description and the five settings it requires, closed."""
    found = {item["kind"]: item for item in gm.study.kinds()}
    item = found["evolve"]
    assert item["use"] == "method" and item["title"] and item["description"].endswith(".")
    settings = item["settings"]
    assert settings["required"] == ["objectives", "evaluations", "population", "seed", "polish"]
    assert set(settings["properties"]) == set(settings["required"]) | {"stop"}
    assert settings["additionalProperties"] is False
    assert settings["properties"]["population"]["minimum"] == 2
    assert settings["properties"]["polish"]["minimum"] == 0


def test_the_first_generation_is_each_valid_structure_with_the_values_of_the_plant(evolving, case):
    """A budget of one generation runs the four valid structures, every value as given."""
    found = evolved(case, evaluations=4)
    assert found["evaluations"] == len(evolving) == 4 and len(found["history"]) == 1
    ran = [({"x", "y"} & names_of(plant), plant) for plant, _, _ in evolving]
    assert sorted(sorted(names) for names, _ in ran) == [[], ["x"], ["x", "y"], ["y"]]
    assert all(plant.a.rangeability == 30.0 for _, plant in ran)
    assert all(plant.x.flow == 3.0 for names, plant in ran if "x" in names)
