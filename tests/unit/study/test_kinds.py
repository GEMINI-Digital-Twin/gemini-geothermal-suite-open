"""``gm.study.kinds``: the kinds of study in plain words with the settings of each."""

import json

import gemini as gm
from gemini.study.study import METHODS, PREPARE, REQUIRED


def test_every_method_and_the_size_step_has_a_title_and_a_description():
    """Four methods and the action before them, in plain text."""
    found = gm.study.kinds()
    assert [item["kind"] for item in found] == [*METHODS, *PREPARE]
    assert [item["use"] for item in found] == ["method"] * len(METHODS) + ["prepare"]
    assert all(item["title"] and item["description"].endswith(".") for item in found)
    assert json.loads(json.dumps(found)) == found and gm.study.kinds() is not found


def test_the_settings_are_the_keys_the_method_reads():
    """Objective, evaluations and seed for a search; none for a run."""
    settings = {item["kind"]: item["settings"] for item in gm.study.kinds()}
    assert list(settings["minimize"]["properties"]) == ["objective", "evaluations", "seed"]
    assert list(settings["sample"]["properties"]) == ["metrics", "samples", "seed"]
    assert list(settings["sensitivity"]["properties"]) == ["metrics"]
    assert settings["run"]["properties"] == {} == settings["size"]["properties"]
    for method in METHODS:
        assert settings[method]["required"] == list(REQUIRED[method])
        assert settings[method]["additionalProperties"] is False


def test_the_choices_are_the_metrics_a_study_can_read():
    """The objective is a cost or an emission, the metrics are those ``sample`` reads."""
    settings = {item["kind"]: item["settings"] for item in gm.study.kinds()}
    objective = settings["minimize"]["properties"]["objective"]
    assert objective["enum"] == [m["name"] for m in gm.evaluate.metrics() if m["objective"]]
    reads = settings["sample"]["properties"]["metrics"]["items"]["enum"]
    assert {"lcoh", "co2", "cop"} <= set(reads) and "temperature" not in reads
    assert settings["minimize"]["properties"]["evaluations"]["minimum"] == 1


def test_a_document_of_the_settings_is_read_by_the_study():
    """The schema of ``minimize`` and the reader of ``study.json`` agree on a sample."""
    data = {
        "format": 1,
        "kind": "study",
        "name": "s",
        "cases": ["c.json"],
        "plants": ["p.json"],
        "method": "minimize",
        "objective": "lcoh",
        "evaluations": 10,
        "seed": 1,
    }
    assert gm.Study.from_dict(data).objective == "lcoh"
