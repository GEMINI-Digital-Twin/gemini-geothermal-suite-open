"""One call of one module from plain JSON."""

from collections.abc import Mapping

from gemini import units as unit_table
from gemini._utils import registry
from gemini._utils.strings import close_matches, did_you_mean, join_names
from gemini.errors import GeminiError, ValidationError
from gemini.errors.base import check_on_error
from gemini.modules._utils import design
from gemini.modules.module import Module
from gemini.streams.flows import FIELD_SI, STREAM_FIELDS, Stream
from gemini.units import bare
from gemini.units.display import DisplayedValues
from gemini.units.shapes import OutputUnits

UNITS = ("si", "display")
"""The two choices of ``units``: plain ``{value, unit}`` in SI, or ``Quantity`` in display units."""
FLOW = ("m3/s", "volume_flow")
"""The SI unit and the quantity of ``flow``, the volume flow in place of ``m_dot``."""


def evaluate(module, parameters, inlets, controls, units, on_error="raise", state=None, dt=None):
    """Return ``{outlets, outputs, state, errors}`` of one call of a registered module or class.

    ``module`` is a registry name or a ``Module`` class. ``parameters`` maps parameter names to
    quantities (``{"value": 150, "unit": "m3/h"}``, or a ``gm.units.Quantity``) for a value with a
    dimension and plain numbers for one without. ``inlets`` maps each inlet
    port to its stream fields, ``{"m_dot": {"value": 10, "unit": "kg/s"}, "T": ...}``, or ``flow``
    in place of ``m_dot`` for a volume flow, which converts with the density of the inlet's
    fluid, and a ``fluid`` (required, a mapping of the fields of ``Fluid``). ``m_dot`` refuses a
    volume unit and suggests ``flow``.
    ``controls`` maps control and boundary names to values for this call only, in the same form.
    A bare number for a value with a dimension, in ``parameters``, ``controls`` or an inlet
    field, is refused with ``invalid_value`` naming the path, the quantity and its units.

    ``units`` has no default and is ``"si"`` or ``"display"``. ``"si"`` gives every value as the
    plain JSON ``{value, unit}`` in SI. ``"display"`` gives every value as a ``gm.units.Quantity``
    (a ``Value``, which holds the ``reason`` of a value that is ``None``) in the display unit of
    ``gm.units.display.DISPLAY_UNITS`` (MW, MWh, degC, m3/h, ...), the table of the report; a
    quantity the table does not list, and a difference such as a temperature lift, stays in SI.
    Converted back to SI the two results are equal.

    A stateful module, or a plant with one below it, needs ``state`` and ``dt``: ``state`` is the
    state at the start, ``{state name: quantity}`` (for a plant ``{child name: {state name:
    quantity}}``), and ``dt`` the step as a quantity of time. ``state`` in the result is the state
    at the end of the step, in the form of ``state`` and in the choice of ``units``: feed it to
    the next call. A module without state takes neither, and ``state`` in its result is ``{}``.

    ``outlets`` is ``{port: {field: value}}``, ``outputs`` is ``{name: value}``, and ``errors`` is
    empty. A call that fails raises; with ``on_error="record"`` it returns empty ``outlets``,
    ``outputs`` and ``state`` and in ``errors`` the problem of what went wrong.
    """
    check_on_error(on_error)
    try:
        output = _output_values(units)
        _check_mass_flows(inlets or {})
        _check_inlets(inlets or {})
        instance = _instance(module)
        _check_given(instance, parameters or {}, controls or {})
        instance._override_params(parameters or {})
        given, step = _check_state(instance, state, dt)
    except GeminiError as error:
        return _failed(error, on_error)
    except (TypeError, ValueError) as error:
        return _failed(ValidationError(str(error)), on_error)
    try:
        result = instance(dict(inlets or {}), **(controls or {}), state=given)
        advanced = {} if step is None else instance._advance(result, step)
    except GeminiError as error:
        return _failed(error, on_error)
    return {
        "outlets": _outlets(result.outlets, output),
        "outputs": _outputs(instance, result.outputs, output),
        "state": _state_values(instance, advanced, output),
        "errors": [],
    }


def _output_values(units):
    """Return the object that builds the values of the result for the choice ``units``."""
    if units == "si":
        return OutputUnits()
    if units == "display":
        return DisplayedValues()
    raise ValidationError(
        f"evaluate: units = {units!r}; expected one of {join_names(UNITS)}"
        f"{did_you_mean(str(units), UNITS)}",
        path="units",
        code="invalid_value",
        suggestions=close_matches(str(units), UNITS),
    )


