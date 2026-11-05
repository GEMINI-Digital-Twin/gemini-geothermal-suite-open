"""One call of a plant: what its paths read."""

import pytest

import gemini as gm
from gemini.plants._utils.call import Call
from tests.fixtures.sample_cases import example_plant


def plant():
    """Return the doublet of the example plant."""
    return example_plant("DoubletHeatPlant").doublet


def call_of(doublet):
    """Return the call of ``doublet`` before any step: no inputs, inlets or state."""
    return Call(doublet, {}, {}, {}, doublet._compiled())


def test_a_path_reads_a_declaration_of_the_plant():
    """What names no step is a parameter or boundary of the plant or of a child."""
    doublet = plant()
    call = call_of(doublet)
    assert call.read("drainage_radius") == doublet.drainage_radius
    assert call.read("esp.stage_count") == doublet.esp.stage_count


def test_an_unknown_path_raises():
    """A path that names nothing says so."""
    with pytest.raises(gm.errors.ValidationError):
        call_of(plant()).read("nothing.at.all")
