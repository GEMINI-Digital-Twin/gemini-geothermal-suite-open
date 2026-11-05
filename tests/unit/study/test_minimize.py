"""``gm.study.minimize`` on the shallow plant, with the run replaced by a known cost."""

import importlib
import json

import numpy as np
import pytest

import gemini as gm
from gemini._utils.jsonable import to_plain
from gemini.evaluate.verdict import Verdict, reason
from gemini.study._utils import trial
from gemini.study._utils.best import Best
from gemini.units import Quantity
from gemini.units.shapes import measure
from tests.fixtures import si
from tests.fixtures.errors import raises
from tests.unit.study.conftest import clean_verdict, shallow_case, shallow_plant, simulation

minimize_module = importlib.import_module("gemini.study.minimize")
DEPTH = {"depth": (Quantity(1000, "m"), Quantity(2000, "m"))}
COUNT = {"size.doublets": (1, 3)}


def searching(ranges, options=None, plant=None):
    """Return the shallow plant that searches only ``ranges`` ``{path: (min, max)}``."""
    plant = plant or shallow_plant()
    for path in plant.ranges:
        plant.set_range(path)
    for path, (low, high) in ranges.items():
        plant.set_range(path, min=low, max=high)
    for path, choices in (options or {}).items():
        plant.set_options(path, choices)
    return plant


def minimized(plant, objective="lcts", evaluations=5, seed=0, **keywords):
    """Return ``gm.study.minimize`` of ``plant`` on the shallow case."""
    return gm.study.minimize(plant, shallow_case(), objective, evaluations, seed, **keywords)


@pytest.fixture
def found(runs):
    """Return the search over 1 to 3 doublets and the depth."""
    return minimized(searching(COUNT | DEPTH), evaluations=10)


def test_the_ranges_of_the_plant_are_the_variables(found, runs):
    """Each of the three counts is searched alone, with the budget for the depth."""
    assert found["evaluations"] == len(found["history"]) == len(runs) == 30
    counts = {item.parts["parameters"]["size.doublets"].value for item in found["history"]}
    assert counts == {1, 2, 3}


def test_the_cheapest_count_wins_with_its_plant(found):
    """The cost model makes two doublets cheapest, near 1500 m."""
    best = found["best"]
    assert best.parts["parameters"]["size.doublets"].value == 2
    assert best.parts["parameters"]["depth"].value == pytest.approx(1500, abs=150)
    assert best.value == min(item.value for item in found["history"] if item.reason is None)
    design = best["plant"]
    assert design.size == {"doublets": 2}
    assert design.depth == best.parts["parameters"]["depth"].value


def test_the_best_design_is_a_plant_whose_file_runs_the_same(found, tmp_path):
    """``to_json`` of the best plant is a plant file; read back it gives the same metrics."""
    best = found["best"]["plant"]
    best.to_json(tmp_path / "best.json")
    again = gm.Plant.from_json(tmp_path / "best.json")
    case = shallow_case()
    for name in ("lcts", "co2"):
        one = trial.metric(best, case, None, name)
        assert trial.metric(again, case, None, name).value == one.value


def test_the_result_is_plain_json_with_the_plant_as_its_dict(found):
    """``to_plain`` gives the JSON form, the best plant as its plant dict."""
    text = json.dumps(to_plain(found), allow_nan=False)
    assert "peak_boiler" in text


def test_best_round_trips_through_json_without_an_encoder(runs):
    """``to_dict`` dumps as it is, quantities as ``{value, unit}``; ``from_dict`` reads it back."""
    best = minimized(searching(DEPTH))["best"]
    plain = json.loads(json.dumps(best.to_dict(), allow_nan=False))
    assert plain["plant"] == best["plant"].to_dict()
    assert plain["parameters"]["depth"].keys() == {"value", "unit"}
    assert plain["unit"] == "EUR/MWh" and plain["value"] == pytest.approx(best.si * 3.6e9)
    again = Best.from_dict(plain)
    assert again.si == pytest.approx(best.si)
    assert again.parts["parameters"]["depth"] == best.parts["parameters"]["depth"]
    assert again["plant"].to_dict() == best["plant"].to_dict()
    assert again.to_dict() == best.to_dict()


def test_a_best_without_a_trial_has_no_plant_in_its_json():
    """With no trial that ran, ``plant`` is ``None`` and the round trip keeps the reason."""
    empty = Best(None, "-", "every trial failed", {"parameters": None}, None)
    plain = json.loads(json.dumps(empty.to_dict()))
    assert plain["plant"] is None and plain["reason"] == "every trial failed"
    again = Best.from_dict(plain)
    assert again.value is None and again.plant is None and again.reason == "every trial failed"


