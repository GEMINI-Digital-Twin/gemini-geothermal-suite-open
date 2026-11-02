"""One plant on one case through the method of a study."""

import pytest

import gemini as gm
from gemini.study._utils import execute
from tests.unit.study.conftest import shallow_case, shallow_plant
from tests.unit.study.test_study import run_settings, settings


def test_every_method_has_its_function():
    """The closed list of the methods of ``study.json`` is the one the study reads."""
    assert tuple(execute.METHODS) == gm.study.study.METHODS


def test_a_study_that_prepares_sizes_the_plant_first(fake_runs, monkeypatch):
    """``size`` runs before the method, with the criterion in the plant."""
    seen = []

    def sized(plant, case):
        seen.append(plant)
        return plant

    monkeypatch.setattr(execute, "size", sized)
    study = gm.Study.from_dict(run_settings(prepare=["size"]))
    design, found, note, _, _ = execute.executed(study, shallow_plant(), shallow_case())
    assert len(seen) == 1 and found is None and note is None and design is seen[0]


def test_a_search_gives_the_best_plant_and_a_run_as_it_is_gives_the_plant(fake_runs):
    """``minimize`` returns the best design; a plant without ranges is run as it is, with a note."""
    study = gm.Study.from_dict(settings())
    plant = shallow_plant()
    for path in plant.ranges:
        plant.set_range(path)
    design, found, note, _, _ = execute.executed(study, plant, shallow_case())
    assert design is plant and found is None and "no range" in note
    plant.set_range("depth", min=gm.units.Quantity(1000, "m"), max=gm.units.Quantity(2000, "m"))
    design, found, note, _, _ = execute.executed(study, plant, shallow_case())
    assert design is found["best"]["plant"] and note is None


@pytest.mark.parametrize("method", ["sample", "sensitivity"])
def test_the_spread_methods_read_the_metrics_of_the_study(method, monkeypatch, fake_runs):
    """The names go to the function of the method."""
    seen = {}

    def spread(plant, case, names, *rest):
        seen["names"] = names
        return {"names": names}

    monkeypatch.setattr(execute, "sample", spread)
    monkeypatch.setattr(execute, "sensitivity", spread)
    data = settings(method=method, samples=3) if method == "sample" else settings(method=method)
    data = {k: v for k, v in data.items() if method == "sample" or k not in ("evaluations", "seed")}
    data = {k: v for k, v in data.items() if method != "sample" or k != "evaluations"}
    study = gm.Study.from_dict(data)
    _, found, _, _, _ = execute.executed(study, shallow_plant(), shallow_case())
    assert seen["names"] == ["lcts", "co2"] and found == {"names": ["lcts", "co2"]}
