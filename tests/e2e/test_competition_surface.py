"""The calls and files of ``examples/hackathon.py`` and ``examples/hackathon_2026``, pinned.

Anything the competition runs must stay as it is: the signatures it calls, the file formats it
reads and the fields and numbers it prints. A short ranking of two plants stands for the full one.
"""

import inspect
import json
from pathlib import Path

import pytest

import gemini as gm

SAMPLE = Path(__file__).parents[2] / "examples" / "hackathon_2026"

SIGNATURES = {
    "Study.from_json": (gm.Study.from_json, ["path"]),
    "Study.from_dict": (gm.Study.from_dict, ["data", "files", "folder"]),
    "Study.run": (gm.Study.run, ["plants"]),
    "Plant.from_json": (gm.Plant.from_json, ["path"]),
    "Case.from_json": (gm.Case.from_json, ["path"]),
    "runtime.settings": (gm.runtime.settings, ["backend", "changes"]),
}
"""Parameter names, in order, of every public call the competition scripts make."""


def names(function):
    """Return the parameter names of a callable without ``self`` and ``cls``."""
    return [n for n in inspect.signature(function).parameters if n not in ("self", "cls")]


@pytest.fixture(scope="module")
def ranking():
    """Run the sensitivity of two plants of the competition sample once."""
    data = json.loads((SAMPLE / "study_sensitivity.json").read_text())
    data["plants"] = ["plants/HackathonPlant.json", "plants/HeatingPlant.json"]
    return gm.Study.from_dict(data, folder=SAMPLE).run()


@pytest.mark.e2e
@pytest.mark.parametrize("key", SIGNATURES)
def test_the_calls_of_the_competition_scripts_keep_their_signature(key):
    """Names and order of the parameters of each call used by hackathon.py."""
    function, expected = SIGNATURES[key]
    assert names(function) == expected, key


@pytest.mark.e2e
def test_the_files_of_the_competition_sample_load():
    """The case, the economics, the plants of both folders and the four studies read as stored."""
    assert gm.Case.from_json(SAMPLE / "case.json")
    for folder in ("plants", "plants_brief"):
        for path in sorted((SAMPLE / folder).glob("*.json")):
            assert gm.Plant.from_json(path).to_dict(), path
    for name in ("study", "study_brief", "study_sample", "study_sensitivity"):
        assert gm.Study.from_json(SAMPLE / f"{name}.json").to_dict()["kind"] == "study"
    assert json.loads((SAMPLE / "economics.json").read_text())["kind"] == "economics"


@pytest.mark.e2e
def test_the_ranking_has_the_fields_and_numbers_the_script_prints(ranking):
    """The comparison table, the runs and their verdicts, as hackathon.py reads them."""
    (name,) = ranking.comparison
    frame = ranking.comparison[name].to_frame()
    assert list(frame.columns) == ["lcts [EUR/MWh]", "rank_lcts", "pareto", "feasible"]
    assert [run.plant_name for run in ranking.runs] == ["HackathonPlant", "HeatingPlant"]
    assert list(frame["lcts [EUR/MWh]"]) == pytest.approx([48.478634, 47.813020], rel=1e-5)
    assert list(frame["rank_lcts"]) == [1, 2]
    assert list(frame["feasible"]) == [True, False]
    run = ranking.runs[0]
    assert run.verdict["feasible"] is True and run.verdict["reasons"] == []
    assert list(run.found.to_frame().columns) == [
        "parameter",
        "metric",
        "low",
        "high",
        "value_unit",
        "at_low",
        "at_high",
        "effect",
        "unit",
    ]
    assert ranking.best[name] is None
    assert hasattr(run.plant, "to_dict") and run.report is not None


@pytest.mark.e2e
def test_the_result_writes_its_records(ranking, tmp_path):
    """``result.to_json(folder)`` writes the study, the case, and per plant the records."""
    ranking.to_json(tmp_path / "out")
    written = {path.name for path in (tmp_path / "out").rglob("*")}
    assert {"study.json", "case.json", "plant.json", "found.json", "verdict.json"} <= written
    assert {"report.json", "result.json", "series.csv", "source.json"} <= written


@pytest.mark.e2e
def test_the_draws_of_the_best_design_give_the_statistics_the_script_prints(ranking):
    """Study sample on the plant given in memory: keys and the mean in the printed unit."""
    data = json.loads((SAMPLE / "study_sample.json").read_text())
    data["samples"] = 2
    plants = {"HackathonPlant": ranking.runs[0].plant}
    found = gm.Study.from_dict(data, folder=SAMPLE).run(plants=plants).runs[0].found
    assert sorted(found) == ["samples", "summary"] and len(found["samples"]) == 2
    stats = found["summary"]["lcts"]
    assert sorted(stats) == ["failed", "mean", "p5", "p50", "p95"]
    assert stats["mean"].to("EUR/MWh").value == pytest.approx(49.4932, rel=1e-5)
