"""A plant on another number of doublets."""

import gemini as gm
from gemini.study._utils import resize
from gemini.study._utils.resize import resized
from tests.fixtures.errors import raises
from tests.unit.study.conftest import shallow_plant


def test_added_doublets_repeat_the_values_of_the_first():
    """Three doublets: d1 and d2 state what d0 states."""
    plant = resized(shallow_plant(), 3)
    data = plant.to_dict()
    assert plant.size == {"doublets": 3} and data["size"]["doublets"]["value"] == 3
    for name in ("d1", "d2"):
        assert data["params"][name]["nominal_flow"] == data["params"]["d0"]["nominal_flow"]


def test_removed_doublets_leave_nothing_behind():
    """Back to one doublet gives the plant dict it came from."""
    plant = shallow_plant()
    assert resized(resized(plant, 3), 1).to_dict() == plant.to_dict()


def test_the_plant_is_not_changed():
    """A new plant."""
    plant = shallow_plant()
    before = plant.to_dict()
    assert resized(plant, 2) is not plant and plant.to_dict() == before


def test_a_class_without_the_size_is_refused():
    """The plant dict has no ``size.doublets``."""
    with raises(gm.errors.ValidationError, "invalid_design", match="doublets") as refused:
        resized(gm.plants.get("DoubletHeatPlant"), 2)
    assert refused.value.path == "size.doublets"


def test_a_count_the_class_does_not_allow_is_refused():
    """The class says its own limits."""
    with raises(gm.errors.ValidationError, "invalid_design"):
        resized(shallow_plant(), 4)


def test_keys_without_a_doublet_survive_a_removal_of_every_doublet():
    """Only the doublets go; a parameter of another module stays."""
    section = {"d0.nominal_flow": 1, "heat_pump.capacity": 2}
    assert resize._renumbered(section, 1, 0) == {"heat_pump.capacity": 2}


def test_added_doublets_get_the_esp_limits_of_the_first():
    """The operating limits are plant values: every doublet the search adds has them."""
    plant = resized(shallow_plant(), 3)
    for name in ("d0", "d1", "d2"):
        esp = plant.get_submodule(f"{name}.esp")
        assert esp.minimum_intake_pressure == 500000.0 and esp.maximum_gas_fraction == 0.1875
