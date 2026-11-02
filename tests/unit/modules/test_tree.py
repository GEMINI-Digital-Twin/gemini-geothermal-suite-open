"""Navigating the children of a module and listing the declarations of its tree."""

import pytest

from gemini.errors import ValidationError
from gemini.modules import ModuleDict
from gemini.modules.control import PIDController
from gemini.modules.pumps import ESP
from tests.fixtures.errors import raises


def pair():
    """Return a container of two controllers named like their loops."""
    return ModuleDict({"heating": PIDController(), "cooling": PIDController()})


def test_children_and_paths_walk_the_tree_once():
    """Paths are dotted from the module asked; the empty path is the module itself."""
    tree = pair()
    assert [name for name, _ in tree.named_children()] == ["heating", "cooling"]
    assert [path for path, _ in tree.named_modules()] == ["", "heating", "cooling"]
    assert tree.get_submodule("heating") is tree["heating"] and tree.get_submodule("") is tree
    assert not tree.is_leaf and tree["heating"].is_leaf


def test_listings_recurse_by_dotted_path_and_a_typo_suggests_a_match():
    """Every listing is keyed by path below the module; an unknown path names the close ones."""
    tree = pair()
    assert set(tree.controls()) == {"heating.setpoint", "cooling.setpoint"}
    assert set(tree.controls(recurse=False)) == set()
    assert "heating.integral" in tree.states() and "cooling.command" in tree.outputs()
    pid = tree["heating"]
    assert pid.get("setpoint") is pid.controls()["setpoint"]
    with raises(ValidationError, "unknown_name", match="did you mean 'heating'"):
        tree.get_submodule("heatng")
    with raises(ValidationError, "unknown_name", match="unknown name 'setpint'"):
        pid.get("setpint")


def test_ports_of_a_module_are_its_own():
    """``inlets`` and ``outlets`` list the module's own ports, never a child's."""
    assert set(ESP().inlets()) == {"fluid_in", "power_in"} and set(ESP().outlets()) == {"fluid_out"}
    assert pair().inlets() == {} and pair().outlets() == {}
    with pytest.raises(ValidationError):
        ESP().get_submodule("nothing")