def test_the_search_leaves_the_plant_and_the_case_alone(runs):
    """Every trial runs a copy."""
    plant, case = searching(DEPTH), shallow_case()
    before = plant.to_dict()
    gm.study.minimize(plant, case, "lcts", 5, 0)
    assert plant.to_dict() == before and case == shallow_case()
    assert all(copy is not plant for copy, _, _ in runs)


def test_the_same_call_gives_the_same_trials(runs):
    """A seed makes the trials; it has no default."""
    one, other = (minimized(searching(DEPTH), seed=0) for _ in "ab")
    assert one["history"] == other["history"]


def test_an_option_is_a_discrete_variable(runs, monkeypatch):
    """A choice is searched as an integer: both options are tried, and the cheaper one wins."""
    path = "heat_exchanger.arrangement"
    plant = searching({}, {path: ["counterflow", "parallel"]})
    cost = trial.metric

    def dearer_in_parallel(plant, case, results, name):
        extra = 5.0 if plant.heat_exchanger.arrangement == "parallel" else 0.0
        return measure(cost(plant, case, results, name).value + extra, "currency/J")

    monkeypatch.setattr(trial, "metric", dearer_in_parallel)
    result = minimized(plant)
    tried = {item.parts["parameters"][path] for item in result["history"]}
    assert tried == {"counterflow", "parallel"}
    assert result["best"].parts["parameters"][path] == "counterflow"
    assert result["best"]["plant"].heat_exchanger.arrangement == "counterflow"
    assert result["best"]["plant"].options == plant.options


def test_the_plant_without_a_doublet_range_keeps_its_count(runs):
    """Only the depth is searched: the number of doublets stays."""
    result = minimized(searching(DEPTH))
    assert result["evaluations"] == 5
    assert result["best"]["plant"].size == {"doublets": 1}


def test_a_limit_on_a_metric_is_a_requirement_of_the_case_not_an_argument(runs):
    """The rules of third parties are the case's: ``constraints`` is not an argument."""
    with pytest.raises(TypeError, match="constraints"):
        gm.study.minimize(
            searching(DEPTH), shallow_case(), "lcts", 5, 0, constraints=[{"metric": "co2"}]
        )
    assert runs == []


def test_a_leading_minus_maximises(runs):
    """The value keeps the sign of the metric."""
    result = minimized(searching(DEPTH), "-co2")
    assert result["best"].value == max(item.value for item in result["history"])


def test_every_trial_failing_leaves_no_best(monkeypatch, runs):
    """No value and no plant, with the reason."""

    def failing(plant, case, plan=None):
        raise gm.errors.ValidationError("no run", code="invalid_value")

    monkeypatch.setattr(trial, "simulation_steps", simulation(failing))
    result = minimized(searching(DEPTH))
    assert result["best"].value is None and result["best"].plant is None
    assert "every trial" in result["best"].reason


def test_a_plant_that_states_nothing_to_search_is_refused_before_any_run(runs):
    """Nothing to search: ``invalid_design`` naming the plant parameters."""
    with raises(gm.errors.ValidationError, "invalid_design") as refused:
        minimized(searching({}))
    assert refused.value.path == "params" and runs == []


def test_the_evaluations_and_the_seed_have_no_default(runs):
    """A call without either does not run."""
    with pytest.raises(TypeError, match="evaluations"):
        gm.study.minimize(searching(DEPTH), shallow_case(), "lcts", seed=0)
    with pytest.raises(TypeError, match="seed"):
        gm.study.minimize(searching(DEPTH), shallow_case(), "lcts", 5)
    assert runs == []


@pytest.mark.parametrize(
    ("arguments", "code"),
    [
        ({"objective": "lcox"}, "unknown_name"),
        ({"evaluations": 4}, "invalid_value"),
    ],
)
def test_a_search_that_does_not_fit_is_refused(arguments, code, runs):
    """Before any simulation."""
    call = {"objective": "lcts", "evaluations": 5, "seed": 0} | arguments
    with raises(gm.errors.ValidationError, code):
        gm.study.minimize(searching(DEPTH), shallow_case(), **call)
    assert runs == []


def test_a_plant_that_is_not_ready_for_the_case_is_refused_with_every_issue(runs):
    """``gm.check`` runs first: a requirement on a role the plant lacks is named."""
    case = shallow_case(requirements=[requirement_on("chp")])
    with raises(gm.errors.ValidationError, "invalid_value") as refused:
        gm.study.minimize(searching(DEPTH), case, "lcts", 5, 0)
    assert "requirements[0].on" in str(refused.value) and runs == []


def requirement_on(role):
    """Return a requirement dict on ``role`` that no shallow plant can meet."""
    return {
        "name": "n",
        "on": role,
        "quantity": "power_output",
        "over": "each",
        "unit": "W",
        "min": 0,
    }


