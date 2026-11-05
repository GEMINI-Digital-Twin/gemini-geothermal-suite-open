"""``gm.Study``: the file, its checks, and the run that calls the functions of ``gm.study``."""

import json

import pytest

import gemini as gm
from gemini.plants._utils.resize import resized
from gemini.study import study
from tests.unit.study.conftest import shallow_case, shallow_plant


def settings(**changes):
    """Return the dict of a study file of the minimize method, with ``changes``."""
    data = {"format": 1, "kind": "study", "name": "test", "cases": ["case.json"]}
    data |= {"plants": ["one.json"], "method": "minimize", "objective": "lcts"}
    data |= {"evaluations": 5, "seed": 0, "metrics": ["co2"]}
    return data | changes


def run_settings(**changes):
    """Return the dict of a study file of the method ``run``."""
    return without(settings(method="run"), "evaluations", "seed") | changes


def without(data, *keys):
    """Return ``data`` without ``keys``."""
    return {key: item for key, item in data.items() if key not in keys}


def issues_of(data):
    """Return ``{path: kind}`` of the issues ``Study.from_dict`` raises for ``data``."""
    with pytest.raises(gm.errors.ValidationError) as refused:
        gm.Study.from_dict(data)
    return {item.path: item.kind for item in refused.value.issues}


def test_a_study_round_trips_through_its_dict():
    """The header first, the keys that are set, no default added."""
    study = gm.Study.from_dict(settings())
    assert study.to_dict() == settings()
    assert study.method == "minimize" and study.seed == 0 and study.names == ["lcts", "co2"]


def test_every_issue_is_found_at_once():
    """A missing setting, a key the method does not read and an unknown key."""
    found = issues_of(without(settings(samples=3, bogus=1), "evaluations"))
    assert found == {"evaluations": "missing", "samples": "incompatible", "bogus": "unknown_key"}


def test_what_a_method_needs_has_no_default():
    """``sample`` needs its metrics, the samples and the seed; none is filled in."""
    data = without(settings(method="sample"), "objective", "evaluations", "seed", "metrics")
    assert issues_of(data) == {"metrics": "missing", "samples": "missing", "seed": "missing"}
    assert issues_of(without(settings(), "seed", "evaluations", "objective")) == {
        "objective": "missing",
        "evaluations": "missing",
        "seed": "missing",
    }


def test_the_method_is_a_closed_list_and_a_metric_must_exist():
    """A method or a metric that does not exist is an issue with its path."""
    found = issues_of(settings(method="anneal", metrics=["co3"], objective="lcox"))
    assert found == {
        "method": "not_allowed",
        "metrics[0]": "not_allowed",
        "objective": "not_allowed",
    }


def test_an_older_file_or_the_wrong_kind_is_refused():
    """The header decides first."""
    assert issues_of(without(settings(), "kind"))[""] == "incompatible"
    assert "kind" in issues_of(settings(kind="plant"))


def test_the_settings_are_whole_numbers():
    """A budget of 0 or a text is an issue."""
    found = issues_of(settings(evaluations=0, seed="a"))
    assert found == {"evaluations": "incompatible", "seed": "incompatible"}


def test_the_files_are_read_from_the_folder_of_the_study(folder):
    """``from_json`` and ``check`` find the case and the plants; a missing file is an issue."""
    path = folder / "study.json"
    path.write_text(json.dumps(settings(plants=["one.json", "two.json"])))
    study = gm.Study.from_json(path)
    assert study.check() == []
    path.write_text(json.dumps(settings(plants=["gone.json"])))
    found = gm.Study.from_json(path).check()
    assert [item.path for item in found] == ["gone.json"]


def test_check_lists_what_the_plant_and_the_case_lack_and_never_raises(folder):
    """The pairs go through ``gm.check``; a template plant's missing parameters are for ``size``."""
    case = shallow_case()
    data = case.to_dict()
    data["requirements"] = []
    gm.Case.from_dict(data, files=case.files())
    study = gm.Study.from_dict(settings(prepare=["size"]), folder=folder)
    assert study.check() == []
    broken = json.loads((folder / "one.json").read_text())
    del broken["params"]["peak_boiler"]["capacity"]["value"]
    (folder / "one.json").write_text(json.dumps(broken))
    assert study.check() == []
    assert gm.Study.from_dict(settings(), folder=folder).check()[0].path.startswith("params.")


def test_the_files_can_be_given_in_memory(folder):
    """``files`` is ``{path: bytes}`` and wins over the folder."""
    files = {name: (folder / name).read_bytes() for name in ("case.json", "one.json")}
    files |= {
        path.relative_to(folder).as_posix(): path.read_bytes() for path in folder.rglob("*.csv")
    }
    study = gm.Study.from_dict(settings(), files=files)
    assert study.check() == []


