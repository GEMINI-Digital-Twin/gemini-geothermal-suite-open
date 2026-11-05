"""``scan``: the state carried from step to step, failed steps, and the traced door."""

import numpy as np

from gemini import ops
from gemini.ops import kernels, registry


def _body(state, x):
    if x["flow"] < 0:
        raise ValueError("negative flow")
    total = state["total"] + x["flow"] * x["dt"]
    return {"total": total}, [total, x["flow"], [total, -total]]


def test_scan_is_registered_without_a_backend_kernel():
    """The op exists for the graph; the loop is the eager implementation, not a kernel."""
    assert registry.get("scan").kind == "scan"
    assert not hasattr(kernels.get("numpy"), "scan")


def test_a_scan_carries_the_state_and_stacks_the_values():
    """The final state is the carry after the last step and each value is an array over steps."""
    xs = {"flow": [1.0, 2.0, 3.0], "dt": 10.0}
    scanned = ops.control.scan(_body, {"total": 0.0}, xs, 3)
    assert scanned.final == {"total": 60.0}
    assert scanned.ys[0].tolist() == [10.0, 30.0, 60.0]
    assert scanned.ys[1].tolist() == [1.0, 2.0, 3.0]
    assert scanned.ys[2].tolist() == [[10.0, -10.0], [30.0, -30.0], [60.0, -60.0]]
    assert not scanned.failed.any()


def test_a_failed_step_is_nan_and_leaves_the_state_as_it_was():
    """The step after a failure starts from the state before it; its values are NaN, not zero."""
    xs = {"flow": [1.0, -1.0, 3.0], "dt": 10.0}
    scanned = ops.control.scan(_body, {"total": 0.0}, xs, 3)
    assert scanned.failed.tolist() == [False, True, False]
    assert isinstance(scanned.errors(1), ValueError)
    assert scanned.final == {"total": 40.0}
    assert np.isnan(scanned.ys[0][1]) and np.isnan(scanned.ys[2][1]).all()
    assert scanned.ys[0][2] == 40.0


def test_halt_ends_the_scan_at_the_first_step_it_names():
    """The steps after a halting failure fail with its error; the state stays before it."""
    xs = {"flow": [1.0, -1.0, 3.0, 4.0], "dt": 10.0}
    scanned = ops.control.scan(_body, {"total": 0.0}, xs, 4, halt=lambda error: True)
    assert scanned.failed.tolist() == [False, True, True, True]
    assert scanned.errors(3) is scanned.errors(1)
    assert scanned.final == {"total": 10.0}


def test_an_empty_scan_returns_its_start():
    """No step: the state is unchanged and there is nothing stacked."""
    scanned = ops.control.scan(_body, {"total": 5.0}, {"flow": [], "dt": 1.0}, 0)
    assert scanned.final == {"total": 5.0} and scanned.ys == [] and not scanned.failed.size