def _check_state(instance, state, dt):
    """Return ``(state tree, step in s)`` of a call; both are ``None`` for a module without state.

    A stateful module needs both and refuses a bare number for a state or the step; a module
    without state refuses either.
    """
    if not instance._has_state():
        if state is not None or dt is not None:
            raise ValidationError(
                f"evaluate: {'state' if state is not None else 'dt'} is given; expected none, "
                f"because {instance.path or type(instance).__name__} has no state",
                path="state" if state is not None else "dt",
                code="invalid_call",
            )
        return None, None
    for name, value in (("state", state), ("dt", dt)):
        if value is None:
            raise ValidationError(
                f"evaluate: {name} is missing; expected a value for a module with state "
                "(it has no default)",
                path=name,
                code="missing_value",
            )
    bare.refuse("dt", dt, "s", "duration")
    _refuse_bare_states(instance, state, "state")
    return state, unit_table.value_in_si(dt, "s", "dt", "duration")


def _refuse_bare_states(module, tree, path):
    """Refuse a bare number for a state with a dimension anywhere in ``tree``."""
    for name, value in tree.items():
        if name in module._states:
            design.refuse_bare(module._states[name], value, f"{path}.{name}")
        elif isinstance(value, Mapping) and module._find_submodule(name) is not None:
            _refuse_bare_states(module.get_submodule(name), value, f"{path}.{name}")


def _state_values(module, tree, output):
    """Return the state tree ``tree`` as values: ``{state name: value}``, nested by child name."""
    found = {}
    for name, value in tree.items():
        if name in module._states:
            declaration = module._states[name]
            found[name] = output.value(value, declaration.unit or "-", declaration.quantity)
        else:
            found[name] = _state_values(module.get_submodule(name), value, output)
    return found


def _check_mass_flows(inlets):
    """Refuse a volume flow given as ``m_dot``, pointing to ``flow``."""
    for port, fields in inlets.items():
        flow = fields.get("m_dot") if isinstance(fields, Mapping) else None
        unit = flow.get("unit") if isinstance(flow, Mapping) else getattr(flow, "unit", None)
        if unit is not None and unit_table.fits(unit, "volume_flow"):
            raise ValidationError(
                f"evaluate: {port}.m_dot = {flow!r}; expected a mass flow; give it as 'flow'",
                path=f"{port}.m_dot",
                code="invalid_call",
                suggestions=["flow"],
            )


def _check_inlets(inlets):
    """Refuse a bare number for a stream field of an inlet: it is a quantity."""
    for port, fields in inlets.items():
        if not isinstance(fields, Mapping):
            continue
        for name, value in fields.items():
            unit, quantity = FLOW if name == "flow" else FIELD_SI.get(name, (None, None))
            bare.refuse(f"{port}.{name}", value, unit, quantity)


def _check_given(instance, parameters, controls):
    """Refuse a bare number for a parameter, control or boundary with a dimension."""
    for name, value in parameters.items():
        design.refuse_bare(instance.get(name), value, name)
    declared = instance.inputs()
    for name, value in controls.items():
        if name in declared:
            design.refuse_bare(declared[name], value, name)


def _instance(module):
    """Return a new module from a registry name or a class."""
    if isinstance(module, str):
        module = registry.get(module)
    if isinstance(module, Module):
        return module
    if not (isinstance(module, type) and issubclass(module, Module)):
        raise ValidationError(
            f"evaluate: module = {module!r}; expected a registry name or a Module class"
        )
    return module()


def _failed(error, on_error):
    """Raise the failure of a call, or return it under ``on_error="record"``."""
    if on_error == "raise":
        raise error
    return {"outlets": {}, "outputs": {}, "state": {}, "errors": [error.to_dict()]}


def _outlets(outlets, output):
    """Return each outlet as ``{field: {value, unit}}``; a power port has the field ``power``."""
    return {port: _outlet(value, output) for port, value in outlets.items()}


def _outlet(value, output):
    """Return one outlet: its stream fields, or ``{power: {value, unit}}``."""
    if isinstance(value, list):
        return [_outlet(item, output) for item in value]
    if not isinstance(value, Stream):
        return {"power": output.value(value, "W", "power")}
    return {name: output.value(getattr(value, name), *FIELD_SI[name]) for name in STREAM_FIELDS}


def _outputs(instance, outputs, output):
    """Return each output as ``{value, unit}``; an output without a declared unit is ``"-"``."""
    declarations = instance.outputs(recurse=False)
    return {
        name: output.value(
            number,
            (declarations[name].unit if name in declarations else None) or "-",
            declarations[name].quantity if name in declarations else None,
        )
        for name, number in outputs.items()
    }
