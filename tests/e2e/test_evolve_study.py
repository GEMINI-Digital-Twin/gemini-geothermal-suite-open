"""An agent's path through ``evolve``: JSON files in, ``Study.run``, JSON files out.

An agent drives gemini with files: a superstructure plant file, a case and a ``study.json`` of the
method ``evolve``. No Python object is built by hand; the result is read back as plain JSON.
"""

import json
import shutil
from pathlib import Path

import pytest

import gemini as gm

pytestmark = pytest.mark.e2e

EXAMPLES = Path(__file__).parents[2] / "examples"
STUDY = {
    "format": 1,
    "kind": "study",
    "name": "superstructure",
    "cases": ["hackathon_2026/case.json"],
    "plants": ["hackathon_superstructure/plants/HackathonSuperstructure.json"],
    "prepare": ["size"],
    "method": "evolve",
    "objectives": ["lcts", "co2"],
    "evaluations": 32,
    "population": 16,
    "seed": 0,
    "polish": 0,
    "stop": {"generations": 4},
}
"""The study an agent writes: a small budget, both objectives, a stop when the front is still."""


@pytest.fixture(scope="module")
def written(tmp_path_factory):
    """Copy the sample files, write the study, check it, run it and write the records."""
    folder = tmp_path_factory.mktemp("agent")
    for name in ("hackathon_2026", "hackathon_superstructure"):
        shutil.copytree(EXAMPLES / name, folder / name)
    (folder / "study.json").write_text(json.dumps(STUDY))
    study = gm.Study.from_json(folder / "study.json")
    issues = [item for item in study.check() if not item.is_warning]
    study.run().to_json(folder / "out")
    return folder / "out", issues


def test_the_study_is_ready_before_any_simulation(written):
    """``Study.check`` finds nothing to change: the agent may run it."""
    assert written[1] == []


def test_the_records_hold_the_front_and_why_each_structure_ranks(written):
    """``found.json`` is plain JSON: the front, the best, every structure and the budget."""
    out, _ = written
    case = json.loads((out / "result.json").read_text())["runs"][0]["case_name"]
    found = json.loads((out / case / "HackathonSuperstructure" / "found.json").read_text())
    assert found["objectives"] == ["lcts", "co2"]
    assert found["front"] and all(item["feasible"] for item in found["front"])
    assert {item["structure"]["compression"] for item in found["front"]} <= {"on", "off"}
    assert found["budget"]["evaluations"] <= STUDY["evaluations"]
    assert len(found["structures"]) + len(found["rejected"]) >= len(found["structures"])
    assert all(item["structure"] for item in found["structures"])
    assert found["best"]["plant"]["kind"] == "plant"


def test_the_best_plant_runs_again_from_its_file(written):
    """The best plant the agent finds is a plant file that runs as it is."""
    out, _ = written
    case_name = json.loads((out / "result.json").read_text())["runs"][0]["case_name"]
    folder = out / case_name / "HackathonSuperstructure"
    plant = gm.Plant.from_json(folder / "plant.json")
    case = gm.Case.from_json(out / case_name / "case.json")
    report = gm.evaluate.report(plant, case, gm.simulate(plant, case))
    found = json.loads((folder / "found.json").read_text())
    assert report["lcts"].to("EUR/MWh").value == pytest.approx(
        found["best"]["metrics"]["lcts"]["value"], rel=1e-6
    )
