"""How the arguments of a call and the ports it returns are read and checked."""

import pytest

from gemini.errors import DefinitionError, ValidationError
from gemini.modules.pumps import ESP
from gemini.streams.flows import Stream
from gemini.streams.fluid import BRINE
from gemini.units import Quantity

STREAM = Stream(fluid=BRINE, m_dot=Quantity(1, "kg/s"), T=Quantity(300, "K"), p=Quantity(1e5, "Pa"))


def test_inlets_come_by_position_name_or_mapping_and_controls_by_keyword():
    """The three ways to give an inlet agree; a control is a keyword."""
    pump = ESP()
    by_position, supplied = pump._split_call_args((STREAM,), {"frequency": 50})
    by_name, _ = pump._split_call_args((), {"fluid_in": STREAM})
    by_mapping, _ = pump._split_call_args(({"fluid_in": STREAM},), {})
    assert by_position.fluid_in == by_name.fluid_in == by_mapping.fluid_in
    assert supplied == {"frequency": 50}


@pytest.mark.parametrize(
    ("args", "kwargs", "match"),
    [
        ((), {}, "missing required inlet"),
        ((STREAM, STREAM, STREAM), {}, "expected at most 1 positional"),
        ((STREAM,), {"fluid_in": STREAM}, "multiple values for inlet"),
        ((), {"fluid_in": STREAM, "frequncy": 1}, "unexpected keyword 'frequncy'"),
        (({"fluid_in": STREAM, "other": STREAM},), {}, "unknown inlet 'other'"),
    ],
)
def test_a_wrong_call_names_the_path_and_the_valid_names(args, kwargs, match):
    """A call that does not fit the declarations is an ``invalid_call`` naming the module."""
    with pytest.raises(ValidationError, match=match) as raised:
        ESP()._split_call_args(args, kwargs)
    assert raised.value.code == "invalid_call"


def test_returned_outlet_names_are_checked_against_the_declarations():
    """A missing or an extra outlet names the module and the valid names."""
    pump = ESP()
    pump._check_outlet_names({"fluid_out": STREAM, "power_in": 1.0})
    with pytest.raises(DefinitionError, match="esp: outlet names missing=\\['power_in'\\]"):
        pump._check_outlet_names({"fluid_out": STREAM})
    with pytest.raises(DefinitionError, match="extra=\\['other'\\]"):
        pump._check_outlet_names({"fluid_out": STREAM, "power_in": 1.0, "other": 1})
