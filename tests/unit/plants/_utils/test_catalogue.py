"""The plant catalogue: names and new plants."""

import hashlib
import json

import pytest

import gemini as gm
from gemini.plants._utils import catalogue
from tests.fixtures.errors import raises
from tests.fixtures.plant_files import issues, leaves
from tests.fixtures.sample_cases import example_plant, treatment_plant

TEMPLATE_PLANTS = (
    "HeatingPlant",
    "HeatingCoolingPlant",
    "HeatingFullCoolingPlant",
    "HeatingAbsorptionCoolingPlant",
    "HeatingHeatPumpCoolingPlant",
)
"""The plants whose values are the sample problem's, in ``inputs/examples/``, not an example."""
FORMER_EXAMPLES = {
    "ATESPlant": "8aa9d46daaa933276799cb86763a972fdf7000693459d6513d275a08fe7d4941",
    "BoilerChpPlant": "15f32df6b61a5d8c0a45a4366bc624458c316ff01d3f043bd1dc33a569efb8a0",
    "CoolingSubstation": "5e2b82d31eb5476286a9e1ba56c23043d3dd509e1134f83c4ba24985d1f6f912",
    "DistrictEnergyPlant": "911708d383cff88412a047e72a2013f5a3a5a43730a93035f3f45b9c008d8ba6",
    "DistrictNetwork": "4c22d24d66084e76c7a123f5f23ea0cf81abff8bf824841147bf189421e1fd69",
    "Doublet": "2d4e3a0e75760ee1db12a32361b4630e42332f750390d3718cf5aeddd4d70aa9",
    "DoubletHeatPlant": "b0e9045f1981d87edbf3259c8a41bd62d28e56dfb6019a7877507d62166058b7",
    "HeatingSubstation": "3eefcd37ca64d8a894252b71a31838a0f3f43118a3144dd8d90dc93621fcad95",
    "MultiWellPlant": "78b05793a3a184381a0d9f00ed1696b57b49efc80afd6015dc4112d4796a2733",
    "NodalDoublet": "1184ba2953c57dcd6c9c8ff8de660f26be59747cf80e78ac21076189f294e76f",
    "ParallelExchangerPlant": "65657b9eb43cd9484cd74646ab43685ac1ad6a3a7658b4c90d809afb5a684b8b",
}
"""Hash of ``to_dict()`` of the plant built from each whole example file these values replaced.

The hashes were taken again when the plant dict lost the values of the case and wrote every value
with a unit as ``{"value", "unit"}``; the design values are those of the files.
They were taken again when the declarations of the modules lost their default design values: each
file now states, with the value it effectively used, what a declaration used to default (a
roughness, an arrangement, an alarm threshold); no value changed.
They were taken again when the files moved to the plant file form (header, nested ``params`` of
leaf objects, no ``inputs`` and no ``bindings``): the hash is of the new form, and
``.tmp/inputs/convert_plants.py`` checked, for every file, that each old param and input equals the
value read from the new file, as do the fluids, the boundary and the history.

The template plants have no example: their values are in the sample problem. ``Doublet`` is hashed
without ``outputs``, which its structure file has and its former example file lacked.
"""


def test_names_are_the_registered_plants():
    """Spec plants and the special cases are listed, sorted, and nothing else."""
    assert catalogue.names() == gm.modules.names("plants")
    assert {"Doublet", "DoubletHeatPlant", "MultiWellPlant", "DistrictNetwork"} <= set(
        catalogue.names()
    )
    assert {"HeatingSubstation", "CoolingSubstation", "ATESPlant"} <= set(catalogue.names())
    assert {"NodalDoublet", "ParallelExchangerPlant", "BoilerChpPlant"} <= set(catalogue.names())
    assert {"DistrictEnergyPlant", "HeatingCoolingPlant"} <= set(catalogue.names())
    assert "ESP" not in catalogue.names()


def test_get_returns_a_new_plant_without_values():
    """A spec plant is a Plant, a special case an instance of its class; each call is new."""
    first, second = catalogue.get("Doublet"), catalogue.get("Doublet")
    assert isinstance(first, gm.Plant) and first is not second
    assert isinstance(catalogue.get("HeatingSubstation"), gm.plants.HeatingSubstation)
    assert first.name == "Doublet"


