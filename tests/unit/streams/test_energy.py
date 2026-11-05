"""``gm.streams.Energy``: the forms of power a power port carries."""

import pytest

import gemini as gm
from gemini.streams import Energy


def test_the_forms_are_presets_equal_by_name():
    """A form is its name and the unit W; ``of`` gives the preset of a name."""
    assert Energy.ELECTRICITY == "electricity" and Energy.of("heat") is Energy.HEAT
    assert Energy.FUEL.to_dict() == {"name": "fuel", "unit": "W"}
    assert set(Energy.presets()) == {"electricity", "heat", "fuel", "any"}
    assert gm.streams.Energy is Energy and repr(Energy.HEAT) == "Energy.HEAT"


def test_an_unknown_form_is_refused():
    """A name gemini does not know is ``invalid_value``."""
    with pytest.raises(gm.errors.ValidationError, match="energy = 'steam'"):
        Energy.of("steam")
