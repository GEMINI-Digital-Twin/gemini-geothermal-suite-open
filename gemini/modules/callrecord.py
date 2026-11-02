"""The record of one module call in progress, and the helpers that read and shape its values.

The values of one call (resolved controls and boundaries, recorded outputs, the state it starts
from and the results of child calls) live in a ``CallRecord`` held in the ``current_call`` context
variable while the call runs; it is the only per-call state, so a module holds none.
``no_outputs()`` is the only other context setting.
"""

from contextvars import ContextVar
from dataclasses import dataclass, field
from itertools import repeat

import numpy as np

from gemini import ops
from gemini._utils.context import ContextSetting
from gemini.streams.flows import Stream
from gemini.streams.ports import Ports

current_call = ContextVar("module_call", default=None)
outputs_enabled_setting = ContextVar("module_outputs_enabled", default=True)
in_trial = ContextVar("module_in_trial", default=False)


def no_outputs():
    """Skip output computation and hooks within a nestable context or decorator."""
    return ContextSetting(outputs_enabled_setting, lambda current: False)


def outputs_enabled():
    """Return whether the current context records computed outputs."""
    return outputs_enabled_setting.get()


class ScalarParameters(dict):
    """Parameter values of an eager call as the scope gives them, wrapped on first read."""

    def __init__(self, module):
        """Read parameters of ``module``."""
        super().__init__()
        self._module = module

    def __missing__(self, name):
        """Return the stored value of parameter ``name`` wrapped, and keep it for this call."""
        value = self[name] = ops.scope.wrap(self._module._parameter_value(name))
        return value


def holds_array(value):
    """Return whether a port value holds an array over rows; a 0-d array is a scalar."""
    if isinstance(value, list):
        return any(holds_array(item) for item in value)
    if isinstance(value, Stream):
        return any(holds_array(item) for item in (value.m_dot, value.T, value.p))
    return isinstance(value, np.ndarray) and bool(value.ndim)


def has_arrays(inlets, inputs):
    """Return whether a call holds arrays over rows, which leaves its scope unwrapped.

    A 0-d array is a scalar: ops give one under a forced NumPy backend.
    """
    return any(holds_array(value) for value in (*inlets.values(), *inputs.values()))


def numpy_value(value):
    """Return a port value for the eager scope: a stream's fields or a power as ``np.float64``."""
    if isinstance(value, list):
        return [numpy_value(item) for item in value]
    return value._numpy() if isinstance(value, Stream) else ops.scope.wrap(value)


def numpy_ports(inlets):
    """Return ``inlets`` with stream fields and powers as ``np.float64`` for the eager scope."""
    return Ports._trusted(
        {name: numpy_value(value) for name, value in inlets.items()}, inlets._path
    )


def recorded_output(call, value):
    """Return a recorded output as the call's physics sees it: wrapped in a wrapping call."""
    if not call.wrapping:
        return value
    return np.float64(value) if type(value) is float else ops.scope.wrap(value)


def restored(returned, scoped, inlets):
    """Return the outlets of ``forward`` with a passed-through scoped inlet restored."""
    if scoped is inlets or not isinstance(returned, dict):
        return returned
    originals = {id(scoped[name]): inlets[name] for name in inlets}
    return {name: originals.get(id(value), value) for name, value in returned.items()}


def scalar_output(declaration, value):
    """Return an output of a forced backend: a 0-d NaN is the ``None`` of ``X | None``."""
    is_scalar_array = isinstance(value, np.ndarray) and not value.ndim
    if is_scalar_array and declaration.accepts_none() and value != value:
        return None
    return value


def row_output(declaration, item):
    """Return one row of an array output: a NaN is the ``None`` of ``X | None``."""
    if isinstance(item, float) and item != item and declaration.accepts_none():
        return None
    return item


def is_column(item):
    """Return whether ``item`` is an array of rows."""
    return isinstance(item, np.ndarray) and item.ndim > 0


def output_rows(value):
    """Return the rows of an array output (a column's values once) or of a list holding arrays.

    A call that made one row returns ``None``.
    """
    if not isinstance(value, list):
        if not is_column(value):
            return None
        rows = value.tolist()
        return list(dict.fromkeys(rows)) if value.ndim == 1 else rows
    if not any(is_column(item) for item in value):
        return None
    columns = [item.tolist() if is_column(item) else repeat(item) for item in value]
    return [list(row) for row in zip(*columns)]


def plain_outlet(value):
    """Return an outlet value with plain scalars; a ``Failed`` field raises its error."""
    if isinstance(value, list):
        return [plain_outlet(item) for item in value]
    return value._plain() if isinstance(value, Stream) else ops.scope.plain(value)


@dataclass
class CallRecord:
    """Values of one module call in progress.

    ``outputs`` holds what ``forward`` returned, validated. ``recording`` is
    false when outputs are disabled: the values are not validated and the result drops them.
    ``call_records`` collects the results of every child call made during this call, in call
    order. ``parent`` is the enclosing call.
    ``state`` holds the state ``forward`` gets: the own states of a stateful module, the state
    tree of a plant, else an empty dict.
    A traced call (a call of the compiler) sets ``parameters`` to the traced parameter values
    that replace the stored ones, and records outputs without validating them. ``trace`` is the
    running trace of the compiler: a call made while it is set is recorded through
    ``trace.child`` instead of being evaluated. ``wrapping`` marks an eager call whose
    physics gets NumPy scalars (``gemini.ops.scope``).
    """

    module: object
    inputs: dict
    outputs: dict
    parent: "CallRecord | None"
    recording: bool = True
    state: dict | None = None
    call_records: list = field(default_factory=list)
    parameters: dict | None = None
    trace: object | None = None
    wrapping: bool = False
    drawn: dict = field(default_factory=dict)

    def kept_outputs(self):
        """Return the outputs the result of this call holds."""
        return self.outputs if self.recording or in_trial.get() else {}

    def owned_by(self, module):
        """Return the innermost call of ``module`` in this chain, or ``None``."""
        call = self
        while call is not None and call.module is not module:
            call = call.parent
        return call


def active_call(module):
    """Return the running call of ``module``, or ``None`` outside its calls."""
    current = current_call.get()
    return current.owned_by(module) if current is not None else None
