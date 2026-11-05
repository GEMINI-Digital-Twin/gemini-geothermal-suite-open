"""The module contract: pure ``forward`` and ``update``, enforced keys, hooks, pre-run values."""

import pytest

import gemini as gm
from gemini.errors import DefinitionError, ValidationError
from gemini.modules import Module, Port
from gemini.modules.declarations import Boundary, Control, Output, Parameter, State
from gemini.streams.flows import Stream
from gemini.streams.fluid import BRINE, Fluid
from gemini.streams.kinds import Direction, Flow, Level, Phase
from gemini.streams.ports import Ports
from gemini.units import Quantity
from gemini.units.quantities import Frequency, Temperature
from tests.fixtures.errors import raises
from tests.fixtures.purity import unchanged

STREAM = Stream(fluid=BRINE, m_dot=Quantity(1, "kg/s"), T=Quantity(300, "K"), p=Quantity(1e5, "Pa"))


class Gain(Module):
    """Converted fixture: a gain on a control and a boundary, a parameter and a pass-through."""

    def __init__(self):
        """Declare the gain."""
        super().__init__()

        # Parameters
        self.scale = Parameter(float, gt=0)

        # Inlets
        self.fluid_in = Port(
            Direction.IN, fluid=Fluid.ANY, phase=Phase.ANY, level=Level.ANY, flow=Flow.IMPOSED
        )

        # Controls
        self.boost = Control(Frequency)

        # Boundaries
        self.offset = Boundary(float, default=0.0)

        # Outputs
        self.rise = Output(float)

        # Outlets
        self.fluid_out = Port(
            Direction.OUT, fluid=Fluid.ANY, phase=Phase.ANY, level=Level.ANY, flow=Flow.IMPOSED
        )

    def forward(self, inputs, inlets, state):
        """Return the gain of the boost and the offset, and the inlet."""
        outputs = dict(rise=self.scale * inputs["boost"] + inputs["offset"])
        outlets = dict(fluid_out=inlets.fluid_in)
        return outputs, outlets


def gain():
    """Return a gain with its scale set."""
    return Gain().set_params("", {"scale": 2.0})


def test_forward_gets_inputs_inlets_and_state_and_returns_outputs_and_outlets():
    """A call resolves the controls into inputs; the result holds what forward returned."""
    result = gain()(fluid_in=STREAM, boost=Quantity(5, "Hz"), offset=1.0)
    assert result.outputs.rise == 11.0
    assert result.outlets.fluid_out is STREAM
    assert result.inputs == {"boost": 5.0, "offset": 1.0}
    assert result.state == {}


def test_a_value_set_before_the_run_is_a_quantity_and_a_column_wins():
    """A control set on the module is a pre-run value poured into inputs; a keyword wins."""
    module = gain()
    module.boost = Quantity(5, "Hz")
    assert module.boost == 5.0
    assert module(fluid_in=STREAM).inputs["boost"] == 5.0
    assert module(fluid_in=STREAM, boost=Quantity(7, "Hz")).inputs["boost"] == 7.0
    assert module.boost == 5.0
    with raises(ValidationError, "invalid_value", match="boost.*accepted units"):
        module.boost = 5


def test_parameters_are_read_on_self_and_nothing_else_is():
    """Inside a call self gives parameters; a control, a boundary and an output come from args."""

    class Greedy(Gain):
        """Reads a control from self."""

        def forward(self, inputs, inlets, state):
            """Read the boost from self."""
            return dict(rise=self.boost), dict(fluid_out=inlets.fluid_in)

    with pytest.raises(DefinitionError, match="boost: forward and update take a control"):
        Greedy().set_params("", {"scale": 1.0})(fluid_in=STREAM, boost=Quantity(1, "Hz"))


def test_forward_writes_no_output_control_or_state_to_self():
    """Assigning an output or a control inside a converted forward is refused."""

    class Writer(Gain):
        """Assigns an output."""

        def forward(self, inputs, inlets, state):
            """Assign the output instead of returning it."""
            self.rise = 1.0
            return dict(rise=1.0), dict(fluid_out=inlets.fluid_in)

    with pytest.raises(DefinitionError, match="rise: an output is returned by forward"):
        Writer().set_params("", {"scale": 1.0})(fluid_in=STREAM, boost=Quantity(1, "Hz"))
    with pytest.raises(DefinitionError, match="rise: an output is returned by forward"):
        gain().rise = 1.0


