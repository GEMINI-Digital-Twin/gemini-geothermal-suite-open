"""The variables of a search, found in the plant file: ranges and options, tied by role."""

import gemini as gm
from gemini.study._utils.variables import Variable, counts, searchable, variables
from gemini.units import Quantity
from tests.fixtures.errors import raises
from tests.fixtures.sample_cases import HACKATHON_2026
from tests.unit.study.conftest import shallow_plant

MW = Quantity(1, "MW"), Quantity(5, "MW")


def hackathon(name="HeatingCoolingPlant"):
    """Return a sample plant of the hackathon, with the ranges of its file."""
    return gm.Plant.from_json(HACKATHON_2026 / "plants" / f"{name}.json")


def test_the_variables_are_in_the_order_of_the_file_without_the_doublet_count():
    """``size.doublets`` is searched on its own: the others come in file order."""
    found = variables(shallow_plant())
    assert [item.name for item in found] == [
        "depth",
        "heat_pump.capacity",
        "compression_chiller.capacity",
        "d0.nominal_flow",
    ]
    assert counts(shallow_plant()) == [1, 2, 3]


def test_leaves_with_the_same_role_parameter_and_range_are_one_variable():
    """The nominal flows of two doublets are one variable that sets both."""
    found = {item.name: item for item in variables(hackathon())}
    flow = found["doublet.nominal_flow"]
    assert flow.paths == ("d0.nominal_flow", "d1.nominal_flow") and flow.low < flow.high


def test_three_chillers_of_one_range_are_one_capacity():
    """Absorption, adsorption and compression chillers share a role: one variable."""
    found = {item.name: item for item in variables(hackathon())}
    assert found["chiller.capacity"].paths == (
        "absorption_chiller.capacity",
        "adsorption_chiller.capacity",
        "compression_chiller.capacity",
    )


def test_another_range_unties_a_leaf():
    """A leaf with a range of its own is a variable of its own, named by its path."""
    plant = hackathon()
    plant.set_range("adsorption_chiller.capacity", min=MW[0], max=MW[1])
    found = {item.name: item.paths for item in variables(plant)}
    assert found["adsorption_chiller.capacity"] == ("adsorption_chiller.capacity",)
    assert found["chiller.capacity"] == (
        "absorption_chiller.capacity",
        "compression_chiller.capacity",
    )


def test_the_depth_of_the_plant_is_a_variable_of_the_plant():
    """The plant-level leaf is its own, tied by the class to its doublets."""
    found = {item.name: item for item in variables(shallow_plant())}
    assert found["depth"].paths == ("depth",)
    assert (found["depth"].low, found["depth"].high) == (1000.0, 2000.0)


def test_options_are_variables_with_their_choices():
    """A choice is searched as one of its options."""
    plant = shallow_plant()
    plant.set_options("heat_exchanger.arrangement", ["counterflow", "parallel"])
    (choice,) = [item for item in variables(plant) if item.options is not None]
    assert choice == Variable(
        "heat_exchanger.arrangement",
        ("heat_exchanger.arrangement",),
        options=("counterflow", "parallel"),
    )


def test_an_integer_parameter_is_searched_as_an_integer():
    """The parameter says whether its range is whole numbers."""
    plant = shallow_plant()
    flags = {item.name: item.integer for item in variables(plant)}
    assert flags["depth"] is False


def test_a_range_with_one_side_cannot_be_searched():
    """Both ends are needed: ``missing_value`` naming the leaf."""
    plant = shallow_plant()
    plant.set_range("depth", min=Quantity(1000, "m"))
    with raises(gm.errors.ValidationError, "missing_value") as refused:
        variables(plant)
    assert refused.value.path == "depth"


def test_a_plant_with_no_range_or_options_has_nothing_to_search():
    """No doublet range either: the plant is as it is."""
    plant = shallow_plant()
    for path in plant.ranges:
        plant.set_range(path)
    assert variables(plant) == [] and counts(plant) == [None] and not searchable(plant)
    assert searchable(shallow_plant())


def test_the_sample_plants_state_the_variables_the_search_had_in_the_order_it_had():
    """Capacities, then the flow and the depth of the doublets (the plant has no depth)."""
    names = [item.name for item in variables(hackathon("HackathonPlant"))]
    assert names == [
        "heat_pump.capacity",
        "chiller.capacity",
        "doublet.nominal_flow",
        "doublet.depth",
    ]
    names = [item.name for item in variables(hackathon("HeatingPlant"))]
    assert names == ["depth", "doublet.nominal_flow"]
