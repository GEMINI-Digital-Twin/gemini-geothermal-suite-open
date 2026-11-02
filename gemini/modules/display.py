"""How a module shows itself: parameter values in display units, and its declarations."""

from gemini import runtime, units
from gemini.modules.declarations import UNSET, Output, Parameter

FIELD_DISPLAY_UNITS = {"Pa": "bar", "K": "°C", "m3/s": "m3/h", "W": "kW"}


def display(value, unit, quantity):
    """Format one parameter value with its unit, in field units when the runtime asks for them."""
    if runtime.get_display_units() == "field" and unit in FIELD_DISPLAY_UNITS:
        target = FIELD_DISPLAY_UNITS[unit]
        value, unit = units.convert(value, unit, target, quantity), target
    shown = f"{value:.5g}" if isinstance(value, float) else str(value)
    return shown + (f" {unit}" if unit and unit != "-" else "")


def describe(declaration):
    """Return the unit, default and flags of one declaration for ``Module.help``."""
    details = [declaration.unit] if declaration.unit else []
    if isinstance(declaration, Parameter) and declaration.default is not UNSET:
        details.append(f"default={declaration.default!r}")
    if isinstance(declaration, Parameter) and declaration.calibratable:
        details.append("calibratable")
    if isinstance(declaration, Output) and declaration.soft_sensor:
        details.append("soft sensor")
    return ", ".join(details)
