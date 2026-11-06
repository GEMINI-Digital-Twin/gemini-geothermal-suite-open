"""Unit tests for gemini_simulator.registry."""

import pytest

from gemini_model.adder.adder import Adder
from gemini_simulator.registry import COMPONENT_REGISTRY, create_component


def test_all_registered_types_are_instantiable():
    """Every registered component type should be instantiable."""
    for type_name in COMPONENT_REGISTRY:
        instance = create_component(type_name)
        assert instance is not None


def test_create_component_returns_expected_class():
    """Creating a component by name should return the expected class."""
    instance = create_component("adder")
    assert isinstance(instance, Adder)


def test_unknown_type_raises_key_error():
    """Creating an unknown component type should raise a KeyError."""
    with pytest.raises(KeyError):
        create_component("not_a_real_component")
