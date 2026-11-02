"""State connections: an inlet that reads the value its source outlet had at the previous step.

A connection of type ``state`` is no edge of the order: its target reads the plant's state at the
start of the step, where the plant keeps, under ``PREVIOUS``, what each such source outlet gave at
the end of the step before, by ``"<path>.<port>"``. A stream is kept as ``{m_dot, T, p}`` (its
fluid is that of the source module), another outlet as a number. ``Plant._advance`` writes the new
values from the call of the step. The first step has no previous value: ``start`` is the stream at
rest at the temperature the source module guesses for a loop (``Module._loop_start``) and at the
highest pressure among the inlets of the plant, so a state connection is a loop with a one step
delay, not an iteration.
"""

from gemini.errors import DefinitionError, ValidationError
from gemini.streams.flows import STREAM_FIELDS, Stream

PREVIOUS = "@previous"
"""The key of the previous-step values in the state of a plant that has state connections."""


def has_delays(plant):
    """Return whether a connection of ``plant`` is of type ``state``."""
    return any(item.get("type") == "state" for item in plant._connections)


def start(call):
    """Return the values the first step reads: no flow, a guessed temperature, a pressure."""
    entering = [value for value in call.inlets.values() if isinstance(value, Stream)]
    pressures = [stream.p for stream in entering]
    found = {}
    for key, (path, port) in call.plan.delays.items():
        module = call.nodes[path]
        if module._outlets[port].type is not Stream:
            found[key] = 0.0
            continue
        temperature = module._loop_start(module._stated_inputs(), port, entering)
        if temperature is None or not pressures:
            raise ValidationError(
                f"{call.plant.path}: state connection from {key} has no value for the first "
                "step; expected a source module that guesses its outlet temperature "
                "(_loop_start) and a plant inlet stream for the pressure",
                path=key,
                code="invalid_design",
            )
        found[key] = {"m_dot": 0.0, "T": temperature, "p": max(pressures)}
    return found


def read(call, key):
    """Return what the source outlet ``key`` gave at the previous step."""
    previous = call.state.get(PREVIOUS) if call.state else None
    value = (previous if previous is not None else start(call))[key]
    if isinstance(value, dict):
        return Stream._si(fluid=call.nodes[call.plan.delays[key][0]].fluid, **value)
    return value


def written(plant, plan, result):
    """Return the values of the state connections at the end of the call of ``result``."""
    records = dict(result.call_records)
    values = {}
    for key, (path, port) in plan.delays.items():
        value = records[path].outlets[port]
        if isinstance(value, Stream):
            fluid = plan.nodes[path].fluid
            if value.fluid != fluid:
                raise DefinitionError(
                    f"{plant.path}: state connection from {key} carries the fluid "
                    f"{value.fluid!r}; expected that of {path}, {fluid!r}"
                )
            values[key] = {name: getattr(value, name) for name in STREAM_FIELDS}
        else:
            values[key] = value
    return {PREVIOUS: values}