def test_a_call_leaves_the_module_unchanged():
    """The purity guard: a call writes nothing to the module."""
    module = gain()
    with unchanged(module):
        module(fluid_in=STREAM, boost=Quantity(5, "Hz"))
        module.forward({"boost": 5.0, "offset": 0.0}, Ports({"fluid_in": STREAM}), {})


@pytest.mark.parametrize(
    ("returned", "word", "key"),
    [
        ({}, "missing", "rise"),
        ({"rise": 1.0, "extra": 2.0}, "extra", "extra"),
        ({"rise": 1.0, "boost": 2.0}, "extra", "boost"),
    ],
)
def test_returned_output_keys_are_enforced_with_the_module_and_the_key(returned, word, key):
    """A missing or an extra output key is an error naming the module and the key."""

    class Wrong(Gain):
        """Returns the wrong keys."""

        def forward(self, inputs, inlets, state):
            """Return the keys of the case."""
            return returned, dict(fluid_out=inlets.fluid_in)

    with pytest.raises(DefinitionError, match=rf"wrong.*{word} key '{key}'"):
        Wrong().set_params("", {"scale": 1.0})(fluid_in=STREAM, boost=Quantity(1, "Hz"))


@pytest.mark.parametrize(
    ("outlets", "word"), [({}, "missing"), ({"fluid_out": STREAM, "other": STREAM}, "extra")]
)
def test_returned_outlet_keys_are_enforced(outlets, word):
    """A missing or an extra outlet key is an error naming the module and the key."""

    class Wrong(Gain):
        """Returns the wrong outlets."""

        def forward(self, inputs, inlets, state):
            """Return the outlets of the case."""
            return dict(rise=1.0), outlets

    with pytest.raises(DefinitionError, match=rf"wrong.*{word}=\['(fluid_out|other)'\]"):
        Wrong().set_params("", {"scale": 1.0})(fluid_in=STREAM, boost=Quantity(1, "Hz"))


def test_forward_must_return_outputs_and_outlets():
    """A forward that returns one dict is refused."""

    class Single(Gain):
        """Returns the outlets alone."""

        def forward(self, inputs, inlets, state):
            """Return one dict."""
            return dict(fluid_out=inlets.fluid_in)

    with pytest.raises(DefinitionError, match="forward must return"):
        Single().set_params("", {"scale": 1.0})(fluid_in=STREAM, boost=Quantity(1, "Hz"))


def test_a_pre_hook_replaces_inputs_and_a_hook_replaces_outputs():
    """D2: hooks take the arguments of forward; the mapping a hook returns changes the call."""
    module, seen = gain(), []

    def clamp(module, inputs, inlets, state):
        seen.append(("pre", dict(inputs), dict(state)))
        return {"boost": min(inputs["boost"], 4.0)}

    def double(module, inputs, inlets, state, outputs, outlets):
        seen.append(("post", dict(outputs), outlets.fluid_out is inlets.fluid_in))
        return {"rise": outputs["rise"] * 2}

    first, second = module.register_forward_pre_hook(clamp), module.register_forward_hook(double)
    result = module(fluid_in=STREAM, boost=Quantity(5, "Hz"))
    assert result.outputs.rise == 2 * (2 * 4.0)
    assert [item[0] for item in seen] == ["pre", "post"]
    assert seen[1][1] == {"rise": 8.0} and seen[1][2]
    first.remove()
    second.remove()
    assert module(fluid_in=STREAM, boost=Quantity(5, "Hz")).outputs.rise == 10.0


def test_a_hook_that_returns_something_else_or_an_unknown_name_is_refused():
    """A hook returns None or a mapping of declared names."""
    module = gain()
    handle = module.register_forward_hook(lambda module, inputs, inlets, state, outputs, outlets: 3)
    with pytest.raises(DefinitionError, match="forward hook returns None or a mapping"):
        module(fluid_in=STREAM, boost=Quantity(5, "Hz"))
    handle.remove()
    module.register_forward_hook(
        lambda module, inputs, inlets, state, outputs, outlets: {"nothing": 1.0}
    )
    with pytest.raises(DefinitionError, match="forward hook returned 'nothing'"):
        module(fluid_in=STREAM, boost=Quantity(5, "Hz"))
    module = gain()
    module.register_forward_pre_hook(lambda module, inputs, inlets, state: {"nothing": 1.0})
    with pytest.raises(DefinitionError, match="pre-hook returned 'nothing'"):
        module(fluid_in=STREAM, boost=Quantity(5, "Hz"))