def test_get_refuses_unknown_names_and_modules_that_are_not_plants():
    """An unknown name has close matches; a pump is not a plant."""
    with raises(gm.errors.ValidationError, "unknown_name") as unknown:
        catalogue.get("DubletHeatPlant")
    assert "DoubletHeatPlant" in unknown.value.suggestions
    with raises(gm.errors.ValidationError, "unknown_name"):
        catalogue.get("ESP")


EXAMPLES = [name for name in catalogue.names() if name not in TEMPLATE_PLANTS]


@pytest.mark.parametrize("name", EXAMPLES)
def test_every_spec_plant_and_special_case_has_an_example_that_round_trips(name):
    """An example builds, has no problems and writes the spec it was read from."""
    spec = example_plant(name).to_dict()
    assert issues(spec) == []
    assert gm.Plant.from_dict(spec).to_dict() == spec


@pytest.mark.parametrize("name", EXAMPLES)
def test_every_example_equals_the_plant_of_its_former_file(name):
    """``get`` and the values of ``inputs/plants/`` give the structure and the values pinned."""
    spec = example_plant(name).to_dict(structure=True)
    if name == "Doublet":
        del spec["outputs"]
    text = json.dumps(spec, sort_keys=True)
    assert hashlib.sha256(text.encode()).hexdigest() == FORMER_EXAMPLES[name]


def test_the_doublet_examples_carry_the_shared_doublet_heat_values():
    """The doublet is the ``doublet`` child of the doublet heat plant."""
    shared = leaves(example_plant("DoubletHeatPlant").to_dict(structure=True))
    expected = {
        name[len("doublet.") :]: value
        for name, value in shared.items()
        if name.startswith("doublet.") and "." in name[len("doublet.") :]
    }
    found = leaves(example_plant("Doublet").to_dict(structure=True))
    assert {name: value for name, value in found.items() if "." in name} == expected


def test_the_other_examples_carry_the_values_of_their_tests(plants):
    """The substations and the network are filled as the unit tests of their folder fill them."""
    heating = plants["heating_substation"](catalogue.get("HeatingSubstation"))
    assert example_plant("HeatingSubstation").state_dict() == heating.state_dict()
    cooling = plants["cooling_substation"](catalogue.get("CoolingSubstation"))
    assert example_plant("CoolingSubstation").state_dict() == cooling.state_dict()
    network = plants["network"](catalogue.get("DistrictNetwork"), plants["heating_substation"])
    assert example_plant("DistrictNetwork").state_dict() == network.state_dict()


def test_a_state_dictionary_fills_a_plant_without_values():
    """A plant from ``get`` has no values and takes those of an example; groups stay groups."""
    example = example_plant("DoubletHeatPlant")
    assert isinstance(example.filters, gm.modules.ModuleDict)
    fresh = catalogue.get("DoubletHeatPlant")
    assert not fresh.is_initialized
    fresh.set_state_dict(example.state_dict())
    assert fresh.is_initialized


def test_the_treatment_design_is_complete_and_valid():
    """Every port is connected and every parameter has a value."""
    plant = treatment_plant()
    assert plant.is_initialized
    assert plant.check() == []
    assert plant.d0.reservoir.temperature == plant.d1.reservoir.temperature
    assert plant.heat_users.fluid == gm.WATER


def test_names_lists_the_plants_of_a_purpose():
    """``category`` is what a plant serves; a building block serves nothing by itself."""
    assert catalogue.names("heating") == ["HeatingPlant"]
    assert "HeatingCoolingPlant" in catalogue.names("both")
    assert "Doublet" not in catalogue.names("both") + catalogue.names("heating")
    with raises(gm.errors.ValidationError, "unknown_name"):
        catalogue.names("steam")


def test_check_gives_the_same_for_a_plant_and_its_dict():
    """A good plant and a broken one: the plant and its dict agree on what is wrong."""
    good = treatment_plant()
    assert good.check() == issues(good.to_dict(structure=True)) == []
    broken = gm.Plant("Open")
    broken.add("Degasser", "degasser")
    found = [item for item in broken.check() if item.kind != "missing"]
    assert found and found == issues(broken.to_dict(structure=True))
