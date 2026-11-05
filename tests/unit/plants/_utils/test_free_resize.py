"""A plant without a class on one doublet varies its doublet count (geomind QA-129)."""

import re

import gemini as gm
from gemini.plants._utils.resize import resized
from gemini.study._utils.variables import counts
from tests.fixtures.sample_cases import template_dict


def free_plant():
    """Return the one-doublet heating plant written without its class."""
    data = template_dict("HeatingPlant")
    data["size"] = {"doublets": {"value": 1}}
    data["params"] = {k: v for k, v in data["params"].items() if not re.match(r"d[1-9]", k)}
    flat = gm.Plant.from_dict(data).to_dict(structure=True)
    for key in ("type", "size"):
        flat.pop(key, None)
    flat["params"].pop("depth", None)
    return gm.Plant.from_dict(flat)


def test_a_free_plant_takes_a_doublet_range_and_keeps_it():
    plant = free_plant().set_range("size.doublets", 1, 3)
    again = gm.Plant.from_dict(plant.to_dict())
    assert counts(again) == [1, 2, 3]


def test_a_free_plant_resized_joins_the_doublets_in_parallel():
    plant = resized(free_plant(), 3)
    names = [name for name, _ in plant.named_children()]
    assert {"d0", "d1", "d2"} <= set(names)
    sources = {item["source"] for item in plant.to_dict()["connections"]}
    assert {"d1.supply_out", "d2.supply_out", "production_mixers.1.fluid_out"} <= sources
    targets = [item["target"] for item in plant.to_dict()["connections"]]
    assert {"d0.power_in", "d1.power_in", "d2.power_in"} <= set(targets)
