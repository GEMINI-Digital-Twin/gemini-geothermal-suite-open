"""``gm.check``: well paths stated by hand must reach the doublet's depth (geomind QA-357)."""

import copy

import gemini as gm
from tests.fixtures.sample_cases import sample_case, template_dict

PLANT = "HackathonPlant"
WELL = "params.d0.well.section_length"


def stated(lengths, searched=True, depth=2500.0):
    """Return the sample plant dict with d0's well paths stated as ``lengths``."""
    found = copy.deepcopy(template_dict(PLANT))
    limb = found["params"]["d0"]
    limb["depth"] = {"value": depth, "unit": "m"} | (
        {"range": limb["depth"]["range"]} if searched else {}
    )
    for well in ("well", "riser", "injector"):
        limb[well]["section_length"] = {"value": lengths, "unit": "m"}
    return found


def issues_at(data, path=WELL):
    """Return the issues ``gm.check`` names at ``path`` for a plant dict on the sample case."""
    return [item for item in gm.check(gm.Plant.from_dict(data), sample_case()) if item.path == path]


def test_a_searched_depth_with_stated_well_paths_is_named():
    """The run: paths of 2500 m stated, depth searched 2000 to 3500 m."""
    [issue] = issues_at(stated([2500.0]))
    assert issue.kind == "incompatible" and "do not follow it" in issue.message


def test_a_stated_path_that_misses_the_depth_is_named_and_one_that_reaches_it_passes():
    """No range: the true vertical extent of the path against the depth."""
    [issue] = issues_at(stated([2500.0], searched=False, depth=2875.0))
    assert "2500.0 m true vertical depth" in issue.message
    assert not issues_at(stated([2875.0], searched=False, depth=2875.0))


def test_the_sample_plant_with_derived_paths_has_no_such_issue():
    """Paths derived from depth follow it, searched or not."""
    assert not issues_at(template_dict(PLANT))