def failing_above(limit):
    """Return a verdict that fails when the depth is above ``limit`` m, with a violation."""

    def judged(plant, case, results):
        if plant.depth <= limit:
            return clean_verdict(plant, case, results)
        found = reason("requirement", "d0.depth", "too deep", violation=(plant.depth - limit) / 1e3)
        return Verdict(feasible=False, reasons=[found])

    return judged


def test_the_cheapest_trial_that_breaks_a_limit_is_not_best(monkeypatch, runs):
    """The cost falls with a shallower depth in this model only above 1500 m: a limit decides."""
    monkeypatch.setattr(trial, "verdict", failing_above(1200))
    result = minimized(searching(DEPTH))
    assert result["feasible"] is True
    assert result["best"].parts["parameters"]["depth"].value <= 1200
    broken = [item for item in result["history"] if item.reason]
    assert broken and all(item.reason["name"] == "d0.depth" for item in broken)
    assert all(item.parts["violation"] > 0 for item in broken)


def test_without_a_feasible_trial_the_least_violating_one_is_best(monkeypatch, runs):
    """``feasible`` is false and the best trial is the shallowest, the nearest to the limit."""
    monkeypatch.setattr(trial, "verdict", failing_above(900))
    result = minimized(searching(DEPTH))
    assert result["feasible"] is False and result["best"].reason["name"] == "d0.depth"
    violations = [item.parts["violation"] for item in result["history"]]
    assert result["best"].parts["violation"] == min(violations)
    assert result["best"]["plant"].depth == result["best"].parts["parameters"]["depth"].value


def test_a_reason_no_design_can_change_does_not_rank_the_trials(monkeypatch, runs):
    """A service the plant has no unit for stays in the verdict of the run, not in the search."""

    def structural(plant, case, results):
        found = reason("requirement", "cold_delivered", "no cold for the cooling")
        return Verdict(feasible=False, reasons=[found])

    monkeypatch.setattr(trial, "verdict", structural)
    result = minimized(searching(DEPTH))
    assert result["feasible"] is True
    assert all(item.reason is None for item in result["history"])


def test_a_trial_that_raises_is_infeasible_and_the_search_goes_on(monkeypatch, runs):
    """A physics error at some depth costs the trial, not the search."""
    cost = trial.metric

    def deep_fails(plant, case, results, name):
        if plant.depth > 1700:
            raise gm.errors.ValidationError("negative head", code="invalid_value")
        return cost(plant, case, results, name)

    monkeypatch.setattr(trial, "metric", deep_fails)
    result = minimized(searching(DEPTH))
    failed = [item for item in result["history"] if item.value is None]
    assert failed and all(item.parts["violation"] == trial.LARGEST_VIOLATION for item in failed)
    assert result["feasible"] and result["best"].parts["parameters"]["depth"].value <= 1700


def test_the_plant_as_given_is_one_of_the_trials(runs):
    """The search starts from the plant, so its depth is tried and the best is never worse."""
    plant = searching(DEPTH)
    si.assign(plant, "depth", 1234.0)
    found = minimized(plant)
    depths = [item.parts["parameters"]["depth"].value for item in found["history"]]
    assert 1234.0 in depths
    start = next(
        item for item in found["history"] if item.parts["parameters"]["depth"].value == 1234.0
    )
    assert found["best"].value <= start.value


def test_a_trial_with_failed_steps_is_infeasible_and_never_the_best(failing_runs):
    """Deep trials fail: the reason is the failed steps of the verdict; the best ran clean."""
    result = minimized(searching(DEPTH), evaluations=10)
    deep = [i for i in result["history"] if i.parts["parameters"]["depth"].value > 1700]
    assert deep and all(i.reason["kind"] == "failed_step" for i in deep)
    assert all(i.parts["violation"] == trial.LARGEST_VIOLATION for i in deep)
    assert result["feasible"] and result["best"].parts["parameters"]["depth"].value <= 1700


def test_the_first_population_is_one_batch_and_the_trials_after_it_run_one_by_one(
    monkeypatch, runs
):
    """Each candidate of a later generation is built from the members replaced before it."""
    sizes = []
    real = minimize_module.run_trials

    def counting(shared, case, plan, valued, names, judge):
        sizes.append(len(valued))
        return real(shared, case, plan, valued, names, judge)

    monkeypatch.setattr(minimize_module, "run_trials", counting)
    found = minimized(searching(DEPTH), evaluations=10)
    assert sizes[0] == 5 and set(sizes[1:]) == {1} and sum(sizes) == found["evaluations"] == 10


