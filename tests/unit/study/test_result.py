"""The result of a study run: its runs as plain data and as records."""

import json

import gemini as gm
from tests.unit.study.test_study import run_settings, settings


def test_a_run_is_plain_json_with_its_verdict_metrics_and_what_the_method_found(folder, fake_runs):
    """The names, the verdict, the metrics, the note and the history of a search."""
    result = gm.Study.from_dict(settings(), folder=folder).run()
    (run,) = result.runs
    plain = json.loads(json.dumps(run.to_dict(), allow_nan=False))
    assert plain["plant_name"] == "one" and plain["verdict"] == {"feasible": True, "reasons": []}
    assert set(plain["metrics"]) == {"lcts", "co2"} and plain["note"] is None
    assert plain["found"]["evaluations"] == 5 and len(plain["found"]["history"]) == 5
    assert plain["found"]["best"]["plant"] is None


def test_the_result_names_its_best_run_of_each_case(folder, fake_runs):
    """The dict holds the name of the best plant of each case, not the plant."""
    result = gm.Study.from_dict(run_settings(), folder=folder).run()
    plain = json.loads(json.dumps(result.to_dict(), allow_nan=False))
    assert plain["best"] == {"shallow_district": {"plant_name": "one"}}
    assert plain["study"] == run_settings()
    assert plain["comparison"]["shallow_district"][0]["feasible"] is True


def test_without_an_objective_there_is_no_best_and_no_comparison(folder, fake_runs):
    """A study of the method ``run`` with no objective and no metrics only records the runs."""
    data = {
        key: item for key, item in run_settings().items() if key not in ("objective", "metrics")
    }
    result = gm.Study.from_dict(data, folder=folder).run()
    assert result.comparison == {} and result.best == {"shallow_district": None}
