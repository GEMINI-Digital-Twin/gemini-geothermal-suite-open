"""The record of a call in progress and the context that holds it."""

import numpy as np

from gemini.modules.callrecord import (
    CallRecord,
    active_call,
    current_call,
    has_arrays,
    no_outputs,
    output_rows,
    outputs_enabled,
    plain_outlet,
)
from gemini.modules.pumps import ESP


def test_no_outputs_is_nested_and_restores_the_setting():
    """Outputs are enabled by default, disabled inside the context, restored after it."""
    assert outputs_enabled()
    with no_outputs():
        with no_outputs():
            assert not outputs_enabled()
        assert not outputs_enabled()
    assert outputs_enabled()


def test_a_record_is_found_through_its_parents_and_keeps_outputs_only_when_recording():
    """``active_call`` walks up the chain; a record that does not record keeps nothing."""
    outer, inner = ESP(), ESP()
    parent = CallRecord(module=outer, inputs={}, outputs={"head": 1.0}, parent=None)
    child = CallRecord(module=inner, inputs={}, outputs={"head": 2.0}, parent=parent)
    token = current_call.set(child)
    try:
        assert active_call(inner) is child and active_call(outer) is parent
        assert active_call(ESP()) is None
    finally:
        current_call.reset(token)
    assert active_call(outer) is None
    silent = CallRecord(
        module=outer, inputs={}, outputs={"head": 1.0}, parent=None, recording=False
    )
    assert silent.kept_outputs() == {} and parent.kept_outputs() == {"head": 1.0}


def test_arrays_over_rows_are_told_from_scalars():
    """A 0-d array is a scalar; an array output has the rows of its distinct values."""
    assert has_arrays({}, {"a": np.array([1.0, 2.0])})
    assert not has_arrays({}, {"a": np.array(1.0), "b": 2.0})
    assert output_rows(np.array([1.0, 1.0, 2.0])) == [1.0, 2.0]
    assert output_rows(3.0) is None
    assert plain_outlet(np.float64(2.0)) == 2.0 and type(plain_outlet(np.float64(2.0))) is float
