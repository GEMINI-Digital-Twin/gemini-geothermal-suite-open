"""The sample cases of ``examples/``: only examples and tests read them."""

import json
from pathlib import Path

import gemini as gm
from gemini.engine.apply import apply_case
from tests.fixtures import paths

HACKATHON_2026 = paths.example("hackathon_2026")
SHALLOW_DISTRICT = paths.example("shallow_district")
SAMPLE_PLANT = "HeatingCoolingPlant"
"""The class of the main candidate; every candidate is in ``plants/``."""
TEMPLATES = (
    "HeatingPlant",
    "HeatingAbsorptionCoolingPlant",
    "HeatingHeatPumpCoolingPlant",
    "HeatingFullCoolingPlant",
)


CASE_VALUES = json.loads((Path(__file__).parent / "plant_case_values.json").read_text())
"""``{plant: {path: leaf}}``: the values of a case that the unit tests of the plants set."""


def _quantity(leaf):
    """Return the value of a leaf as a ``Quantity``, or as it is when it has no unit."""
    if "unit" in leaf:
        return gm.units.Quantity(leaf["value"], leaf["unit"])
    return leaf["value"]


def sample_json(name):
    """Return the JSON file ``name`` of the sample problem as data."""
    return json.loads((HACKATHON_2026 / name).read_text())


def sample_case(name="case.json"):
    """Return case ``name`` of the hackathon sample: site, demand, requirements, prices."""
    return gm.Case.from_json(HACKATHON_2026 / name)


def shallow_case():
    """Return the case of the ``shallow_district`` sample."""
    return gm.Case.from_json(SHALLOW_DISTRICT / "case.json")


def treatment_plant():
    """Return the design with desander and inhibitor dosing, with the values of the sample case."""
    return apply_case(gm.Plant.from_dict(sample_json("plants/HackathonPlant.json")), sample_case())


def template_dict(name):
    """Return the plant dict of template plant ``name``, without the values of the case."""
    return sample_json(f"plants/{name}.json")


def template_plant(name):
    """Return template plant ``name`` with the values of the sample case set."""
    return apply_case(gm.Plant.from_dict(template_dict(name)), sample_case())


RULES = {"dispatch": "least_cost", "outages": "lowest_demand", "backup": "none"}
"""The plant rules a run needs (``gm.check`` names each unset one); ``backup`` acts only in a
sizing, so ``none`` leaves every run as it was."""


def filled_plant(name):
    """Return plant ``name`` with values: of the sample case for a template, else its example.

    A plant to run states the rules of its schedule and its sizing (gemini 0.6.5: none has a
    default); the example of a plant that is not scheduled does not, so they are set here.
    """
    plant = template_plant(name) if name in (SAMPLE_PLANT, *TEMPLATES) else example_plant(name)
    return plant.set_params("", RULES)


def example_plant(name):
    """Return plant ``name`` with the design values of ``tests/fixtures/plants/<name>.json``.

    ``Doublet`` and ``DoubletHeatPlant`` carry the values of the measured doublet, the other plants
    the values their unit tests use, and the two doublets their bindings to the measured columns,
    which a plant file does not hold (``fixtures/doublet_heat/bindings.json``). The values a case
    owns (the grid gas, the return limits of a consumer, the ambient pressure) are not in these
    plant files; ``plant_case_values.json`` holds the ones the unit tests of the plant use, and
    they are set on the modules here. Only tests, scripts and examples read the data folders.
    """
    plant = gm.Plant.from_json(paths.plant_values(name))
    for path, leaf in CASE_VALUES.get(name, {}).items():
        plant.set_params("", {path: _quantity(leaf)})
    bindings = json.loads(paths.doublet_heat("bindings.json").read_text()).get(name, {})
    for path, binding in bindings.items():
        plant.set_bindings(path, binding)
    return plant