def test_run_runs_every_plant_on_every_case_and_ranks_them(folder, fake_runs):
    """A search, then the best design simulated and reported; the best plant is a plant."""
    study = gm.Study.from_dict(settings(plants=["one.json", "two.json"]), folder=folder)
    result = study.run()
    assert [(run.plant_name, run.case_name) for run in result.runs] == [
        ("one", "shallow_district"),
        ("two", "shallow_district"),
    ]
    first, second = result.runs
    assert first.found["evaluations"] == 5 and first.note is None
    assert second.found is None and "no range and no options" in second.note
    assert first.metrics["lcts"].si <= second.metrics["lcts"].si
    assert set(first.metrics) == {"lcts", "co2"}
    entry = result.comparison["shallow_district"]
    assert [item["feasible"] for item in entry] == [True, True]
    best = result.best["shallow_district"]
    assert best is first and isinstance(best.plant, gm.Plant)
    assert first.plant is not first.source and first.plant.depth != first.source.depth


def test_a_search_is_written_in_display_units(folder, fake_runs):
    """The best trial and the history of the result JSON are in EUR/MWh, not currency/J."""
    result = gm.Study.from_dict(settings(plants=["one.json"]), folder=folder).run()
    found = result.to_dict()["runs"][0]["found"]
    assert found["best"]["unit"] == "EUR/MWh"
    assert {item["unit"] for item in found["history"]} == {"EUR/MWh"}


def test_the_plants_can_be_given_in_memory(folder, fake_runs):
    """A later study samples the best design of an earlier one."""
    study = gm.Study.from_dict(run_settings(), folder=folder)
    again = study.run(plants={"best": shallow_plant()})
    assert [run.plant_name for run in again.runs] == ["best"]
    assert again.runs[0].plant is again.runs[0].source


def test_an_infeasible_run_is_never_the_best(folder, fake_runs):
    """The plant on two doublets breaks a requirement: it can rank first and still not win."""
    two = resized(shallow_plant(), 2)
    study = gm.Study.from_dict(run_settings(objective="lcts"), folder=folder)
    result = study.run(plants={"one": shallow_plant(), "two": two})
    verdicts = {run.plant_name: run.verdict["feasible"] for run in result.runs}
    assert verdicts == {"one": True, "two": False}
    ranks = {
        entry["index"]: entry["ranks"]["lcts"] for entry in result.comparison["shallow_district"]
    }
    assert ranks == {0: 1, 1: 2}
    assert result.best["shallow_district"].plant_name == "one"


def test_a_study_is_written_as_run_records(folder, fake_runs, tmp_path_factory):
    """The study, the version, every input and each run's plant, report, verdict and series."""
    result = gm.Study.from_dict(settings(plants=["one.json"]), folder=folder).run()
    out = tmp_path_factory.mktemp("records")
    result.to_json(out)
    run = out / "shallow_district" / "one"
    for name in ("source.json", "plant.json", "report.json", "verdict.json", "series.csv"):
        assert (run / name).is_file()
    assert (out / "shallow_district" / "case.json").is_file()
    assert json.loads((out / "version.json").read_text())["gemini"] == gm.__version__
    assert json.loads((out / "study.json").read_text()) == settings(plants=["one.json"])
    full = gm.Plant.from_json(run / "plant.json")
    assert full.depth == result.runs[0].plant.depth
    assert json.loads((run / "verdict.json").read_text()) == {"feasible": True, "reasons": []}
    assert json.loads((out / "result.json").read_text())["best"] == {
        "shallow_district": {"plant_name": "one"}
    }


def test_the_schema_names_the_keys_the_reader_accepts():
    """``Study.schema()`` is closed on the keys of ``study.json``, and the methods are its enum."""
    schema = gm.Study.schema()
    assert set(schema["properties"]) == {*study.KEYS, "about"}
    assert schema["properties"]["method"]["enum"] == list(study.METHODS)
    assert schema["additionalProperties"] is False


def test_the_plants_of_a_study_run_in_worker_processes_as_in_turn(folder):
    """With ``processes`` > 1 the plants run at once and the result is the one of one process."""
    study = gm.Study.from_dict(run_settings(), folder=folder)
    plants = {"one": shallow_plant(), "two": resized(shallow_plant(), 2)}
    alone = study.run(plants=plants).to_dict()
    with gm.runtime.settings(processes=2):
        together = study.run(plants=plants).to_dict()
    assert json.dumps(together, sort_keys=True) == json.dumps(alone, sort_keys=True)


def test_an_evolve_study_too_small_for_its_polish_is_named_by_check(folder):
    """QA-282: polish needs 5 per variable; check says so when the study is made, not at its end."""
    data = without(settings(method="evolve"), "objective", "metrics")
    data |= {"objectives": ["lcts"], "evaluations": 4, "population": 2, "seed": 0, "polish": 1}
    found = [item for item in gm.Study.from_dict(data, folder=folder).check()]
    issue = next(item for item in found if item.path == "population")
    assert issue.code == "invalid_value"
    assert "population 2 is too small for polish: needs at least" in issue.message
    assert "raise population to" in issue.message and "or set polish 0" in issue.message
    quiet = gm.Study.from_dict(data | {"polish": 0}, folder=folder).check()
    assert all(item.path != "population" for item in quiet)
