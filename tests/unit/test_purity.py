"""Every converted module is pure: forward and update write nothing to it or its children."""

import pytest

import gemini as gm
from gemini.modules.unconverted import OLD_STYLE_MUST_BECOME_EMPTY
from gemini.plants.plant import Plant
from tests.fixtures.purity import CASES, snapshot, unchanged
from tests.unit.plants.test_plant_contract import two_loops

NAMES = sorted(gm.modules.names())


def parametrized():
    """Return the registered names, those not yet converted marked as skipped."""
    skipped = pytest.mark.skip(reason="not converted: listed in OLD_STYLE_MUST_BECOME_EMPTY")
    return [
        pytest.param(name, marks=skipped if name in OLD_STYLE_MUST_BECOME_EMPTY else ())
        for name in NAMES
    ]


@pytest.mark.parametrize("name", parametrized())
def test_running_a_converted_module_leaves_it_and_its_children_unchanged(name):
    """The guard of ``tests/fixtures/purity.py`` holds for every registered class."""
    cls = gm.modules.get(name)
    if issubclass(cls, Plant):
        assert "forward" not in cls.__dict__ and "update" not in cls.__dict__, name
        return
    assert name in CASES, f"{name} is converted: add its purity case to tests/fixtures/purity.py"
    module, run = CASES[name]()
    with unchanged(module):
        run(module)


def test_a_plant_class_shares_the_one_forward_and_update_of_plant():
    """The one implementation runs a plant of any graph; it is tested on a plant of two loops."""
    plant = two_loops()
    state = {"heating": {"integral": 0.0, "previous_error": 0.0, "previous_step": 0.0}}
    state["cooling"] = state["heating"]
    plant(state=state)
    with unchanged(plant):
        plant(state=state)
        plant.step(state, 60, {})


def test_the_guard_finds_a_write_to_a_parameter_a_child_or_the_module_itself():
    """A call that writes is caught and named; one that does not passes."""
    plant = two_loops()
    before = snapshot(plant)
    plant.heating.set_params("", {"proportional_gain": 3.0})
    plant.cooling.extra = 1
    assert snapshot(plant) != before
    with pytest.raises(AssertionError, match="Plant.*heating"):
        with unchanged(plant):
            plant.heating.set_params("", {"proportional_gain": 4.0})


def test_a_call_of_the_doublet_leaves_the_plant_and_every_module_unchanged(fresh_plant):
    """A real graph, with a pump, wells and reservoirs: nothing is written during the call."""
    doublet = fresh_plant.doublet
    doublet._set_inputs({"reservoir.production_rate": 40.0, "esp.frequency": 50.0})
    returned = gm.Stream(
        m_dot=gm.units.Quantity(40, "kg/s"),
        T=gm.units.Quantity(330, "K"),
        p=gm.units.Quantity(5e6, "Pa"),
        fluid=doublet.fluid,
    )
    doublet._prepare()
    with unchanged(doublet):
        doublet(return_in=returned)
