"""Ambient air for a direct call of a module that exchanges heat with it."""

from gemini.streams.flows import Stream
from gemini.streams.fluid import AIR
from tests.fixtures import si


def air(temperature=288.15):
    """Return what ``Atmosphere.air_out`` offers at ``temperature``: a number in K or a quantity."""
    return Stream(**si.stream(m_dot=0.0, T=temperature, p=101325.0, fluid=AIR))