class Counter(Module):
    """Converted stateful fixture: a count that grows by the rate over the step."""

    def __init__(self):
        """Declare the counter."""
        super().__init__()

        # Controls
        self.rate = Control(float)

        # States
        self.count = State(float, ge=0)

        # Outputs
        self.value = Output(float)

    def forward(self, inputs, inlets, state):
        """Return the count at the start of the step."""
        return dict(value=state["count"]), dict()

    def update(self, inputs, inlets, outlets, state, dt):
        """Return the count at the end of the step."""
        return {"count": state["count"] + inputs["rate"] * dt}


def test_a_stateful_module_takes_its_state_and_update_gives_the_next():
    """The forward reads the state it is given; step returns the next state from update."""
    counter = Counter()
    result = counter(rate=2.0, state={"count": 3.0})
    assert result.outputs.value == 3.0 and result.state == {"count": 3.0}
    counter.rate = 2.0
    next_state, result = counter.step({"count": 3.0}, 10, {})
    assert next_state == {"count": 23.0} and result.outputs.value == 3.0
    assert counter.update({"rate": 2.0}, {}, {}, {"count": 3.0}, 10) == {"count": 23.0}
    with unchanged(counter):
        counter.update({"rate": 2.0}, {}, {}, {"count": 3.0}, 10)
        counter.forward({"rate": 2.0}, {}, {"count": 3.0})


def test_a_state_has_no_default_so_a_call_without_it_is_refused():
    """The case states where a module starts; a missing or an unknown state names the module."""
    with raises(ValidationError, "missing_value", match="counter: state count has no value"):
        Counter()(rate=1.0)
    with raises(ValidationError, "unknown_name", match="counter: unknown state 'cuont'"):
        Counter()(rate=1.0, state={"cuont": 1.0})
    with raises(ValidationError, "out_of_bounds", match="counter.count: invalid state"):
        Counter()(rate=1.0, state={"count": -1.0})
    with pytest.raises(DefinitionError, match="changes only in update"):
        Counter().count = 1.0
    with pytest.raises(
        DefinitionError, match="counter.count: forward and update take a state from state"
    ):
        Counter().count


@pytest.mark.parametrize(
    ("returned", "word", "key"),
    [({}, "missing", "count"), ({"count": 1.0, "extra": 2.0}, "extra", "extra")],
)
def test_returned_state_keys_are_enforced_with_the_module_and_the_key(returned, word, key):
    """A missing or an extra state key from update is an error naming the module and the key."""

    class Wrong(Counter):
        """Returns the wrong keys."""

        def update(self, inputs, inlets, outlets, state, dt):
            """Return the keys of the case."""
            return returned

    wrong = Wrong()
    wrong.rate = 1.0
    with pytest.raises(DefinitionError, match=rf"wrong.*{word} key '{key}'"):
        wrong.step({"count": 0.0}, 1, {})


def test_a_converted_module_that_declares_a_state_default_is_refused():
    """A state has no default in a converted module."""

    class Defaulted(Counter):
        """Declares a default."""

        def __init__(self):
            """Declare the default."""
            super().__init__()
            self.other = State(float, default=0.0)

    with pytest.raises(DefinitionError, match="other: a state has no default"):
        Defaulted()


def test_a_state_is_declared_like_a_parameter_with_its_quantity():
    """A state has a quantity, a unit and bounds, and no value of its own."""

    class Tank(Module):
        """A tank temperature."""

        def __init__(self):
            """Declare the state."""
            super().__init__()

            # States
            self.temperature = State(Temperature, description="Tank temperature")

    assert Tank().states()["temperature"].unit == "K"
    assert Tank().states()["temperature"].default is gm.modules.declarations.UNSET


def test_nothing_in_the_registry_keeps_a_state_default():
    """No class declares a state with a default."""
    for name in gm.modules.names():
        module = gm.modules.get(name)()
        for state in module.states(recurse=False).values():
            assert state.default is gm.modules.declarations.UNSET, name


def test_parameters_come_from_the_call_record_when_it_carries_them():
    """The tracer and a batch of trials give a call its own parameter values; nothing is written."""
    from gemini.modules.callrecord import CallRecord, current_call

    module = gain()
    record = CallRecord(
        module=module, inputs={}, outputs={}, parent=None, parameters={"scale": 10.0}
    )
    token = current_call.set(record)
    try:
        outputs, _ = module.forward({"boost": 3.0, "offset": 0.0}, Ports({"fluid_in": STREAM}), {})
    finally:
        current_call.reset(token)
    assert outputs["rise"] == 30.0 and module.scale == 2.0
    with unchanged(module):
        current_call.set(record)
        try:
            module.forward({"boost": 3.0, "offset": 0.0}, Ports({"fluid_in": STREAM}), {})
        finally:
            current_call.set(None)
