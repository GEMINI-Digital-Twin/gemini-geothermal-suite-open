"""``gm.check``: a producer's riser and well are one path cut at the pump (geomind QA-321)."""

import copy

import gemini as gm
from tests.fixtures.sample_cases import sample_case, template_dict

PLANT = "HackathonPlant"
RISER = "params.d0.riser.section_length"


def split(dict_, riser, well, pump):
    """Return a copy of a plant dict whose first producer has its own riser and well paths."""
    found = copy.deepcopy(dict_)
    limb = found["params"]["d0"]
    limb["riser"]["section_length"] = {"value": riser, "unit": "m"}
    limb["well"]["section_length"] = {"value": well, "unit": "m"}
    for part in ("riser", "well"):
        limb[part]["esp_depth"] = {"value": pump, "unit": "m"}
    return found


def test_a_riser_and_a_well_each_with_its_own_part_of_the_path_are_named():
    """Riser [1500] m and well [2000] m, pump at 1500 m: a 2000 m producer, not the 3500 m meant."""
    issues = gm.check(
        gm.Plant.from_dict(split(template_dict(PLANT), [1500.0], [2000.0], 1500.0)), sample_case()
    )
    [issue] = [item for item in issues if item.path == RISER]
    assert issue.kind == "incompatible" and "ONE path cut at esp_depth" in issue.message


def test_a_producer_with_one_whole_path_has_no_such_issue():
    """The sample plant, and one whose riser and well both hold the whole path."""
    case = sample_case()
    assert not [
        item
        for item in gm.check(gm.Plant.from_dict(template_dict(PLANT)), case)
        if item.path == RISER
    ]
    whole = split(template_dict(PLANT), [3500.0], [3500.0], 1500.0)
    assert not [item for item in gm.check(gm.Plant.from_dict(whole), case) if item.path == RISER]
