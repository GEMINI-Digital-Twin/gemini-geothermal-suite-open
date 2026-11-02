"""How a module shows its parameters and its declarations."""

from gemini import runtime
from gemini.modules.display import describe, display
from gemini.modules.pumps import ESP


def test_a_value_shows_with_its_unit_and_field_units_when_asked():
    """The display unit follows the runtime setting for pressure, temperature, flow and power."""
    assert display(2.5, "m", "length") == "2.5 m"
    assert display(3, "-", None) == "3"
    with runtime.settings(display_units="field"):
        assert display(1e5, "Pa", "pressure") == "1 bar"
        assert display(400.0, "W", "power") == "0.4 kW"


def test_help_lists_declarations_with_unit_and_flags():
    """A declaration shows its unit, and its default or its calibration flag."""
    module = ESP()
    assert describe(module.get("frequency")) == "Hz"
    assert "calibratable" in describe(module.get("head_coefficients"))
    assert "Parameters:" in ESP.help() and "Outputs:" in ESP.help()
