"""A ``range`` on a case value changes no number: ``simulate`` and ``size`` give the same."""

import pandas as pd
import pytest

import gemini as gm
from tests.fixtures.sample_cases import SHALLOW_DISTRICT, shallow_case

PLANT = SHALLOW_DISTRICT / "plants/HeatingHeatPumpCoolingPlant.json"


def ranged_case():
    """Return the shallow case with a ``range`` on the air temperature, and the case without."""
    base = shallow_case()
    data = base.to_dict()
    data["economics"] = base.economics.to_dict()
    data["site"]["air"]["temperature"]["range"] = {"min": -5, "max": 20}
    with pytest.warns(gm.errors.GeminiWarning):
        ranged = gm.Case.from_dict(data, files=base.files())
    return base, ranged


def test_simulate_gives_the_same_numbers_with_a_range():
    """Nothing reads the range: the results equal those of the case without it."""
    base, ranged = ranged_case()
    plant = gm.Plant.from_json(PLANT)
    first = gm.simulate(plant, base).to_frame()
    second = gm.simulate(plant, ranged).to_frame()
    pd.testing.assert_frame_equal(first, second, rtol=0, atol=0)


def test_size_gives_the_same_plant_with_a_range():
    """``size`` raises on the issues of the check; a warning is none of them."""
    base, ranged = ranged_case()
    plant = gm.Plant.from_json(PLANT)
    assert gm.study.size(plant, ranged).to_dict() == gm.study.size(plant, base).to_dict()