def test_a_search_with_batches_has_the_history_of_a_search_that_runs_every_trial_alone(
    monkeypatch, runs
):
    """The same trials in the same order with the same objectives, whatever the batches."""
    batched = minimized(searching(DEPTH), evaluations=10, seed=4)
    real = minimize_module.run_trials

    def alone(shared, case, plan, valued, names, judge):
        return [real(shared, case, plan, [values], names, judge)[0] for values in valued]

    monkeypatch.setattr(minimize_module, "run_trials", alone)
    single = minimized(searching(DEPTH), evaluations=10, seed=4)
    assert [item.to_dict() for item in batched["history"]] == [
        item.to_dict() for item in single["history"]
    ]
    assert batched["best"].to_dict() == single["best"].to_dict()


def test_a_feasible_trial_whose_objective_is_nan_is_infeasible_and_never_the_best(
    monkeypatch, runs
):
    """A run that gives a figure that is not a number is no better than one that gives none."""
    cost = trial.metric

    def deep_is_nan(plant, case, results, name):
        if plant.depth > 1700:
            return measure(float("nan"), "currency/J")
        return cost(plant, case, results, name)

    monkeypatch.setattr(trial, "metric", deep_is_nan)
    result = minimized(searching(DEPTH), evaluations=10)
    lost = [item for item in result["history"] if item.parts["parameters"]["depth"].value > 1700]
    assert lost and all(item.value is None and item.reason for item in lost)
    assert all(item.parts["violation"] == trial.LARGEST_VIOLATION for item in lost)
    assert result["feasible"] and result["best"].parts["parameters"]["depth"].value <= 1700


def test_the_ranking_of_a_nan_objective_is_that_of_an_infeasible_trial():
    """The search sees a trial that is not a number above every feasible one."""
    assert minimize_module._is_number(1.5) and not minimize_module._is_number(float("nan"))
    assert not minimize_module._is_number(None)
    assert minimize_module._ranked(1.0, 5.0, None, 0.0) < 1


def test_a_trial_that_raises_something_other_than_a_gemini_error_ends_the_search(monkeypatch, runs):
    """Pinned for the owner (t2.md): only ``GeminiError`` is a failed trial."""
    cost = trial.metric

    def deep_breaks(plant, case, results, name):
        if plant.depth > 1700:
            raise ValueError("a bug in a module")
        return cost(plant, case, results, name)

    monkeypatch.setattr(trial, "metric", deep_breaks)
    with pytest.raises(ValueError, match="a bug in a module"):
        minimized(searching(DEPTH), evaluations=10)


def test_the_result_is_a_search_with_its_history_as_plain_json(found):
    """``to_dict`` holds the best, without its plant, and every trial of the history."""
    assert isinstance(found, gm.study.Search) and isinstance(found, dict)
    plain = json.loads(json.dumps(found.to_dict(), allow_nan=False))
    assert plain.keys() == {"best", "feasible", "evaluations", "history"}
    assert plain["best"]["plant"] is None and plain["feasible"] == found["feasible"]
    assert len(plain["history"]) == plain["evaluations"] == found["evaluations"]
    assert plain["history"][0]["parameters"]["depth"].keys() == {"value", "unit"}
    assert all("violation" in entry for entry in plain["history"])


def test_a_search_of_four_variables_runs_its_budget_never_four_times_it():
    """QA-285: five per variable was a multiplier of the variables: twenty evaluations ran eighty."""
    _, members, generations, polish = minimize_module._generations(20, 4)
    assert members * (generations + 1) + polish == 20 and polish >= 10
    _, members, generations, polish = minimize_module._generations(5, 1)
    assert (members, generations, polish) == (5, 0, 0)


def test_the_polish_finds_a_better_design_next_to_the_only_feasible_one():
    """QA-285: of eighty random points only the start was feasible, so it came back as best.

    Feasible is a narrow band of the second variable around the start; the cost falls as the
    first variable falls, which the compass search follows within its budget.
    """
    from gemini.study._utils.variables import Variable

    found = [Variable("a", ("a",), 3.0, 30.0), Variable("b", ("b",), 0.0, 1.0)]
    trials = []

    def evaluated(point):
        trials.append(point.copy())
        feasible = abs(point[1] - 0.5) < 0.01
        return point[0] / 100 if feasible else 3.0

    start = np.array([9.75, 0.5])
    minimize_module._polish(evaluated, found, (evaluated(start), start), 12)
    assert len(trials) <= 13
    assert min(point[0] for point in trials if abs(point[1] - 0.5) < 0.01) == 3.0


def test_a_search_whose_every_trial_failed_names_the_first_failure():
    """QA-359: six studies ended with no result and no cause; the reason now names it."""
    from gemini.study.minimize import _best

    failed = Best(None, "-", "d0.esp: flow = 8808335 m3/s gives head = 3824522 Pa", {}, None)
    found, feasible = _best([failed, failed], 1, None)
    assert found.value is None and found.plant is None and not feasible
    assert found.reason == (
        "every trial failed; the first: d0.esp: flow = 8808335 m3/s gives head = 3824522 Pa"
    )
