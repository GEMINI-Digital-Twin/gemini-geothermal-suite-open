"""Equipment declares a kind and the size its cost scales with."""

import pytest

from gemini.modules._utils.equipment import Equipment


def test_equipment_has_no_kind_until_a_subclass_sets_one():
    """The base declares none."""
    assert Equipment.equipment_kind is None


def test_equipment_without_a_size_says_so():
    """A subclass that does not define ``cost_size`` is refused."""
    with pytest.raises(NotImplementedError, match="cost_size"):
        Equipment().cost_size()
