"""``gm.study.evolve`` runs the hackathon plant as a superstructure whose best structure is known.

The heat pump may be off, and the cooling is the absorption chiller with its cooler or nothing.
Without a chiller nothing serves the cooling users: their loop through the chiller would join
them to themselves, which the bypass drops, so those structures are refused before any run. The
best design has the chiller.

Slow: every trial simulates the hackathon plant over its year, and the first call compiles it,
seconds of CPU in all, over the budget of the fast tier.
"""

import json

import pytest

import gemini as gm
from tests.fixtures.sample_cases import HACKATHON_2026

pytestmark = pytest.mark.slow

STRUCTURES = 4
"""The structures of the superstructure: the heat pump on or off, the chiller or none."""


@pytest.fixture(scope="module")
def case():
    """Return the hackathon case."""
    return gm.Case.from_json(HACKATHON_2026 / "case.json")


@pytest.fixture(scope="module")
def plant(case):
    """Return the sized hackathon plant with the heat pump optional and a choice of chiller.

    Its ranges are removed, so the structure is all there is to search.
    """
    sized = gm.study.size(gm.Plant.from_json(HACKATHON_2026 / "plants/HackathonPlant.json"), case)
    for path in list(sized.ranges):
        sized.set_range(path)
    sized.set_optional("heat_pump")
    return sized.set_choice("chiller", {"absorption": ["chiller", "chiller_cooler"], "none": []})


def test_the_structures_without_a_chiller_are_not_valid(plant):
    """The heat pump can be bypassed; the cooling users cannot do without the chiller."""
    assert plant.structures() == [
        {"heat_pump": True, "chiller": "absorption"},
        {"heat_pump": False, "chiller": "absorption"},
    ]


def test_the_best_structure_has_the_chiller(plant, case):
    """Each structure is run or refused once, then the search stalls; the best meets the case."""
    found = gm.study.evolve(plant, case, "lcts", 6, 0, population=4, polish=0)
    assert found["evaluations"] == len(plant.structures()) < 6
    assert found["evaluations"] + found["invalid"] == STRUCTURES
    best = found["best"]
    assert best["structure"]["chiller"] == "absorption"
    assert best["feasible"] and best["reason"] is None
    assert found["front"] == [best]
    assert "chiller" in dict(best["plant"].named_modules())
    assert json.loads(json.dumps(found.to_dict(), allow_nan=False))["best"]["feasible"]


def test_worker_processes_give_the_result_of_one_process(plant, case):
    """``processes=2`` gives the same result as one process, in worker processes."""
    alone = gm.study.evolve(plant, case, ["lcts", "co2"], 6, 0, population=4, polish=0)
    with gm.runtime.settings(processes=2):
        together = gm.study.evolve(plant, case, ["lcts", "co2"], 6, 0, population=4, polish=0)
    assert json.dumps(together.to_dict(), sort_keys=True) == json.dumps(
        alone.to_dict(), sort_keys=True
    )
    assert all(item["structure"]["chiller"] == "absorption" for item in alone["front"])
