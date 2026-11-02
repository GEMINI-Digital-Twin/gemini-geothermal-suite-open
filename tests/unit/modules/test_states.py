"""The state tree of a module: its building, merging, checking and stepping."""

import pytest

from gemini.errors import DefinitionError, ValidationError
from gemini.modules.control import PIDController
from gemini.modules.states import merged, nested
from tests.fixtures import si
from tests.fixtures.errors import raises
from tests.fixtures.purity import unchanged
from tests.unit.modules.test_module_contract import Counter

FRESH = {"integral": 0.0, "previous_error": 0.0, "previous_step": 0.0}


def test_a_state_tree_nests_by_module_path_and_merges_in_place():
    """A dotted path is nested; the root path holds the states of the module itself."""
    values = {"storage": {"temperature": 300.0}, "filters.hot": {"loading": 0.1}}
    tree = nested(values)
    assert tree == {"storage": {"temperature": 300.0}, "filters": {"hot": {"loading": 0.1}}}
    advanced = {"filters": {"hot": {"loading": 0.2}}}
    assert merged(tree, advanced) == {
        "storage": {"temperature": 300.0},
        "filters": {"hot": {"loading": 0.2}},
    }
    assert tree["filters"]["hot"]["loading"] == 0.1
    assert nested({"": {"count": 1.0}}) == {"count": 1.0}


def test_a_converted_module_has_no_initial_state_of_its_own():
    """Asking for it raises ``missing_value``: the case states where a run starts."""
    counter = Counter()
    assert counter.stateful and counter._has_state()
    with raises(ValidationError, "missing_value", match="counter: state count"):
        counter.initial_state()


def test_step_runs_forward_then_update_and_keeps_the_start_state():
    """The step gives the result of forward at the start state and the next state of update."""
    counter = Counter()
    counter.rate = 1.5
    start = {"count": 2.0}
    next_state, result = counter.step(start, 4, {})
    assert result.outputs.value == 2.0 and next_state == {"count": 8.0}
    assert start == {"count": 2.0}
    with raises(ValidationError, "invalid_design", match="expected a positive step"):
        counter.step(start, 0, {})


def test_update_validates_what_it_returns_against_the_declared_state():
    """A value outside the bounds of the state is an error naming the state."""

    class Negative(Counter):
        """Steps below zero."""

        def update(self, inputs, inlets, outlets, state, dt):
            """Return a negative count."""
            return {"count": -1.0}

    negative = Negative()
    negative.rate = 1.0
    with raises(ValidationError, "out_of_bounds", match="negative.count: invalid state"):
        negative.step(start := {"count": 1.0}, 1, {})
    assert start == {"count": 1.0}


def test_the_pid_update_and_forward_leave_the_controller_unchanged():
    """The worked stateful example is pure."""
    pid = si.set_params(
        PIDController(),
        "",
        dict(
            proportional_gain=2.0,
            integral_time=100.0,
            derivative_time=10.0,
            minimum_output=0.0,
            maximum_output=1.0,
            direction="reverse",
        ),
    )
    inputs = {"setpoint": 1.0, "measurement": 0.8}
    with unchanged(pid):
        outputs, outlets = pid.forward(inputs, {}, FRESH)
        state = pid.update(inputs, {}, {}, FRESH, 60)
    assert outputs["command"] == pytest.approx(0.4) and outlets == {}
    assert state["integral"] == pytest.approx(2 * 60 / 100 * 0.2)
    assert state["previous_step"] == 60
    with pytest.raises(DefinitionError, match="take a state from state"):
        pid.integral
