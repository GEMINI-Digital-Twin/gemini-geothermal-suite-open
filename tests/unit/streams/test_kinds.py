"""The fixed stream-type list and the stream a port declares."""

import pytest

from gemini.errors import DefinitionError
from gemini.modules import Port
from gemini.streams import kinds as streams
from gemini.streams.fluid import Fluid
from gemini.streams.kinds import Direction, Flow, Level, Phase


def test_names_are_the_fixed_list():
    """The list is what the frontend colours."""
    assert streams.names() == [
        "brine",
        "hot_water",
        "chilled_water",
        "gas",
        "electricity",
        "fuel",
        "heat",
        "air",
        "waste",
        "chemical",
    ]


def test_a_port_keeps_its_stream():
    """A port may name a stream type or take whatever flows through it."""
    assert (
        Port(
            Direction.IN,
            phase=Phase.LIQUID,
            fluid=Fluid.BRINE,
            level=Level.GEOTHERMAL,
            flow=Flow.IMPOSED,
        ).kind
        == "brine"
    )
    assert (
        Port(
            Direction.OUT, fluid=Fluid.ANY, phase=Phase.ANY, level=Level.ANY, flow=Flow.IMPOSED
        ).kind
        is None
    )


def test_an_unknown_stream_suggests_the_closest():
    """A misspelt medium fails while the class is built."""
    with pytest.raises(DefinitionError, match="did you mean 'liquid'"):
        Port(Direction.IN, fluid=Fluid.ANY, phase="liqid", level=Level.ANY, flow=Flow.IMPOSED)
